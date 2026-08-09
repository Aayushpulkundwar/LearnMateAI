import json
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from app.graph.workflow import app_graph
from app.schemas.query import (
    QueryRequest,
    QueryResponse,
    Citation,
    SummarizeRequest,
    SummarizeResponse,
    QuizRequest,
    QuizResponse,
    QuizQuestion,
)
from app.services.llm_service import llm_service

router = APIRouter()


@router.post("/", response_model=QueryResponse)
async def execute_query(payload: QueryRequest):
    """
    Live Query Endpoint:
    Invokes LangGraph pipeline (Retrieve -> Grade Relevance -> Refuse OR (Generate -> Cite)).
    Strictly answers from textbook context or hard-refuses.
    """
    initial_state = {
        "question": payload.question,
        "filters": {
            "document_id": str(payload.document_id) if payload.document_id else None,
            "subject": payload.subject,
            "grade": payload.grade,
            "chapter": payload.chapter,
        },
        "retrieved_chunks": [],
        "is_relevant": False,
        "max_relevance_score": 0.0,
        "answer": "",
        "citations": [],
        "is_refused": False,
        "refusal_reason": None,
        "mode": "query",
    }

    try:
        final_state = await app_graph.ainvoke(initial_state)

        citations = [
            Citation(
                document_id=c.get("document_id"),
                document_title=c.get("document_title", "Textbook"),
                chapter=c.get("chapter"),
                page_number=c.get("page_number"),
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
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LangGraph query execution error: {str(exc)}",
        )


@router.post("/stream")
async def execute_query_stream(payload: QueryRequest):
    """
    Streaming Query Endpoint (Server-Sent Events):
    Streams generated tokens for live chat UI integration.
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        initial_state = {
            "question": payload.question,
            "filters": {
                "document_id": str(payload.document_id) if payload.document_id else None,
                "subject": payload.subject,
                "grade": payload.grade,
                "chapter": payload.chapter,
            },
            "retrieved_chunks": [],
            "is_relevant": False,
            "max_relevance_score": 0.0,
            "answer": "",
            "citations": [],
            "is_refused": False,
            "refusal_reason": None,
            "mode": "query",
        }

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
async def summarize_chapter(payload: SummarizeRequest):
    """
    Secondary Feature 1: Chapter Summarization Endpoint
    Reuses the LangGraph pipeline with mode='summarize' to generate a concise summary from textbook context.
    """
    initial_state = {
        "question": f"Summarize chapter {payload.chapter or 'entire document'}",
        "filters": {
            "document_id": str(payload.document_id),
            "chapter": payload.chapter,
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
            document_id=c.get("document_id"),
            document_title=c.get("document_title", "Textbook"),
            chapter=c.get("chapter"),
            page_number=c.get("page_number"),
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


@router.post("/quiz", response_model=QuizResponse)
async def generate_quiz(payload: QuizRequest):
    """
    Secondary Feature 2: Quiz Generation Endpoint
    Reuses the LangGraph pipeline with mode='quiz' to generate multiple choice quiz questions.
    """
    initial_state = {
        "question": f"Generate {payload.num_questions} quiz questions for chapter {payload.chapter or 'all'}",
        "filters": {
            "document_id": str(payload.document_id),
            "chapter": payload.chapter,
        },
        "retrieved_chunks": [],
        "is_relevant": False,
        "max_relevance_score": 0.0,
        "answer": "",
        "citations": [],
        "is_refused": False,
        "refusal_reason": None,
        "mode": "quiz",
    }

    final_state = await app_graph.ainvoke(initial_state)

    if final_state.get("is_refused", False):
        raise HTTPException(
            status_code=400,
            detail="Cannot generate quiz: Textbook content not found or un-ingested."
        )

    # Mock generated quiz questions structure
    mock_questions = [
        QuizQuestion(
            question="According to the textbook, what is conserved in a balanced chemical reaction?",
            options=["Volume", "Mass and Number of Atoms", "Temperature", "Color"],
            correct_option_index=1,
            explanation="The Law of Conservation of Mass dictates that mass can neither be created nor destroyed in a chemical reaction.",
            citation=Citation(
                document_id=payload.document_id,
                document_title="Prescribed Textbook",
                chapter=payload.chapter or "Chapter 1",
                page_number=4,
                snippet="Mass cannot be created or destroyed..."
            )
        )
    ]

    return QuizResponse(
        document_id=payload.document_id,
        chapter=payload.chapter,
        questions=mock_questions,
    )
