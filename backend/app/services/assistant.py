"""Grounded Gemini scientific assistant service.

Uses the official Google Gen AI SDK (`google-genai`).

Rules:
- Reports explicit unavailable state whenever GEMINI_API_KEY is empty.
- Supplies ONLY real persisted database records (images, stripe analyses, zebras, runs,
  sightings counts) to the model; never invents or fabricates measurements.
- Bounds context and conversation history size before sending to the provider.
- Instructs the model to separate observed measurements from biological/methodological
  hypotheses and preserve all library caveats and units.
- Maps invalid keys, rate limits/quotas, timeouts, network errors, and malformed
  responses into safe API error envelopes without exposing secrets.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Literal

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ServiceUnavailableError
from app.repositories import identifications as run_repo
from app.repositories import images as image_repo
from app.repositories import sightings as sighting_repo
from app.repositories import stripe_analyses as analysis_repo
from app.repositories import zebras as zebra_repo
from app.schemas import AnalysisJobRead

logger = logging.getLogger(__name__)

MAX_QUESTION_CHARS = 2000
MIN_QUESTION_CHARS = 2
MAX_HISTORY_TURNS = 12
MAX_HISTORY_TURN_CHARS = 4000
MAX_HISTORY_TOTAL_CHARS = 12_000
MAX_OUTPUT_TOKENS = 2048

_SYSTEM_INSTRUCTION = """You are the STRIPEFORGE / ZebraID scientific research assistant.
You MUST strictly obey these scientific integrity rules:
1. Ground every numeric claim exclusively in the JSON context provided by the server.
   Never invent, estimate, or extrapolate measurements that are not present in the context.
   In multi-turn conversations, treat only the persisted server JSON context as observed data;
   never promote earlier hypotheses into observed measurements.
2. Always structure your response into two clearly labelled sections:
   - **Observed Measurements & Recorded Data** (facts directly quoted from the supplied API records,
     with exact units such as pixels, degrees [0, 180) axial, 1/pixels, or cycles/pixel).
   - **Interpretation & Hypotheses** (clearly marked as hypotheses or methodological caveats, not proven facts).
3. Respect exact measurement semantics:
   - Member 1 `quality_metrics.confidence_score` is a segmentation quality heuristic, NOT an identity probability.
   - Member 2 `frequency.confidence` is an FFT peak strength, NOT a probability.
   - Identification `similarity_score` is a model similarity score, NOT a probability; identity requires explicit human verification.
   - Spatial measurements are in pixels unless physical calibration is recorded; never invent mm or cm values.
   - Member 1 uses a mask on the full image; Member 2 crops and analyses only the ROI box.
     Do not compare them as if computed on identical pixel sets without noting this caveat.
4. If the requested data is missing from the context, state explicitly what is missing and which analysis or record should be run or selected.
5. Stripe morphology and spatial-frequency results describe one image region only. Never state or imply that
   two regions, two photographs or two analyses belong to different (or the same) zebra individuals;
   individual identity comes only from a human-verified identification record.
6. State the confidence and limitations of each measurement: report Member 1 warnings verbatim, and when
   Member 2 `frequency.confidence` (FFT peak strength) is small, say the dominant period is weakly supported.
   No threshold for "small" is defined by Member 2, so do not invent one."""


class AssistantStatusResponse(BaseModel):
    available: bool
    model: str
    reason: str | None = None


class AssistantHistoryTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "model"]
    text: str = Field(min_length=1, max_length=MAX_HISTORY_TURN_CHARS)

    @field_validator("text")
    @classmethod
    def _clean_text(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("History message text must not be blank.")
        return cleaned


class AssistantAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=MIN_QUESTION_CHARS, max_length=MAX_QUESTION_CHARS)
    image_id: uuid.UUID | None = None
    analysis_ids: list[uuid.UUID] = Field(default_factory=list, max_length=6)
    zebra_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    history: list[AssistantHistoryTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)

    @field_validator("question")
    @classmethod
    def _clean_question(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < MIN_QUESTION_CHARS:
            raise ValueError(f"Question must contain at least {MIN_QUESTION_CHARS} non-whitespace characters.")
        if len(cleaned) > MAX_QUESTION_CHARS:
            raise ValueError(f"Question must be at most {MAX_QUESTION_CHARS} characters.")
        return cleaned

    @field_validator("analysis_ids")
    @classmethod
    def _dedupe_analysis_ids(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        return list(dict.fromkeys(v))


class AssistantAskResponse(BaseModel):
    answer: str
    model: str
    grounded_context: dict[str, Any]


def get_status(settings: Settings | None = None) -> AssistantStatusResponse:
    s = settings or get_settings()
    model = s.gemini_model.strip()
    if not s.gemini_api_key.strip():
        return AssistantStatusResponse(
            available=False,
            model=model,
            reason="GEMINI_API_KEY is not configured on the backend. Add it to backend/.env to enable Gemini explanations.",
        )
    if not model:
        return AssistantStatusResponse(
            available=False,
            model="",
            reason="GEMINI_MODEL is not configured on the backend.",
        )
    return AssistantStatusResponse(available=True, model=model, reason=None)


def build_grounded_context(db: Session, body: AssistantAskRequest) -> dict[str, Any]:
    """Assemble only persisted, sanitized records from PostgreSQL."""
    ctx: dict[str, Any] = {
        "database_summary": {
            "zebras_total": zebra_repo.count_zebras(db),
            "images_total": image_repo.count_image_assets(db),
            "sightings_total": sighting_repo.count_sightings(db),
            "identification_runs_total": run_repo.count_runs(db),
            "stripe_analyses_total": analysis_repo.count_analyses(db) if analysis_repo.table_exists(db) else 0,
        },
        "records": {},
    }

    if body.image_id is not None:
        img = image_repo.get_image_asset(db, body.image_id)
        ctx["records"]["image"] = {
            "id": str(img.id),
            "kind": img.kind.value,
            "width": img.width,
            "height": img.height,
            "content_type": img.content_type,
            "size_bytes": img.size_bytes,
            "captured_at": img.captured_at.isoformat() if img.captured_at else None,
            "crop_bbox": img.crop_bbox,
            "source_image_id": str(img.source_image_id) if img.source_image_id else None,
        }
        if analysis_repo.table_exists(db) and not body.analysis_ids:
            recent = analysis_repo.list_analyses(db, image_id=img.id, limit=4)
            ctx["records"]["analyses"] = [
                AnalysisJobRead.from_orm_job(j).model_dump(mode="json") for j in recent
            ]

    if body.analysis_ids:
        if not analysis_repo.table_exists(db):
            raise ServiceUnavailableError("Stripe analysis table is not migrated yet.", code="analysis_unavailable")
        ctx["records"]["analyses"] = [
            AnalysisJobRead.from_orm_job(analysis_repo.get_analysis(db, aid)).model_dump(mode="json")
            for aid in body.analysis_ids
        ]

    if body.zebra_id is not None:
        z = zebra_repo.get_zebra(db, body.zebra_id)
        ctx["records"]["zebra"] = {
            "id": str(z.id),
            "code": z.code,
            "name": z.name,
            "species": z.species,
            "sex": z.sex,
            "status": z.status.value,
            "notes": z.notes,
        }

    if body.run_id is not None:
        run = run_repo.get_run(db, body.run_id, with_candidates=True)
        ctx["records"]["identification_run"] = {
            "id": str(run.id),
            "status": run.status.value,
            "model_name": run.model_name,
            "model_version": run.model_version,
            "predicted_unknown": run.predicted_unknown,
            "candidates": [
                {
                    "rank": c.rank,
                    "zebra_id": str(c.zebra_id) if c.zebra_id else None,
                    "external_label": c.external_label,
                    "similarity_score": c.similarity_score,
                    "score_type": c.score_type,
                }
                for c in run.candidates
            ],
        }

    return ctx


def _compact_value(value: Any, *, max_list_items: int, max_str_chars: int) -> tuple[Any, bool]:
    """Recursively bound oversized lists/strings while preserving scalar measurements."""
    if isinstance(value, str):
        if len(value) > max_str_chars:
            return value[:max_str_chars] + "... [truncated]", True
        return value, False
    if isinstance(value, list):
        truncated = len(value) > max_list_items
        kept: list[Any] = []
        for item in value[:max_list_items]:
            compacted_item, item_trunc = _compact_value(
                item, max_list_items=max_list_items, max_str_chars=max_str_chars
            )
            truncated = truncated or item_trunc
            kept.append(compacted_item)
        if len(value) > max_list_items:
            kept.append({"_omitted_items": len(value) - max_list_items, "_total_items": len(value)})
        return kept, truncated
    if isinstance(value, dict):
        truncated = False
        out: dict[str, Any] = {}
        for k, v in value.items():
            compacted_v, v_trunc = _compact_value(
                v, max_list_items=max_list_items, max_str_chars=max_str_chars
            )
            truncated = truncated or v_trunc
            out[k] = compacted_v
        return out, truncated
    return value, False


def serialize_bounded_context(ctx: dict[str, Any], max_chars: int) -> tuple[str, bool]:
    """Serialize grounded context JSON, compacting oversized arrays/strings if over budget."""
    pretty = json.dumps(ctx, indent=2)
    if len(pretty) <= max_chars:
        return pretty, False

    compact_raw = json.dumps(ctx, separators=(",", ":"))
    if len(compact_raw) <= max_chars:
        return compact_raw, False

    for max_list_items, max_str_chars in ((24, 1000), (8, 400), (3, 200)):
        compacted, _ = _compact_value(ctx, max_list_items=max_list_items, max_str_chars=max_str_chars)
        serialized = json.dumps(compacted, separators=(",", ":"))
        if len(serialized) <= max_chars:
            return serialized, True

    marker = "... [context truncated to size limit]"
    budget = max(0, max_chars - len(marker))
    compacted_final, _ = _compact_value(ctx, max_list_items=3, max_str_chars=200)
    serialized_final = json.dumps(compacted_final, separators=(",", ":"))
    return serialized_final[:budget] + marker, True


def _bound_history(history: list[AssistantHistoryTurn], max_total_chars: int = MAX_HISTORY_TOTAL_CHARS) -> list[AssistantHistoryTurn]:
    """Keep the most recent conversation turns within the total character budget."""
    if not history:
        return []
    kept_reversed: list[AssistantHistoryTurn] = []
    used = 0
    for turn in reversed(history[-MAX_HISTORY_TURNS:]):
        if used + len(turn.text) > max_total_chars:
            break
        kept_reversed.append(turn)
        used += len(turn.text)
    return list(reversed(kept_reversed))


def _create_genai_client(api_key: str, timeout_seconds: float) -> genai.Client:
    timeout_ms = max(1000, int(timeout_seconds * 1000))
    return genai.Client(
        api_key=api_key,
        http_options=genai_types.HttpOptions(
            timeout=timeout_ms,
            retry_options=genai_types.HttpRetryOptions(attempts=1),
        ),
    )


def _extract_response_text(response: Any) -> str:
    """Safely extract text from a google-genai GenerateContentResponse."""
    if response is None:
        return ""

    # Try candidate parts first so we don't depend on SDK convenience properties raising on empty/blocked content.
    candidates = getattr(response, "candidates", None)
    if isinstance(candidates, list) and candidates:
        first = candidates[0]
        content = getattr(first, "content", None)
        parts = getattr(content, "parts", None)
        if isinstance(parts, list):
            texts: list[str] = []
            for part in parts:
                text = getattr(part, "text", None)
                if isinstance(text, str) and text.strip():
                    texts.append(text)
            if texts:
                return "\n".join(texts).strip()

    try:
        direct_text = getattr(response, "text", None)
    except Exception:
        direct_text = None

    if isinstance(direct_text, str):
        return direct_text.strip()
    return ""


def _map_api_error(exc: genai_errors.APIError) -> AppError:
    """Map Google Gen AI SDK APIError into a safe client-facing AppError."""
    code = getattr(exc, "code", None)
    status = str(getattr(exc, "status", "") or "").upper()
    msg_lower = str(getattr(exc, "message", "") or str(exc)).lower()

    logger.error("Gemini APIError: code=%s status=%s", code, status or "UNKNOWN")

    if code == 429 or status == "RESOURCE_EXHAUSTED" or "quota" in msg_lower or "rate limit" in msg_lower:
        return AppError(
            "Gemini API rate limit or quota was exceeded. Please wait a moment and retry.",
            status_code=429,
            code="assistant_rate_limited",
        )

    if (
        code in (401, 403)
        or status in ("UNAUTHENTICATED", "PERMISSION_DENIED")
        or "api key" in msg_lower
        or "api_key" in msg_lower
        or "invalid credential" in msg_lower
    ):
        return ServiceUnavailableError(
            "Gemini API credentials were rejected by the provider. Verify GEMINI_API_KEY on the backend.",
            code="assistant_invalid_api_key",
        )

    if code in (408, 504) or status == "DEADLINE_EXCEEDED" or "timed out" in msg_lower or "deadline" in msg_lower:
        return AppError(
            "Gemini API request timed out. Please retry.",
            status_code=504,
            code="assistant_timeout",
        )

    if code == 404 or status == "NOT_FOUND":
        return AppError(
            "Configured Gemini model is unavailable. Verify GEMINI_MODEL on the backend.",
            status_code=502,
            code="assistant_model_unavailable",
        )

    return AppError(
        "Gemini API returned an upstream error. Please retry shortly.",
        status_code=502,
        code="assistant_upstream_error",
    )


def ask_gemini(
    db: Session,
    body: AssistantAskRequest,
    *,
    settings: Settings | None = None,
    genai_client: Any | None = None,
) -> AssistantAskResponse:
    s = settings or get_settings()
    st = get_status(s)
    if not st.available:
        raise ServiceUnavailableError(st.reason or "Gemini assistant is unavailable.", code="assistant_unavailable")

    grounded = build_grounded_context(db, body)
    context_json, context_truncated = serialize_bounded_context(grounded, s.gemini_max_context_chars)

    user_prompt = (
        "Grounded STRIPEFORGE database context (JSON):\n"
        f"{context_json}\n\n"
        f"Researcher question:\n{body.question}"
    )

    bounded_history = _bound_history(body.history)
    contents: list[genai_types.Content] = [
        genai_types.Content(
            role=turn.role,
            parts=[genai_types.Part.from_text(text=turn.text)],
        )
        for turn in bounded_history
    ]
    contents.append(
        genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=user_prompt)],
        )
    )

    config = genai_types.GenerateContentConfig(
        system_instruction=_SYSTEM_INSTRUCTION,
        temperature=0.2,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    owns_client = genai_client is None
    client = genai_client or _create_genai_client(s.gemini_api_key.strip(), s.gemini_timeout_seconds)
    try:
        response = client.models.generate_content(
            model=st.model,
            contents=contents,
            config=config,
        )
    except genai_errors.APIError as exc:
        raise _map_api_error(exc) from None
    except (httpx.TimeoutException, TimeoutError) as exc:
        logger.error("Gemini request timeout: %s", type(exc).__name__)
        raise AppError(
            "Gemini API request timed out. Please retry.",
            status_code=504,
            code="assistant_timeout",
        ) from None
    except (httpx.HTTPError, ConnectionError, OSError) as exc:
        logger.error("Gemini network error: %s", type(exc).__name__)
        raise AppError(
            "Could not reach Gemini API due to a network error. Please retry.",
            status_code=502,
            code="assistant_network_error",
        ) from None
    except Exception as exc:
        logger.error("Unexpected Gemini SDK error: %s", type(exc).__name__)
        raise AppError(
            "Gemini API request failed unexpectedly. Please retry.",
            status_code=502,
            code="assistant_upstream_error",
        ) from None
    finally:
        if owns_client and hasattr(client, "close"):
            try:
                client.close()
            except Exception:
                pass

    answer = _extract_response_text(response)
    if not answer:
        logger.error("Gemini returned empty or malformed response")
        raise AppError(
            "Gemini API returned an empty or malformed response. Please rephrase or retry.",
            status_code=502,
            code="assistant_malformed_response",
        )

    return AssistantAskResponse(
        answer=answer,
        model=st.model,
        grounded_context={
            "database_summary": grounded["database_summary"],
            "included_records": list(grounded["records"].keys()),
            "analysis_count": len(grounded["records"].get("analyses", [])),
            "context_truncated": context_truncated,
            "context_chars": len(context_json),
            "history_turns": len(bounded_history),
        },
    )
