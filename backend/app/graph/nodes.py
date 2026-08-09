from typing import Dict, Any, List
from app.core.config import settings
from app.graph.state import QueryState, RetainedChunk
from app.services.embedding_service import embedding_service
from app.services.llm_service import llm_service


async def retrieve_node(state: QueryState) -> Dict[str, Any]:
    """
    Node 1: Retrieve relevant textbook chunks from pgvector database table,
    filtered by requested subject, grade, chapter, or document_id if provided.
    """
    question = state.get("question", "")
    filters = state.get("filters", {})

    # TODO: Generate query embedding using embedding_service.get_embedding(question)
    # TODO: Query pgvector using cosine distance / dot product with filtering clauses
    
    # Mock retrieved chunks for scaffold verification
    mock_chunks: List[RetainedChunk] = [
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "document_id": filters.get("document_id", "11111111-1111-1111-1111-111111111111"),
            "document_title": "NCERT Class 10 Science",
            "chapter": filters.get("chapter", "Chemical Reactions and Equations"),
            "page_number": 4,
            "content": "A balanced chemical equation has an equal number of atoms of each element on both sides of the equation, satisfying the law of conservation of mass.",
            "similarity_score": 0.85  # Exceeds RELEVANCE_THRESHOLD (0.6)
        }
    ]

    return {"retrieved_chunks": mock_chunks}


async def grade_relevance_node(state: QueryState) -> Dict[str, Any]:
    """
    Node 2: Heuristic Relevance Check
    Compares the maximum vector similarity score of retrieved chunks against RELEVANCE_THRESHOLD (.env).
    Bypasses costly LLM call for grading relevance.
    """
    chunks = state.get("retrieved_chunks", [])
    threshold = settings.RELEVANCE_THRESHOLD

    if not chunks:
        return {
            "is_relevant": False,
            "max_relevance_score": 0.0
        }

    max_score = max(chunk.get("similarity_score", 0.0) for chunk in chunks)
    is_relevant = max_score >= threshold

    return {
        "is_relevant": is_relevant,
        "max_relevance_score": max_score
    }


async def refuse_node(state: QueryState) -> Dict[str, Any]:
    """
    Node 3a: Refusal Hard Stop
    Triggered when retrieved textbook context is insufficient or below relevance threshold.
    Strict product requirement: Refuse rather than answering from general LLM pre-training knowledge.
    """
    reason = "The requested question is not covered in your prescribed textbook."
    return {
        "is_refused": True,
        "refusal_reason": reason,
        "answer": f"I cannot answer this question because it is not covered in your prescribed textbook. ({reason})",
        "citations": []
    }


async def generate_node(state: QueryState) -> Dict[str, Any]:
    """
    Node 3b: Generation Node (via Ollama Llama 3.1)
    Constructs a strict context-bounded prompt using retrieved textbook chunks.
    Supports query answering, chapter summarization, and quiz generation modes.
    """
    question = state.get("question", "")
    chunks = state.get("retrieved_chunks", [])
    mode = state.get("mode", "query")

    context_str = "\n\n".join(
        [f"[Chapter: {c['chapter']}, Page: {c['page_number']}]\n{c['content']}" for c in chunks]
    )

    system_prompt = (
        "You are LearnMateAI, an AI Textbook Tutor for school students. "
        "Answer the question STRICTLY using ONLY the provided textbook context below. "
        "Do NOT use any outside general knowledge. "
        "Use simple, clear, age-appropriate language suitable for students."
    )

    if mode == "summarize":
        # TODO: Refine chapter summarization prompt template
        user_prompt = f"Summarize the following textbook context:\n\n{context_str}"
    elif mode == "quiz":
        # TODO: Refine multiple-choice quiz generation prompt template (JSON structure)
        user_prompt = f"Generate a 5-question multiple choice quiz based on this context:\n\n{context_str}"
    else:
        # Standard Q&A mode
        user_prompt = f"Textbook Context:\n{context_str}\n\nStudent Question: {question}"

    # TODO: In production, uncomment the actual llm_service call:
    # generated_text = await llm_service.generate(prompt=user_prompt, system_prompt=system_prompt)
    
    # Scaffold response:
    generated_text = (
        f"Based on your textbook context ({chunks[0]['document_title']}, Chapter: {chunks[0]['chapter']}, Page {chunks[0]['page_number']}): "
        "A balanced chemical equation ensures that the mass of reactants equals the mass of products according to the Law of Conservation of Mass."
    )

    return {
        "answer": generated_text,
        "is_refused": False
    }


async def cite_node(state: QueryState) -> Dict[str, Any]:
    """
    Node 4: Citation Node
    Attaches detailed chapter/page metadata to the generated response.
    """
    chunks = state.get("retrieved_chunks", [])
    citations = []

    for c in chunks:
        citations.append({
            "document_id": c.get("document_id"),
            "document_title": c.get("document_title"),
            "chapter": c.get("chapter"),
            "page_number": c.get("page_number"),
            "snippet": c.get("content")[:150] + "..." if len(c.get("content", "")) > 150 else c.get("content")
        })

    return {"citations": citations}
