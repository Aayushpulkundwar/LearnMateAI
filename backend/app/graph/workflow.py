from langgraph.graph import StateGraph, END
from app.graph.state import QueryState
from app.graph.nodes import (
    retrieve_node,
    grade_relevance_node,
    refuse_node,
    generate_node,
    cite_node,
)


def route_relevance(state: QueryState) -> str:
    """Conditional edge routing decision based on heuristic relevance check."""
    if state.get("is_relevant", False):
        return "generate"
    return "refuse"


# Assemble the state graph
builder = StateGraph(QueryState)

# Add nodes
builder.add_node("retrieve", retrieve_node)
builder.add_node("grade_relevance", grade_relevance_node)
builder.add_node("refuse", refuse_node)
builder.add_node("generate", generate_node)
builder.add_node("cite", cite_node)

# Set entry point
builder.set_entry_point("retrieve")

# Connect retrieve -> grade_relevance
builder.add_edge("retrieve", "grade_relevance")

# Conditional routing from grade_relevance
builder.add_conditional_edges(
    "grade_relevance",
    route_relevance,
    {
        "generate": "generate",
        "refuse": "refuse",
    }
)

# Connect generate -> cite -> END
builder.add_edge("generate", "cite")
builder.add_edge("cite", END)

# Connect refuse -> END
builder.add_edge("refuse", END)

# Compile into runnable graph
app_graph = builder.compile()
