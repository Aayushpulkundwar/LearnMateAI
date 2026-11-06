import unittest
from types import SimpleNamespace

from scripts.seed_science_curriculum import get_single_by_normalized_name, normalized


class ScienceCurriculumSeedTests(unittest.TestCase):
    def test_normalized_name_is_case_and_whitespace_insensitive(self):
        self.assertEqual(normalized("  Chemical   Reactions AND Equations "), "chemical reactions and equations")

    def test_existing_subject_is_reused_by_normalized_name(self):
        subject = SimpleNamespace(name=" science ")
        self.assertIs(get_single_by_normalized_name([subject], "Science", "Science subject"), subject)

    def test_duplicate_normalized_subjects_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Multiple Science subject"):
            get_single_by_normalized_name([SimpleNamespace(name="Science"), SimpleNamespace(name=" science ")], "Science", "Science subject")
