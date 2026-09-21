"""Deterministic context construction for grounded tutor generation."""
from typing import Iterable, Mapping


def build_grounded_context(chunks: Iterable[Mapping], max_chars: int) -> tuple[str, list[Mapping]]:
    """Render rank-ordered retrieved chunks within a character budget.

    The source headers are deliberately kept alongside each chunk so retrieved
    document text cannot blur into application instructions or other sources.
    """
    sections = []
    included_chunks = []
    used = 0
    for rank, chunk in enumerate(chunks, start=1):
        metadata = [f"Document: {chunk.get('document_title', 'Unknown document')}"]
        if chunk.get("chapter") is not None:
            metadata.append(f"Chapter: {chunk['chapter']}")
        if chunk.get("page_number") is not None:
            metadata.append(f"Page: {chunk['page_number']}")
        if chunk.get("chunk_index") is not None:
            metadata.append(f"Chunk: {chunk['chunk_index']}")
        header = f"[Source {rank}]\n" + "\n".join(metadata) + "\nContent:\n"
        remaining = max_chars - used - len(header) - 2
        if remaining <= 0: break
        content = str(chunk.get("content", ""))[:remaining].rstrip()
        if not content: continue
        section = header + content
        sections.append(section)
        included_chunks.append(chunk)
        used += len(section) + 2
        if len(content) < len(str(chunk.get("content", ""))): break
    return "\n\n".join(sections), included_chunks
