"""Public API errors with safe, stable response contracts."""

from __future__ import annotations


class APIError(Exception):
    """An expected client-facing error without internal implementation details."""

    def __init__(self, message: str, status_code: int = 400, code: str = "validation_error") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
