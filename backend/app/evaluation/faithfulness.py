"""Auditable claim and inline-citation checks for grounded answers.

This module deliberately does not infer factual entailment from word overlap.
Supported/contradicted labels require a human annotation or an explicitly
configured evaluator; deterministic checks only verify source structure.
"""

from dataclasses import dataclass
import re
from typing import Callable, Iterable, Mapping, Sequence


CLAIM_STATUSES = {"supported", "contradicted", "insufficiently_evidenced"}
SOURCE_PATTERN = re.compile(r"\[Source\s+(\d+)\]", re.IGNORECASE)
ABSTENTION_PATTERN = re.compile(r"\b(?:cannot answer|can't answer|insufficient (?:context|evidence)|not covered)\b", re.IGNORECASE)

ClaimJudge = Callable[[str, Sequence[Mapping]], str]


@dataclass(frozen=True)
class ClaimAssessment:
    claim: str
    source_indices: tuple[int, ...]
    status: str
    reason: str


def _claims(answer: str) -> list[str]:
    """Extract raw answer clauses conservatively; headings are ignored."""
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+(?!\[Source\s+\d+\])|\n+", answer) if len(SOURCE_PATTERN.sub("", part).strip()) >= 8]


def _source_numbers(text: str) -> tuple[int, ...]:
    return tuple(sorted({int(value) for value in SOURCE_PATTERN.findall(text)}))


def _valid_source(chunk: Mapping) -> bool:
    return bool(chunk.get("id") and chunk.get("document_id") and chunk.get("document_title") and chunk.get("page_number") is not None and str(chunk.get("content", "")).strip())


def audit_answer(
    answer: str,
    context_chunks: Iterable[Mapping],
    *,
    human_labels: Mapping[str, str] | None = None,
    claim_judge: ClaimJudge | None = None,
) -> dict:
    """Return serializable claim/citation audit data without modifying an answer.

    ``human_labels`` maps an exact normalized claim to a verified status.
    ``claim_judge`` is optional and must be separately evaluated/configured;
    it receives only the cited context passages.
    """
    sources = list(context_chunks)
    references = _source_numbers(answer)
    valid_references = []
    invalid_references = []
    for number in references:
        if 1 <= number <= len(sources) and _valid_source(sources[number - 1]):
            valid_references.append(number)
        else:
            invalid_references.append(number)

    claims = []
    for raw_claim in _claims(answer):
        cited = _source_numbers(raw_claim)
        claim = SOURCE_PATTERN.sub("", raw_claim).strip()
        # Citations are usually placed at the end of the sentence. When the
        # sentence splitter removes no marker this remains exact; otherwise a
        # claim without one is explicitly insufficient rather than guessed.
        valid_cited = tuple(number for number in cited if number in valid_references)
        if not valid_cited:
            status, reason = "insufficiently_evidenced", "No valid inline source reference."
        else:
            normalized = claim.casefold()
            status = human_labels.get(normalized) if human_labels else None
            if status is not None:
                if status not in CLAIM_STATUSES:
                    raise ValueError("Human claim labels must use a supported faithfulness status.")
                reason = "Human-verified label."
            elif claim_judge:
                status = claim_judge(claim, [sources[number - 1] for number in valid_cited])
                if status not in CLAIM_STATUSES:
                    raise ValueError("Claim judge returned an invalid faithfulness status.")
                reason = "Optional evaluator label; not human-verified."
            else:
                status, reason = "insufficiently_evidenced", "Valid source reference exists, but entailment is not automatically inferred."
        claims.append(ClaimAssessment(claim, cited, status, reason).__dict__)

    return {
        "is_abstention": bool(ABSTENTION_PATTERN.search(answer)),
        "source_reference_count": len(references),
        "valid_source_references": valid_references,
        "invalid_source_references": invalid_references,
        "claims": claims,
    }


def faithfulness_metrics(audits: Iterable[Mapping], *, expected_answerable: Iterable[bool] | None = None) -> dict:
    """Aggregate audit outputs for reproducible reports, not quality claims."""
    reports = list(audits)
    claims = [claim for report in reports for claim in report.get("claims", [])]
    supported = sum(claim.get("status") == "supported" for claim in claims)
    contradicted = sum(claim.get("status") == "contradicted" for claim in claims)
    insufficient = sum(claim.get("status") == "insufficiently_evidenced" for claim in claims)
    valid = sum(len(report.get("valid_source_references", [])) for report in reports)
    invalid = sum(len(report.get("invalid_source_references", [])) for report in reports)
    result = {
        "claims": len(claims), "supported_claims": supported, "contradicted_claims": contradicted,
        "unsupported_claims": insufficient, "claim_support_rate": supported / len(claims) if claims else 0.0,
        "citation_precision": valid / (valid + invalid) if valid + invalid else 0.0,
        "invalid_citations": invalid,
    }
    if expected_answerable is not None:
        labels = list(expected_answerable)
        if len(labels) != len(reports):
            raise ValueError("expected_answerable must align with faithfulness audits.")
        appropriate = sum(bool(report.get("is_abstention")) == (not label) for report, label in zip(reports, labels))
        result["appropriate_abstention_rate"] = appropriate / len(labels) if labels else 0.0
    return result
