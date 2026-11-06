"""Fixed research scope, independent of later ingestion status changes."""
import hashlib
import json

APPROVED = {
    1: "6b418b53-971c-4547-b4ac-e0eae9fdff92",
    2: "93116cc1-6a00-4968-9268-59db13424b09",
    3: "4a8d4852-5979-45ca-b5b2-44b994ec2385",
    7: "1360321a-7a0d-417a-a1d4-560a635693e1",
    9: "a92321fa-f136-4203-95e3-550530be58f7",
    10: "925e4a60-1e33-4394-a333-485a7682e584",
    11: "c9981302-fda6-45bc-ab4e-c142379f0035",
    12: "c71bbe0c-0206-4a2c-bb13-d6fa2802f9b4",
    13: "672dfbdf-af01-4c86-9321-f034f6d25aa9",
}
EXCLUDED = (4, 5, 6, 8)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def verify_scope(snapshot):
    if snapshot["approved"] != {str(k): v for k, v in APPROVED.items()}:
        raise ValueError("Snapshot document allowlist differs from the approved nine chapters.")
    allowed = set(APPROVED.values())
    if not snapshot["chunks"] or any(c["document_id"] not in allowed for c in snapshot["chunks"]):
        raise ValueError("Snapshot includes an unapproved document or has no chunks.")


def validate_judgments(records, snapshot):
    """Refuse drafts and references to anything outside the frozen snapshot."""
    verify_scope(snapshot)
    chunks = {c["id"]: c for c in snapshot["chunks"]}
    if len(records) != 50 or len({r.get("id") for r in records}) != 50:
        raise ValueError("Exactly 50 uniquely identified questions are required.")
    seen = set()
    for record in records:
        question = " ".join(record.get("question", "").casefold().split())
        if not question or question in seen:
            raise ValueError("Questions must be nonempty and unique across splits.")
        seen.add(question)
        if record.get("document_id") not in set(APPROVED.values()) or record.get("split") not in {"dev", "test"}:
            raise ValueError("Question scope or split is not approved.")
        if APPROVED.get(record.get("chapter_number")) != record["document_id"]:
            raise ValueError("Question chapter must match its approved document.")
        if record.get("filters"):
            raise ValueError("Question filters cannot change the fixed whole-corpus retrieval conditions.")
        review = record.get("relevance_review")
        if not isinstance(review, dict) or review.get("provenance") != "human" or not isinstance(review.get("reviewer_id"), str) or not review["reviewer_id"].strip() or not isinstance(review.get("rationale"), str) or not review["rationale"].strip() or review.get("status") != "approved":
            raise ValueError("All relevance judgments require explicit human review.")
        gold = record.get("gold_passage_ids", [])
        if not isinstance(record.get("answerable"), bool) or not isinstance(gold, list) or any(not isinstance(g, str) for g in gold) or len(set(gold)) != len(gold):
            raise ValueError("Invalid answerability or gold labels.")
        if bool(gold) != record["answerable"]:
            raise ValueError("Answerability must agree with reviewed gold passages.")
        if any(g not in chunks for g in gold):
            raise ValueError("Gold passage lies outside the frozen nine-chapter corpus.")
        if any(c.get("passage_id") not in chunks for c in record.get("candidate_passages", [])):
            raise ValueError("A suggested source lies outside the frozen corpus.")
        spans = record.get("evidence_spans")
        if not isinstance(spans, list):
            raise ValueError("Evidence spans must be a list.")
        for span in spans:
            if not isinstance(span, dict):
                raise ValueError("Evidence span is outside a reviewed gold passage.")
            c = chunks.get(span.get("passage_id"))
            if not isinstance(span.get("start_char"), int) or not isinstance(span.get("end_char"), int) or not c or span["passage_id"] not in gold or not (0 <= span["start_char"] < span["end_char"] <= len(c["content"])):
                raise ValueError("Evidence span is outside a reviewed gold passage.")
        if record["answerable"] and (not record.get("reference_answer") or not record.get("evidence_spans")):
            raise ValueError("Answerable questions require a reference answer and evidence spans.")


def scoped_retriever(snapshot, retrieve):
    verify_scope(snapshot)
    documents = set(APPROVED.values())
    chunks = {c["id"] for c in snapshot["chunks"]}

    async def wrapped(embedding, **kwargs):
        if "document_ids" in kwargs or "chunk_ids" in kwargs:
            raise ValueError("Callers cannot override the fixed research scope.")
        rows = list(await retrieve(embedding, document_ids=sorted(documents), chunk_ids=sorted(chunks), **kwargs))
        if any(row.document_id not in documents or row.id not in chunks for row in rows):
            raise ValueError("Retrieval returned a result outside the frozen corpus.")
        return rows

    return wrapped
