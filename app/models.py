import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class LunchEvent(Base):
    __tablename__ = "lunch_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location: Mapped[str] = mapped_column(String, default="Bangalore Office")
    budget_per_head: Mapped[float] = mapped_column(Float)
    headcount_estimate: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="dietary_poll_open")
    # dietary_poll_open -> cuisine_poll_open -> awaiting_restaurant_pick
    # -> awaiting_cart_approval -> order_placed -> delivered

    veg_count: Mapped[int] = mapped_column(Integer, default=0)
    non_veg_count: Mapped[int] = mapped_column(Integer, default=0)
    pure_veg_count: Mapped[int] = mapped_column(Integer, default=0)

    winning_cuisine: Mapped[str] = mapped_column(String, default="")
    selected_restaurant_name: Mapped[str] = mapped_column(String, default="")

    pending_interrupt: Mapped[dict] = mapped_column(JSON, default=dict)
    cart_items: Mapped[list] = mapped_column(JSON, default=list)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )


class Poll(Base):
    __tablename__ = "polls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("lunch_events.id"))
    type: Mapped[str] = mapped_column(String)  # "dietary" | "cuisine"
    options: Mapped[list] = mapped_column(JSON, default=list)
    responses: Mapped[list] = mapped_column(JSON, default=list)  # [{"name": str, "choice": str}]
    closes_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    closed: Mapped[bool] = mapped_column(default=False)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("lunch_events.id"))
    restaurant_name: Mapped[str] = mapped_column(String)
    swiggy_order_id: Mapped[str] = mapped_column(String)
    cart_items: Mapped[list] = mapped_column(JSON, default=list)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="placed")
    placed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )


class SwiggyToken(Base):
    __tablename__ = "swiggy_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    access_token: Mapped[str] = mapped_column(String)
    expires_at: Mapped[float] = mapped_column(Float)
    scope: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

