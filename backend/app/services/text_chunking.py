"""Deterministic, page-aware text chunking for extracted PDF pages."""

from dataclasses import dataclass
import re
from typing import Iterable, List

from app.services.pdf_extraction import ExtractedPDFPage


@dataclass(frozen=True)
class TextChunk:
    """A text segment that never crosses a physical PDF-page boundary."""

    page_number: int
    content: str
    chunk_index: int


def _find_chunk_end(text: str, start: int, chunk_size: int) -> int:
    """Choose a natural boundary near the configured character limit."""
    limit = min(len(text), start + chunk_size)
    if limit == len(text):
        return limit

    # Avoid very short chunks when a nearby paragraph or sentence boundary is
    # available only near the beginning of the window.
    minimum_natural_boundary = start + (chunk_size // 2)
    window = text[start:limit]

    paragraph_break = window.rfind("\n\n")
    if paragraph_break >= minimum_natural_boundary - start:
        return start + paragraph_break

    newline_break = window.rfind("\n")
    if newline_break >= minimum_natural_boundary - start:
        return start + newline_break

    sentence_breaks = list(re.finditer(r"[.!?](?=\s|$)", window))
    if sentence_breaks and sentence_breaks[-1].end() >= minimum_natural_boundary - start:
        return start + sentence_breaks[-1].end()

    word_break = window.rfind(" ")
    if word_break > 0:
        return start + word_break

    # A single token longer than chunk_size has no safe word boundary. This is
    # the only case where a hard cut is necessary to guarantee progress.
    return limit


def _next_start(text: str, start: int, end: int, overlap: int) -> int:
    """Move to an earlier word boundary to preserve useful overlap safely."""
    candidate = max(start + 1, end - overlap)
    while candidate > start and not text[candidate - 1].isspace():
        candidate -= 1
    while candidate < end and text[candidate].isspace():
        candidate += 1
    return candidate if candidate < end else end


def _chunk_page(text: str, page_number: int, chunk_size: int, chunk_overlap: int) -> List[TextChunk]:
    normalized = text.strip()
    if not normalized:
        return []

    chunks: List[TextChunk] = []
    start = 0
    while start < len(normalized):
        end = _find_chunk_end(normalized, start, chunk_size)
        content = normalized[start:end].strip()
        if content and (not chunks or content != chunks[-1].content):
            chunks.append(TextChunk(page_number=page_number, content=content, chunk_index=-1))
        if end >= len(normalized):
            break
        next_start = _next_start(normalized, start, end, chunk_overlap)
        start = next_start if next_start > start else end
    return chunks


def chunk_extracted_pages(
    pages: Iterable[ExtractedPDFPage],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> List[TextChunk]:
    """Chunk each page independently and assign document-monotonic indexes."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be greater than or equal to zero and less than chunk_size.")

    chunks: List[TextChunk] = []
    for page in pages:
        chunks.extend(_chunk_page(page.text, page.page_number, chunk_size, chunk_overlap))

    return [
        TextChunk(page_number=chunk.page_number, content=chunk.content, chunk_index=index)
        for index, chunk in enumerate(chunks)
    ]
