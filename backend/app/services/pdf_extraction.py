"""Page-aware PDF text extraction for document ingestion."""

from dataclasses import dataclass
from io import BytesIO
from typing import List, Protocol

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pypdf.errors import LimitReachedError

MAX_INPUT_BYTES = 25 * 1024 * 1024
MAX_PAGES = 500
MAX_PAGE_CHARS = 100_000
MAX_TOTAL_CHARS = 2_000_000
EXTRACTION_TIMEOUT_SECONDS = 120
EXTRACTION_MEMORY_BYTES = 1024 * 1024 * 1024


def extract_pdf_pages_mupdf(pdf_bytes: bytes) -> List["ExtractedPDFPage"]:
    """Fast text-only extraction; call inside the bounded Linux subprocess.

    Open once and exclude image payloads. Avoid pypdf layout construction and
    its retained allocations before MuPDF sees image-heavy textbook pages.
    """
    import pymupdf

    if not pdf_bytes or len(pdf_bytes) > MAX_INPUT_BYTES:
        raise PDFExtractionError("PDF is empty or exceeds extraction input size limit.")
    pages = []
    total = 0
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        if document.needs_pass:
            raise PDFExtractionError("Encrypted PDFs are not supported.")
        if not 0 < document.page_count <= MAX_PAGES:
            raise PDFExtractionError("PDF has no pages or exceeds extraction page count limit.")
        for index in range(document.page_count):
            try:
                text = document.load_page(index).get_text(
                    "text", sort=True,
                    flags=pymupdf.TEXTFLAGS_TEXT & ~pymupdf.TEXT_PRESERVE_IMAGES,
                ).strip()
                total += len(text)
                if len(text) > MAX_PAGE_CHARS or total > MAX_TOTAL_CHARS:
                    raise PDFExtractionError("Extraction output text limit exceeded.")
            except Exception as exc:
                raise PDFExtractionError(
                    f"MuPDF failed on PDF page {index + 1} ({type(exc).__name__})."
                ) from exc
            pages.append(ExtractedPDFPage(index + 1, text))
    if not any(page.text for page in pages):
        raise PDFExtractionError("PDF contains no extractable text; OCR is required.")
    return pages


def _extract_limit_page(pdf_bytes: bytes, page_number: int) -> str:
    """MuPDF text extraction, used only after pypdf refuses decompression.

    Production callers run this inside the bounded extraction subprocess.
    The original bytes and physical page index are retained.
    """
    import pymupdf

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        text = document.load_page(page_number - 1).get_text("text", sort=True)
    if not text.strip():
        raise PDFExtractionError(f"Fallback returned no text for PDF page {page_number}.")
    return text


class PDFExtractionError(ValueError):
    """Raised when a PDF cannot be read or does not contain usable text."""


class OCRExtractionError(PDFExtractionError):
    """Raised when optional local OCR cannot produce usable page text."""


@dataclass(frozen=True)
class ExtractedPDFPage:
    """Text extracted from one physical PDF page."""

    page_number: int
    text: str
    used_ocr: bool = False


class OCRPageExtractor(Protocol):
    """Small boundary that keeps OCR optional and independently testable."""

    def extract_page(self, pdf_bytes: bytes, page_number: int) -> str:
        """Return text for a one-based PDF page number."""


class LocalTesseractOCREngine:
    """Optional, local-only OCR using PyMuPDF rendering and Tesseract.

    Dependencies are intentionally imported lazily so text PDFs do not require
    OCR packages. Install ``requirements-ocr.txt`` plus the native Tesseract
    executable to enable this engine.
    """

    def extract_page(self, pdf_bytes: bytes, page_number: int) -> str:
        try:
            import fitz
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise OCRExtractionError(
                "OCR fallback requires optional PyMuPDF, Pillow, and pytesseract dependencies."
            ) from exc
        try:
            document = fitz.open(stream=pdf_bytes, filetype="pdf")
            try:
                page = document.load_page(page_number - 1)
                pixmap = page.get_pixmap(dpi=300, alpha=False)
                image = Image.open(BytesIO(pixmap.tobytes("png")))
                return (pytesseract.image_to_string(image) or "").strip()
            finally:
                document.close()
        except OCRExtractionError:
            raise
        except Exception as exc:
            raise OCRExtractionError(f"OCR failed for PDF page {page_number}.") from exc


def _extract_layout_text(page) -> str:
    """Prefer pypdf's layout-preserving mode without breaking older PDFs.

    Layout mode retains spacing/line structure needed by educational tables and
    headings.  Some malformed or older PDFs reject that mode, where the normal
    pypdf extractor remains the safe compatibility fallback.
    """
    try:
        return page.extract_text(extraction_mode="layout") or ""
    except (TypeError, ValueError):
        return page.extract_text() or ""


def extract_pdf_pages(pdf_bytes: bytes, *, ocr_engine: OCRPageExtractor | None = None) -> List[ExtractedPDFPage]:
    """Extract text while preserving every source-page boundary.

    Empty pages are represented with an empty ``text`` value. A document with
    no usable text on *any* page is rejected so image-only/scanned PDFs are not
    silently treated as text documents.
    """
    if not pdf_bytes:
        raise PDFExtractionError("PDF is empty.")
    if len(pdf_bytes) > MAX_INPUT_BYTES:
        raise PDFExtractionError("PDF exceeds extraction input size limit.")

    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=False)
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise PDFExtractionError("Encrypted PDFs are not supported.")

        if len(reader.pages) > MAX_PAGES:
            raise PDFExtractionError("PDF exceeds extraction page count limit.")
        pages = []
        total_chars = 0
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                try:
                    text = _extract_layout_text(page)
                except LimitReachedError:
                    text = _extract_limit_page(pdf_bytes, page_number)
                total_chars += len(text)
                if len(text) > MAX_PAGE_CHARS or total_chars > MAX_TOTAL_CHARS:
                    raise PDFExtractionError("Extraction output text limit exceeded.")
            except Exception as exc:  # pypdf uses multiple parser exceptions here.
                raise PDFExtractionError(
                    f"Could not extract text from PDF page {page_number} ({type(exc).__name__})."
                ) from exc
            pages.append(ExtractedPDFPage(page_number=page_number, text=text.strip()))
    except PDFExtractionError:
        raise
    except (PdfReadError, OSError, ValueError, TypeError) as exc:
        raise PDFExtractionError("PDF is malformed or unreadable.") from exc

    if not pages:
        raise PDFExtractionError("PDF contains no pages.")
    if ocr_engine:
        recovered_pages = []
        for page in pages:
            if page.text:
                recovered_pages.append(page)
                continue
            try:
                text = ocr_engine.extract_page(pdf_bytes, page.page_number).strip()
            except OCRExtractionError:
                raise
            except Exception as exc:
                raise OCRExtractionError(f"OCR failed for PDF page {page.page_number}.") from exc
            recovered_pages.append(ExtractedPDFPage(page.page_number, text, used_ocr=bool(text)))
        pages = recovered_pages

    if not any(page.text for page in pages):
        message = "PDF contains no extractable text after OCR." if ocr_engine else "PDF contains no extractable text; OCR is required."
        raise PDFExtractionError(message)

    return pages


def extract_pdf_pages_isolated(pdf_bytes: bytes, *, enable_ocr: bool = False) -> List[ExtractedPDFPage]:
    """Hard wall-time/memory limits for Linux Celery ingestion; fail closed elsewhere.

    A fresh interpreter contains native parser allocations and is killed on timeout.
    stdout is a size-bounded JSON file, never an unbounded pipe in worker memory.
    """
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys
    import tempfile

    if not pdf_bytes or len(pdf_bytes) > MAX_INPUT_BYTES:
        raise PDFExtractionError("PDF is empty or exceeds extraction input size limit.")
    if sys.platform != "linux":
        raise PDFExtractionError("Resource-bounded ingestion requires the Linux worker container.")
    with tempfile.TemporaryDirectory(prefix="learnmate-pdf-") as directory:
        source = Path(directory) / "input.pdf"
        output = Path(directory) / "pages.json"
        source.write_bytes(pdf_bytes)
        with open(os.devnull, "wb") as discarded:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "app.services.pdf_extraction_worker", str(source), str(output), str(int(enable_ocr))],
                    stdout=discarded, stderr=discarded, timeout=EXTRACTION_TIMEOUT_SECONDS,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise PDFExtractionError("PDF extraction exceeded 120-second processing limit.") from exc
        if not output.exists() or output.stat().st_size > 16_000_000:
            raise PDFExtractionError("PDF extraction failed within resource limits; no complete output.")
        payload = json.loads(output.read_text(encoding="utf-8"))
        if result.returncode or "error" in payload:
            raise PDFExtractionError(payload.get("error", "PDF extraction worker failed."))
        return [ExtractedPDFPage(**page) for page in payload["pages"]]
