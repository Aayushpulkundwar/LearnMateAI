"""Pure metrics used for empirical relevance-threshold comparisons."""

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ThresholdMetrics:
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.true_positives + self.false_negatives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        denominator = self.precision + self.recall
        return 2 * self.precision * self.recall / denominator if denominator else 0.0

    @property
    def accuracy(self) -> float:
        total = self.true_positives + self.false_positives + self.true_negatives + self.false_negatives
        return (self.true_positives + self.true_negatives) / total if total else 0.0


def calculate_threshold_metrics(results: Iterable[Mapping[str, object]], threshold: float) -> ThresholdMetrics:
    """Score higher-is-better cosine similarities against relevance labels."""
    tp = fp = tn = fn = 0
    for result in results:
        accepted = float(result["similarity"]) >= threshold
        relevant = bool(result["expected_relevant"])
        if accepted and relevant:
            tp += 1
        elif accepted:
            fp += 1
        elif relevant:
            fn += 1
        else:
            tn += 1
    return ThresholdMetrics(tp, fp, tn, fn)
