"""Lightweight WeasyPrint compatibility shim for environments without native libraries.

The real WeasyPrint package depends on system libraries that are not available in
this Windows workspace. This shim keeps imports and test patching working, while
making PDF generation fall back cleanly to HTML in Agent 6.
"""

from __future__ import annotations


class WeasyPrintUnavailableError(RuntimeError):
    """Raised when PDF generation is unavailable in this environment."""


class HTML:
    def __init__(self, string: str, base_url: str | None = None) -> None:
        self.string = string
        self.base_url = base_url

    def write_pdf(self, target: str) -> None:
        raise WeasyPrintUnavailableError(
            "WeasyPrint native dependencies are unavailable in this environment"
        )