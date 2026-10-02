"""Chat completions with Google Gemini.

    generate(system, messages)        -> LLMResult(text, model, finish_reason, tokens)
    stream_generate(system, messages) -> async iterator of text deltas

The model is LLM_MODEL (gemini-3.5-flash-lite by default: fast and on the
free tier). Rate limits and overloads (429/5xx) are retried with backoff;
anything else becomes LLMError (502) with a user-safe message.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
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


# --- streaming ------------------------------------------------------------

def _async_client() -> httpx.AsyncClient:
    """One client per stream: no event-loop-bound state shared between requests."""
    key = get_settings().gemini_api_key
    if key is None or not key.get_secret_value().strip():
        logger.error("LLM misconfigured: GEMINI_API_KEY is not set")
        raise LLMError("The AI model is not configured on the server.")
    return httpx.AsyncClient(
        base_url=gemini.GEMINI_BASE_URL,
        headers={"x-goog-api-key": key.get_secret_value()},
        timeout=httpx.Timeout(120.0, connect=10.0),
    )


async def stream_generate(system: str, messages: list[ChatMessage]) -> AsyncIterator[str]:
    """Yield the answer as text deltas while Gemini generates it.

    Failures before the first delta (rate limit, overload, network) are
    retried like generate(); after text has been sent they cannot be undone,
    so they raise LLMError immediately. An answer that produces no text at
    all (blocked) raises LLMError too.
    """
    model = get_settings().llm_model
    body = build_request(system, messages)
    path = f"/models/{model}:streamGenerateContent"
    started = time.perf_counter()
    produced = 0
    finish_reason, usage = "UNKNOWN", {}

    async with _async_client() as client:
        for attempt in range(1, gemini.MAX_ATTEMPTS + 1):
            try:
                async with client.stream("POST", path, params={"alt": "sse"}, json=body) as response:
                    if response.status_code != 200:
                        await response.aread()
                    gemini.check_response(response)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = json.loads(line[5:])
                        if "error" in data:
                            raise ProviderError(str(data["error"].get("message", ""))[:300])
                        usage = data.get("usageMetadata", usage)
                        candidates = data.get("candidates") or []
                        if not candidates:
                            if data.get("promptFeedback", {}).get("blockReason"):
                                break
                            continue
                        finish_reason = candidates[0].get("finishReason", finish_reason)
                        for part in candidates[0].get("content", {}).get("parts", []):
                            text = part.get("text", "")
                            if text and not part.get("thought"):
                                produced += len(text)
                                yield text
                break
            except gemini.RetryableError as exc:
                if produced or attempt == gemini.MAX_ATTEMPTS:
                    logger.error("LLM stream failed model=%s after %d chars: %s", model, produced, exc)
                    raise LLMError(
                        "The answer was interrupted. Please try again." if produced
                        else "The AI model is busy right now. Please try again in a minute."
                    ) from exc
                delay = min(exc.retry_after or 2.0**attempt, gemini.MAX_RETRY_DELAY_SECONDS)
                logger.warning("LLM stream attempt %d/%d failed (%s); retrying in %.1fs", attempt, gemini.MAX_ATTEMPTS, exc, delay)
                await asyncio.sleep(delay)
            except httpx.TransportError as exc:
                if produced or attempt == gemini.MAX_ATTEMPTS:
                    logger.error("LLM stream network error model=%s after %d chars: %s", model, produced, type(exc).__name__)
                    raise LLMError("The answer was interrupted. Please try again.") from exc
                await asyncio.sleep(min(2.0**attempt, gemini.MAX_RETRY_DELAY_SECONDS))
            except (ProviderError, ValueError) as exc:
                logger.error("LLM stream rejected model=%s: %s", model, exc)
                raise LLMError() from exc

    if not produced:
        logger.warning("LLM stream produced no text model=%s finish=%s", model, finish_reason)
        raise LLMError("The AI model declined to answer this question. Try rephrasing it.")
    if finish_reason == "MAX_TOKENS":
        logger.warning("LLM answer truncated at max tokens model=%s", model)
    logger.info(
        "LLM stream model=%s finish=%s tokens in=%s out=%s chars=%d in %.2fs",
        model, finish_reason, usage.get("promptTokenCount"), usage.get("candidatesTokenCount"),
        produced, time.perf_counter() - started,
    )
