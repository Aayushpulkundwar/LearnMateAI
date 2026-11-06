import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy import select
from app.models.chunk import Chunk
from app.evaluation.nine_chapter_corpus import APPROVED, scoped_retriever, validate_judgments
from app.evaluation.retrieval_benchmark import _ranking_metrics, percentile
from app.services.retrieval_service import RetrievalService


def frozen():
    return {"approved": {str(k): v for k, v in APPROVED.items()},
            "chunks": [{"id": "11111111-1111-1111-1111-111111111111", "document_id": APPROVED[1], "content": "source"}]}


@pytest.mark.parametrize("excluded", ["c8432cec-6b58-41ff-a228-a2dbce40b648", "01a8f57c-144b-4a07-accf-5cf180a164b0", "a4fc3f78-1df2-43e6-ab25-9bc7ccce6dc9", "342c7865-7f32-43cf-ad44-23870b66625a"])
def test_excluded_document_is_rejected_even_if_later_completed_and_indexed(excluded):
    retrieve = AsyncMock(return_value=[SimpleNamespace(id="new-indexed-chunk", document_id=excluded, processing_status="completed")])
    with pytest.raises(ValueError, match="outside"):
        asyncio.run(scoped_retriever(frozen(), retrieve)([.1], mode="hybrid"))
    assert set(retrieve.call_args.kwargs["document_ids"]) == set(APPROVED.values())
    assert retrieve.call_args.kwargs["chunk_ids"] == [frozen()["chunks"][0]["id"]]


def test_empty_document_allowlist_matches_nothing():
    statement = RetrievalService._apply_filters(select(Chunk), document_ids=[])
    assert list(statement.compile().params.values()) == [[]]


@pytest.mark.parametrize("mode,expected", [("dense", 1), ("lexical", 1), ("hybrid", 2)])
def test_every_sql_candidate_path_has_allowlist_before_limit(mode, expected):
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    session.execute.return_value = result
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.retrieval_service.AsyncSessionLocal", return_value=context):
        asyncio.run(RetrievalService().retrieve_chunks([.1], query_text="acid", mode=mode, document_ids=list(APPROVED.values()), chunk_ids=[frozen()["chunks"][0]["id"]]))
    assert session.execute.call_count == expected
    for call in session.execute.call_args_list:
        statement = call.args[0]
        values = list(statement.compile().params.values())
        assert [UUID(v) for v in APPROVED.values()] in values
        assert [UUID(frozen()["chunks"][0]["id"])] in values


def test_pending_questions_cannot_be_used_as_verified_labels():
    records = [{"id": str(n), "question": f"question {n}", "document_id": APPROVED[1], "chapter_number": 1, "split": "dev"} for n in range(50)]
    with pytest.raises(ValueError, match="human review"):
        validate_judgments(records, frozen())


def test_reviewed_labels_cannot_reference_a_future_excluded_chunk():
    records = [{"id": str(n), "question": f"question {n}", "document_id": APPROVED[1], "chapter_number": 1, "split": "dev",
                "answerable": True, "gold_passage_ids": ["future-excluded-chunk"],
                "relevance_review": {"status": "approved", "provenance": "human", "reviewer_id": "reviewer", "rationale": "reviewed"}} for n in range(50)]
    with pytest.raises(ValueError, match="outside"):
        validate_judgments(records, frozen())


def reviewed_records():
    chunk_id = frozen()["chunks"][0]["id"]
    return [{"schema_version": "1.0", "id": f"q-{n}", "question": f"Reviewed question {n}",
             "document_id": APPROVED[1], "chapter_number": 1, "split": "dev" if n < 18 else "test",
             "corpus_sha256": "frozen-fingerprint", "answerable": True,
             "gold_passage_ids": [chunk_id], "reference_answer": "Source-backed answer",
             "evidence_spans": [{"passage_id": chunk_id, "start_char": 0, "end_char": 4}],
             "candidate_passages": [], "relevance_review": {"status": "approved", "provenance": "human",
             "reviewer_id": "reviewer-1", "rationale": "Question and cited evidence checked against the textbook."}}
            for n in range(50)]


def test_incomplete_human_review_is_rejected():
    records = reviewed_records()
    records[-1]["relevance_review"]["status"] = "pending"
    with pytest.raises(ValueError, match="explicit human review"):
        validate_judgments(records, frozen())


def test_invalid_evidence_span_is_rejected():
    records = reviewed_records()
    records[0]["evidence_spans"][0]["end_char"] = 500
    with pytest.raises(ValueError, match="Evidence span"):
        validate_judgments(records, frozen())


def test_successfully_reviewed_dataset_passes_validation():
    records = reviewed_records()
    validate_judgments(records, frozen())


def test_mrr_counts_relevant_results_beyond_precision_cutoff():
    metrics = _ranking_metrics([str(i) for i in range(10)], {"7"})
    assert metrics["mrr"] == 1 / 8
    assert metrics["precision_at_5"] == 0
    assert percentile([0, 10], .95) == 9.5
