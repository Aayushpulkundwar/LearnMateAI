import json
import logging
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.graph.workflow import app_graph
from app.schemas.query import (
    QueryRequest,
    QueryResponse,
    Citation,
    SummarizeRequest,
    SummarizeResponse,
    QuizRequest,
)
from app.schemas.assessment import AttemptView
from app.api.routes.assessments import owned_attempt, view
from app.services.tutor_quiz_service import create_quiz
from app.api.dependencies import get_current_student
from app.core.db import get_async_db
from app.models.learning import Student
from app.models.document import Document
from app.services.tutoring_context_service import resolve_tutoring_context
from app.services.curriculum_authorization import resolve_authorized_scope

router = APIRouter()
logger = logging.getLogger(__name__)

NO_TEXTBOOK_ANSWER = "I don't have Science textbook material for your class yet, so I can't provide a textbook-grounded answer."


async def has_authorized_textbook(filters: dict, db: AsyncSession) -> bool:
    """Check only normalized, completed documents in the already-authorized scope."""
    statement = select(Document.id).where(
        Document.grade_id == filters["grade_id"],
        Document.subject_id == filters["subject_id"],
        Document.processing_status == "completed",
    )
    if filters.get("chapter_id"):
        statement = statement.where(Document.chapter_id == filters["chapter_id"])
    return (await db.scalar(statement.limit(1))) is not None


async def authorized_query_state(payload: QueryRequest, student: Student, db: AsyncSession, mode: str = "query"):
    scope = await resolve_authorized_scope(
        db, student, document_id=payload.document_id, subject_id=payload.subject_id,
        chapter_id=payload.chapter_id, legacy_grade=payload.grade,
        legacy_subject=payload.subject, legacy_chapter=payload.chapter,
    )
    tutoring_context = None
    if payload.study_topic_id:
        tutoring_context = await resolve_tutoring_context(db, student, payload.study_topic_id, payload.explanation_depth)
        if not tutoring_context or tutoring_context["subject_id"] != scope.subject_id or (
            scope.chapter_id and tutoring_context["chapter_id"] != scope.chapter_id
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Study topic is not available in the authorized curriculum scope.")
    tutoring_context = {**(tutoring_context or {}), 'grade_name': student.grade.name, 'explanation_depth': payload.explanation_depth}
    return {
        "question": payload.question,
        "filters": {"document_id": str(scope.document_id) if scope.document_id else None,
                    "grade_id": str(scope.grade_id), "subject_id": str(scope.subject_id),
                    "chapter_id": str(scope.chapter_id) if scope.chapter_id else None},
        "retrieved_chunks": [], "is_relevant": False, "max_relevance_score": 0.0,
        "answer": "", "citations": [], "is_refused": False, "refusal_reason": None,
        "mode": mode, "tutoring_context": tutoring_context,
    }


@router.post("/", response_model=QueryResponse)
async def execute_query(payload: QueryRequest, student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db)):
    """
    Live Query Endpoint:
    Invokes LangGraph pipeline (Retrieve -> Grade Relevance -> Refuse OR (Generate -> Cite)).
    Strictly answers from textbook context or hard-refuses.
    """
    initial_state = await authorized_query_state(payload, student, db)
    if not await has_authorized_textbook(initial_state["filters"], db):
        return QueryResponse(question=payload.question, answer=NO_TEXTBOOK_ANSWER, citations=[], is_refused=True, refusal_reason="No authorized textbook material is available.")

    try:
        final_state = await app_graph.ainvoke(initial_state)

        citations = [
            Citation(
                chunk_id=c.get("chunk_id"),
                document_id=c.get("document_id"),
                document_title=c.get("document_title", "Textbook"),
                chapter=c.get("chapter"),
                page_number=c.get("page_number"),
                chunk_index=c.get("chunk_index"),
                source_index=c.get("source_index"),
                similarity_score=c.get("similarity_score"),
                snippet=c.get("snippet", ""),
            )
            for c in final_state.get("citations", [])
        ]

        return QueryResponse(
            question=payload.question,
            answer=final_state.get("answer", ""),
            citations=citations,
            is_refused=final_state.get("is_refused", False),
            refusal_reason=final_state.get("refusal_reason"),
        )
    except Exception:
        logger.exception("query_execution_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The textbook tutor is temporarily unavailable. Please try again later.",
        )


@router.post("/stream")
async def execute_query_stream(payload: QueryRequest, student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db)):
    """
    Streaming Query Endpoint (Server-Sent Events):
    Streams generated tokens for live chat UI integration.
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        initial_state = await authorized_query_state(payload, student, db)
        if not await has_authorized_textbook(initial_state["filters"], db):
            yield json.dumps({"event": "refusal", "content": NO_TEXTBOOK_ANSWER, "reason": "No authorized textbook material is available."})
            return

        # Run pipeline up to generation/refusal
        final_state = await app_graph.ainvoke(initial_state)

        if final_state.get("is_refused", False):
            refusal_data = {
                "event": "refusal",
                "content": final_state.get("answer"),
                "reason": final_state.get("refusal_reason"),
            }
            yield json.dumps(refusal_data)
            return

        # TODO: Stream token deltas from llm_service.generate_stream
        full_text = final_state.get("answer", "")
        words = full_text.split(" ")
        for word in words:
            yield json.dumps({"event": "token", "content": f"{word} "})

        # Yield citations payload at completion
        citations_data = {
            "event": "citations",
            "citations": final_state.get("citations", []),
        }
        yield json.dumps(citations_data)

    return EventSourceResponse(event_generator())


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize_chapter(payload: SummarizeRequest, student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db)):
    """
    Secondary Feature 1: Chapter Summarization Endpoint
    Reuses the LangGraph pipeline with mode='summarize' to generate a concise summary from textbook context.
    """
    scope = await resolve_authorized_scope(db, student, document_id=payload.document_id, legacy_chapter=payload.chapter)
    initial_state = {
        "question": f"Summarize chapter {payload.chapter or 'entire document'}",
        "filters": {
            "document_id": str(scope.document_id), "grade_id": str(scope.grade_id), "subject_id": str(scope.subject_id), "chapter_id": str(scope.chapter_id) if scope.chapter_id else None,
        },
        "retrieved_chunks": [],
        "is_relevant": False,
        "max_relevance_score": 0.0,
        "answer": "",
        "citations": [],
        "is_refused": False,
        "refusal_reason": None,
        "mode": "summarize",
    }

    final_state = await app_graph.ainvoke(initial_state)

    if final_state.get("is_refused", False):
        raise HTTPException(
            status_code=400,
            detail="Cannot summarize chapter: Textbook content not found or un-ingested."
        )

    citations = [
            Citation(
                chunk_id=c.get("chunk_id"),
                document_id=c.get("document_id"),
                document_title=c.get("document_title", "Textbook"),
                chapter=c.get("chapter"),
                page_number=c.get("page_number"),
                chunk_index=c.get("chunk_index"),
                source_index=c.get("source_index"),
                similarity_score=c.get("similarity_score"),
                snippet=c.get("snippet", ""),
        )
        for c in final_state.get("citations", [])
    ]

    return SummarizeResponse(
        document_id=payload.document_id,
        chapter=payload.chapter,
        summary=final_state.get("answer", "Summary placeholder."),
        key_takeaways=[
            "Key Concept 1: Textbook-grounded principle.",
            "Key Concept 2: Prescribed curriculum formula/definition."
        ],
        citations=citations,
    )


@router.post("/quiz", response_model=AttemptView, status_code=201)
async def generate_quiz(payload: QuizRequest, student: Student = Depends(get_current_student), db: AsyncSession = Depends(get_async_db)):
    """Create a source-grounded practice attempt. Answer keys stay server-side."""
    attempt_id = await create_quiz(payload, student, db)
    return view(await owned_attempt(attempt_id, student.id, db))
