import unittest

from app.services.pdf_extraction import PDFExtractionError, extract_pdf_pages


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

    def test_invalid_pdf_has_controlled_failure(self):
        with self.assertRaisesRegex(PDFExtractionError, "malformed or unreadable"):
            extract_pdf_pages(b"this is not a PDF")
