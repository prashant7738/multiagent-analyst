"""Import proxy for WeasyPrint.

``backend/`` is placed at ``sys.path[0]`` by ``api.config``, so a naive
``import weasyprint`` used to find THIS directory's stub forever and silently
disabled a genuinely-installed WeasyPrint. This proxy fixes that while keeping
the public surface identical:

1. Search ``sys.path`` for the real ``weasyprint`` package (skipping our own
   file) and load it under the ``weasyprint`` name when present.
2. Otherwise provide a lightweight stub whose ``HTML.write_pdf`` raises
   :class:`WeasyPrintUnavailableError`, so Agent 6 falls back cleanly to the
   HTML-only report.

Tests patch ``weasyprint.HTML`` directly; because the import system honors a
module replacing itself in ``sys.modules``, patched attributes land on the
same module object every importer sees.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import sys
from pathlib import Path

__all__ = ["HTML", "WeasyPrintUnavailableError"]


class WeasyPrintUnavailableError(RuntimeError):
    """Raised when PDF generation is unavailable in this environment."""


def _load_real_weasyprint():
    """Locate and execute the real weasyprint package, skipping this file."""
    self_file = Path(__file__).resolve()
    self_module = sys.modules.get("weasyprint")  # our own (partially initialized) module

    for entry in list(sys.path):
        if not entry:  # '' means cwd; backend/ itself is handled explicitly below
            continue
        base = Path(entry).expanduser()
        # Cheap pre-filter before touching the import machinery.
        if not (base / "weasyprint" / "__init__.py").is_file() \
                and not (base / "weasyprint.py").is_file():
            continue
        try:
            spec = importlib.machinery.PathFinder.find_spec("weasyprint", [str(base)])
        except (ImportError, ValueError):
            continue
        if spec is None or not spec.origin:
            continue
        if Path(spec.origin).resolve() == self_file:
            continue  # that's us — keep scanning other path entries
        try:
            module = importlib.util.module_from_spec(spec)
            sys.modules["weasyprint"] = module
            buffer = io.StringIO()
            with contextlib.redirect_stderr(buffer):  # silence native-lib banners
                spec.loader.exec_module(module)
            return module
        except Exception:  # noqa: BLE001 — a broken real install falls back to the stub
            sys.modules.pop("weasyprint", None)
            continue

    # No usable real package: put ourselves back so the outer import machinery
    # (which pops/re-adds sys.modules[name] around exec) never sees a gap.
    if self_module is not None:
        sys.modules["weasyprint"] = self_module
    return None


_real = _load_real_weasyprint()

if _real is not None:
    HTML = _real.HTML  # type: ignore[has-type]
    WeasyPrintUnavailableError = getattr(_real, "WeasyPrintUnavailableError",
                                         WeasyPrintUnavailableError)
else:
    class HTML:  # noqa: N801 — mirrors the upstream API surface
        def __init__(self, string: str, base_url: str | None = None) -> None:
            self.string = string
            self.base_url = base_url

        def write_pdf(self, target: str) -> None:
            raise WeasyPrintUnavailableError(
                "WeasyPrint native dependencies are unavailable in this environment"
            )
