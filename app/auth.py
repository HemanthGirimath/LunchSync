import base64
import hashlib
import os
import secrets
import time
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from app.config import SWIGGY_BASE_URL, SWIGGY_CLIENT_ID

# In-memory storage for pending PKCE states: state -> (verifier, created_at)
_pending_states: dict[str, tuple[str, float]] = {}

# In-memory storage for Swiggy token
_token_store: dict[str, Any] = {
    "access_token": None,
    "expires_at": 0.0,
    "scope": None,
}


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_pkce() -> tuple[str, str]:
    """Generates (code_verifier, code_challenge) per RFC 7636 and Swiggy MCP OAuth 2.1 specs."""
    verifier = _base64url_encode(secrets.token_bytes(32))
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = _base64url_encode(digest)
    return verifier, challenge


def create_authorization_flow(redirect_uri: str) -> tuple[str, str]:
    """Creates a state & PKCE challenge, stores the verifier, and returns (state, authorize_url)."""
    state = secrets.token_urlsafe(24)
    verifier, challenge = generate_pkce()

    # Clean up stale states older than 10 minutes
    now = time.time()
    stale_keys = [k for k, (_, ts) in _pending_states.items() if now - ts > 600]
    for k in stale_keys:
        _pending_states.pop(k, None)

    _pending_states[state] = (verifier, now)

    params = {
        "response_type": "code",
        "client_id": SWIGGY_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "scope": "mcp:tools",
    }
    authorize_url = f"{SWIGGY_BASE_URL}/auth/authorize?{urlencode(params)}"
    return state, authorize_url


def pop_verifier_for_state(state: str) -> Optional[str]:
    """Retrieves and removes the stored verifier for the state."""
    entry = _pending_states.pop(state, None)
    return entry[0] if entry else None


async def exchange_code_for_token(code: str, verifier: str, redirect_uri: str) -> dict:
    """Exchanges authorization_code + code_verifier for an access token via POST /auth/token."""
    url = f"{SWIGGY_BASE_URL}/auth/token"
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()

    # Store token in memory
    save_token(data)
    return data


def save_token(token_data: dict) -> None:
    """Saves the access token and calculated expiry timestamp to memory and DB."""
    access_token = token_data.get("access_token")
    expires_in = token_data.get("expires_in", 432000)
    expires_at = time.time() + float(expires_in)
    scope = token_data.get("scope", "")

    _token_store["access_token"] = access_token
    _token_store["expires_at"] = expires_at
    _token_store["scope"] = scope

    try:
        from app.db import SessionLocal
        from app.models import SwiggyToken

        db = SessionLocal()
        token_record = db.query(SwiggyToken).order_by(SwiggyToken.id.desc()).first()
        if not token_record:
            token_record = SwiggyToken(
                access_token=access_token,
                expires_at=expires_at,
                scope=scope,
            )
            db.add(token_record)
        else:
            token_record.access_token = access_token
            token_record.expires_at = expires_at
            token_record.scope = scope
        db.commit()
        db.close()
    except Exception as exc:
        print(f"[auth] Failed to persist token to database: {exc}")


def get_token() -> Optional[str]:
    """Returns the current valid access token from memory or DB, or None if missing/expired."""
    token = _token_store.get("access_token")
    expires_at = _token_store.get("expires_at", 0.0)

    # If memory is empty (e.g. after container restart), load latest token from DB
    if not token or expires_at <= time.time():
        try:
            from app.db import SessionLocal
            from app.models import SwiggyToken

            db = SessionLocal()
            token_record = db.query(SwiggyToken).order_by(SwiggyToken.id.desc()).first()
            if token_record and token_record.expires_at > time.time():
                _token_store["access_token"] = token_record.access_token
                _token_store["expires_at"] = token_record.expires_at
                _token_store["scope"] = token_record.scope
                token = token_record.access_token
                expires_at = token_record.expires_at
            db.close()
        except Exception as exc:
            print(f"[auth] Failed to load token from database: {exc}")

    # Re-auth/refresh if <= 60 seconds remain as recommended by Swiggy docs
    if token and expires_at > (time.time() + 60):
        return token
    return None


def is_authenticated() -> bool:
    """Checks if a valid, unexpired token is available."""
    return get_token() is not None
