"""Chat completions with Google Gemini.

    generate(system, messages) -> LLMResult(text, model, finish_reason, tokens)

The model is LLM_MODEL (gemini-3.5-flash-lite by default: fast and on the
free tier). Rate limits and overloads (429/5xx) are retried with backoff;
anything else becomes LLMError (502) with a user-safe message.
"""

import logging
import time
from dataclasses import dataclass
from typing import Literal

import httpx

from app.config import get_settings
from app.errors import ExternalServiceError
from app.services import gemini
from app.services.gemini import ProviderError, RetriesExhaustedError

logger = logging.getLogger(__name__)

Role = Literal["user", "assistant"]
_GEMINI_ROLES = {"user": "user", "assistant": "model"}


class LLMError(ExternalServiceError):
    default_message = "Could not generate an answer. Please try again."


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    finish_reason: str
    input_tokens: int | None = None
    output_tokens: int | None = None


_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        key = get_settings().gemini_api_key
        if key is None or not key.get_secret_value().strip():
            logger.error("LLM misconfigured: GEMINI_API_KEY is not set")
            raise LLMError("The AI model is not configured on the server.")
        _client = gemini.gemini_client(key.get_secret_value(), timeout=120.0)
    return _client


def build_request(system: str, messages: list[ChatMessage]) -> dict:
    settings = get_settings()
    generation_config: dict = {
        "temperature": settings.llm_temperature,
        "maxOutputTokens": settings.llm_max_output_tokens,
    }
    if settings.llm_thinking_level:
        generation_config["thinkingConfig"] = {"thinkingLevel": settings.llm_thinking_level}
    return {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": _GEMINI_ROLES[m.role], "parts": [{"text": m.content}]} for m in messages],
        "generationConfig": generation_config,
    }


def generate(system: str, messages: list[ChatMessage]) -> LLMResult:
    model = get_settings().llm_model
    client = _get_client()
    body = build_request(system, messages)
    started = time.perf_counter()
    try:
        data = gemini.with_retry(
            lambda: gemini.post(client, f"/models/{model}:generateContent", body), f"LLM ({model})"
        )
    except RetriesExhaustedError as exc:
        raise LLMError("The AI model is busy right now. Please try again in a minute.") from exc
    except ProviderError as exc:
        logger.error("LLM request rejected model=%s: %s", model, exc)
        raise LLMError() from exc

    result = parse_response(data, model)
    logger.info(
        "LLM answer model=%s finish=%s tokens in=%s out=%s chars=%d in %.2fs",
        model, result.finish_reason, result.input_tokens, result.output_tokens,
        len(result.text), time.perf_counter() - started,
    )
    return result


def parse_response(data: dict, model: str) -> LLMResult:
    usage = data.get("usageMetadata", {})
    candidates = data.get("candidates") or []
    if not candidates:
        reason = data.get("promptFeedback", {}).get("blockReason", "no candidates")
        logger.warning("LLM returned no answer model=%s reason=%s", model, reason)
        raise LLMError("The AI model declined to answer this question. Try rephrasing it.")

    candidate = candidates[0]
    finish_reason = candidate.get("finishReason", "UNKNOWN")
    parts = candidate.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        logger.warning("LLM returned empty text model=%s finish=%s", model, finish_reason)
        raise LLMError("The AI model declined to answer this question. Try rephrasing it.")
    if finish_reason == "MAX_TOKENS":
        logger.warning("LLM answer truncated at max tokens model=%s", model)

    return LLMResult(
        text=text,
        model=model,
        finish_reason=finish_reason,
        input_tokens=usage.get("promptTokenCount"),
        output_tokens=usage.get("candidatesTokenCount"),
    )
