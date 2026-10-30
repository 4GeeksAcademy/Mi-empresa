"""Commercial knowledge query endpoint."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from auth import get_current_user
from services.knowledge.pipeline import query

logger = logging.getLogger("trackflow_api.knowledge")
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class KnowledgeQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)


class KnowledgeQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


@router.post("/query", response_model=KnowledgeQueryResponse)
def query_knowledge(
    request: KnowledgeQueryRequest,
    current_user: dict = Depends(get_current_user),
) -> KnowledgeQueryResponse:
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="La pregunta no puede estar vacía.")
    try:
        answer = query(request.question)
    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        logger.error("Knowledge query failed error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="La base de conocimiento no está disponible temporalmente.",
        ) from exc
    return KnowledgeQueryResponse(answer=answer)
