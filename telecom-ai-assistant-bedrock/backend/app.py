from __future__ import annotations

from typing import List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from bedrock_client import invoke_bedrock
from config import TOP_K
from dataset_loader import build_retrieved_context_block, get_severity_counts, search_incident_by_id
from memory_store import long_term_memory_store, session_memory_store
from prompt_builder import SYSTEM_PROMPT, build_user_prompt

app = FastAPI(title="Telecom Operations Assistant API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    user_id: str = Field(default="telecom_user")
    session_id: Optional[str] = None
    history: List[ChatTurn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    session_id: str
    user_id: str
    answer: str
    sources: List[dict]
    long_term_memory: dict


@app.get("/health")
def health():
    return {"status": "ok", "service": "telecom-operations-assistant"}


@app.get("/")
def root():
    return {
        "message": "Telecom Operations Assistant API is running",
        "health": "/health",
        "chat": "/chat",
    }


@app.get("/memory/{user_id}")
def get_memory(user_id: str):
    return long_term_memory_store.get(user_id)


@app.post("/memory/{session_id}/clear")
def clear_session_memory(session_id: str):
    session_memory_store.clear(session_id)
    return {"session_id": session_id, "status": "cleared"}


@app.get("/severity-summary")
def severity_summary():
    counts = get_severity_counts()
    return {**counts, "total": sum(counts.values())}


@app.get("/incidents/search")
def incidents_search(q: str = Query(..., min_length=1)):
    results = search_incident_by_id(q)
    return {"query": q, "match_count": len(results), "incidents": results}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    try:
        session_id = request.session_id or str(uuid4())

        # Short-term memory: merge backend history with the current request history.
        backend_history = session_memory_store.get_history(session_id)
        request_history = [item.model_dump() for item in request.history]
        merged_history = backend_history[-(TOP_K * 4):] + request_history

        # Persist the current user turn early so the session history remains continuous.
        session_memory_store.append(session_id, "user", request.query)

        # Long-term memory: persistent facts/preferences across sessions.
        long_term = long_term_memory_store.get(request.user_id)

        retrieved_context, sources = build_retrieved_context_block(request.query, top_k=TOP_K)
        user_prompt = build_user_prompt(
            query=request.query,
            short_term_history=merged_history,
            long_term_memory=long_term,
            retrieved_context_block=retrieved_context,
            sources=sources,
        )

        answer = invoke_bedrock(SYSTEM_PROMPT, user_prompt).strip()

        # Persist assistant response in both memory stores.
        session_memory_store.append(session_id, "assistant", answer)
        updated_long_term = long_term_memory_store.update(request.user_id, request.query, answer)

        return ChatResponse(
            session_id=session_id,
            user_id=request.user_id,
            answer=answer,
            sources=sources,
            long_term_memory=updated_long_term,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {exc}") from exc
