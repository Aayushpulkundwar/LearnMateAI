"""Post-gate selection of retrieval evidence for grounded LLM context."""

from typing import Iterable, Mapping


def select_context_chunks(
    chunks: Iterable[Mapping],
    *,
    minimum_similarity: float,
    maximum_similarity_drop: float,
) -> list[Mapping]:
    """Keep useful rank-ordered evidence without changing question relevance."""
    ranked_chunks = list(chunks)
    if not ranked_chunks:
        return []

    selected = [ranked_chunks[0]]
    best_similarity = float(ranked_chunks[0].get("similarity_score", 0.0))
    for chunk in ranked_chunks[1:]:
        similarity = float(chunk.get("similarity_score", 0.0))
        if (
            similarity >= minimum_similarity
            and best_similarity - similarity <= maximum_similarity_drop
        ):
            selected.append(chunk)
    return selected
