"""Filesystem locations shared by save-adjacent systems.

This module intentionally imports no simulation or game code so independent
installation-wide registries can resolve their paths without creating runtime
import cycles through ``engine.persistence``.
"""

from __future__ import annotations

import os
from pathlib import Path


def default_save_dir():
    raw = str(os.getenv("BAKERRRR_SAVE_DIR", "") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(__file__).resolve().parents[1] / "saves"


SAVE_DIR = default_save_dir()


__all__ = ("SAVE_DIR", "default_save_dir")
