"""Application errors and their HTTP mapping.

Services raise these domain errors; a single handler in main.py turns them
into `{"detail": message}` JSON responses. Messages must be safe to show to
end users: no stack traces, SQL, keys or internal identifiers.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    default_message: str = "Request failed."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_message = "Not authenticated."


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    default_message = "Not found."


class InvalidFileError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_message = "Invalid file."


class UnsupportedFileTypeError(InvalidFileError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_message = "Only PDF files are supported."


class FileTooLargeError(InvalidFileError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    default_message = "File is too large."


class ExternalServiceError(AppError):
    """A dependency (Storage, database, OpenAI) failed."""

    status_code = status.HTTP_502_BAD_GATEWAY
    default_message = "An upstream service failed. Please try again."


class UnhandledErrorMiddleware:
    """Turn unexpected exceptions into a JSON 500 *inside* the CORS layer.

    FastAPI's catch-all Exception handler runs in the outermost middleware,
    outside CORSMiddleware, so its 500s carry no CORS headers and browsers
    report them as network failures ("Unable to reach the server"). Added
    before CORSMiddleware, this middleware sits inside it. Errors after a
    response has started (e.g. mid-stream) are re-raised.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            if started:
                raise
            logger.exception("Unhandled error on %s %s", scope.get("method"), scope.get("path"))
            response = JSONResponse(
                {"detail": "Internal server error."}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            await response(scope, receive, send)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, AuthenticationError) else None
        if exc.status_code >= 500:
            logger.warning("%s %s -> %d %s", request.method, request.url.path, exc.status_code, exc.message)
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code, headers=headers)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Internal server error."}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
