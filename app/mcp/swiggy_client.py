"""
Swiggy MCP Client for Food Server tools.
Calls the official Swiggy MCP Food server at https://mcp.swiggy.com/food
using the OAuth 2.1 access token obtained via PKCE.
"""

import logging
from typing import Any, Dict, List, Optional
import httpx

from app.auth import get_token
from app.config import SWIGGY_BASE_URL

logger = logging.getLogger(__name__)

FOOD_SERVER_URL = f"{SWIGGY_BASE_URL}/food"


async def call_swiggy_mcp_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Executes a tool call on Swiggy Food MCP Server using the authenticated Bearer token."""
    token = get_token()
    if not token:
        raise RuntimeError(
            "Swiggy access token not found or expired. Please connect your Swiggy account at /auth/swiggy/login."
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments,
        },
        "id": 1,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(FOOD_SERVER_URL, json=payload, headers=headers)
        if response.status_code == 401:
            raise RuntimeError("Swiggy token rejected (401). Please re-authenticate at /auth/swiggy/login.")
        response.raise_for_status()
        data = response.json()

    if "error" in data:
        err_msg = data["error"].get("message", str(data["error"]))
        raise RuntimeError(f"Swiggy MCP error in {name}: {err_msg}")

    result = data.get("result", {})
    return result


async def get_addresses() -> List[Dict[str, Any]]:
    """Fetches user's saved addresses on Swiggy."""
    result = await call_swiggy_mcp_tool("get_addresses", {})
    return result.get("data", result.get("addresses", []))


async def search_restaurants(cuisine: str, location: str, budget_per_head: float) -> List[Dict[str, Any]]:
    """Searches for open restaurants serving the requested cuisine."""
    arguments = {"query": cuisine}
    # Resolve user address if possible
    try:
        addresses = await get_addresses()
        if addresses:
            selected_addr = next((a for a in addresses if a.get("label") == "Home"), addresses[0])
            arguments["addressId"] = selected_addr.get("id") or selected_addr.get("addressId")
    except Exception as exc:
        logger.warning(f"Could not fetch address before searching restaurants: {exc}")

    result = await call_swiggy_mcp_tool("search_restaurants", arguments)
    items = result.get("data", {}).get("restaurants", []) or result.get("restaurants", [])

    candidates = []
    for r in items:
        # Filter for open restaurants as recommended in docs
        if r.get("availabilityStatus", "OPEN") != "OPEN":
            continue
        candidates.append({
            "id": str(r.get("id")),
            "name": r.get("name", "Unknown Restaurant"),
            "cuisine": cuisine,
            "rating": float(r.get("rating", 4.0)),
            "estimated_per_person_cost": float(r.get("costForTwo", budget_per_head * 2) / 2),
            "location": location,
        })
    return sorted(candidates, key=lambda x: x["rating"], reverse=True)


async def get_restaurant_menu(restaurant_id: str) -> List[Dict[str, Any]]:
    """Retrieves items on a restaurant's menu."""
    result = await call_swiggy_mcp_tool("get_restaurant_menu", {"restaurantId": restaurant_id})
    raw_items = result.get("data", {}).get("items", []) or result.get("items", [])

    menu = []
    for item in raw_items:
        menu.append({
            "id": str(item.get("id")),
            "name": item.get("name"),
            "price": float(item.get("price", 0)),
            "veg": bool(item.get("isVeg") or item.get("veg", False)),
        })
    return menu


async def update_food_cart(restaurant_id: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Builds/updates cart with selected items."""
    swiggy_items = [{"itemId": str(i.get("id", "")), "quantity": int(i.get("quantity", 1))} for i in items]
    result = await call_swiggy_mcp_tool(
        "update_food_cart",
        {"restaurantId": restaurant_id, "items": swiggy_items},
    )
    cart_data = result.get("data", result)
    total = sum(i.get("price", 0) * i.get("quantity", 1) for i in items)
    return {
        "cart_id": str(cart_data.get("cartId", "cart-1")),
        "restaurant_id": restaurant_id,
        "items": items,
        "total": total,
    }


async def place_food_order(cart_id: str, delivery_address: str) -> Dict[str, Any]:
    """Places the order via Swiggy MCP (COD payment)."""
    result = await call_swiggy_mcp_tool("place_food_order", {"paymentMethod": "COD"})
    order_data = result.get("data", result)
    order_id = order_data.get("orderId") or order_data.get("swiggy_order_id") or "SWG-ORDER"
    return {
        "swiggy_order_id": str(order_id),
        "status": order_data.get("status", "confirmed"),
    }


async def track_food_order(swiggy_order_id: str) -> Dict[str, Any]:
    """Tracks live delivery status of an order."""
    result = await call_swiggy_mcp_tool("track_food_order", {"orderId": swiggy_order_id})
    status_data = result.get("data", result)
    status = status_data.get("status", "Order confirmed")
    delivered = status.lower() == "delivered" or status_data.get("delivered", False)
    return {
        "swiggy_order_id": swiggy_order_id,
        "status": status,
        "delivered": delivered,
    }
