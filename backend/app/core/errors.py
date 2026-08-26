"""Application exceptions and their HTTP mapping."""

from __future__ import annotations

from fastapi import HTTPException, status


class AppError(HTTPException):
    """Base for errors we raise deliberately, so handlers can tell them apart
    from incidental HTTPExceptions raised by the framework."""

    def __init__(self, status_code: int, detail: str, code: str | None = None) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.code = code or self.__class__.__name__


class NotFound(AppError):
    def __init__(self, what: str = "Resource") -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, f"{what} not found", "not_found")


class Conflict(AppError):
    def __init__(self, detail: str = "Conflicting state") -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail, "conflict")


class Unauthorized(AppError):
    def __init__(self, detail: str = "Not authenticated") -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail, "unauthorized")
        self.headers = {"WWW-Authenticate": "Bearer"}


class Forbidden(AppError):
    def __init__(self, detail: str = "Insufficient permissions") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, detail, "forbidden")


class BadRequest(AppError):
    def __init__(self, detail: str = "Invalid request") -> None:
        super().__init__(status.HTTP_400_BAD_REQUEST, detail, "bad_request")


class PayloadTooLarge(AppError):
    def __init__(self, detail: str = "Payload too large") -> None:
        super().__init__(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail, "payload_too_large")


class ProviderError(RuntimeError):
    """A speech-to-text or analysis provider failed.

    `retryable` decides whether the pipeline reschedules the job or parks it.
    """

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable
