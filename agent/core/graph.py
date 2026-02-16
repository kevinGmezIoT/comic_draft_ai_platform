from langgraph.graph import StateGraph, END
from .models import AgentState
from .nodes import (
    ingest_and_rag,
    story_understanding,
    world_model_builder,
    planner,
    image_generator,
    layout_designer,
    page_merger,
    balloon_generator
)

# Export nodes for worker.py compatibility
__all__ = [
    'create_comic_graph',
    'ingest_and_rag',
    'story_understanding',
    'world_model_builder',
    'planner',
    'image_generator',
    'layout_designer',
    'page_merger',
    'balloon_generator'
]

def create_comic_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("ingest", ingest_and_rag)
    workflow.add_node("story_understanding", story_understanding)
    workflow.add_node("world_model_builder", world_model_builder)
    workflow.add_node("planner", planner)
    workflow.add_node("layout_designer", layout_designer)
    workflow.add_node("generator", image_generator)
    workflow.add_node("balloons", balloon_generator)
    workflow.add_node("merger", page_merger)

    # Router de entrada para regeneración selectiva
    def router_entry(state: AgentState):
        if state.get("action") == "regenerate_panel":
            return "generator"
        if state.get("action") == "regenerate_merge":
            return "merger"
        return "ingest"

    workflow.set_conditional_entry_point(
        router_entry,
        {
            "generator": "generator",
            "merger": "merger",
            "ingest": "ingest"
        }
    )

    workflow.add_edge("ingest", "story_understanding")
    workflow.add_edge("story_understanding", "world_model_builder")
    workflow.add_edge("world_model_builder", "planner")
    workflow.add_edge("planner", "layout_designer")

    # Camino condicional según plan_only
    def should_continue(state: AgentState):
        if state.get("plan_only"):
            return "end"
        return "continue"

    workflow.add_conditional_edges(
        "layout_designer",
        should_continue,
        {
            "end": END,
            "continue": "generator"
        }
    )

    # Para regeneración selectiva, después del generador terminamos (o podemos seguir a globos si quisiéramos)
    def post_generator_router(state: AgentState):
        if state.get("action") == "regenerate_panel":
            return "end"
        return "continue"

    workflow.add_conditional_edges(
        "generator",
        post_generator_router,
        {
            "end": END,
            "continue": "balloons"
        }
    )

    workflow.add_edge("balloons", "merger")
    workflow.add_edge("merger", END)

    return workflow.compile()
