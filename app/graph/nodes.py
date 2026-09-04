from langgraph.types import interrupt

from app.graph.cart_ai import choose_items
from app.graph.state import LunchState
from app.mcp import swiggy_client as swiggy


async def search_restaurants_node(state: LunchState) -> dict:
    candidates = await swiggy.search_restaurants(
        cuisine=state["cuisine"],
        location=state["location"],
        budget_per_head=state["budget_per_head"],
    )
    return {"restaurant_candidates": candidates[:10]}


def await_restaurant_choice_node(state: LunchState) -> dict:
    choice_id = interrupt({"type": "pick_restaurant", "candidates": state["restaurant_candidates"]})
    selected = next(
        (c for c in state["restaurant_candidates"] if c["id"] == choice_id),
        state["restaurant_candidates"][0],
    )
    return {"selected_restaurant": selected}


async def get_menu_node(state: LunchState) -> dict:
    cuisine = state.get("cuisine", "")
    menu = await swiggy.get_restaurant_menu(state["selected_restaurant"]["id"], cuisine=cuisine)
    return {"menu": menu}


async def build_cart_node(state: LunchState) -> dict:
    veg_item, non_veg_item = await choose_items(state["menu"], state["budget_per_head"])
    veg_qty = state["veg_count"] + state["pure_veg_count"]
    non_veg_qty = state["non_veg_count"]

    cart_items = []
    if veg_qty > 0:
        cart_items.append({**veg_item, "quantity": veg_qty})
    if non_veg_qty > 0:
        cart_items.append({**non_veg_item, "quantity": non_veg_qty})

    total_cost = sum(i["price"] * i["quantity"] for i in cart_items)
    return {"cart_items": cart_items, "total_cost": total_cost}


def await_cart_approval_node(state: LunchState) -> dict:
    decision = interrupt(
        {
            "type": "approve_cart",
            "cart_items": state["cart_items"],
            "total_cost": state["total_cost"],
            "menu": state.get("menu", []),
        }
    )
    result = {}
    if decision and isinstance(decision, dict):
        if decision.get("cart_items"):
            items = decision["cart_items"]
            result["cart_items"] = items
            result["total_cost"] = sum(i["price"] * i["quantity"] for i in items)
        if "is_simulation" in decision:
            result["is_simulation"] = bool(decision["is_simulation"])
    return result


async def place_order_node(state: LunchState) -> dict:
    is_sim = state.get("is_simulation", True)  # Safe default to simulation
    if is_sim:
        import uuid
        sim_order_id = f"TEST-SWG-{uuid.uuid4().hex[:8].upper()}"
        return {"order_id": sim_order_id}

    cart = await swiggy.update_food_cart(state["selected_restaurant"]["id"], state["cart_items"])
    result = await swiggy.place_food_order(cart["cart_id"], state["location"])
    return {"order_id": result["swiggy_order_id"]}
