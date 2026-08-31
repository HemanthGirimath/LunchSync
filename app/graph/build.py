from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    await_cart_approval_node,
    await_restaurant_choice_node,
    build_cart_node,
    get_menu_node,
    place_order_node,
    search_restaurants_node,
)
from app.graph.state import LunchState

_checkpointer = MemorySaver()


def build_graph():
    graph = StateGraph(LunchState)
    graph.add_node("search_restaurants", search_restaurants_node)
    graph.add_node("await_restaurant_choice", await_restaurant_choice_node)
    graph.add_node("get_menu", get_menu_node)
    graph.add_node("build_cart", build_cart_node)
    graph.add_node("await_cart_approval", await_cart_approval_node)
    graph.add_node("place_order", place_order_node)

    graph.add_edge(START, "search_restaurants")
    graph.add_edge("search_restaurants", "await_restaurant_choice")
    graph.add_edge("await_restaurant_choice", "get_menu")
    graph.add_edge("get_menu", "build_cart")
    graph.add_edge("build_cart", "await_cart_approval")
    graph.add_edge("await_cart_approval", "place_order")
    graph.add_edge("place_order", END)

    return graph.compile(checkpointer=_checkpointer)


lunch_graph = build_graph()
