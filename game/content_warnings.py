"""Runtime warnings for moddable content fallbacks."""

from __future__ import annotations

import sys
from pathlib import Path


_WARNED_FALLBACKS = set()


def warn_content_fallback(path, fallback_desc, *, exc=None, problem=None):
    try:
        path_text = str(Path(path))
    except (TypeError, ValueError):
        path_text = str(path)

    reason = str(problem or "").strip()
    if exc is not None:
        reason = f"{exc.__class__.__name__}: {exc}"
    if not reason:
        reason = "unusable content source"

    key = (path_text, str(fallback_desc), reason)
    if key in _WARNED_FALLBACKS:
        return
    _WARNED_FALLBACKS.add(key)

    print(
        f"[bakerrrr] Warning: {path_text} could not be used ({reason}); "
        f"falling back to {fallback_desc}.",
        file=sys.stderr,
    )
