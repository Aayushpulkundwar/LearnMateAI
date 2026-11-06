"""Reproducible, dependency-injected retrieval benchmark utilities."""

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Mapping

from app.evaluation.metrics import evaluate_retrieval_relevance
from app.evaluation.faithfulness import audit_answer, faithfulness_metrics
from app.evaluation.review_dataset import adjudicated_claim_labels


Retriever = Callable[..., Awaitable[Iterable[Any]]]
Embedder = Callable[[str], Awaitable[list[float]]]
AnswerGenerator = Callable[[str, list[Mapping[str, Any]]], Awaitable[str]]


@dataclass(frozen=True)
class BenchmarkExample:
    question: str
    gold_passage_ids: tuple[str, ...]
    answerable: bool
    filters: dict[str, Any]
    split: str | None = None
    id: str | None = None
    document_id: str | None = None
    chapter_id: str | None = None
    topic_id: str | None = None
    reference_answer: str | None = None
    evidence_spans: tuple[dict[str, Any], ...] = ()
    claim_labels: dict[str, str] | None = None


def load_benchmark_dataset(path: str | Path, *, split: str | None = None) -> list[BenchmarkExample]:
    """Load JSON arrays or JSONL; accept common gold-passage field aliases."""
    source = Path(path)
    raw = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()] if source.suffix.lower() == ".jsonl" else json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Benchmark JSON must be an array of examples.")
    examples = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or not isinstance(item.get("question"), str) or not item["question"].strip():
            raise ValueError(f"Example {index} requires a non-empty question.")
        item_split = item.get("split")
        if split and item_split != split:
            continue
        gold = item.get("gold_passage_ids", item.get("gold_chunk_ids", item.get("gold_ids", [])))
        if gold is None:
            gold = []
        if not isinstance(gold, list) or not all(isinstance(value, (str, int)) for value in gold):
            raise ValueError(f"Example {index} has invalid gold_passage_ids.")
        answerable = item.get("answerable", item.get("expected_relevant"))
        if not isinstance(answerable, bool):
            raise ValueError(f"Example {index} requires boolean answerable (or expected_relevant).")
        if answerable and not gold:
            raise ValueError(f"Answerable example {index} requires at least one gold passage ID.")
        filters = item.get("filters", {})
        if not isinstance(filters, Mapping):
            raise ValueError(f"Example {index} filters must be an object.")
        examples.append(BenchmarkExample(
            item["question"], tuple(str(value) for value in gold), answerable, dict(filters), item_split, str(item.get("id", index)),
            str(item["document_id"]) if item.get("document_id") is not None else None,
            str(item["chapter_id"]) if item.get("chapter_id") is not None else None,
            str(item["topic_id"]) if item.get("topic_id") is not None else None,
            item.get("reference_answer"), tuple(item.get("evidence_spans", ())), adjudicated_claim_labels(item) or None,
        ))
    return examples


def _ranking_metrics(retrieved_ids: list[str], gold_ids: set[str], *, k: int = 5, ndcg_k: int = 10) -> dict[str, float]:
    top_k = retrieved_ids[:k]
    relevant = [index + 1 for index, passage_id in enumerate(top_k) if passage_id in gold_ids]
    precision = len(relevant) / k
    recall = len(relevant) / len(gold_ids)
    reciprocal_rank = next((1.0 / (index + 1) for index, passage_id in enumerate(retrieved_ids) if passage_id in gold_ids), 0.0)
    dcg = sum(1.0 / math.log2(index + 2) for index, passage_id in enumerate(retrieved_ids[:ndcg_k]) if passage_id in gold_ids)
    ideal = sum(1.0 / math.log2(index + 2) for index in range(min(len(gold_ids), ndcg_k)))
    return {"precision_at_5": precision, "recall_at_5": recall, "mrr": reciprocal_rank, "ndcg_at_10": dcg / ideal if ideal else 0.0}


class RetrievalBenchmark:
    def __init__(self, *, embed: Embedder, retrieve: Retriever, top_k: int = 10):
        self.embed = embed
        self.retrieve = retrieve
        self.top_k = top_k

    async def run(self, examples: Iterable[BenchmarkExample], *, mode: str, dense_threshold: float, lexical_threshold: float, answer_generator: AnswerGenerator | None = None) -> dict[str, Any]:
        traces = []
        answerable_metrics = []
        false_refusals = unsupported_acceptances = answerable = unsupported = 0
        faithfulness_audits = []
        faithfulness_labels = []
        for example in examples:
            started = time.perf_counter()
            embedding = await self.embed(example.question) if mode != "lexical" else []
            after_embedding = time.perf_counter()
            chunks = list(await self.retrieve(embedding, query_text=example.question, top_k=self.top_k, mode=mode, **example.filters))
            finished = time.perf_counter()
            chunk_dicts = [chunk.__dict__ if hasattr(chunk, "__dict__") else dict(chunk) for chunk in chunks]
            accepted, dense_score, lexical_score = evaluate_retrieval_relevance(chunk_dicts, dense_threshold=dense_threshold, lexical_threshold=lexical_threshold)
            retrieved_ids = [str(chunk["id"]) for chunk in chunk_dicts]
            trace = {
                "id": example.id, "question": example.question, "answerable": example.answerable,
                "filters": example.filters, "gold_passage_ids": list(example.gold_passage_ids),
                "retrieved": [{key: chunk.get(key) for key in ("id", "document_id", "page_number", "chunk_index", "similarity_score", "lexical_score", "vector_rank", "lexical_rank", "rrf_score")} for chunk in chunk_dicts],
                "accepted": accepted, "max_dense_score": dense_score, "max_lexical_score": lexical_score,
                "embedding_latency_ms": round((after_embedding - started) * 1000, 3),
                "retrieval_latency_ms": round((finished - after_embedding) * 1000, 3),
                "total_latency_ms": round((finished - started) * 1000, 3),
            }
            if answer_generator:
                answer = await answer_generator(example.question, chunk_dicts)
                audit = audit_answer(answer, chunk_dicts, human_labels=example.claim_labels)
                trace["answer"] = answer
                trace["faithfulness"] = audit
                faithfulness_audits.append(audit)
                faithfulness_labels.append(example.answerable)
            if example.answerable:
                answerable += 1
                trace["ranking_metrics"] = _ranking_metrics(retrieved_ids, set(example.gold_passage_ids))
                answerable_metrics.append(trace["ranking_metrics"])
                false_refusals += not accepted
            else:
                unsupported += 1
                unsupported_acceptances += accepted
            traces.append(trace)
        average = lambda name: sum(metric[name] for metric in answerable_metrics) / len(answerable_metrics) if answerable_metrics else 0.0
        aggregate = {"examples": len(traces), "answerable_examples": answerable, "unsupported_examples": unsupported, "precision_at_5": average("precision_at_5"), "recall_at_5": average("recall_at_5"), "mrr": average("mrr"), "ndcg_at_10": average("ndcg_at_10"), "mean_retrieval_latency_ms": sum(trace["retrieval_latency_ms"] for trace in traces) / len(traces) if traces else 0.0, "false_refusals": false_refusals, "false_refusal_rate": false_refusals / answerable if answerable else 0.0, "unsupported_query_acceptances": unsupported_acceptances, "unsupported_query_acceptance_rate": unsupported_acceptances / unsupported if unsupported else 0.0}
        aggregate["retrieval_latency_p50_ms"] = percentile([trace["retrieval_latency_ms"] for trace in traces], 0.50)
        aggregate["retrieval_latency_p95_ms"] = percentile([trace["retrieval_latency_ms"] for trace in traces], 0.95)
        if faithfulness_audits:
            aggregate["faithfulness"] = faithfulness_metrics(faithfulness_audits, expected_answerable=faithfulness_labels)
        return {
            "configuration": {"mode": mode, "top_k": self.top_k, "dense_threshold": dense_threshold, "lexical_threshold": lexical_threshold},
            "aggregate": aggregate,
            "predictions": traces,
        }


def percentile(values, fraction):
    """Linearly interpolated empirical quantile; null for no observations."""
    ordered = sorted(values)
    if not ordered:
        return None
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (index - lower) * (ordered[upper] - ordered[lower])


def select_dev_thresholds(predictions: Iterable[Mapping[str, Any]], *, dense_candidates: Iterable[float], lexical_candidates: Iterable[float]) -> dict[str, float]:
    """Return the highest-F1 gate configuration using development predictions only."""
    dev = list(predictions)
    if not dev:
        raise ValueError("Development predictions are required for threshold calibration.")
    best = None
    for dense in dense_candidates:
        for lexical in lexical_candidates:
            tp = fp = fn = 0
            for prediction in dev:
                accepted = float(prediction["max_dense_score"]) >= dense or float(prediction["max_lexical_score"]) >= lexical
                if prediction["answerable"] and accepted:
                    tp += 1
                elif prediction["answerable"]:
                    fn += 1
                elif accepted:
                    fp += 1
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            candidate = (f1, precision, recall, -dense, -lexical, {"dense_threshold": dense, "lexical_threshold": lexical, "precision": precision, "recall": recall, "f1": f1})
            if best is None or candidate[:5] > best[:5]:
                best = candidate
    return best[5]


def write_benchmark_report(report: Mapping[str, Any], output_path: str | Path) -> None:
    Path(output_path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
