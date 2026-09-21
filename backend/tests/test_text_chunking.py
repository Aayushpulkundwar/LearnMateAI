import unittest

from app.services.pdf_extraction import ExtractedPDFPage
from app.services.text_chunking import chunk_extracted_pages


class TextChunkingTests(unittest.TestCase):
    def test_short_page_produces_one_trimmed_chunk(self):
        chunks = chunk_extracted_pages(
            [ExtractedPDFPage(page_number=4, text="  A short textbook paragraph.  ")],
            chunk_size=1000,
            chunk_overlap=150,
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].page_number, 4)
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertEqual(chunks[0].content, "A short textbook paragraph.")

    def test_long_page_creates_multiple_chunks_with_overlap(self):
        text = " ".join(f"Sentence {index} explains a textbook concept clearly." for index in range(180))
        chunks = chunk_extracted_pages(
            [ExtractedPDFPage(page_number=1, text=text)],
            chunk_size=300,
            chunk_overlap=60,
        )

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.page_number == 1 for chunk in chunks))
        self.assertTrue(all(len(chunk.content) <= 300 for chunk in chunks))
        self.assertTrue(any(previous.content[-60:] in current.content for previous, current in zip(chunks, chunks[1:])))

    def test_multiple_pages_preserve_page_numbers_and_monotonic_indexes(self):
        chunks = chunk_extracted_pages(
            [
                ExtractedPDFPage(page_number=4, text="First physical page text."),
                ExtractedPDFPage(page_number=5, text="Second physical page text."),
            ],
            chunk_size=1000,
            chunk_overlap=150,
        )

        self.assertEqual([chunk.page_number for chunk in chunks], [4, 5])
        self.assertEqual([chunk.chunk_index for chunk in chunks], [0, 1])

    def test_empty_and_whitespace_pages_produce_no_chunks(self):
        chunks = chunk_extracted_pages(
            [
                ExtractedPDFPage(page_number=1, text=""),
                ExtractedPDFPage(page_number=2, text=" \n\t "),
                ExtractedPDFPage(page_number=3, text="Usable text."),
            ],
            chunk_size=1000,
            chunk_overlap=150,
        )

        self.assertEqual([(chunk.page_number, chunk.content) for chunk in chunks], [(3, "Usable text.")])
        self.assertEqual(chunks[0].chunk_index, 0)

    def test_normal_split_boundaries_preserve_words(self):
        text = "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu. " * 30
        chunks = chunk_extracted_pages(
            [ExtractedPDFPage(page_number=1, text=text)],
            chunk_size=180,
            chunk_overlap=40,
        )

        self.assertTrue(all(not chunk.content.startswith(" ") and not chunk.content.endswith(" ") for chunk in chunks))
        self.assertTrue(all(chunk.content[-1] in ".!?" for chunk in chunks[:-1]))
