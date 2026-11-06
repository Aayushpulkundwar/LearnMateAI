"""Post-gate selection of retrieval evidence for grounded LLM context."""

from typing import Iterable, Mapping


def select_context_chunks(
    chunks: Iterable[Mapping],
    *,
    minimum_similarity: float,
    maximum_similarity_drop: float,
    minimum_lexical_score: float = 0.08,
) -> list[Mapping]:
    """Keep useful rank-ordered evidence without changing question relevance."""
    ranked_chunks = []
    seen = set()
    for chunk in chunks:
        content = ' '.join(str(chunk.get('content', '')).casefold().split())
        key = content or str(chunk.get('id'))
        if key not in seen:
            ranked_chunks.append(chunk)
            seen.add(key)
    if not ranked_chunks:
        return []

    selected = [ranked_chunks[0]]
    best_similarity = max(float(chunk.get('similarity_score', 0.0)) for chunk in ranked_chunks)
    for chunk in ranked_chunks[1:]:
        similarity = float(chunk.get("similarity_score", 0.0))
        lexical_match = chunk.get("lexical_rank") is not None and float(chunk.get("lexical_score", 0.0)) >= minimum_lexical_score
        if (
            (similarity >= minimum_similarity and best_similarity - similarity <= maximum_similarity_drop)
            or lexical_match
        ):
            selected.append(chunk)
    return selected
