import unittest
from unittest.mock import Mock, patch
from pypdf.errors import LimitReachedError

from app.services.pdf_extraction import OCRExtractionError, PDFExtractionError, _extract_layout_text, extract_pdf_pages


def build_pdf(page_texts: list[str]) -> bytes:
    """Create a minimal text PDF without adding a PDF-generation dependency."""
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "",  # Filled after page object numbers are known.
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    page_ids = []
    for text in page_texts:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET" if text else ""
        content_id = len(objects) + 1
        objects.append(f"<< /Length {len(content.encode('latin-1'))} >>\nstream\n{content}\nendstream")
        page_id = len(objects) + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        )
        page_ids.append(page_id)
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {len(page_ids)} >>"

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_number} 0 obj\n{body}\nendobj\n".encode("latin-1"))
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    output.extend("".join(f"{offset:010d} 00000 n \n" for offset in offsets[1:]).encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


class PDFExtractionTests(unittest.TestCase):
    def test_mupdf_full_document_preserves_pages_three_and_eight(self):
        from app.services.pdf_extraction import extract_pdf_pages_mupdf
        with patch("app.services.pdf_extraction.PdfReader", side_effect=AssertionError("pypdf must not allocate before MuPDF")):
            pages = extract_pdf_pages_mupdf(build_pdf([f"Page {n} text" for n in range(1, 10)]))
        self.assertEqual([p.page_number for p in pages], list(range(1, 10)))
        self.assertEqual(pages[2].text, "Page 3 text")
        self.assertEqual(pages[7].text, "Page 8 text")

    def test_mupdf_failure_on_page_three_or_eight_never_returns_partial_pages(self):
        from app.services.pdf_extraction import extract_pdf_pages_mupdf
        for failed_page in (3, 8):
            document = Mock(page_count=9, needs_pass=False)
            document.load_page.return_value.get_text.side_effect = ["text"] * (failed_page - 1) + [MemoryError()]
            with patch("pymupdf.open") as opened:
                opened.return_value.__enter__.return_value = document
                with self.assertRaisesRegex(PDFExtractionError, f"page {failed_page}.*MemoryError"):
                    extract_pdf_pages_mupdf(build_pdf(["text"]))

    def test_mupdf_input_page_and_output_limits(self):
        from app.services.pdf_extraction import extract_pdf_pages_mupdf
        data = build_pdf(["Text one", "Text two"])
        for limit, value in (("MAX_INPUT_BYTES", 1), ("MAX_PAGES", 1), ("MAX_PAGE_CHARS", 1), ("MAX_TOTAL_CHARS", 1)):
            with patch("app.services.pdf_extraction." + limit, value):
                with self.assertRaises(PDFExtractionError):
                    extract_pdf_pages_mupdf(data)

    def test_decompression_limit_fallback_retains_physical_page(self):
        with patch("app.services.pdf_extraction._extract_layout_text", side_effect=["Page one", LimitReachedError("limit")]), patch("app.services.pdf_extraction._extract_limit_page", return_value="Recovered page two") as fallback:
            data = build_pdf(["one", "two"])
            pages = extract_pdf_pages(data)
        fallback.assert_called_once_with(data, 2)
        self.assertEqual([(p.page_number, p.text) for p in pages], [(1, "Page one"), (2, "Recovered page two")])

    def test_fallback_failure_never_returns_partial_document(self):
        with patch("app.services.pdf_extraction._extract_layout_text", side_effect=LimitReachedError("limit")), patch("app.services.pdf_extraction._extract_limit_page", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(PDFExtractionError, "page 1"):
                extract_pdf_pages(build_pdf(["one"]))

    def test_input_page_and_text_limits(self):
        with patch("app.services.pdf_extraction.MAX_INPUT_BYTES", 1):
            with self.assertRaisesRegex(PDFExtractionError, "input size"):
                extract_pdf_pages(b"xx")
        with patch("app.services.pdf_extraction.MAX_PAGES", 1):
            with self.assertRaisesRegex(PDFExtractionError, "page count"):
                extract_pdf_pages(build_pdf(["a", "b"]))
        with patch("app.services.pdf_extraction.MAX_PAGE_CHARS", 1):
            with self.assertRaisesRegex(PDFExtractionError, "page 1"):
                extract_pdf_pages(build_pdf(["too much text"]))

    def test_real_mupdf_fallback_extracts_text(self):
        from app.services.pdf_extraction import _extract_limit_page
        self.assertIn("Actual fallback text", _extract_limit_page(build_pdf(["Actual fallback text"]), 1))

    def test_isolated_timeout_is_explicit(self):
        import subprocess
        from app.services.pdf_extraction import extract_pdf_pages_isolated
        with patch("sys.platform", "linux"), patch("subprocess.run", side_effect=subprocess.TimeoutExpired("extract", 120)):
            with self.assertRaisesRegex(PDFExtractionError, "processing limit"):
                extract_pdf_pages_isolated(build_pdf(["text"]))

    def test_prefers_layout_preserving_extraction(self):
        page = Mock()
        page.extract_text.return_value = "Heading    Value\nA          1"

        self.assertEqual(_extract_layout_text(page), "Heading    Value\nA          1")
        page.extract_text.assert_called_once_with(extraction_mode="layout")

    def test_falls_back_when_layout_mode_is_not_supported(self):
        page = Mock()
        page.extract_text.side_effect = [TypeError("unsupported"), "plain text"]

        self.assertEqual(_extract_layout_text(page), "plain text")
        self.assertEqual(page.extract_text.call_count, 2)
    def test_extracts_actual_text_from_multiple_pages_with_page_numbers(self):
        pages = extract_pdf_pages(build_pdf(["Actual first page text", "Actual second page text"]))

        self.assertEqual([page.page_number for page in pages], [1, 2])
        self.assertEqual([page.text for page in pages], ["Actual first page text", "Actual second page text"])

    def test_empty_page_is_preserved_without_corrupting_other_pages(self):
        pages = extract_pdf_pages(build_pdf(["Before blank page", "", "After blank page"]))

        self.assertEqual([page.page_number for page in pages], [1, 2, 3])
        self.assertEqual(pages[1].text, "")
        self.assertEqual(pages[2].text, "After blank page")

    def test_all_empty_pages_are_rejected_as_no_extractable_text(self):
        with self.assertRaisesRegex(PDFExtractionError, "no extractable text"):
            extract_pdf_pages(build_pdf(["", ""]))

    def test_scanned_pdf_uses_optional_ocr_with_original_page_provenance(self):
        class OCR:
            def extract_page(self, _pdf_bytes, page_number):
                return {1: "Scanned first page", 2: "Scanned second page"}[page_number]

        pages = extract_pdf_pages(build_pdf(["", ""]), ocr_engine=OCR())

        self.assertEqual([page.page_number for page in pages], [1, 2])
        self.assertEqual([page.text for page in pages], ["Scanned first page", "Scanned second page"])
        self.assertTrue(all(page.used_ocr for page in pages))

    def test_mixed_pdf_uses_ocr_only_for_image_only_page(self):
        class OCR:
            calls = []

            def extract_page(self, _pdf_bytes, page_number):
                self.calls.append(page_number)
                return "Recovered scan"

        ocr = OCR()
        pages = extract_pdf_pages(build_pdf(["Digital content", ""]), ocr_engine=ocr)

        self.assertEqual([page.text for page in pages], ["Digital content", "Recovered scan"])
        self.assertFalse(pages[0].used_ocr)
        self.assertTrue(pages[1].used_ocr)
        self.assertEqual(ocr.calls, [2])

    def test_ocr_failure_is_controlled_and_identifies_the_page(self):
        class OCR:
            def extract_page(self, _pdf_bytes, _page_number):
                raise RuntimeError("engine unavailable")

        with self.assertRaisesRegex(OCRExtractionError, "page 1"):
            extract_pdf_pages(build_pdf([""]), ocr_engine=OCR())

    def test_invalid_pdf_has_controlled_failure(self):
        with self.assertRaisesRegex(PDFExtractionError, "malformed or unreadable"):
            extract_pdf_pages(b"this is not a PDF")
