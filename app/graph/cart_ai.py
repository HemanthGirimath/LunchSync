from pydantic import BaseModel, Field

from app.config import ANTHROPIC_API_KEY


class CartSelection(BaseModel):
    veg_item_name: str = Field(description="Exact name of the chosen veg menu item")
    non_veg_item_name: str = Field(description="Exact name of the chosen non-veg menu item")
    reasoning: str = Field(description="One sentence on why these give the best value within budget")


def _best_value_fallback(items: list[dict], budget_per_head: float) -> dict:
    affordable = [i for i in items if i["price"] <= budget_per_head]
    pool = affordable or sorted(items, key=lambda i: i["price"])[:1]
    return max(pool, key=lambda i: i["price"])


def _deterministic_pick(menu: list[dict], budget_per_head: float) -> tuple[dict, dict]:
    veg_items = [i for i in menu if i["veg"]]
    non_veg_items = [i for i in menu if not i["veg"]]
    return _best_value_fallback(veg_items, budget_per_head), _best_value_fallback(non_veg_items, budget_per_head)


async def choose_items(menu: list[dict], budget_per_head: float) -> tuple[dict, dict]:
    """Returns (veg_item, non_veg_item). Uses Claude when available, with a
    deterministic best-value fallback if there's no API key or the model
    picks something invalid."""
    veg_fallback, non_veg_fallback = _deterministic_pick(menu, budget_per_head)

    if not ANTHROPIC_API_KEY:
        return veg_fallback, non_veg_fallback

    try:
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0).with_structured_output(
            CartSelection
        )
        menu_lines = "\n".join(f"- {i['name']} (Rs.{i['price']}, {'veg' if i['veg'] else 'non-veg'})" for i in menu)
        result: CartSelection = await llm.ainvoke(
            "Pick the single best-value veg item and single best-value non-veg item from this "
            f"menu, each within a per-person budget of Rs.{budget_per_head}. Prefer items closer "
            f"to the budget over cheaper ones, as long as they don't exceed it.\n\nMenu:\n{menu_lines}"
        )
    except Exception:
        return veg_fallback, non_veg_fallback

    by_name = {i["name"]: i for i in menu}
    veg_choice = by_name.get(result.veg_item_name)
    non_veg_choice = by_name.get(result.non_veg_item_name)

    if not veg_choice or not veg_choice["veg"] or veg_choice["price"] > budget_per_head:
        veg_choice = veg_fallback
    if not non_veg_choice or non_veg_choice["veg"] or non_veg_choice["price"] > budget_per_head:
        non_veg_choice = non_veg_fallback

    return veg_choice, non_veg_choice
