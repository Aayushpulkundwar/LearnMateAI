"""Page-aware PDF text extraction for document ingestion."""

from dataclasses import dataclass
from io import BytesIO
from typing import List

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PDFExtractionError(ValueError):
    """Raised when a PDF cannot be read or does not contain usable text."""


@dataclass(frozen=True)
class ExtractedPDFPage:
    """Text extracted from one physical PDF page."""

    page_number: int
    text: str


def extract_pdf_pages(pdf_bytes: bytes) -> List[ExtractedPDFPage]:
    """Extract text while preserving every source-page boundary.

    Empty pages are represented with an empty ``text`` value. A document with
    no usable text on *any* page is rejected so image-only/scanned PDFs are not
    silently treated as text documents.
    """
    if not pdf_bytes:
        raise PDFExtractionError("PDF is empty.")

    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=False)
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise PDFExtractionError("Encrypted PDFs are not supported.")

        pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # pypdf uses multiple parser exceptions here.
                raise PDFExtractionError(
                    f"Could not extract text from PDF page {page_number}."
                ) from exc
            pages.append(ExtractedPDFPage(page_number=page_number, text=text.strip()))
    except PDFExtractionError:
        raise
    except (PdfReadError, OSError, ValueError, TypeError) as exc:
        raise PDFExtractionError("PDF is malformed or unreadable.") from exc

    if not pages:
        raise PDFExtractionError("PDF contains no pages.")
    if not any(page.text for page in pages):
        raise PDFExtractionError("PDF contains no extractable text; OCR is required.")

    return pages
