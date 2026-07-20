from __future__ import annotations

import datetime as _datetime
import os
import platform
import re
import signal
import sys
import traceback
from pathlib import Path

from engine.persistence import SAVE_DIR


GAME_VERSION = "0.4.22-increasinglycivil"
CRASH_REPORT_PATH = SAVE_DIR / "bakerrrr_last_crash.txt"

_SIGUSR2_DEBUG_UNLOCKED = False
_ACTIVE_DEBUG_SIM = None


def _truthy(value, default=False):
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "debug"}:
        return True
    if text in {"0", "false", "no", "off", "public"}:
        return False
    return bool(default)


def game_build_label(env=None):
    env = os.environ if env is None else env
    version = str(env.get("BAKERRRR_BUILD_VERSION", "") or "").strip() or GAME_VERSION
    label = str(env.get("BAKERRRR_BUILD_LABEL", "") or "").strip()
    sha = str(env.get("GITHUB_SHA", "") or "").strip()
    if not label and sha:
        label = sha[:7]
    if label:
        return f"bakerrrr {version} ({label})"
    return f"bakerrrr {version}"


def debug_mode_from_options(argv=None, env=None):
    env = os.environ if env is None else env
    enabled = _truthy(env.get("BAKERRRR_DEBUG"), False)
    for raw in list(argv or ()):
        if str(raw).strip().lower() == "--debug":
            enabled = True
    return bool(enabled)


def set_signal_debug_unlocked(enabled=True):
    global _SIGUSR2_DEBUG_UNLOCKED
    _SIGUSR2_DEBUG_UNLOCKED = bool(enabled)
    if _SIGUSR2_DEBUG_UNLOCKED and _ACTIVE_DEBUG_SIM is not None:
        set_debug_mode(_ACTIVE_DEBUG_SIM, True, source="sigusr2")


def signal_debug_unlocked():
    return bool(_SIGUSR2_DEBUG_UNLOCKED)


def set_active_debug_sim(sim):
    global _ACTIVE_DEBUG_SIM
    _ACTIVE_DEBUG_SIM = sim
    if sim is not None and signal_debug_unlocked():
        set_debug_mode(sim, True, source="sigusr2")


def set_debug_mode(sim, enabled=True, *, source="startup"):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    traits["debug_mode"] = bool(enabled)
    traits["debug_mode_source"] = str(source or "startup")
    return bool(enabled)


def debug_mode_enabled(sim=None, env=None):
    if signal_debug_unlocked():
        return True
    if sim is not None:
        traits = getattr(sim, "world_traits", None)
        if isinstance(traits, dict) and "debug_mode" in traits:
            return bool(traits.get("debug_mode"))
    return debug_mode_from_options((), env=env)


def _sigusr2_debug_handler(_signum, _frame):
    set_signal_debug_unlocked(True)
    sim = _ACTIVE_DEBUG_SIM
    if sim is not None:
        log = getattr(sim, "log", None)
        if log is not None and hasattr(log, "add"):
            try:
                log.add("Debug overlay unlocked for this process (SIGUSR2).", channel="system", dedupe_key="sigusr2_debug_unlock")
            except TypeError:
                log.add("Debug overlay unlocked for this process (SIGUSR2).")


def install_sigusr2_debug_unlock_handler():
    if not hasattr(signal, "SIGUSR2"):
        return False
    try:
        signal.signal(signal.SIGUSR2, _sigusr2_debug_handler)
        return True
    except (AttributeError, OSError, RuntimeError, ValueError):
        return False


def release_control_text(text, sim=None):
    if debug_mode_enabled(sim):
        return str(text or "")
    cleaned = str(text or "")
    replacements = (
        ("D/Esc close", "Esc close"),
        ("D / Esc close", "Esc close"),
        ("D debug, ", ""),
        (", D debug", ""),
        (" | D debug", ""),
        ("D debug | ", ""),
        ("D debug", ""),
        ("D/Esc", "Esc"),
    )
    for old, new in replacements:
        cleaned = cleaned.replace(old, new)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+\|\s+\|", " | ", cleaned)
    cleaned = re.sub(r"^\s*\|\s*", "", cleaned)
    cleaned = re.sub(r"\s*\|\s*$", "", cleaned)
    cleaned = cleaned.replace(", ,", ",")
    cleaned = cleaned.replace(" ,", ",")
    cleaned = cleaned.replace("or ? for help", "? help")
    return cleaned.strip()


def debug_disabled_hint(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    if traits.get("debug_disabled_hint_shown"):
        return
    traits["debug_disabled_hint_shown"] = True
    log = getattr(sim, "log", None)
    if log is None or not hasattr(log, "add"):
        return
    try:
        log.add(
            "Debug overlay is disabled in public mode. Launch with --debug, set BAKERRRR_DEBUG=1, or send SIGUSR2 to unlock it.",
            channel="system",
            dedupe_key="debug_disabled_public",
        )
    except TypeError:
        log.add("Debug overlay is disabled in public mode.")


def _compact_run_summary(run_end):
    if not isinstance(run_end, dict):
        return "unavailable"
    keys = ("outcome", "reason", "objective_title", "tick", "saved")
    parts = []
    for key in keys:
        if key in run_end:
            parts.append(f"{key}={run_end.get(key)!r}")
    return ", ".join(parts) if parts else "unavailable"


def write_crash_report(exc, *, argv=None, backend=None, run_end=None, crash_path=None):
    path = Path(crash_path) if crash_path else CRASH_REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    now = _datetime.datetime.now(_datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    args_text = " ".join(str(arg) for arg in list(argv or sys.argv[1:]))
    lines = [
        game_build_label(),
        f"timestamp: {now}",
        f"platform: {platform.platform()}",
        f"python: {sys.version.split()[0]}",
        f"argv: {args_text}",
        f"selected_ui: {backend or 'unknown'}",
        f"save_dir: {SAVE_DIR}",
        f"last_run_summary: {_compact_run_summary(run_end)}",
        "",
        "traceback:",
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip(),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
