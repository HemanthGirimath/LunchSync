"""
Stand-ins for the real Swiggy MCP Food Server tools, matching the tool
names/signatures from the LunchSync spec: search_restaurants,
get_restaurant_menu, update_food_cart, place_food_order, track_food_order.

Swap `app.mcp.swiggy_client` in once Swiggy grants MCP access — the graph
nodes in app/graph/nodes.py only import from this module, so the swap is a
one-line change per node.
"""

import random
import uuid

_CUISINE_RESTAURANTS = {
    "Biryani": ["Paradise Biryani", "Behrouz Biryani", "Meghana Foods"],
    "Pizza": ["Domino's", "La Pino'z", "Oven Story"],
    "Thali": ["Rajdhani Thali", "Anna Poorna", "Swati Snacks"],
    "Rolls": ["Kathi Junction", "Wrap Chef", "Roll Baba"],
    "Chinese": ["Mainland China", "China Bistro", "Wok On"],
}

_MENU_TEMPLATES = {
    "veg": [
        ("Veg Thali", 180),
        ("Paneer Butter Masala + Rice", 220),
        ("Veg Biryani", 190),
        ("Veg Fried Rice + Manchurian", 200),
        ("Margherita Pizza (Regular)", 250),
    ],
    "non_veg": [
        ("Chicken Thali", 230),
        ("Chicken Biryani", 240),
        ("Butter Chicken + Rice", 260),
        ("Chicken Fried Rice", 210),
        ("Chicken Pizza (Regular)", 290),
    ],
}

_order_state: dict[str, list[str]] = {}

_TRACKING_STATES = [
    "Order confirmed",
    "Restaurant is preparing your food",
    "Rider picked up your order",
    "Arriving in 5 minutes",
    "Delivered",
]


async def search_restaurants(cuisine: str, location: str, budget_per_head: float) -> list[dict]:
    names = _CUISINE_RESTAURANTS.get(cuisine, ["Local Kitchen", "Tasty Bites", "City Diner"])
    results = []
    for name in names:
        est_cost = round(budget_per_head * random.uniform(0.75, 0.98), -1)
        results.append(
            {
                "id": str(uuid.uuid4())[:8],
                "name": name,
                "cuisine": cuisine,
                "rating": round(random.uniform(3.9, 4.7), 1),
                "estimated_per_person_cost": est_cost,
                "location": location,
            }
        )
    return sorted(results, key=lambda r: r["rating"], reverse=True)


async def get_restaurant_menu(restaurant_id: str) -> list[dict]:
    menu = []
    for category, items in _MENU_TEMPLATES.items():
        for name, price in items:
            menu.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "name": name,
                    "price": price,
                    "veg": category == "veg",
                }
            )
    return menu


async def update_food_cart(restaurant_id: str, items: list[dict]) -> dict:
    cart_id = str(uuid.uuid4())[:8]
    total = sum(i["price"] * i["quantity"] for i in items)
    return {"cart_id": cart_id, "restaurant_id": restaurant_id, "items": items, "total": total}


async def place_food_order(cart_id: str, delivery_address: str) -> dict:
    order_id = f"SWG-{str(uuid.uuid4())[:8].upper()}"
    _order_state[order_id] = []
    return {"swiggy_order_id": order_id, "status": "confirmed"}


async def track_food_order(swiggy_order_id: str) -> dict:
    history = _order_state.setdefault(swiggy_order_id, [])
    next_index = min(len(history), len(_TRACKING_STATES) - 1)
    status = _TRACKING_STATES[next_index]
    history.append(status)
    return {"swiggy_order_id": swiggy_order_id, "status": status, "delivered": status == "Delivered"}
