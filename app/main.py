from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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


@app.get("/auth/swiggy/callback")
def swiggy_oauth_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")
    print(f"[swiggy oauth callback] code={code} state={state} error={error}")
    return {
        "message": "LunchSync received the Swiggy OAuth redirect.",
        "code_received": bool(code),
        "error": error,
    }


@app.get("/")
def home(request: Request):
    db = SessionLocal()
    events = db.query(LunchEvent).order_by(LunchEvent.id.desc()).limit(10).all()
    db.close()
    return templates.TemplateResponse("home.html", {"request": request, "events": events})


@app.post("/events")
def create_event(
    request: Request,
    location: str = Form(...),
    budget_per_head: float = Form(...),
    headcount_estimate: int = Form(...),
    poll_minutes: int = Form(2),
):
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
        },
    )


@app.get("/poll/{poll_id}")
def poll_page(request: Request, poll_id: int):
    db = SessionLocal()
    poll = db.get(Poll, poll_id)
    db.close()
    return templates.TemplateResponse("poll_page.html", {"request": request, "poll": poll, "submitted": False})


@app.post("/poll/{poll_id}")
def poll_submit(request: Request, poll_id: int, name: str = Form(...), choice: str = Form(...)):
    db = SessionLocal()
    poll = db.get(Poll, poll_id)
    if poll and not poll.closed:
        poll.responses = [*poll.responses, {"name": name, "choice": choice}]
        db.commit()
    db.close()
    return templates.TemplateResponse("poll_page.html", {"request": request, "poll": poll, "submitted": True})


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

    decision = {"approved": True}
    if form.get("mode") == "edit":
        item_count = int(form.get("item_count", 0))
        items = []
        for i in range(item_count):
            items.append(
                {
                    "name": form[f"name_{i}"],
                    "price": float(form[f"price_{i}"]),
                    "veg": form[f"veg_{i}"] == "True",
                    "quantity": int(form[f"qty_{i}"]),
                }
            )
        decision = {"cart_items": items}

    await services.submit_cart_decision(db, event, decision)
    db.close()
    return RedirectResponse(f"/events/{event_id}", status_code=303)
