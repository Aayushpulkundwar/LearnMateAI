import asyncio
import unittest
from unittest.mock import patch

from app.core.config import settings
from app.evaluation.metrics import calculate_threshold_metrics
from app.evaluation.sql_relevance import SQL_RELEVANCE_EVALUATION
from app.graph.nodes import grade_relevance_node


class RelevanceThresholdTests(unittest.TestCase):
    def test_evaluation_fixture_has_expected_labeled_coverage(self):
        self.assertEqual(len(SQL_RELEVANCE_EVALUATION), 15)
        self.assertEqual(sum(item["expected_relevant"] for item in SQL_RELEVANCE_EVALUATION), 10)
        self.assertEqual(sum(not item["expected_relevant"] for item in SQL_RELEVANCE_EVALUATION), 5)

    def test_metrics_keep_higher_similarity_as_positive(self):
        metrics = calculate_threshold_metrics([
            {"expected_relevant": True, "similarity": 0.56},
            {"expected_relevant": False, "similarity": 0.47},
        ], 0.55)
        self.assertEqual((metrics.true_positives, metrics.false_positives, metrics.true_negatives, metrics.false_negatives), (1, 0, 1, 0))

    def test_selected_threshold_accepts_direct_and_insert_tree_queries_but_refuses_unrelated(self):
        with patch.object(settings, "RELEVANCE_THRESHOLD", 0.55):
            direct = asyncio.run(grade_relevance_node({"retrieved_chunks": [{"similarity_score": 0.7311356984}]}))
            insert_tree = asyncio.run(grade_relevance_node({"retrieved_chunks": [{"similarity_score": 0.567829}]}))
            unrelated = asyncio.run(grade_relevance_node({"retrieved_chunks": [{"similarity_score": 0.470022}]}))
            borderline = asyncio.run(grade_relevance_node({"retrieved_chunks": [{"similarity_score": 0.557311}]}))

        self.assertTrue(direct["is_relevant"])
        self.assertTrue(insert_tree["is_relevant"])
        self.assertFalse(unrelated["is_relevant"])
        self.assertTrue(borderline["is_relevant"])
