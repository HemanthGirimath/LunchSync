from typing import Any

from langgraph.types import Command

from app.graph.build import lunch_graph


def _config(event_id: int) -> dict:
    return {"configurable": {"thread_id": str(event_id)}}


def _pending_interrupt(event_id: int) -> dict | None:
    state = lunch_graph.get_state(_config(event_id))
    for task in state.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


async def start(event_id: int, initial_state: dict[str, Any]) -> dict | None:
    await lunch_graph.ainvoke(initial_state, _config(event_id))
    return _pending_interrupt(event_id)


async def resume(event_id: int, resume_value: Any) -> dict | None:
    await lunch_graph.ainvoke(Command(resume=resume_value), _config(event_id))
    return _pending_interrupt(event_id)


def current_values(event_id: int) -> dict:
    return lunch_graph.get_state(_config(event_id)).values
