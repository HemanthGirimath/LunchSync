from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import auth as swiggy_auth
from app import services
from app.config import BASE_URL
from app.db import Base, SessionLocal, engine
from app.models import LunchEvent, Order, Poll
from app.scheduler import scheduler

app = FastAPI(title="LunchSync")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

Base.metadata.create_all(bind=engine)


@app.on_event("startup")
async def on_startup():
    if not scheduler.running:
        scheduler.start()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/auth/swiggy/login")
def swiggy_login():
    redirect_uri = f"{BASE_URL.rstrip('/')}/auth/swiggy/callback"
    state, auth_url = swiggy_auth.create_authorization_flow(redirect_uri)
    return RedirectResponse(auth_url, status_code=307)


@app.get("/auth/swiggy/status")
def swiggy_status():
    return {
        "authenticated": swiggy_auth.is_authenticated(),
        "has_token": swiggy_auth.get_token() is not None,
    }


@app.get("/auth/swiggy/callback")
async def swiggy_oauth_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        return templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "events": [],
                "error": f"OAuth authorization failed: {error}",
                "swiggy_connected": False,
            },
            status_code=400,
        )

    if not code or not state:
        return templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "events": [],
                "error": "Missing authorization code or state.",
                "swiggy_connected": False,
            },
            status_code=400,
        )

    verifier = swiggy_auth.pop_verifier_for_state(state)
    if not verifier:
        return templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "events": [],
                "error": "Invalid or expired session state. Please click 'Connect Swiggy' to try again.",
                "swiggy_connected": False,
            },
            status_code=400,
        )

    redirect_uri = f"{BASE_URL.rstrip('/')}/auth/swiggy/callback"
    try:
        await swiggy_auth.exchange_code_for_token(
            code=code,
            verifier=verifier,
            redirect_uri=redirect_uri,
        )
        return RedirectResponse(url="/?swiggy_connected=1", status_code=303)
    except Exception as exc:
        return templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "events": [],
                "error": f"Token exchange failed: {str(exc)}",
                "swiggy_connected": False,
            },
            status_code=400,
        )



@app.get("/auth/swiggy/logout")
@app.post("/auth/swiggy/logout")
def swiggy_logout():
    swiggy_auth.logout()
    return RedirectResponse(url="/?logged_out=1", status_code=303)


@app.get("/")
def home(request: Request):
    is_conn = swiggy_auth.is_authenticated()
    events = []
    if is_conn:
        db = SessionLocal()
        events = db.query(LunchEvent).order_by(LunchEvent.id.desc()).limit(10).all()
        db.close()

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "events": events,
            "swiggy_connected": is_conn,
        },
    )


@app.post("/events")
def create_event(
    request: Request,
    location: str = Form(...),
    budget_per_head: float = Form(...),
    headcount_estimate: int = Form(...),
    poll_minutes: int = Form(2),
):
    if not swiggy_auth.is_authenticated():
        return templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "events": [],
                "error": "Please connect your Swiggy account before creating a lunch event.",
                "swiggy_connected": False,
            },
            status_code=403,
        )

    db = SessionLocal()
    event = services.create_event_with_dietary_poll(db, location, budget_per_head, headcount_estimate, poll_minutes)
    event_id = event.id
    db.close()
    return RedirectResponse(f"/events/{event_id}", status_code=303)


@app.get("/events/{event_id}")
def event_dashboard(request: Request, event_id: int):
    db = SessionLocal()
    event = db.get(LunchEvent, event_id)
    dietary_poll = db.query(Poll).filter_by(event_id=event_id, type="dietary").first()
    cuisine_poll = db.query(Poll).filter_by(event_id=event_id, type="cuisine").first()
    order = db.query(Order).filter_by(event_id=event_id).first()
    db.close()
    return templates.TemplateResponse(
        "event_dashboard.html",
        {
            "request": request,
            "event": event,
            "dietary_poll": dietary_poll,
            "cuisine_poll": cuisine_poll,
            "order": order,
            "base_url": BASE_URL,
            "swiggy_connected": swiggy_auth.is_authenticated(),
        },
    )


@app.post("/events/{event_id}/update-location")
def update_event_location(event_id: int, location: str = Form(...)):
    db = SessionLocal()
    event = db.get(LunchEvent, event_id)
    if event and location.strip():
        event.location = location.strip()
        db.commit()
    db.close()
    return RedirectResponse(f"/events/{event_id}", status_code=303)


@app.get("/events/{event_id}/poll-counts")
def event_poll_counts(event_id: int):
    db = SessionLocal()
    dietary_poll = db.query(Poll).filter_by(event_id=event_id, type="dietary").first()
    cuisine_poll = db.query(Poll).filter_by(event_id=event_id, type="cuisine").first()
    event = db.get(LunchEvent, event_id)
    data = {
        "status": event.status if event else "",
        "dietary_count": len(dietary_poll.responses) if dietary_poll else 0,
        "cuisine_count": len(cuisine_poll.responses) if cuisine_poll else 0,
        "veg_count": event.veg_count if event else 0,
        "non_veg_count": event.non_veg_count if event else 0,
        "pure_veg_count": event.pure_veg_count if event else 0,
    }
    db.close()
    return data


@app.get("/poll/{poll_id}")
def poll_page(request: Request, poll_id: int):
    db = SessionLocal()
    poll = db.get(Poll, poll_id)
    db.close()
    return templates.TemplateResponse(
        "poll_page.html",
        {
            "request": request,
            "poll": poll,
            "submitted": False,
            "swiggy_connected": swiggy_auth.is_authenticated(),
        },
    )


@app.post("/poll/{poll_id}")
def poll_submit(request: Request, poll_id: int, name: str = Form(...), choice: str = Form(...)):
    db = SessionLocal()
    poll = db.get(Poll, poll_id)
    clean_name = name.strip()
    if poll and not poll.closed:
        poll.responses = [*poll.responses, {"name": clean_name, "choice": choice}]
        db.commit()
    db.close()
    return templates.TemplateResponse(
        "poll_page.html",
        {
            "request": request,
            "poll": poll,
            "submitted": True,
            "swiggy_connected": swiggy_auth.is_authenticated(),
        },
    )


@app.post("/polls/{poll_id}/close")
async def close_poll(poll_id: int):
    db = SessionLocal()
    poll = db.get(Poll, poll_id)
    event_id = poll.event_id
    if poll.type == "dietary":
        await services.close_dietary_poll(db, event_id)
    else:
        await services.close_cuisine_poll(db, event_id)
    db.close()
    return RedirectResponse(f"/events/{event_id}", status_code=303)


@app.post("/events/{event_id}/resolve-tiebreak")
async def resolve_tiebreak(event_id: int, chosen_cuisine: str = Form(...)):
    db = SessionLocal()
    event = db.get(LunchEvent, event_id)
    if event and event.status == "awaiting_cuisine_tiebreak":
        await services.resolve_cuisine_tiebreak(db, event, chosen_cuisine)
    db.close()
    return RedirectResponse(f"/events/{event_id}", status_code=303)


@app.post("/events/{event_id}/pick-restaurant")
async def pick_restaurant(event_id: int, restaurant_id: str = Form(...)):
    db = SessionLocal()
    event = db.get(LunchEvent, event_id)
    await services.pick_restaurant(db, event, restaurant_id)
    db.close()
    return RedirectResponse(f"/events/{event_id}", status_code=303)


@app.post("/events/{event_id}/approve-cart")
async def approve_cart(request: Request, event_id: int):
    form = await request.form()
    db = SessionLocal()
    event = db.get(LunchEvent, event_id)

    is_simulation = form.get("order_type") != "live"
    decision = {"approved": True, "is_simulation": is_simulation}
    item_count = int(form.get("item_count", 0))
    if item_count > 0:
        items = []
        for i in range(item_count):
            qty = int(form.get(f"qty_{i}", 0))
            if qty > 0:
                items.append(
                    {
                        "name": form.get(f"name_{i}"),
                        "price": float(form.get(f"price_{i}", 0)),
                        "veg": form.get(f"veg_{i}") == "True",
                        "quantity": qty,
                    }
                )
        if items:
            decision["cart_items"] = items

    await services.submit_cart_decision(db, event, decision)
    db.close()
    return RedirectResponse(f"/events/{event_id}", status_code=303)
