"""Structured authoring for ``game/items.json``.

The raw item object remains canonical.  Common fields get typed controls while
the long tail of runtime profiles stays available as validated JSON, so adding
a trap/drone/Wire profile never depends on a bespoke form landing first.
"""

from __future__ import annotations

import copy
import json
import re
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, simpledialog, ttk
from typing import Any

from editor.mode_api import EditorMode, register_mode
from game.item_content import (
    PROFILE_FIELDS,
    PROFILE_TEMPLATES,
    ItemDocument,
    ItemDocumentError,
    format_item_issue,
    profile_template,
    validate_item_document,
)


ADVANCED_PROFILE_FIELDS = tuple(field for field in PROFILE_FIELDS if field != "appearance_profile")


@dataclass
class _ItemHistoryEntry:
    before: dict[str, dict[str, Any] | None]
    after: dict[str, dict[str, Any] | None]
    before_order: tuple[str, ...]
    after_order: tuple[str, ...]
    before_selection: str
    after_selection: str


def _csv_values(text: str) -> list[str]:
    return [value.strip() for value in re.split(r"[,\n]", text) if value.strip()]


def _reference_lines(references: list[str] | tuple[str, ...], *, limit: int = 40) -> list[str]:
    values = list(dict.fromkeys(references))
    lines = values[:limit]
    if len(values) > limit:
        lines.append(f"… and {len(values) - limit} more; search the project for the item ID to inspect all")
    return lines


@register_mode
class ItemsMode(EditorMode):
    mode_id = "items"
    mode_title = "Items"
    mode_description = "Author the complete item catalog with runtime-normalized preview"
    content_domain = "items"

    PROFILE_FILTERS = (
        "All items", "Wearables", "Weapons", "Traps", "Drones", "Wire",
        "Containers", "Consumables",
    )

    def __init__(self, app, parent) -> None:
        super().__init__(app, parent)
        self.document: ItemDocument | None = None
        self.selected_item_id = ""
        self.filtered_ids: list[str] = []
        self._saved_source = ""
        self._service_revision = -1
        self._form_guard = False
        self._selection_guard = False
        self._form_dirty = False
        self._undo: list[_ItemHistoryEntry] = []
        self._redo: list[_ItemHistoryEntry] = []
        self._analysis_source = ""
        self._analysis_reference_fingerprint = ""
        self._analysis_normalized: dict[str, dict[str, Any]] = {}
        self._analysis_issues = []

        self.search_var = tk.StringVar()
        self.profile_filter_var = tk.StringVar(value="All items")
        self.legal_filter_var = tk.StringVar(value="All legality")
        self.summary_var = tk.StringVar(value="Set a Bakerrrr root to load game/items.json")
        self.identity_var = tk.StringVar(value="No item selected")
        self.validation_var = tk.StringVar(value="No catalog loaded")

        self.name_var = tk.StringVar()
        self.glyph_var = tk.StringVar()
        self.stack_var = tk.StringVar(value="1")
        self.slot_cost_var = tk.StringVar(value="1")
        self.legal_var = tk.StringVar(value="legal")
        self.category_var = tk.StringVar()
        self.weapon_var = tk.StringVar()
        self.tags_var = tk.StringVar()
        self.item_drawable_var = tk.StringVar()
        self.appearance_family_var = tk.StringVar()
        self.appearance_slots_var = tk.StringVar()
        self.drawable_var = tk.StringVar()
        self.template_var = tk.StringVar(value="trap_profile")

        self._build_ui()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())
        self.profile_filter_var.trace_add("write", lambda *_: self._apply_filter())
        self.legal_filter_var.trace_add("write", lambda *_: self._apply_filter())
        for variable in (
            self.name_var, self.glyph_var, self.stack_var, self.slot_cost_var,
            self.legal_var, self.category_var, self.weapon_var, self.tags_var,
            self.item_drawable_var,
            self.appearance_family_var, self.appearance_slots_var, self.drawable_var,
        ):
            variable.trace_add("write", lambda *_: self._mark_form_dirty())
        self.reload_catalog(negotiate=False, rescan=False)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=7)
        outer.pack(fill="both", expand=True)

        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x", pady=(0, 6))
        for text, command in (
            ("New", self.new_item), ("Duplicate", self.duplicate_item),
            ("Rename", self.rename_item), ("Delete", self.delete_item),
        ):
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=(0, 4))
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=5)
        ttk.Button(toolbar, text="Apply Item", command=self.apply_form).pack(side="left")
        ttk.Button(toolbar, text="Save Catalog", command=self.save_catalog).pack(side="left", padx=(4, 0))
        ttk.Button(toolbar, text="Reload", command=self.reload_catalog).pack(side="left", padx=(4, 0))
        ttk.Button(toolbar, text="Paper Doll", command=self.open_in_paper_doll).pack(side="left", padx=(12, 0))
        ttk.Label(toolbar, textvariable=self.identity_var, font=("TkDefaultFont", 11, "bold")).pack(side="right")

        panes = ttk.Panedwindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes, padding=(0, 0, 7, 0))
        panes.add(left, weight=3)
        ttk.Label(left, text="Item catalog").pack(anchor="w")
        ttk.Entry(left, textvariable=self.search_var).pack(fill="x", pady=(4, 4))
        filters = ttk.Frame(left)
        filters.pack(fill="x", pady=(0, 5))
        ttk.Combobox(
            filters, textvariable=self.profile_filter_var, values=self.PROFILE_FILTERS,
            state="readonly", width=15,
        ).pack(side="left", fill="x", expand=True)
        ttk.Combobox(
            filters, textvariable=self.legal_filter_var,
            values=("All legality", "legal", "restricted", "suspicious", "illegal"),
            state="readonly", width=13,
        ).pack(side="left", padx=(4, 0))
        list_holder = ttk.Frame(left)
        list_holder.pack(fill="both", expand=True)
        self.item_list = tk.Listbox(list_holder, exportselection=False, activestyle="none", width=38)
        self.item_list.pack(side="left", fill="both", expand=True)
        item_scroll = ttk.Scrollbar(list_holder, orient="vertical", command=self.item_list.yview)
        item_scroll.pack(side="right", fill="y")
        self.item_list.configure(yscrollcommand=item_scroll.set)
        self.item_list.bind("<<ListboxSelect>>", self._on_item_selected)
        ttk.Label(left, textvariable=self.summary_var, wraplength=340, justify="left").pack(anchor="w", pady=(6, 0))

        center = ttk.Frame(panes, padding=(0, 0, 7, 0))
        panes.add(center, weight=6)
        self.notebook = ttk.Notebook(center)
        self.notebook.pack(fill="both", expand=True)
        self._build_common_tab()
        self._build_art_tab()
        self._build_effects_tab()
        self._build_appearance_tab()
        self._build_profiles_tab()

        apply_row = ttk.Frame(center)
        apply_row.pack(fill="x", pady=(5, 0))
        ttk.Button(apply_row, text="Apply Item Changes", command=self.apply_form).pack(side="left")
        ttk.Label(apply_row, textvariable=self.validation_var, wraplength=520).pack(side="left", padx=(9, 0))

        right = ttk.Frame(panes)
        panes.add(right, weight=4)
        preview_tabs = ttk.Notebook(right)
        preview_tabs.pack(fill="both", expand=True)
        self.raw_text = self._preview_tab(preview_tabs, "Raw item")
        self.normalized_text = self._preview_tab(preview_tabs, "Runtime")
        self.issues_text = self._preview_tab(preview_tabs, "Issues + refs")
        ttk.Button(right, text="Copy Raw Item JSON", command=self.copy_raw_item).pack(anchor="e", pady=(5, 0))

    def _build_common_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=9)
        self.notebook.add(tab, text="Common")
        tab.columnconfigure(1, weight=1)
        row = 0
        for label, variable, width in (
            ("Name", self.name_var, 42), ("Glyph", self.glyph_var, 8),
            ("Stack max", self.stack_var, 12), ("Inventory slot cost", self.slot_cost_var, 12),
        ):
            ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(tab, textvariable=variable, width=width).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
            row += 1
        ttk.Label(tab, text="Legal status").grid(row=row, column=0, sticky="w", pady=3)
        ttk.Combobox(
            tab, textvariable=self.legal_var,
            values=("legal", "restricted", "suspicious", "illegal"), state="readonly",
        ).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        row += 1
        ttk.Label(tab, text="Category").grid(row=row, column=0, sticky="w", pady=3)
        self.category_combo = ttk.Combobox(tab, textvariable=self.category_var, state="normal")
        self.category_combo.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        row += 1
        ttk.Label(tab, text="Weapon ID").grid(row=row, column=0, sticky="w", pady=3)
        self.weapon_combo = ttk.Combobox(tab, textvariable=self.weapon_var, state="normal")
        self.weapon_combo.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        row += 1
        ttk.Label(tab, text="Tags (comma separated)").grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(tab, textvariable=self.tags_var).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        row += 1
        ttk.Label(tab, text="Description").grid(row=row, column=0, sticky="nw", pady=3)
        self.description_text = tk.Text(tab, height=8, wrap="word", undo=False)
        self.description_text.grid(row=row, column=1, sticky="nsew", padx=(8, 0), pady=3)
        self.description_text.bind("<<Modified>>", self._on_text_modified)
        tab.rowconfigure(row, weight=1)

    def _build_art_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=9)
        self.notebook.add(tab, text="Ground Art")
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="Ground drawable ID").grid(row=0, column=0, sticky="w", pady=3)
        self.item_drawable_combo = ttk.Combobox(
            tab,
            textvariable=self.item_drawable_var,
            state="normal",
        )
        self.item_drawable_combo.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=3)
        ttk.Button(tab, text="Edit Art", command=self.open_item_drawable).grid(
            row=0,
            column=2,
            padx=(5, 0),
        )
        ttk.Button(tab, text="New Art", command=self.new_item_drawable).grid(
            row=0,
            column=3,
            padx=(5, 0),
        )
        ttk.Label(
            tab,
            text=(
                "Optional authored on-ground art. Blank keeps the current procedural category "
                "renderer as a compatibility fallback."
            ),
            wraplength=620,
            justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))

    def _build_effects_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab, text="Effects")
        ttk.Label(tab, text="Effect list (JSON) — consumed in order by the item-use runtime").pack(anchor="w", pady=(0, 5))
        self.effects_text = self._editable_json_text(tab)

    def _build_appearance_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab, text="Appearance")
        form = ttk.Frame(tab)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        for row, (label, variable) in enumerate((
            ("Family", self.appearance_family_var),
            ("Slots (comma separated)", self.appearance_slots_var),
            ("Drawable ID", self.drawable_var),
        )):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            if variable is self.drawable_var:
                self.drawable_combo = ttk.Combobox(form, textvariable=variable, state="normal")
                self.drawable_combo.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
                ttk.Button(form, text="Edit Drawable", command=self.open_drawable).grid(row=row, column=2, padx=(5, 0))
            else:
                ttk.Entry(form, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=3)
        ttk.Label(tab, text="Appearance profile (JSON object)").pack(anchor="w", pady=(8, 4))
        self.appearance_text = self._editable_json_text(tab, height=16)

    def _build_profiles_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab, text="Advanced Profiles")
        top = ttk.Frame(tab)
        top.pack(fill="x", pady=(0, 5))
        ttk.Label(top, text="Add profile template").pack(side="left")
        self.template_combo = ttk.Combobox(
            top, textvariable=self.template_var, values=tuple(PROFILE_TEMPLATES),
            state="readonly", width=25,
        )
        self.template_combo.pack(side="left", padx=(6, 4))
        ttk.Button(top, text="Add / Replace", command=self.add_profile_template).pack(side="left")
        ttk.Label(
            tab,
            text="All specialized profiles as one JSON object. Trap profiles are authored here; trap graphics are not required.",
            wraplength=620, justify="left",
        ).pack(anchor="w", pady=(0, 5))
        self.profiles_text = self._editable_json_text(tab)

    def _editable_json_text(self, parent, *, height: int = 24) -> tk.Text:
        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True)
        widget = tk.Text(holder, height=height, wrap="none", font=("TkFixedFont", 9), undo=False)
        widget.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=widget.yview)
        scroll.pack(side="right", fill="y")
        widget.configure(yscrollcommand=scroll.set)
        widget.bind("<<Modified>>", self._on_text_modified)
        return widget

    def _preview_tab(self, notebook: ttk.Notebook, label: str) -> tk.Text:
        frame = ttk.Frame(notebook, padding=5)
        notebook.add(frame, text=label)
        widget = tk.Text(frame, wrap="none", font=("TkFixedFont", 9))
        widget.pack(fill="both", expand=True)
        widget.configure(state="disabled")
        return widget

    # ------------------------------------------------------------------
    # Lifecycle and catalog
    # ------------------------------------------------------------------

    def activate(self) -> None:
        if self._service_revision != self.services.items.revision and not self.dirty:
            self._load_from_service()
        else:
            self._refresh_reference_values()
        self._refresh_preview()

    def deactivate(self) -> None:
        self._commit_form(show_error=False)

    def game_root_changed(self) -> None:
        if self.dirty:
            self.set_shell_status(
                "Items: old-root draft retained for recovery; it cannot save into this root. Switch back or reload/discard"
            )
            return
        self._load_from_service()

    def project_label(self) -> str:
        return "items.json"

    def maybe_save_changes(self) -> bool:
        if self._form_dirty and not self._commit_form(show_error=True):
            return False
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved item changes", "Save changes to game/items.json?", parent=self,
        )
        if answer is None:
            return False
        return self.save_catalog() if answer else True

    def reload_catalog(self, *, negotiate: bool = True, rescan: bool = True) -> bool:
        if negotiate and (self.dirty or self._form_dirty):
            if not self.maybe_save_changes():
                return False
        if rescan:
            self.services.drawables.reload(self.services.game)
            ok = self.services.items.reload(self.services.game, self.services.drawables)
            if not ok:
                messagebox.showerror("Reload items", self.services.items.error, parent=self)
                return False
        self._load_from_service()
        return self.document is not None

    def _load_from_service(self) -> None:
        service = self.services.items
        self._service_revision = service.revision
        self.document = service.document.clone() if service.document is not None else None
        self._saved_source = self.document.dumps() if self.document else ""
        self._undo.clear()
        self._redo.clear()
        self.dirty = False
        self._form_dirty = False
        self._analysis_source = self._saved_source
        self._analysis_reference_fingerprint = service.references.fingerprint
        self._analysis_normalized = copy.deepcopy(service.normalized)
        self._analysis_issues = list(service.issues)
        self.selected_item_id = self.selected_item_id if self.document and self.selected_item_id in self.document.items else ""
        self._refresh_reference_values()
        self._apply_filter()
        if self.document and not self.selected_item_id:
            self.selected_item_id = next(iter(self.document.items), "")
            self._apply_filter()
        self._load_form()
        self.app.refresh_title()
        if service.error:
            self.summary_var.set(service.error)
        elif self.document:
            self.set_shell_status(f"Items: {len(self.document.items)} definitions loaded")

    def _refresh_reference_values(self) -> None:
        refs = self.services.items.references
        self.weapon_combo.configure(values=("", *sorted(refs.weapon_ids)))
        self.drawable_combo.configure(values=("", *sorted(refs.drawable_ids)))
        self.item_drawable_combo.configure(values=("", *sorted(refs.ground_drawable_ids)))
        if self.document:
            categories = sorted({str(row.get("category")) for row in self.document.items.values() if row.get("category")})
        else:
            categories = []
        self.category_combo.configure(values=("", *categories))

    # ------------------------------------------------------------------
    # Selection/filter/form
    # ------------------------------------------------------------------

    def _matches_profile(self, item: dict[str, Any], filter_name: str) -> bool:
        if filter_name == "Wearables":
            return bool(item.get("appearance_drawable") or item.get("appearance_slots"))
        if filter_name == "Weapons":
            return bool(item.get("weapon_id"))
        if filter_name == "Traps":
            return "trap_profile" in item
        if filter_name == "Drones":
            return "drone_profile" in item
        if filter_name == "Wire":
            return "wire_profile" in item or "wire_interface_profile" in item
        if filter_name == "Containers":
            return "container" in item
        if filter_name == "Consumables":
            return bool(item.get("effects")) or "consumable" in item.get("tags", ())
        return True

    def _apply_filter(self) -> None:
        if not hasattr(self, "item_list"):
            return
        self.item_list.delete(0, "end")
        self.filtered_ids = []
        if self.document is None:
            self.summary_var.set("No item catalog loaded")
            return
        query = self.search_var.get().strip().lower()
        profile_filter = self.profile_filter_var.get()
        legal_filter = self.legal_filter_var.get()
        for item_id, item in self.document.items.items():
            haystack = " ".join((
                item_id, str(item.get("name") or ""), str(item.get("category") or ""),
                " ".join(str(value) for value in item.get("tags", ()) if isinstance(value, str)),
            )).lower()
            if query and query not in haystack:
                continue
            if legal_filter != "All legality" and item.get("legal_status", "legal") != legal_filter:
                continue
            if not self._matches_profile(item, profile_filter):
                continue
            self.filtered_ids.append(item_id)
            markers = []
            if item.get("appearance_drawable"):
                markers.append("wear")
            if item.get("item_drawable"):
                markers.append("art")
            if item.get("weapon_id"):
                markers.append("weapon")
            if item.get("trap_profile"):
                markers.append("trap")
            suffix = f" · {','.join(markers)}" if markers else ""
            self.item_list.insert("end", f"{item.get('name') or item_id}  [{item_id}]{suffix}")
        if self.selected_item_id in self.filtered_ids:
            index = self.filtered_ids.index(self.selected_item_id)
            self.item_list.selection_set(index)
            self.item_list.see(index)
        self.summary_var.set(
            f"Showing {len(self.filtered_ids)} of {len(self.document.items)} items. "
            "List filtering uses the cached document."
        )

    def _on_item_selected(self, _event=None) -> None:
        if self._selection_guard:
            return
        selection = self.item_list.curselection()
        if not selection:
            return
        requested = self.filtered_ids[int(selection[0])]
        if requested == self.selected_item_id:
            return
        previous = self.selected_item_id
        if self._form_dirty and not self._commit_form(show_error=True):
            self._selection_guard = True
            try:
                self.item_list.selection_clear(0, "end")
                if previous in self.filtered_ids:
                    self.item_list.selection_set(self.filtered_ids.index(previous))
            finally:
                self._selection_guard = False
            return
        self.selected_item_id = requested
        self._load_form()

    def _mark_form_dirty(self) -> None:
        if not self._form_guard and self.selected_item_id:
            self._form_dirty = True
            self.validation_var.set("Unapplied item edits")

    def _on_text_modified(self, event) -> None:
        widget = event.widget
        if not widget.edit_modified():
            return
        widget.edit_modified(False)
        self._mark_form_dirty()

    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.edit_modified(False)

    def _load_form(self) -> None:
        self._form_guard = True
        try:
            item = self.document.items.get(self.selected_item_id) if self.document and self.selected_item_id else None
            if item is None:
                self.identity_var.set("No item selected")
                for variable in (
                    self.name_var, self.glyph_var, self.category_var, self.weapon_var,
                    self.tags_var, self.item_drawable_var, self.appearance_family_var,
                    self.appearance_slots_var,
                    self.drawable_var,
                ):
                    variable.set("")
                self.stack_var.set("1")
                self.slot_cost_var.set("1")
                self.legal_var.set("legal")
                for widget in (self.description_text, self.effects_text, self.appearance_text, self.profiles_text):
                    self._set_text(widget, "")
                self._refresh_preview()
                return
            self.identity_var.set(f"{item.get('name') or self.selected_item_id} · {self.selected_item_id}")
            self.name_var.set(str(item.get("name") or ""))
            self.glyph_var.set(str(item.get("glyph") or ""))
            self.stack_var.set(str(item.get("stack_max", 1)))
            self.slot_cost_var.set(str(item.get("inventory_slot_cost", 1)))
            self.legal_var.set(str(item.get("legal_status") or "legal"))
            self.category_var.set(str(item.get("category") or ""))
            self.weapon_var.set(str(item.get("weapon_id") or ""))
            self.tags_var.set(", ".join(str(value) for value in item.get("tags", ())))
            self.item_drawable_var.set(str(item.get("item_drawable") or ""))
            self.appearance_family_var.set(str(item.get("appearance_family") or ""))
            self.appearance_slots_var.set(", ".join(str(value) for value in item.get("appearance_slots", ())))
            self.drawable_var.set(str(item.get("appearance_drawable") or ""))
            self._set_text(self.description_text, str(item.get("description") or ""))
            self._set_text(self.effects_text, json.dumps(item.get("effects", []), indent=2, ensure_ascii=False))
            appearance = item.get("appearance_profile")
            self._set_text(self.appearance_text, json.dumps(appearance, indent=2, ensure_ascii=False) if appearance is not None else "")
            profiles = {key: copy.deepcopy(item[key]) for key in ADVANCED_PROFILE_FIELDS if key in item}
            self._set_text(self.profiles_text, json.dumps(profiles, indent=2, ensure_ascii=False))
        finally:
            self._form_guard = False
        self._form_dirty = False
        self._refresh_preview()

    def _json_from_text(self, widget: tk.Text, label: str, *, default: Any) -> Any:
        source = widget.get("1.0", "end-1c").strip()
        if not source:
            return copy.deepcopy(default)
        try:
            return json.loads(source)
        except json.JSONDecodeError as exc:
            raise ItemDocumentError(f"{label}: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc

    def _collect_form(self) -> dict[str, Any]:
        if self.document is None or self.selected_item_id not in self.document.items:
            raise ItemDocumentError("select an item first")
        item = copy.deepcopy(self.document.items[self.selected_item_id])
        name = self.name_var.get().strip()
        glyph = self.glyph_var.get()
        if not name:
            raise ItemDocumentError("name cannot be empty")
        if not glyph:
            raise ItemDocumentError("glyph cannot be empty")
        try:
            stack_max = int(self.stack_var.get())
            slot_cost = int(self.slot_cost_var.get())
        except ValueError as exc:
            raise ItemDocumentError("stack max and inventory slot cost must be integers") from exc
        item.update({
            "name": name, "glyph": glyph, "stack_max": stack_max,
            "inventory_slot_cost": slot_cost, "legal_status": self.legal_var.get().strip(),
            "tags": _csv_values(self.tags_var.get()),
        })
        if slot_cost == 1 and "inventory_slot_cost" not in self.document.items[self.selected_item_id]:
            item.pop("inventory_slot_cost", None)
        for field_name, value in (
            ("description", self.description_text.get("1.0", "end-1c").strip()),
            ("category", self.category_var.get().strip()),
            ("weapon_id", self.weapon_var.get().strip()),
            ("item_drawable", self.item_drawable_var.get().strip()),
            ("appearance_family", self.appearance_family_var.get().strip()),
            ("appearance_drawable", self.drawable_var.get().strip()),
        ):
            if value:
                item[field_name] = value
            else:
                item.pop(field_name, None)
        slots = _csv_values(self.appearance_slots_var.get())
        if slots:
            item["appearance_slots"] = slots
        else:
            item.pop("appearance_slots", None)

        effects = self._json_from_text(self.effects_text, "Effects", default=[])
        if not isinstance(effects, list):
            raise ItemDocumentError("Effects must be a JSON list")
        item["effects"] = effects
        appearance = self._json_from_text(self.appearance_text, "Appearance profile", default=None)
        if appearance is not None and not isinstance(appearance, dict):
            raise ItemDocumentError("Appearance profile must be a JSON object")
        if appearance:
            item["appearance_profile"] = appearance
        else:
            item.pop("appearance_profile", None)
        profiles = self._json_from_text(self.profiles_text, "Advanced profiles", default={})
        if not isinstance(profiles, dict):
            raise ItemDocumentError("Advanced profiles must be one JSON object")
        unknown = sorted(set(profiles) - set(ADVANCED_PROFILE_FIELDS))
        if unknown:
            raise ItemDocumentError(f"Unknown advanced profile field {unknown[0]!r}")
        for key in ADVANCED_PROFILE_FIELDS:
            item.pop(key, None)
        item.update(copy.deepcopy(profiles))
        return item

    def _commit_form(self, *, show_error: bool) -> bool:
        if not self._form_dirty:
            return True
        try:
            replacement = self._collect_form()
        except ItemDocumentError as exc:
            self.validation_var.set(str(exc))
            if show_error:
                messagebox.showerror("Apply item", str(exc), parent=self)
            return False
        assert self.document is not None
        current = self.document.items[self.selected_item_id]
        if current != replacement:
            affected = {self.selected_item_id}
            before, before_order, before_selection = self._capture_history(affected)
            self.document.items[self.selected_item_id] = replacement
            self._record_history(before, before_order, before_selection, affected)
            self._redo.clear()
            self._update_dirty()
        self._form_dirty = False
        self._apply_filter()
        self._refresh_preview()
        return True

    def apply_form(self) -> bool:
        if not self._form_dirty:
            self.validation_var.set("No unapplied changes")
            return True
        ok = self._commit_form(show_error=True)
        if ok:
            self.set_shell_status(f"Applied edits to {self.selected_item_id}; save catalog to persist")
        return ok

    # ------------------------------------------------------------------
    # CRUD/history/save
    # ------------------------------------------------------------------

    def _capture_history(
        self,
        affected: set[str],
    ) -> tuple[dict[str, dict[str, Any] | None], tuple[str, ...], str]:
        assert self.document is not None
        values = {
            item_id: copy.deepcopy(self.document.items[item_id]) if item_id in self.document.items else None
            for item_id in affected
        }
        return values, tuple(self.document.items), self.selected_item_id

    def _record_history(
        self,
        before: dict[str, dict[str, Any] | None],
        before_order: tuple[str, ...],
        before_selection: str,
        affected: set[str],
    ) -> None:
        assert self.document is not None
        after = {
            item_id: copy.deepcopy(self.document.items[item_id]) if item_id in self.document.items else None
            for item_id in affected
        }
        self._undo.append(_ItemHistoryEntry(
            before=before,
            after=after,
            before_order=before_order,
            after_order=tuple(self.document.items),
            before_selection=before_selection,
            after_selection=self.selected_item_id,
        ))
        if len(self._undo) > 40:
            self._undo.pop(0)

    def _apply_history_state(
        self,
        values: dict[str, dict[str, Any] | None],
        order: tuple[str, ...],
        selection: str,
    ) -> None:
        assert self.document is not None
        combined = dict(self.document.items)
        for item_id, value in values.items():
            if value is None:
                combined.pop(item_id, None)
            else:
                combined[item_id] = copy.deepcopy(value)
        rebuilt = {item_id: combined.pop(item_id) for item_id in order if item_id in combined}
        rebuilt.update(combined)
        self.document.items = rebuilt
        self.selected_item_id = selection if selection in rebuilt else next(iter(rebuilt), "")

    def _update_dirty(self) -> None:
        self.dirty = bool(self.document and self.document.dumps() != self._saved_source)
        self.app.refresh_title()

    def new_item(self) -> bool:
        if self._form_dirty and not self._commit_form(show_error=True):
            return False
        item_id = simpledialog.askstring("New item", "Item ID ([a-z0-9_]+)", parent=self)
        if not item_id or self.document is None:
            return False
        item_id = item_id.strip().lower()
        affected = {item_id}
        before, before_order, before_selection = self._capture_history(affected)
        try:
            self.document.add(item_id)
        except ItemDocumentError as exc:
            messagebox.showerror("New item", str(exc), parent=self)
            return False
        self.selected_item_id = item_id
        self._record_history(before, before_order, before_selection, affected)
        self._redo.clear()
        self.search_var.set("")
        self.profile_filter_var.set("All items")
        self.legal_filter_var.set("All legality")
        self._update_dirty()
        self._apply_filter()
        self._load_form()
        return True

    def duplicate_item(self) -> bool:
        if not self.selected_item_id or self.document is None:
            return False
        if self._form_dirty and not self._commit_form(show_error=True):
            return False
        new_id = simpledialog.askstring(
            "Duplicate item", "New item ID", initialvalue=f"{self.selected_item_id}_copy", parent=self,
        )
        if not new_id:
            return False
        new_id = new_id.strip().lower()
        affected = {new_id}
        before, before_order, before_selection = self._capture_history(affected)
        try:
            self.document.duplicate(self.selected_item_id, new_id)
        except ItemDocumentError as exc:
            messagebox.showerror("Duplicate item", str(exc), parent=self)
            return False
        self.selected_item_id = new_id
        self._record_history(before, before_order, before_selection, affected)
        self._redo.clear()
        self._update_dirty()
        self._apply_filter()
        self._load_form()
        return True

    def rename_item(self) -> bool:
        if not self.selected_item_id or self.document is None:
            return False
        if self._form_dirty and not self._commit_form(show_error=True):
            return False
        external = self.services.items.external_references_to(self.selected_item_id)
        if external:
            messagebox.showerror(
                "Rename item",
                "This editor will not silently rewrite other content or Python files. References:\n\n"
                + "\n".join(_reference_lines(external)),
                parent=self,
            )
            return False
        old_id = self.selected_item_id
        new_id = simpledialog.askstring("Rename item", "New item ID", initialvalue=old_id, parent=self)
        if not new_id or new_id.strip().lower() == old_id:
            return False
        new_id = new_id.strip().lower()
        affected = {old_id, new_id}
        for owner, item in self.document.items.items():
            trap = item.get("trap_profile")
            container = item.get("container")
            if (
                isinstance(trap, dict) and trap.get("payload_item_id") == old_id
            ) or (
                isinstance(container, dict) and old_id in container.get("accepted_item_ids", ())
            ):
                affected.add(owner)
        before, before_order, before_selection = self._capture_history(affected)
        try:
            self.document.rename(old_id, new_id)
        except ItemDocumentError as exc:
            messagebox.showerror("Rename item", str(exc), parent=self)
            return False
        self.selected_item_id = new_id
        self._record_history(before, before_order, before_selection, affected)
        self._redo.clear()
        self._update_dirty()
        self._apply_filter()
        self._load_form()
        return True

    def _internal_references_to(self, item_id: str) -> list[str]:
        found: list[str] = []
        if self.document is None:
            return found
        for owner, item in self.document.items.items():
            trap = item.get("trap_profile")
            if isinstance(trap, dict) and trap.get("payload_item_id") == item_id:
                found.append(f"{owner}.trap_profile.payload_item_id")
            container = item.get("container")
            if isinstance(container, dict) and item_id in container.get("accepted_item_ids", ()):
                found.append(f"{owner}.container.accepted_item_ids")
        return found

    def delete_item(self) -> bool:
        if not self.selected_item_id or self.document is None:
            return False
        if self._form_dirty and not self._commit_form(show_error=True):
            return False
        references = list(self.services.items.external_references_to(self.selected_item_id))
        references.extend(self._internal_references_to(self.selected_item_id))
        if references:
            messagebox.showerror(
                "Delete item",
                "Cannot delete an item that is still referenced:\n\n"
                + "\n".join(_reference_lines(references)),
                parent=self,
            )
            return False
        if not messagebox.askyesno(
            "Delete item", f"Delete {self.selected_item_id!r} from the catalog?", parent=self,
        ):
            return False
        affected = {self.selected_item_id}
        before, before_order, before_selection = self._capture_history(affected)
        self.document.remove(self.selected_item_id)
        self.selected_item_id = next(iter(self.document.items), "")
        self._record_history(before, before_order, before_selection, affected)
        self._redo.clear()
        self._update_dirty()
        self._apply_filter()
        self._load_form()
        return True

    def undo(self) -> bool:
        if not self._undo or self.document is None:
            return False
        entry = self._undo.pop()
        self._apply_history_state(entry.before, entry.before_order, entry.before_selection)
        self._redo.append(entry)
        self._update_dirty()
        self._apply_filter()
        self._load_form()
        return True

    def redo(self) -> bool:
        if not self._redo or self.document is None:
            return False
        entry = self._redo.pop()
        self._apply_history_state(entry.after, entry.after_order, entry.after_selection)
        self._undo.append(entry)
        self._update_dirty()
        self._apply_filter()
        self._load_form()
        return True

    def save_catalog(self) -> bool:
        if self._form_dirty and not self._commit_form(show_error=True):
            return False
        if self.document is None:
            return False
        _normalized, issues = self._analyze_document()
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            details = "\n".join(format_item_issue(issue) for issue in errors[:12])
            messagebox.showerror("Save items", f"Resolve {len(errors)} error(s) before saving:\n\n{details}", parent=self)
            self._refresh_preview()
            return False
        try:
            self.services.items.save(self.document)
        except (OSError, ItemDocumentError, ValueError) as exc:
            messagebox.showerror("Save items", str(exc), parent=self)
            return False
        self._service_revision = self.services.items.revision
        self.document = self.services.items.document.clone()
        self._saved_source = self.document.dumps()
        self._analysis_source = self._saved_source
        self._analysis_reference_fingerprint = self.services.items.references.fingerprint
        self._analysis_normalized = copy.deepcopy(self.services.items.normalized)
        self._analysis_issues = list(self.services.items.issues)
        self.dirty = False
        self._undo.clear()
        self._redo.clear()
        self._load_form()
        self.app.refresh_title()
        self.set_shell_status("Saved game/items.json atomically; shared item preview refreshed")
        return True

    # ------------------------------------------------------------------
    # Preview/templates/handoffs
    # ------------------------------------------------------------------

    def _put_preview(self, widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _analyze_document(self) -> tuple[dict[str, dict[str, Any]], list[Any]]:
        if self.document is None:
            return {}, []
        source = self.document.dumps()
        reference_fingerprint = self.services.items.references.fingerprint
        if (
            source != self._analysis_source
            or reference_fingerprint != self._analysis_reference_fingerprint
        ):
            normalized = self.document.normalized()
            self._analysis_source = source
            self._analysis_reference_fingerprint = reference_fingerprint
            self._analysis_normalized = normalized
            self._analysis_issues = validate_item_document(
                self.document,
                self.services.items.references,
                normalized_catalog=normalized,
            )
        return self._analysis_normalized, self._analysis_issues

    def _refresh_preview(self) -> None:
        if self.document is None or self.selected_item_id not in self.document.items:
            for widget in (self.raw_text, self.normalized_text, self.issues_text):
                self._put_preview(widget, "No item selected")
            return
        item = self.document.items[self.selected_item_id]
        normalized_catalog, issues = self._analyze_document()
        normalized = normalized_catalog.get(self.selected_item_id, {})
        local = [issue for issue in issues if issue.path.startswith(f"$.{self.selected_item_id}")]
        errors = sum(issue.severity == "error" for issue in issues)
        warnings = sum(issue.severity == "warning" for issue in issues)
        self.validation_var.set(f"Catalog: {errors} error(s), {warnings} warning(s)")
        self._put_preview(self.raw_text, json.dumps(item, indent=2, ensure_ascii=False))
        self._put_preview(self.normalized_text, json.dumps(normalized, indent=2, ensure_ascii=False, default=list))
        references = list(self.services.items.external_references_to(self.selected_item_id))
        references.extend(self._internal_references_to(self.selected_item_id))
        lines = [format_item_issue(issue) for issue in local]
        if not lines:
            lines.append("No validation issues for this item.")
        lines.append("")
        lines.append("References to this item:")
        lines.extend(f"- {value}" for value in _reference_lines(references, limit=80))
        if not references:
            lines.append("- none in the catalog, declared JSON dependencies, or Python literals")
        if item != normalized:
            lines.extend(("", "Runtime preview includes defaults and normalized/clamped values; raw JSON remains canonical."))
        self._put_preview(self.issues_text, "\n".join(lines))

    def add_profile_template(self) -> bool:
        name = self.template_var.get()
        if name not in PROFILE_TEMPLATES:
            return False
        try:
            if name == "appearance_profile":
                existing = self._json_from_text(self.appearance_text, "Appearance profile", default={})
                if existing and not messagebox.askyesno("Replace profile", "Replace the current appearance profile?", parent=self):
                    return False
                drawable_ids = sorted(self.services.items.references.drawable_ids)
                drawable_id = self.drawable_var.get().strip()
                if not drawable_id:
                    if not drawable_ids:
                        raise ItemDocumentError(
                            "Appearance profiles also require a drawable; reload a root with drawables first"
                        )
                    drawable_id = "tee" if "tee" in drawable_ids else drawable_ids[0]
                    self.drawable_var.set(drawable_id)
                if not _csv_values(self.appearance_slots_var.get()):
                    self.appearance_slots_var.set("top")
                self._set_text(self.appearance_text, json.dumps(profile_template(name), indent=2))
            else:
                profiles = self._json_from_text(self.profiles_text, "Advanced profiles", default={})
                if not isinstance(profiles, dict):
                    raise ItemDocumentError("Advanced profiles must be an object")
                if name in profiles and not messagebox.askyesno("Replace profile", f"Replace {name}?", parent=self):
                    return False
                if name == "trap_profile":
                    assert self.document is not None
                    normalized, _issues = self._analyze_document()
                    payloads = sorted(
                        item_id for item_id, value in normalized.items()
                        if value.get("throw_profile")
                    )
                    if not payloads:
                        raise ItemDocumentError(
                            "Trap profiles require a throwable payload, but this catalog has none"
                        )
                    payload_id = "tear_gas_canister" if "tear_gas_canister" in payloads else payloads[0]
                    profiles[name] = profile_template(name, trap_payload_item_id=payload_id)
                else:
                    profiles[name] = profile_template(name)
                self._set_text(self.profiles_text, json.dumps(profiles, indent=2))
        except ItemDocumentError as exc:
            messagebox.showerror("Profile template", str(exc), parent=self)
            return False
        self._form_dirty = True
        self.validation_var.set("Unapplied profile template")
        return True

    def open_drawable(self) -> bool:
        drawable_id = self.drawable_var.get().strip()
        if not drawable_id:
            messagebox.showinfo("Drawable", "Set an appearance drawable ID first.", parent=self)
            return False
        mode = self.app.get_mode("drawables")
        if hasattr(mode, "open_drawable_id") and not mode.open_drawable_id(drawable_id):
            return False
        self.app.show_mode("drawables")
        return True

    def open_item_drawable(self) -> bool:
        drawable_id = self.item_drawable_var.get().strip()
        if not drawable_id:
            messagebox.showinfo(
                "Ground art",
                "Choose a ground drawable ID or create new art first.",
                parent=self,
            )
            return False
        mode = self.app.get_mode("drawables")
        if hasattr(mode, "open_drawable_id") and not mode.open_drawable_id(drawable_id):
            return False
        self.app.show_mode("drawables")
        return True

    def new_item_drawable(self) -> bool:
        if not self.selected_item_id:
            return False
        initial_id = self.item_drawable_var.get().strip() or f"{self.selected_item_id}_art"
        mode = self.app.get_mode("drawables")
        if not hasattr(mode, "new_ground_document"):
            messagebox.showerror(
                "Ground art",
                "The Drawables editor cannot create ground art in this build.",
                parent=self,
            )
            return False
        drawable_id = mode.new_ground_document(initial_id=initial_id)
        if not drawable_id:
            return False
        self.item_drawable_var.set(str(drawable_id))
        self.app.show_mode("drawables")
        return True

    def open_in_paper_doll(self) -> bool:
        if self._form_dirty and not self._commit_form(show_error=True):
            return False
        if self.dirty:
            if not messagebox.askyesno(
                "Paper Doll",
                "Paper Doll reads the shared saved catalog. Save these item changes first?",
                parent=self,
            ):
                return False
            if not self.save_catalog():
                return False
        mode = self.app.get_mode("paper_doll")
        self.app.show_mode("paper_doll")
        if hasattr(mode, "focus_item"):
            mode.focus_item(self.selected_item_id)
        return True

    def copy_raw_item(self) -> bool:
        if self.document is None or self.selected_item_id not in self.document.items:
            return False
        value = json.dumps(self.document.items[self.selected_item_id], indent=2, ensure_ascii=False)
        self.clipboard_clear()
        self.clipboard_append(value)
        self.update_idletasks()
        self.set_shell_status(f"Copied raw JSON for {self.selected_item_id}")
        return True

    def handle_action(self, action: str, event=None) -> bool:
        actions = {
            "new": self.new_item, "save": self.save_catalog,
            "undo": self.undo, "redo": self.redo,
            "duplicate": self.duplicate_item, "delete": self.delete_item,
            "copy": self.copy_raw_item,
        }
        function = actions.get(action)
        if function is None:
            return False
        return bool(function())
