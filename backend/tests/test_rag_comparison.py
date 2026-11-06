import csv
import asyncio
import json

import pytest

from app.evaluation.nine_chapter_corpus import APPROVED, fingerprint, verify_scope
from scripts import rag_comparison as rag


def test_retrieval_rejects_missing_environment_before_loading_services(tmp_path, monkeypatch):
    for name in ("corpus.json", "ollama_models.json", "questions.jsonl"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    def unexpected_configuration(_):
        pytest.fail("Configuration must not be built before file preflight")
    monkeypatch.setattr(rag, "build_system_configuration", unexpected_configuration)
    with pytest.raises(FileNotFoundError, match="environment.json"):
        asyncio.run(rag.execute_retrieval(tmp_path, tmp_path / "questions.jsonl", tmp_path / "out"))
    assert not (tmp_path / "out").exists()


def test_frozen_preflight_lists_all_missing_files(tmp_path):
    with pytest.raises(FileNotFoundError) as failure:
        rag.validate_frozen_artifacts(tmp_path, tmp_path / "questions.jsonl")
    for name in (*rag.FROZEN_RETRIEVAL_ARTIFACTS, "questions.jsonl"):
        assert str(tmp_path / name) in str(failure.value)


def test_dataset_selection_preserves_all_dev_and_selects_22_test_balanced():
    records = []
    for index in range(50):
        split = "dev" if index < 18 else "test"
        chapter = rag.CHAPTER_ORDER[index % len(rag.CHAPTER_ORDER)]
        records.append({"id": f"q{index}", "question": f"question {index}", "split": split, "chapter_number": chapter})
    selected = rag.select_research_records(records)
    assert len(selected) == 40
    assert [r["id"] for r in selected[:18]] == [r["id"] for r in records[:18]]
    assert sum(r["split"] == "dev" for r in selected) == 18
    assert sum(r["split"] == "test" for r in selected) == 22
    assert {r["chapter_number"] for r in selected} == set(rag.CHAPTER_ORDER)


def test_duplicate_questions_are_detected_after_whitespace_and_case_normalization():
    assert rag.has_duplicate_questions([{"question": "Same question?"}, {"question": " same   QUESTION? "}])
    assert not rag.has_duplicate_questions([{"question": "Question one"}, {"question": "Question two"}])


def test_snapshot_allowlist_rejects_excluded_document_even_when_present():
    snapshot = {"approved": {str(k): v for k, v in APPROVED.items()}, "chunks": [{"document_id": APPROVED[1]}]}
    verify_scope(snapshot)
    snapshot["chunks"].append({"document_id": "c8432cec-6b58-41ff-a228-a2dbce40b648"})
    with pytest.raises(ValueError, match="unapproved"):
        verify_scope(snapshot)


def test_frozen_fingerprint_validation_accepts_expected_and_rejects_mutation(tmp_path, monkeypatch):
    body = {"approved": {str(k): v for k, v in APPROVED.items()},
            "chunks": [{"id": f"x{n}", "document_id": APPROVED[1]} for n in range(643)],
            "documents": [{"id": did, "embedding_dimensions": 1024} for did in APPROVED.values()]}
    digest = fingerprint(body)
    monkeypatch.setattr(rag, "EXPECTED_CORPUS_SHA256", digest)
    (tmp_path / "corpus.json").write_text(json.dumps({**body, "corpus_sha256": digest}), encoding="utf-8")
    loaded, value = rag.load_snapshot(tmp_path)
    assert value == digest
    loaded["chunks"][0]["id"] = "changed"
    (tmp_path / "corpus.json").write_text(json.dumps({**loaded, "corpus_sha256": digest}), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        rag.load_snapshot(tmp_path)


def test_retrieval_schema_requires_order_and_frozen_provenance():
    chunk = {"id": "c1", "document_id": APPROVED[1], "chapter": "Ch 1", "page_number": 2}
    snapshot = {"chunks": [chunk], "documents": [{"id": APPROVED[1]}]}
    record = {"question_id": "q1", "mode": "dense", "status": "success", "latency_ms": 1.2,
              "pre_gate_ranked": [{"rank": 1, "chunk_id": "c1", "document_id": APPROVED[1], "chapter": "Ch 1", "page_number": 2}]}
    rag.retrieval_schema([record], snapshot, {"q1"})
    record["pre_gate_ranked"][0]["document_id"] = "c8432cec-6b58-41ff-a228-a2dbce40b648"
    with pytest.raises(ValueError, match="outside frozen"):
        rag.retrieval_schema([record], snapshot, {"q1"})
    record["pre_gate_ranked"][0].update({"document_id": APPROVED[1], "chunk_id": "c1", "chapter": "Ch 1", "page_number": 2, "rank": 2})
    with pytest.raises(ValueError, match="Ranks"):
        rag.retrieval_schema([record], snapshot, {"q1"})


def test_pool_deduplicates_and_shuffles_reproducibly_without_exposing_origin():
    rows = {"dense": [{"chunk_id": "a", "rank": 1, "similarity_score": .8}],
            "fts": [{"chunk_id": "a", "rank": 2, "lexical_score": .5}, {"chunk_id": "b", "rank": 1}],
            "hybrid": [{"chunk_id": "b", "rank": 1, "rrf_score": .03}]}
    order1, mapping1 = rag.pooled_candidates(rows, 12)
    order2, mapping2 = rag.pooled_candidates(rows, 12)
    assert order1 == order2 and mapping1 == mapping2
    assert len(order1) == 2
    assert {source["mode"] for source in mapping1["a"]} == {"dense", "fts"}
    assert "mode" not in rag.ANNOTATION_FIELDS and "rank" not in rag.ANNOTATION_FIELDS
    assert "scores" not in rag.ANNOTATION_FIELDS


def test_cohen_kappa_matches_binary_reference_cases():
    assert rag.cohen_kappa([1, 1, 0, 0], [1, 0, 1, 0]) == pytest.approx(0.0)
    assert rag.cohen_kappa([1, 1, 0, 0], [1, 1, 0, 0]) == pytest.approx(1.0)
    assert rag.cohen_kappa([1, 1], [1, 1]) is None


def test_reviewer_ids_must_be_distinct():
    with pytest.raises(ValueError, match="distinct"):
        rag.require_distinct_reviewers("same", "same")
    rag.require_distinct_reviewers("reviewer-a", "reviewer-b")


def test_adjudication_requires_every_dispute_and_valid_attribution():
    disputes = {("relevance", "q1-c001"): None}
    with pytest.raises(ValueError, match="Every disagreement"):
        rag.validate_adjudications(disputes, [])
    row = {"disagreement_type": "relevance", "candidate_id": "q1-c001", "final_relevance": "1",
           "adjudicator_id": "adjudicator-1", "adjudication_rationale": "Evidence reviewed.", "adjudication_date": "2026-10-30"}
    assert rag.validate_adjudications(disputes, [row])[("relevance", "q1-c001")] == 1
    row["adjudication_date"] = "yesterday"
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        rag.validate_adjudications(disputes, [row])


def _single_review(tmp_path, *, relevance="1", reviewer="R1", answerability="true"):
    chunk_id = "c1"
    row = {"question_id": "q1", "question": "Question?", "chapter": "Chapter 1", "candidate_id": "q1-c001",
           "chunk_id": chunk_id, "document_id": APPROVED[1], "page": "3", "passage_text": "Evidence passage text",
           "relevance": relevance, "reviewer_id": reviewer, "rationale": "Reviewed against the source.",
           "review_duration_seconds": "12.5", "review_timestamp_utc": "2026-10-30T12:00:00Z", "answerability": answerability,
           "reference_answer": "Evidence passage", "evidence_spans_json": '[{"passage_id":"c1","start_char":0,"end_char":8}]',
           "question_comments": "", "corpus_sha256": "abc"}
    path = tmp_path / f"{reviewer}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rag.ANNOTATION_FIELDS); writer.writeheader(); writer.writerow(row)
    expected = [{key: row[key] for key in ("question_id", "question", "chapter", "candidate_id", "chunk_id", "document_id", "page", "corpus_sha256")}]
    snapshot = {"chunks": [{"id": "c1", "document_id": APPROVED[1], "content": "Evidence passage text"}]}
    return path, expected, snapshot


def test_review_import_requires_relevance_and_reviewer_identity(tmp_path):
    path, expected, snapshot = _single_review(tmp_path, relevance="")
    with pytest.raises(ValueError, match="explicit 0 or 1"):
        rag._review_file(path, expected, snapshot, "abc")
    path, expected, snapshot = _single_review(tmp_path, reviewer="")
    with pytest.raises(ValueError, match="Reviewer ID"):
        rag._review_file(path, expected, snapshot, "abc")


def test_review_import_accepts_valid_explicit_judgment_and_measured_duration(tmp_path):
    path, expected, snapshot = _single_review(tmp_path)
    reviewer, labels, questions, durations = rag._review_file(path, expected, snapshot, "abc")
    assert reviewer == "R1"
    assert labels == {"q1-c001": 1}
    assert questions["q1"]["answerable"] is True
    assert durations == [12.5]


def test_invalid_review_timestamp_is_rejected(tmp_path):
    path, expected, snapshot = _single_review(tmp_path)
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    rows[0]["review_timestamp_utc"] = "not-a-timestamp"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rag.ANNOTATION_FIELDS); writer.writeheader(); writer.writerows(rows)
    with pytest.raises(ValueError, match="ISO 8601"):
        rag._review_file(path, expected, snapshot, "abc")


def test_jsonl_writer_refuses_to_overwrite_research_evidence(tmp_path):
    path = tmp_path / "artifact.jsonl"
    path.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        rag.write_jsonl(path, [{"a": 1}])
    assert path.read_text(encoding="utf-8") == "existing"


def test_gold_export_refuses_overwrite_of_existing_artifacts(tmp_path):
    path = tmp_path / "gold.json"
    path.write_text("existing gold", encoding="utf-8")
    with pytest.raises(FileExistsError):
        rag.write_gold_artifacts([], {}, path)
    assert path.read_text(encoding="utf-8") == "existing gold"
