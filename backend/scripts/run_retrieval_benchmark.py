"""Run dense, lexical, and hybrid retrieval benchmarks against labeled data.

Usage: python -m scripts.run_retrieval_benchmark DATASET.jsonl REPORT.json --split dev --calibrate
"""

import argparse
import asyncio
from pathlib import Path

from app.core.config import settings
from app.evaluation.retrieval_benchmark import (
    RetrievalBenchmark,
    load_benchmark_dataset,
    select_dev_thresholds,
    write_benchmark_report,
)
from app.services.embedding_service import embedding_service
from app.services.retrieval_service import retrieval_service


async def main(args: argparse.Namespace) -> None:
    if args.calibrate and args.split != "dev":
        raise ValueError("Threshold calibration requires --split dev; test data is never used for calibration.")
    examples = load_benchmark_dataset(args.dataset, split=args.split)
    if not examples:
        raise ValueError("No benchmark examples matched the selected split.")
    benchmark = RetrievalBenchmark(embed=embedding_service.get_embedding, retrieve=retrieval_service.retrieve_chunks, top_k=args.top_k)
    modes = ("dense", "lexical", "hybrid") if args.mode == "all" else (args.mode,)
    reports = {}
    for mode in modes:
        reports[mode] = await benchmark.run(
            examples, mode=mode, dense_threshold=args.dense_threshold, lexical_threshold=args.lexical_threshold
        )
    output = {
        "dataset": str(Path(args.dataset)),
        "split": args.split,
        "model_configuration": {
            "embedding_model": settings.EMBEDDING_MODEL,
            "embedding_dimension": settings.EMBEDDING_DIM,
            "generation_model": settings.LLM_MODEL,
        },
        "reports": reports,
    }
    if args.calibrate:
        hybrid_predictions = reports["hybrid"]["predictions"]
        dense_candidates = sorted({0.0, 1.0, *(trace["max_dense_score"] for trace in hybrid_predictions)})
        lexical_candidates = sorted({0.0, 1.0, *(trace["max_lexical_score"] for trace in hybrid_predictions)})
        output["development_calibration"] = select_dev_thresholds(
            hybrid_predictions, dense_candidates=dense_candidates, lexical_candidates=lexical_candidates
        )
    write_benchmark_report(output, args.output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", help="Labeled JSON array or JSONL dataset")
    parser.add_argument("output", help="JSON report path")
    parser.add_argument("--split", choices=("dev", "test"), help="Dataset split to run")
    parser.add_argument("--mode", choices=("dense", "lexical", "hybrid", "all"), default="all")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--dense-threshold", type=float, default=settings.RELEVANCE_THRESHOLD)
    parser.add_argument("--lexical-threshold", type=float, default=settings.LEXICAL_RELEVANCE_THRESHOLD)
    parser.add_argument("--calibrate", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
