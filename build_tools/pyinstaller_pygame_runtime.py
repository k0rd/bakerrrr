"""Runtime defaults for packaged pygame builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("BAKERRRR_UI", "pygame")

if getattr(sys, "frozen", False):
    exe_dir = Path(sys.executable).resolve().parent
    os.environ.setdefault("BAKERRRR_SAVE_DIR", str(exe_dir / "saves"))
