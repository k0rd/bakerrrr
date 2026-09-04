"""Stable mode boundary for the private Bakerrrr Content Workbench."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from editor.workbench import WorkbenchApp


MODE_REGISTRY: dict[str, type["EditorMode"]] = {}


def register_mode(cls: type["EditorMode"]) -> type["EditorMode"]:
    """Register a mode without coupling it to the application shell."""
    if not cls.mode_id:
        raise ValueError("Editor mode needs mode_id")
    if cls.mode_id in MODE_REGISTRY:
        raise ValueError(f"Duplicate editor mode: {cls.mode_id}")
    MODE_REGISTRY[cls.mode_id] = cls
    return cls


class EditorMode(ttk.Frame):
    """Small lifecycle/action contract implemented by each editor slice."""

    mode_id = "base"
    mode_title = "Base"
    mode_description = ""
    content_domain = ""

    def __init__(self, app: "WorkbenchApp", parent: tk.Misc) -> None:
        super().__init__(parent)
        self.app = app
        self.services = app.services
        self.dirty = False

    def activate(self) -> None:
        """Refresh mode state as it becomes visible."""

    def deactivate(self) -> None:
        """Commit transient UI state before another mode becomes visible."""

    def maybe_save_changes(self) -> bool:
        """Return false only when a requested mode/app close must be cancelled."""
        return True

    def project_label(self) -> str:
        return self.mode_title

    def handle_action(self, action: str, event: tk.Event | None = None) -> bool:
        return False

    def handle_keypress(self, event: tk.Event) -> bool:
        return False

    def game_root_changed(self) -> None:
        """Invalidate root-derived state after the selected checkout changes."""

    def set_shell_status(self, text: str) -> None:
        self.app.set_status(text)


class PlaceholderMode(EditorMode):
    """Visible registered seam for a content domain not implemented yet."""

    heading = "Future mode"
    detail = ""

    def __init__(self, app: "WorkbenchApp", parent: tk.Misc) -> None:
        super().__init__(app, parent)
        card = ttk.Frame(self, padding=28)
        card.pack(fill="both", expand=True)
        ttk.Label(card, text=self.heading, font=("TkDefaultFont", 18, "bold")).pack(anchor="w")
        ttk.Label(card, text=self.detail, wraplength=760, justify="left").pack(anchor="w", pady=(10, 0))
        ttk.Label(
            card,
            text="This mode is registered through the same drop-in contract as GFX; the shell does not need to change when it becomes real.",
            wraplength=760,
            justify="left",
        ).pack(anchor="w", pady=(16, 0))
