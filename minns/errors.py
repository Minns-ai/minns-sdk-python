"""Minns SDK exceptions."""

from __future__ import annotations


class MinnsError(Exception):
    """Raised when a Minns API request fails."""

    def __init__(self, message: str, status_code: int, details: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details

    def __repr__(self) -> str:
        return f"MinnsError({self.args[0]!r}, status_code={self.status_code})"
