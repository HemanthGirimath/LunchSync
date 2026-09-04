import datetime

from sqlalchemy.orm import Session

from app.graph import runner
from app.mcp import swiggy_client as swiggy
from app.models import LunchEvent, Order, Poll

CUISINE_OPTIONS = ["Biryani", "Pizza", "Thali", "Rolls", "Chinese"]
DIETARY_OPTIONS = ["veg", "non_veg", "pure_veg"]


def create_event_with_dietary_poll(
    db: Session, location: str, budget_per_head: float, headcount_estimate: int, poll_minutes: int
) -> LunchEvent:
    event = LunchEvent(
        location=location, budget_per_head=budget_per_head, headcount_estimate=headcount_estimate
    )
    db.add(event)
    db.flush()

    closes_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=poll_minutes)
    poll = Poll(event_id=event.id, type="dietary", options=DIETARY_OPTIONS, responses=[], closes_at=closes_at)
    db.add(poll)
    db.commit()
    db.refresh(event)

    from app.scheduler import schedule_poll_close

    schedule_poll_close(poll.id, "dietary", closes_at)
    return event


async def close_dietary_poll(db: Session, event_id: int, poll_minutes: int = 2) -> None:
    poll = db.query(Poll).filter_by(event_id=event_id, type="dietary", closed=False).first()
    if not poll:
        return
    poll.closed = True

    counts = {"veg": 0, "non_veg": 0, "pure_veg": 0}
    for r in poll.responses:
        if r["choice"] in counts:
            counts[r["choice"]] += 1

    event = db.get(LunchEvent, event_id)
    event.veg_count = counts["veg"]
    event.non_veg_count = counts["non_veg"]
    event.pure_veg_count = counts["pure_veg"]
    event.status = "cuisine_poll_open"

    closes_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=poll_minutes)
    cuisine_poll = Poll(event_id=event_id, type="cuisine", options=CUISINE_OPTIONS, responses=[], closes_at=closes_at)
    db.add(cuisine_poll)
    db.commit()
    db.refresh(cuisine_poll)

    from app.scheduler import schedule_poll_close

    schedule_poll_close(cuisine_poll.id, "cuisine", closes_at)


async def close_cuisine_poll(db: Session, event_id: int) -> None:
    poll = db.query(Poll).filter_by(event_id=event_id, type="cuisine", closed=False).first()
    if not poll:
        return
    poll.closed = True

    tally: dict[str, int] = {}
    for r in poll.responses:
        tally[r["choice"]] = tally.get(r["choice"], 0) + 1
    winning = max(tally, key=tally.get) if tally else poll.options[0]

    event = db.get(LunchEvent, event_id)
    event.winning_cuisine = winning
    event.status = "awaiting_restaurant_pick"
    db.commit()

    pending = await runner.start(
        event_id,
        {
            "event_id": event_id,
            "location": event.location,
            "budget_per_head": event.budget_per_head,
            "veg_count": event.veg_count,
            "non_veg_count": event.non_veg_count,
            "pure_veg_count": event.pure_veg_count,
            "cuisine": winning,
        },
    )
    event.pending_interrupt = pending or {}
    db.commit()


async def pick_restaurant(db: Session, event: LunchEvent, restaurant_id: str) -> None:
    pending = await runner.resume(event.id, restaurant_id)
    values = runner.current_values(event.id)
    if values.get("selected_restaurant"):
        event.selected_restaurant_name = values["selected_restaurant"]["name"]
    _apply_pending(db, event, pending)


async def submit_cart_decision(db: Session, event: LunchEvent, decision: dict) -> None:
    pending = await runner.resume(event.id, decision)
    _apply_pending(db, event, pending)


def _apply_pending(db: Session, event: LunchEvent, pending: dict | None) -> None:
    event.pending_interrupt = pending or {}
    if pending and pending.get("type") == "approve_cart":
        event.status = "awaiting_cart_approval"
        event.cart_items = pending["cart_items"]
        event.total_cost = pending["total_cost"]
    elif pending is None:
        values = runner.current_values(event.id)
        event.status = "order_placed"
        order = Order(
            event_id=event.id,
            restaurant_name=values["selected_restaurant"]["name"],
            swiggy_order_id=values["order_id"],
            cart_items=values["cart_items"],
            total_cost=values["total_cost"],
            status="confirmed",
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        from app.scheduler import schedule_order_tracking

        schedule_order_tracking(order.id, values["order_id"])
    db.commit()


async def poll_order_tracking_once(db: Session, order_id: int) -> bool:
    order = db.get(Order, order_id)
    if not order:
        return True
    result = await swiggy.track_food_order(order.swiggy_order_id)
    order.status = result["status"]
    if result["delivered"]:
        event = db.get(LunchEvent, order.event_id)
        event.status = "delivered"
    db.commit()
    return result["delivered"]
