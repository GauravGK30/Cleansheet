"""User-facing errors. Anything raised as CleanSheetError is safe to show to the person using the app."""
from __future__ import annotations


class CleanSheetError(Exception):
    """An expected problem with a clear message (bad file, invalid selection, expired session...)."""

    def __init__(self, message: str, status: int = 400, code: str = "bad_request") -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
