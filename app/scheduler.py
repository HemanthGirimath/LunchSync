import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()


def schedule_poll_close(poll_id: int, poll_type: str, run_date: datetime.datetime) -> None:
    scheduler.add_job(
        _run_poll_close,
        trigger="date",
        run_date=run_date,
        args=[poll_id, poll_type],
        id=f"close-{poll_type}-{poll_id}",
        replace_existing=True,
    )


def schedule_order_tracking(order_id: int, swiggy_order_id: str) -> None:
    scheduler.add_job(
        _run_tracking_tick,
        trigger="interval",
        seconds=5,
        args=[order_id],
        id=f"track-{order_id}",
        replace_existing=True,
    )


async def _run_poll_close(poll_id: int, poll_type: str) -> None:
    from app import services
    from app.db import SessionLocal
    from app.models import Poll

    db = SessionLocal()
    try:
        poll = db.get(Poll, poll_id)
        if not poll or poll.closed:
            return
        if poll_type == "dietary":
            await services.close_dietary_poll(db, poll.event_id)
        else:
            await services.close_cuisine_poll(db, poll.event_id)
    finally:
        db.close()


async def _run_tracking_tick(order_id: int) -> None:
    from app import services
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        delivered = await services.poll_order_tracking_once(db, order_id)
        if delivered:
            scheduler.remove_job(f"track-{order_id}")
    finally:
        db.close()
