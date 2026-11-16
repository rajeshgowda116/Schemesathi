from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

from backend.app.services.scheme_sync_service import SchemeSyncService
from backend.app.api.sync import get_sync_service

router = APIRouter(prefix="/api/rag", tags=["RAG Citizen Assistant"])


class ChatRequest(BaseModel):
    query: str = Field(..., description="Citizen question regarding schemes, eligibility, or services")
    profile: Optional[Dict[str, Any]] = Field(default=None, description="Optional citizen profile (age, income, category, occupation)")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Optional metadata filters (department, state, scheme_id)")


class SourceItem(BaseModel):
    scheme_id: Optional[int] = None
    scheme_name: str
    department: str
    state: str
    official_url: str
    relevance_score: float


class ChatResponse(BaseModel):
    status: str
    answer: str
    sources: List[SourceItem]
    retrieved_chunks: int
    llm_engine: str


@router.post("/chat", response_model=ChatResponse)
def citizen_chat(
    req: ChatRequest,
    service: SchemeSyncService = Depends(get_sync_service)
) -> ChatResponse:
    """
    Accepts a user question and optional profile, queries the Qdrant vector database,
    and returns a grounded answer with official source citations.
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query string cannot be empty.")

    try:
        res = service.ask(
            query=req.query,
            user_profile=req.profile,
            filters=req.filters
        )
        return ChatResponse(
            status="SUCCESS",
            answer=res["answer"],
            sources=[SourceItem(**s) for s in res.get("sources", [])],
            retrieved_chunks=res.get("retrieved_chunks", 0),
            llm_engine=res.get("llm_engine", "unknown")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat generation failed: {str(e)}")
