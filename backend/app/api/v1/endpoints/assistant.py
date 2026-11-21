"""Grounded Gemini scientific assistant endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbSession
from app.core.errors import error_responses
from app.services import assistant as assistant_service
from app.services.assistant import AssistantAskRequest, AssistantAskResponse, AssistantStatusResponse

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/status", response_model=AssistantStatusResponse, summary="Check Gemini assistant availability")
def assistant_status():
    return assistant_service.get_status()


@router.post(
    "/ask",
    response_model=AssistantAskResponse,
    summary="Ask Gemini to explain actual persisted records and analysis results",
    responses=error_responses(404, 422, 429, 502, 503, 504),
)
def ask_assistant(db: DbSession, body: AssistantAskRequest):
    return assistant_service.ask_gemini(db, body)
