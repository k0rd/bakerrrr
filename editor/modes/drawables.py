"""Drawable DSL authoring for the Bakerrrr Content Workbench.

The source text remains canonical.  Canvas previews are resolved, disposable
views of one presentation and must never replace symbolic expressions in the
document model.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from editor.mode_api import EditorMode, register_mode
from game.body_geometry import (
    ACTOR_KINDS,
    BODY_PROFILES,
    POINT_DESCRIPTIONS,
    SEMANTIC_POINTS,
    BodyGeometry,
    geometry_for_profile,
)
from game.drawable_dsl import (
    DRAWABLE_FILE_SUFFIX,
    DrawableDefinition,
    DrawableDocument,
    DrawableError,
    DrawableRenderContext,
    ResolvedDrawable,
    ResolvedShape,
    load_drawable_catalog,
    parse_drawable_text,
    resolve_drawable,
)


GROUND_PRESENTATION_SCAFFOLD = """    presentation ground:
        paint fabric = fill
        paint trim = edge

        variant compact:
            layer body:
                rect item fabric:
                    x left + 3
                    y top + 5
                    w right - left - 6
                    h bottom - top - 10
                    outline trim
                    width 0.5
            surface item:
                item"""


GROUND_DOCUMENT_TEMPLATE = """bakerrrr-drawable 2

drawable {drawable_id} context ground:
    paint body = fill
    paint trim = edge
    paint shadow = shade

    variant compact:
        layer body:
            rect item body:
                x left + 3
                y top + 4
                w right - left - 6
                h bottom - top - 8
                outline trim
                width 0.5
        surface item:
            item

    variant detailed:
        layer body:
            rect item body:
                x left + 3
                y top + 4
                w right - left - 6
                h bottom - top - 8
                outline trim
                width 0.5
            line detail shadow width 0.35:
                left + 5, mid
                right - 5, mid
        surface item:
            item
"""


def _line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def source_block_line_span(
    text: str,
    *,
    start_line: int,
    indent: int,
) -> tuple[int, int]:
    """Return the zero-based, end-exclusive line span of an indented block."""

    lines = str(text).splitlines()
    start = max(0, int(start_line) - 1)
    if start >= len(lines):
        raise ValueError(f"line {start_line} is outside the source document")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if not stripped:
            continue
        current_indent = _line_indent(lines[index])
        if stripped.startswith("#"):
            if current_indent <= indent:
                end = index
                break
            continue
        if current_indent <= indent:
            end = index
            break
    return start, end


def _definition(document: DrawableDocument, drawable_id: str) -> DrawableDefinition:
    target = str(drawable_id or "").strip().lower()
    for definition in document.drawables:
        if definition.drawable_id == target:
            return definition
    raise DrawableError(f"unknown drawable id {drawable_id!r}")


def presentation_source_line_span(
    text: str,
    document: DrawableDocument,
    drawable_id: str,
    context: str,
) -> tuple[int, int]:
    """Locate one authored presentation without maintaining a second parser."""

    definition = _definition(document, drawable_id)
    requested = str(context or "").strip().lower()
    if requested == definition.context:
        start, end = source_block_line_span(
            text,
            start_line=definition.location.line,
            indent=0,
        )
        nested_starts = [
            presentation.location.line - 1
            for presentation in definition.presentations
            if start < presentation.location.line - 1 < end
        ]
        return start, min(nested_starts, default=end)
    presentation = definition.presentation(requested)
    if presentation is None:
        raise DrawableError(
            f"drawable {definition.drawable_id!r} has no {requested!r} presentation",
            definition.location,
        )
    return source_block_line_span(
        text,
        start_line=presentation.location.line,
        indent=4,
    )


def add_ground_presentation_source(
    text: str,
    document: DrawableDocument,
    drawable_id: str,
) -> tuple[str, DrawableDocument]:
    """Insert a valid ground scaffold while retaining unrelated source text."""

    definition = _definition(document, drawable_id)
    if definition.presentation("ground") is not None:
        raise DrawableError(
            f"drawable {definition.drawable_id!r} already has a ground presentation",
            definition.location,
        )
    start, end = source_block_line_span(
        text,
        start_line=definition.location.line,
        indent=0,
    )
    lines = str(text).splitlines()
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    addition = [""] + GROUND_PRESENTATION_SCAFFOLD.splitlines()
    if insert_at < len(lines):
        addition.append("")
    result = "\n".join(lines[:insert_at] + addition + lines[insert_at:]).rstrip() + "\n"
    parsed = parse_drawable_text(result, source=document.source)
    return result, parsed


def remove_ground_presentation_source(
    text: str,
    document: DrawableDocument,
    drawable_id: str,
) -> tuple[str, DrawableDocument]:
    """Remove only the optional nested ground presentation from a drawable."""

    definition = _definition(document, drawable_id)
    if definition.context == "ground":
        raise DrawableError("a drawable's primary presentation cannot be removed", definition.location)
    presentation = definition.presentation("ground")
    if presentation is None:
        raise DrawableError(
            f"drawable {definition.drawable_id!r} has no ground presentation",
            definition.location,
        )
    start, end = source_block_line_span(
        text,
        start_line=presentation.location.line,
        indent=4,
    )
    lines = str(text).splitlines()
    remove_from = start
    while remove_from > definition.location.line and not lines[remove_from - 1].strip():
        remove_from -= 1
    result_lines = lines[:remove_from] + lines[end:]
    result = "\n".join(result_lines).rstrip() + "\n"
    parsed = parse_drawable_text(result, source=document.source)
    return result, parsed


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(token for token in re.split(r"[\s,]+", str(text or "").strip()) if token)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(value))) for value in rgb)


def _mix(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    if factor >= 1.0:
        return tuple(
            int(max(0, min(255, value + (255 - value) * (factor - 1.0))))
            for value in rgb
        )
    return tuple(int(max(0, min(255, value * factor))) for value in rgb)


@register_mode
class DrawableMode(EditorMode):
    """Author the exact symbolic drawable documents consumed by the game."""

    mode_id = "drawables"
    mode_title = "Drawables"
    mode_description = "Author worn and on-ground drawable presentations"
    content_domain = "drawables"

    def __init__(self, app, parent) -> None:
        super().__init__(app, parent)
        self.path: Path | None = None
        self.document: DrawableDocument | None = None
        self.selected_drawable_id = ""
        self._catalog_paths: list[Path] = []
        self._text_guard = False
        self._parse_after: str | None = None
        self._source_valid = False

        self.presentation_var = tk.StringVar(value="worn")
        self.fill_var = tk.StringVar(value="fill")
        self.material_var = tk.StringVar()
        self.detail_var = tk.StringVar()
        self.pattern_var = tk.StringVar()
        self.body_profile_var = tk.StringVar(value="mixed_standard")
        self.body_kind_var = tk.StringVar(value="civilian")
        self.show_points_var = tk.BooleanVar(value=True)
        self.point_var = tk.StringVar(value="shoulder_left")
        self.point_help_var = tk.StringVar()
        self.identity_var = tk.StringVar(value="No drawable open")
        self.presentation_summary_var = tk.StringVar(value="")
        self.validation_var = tk.StringVar(value="Set a Bakerrrr root to load drawable files")

        self._build_ui()
        for variable in (
            self.presentation_var,
            self.fill_var,
            self.material_var,
            self.detail_var,
            self.pattern_var,
            self.body_profile_var,
            self.body_kind_var,
            self.show_points_var,
        ):
            variable.trace_add("write", lambda *_args: self._selection_or_preview_changed())
        self.reload_catalog(open_first=True)

    # ------------------------------------------------------------------
    # UI and lifecycle
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=7)
        outer.pack(fill="both", expand=True)

        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(toolbar, text="New", command=self.new_document).pack(side="left")
        ttk.Button(toolbar, text="Open…", command=self.open_document).pack(side="left", padx=(4, 0))
        ttk.Button(toolbar, text="Save", command=self.save_document).pack(side="left", padx=(4, 0))
        ttk.Button(toolbar, text="Reload", command=self.reload_document).pack(side="left", padx=(4, 0))
        ttk.Button(toolbar, text="Validate", command=lambda: self._validate_source(show_dialog=True)).pack(side="left", padx=(12, 0))
        ttk.Label(toolbar, textvariable=self.identity_var, font=("TkDefaultFont", 11, "bold")).pack(side="right")

        panes = ttk.Panedwindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes, padding=(0, 0, 7, 0))
        panes.add(left, weight=1)
        ttk.Label(left, text="Drawable files", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.file_list = tk.Listbox(left, exportselection=False, height=8, width=28)
        self.file_list.pack(fill="x", pady=(5, 7))
        self.file_list.bind("<Double-Button-1>", lambda _event: self.open_selected_file())
        ttk.Button(left, text="Open selected file", command=self.open_selected_file).pack(fill="x")

        ttk.Separator(left).pack(fill="x", pady=9)
        ttk.Label(left, text="Drawables in file", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        drawable_holder = ttk.Frame(left)
        drawable_holder.pack(fill="both", expand=True, pady=(5, 0))
        self.drawable_list = tk.Listbox(drawable_holder, exportselection=False, activestyle="none", width=32)
        self.drawable_list.pack(side="left", fill="both", expand=True)
        drawable_scroll = ttk.Scrollbar(drawable_holder, orient="vertical", command=self.drawable_list.yview)
        drawable_scroll.pack(side="right", fill="y")
        self.drawable_list.configure(yscrollcommand=drawable_scroll.set)
        self.drawable_list.bind("<<ListboxSelect>>", self._on_drawable_selected)

        right = ttk.Panedwindow(panes, orient="vertical")
        panes.add(right, weight=5)

        preview = ttk.Frame(right, padding=(7, 0, 0, 7))
        right.add(preview, weight=3)
        controls = ttk.Frame(preview)
        controls.pack(fill="x", pady=(0, 5))
        ttk.Label(controls, text="Presentation").pack(side="left")
        self.worn_radio = ttk.Radiobutton(
            controls,
            text="Worn",
            value="worn",
            variable=self.presentation_var,
        )
        self.worn_radio.pack(side="left", padx=(6, 0))
        self.ground_radio = ttk.Radiobutton(
            controls,
            text="On ground",
            value="ground",
            variable=self.presentation_var,
        )
        self.ground_radio.pack(side="left", padx=(4, 0))
        self.add_ground_button = ttk.Button(controls, text="Add ground section", command=self.add_ground_presentation)
        self.add_ground_button.pack(side="left", padx=(12, 0))
        self.remove_ground_button = ttk.Button(controls, text="Remove ground section", command=self.remove_ground_presentation)
        self.remove_ground_button.pack(side="left", padx=(4, 0))

        condition_row = ttk.Frame(preview)
        condition_row.pack(fill="x", pady=(0, 5))
        ttk.Label(condition_row, text="Fill").pack(side="left")
        self.fill_box = ttk.Combobox(condition_row, textvariable=self.fill_var, state="normal", width=13)
        self.fill_box.pack(side="left", padx=(4, 10))
        ttk.Label(condition_row, text="Material").pack(side="left")
        ttk.Entry(condition_row, textvariable=self.material_var, width=14).pack(side="left", padx=(4, 10))
        ttk.Label(condition_row, text="Detail").pack(side="left")
        ttk.Entry(condition_row, textvariable=self.detail_var, width=14).pack(side="left", padx=(4, 10))
        ttk.Label(condition_row, text="Pattern").pack(side="left")
        ttk.Entry(condition_row, textvariable=self.pattern_var, width=14).pack(side="left", padx=(4, 0))

        body_row = ttk.Frame(preview)
        body_row.pack(fill="x", pady=(0, 5))
        ttk.Label(body_row, text="Body").pack(side="left")
        self.body_profile_box = ttk.Combobox(
            body_row,
            textvariable=self.body_profile_var,
            state="readonly",
            width=18,
            values=tuple(BODY_PROFILES),
        )
        self.body_profile_box.pack(side="left", padx=(4, 10))
        ttk.Label(body_row, text="Role").pack(side="left")
        self.body_kind_box = ttk.Combobox(
            body_row,
            textvariable=self.body_kind_var,
            state="readonly",
            width=10,
            values=tuple(sorted(ACTOR_KINDS)),
        )
        self.body_kind_box.pack(side="left", padx=(4, 10))
        ttk.Checkbutton(
            body_row,
            text="Show Points",
            variable=self.show_points_var,
        ).pack(side="left")
        ttk.Label(body_row, text="Point").pack(side="left", padx=(14, 0))
        self.point_box = ttk.Combobox(
            body_row,
            textvariable=self.point_var,
            state="readonly",
            width=21,
            values=SEMANTIC_POINTS,
        )
        self.point_box.pack(side="left", padx=(4, 4))
        self.point_box.bind("<<ComboboxSelected>>", self._point_selection_changed)
        ttk.Button(
            body_row,
            text="Insert Point",
            command=self._insert_selected_point,
        ).pack(side="left")

        self.point_help_var.set(self._point_help_text(self.point_var.get()))
        ttk.Label(
            preview,
            textvariable=self.point_help_var,
            justify="left",
            wraplength=960,
        ).pack(fill="x", pady=(0, 5))

        self.preview_canvas = tk.Canvas(
            preview,
            background="#202329",
            highlightthickness=1,
            highlightbackground="#5b6470",
            height=300,
        )
        self.preview_canvas.pack(fill="both", expand=True)
        self.preview_canvas.bind("<Configure>", lambda _event: self._draw_preview())
        ttk.Label(
            preview,
            textvariable=self.presentation_summary_var,
            justify="left",
            wraplength=960,
        ).pack(anchor="w", pady=(4, 0))

        source = ttk.Frame(right, padding=(7, 0, 0, 0))
        right.add(source, weight=4)
        source_header = ttk.Frame(source)
        source_header.pack(fill="x", pady=(0, 4))
        ttk.Label(source_header, text="Canonical drawable DSL", font=("TkDefaultFont", 11, "bold")).pack(side="left")
        self.validation_label = ttk.Label(source_header, textvariable=self.validation_var)
        self.validation_label.pack(side="right")
        source_holder = ttk.Frame(source)
        source_holder.pack(fill="both", expand=True)
        self.source_text = tk.Text(
            source_holder,
            wrap="none",
            undo=True,
            autoseparators=True,
            maxundo=200,
            font=("TkFixedFont", 10),
            background="#17191d",
            foreground="#e8e8e8",
            insertbackground="#e8e8e8",
            selectbackground="#43566e",
        )
        self.source_text.pack(side="left", fill="both", expand=True)
        source_y = ttk.Scrollbar(source_holder, orient="vertical", command=self.source_text.yview)
        source_y.pack(side="right", fill="y")
        source_x = ttk.Scrollbar(source, orient="horizontal", command=self.source_text.xview)
        source_x.pack(fill="x")
        self.source_text.configure(yscrollcommand=source_y.set, xscrollcommand=source_x.set)
        self.source_text.tag_configure("selected_presentation", background="#293443")
        self.source_text.bind("<<Modified>>", self._on_source_modified)

        self.fill_box.configure(values=sorted(self.services.palette.colors))

    def activate(self) -> None:
        self._draw_preview()

    def game_root_changed(self) -> None:
        if self.dirty:
            self.set_shell_status(
                "Drawables: the unsaved document remains open after the root change; use Save As or reload"
            )
            self._refresh_file_catalog()
            return
        self.path = None
        self.document = None
        self.selected_drawable_id = ""
        self.reload_catalog(open_first=True)

    def project_label(self) -> str:
        return self.path.name if self.path else "Drawables"

    def maybe_save_changes(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved drawable changes",
            "Save changes to the current drawable document?",
            parent=self,
        )
        if answer is None:
            return False
        if answer:
            return self.save_document()
        return True

    # ------------------------------------------------------------------
    # Catalogue and document lifecycle
    # ------------------------------------------------------------------

    def _domain_root(self) -> Path | None:
        root = self.services.game.root
        return None if root is None else (root / "game" / "drawables").resolve()

    def _path_in_domain(self, path: Path) -> bool:
        domain = self._domain_root()
        if domain is None:
            return False
        try:
            path.resolve().relative_to(domain)
        except (OSError, ValueError):
            return False
        return True

    def _refresh_file_catalog(self) -> None:
        self._catalog_paths = list(self.services.game.domain_files("drawables"))
        self.file_list.delete(0, "end")
        for path in self._catalog_paths:
            self.file_list.insert("end", self.services.game.display_path(path))
        if self.path is not None:
            resolved = self.path.resolve()
            for index, path in enumerate(self._catalog_paths):
                if path.resolve() == resolved:
                    self.file_list.selection_set(index)
                    self.file_list.see(index)
                    break

    def reload_catalog(self, *, open_first: bool = False) -> None:
        ok = self.services.drawables.reload(self.services.game)
        self._refresh_file_catalog()
        if not ok:
            self.validation_var.set(self.services.drawables.error)
            self.validation_label.configure(foreground="#d97777")
            self.set_shell_status(f"Drawable catalog: {self.services.drawables.error}")
            return
        if open_first and self.path is None and self._catalog_paths:
            self._load_path(self._catalog_paths[0], negotiate=False)
        else:
            self.set_shell_status(
                f"Drawables: {len(self.services.drawables.catalog.definitions)} definition(s)"
            )

    def open_selected_file(self) -> bool:
        selection = self.file_list.curselection()
        if not selection:
            return False
        return self._load_path(self._catalog_paths[int(selection[0])])

    def open_drawable_id(self, drawable_id: str) -> bool:
        """Open and select a catalog definition for another Workbench mode."""
        requested = str(drawable_id or "").strip().lower()
        definition = self.services.drawables.catalog.get(requested)
        if definition is None:
            messagebox.showerror("Drawable", f"Unknown drawable id {requested!r}.", parent=self)
            return False
        source_path = Path(definition.source)
        if not source_path.is_absolute() and self.services.game.root is not None:
            source_path = self.services.game.root / source_path
        if self.path != source_path.resolve():
            if not self._load_path(source_path):
                return False
        self.selected_drawable_id = requested
        self._refresh_drawable_list()
        self._refresh_selection_controls()
        return True

    def open_document(self) -> bool:
        root = self._domain_root()
        if root is None:
            messagebox.showerror("Drawables", "Set a Bakerrrr root before opening drawables.", parent=self)
            return False
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Open drawable document",
            initialdir=str(root),
            filetypes=(("Bakerrrr drawable", f"*{DRAWABLE_FILE_SUFFIX}"), ("All files", "*")),
        )
        return bool(chosen) and self._load_path(Path(chosen))

    def _load_path(self, path: Path, *, negotiate: bool = True) -> bool:
        resolved = path.resolve()
        if not self._path_in_domain(resolved):
            messagebox.showerror(
                "Drawables",
                "Drawable documents must stay inside the selected checkout's game/drawables directory.",
                parent=self,
            )
            return False
        if negotiate and not self.maybe_save_changes():
            return False
        try:
            text = resolved.read_text(encoding="utf-8")
            document = parse_drawable_text(text, source=str(resolved))
        except (OSError, UnicodeError, DrawableError) as exc:
            messagebox.showerror("Open drawable", str(exc), parent=self)
            return False
        self.path = resolved
        self._set_source(text, document, dirty=False)
        self._refresh_file_catalog()
        self.set_shell_status(f"Opened {self.services.game.display_path(resolved)}")
        self.app.refresh_title()
        return True

    def new_document(self) -> bool:
        return bool(self._new_document(context="garment", initial_id="new_drawable"))

    def new_ground_document(self, *, initial_id: str = "new_item_art") -> str:
        """Create a ground-only draft and return the chosen drawable ID."""

        return self._new_document(context="ground", initial_id=initial_id)

    def _new_document(self, *, context: str, initial_id: str) -> str:
        if not self.maybe_save_changes():
            return ""
        ground_only = context == "ground"
        drawable_id = simpledialog.askstring(
            "New ground art" if ground_only else "New drawable document",
            "First drawable ID",
            initialvalue=initial_id,
            parent=self,
        )
        if not drawable_id:
            return ""
        drawable_id = str(drawable_id).strip().lower().replace(" ", "_")
        if self.services.drawables.catalog.get(drawable_id) is not None:
            messagebox.showerror(
                "New drawable",
                f"Drawable {drawable_id!r} already exists; open it instead of creating a duplicate.",
                parent=self,
            )
            return ""
        if ground_only:
            text = GROUND_DOCUMENT_TEMPLATE.format(drawable_id=drawable_id)
        else:
            text = f"""bakerrrr-drawable 2

drawable {drawable_id} context garment:
    paint fabric = fill
    paint trim = edge

    variant compact:
        layer body:
            polygon garment fabric outline trim width 0.25:
                shoulder_left
                shoulder_right
                waist_right
                waist_left
        surface garment:
            garment
"""
        try:
            document = parse_drawable_text(text, source="<new drawable>")
        except DrawableError as exc:
            messagebox.showerror("New drawable", str(exc), parent=self)
            return ""
        self.path = None
        self._set_source(text, document, dirty=True)
        if ground_only:
            self.presentation_var.set("ground")
        self.set_shell_status("New ground-art document" if ground_only else "New drawable document")
        return drawable_id

    def reload_document(self) -> bool:
        if self.path is None:
            self.reload_catalog(open_first=True)
            return True
        return self._load_path(self.path)

    def _set_source(
        self,
        text: str,
        document: DrawableDocument,
        *,
        dirty: bool,
        selected_drawable_id: str | None = None,
    ) -> None:
        self._text_guard = True
        try:
            self.source_text.delete("1.0", "end")
            self.source_text.insert("1.0", text)
            self.source_text.edit_reset()
            self.source_text.edit_modified(False)
        finally:
            self._text_guard = False
        self.document = document
        self._source_valid = True
        self.validation_var.set(f"Valid · {len(document.drawables)} drawable(s)")
        self.validation_label.configure(foreground="#5f9f73")
        preferred = selected_drawable_id or self.selected_drawable_id
        ids = [definition.drawable_id for definition in document.drawables]
        self.selected_drawable_id = preferred if preferred in ids else (ids[0] if ids else "")
        self.dirty = bool(dirty)
        self._refresh_drawable_list()
        self._refresh_selection_controls()
        self.app.refresh_title()

    def _source(self) -> str:
        return self.source_text.get("1.0", "end-1c") + "\n"

    def _on_source_modified(self, _event=None) -> None:
        if self._text_guard:
            self.source_text.edit_modified(False)
            return
        if not self.source_text.edit_modified():
            return
        self.source_text.edit_modified(False)
        self.dirty = True
        self.app.refresh_title()
        self.validation_var.set("Checking…")
        self.validation_label.configure(foreground="#b49a61")
        if self._parse_after is not None:
            self.after_cancel(self._parse_after)
        self._parse_after = self.after(260, self._validate_source)

    def _validate_source(self, *, show_dialog: bool = False) -> bool:
        self._parse_after = None
        source = self._source()
        label = str(self.path or "<drawable editor>")
        try:
            document = parse_drawable_text(source, source=label)
        except DrawableError as exc:
            self._source_valid = False
            self.validation_var.set(str(exc))
            self.validation_label.configure(foreground="#d97777")
            self.presentation_summary_var.set("Source is invalid; preview retains the last valid document.")
            if show_dialog:
                messagebox.showerror("Drawable validation", str(exc), parent=self)
            return False
        self.document = document
        self._source_valid = True
        self.validation_var.set(f"Valid · {len(document.drawables)} drawable(s)")
        self.validation_label.configure(foreground="#5f9f73")
        self._refresh_drawable_list()
        self._refresh_selection_controls()
        if show_dialog:
            self.set_shell_status("Drawable source is valid")
        return True

    def save_document(self, *, save_as: bool = False) -> bool:
        if not self._validate_source(show_dialog=True) or self.document is None:
            return False
        domain = self._domain_root()
        if domain is None:
            messagebox.showerror("Drawables", "Set a Bakerrrr root before saving.", parent=self)
            return False
        target = self.path
        if save_as or target is None:
            initial = (
                self.document.drawables[0].drawable_id + DRAWABLE_FILE_SUFFIX
                if len(self.document.drawables) == 1
                else "drawables" + DRAWABLE_FILE_SUFFIX
            )
            chosen = filedialog.asksaveasfilename(
                parent=self,
                title="Save drawable document",
                initialdir=str(domain),
                initialfile=initial,
                defaultextension=DRAWABLE_FILE_SUFFIX,
                filetypes=(("Bakerrrr drawable", f"*{DRAWABLE_FILE_SUFFIX}"),),
            )
            if not chosen:
                return False
            target = Path(chosen).resolve()
        if target.suffix != DRAWABLE_FILE_SUFFIX or not self._path_in_domain(target):
            messagebox.showerror(
                "Drawables",
                f"Save a {DRAWABLE_FILE_SUFFIX} file inside {domain}.",
                parent=self,
            )
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        source = self._source()
        temporary: Path | None = None
        try:
            fd, raw_temp = tempfile.mkstemp(
                prefix=f".{target.stem}-",
                suffix=DRAWABLE_FILE_SUFFIX,
                dir=target.parent,
                text=True,
            )
            temporary = Path(raw_temp)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(source)
            parse_drawable_text(source, source=str(target))
            other_files = [
                path
                for path in self.services.game.domain_files("drawables")
                if path.resolve() != target.resolve()
            ]
            load_drawable_catalog(tuple(other_files) + (temporary,))
            if target.exists():
                os.chmod(temporary, target.stat().st_mode)
            else:
                os.chmod(temporary, 0o644)
            os.replace(temporary, target)
            temporary = None
        except (OSError, UnicodeError, DrawableError) as exc:
            messagebox.showerror("Cannot save drawable", str(exc), parent=self)
            return False
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass
        self.path = target
        self.document = parse_drawable_text(source, source=str(target))
        self.dirty = False
        self.services.drawables.reload(self.services.game)
        item_refresh_ok = self.services.items.reload(self.services.game, self.services.drawables)
        self._refresh_file_catalog()
        self._refresh_drawable_list()
        self._refresh_selection_controls()
        self.app.refresh_title()
        status = f"Saved {self.services.game.display_path(target)}"
        if not item_refresh_ok:
            status += f"; item references could not refresh: {self.services.items.error}"
        self.set_shell_status(status)
        return True

    # ------------------------------------------------------------------
    # Navigation and presentation operations
    # ------------------------------------------------------------------

    def _refresh_drawable_list(self) -> None:
        if self.document is None:
            self.drawable_list.delete(0, "end")
            return
        definitions = tuple(self.document.drawables)
        self.drawable_list.delete(0, "end")
        selected_index = None
        for index, definition in enumerate(definitions):
            contexts = [definition.context]
            contexts.extend(presentation.context for presentation in definition.presentations)
            status = "worn + ground" if "ground" in contexts and definition.context != "ground" else " / ".join(contexts)
            self.drawable_list.insert("end", f"{definition.drawable_id}  ·  {status}")
            if definition.drawable_id == self.selected_drawable_id:
                selected_index = index
        if selected_index is None and definitions:
            selected_index = 0
            self.selected_drawable_id = definitions[0].drawable_id
        if selected_index is not None:
            self.drawable_list.selection_set(selected_index)
            self.drawable_list.see(selected_index)

    def _on_drawable_selected(self, _event=None) -> None:
        if self.document is None:
            return
        selection = self.drawable_list.curselection()
        if not selection:
            return
        index = int(selection[0])
        if not (0 <= index < len(self.document.drawables)):
            return
        self.selected_drawable_id = self.document.drawables[index].drawable_id
        self._refresh_selection_controls()

    def _selected_definition(self) -> DrawableDefinition | None:
        if self.document is None or not self.selected_drawable_id:
            return None
        return next(
            (
                definition
                for definition in self.document.drawables
                if definition.drawable_id == self.selected_drawable_id
            ),
            None,
        )

    def _selected_context(self, definition: DrawableDefinition) -> str:
        if self.presentation_var.get() == "ground":
            return "ground"
        if definition.presentation("garment") is not None:
            return "garment"
        return definition.context

    def _selection_or_preview_changed(self) -> None:
        if not hasattr(self, "preview_canvas"):
            return
        self._refresh_selection_controls()

    def _refresh_selection_controls(self) -> None:
        definition = self._selected_definition()
        if definition is None:
            self.identity_var.set("No drawable open")
            self.add_ground_button.configure(state="disabled")
            self.remove_ground_button.configure(state="disabled")
            self.presentation_summary_var.set("")
            self._draw_preview()
            return
        ground = definition.presentation("ground")
        if definition.presentation("garment") is None:
            if self.presentation_var.get() != "ground":
                self.presentation_var.set("ground")
            self.worn_radio.configure(state="disabled")
        else:
            self.worn_radio.configure(state="normal")
        self.ground_radio.configure(state="normal")
        self.identity_var.set(definition.drawable_id)
        self.add_ground_button.configure(state="normal" if ground is None else "disabled")
        self.remove_ground_button.configure(
            state="normal" if ground is not None and definition.context != "ground" else "disabled"
        )
        self._highlight_selected_presentation()
        self._draw_preview()

    def _highlight_selected_presentation(self) -> None:
        self.source_text.tag_remove("selected_presentation", "1.0", "end")
        definition = self._selected_definition()
        if definition is None or self.document is None or not self._source_valid:
            return
        context = self._selected_context(definition)
        try:
            start, end = presentation_source_line_span(
                self._source(),
                self.document,
                definition.drawable_id,
                context,
            )
        except DrawableError:
            start = max(0, definition.location.line - 1)
            end = start + 1
        self.source_text.tag_add("selected_presentation", f"{start + 1}.0", f"{end + 1}.0")
        self.source_text.see(f"{start + 1}.0")

    def add_ground_presentation(self) -> bool:
        definition = self._selected_definition()
        if definition is None or not self._validate_source(show_dialog=True) or self.document is None:
            return False
        try:
            source, document = add_ground_presentation_source(
                self._source(),
                self.document,
                definition.drawable_id,
            )
        except DrawableError as exc:
            messagebox.showerror("Add ground presentation", str(exc), parent=self)
            return False
        self.presentation_var.set("ground")
        self._set_source(
            source,
            document,
            dirty=True,
            selected_drawable_id=definition.drawable_id,
        )
        self.set_shell_status(f"Added ground presentation to {definition.drawable_id}")
        return True

    def remove_ground_presentation(self) -> bool:
        definition = self._selected_definition()
        if definition is None or not self._validate_source(show_dialog=True) or self.document is None:
            return False
        if not messagebox.askyesno(
            "Remove ground presentation",
            f"Remove the complete on-ground section from {definition.drawable_id}?",
            parent=self,
        ):
            return False
        try:
            source, document = remove_ground_presentation_source(
                self._source(),
                self.document,
                definition.drawable_id,
            )
        except DrawableError as exc:
            messagebox.showerror("Remove ground presentation", str(exc), parent=self)
            return False
        self.presentation_var.set("worn")
        self._set_source(
            source,
            document,
            dirty=True,
            selected_drawable_id=definition.drawable_id,
        )
        self.set_shell_status(f"Removed ground presentation from {definition.drawable_id}")
        return True

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _preview_geometry(self, requested_variant: str) -> BodyGeometry:
        profile = self.body_profile_var.get().strip() or "mixed_standard"
        kind = self.body_kind_var.get().strip() or "civilian"
        # Match the game's compact/detailed branch boundary, then project both
        # through BodyGeometry's shared 16-unit drawable coordinates.
        px = 24 if requested_variant == "compact" else 48
        return geometry_for_profile(profile, px, kind=kind)

    def _context(
        self,
        context: str,
        *,
        geometry: BodyGeometry | None = None,
    ) -> DrawableRenderContext:
        conditions = {
            "material": _tokens(self.material_var.get()),
            "detail": _tokens(self.detail_var.get()),
            "pattern": _tokens(self.pattern_var.get()),
        }
        if context == "ground":
            return DrawableRenderContext.ground(**conditions)
        if geometry is None:
            geometry = self._preview_geometry("compact")
        return DrawableRenderContext.garment(geometry, **conditions)

    def _fill_rgb(self) -> tuple[int, int, int]:
        token = self.fill_var.get().strip() or "fill"
        return self.services.palette.colors.get(token, self.services.palette.colors.get("fill", (204, 126, 156)))

    def _paint_colors(self) -> dict[str, str]:
        fill = self._fill_rgb()
        return {
            "fill": _hex(fill),
            "edge": _hex(_mix(fill, 1.34)),
            "shade": _hex(_mix(fill, 0.58)),
            "outline": _hex(self.services.palette.colors.get("actor_outline", (16, 20, 28))),
        }

    def _draw_preview(self) -> None:
        if not hasattr(self, "preview_canvas"):
            return
        canvas = self.preview_canvas
        canvas.delete("all")
        width = max(600, canvas.winfo_width())
        height = max(260, canvas.winfo_height())
        definition = self._selected_definition()
        if definition is None:
            canvas.create_text(width / 2, height / 2, text="Open a drawable document", fill="#aeb5bf")
            return
        context_name = self._selected_context(definition)
        presentation = definition.presentation(context_name)
        if presentation is None:
            canvas.create_text(
                width / 2,
                height / 2,
                text=f"{definition.drawable_id} has no on-ground presentation yet",
                fill="#d5bd80",
                font=("TkDefaultFont", 12, "bold"),
            )
            self.presentation_summary_var.set(
                "On-ground art is optional. Add the section to author it; until then the game uses its generic item fallback."
            )
            return
        try:
            geometries: dict[str, BodyGeometry | None] = {}
            resolved = {}
            for variant in ("compact", "detailed"):
                geometry = (
                    self._preview_geometry(variant)
                    if context_name == "garment"
                    else None
                )
                geometries[variant] = geometry
                context = self._context(context_name, geometry=geometry)
                resolved[variant] = resolve_drawable(
                    definition,
                    context,
                    variant=variant,
                )
        except DrawableError as exc:
            canvas.create_text(width / 2, height / 2, text=str(exc), fill="#d97777", width=width - 40)
            self.presentation_summary_var.set(str(exc))
            return

        gap = 18
        margin = 12
        card_width = (width - margin * 2 - gap) / 2
        for index, requested in enumerate(("compact", "detailed")):
            left = margin + index * (card_width + gap)
            self._draw_resolved_card(
                canvas,
                resolved[requested],
                requested=requested,
                context=context_name,
                geometry=geometries[requested],
                left=left,
                top=8,
                width=card_width,
                height=height - 16,
            )
        variant_bits = []
        for requested in ("compact", "detailed"):
            item = resolved[requested]
            fallback = f" -> {item.variant}" if item.variant != requested else ""
            variant_bits.append(
                f"{requested}{fallback}: {len(item.shapes)} shapes, "
                f"{len(item.surfaces)} surface(s)"
            )
        self.presentation_summary_var.set(
            f"{context_name.title()} · {len(presentation.paints)} paint aliases · "
            f"{len(presentation.lets)} shared bindings · " + " · ".join(variant_bits)
        )

    def _draw_resolved_card(
        self,
        canvas: tk.Canvas,
        resolved: ResolvedDrawable,
        *,
        requested: str,
        context: str,
        geometry: BodyGeometry | None,
        left: float,
        top: float,
        width: float,
        height: float,
    ) -> None:
        canvas.create_rectangle(
            left,
            top,
            left + width,
            top + height,
            fill="#282c32",
            outline="#4d5662",
        )
        fallback = f" (uses {resolved.variant})" if resolved.variant != requested else ""
        canvas.create_text(
            left + 10,
            top + 9,
            anchor="nw",
            text=f"{requested.title()}{fallback}",
            fill="#dce1e8",
            font=("TkDefaultFont", 10, "bold"),
        )
        art_size = max(80.0, min(width - 32.0, height - 52.0))
        scale = art_size / 16.0
        origin_x = left + (width - art_size) / 2.0
        origin_y = top + 34.0 + max(0.0, (height - 42.0 - art_size) / 2.0)

        canvas.create_rectangle(
            origin_x,
            origin_y,
            origin_x + art_size,
            origin_y + art_size,
            fill="#1c2025",
            outline="#3d4651",
        )
        for unit in range(1, 16):
            color = "#242a31" if unit != 8 else "#39434f"
            canvas.create_line(
                origin_x + unit * scale,
                origin_y,
                origin_x + unit * scale,
                origin_y + art_size,
                fill=color,
            )
            canvas.create_line(
                origin_x,
                origin_y + unit * scale,
                origin_x + art_size,
                origin_y + unit * scale,
                fill=color,
            )

        if context == "garment" and geometry is not None:
            self._draw_mannequin(canvas, origin_x, origin_y, scale, geometry)
        else:
            canvas.create_oval(
                origin_x + 2.0 * scale,
                origin_y + 12.7 * scale,
                origin_x + 14.0 * scale,
                origin_y + 14.6 * scale,
                fill="#15181c",
                outline="",
            )
        paints = self._paint_colors()
        for shape in resolved.shapes:
            self._draw_shape(canvas, shape, origin_x, origin_y, scale, paints)

    def _draw_mannequin(
        self,
        canvas: tk.Canvas,
        ox: float,
        oy: float,
        scale: float,
        geometry: BodyGeometry,
    ) -> None:
        """Draw the exact shared preview body behind the garment.

        This is intentionally derived from BodyGeometry rather than a second
        editor mannequin model.  If the game's body geometry moves, preview
        Points and the mannequin move together.
        """

        skin = _hex(self.services.palette.colors.get("skin", (213, 168, 142)))
        outline = "#5a443b"
        public_points = geometry.drawable_anchors
        internal = geometry.internal_drawable_anchors

        def canvas_point(point: tuple[float, float]) -> tuple[float, float]:
            return ox + point[0] * scale, oy + point[1] * scale

        # Head bounds come from the same crown/chin and side points that feed
        # garment measurements such as head_width/head_height.
        head_left = internal["head_left"]
        head_right = internal["head_right"]
        crown = public_points["crown"]
        chin = public_points["chin"]
        canvas.create_oval(
            *canvas_point((head_left[0], crown[1])),
            *canvas_point((head_right[0], chin[1])),
            fill=skin,
            outline=outline,
        )

        # The visual contour is derived beside the exact semantic Points.  A
        # meaningful Point such as hip_left need not become a sharp polygon
        # corner merely because authors can attach garments to it.
        torso = [canvas_point(point) for point in geometry.drawable_torso_contour]
        canvas.create_polygon(
            *(value for pair in torso for value in pair),
            fill=skin,
            outline=outline,
        )

        def limb(
            path: tuple[tuple[float, float], ...],
            width_names: tuple[str, str],
        ) -> None:
            canvas_points = [canvas_point(point_value) for point_value in path]
            a = public_points[width_names[0]]
            b = public_points[width_names[1]]
            logical_width = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
            canvas.create_line(
                *(value for pair in canvas_points for value in pair),
                fill=skin,
                width=max(2, int(round(logical_width * scale))),
                joinstyle="round",
                capstyle="round",
            )

        limb(
            geometry.drawable_limb_paths["arm_left"],
            ("wrist_inner_left", "wrist_outer_left"),
        )
        limb(
            geometry.drawable_limb_paths["arm_right"],
            ("wrist_inner_right", "wrist_outer_right"),
        )
        limb(
            geometry.drawable_limb_paths["leg_left"],
            ("knee_inner_left", "knee_outer_left"),
        )
        limb(
            geometry.drawable_limb_paths["leg_right"],
            ("knee_inner_right", "knee_outer_right"),
        )

        if self.show_points_var.get():
            radius = max(1.5, scale * 0.10)
            for name, point_value in public_points.items():
                x, y = canvas_point(point_value)
                tag = f"body_point_{name}"
                canvas.create_oval(
                    x - radius,
                    y - radius,
                    x + radius,
                    y + radius,
                    fill="#d7e4f2",
                    outline="#16202a",
                    tags=("body_point", tag),
                )
                canvas.tag_bind(
                    tag,
                    "<Enter>",
                    lambda _event, value=name: self._show_point_help(value),
                )
                canvas.tag_bind(
                    tag,
                    "<Leave>",
                    lambda _event: self._show_point_help(self.point_var.get()),
                )
                canvas.tag_bind(
                    tag,
                    "<Button-1>",
                    lambda _event, value=name: self._insert_point(value),
                )

    @staticmethod
    def _point_help_text(name: str) -> str:
        name = str(name or "").strip()
        description = POINT_DESCRIPTIONS.get(
            name,
            "Exact public body-geometry Point.",
        )
        return (
            f"{name} — {description} "
            "Click a preview Point or Insert Point to write its bare DSL name."
        )

    def _show_point_help(self, name: str) -> None:
        self.point_help_var.set(self._point_help_text(name))

    def _point_selection_changed(self, _event=None) -> None:
        self._show_point_help(self.point_var.get())

    def _insert_selected_point(self) -> None:
        self._insert_point(self.point_var.get())

    def _insert_point(self, name: str) -> None:
        name = str(name or "").strip()
        if name not in SEMANTIC_POINTS:
            return
        self.point_var.set(name)
        self._show_point_help(name)
        self.source_text.insert("insert", name)
        self.source_text.focus_set()
        self.source_text.see("insert")

    @staticmethod
    def _draw_shape(
        canvas: tk.Canvas,
        shape: ResolvedShape,
        ox: float,
        oy: float,
        scale: float,
        paints: dict[str, str],
    ) -> None:
        fill = paints.get(shape.paint_role, paints["fill"])
        outline = paints.get(str(shape.outline_role), "") if shape.outline_role else ""
        outline_width = max(1, int(round(float(shape.outline_width or 0) * scale))) if outline else 0

        def point(x: float, y: float) -> tuple[float, float]:
            return ox + x * scale, oy + y * scale

        if shape.kind == "polygon":
            coords = [value for x, y in shape.points for value in point(x, y)]
            canvas.create_polygon(*coords, fill=fill, outline=outline, width=outline_width)
        elif shape.kind == "line":
            points = list(shape.points)
            if shape.closed and points:
                points.append(points[0])
            coords = [value for x, y in points for value in point(x, y)]
            canvas.create_line(
                *coords,
                fill=fill,
                width=max(1, int(round(float(shape.stroke_width or 0.25) * scale))),
                joinstyle="round",
                capstyle="round",
            )
        elif shape.kind in {"rect", "ellipse"} and shape.box is not None:
            x, y, box_width, box_height = shape.box
            bounds = (*point(x, y), *point(x + box_width, y + box_height))
            creator = canvas.create_rectangle if shape.kind == "rect" else canvas.create_oval
            creator(*bounds, fill=fill, outline=outline, width=outline_width)
        elif shape.kind == "circle" and shape.points and shape.radius is not None:
            x, y = shape.points[0]
            radius = float(shape.radius)
            creator_bounds = (*point(x - radius, y - radius), *point(x + radius, y + radius))
            canvas.create_oval(*creator_bounds, fill=fill, outline=outline, width=outline_width)

    # ------------------------------------------------------------------
    # Shell actions
    # ------------------------------------------------------------------

    def _text_undo(self) -> None:
        try:
            self.source_text.edit_undo()
        except tk.TclError:
            self.bell()

    def _text_redo(self) -> None:
        try:
            self.source_text.edit_redo()
        except tk.TclError:
            self.bell()

    def handle_action(self, action: str, event: tk.Event | None = None) -> bool:
        actions = {
            "new": self.new_document,
            "open": self.open_document,
            "save": self.save_document,
            "save_as": lambda: self.save_document(save_as=True),
            "undo": self._text_undo,
            "redo": self._text_redo,
            "import": lambda: self.reload_catalog(open_first=False),
            "help": self.show_help,
        }
        func = actions.get(action)
        if func is None:
            return False
        func()
        return True

    def show_help(self) -> None:
        messagebox.showinfo(
            "Drawable editor",
            "The source pane edits the exact symbolic DSL consumed by the game.\n\n"
            "Choose Worn or On ground to focus and preview that presentation. Worn previews use the same shared body geometry as the game; choose a body profile/role and optionally show its exact semantic Points. Click a Point to insert its bare reserved name into the source. Compact and detailed are shown side by side; when detailed is absent, the preview explicitly labels compact fallback.\n\n"
            "In v2, point name = ... creates a Point; let name = ... creates a Scalar; and let (x, y) = point_name explicitly extracts coordinates. Numeric literals are ratios, so a body coordinate cannot silently be nudged by an unscaled 1. distance, x_distance, and y_distance produce body-scaled lengths.\n\n"
            "Add ground section creates a valid starting block. Saving parses the document, validates it against every other drawable file, and atomically replaces the target only after those checks pass.",
            parent=self,
        )
