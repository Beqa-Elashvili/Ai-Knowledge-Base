"""Shared plumbing for Google Gemini API calls (embeddings and chat).

    gemini_client(key)   httpx client; the key travels in a header, never
                         in URLs or logs
    check_response(r)    raises RetryableError for 429/5xx, ProviderError
                         for other non-200 responses
    with_retry(call)     retries RetryableError with backoff, honouring the
                         server's retryDelay
"""

import logging
import re
import time
from collections.abc import Callable
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5
MAX_RETRY_DELAY_SECONDS = 60.0


class RetryableError(Exception):
    """Transient failure (rate limit, overload, network): worth retrying."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderError(Exception):
    """The provider rejected the request; retrying will not help."""


class RetriesExhaustedError(Exception):
    pass


def gemini_client(api_key: str, timeout: float = 60.0) -> httpx.Client:
    return httpx.Client(base_url=GEMINI_BASE_URL, headers={"x-goog-api-key": api_key}, timeout=timeout)


def check_response(response: httpx.Response) -> None:
    if response.status_code in RETRYABLE_STATUS:
        raise RetryableError(f"HTTP {response.status_code}", retry_delay(response))
    if response.status_code != 200:
        raise ProviderError(f"HTTP {response.status_code}: {error_message(response)}")


def post(client: httpx.Client, path: str, body: dict) -> dict:
    try:
        response = client.post(path, json=body)
    except httpx.TransportError as exc:
        raise RetryableError(f"network error: {type(exc).__name__}") from exc
    check_response(response)
    return response.json()


def with_retry(call: Callable[[], T], what: str) -> T:
    """Run `call`, retrying RetryableError up to MAX_ATTEMPTS times.
    Raises RetriesExhaustedError when every attempt failed."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return call()
        except RetryableError as exc:
            if attempt == MAX_ATTEMPTS:
                logger.error("%s failed after %d attempts: %s", what, attempt, exc)
                raise RetriesExhaustedError(str(exc)) from exc
            delay = min(exc.retry_after or 2.0**attempt, MAX_RETRY_DELAY_SECONDS)
            logger.warning("%s attempt %d/%d failed (%s); retrying in %.1fs", what, attempt, MAX_ATTEMPTS, exc, delay)
            time.sleep(delay)
    raise AssertionError("unreachable")


def retry_delay(response: httpx.Response) -> float | None:
    """Seconds from a 429's RetryInfo ("retryDelay": "23s") or Retry-After header."""
    try:
        for detail in response.json()["error"].get("details", []):
            match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(detail.get("retryDelay", "")))
            if match:
                return float(match.group(1))
    except (ValueError, KeyError, AttributeError, TypeError):
        pass
    header = response.headers.get("retry-after", "")
    return float(header) if header.replace(".", "", 1).isdigit() else None


def error_message(response: httpx.Response) -> str:
    try:
        return str(response.json()["error"]["message"])[:300]
    except (ValueError, KeyError, TypeError):
        return response.text[:300]
