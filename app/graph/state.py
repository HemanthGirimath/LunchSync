from typing import Any, TypedDict


class LunchState(TypedDict, total=False):
    event_id: int
    location: str
    budget_per_head: float
    veg_count: int
    non_veg_count: int
    pure_veg_count: int
    cuisine: str

    restaurant_candidates: list[dict[str, Any]]
    selected_restaurant: dict[str, Any]

    menu: list[dict[str, Any]]
    cart_items: list[dict[str, Any]]
    total_cost: float

    order_id: str
