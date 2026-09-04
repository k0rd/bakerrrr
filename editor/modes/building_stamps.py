"""Semantic shell authoring for the Bakerrrr Content Workbench."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from editor.mode_api import EditorMode, register_mode
from engine.building_stamp import (
    BUILDING_STAMP_FORMAT,
    BUILDING_STAMP_VERSION,
    BuildingStampError,
    building_stamp_data,
    parse_building_stamp_data,
    parse_building_stamp_file,
    serialize_building_stamp,
)


SHELL_TOOLS = (
    ("wall", "Wall", "#"),
    ("floor", "Floor", "."),
    ("void", "Void", " "),
    ("door", "Door", "D"),
    ("entry", "Entry", "D"),
    ("window", "Window", "W"),
    ("stairs", "Stairs", "S"),
    ("fixture", "Fixture", "F"),
)

SHELL_COLORS = {
    " ": "#202329",
    "#": "#66717f",
    ".": "#d3c8b5",
    "D": "#a66b39",
    "W": "#58a9cf",
    "S": "#d7b653",
    "F": "#b46fc5",
}

ZONE_COLORS = (
    "#7ab7a4",
    "#d49a72",
    "#8fa9d8",
    "#c48db7",
    "#b8b36e",
    "#7fb5c8",
    "#d47f7f",
    "#9aa76c",
)


def _new_stamp_data(stamp_id: str = "new_shell", width: int = 7, height: int = 7) -> dict:
    width = max(3, int(width))
    height = max(3, int(height))
    middle = width // 2
    shell = []
    zones = []
    for y in range(height):
        row = ["#"] * width if y in {0, height - 1} else ["#"] + (["."] * (width - 2)) + ["#"]
        if y == height - 1:
            row[middle] = "D"
        shell.append("".join(row))
        zones.append(" " * width)
    return {
        "format": BUILDING_STAMP_FORMAT,
        "version": BUILDING_STAMP_VERSION,
        "id": stamp_id,
        "size": {"width": width, "height": height},
        "placement": {
            "exterior_classes": ["building"],
            "clearance": 1,
            "rotations": [0, 90, 180, 270],
            "reflect": False,
        },
        "entry": {"x": middle, "y": height - 1, "z": 0, "side": "south"},
        "zone_legend": {"r": "room"},
        "floors": [{"z": 0, "shell": shell, "zones": zones}],
        "anchors": [],
    }


@register_mode
class BuildingStampMode(EditorMode):
    mode_id = "building_stamps"
    mode_title = "Building Stamps"
    mode_description = "Paint shell · place apertures · define rooms"
    content_domain = "building_stamps"

    def __init__(self, app, parent) -> None:
        super().__init__(app, parent)
        self.path: Path | None = None
        self.data = _new_stamp_data()
        self.tool = "wall"
        self.floor_z = 0
        self._cell_rects = {}

        toolbar = ttk.Frame(self, padding=(8, 7))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="New", command=self.new_document).pack(side="left")
        ttk.Button(toolbar, text="Open…", command=self.open_document).pack(side="left", padx=(4, 0))
        ttk.Button(toolbar, text="Save", command=self.save_document).pack(side="left", padx=(4, 0))
        ttk.Button(toolbar, text="Reload", command=self.reload_catalog).pack(side="left", padx=(4, 12))
        ttk.Label(toolbar, text="Floor").pack(side="left")
        self.floor_var = tk.StringVar(value="0")
        self.floor_box = ttk.Combobox(toolbar, textvariable=self.floor_var, width=5, state="readonly")
        self.floor_box.pack(side="left", padx=(4, 0))
        self.floor_box.bind("<<ComboboxSelected>>", self._floor_selected)
        self.identity_var = tk.StringVar(value="new_shell")
        ttk.Label(toolbar, textvariable=self.identity_var, font=("TkDefaultFont", 11, "bold")).pack(side="right")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        catalogue = ttk.Frame(body, padding=7)
        body.add(catalogue, weight=1)
        ttk.Label(catalogue, text="Shell catalogue", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.catalogue_list = tk.Listbox(catalogue, exportselection=False, width=24)
        self.catalogue_list.pack(fill="both", expand=True, pady=(6, 0))
        self.catalogue_list.bind("<Double-Button-1>", lambda _event: self.open_selected())
        ttk.Button(catalogue, text="Open selected", command=self.open_selected).pack(fill="x", pady=(6, 0))

        preview = ttk.Frame(body, padding=7)
        body.add(preview, weight=4)
        ttk.Label(preview, text="Semantic shell", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.canvas = tk.Canvas(preview, background="#202329", highlightthickness=1, highlightbackground="#68717d")
        self.canvas.pack(fill="both", expand=True, pady=(6, 0))
        self.canvas.bind("<Button-1>", self._paint_cell)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())

        inspector = ttk.Frame(body, padding=7)
        body.add(inspector, weight=2)
        ttk.Label(inspector, text="Shell", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.tool_var = tk.StringVar(value=self.tool)
        for tool_id, label, _glyph in SHELL_TOOLS:
            ttk.Radiobutton(
                inspector,
                text=label,
                value=tool_id,
                variable=self.tool_var,
                command=self._tool_selected,
            ).pack(anchor="w")

        ttk.Separator(inspector).pack(fill="x", pady=9)
        ttk.Label(inspector, text="Rooms", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.room_frame = ttk.Frame(inspector)
        self.room_frame.pack(fill="x", pady=(4, 0))
        ttk.Button(inspector, text="Add room type…", command=self.add_room_type).pack(fill="x", pady=(6, 0))
        ttk.Radiobutton(
            inspector,
            text="Clear room",
            value="zone: ",
            variable=self.tool_var,
            command=self._tool_selected,
        ).pack(anchor="w", pady=(3, 0))

        ttk.Separator(inspector).pack(fill="x", pady=9)
        self.validation_var = tk.StringVar()
        ttk.Label(inspector, textvariable=self.validation_var, wraplength=240, justify="left").pack(anchor="w")
        ttk.Label(
            inspector,
            text="Paint the footprint, place doors/windows, then paint named rooms.",
            wraplength=240,
            justify="left",
            foreground="#59636e",
        ).pack(anchor="w", pady=(10, 0))

        self.reload_catalog()
        self._refresh_document()

    def project_label(self) -> str:
        return f"Building Stamp: {self.data.get('id', 'untitled')}"

    def activate(self) -> None:
        self.redraw()

    def game_root_changed(self) -> None:
        self.reload_catalog()

    def _domain_root(self) -> Path | None:
        root = self.services.game.root
        return None if root is None else (root / "game" / "building_stamps").resolve()

    def reload_catalog(self) -> None:
        self.services.building_stamps.reload(self.services.game)
        self.catalogue_list.delete(0, "end")
        for stamp_id in sorted(self.services.building_stamps.catalog.definitions):
            self.catalogue_list.insert("end", stamp_id)
        error = self.services.building_stamps.error
        self.set_shell_status(error or f"{self.catalogue_list.size()} building stamp(s)")

    def open_selected(self) -> bool:
        selection = self.catalogue_list.curselection()
        if not selection:
            return False
        stamp_id = self.catalogue_list.get(selection[0])
        source = self.services.building_stamps.catalog.sources.get(stamp_id)
        return bool(source) and self._load_path(Path(source))

    def new_document(self) -> bool:
        if not self.maybe_save_changes():
            return False
        stamp_id = simpledialog.askstring("New building stamp", "Stamp ID", initialvalue="new_shell", parent=self)
        if not stamp_id:
            return False
        self.data = _new_stamp_data(str(stamp_id).strip().lower().replace(" ", "_"))
        self.path = None
        self.dirty = True
        self._refresh_document()
        self.app.refresh_title()
        return True

    def open_document(self) -> bool:
        if not self.maybe_save_changes():
            return False
        root = self._domain_root() or Path.cwd()
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Open building stamp",
            initialdir=str(root),
            filetypes=(("Building stamp JSON", "*.json"), ("All files", "*")),
        )
        return bool(chosen) and self._load_path(Path(chosen))

    def _load_path(self, path: Path) -> bool:
        try:
            stamp = parse_building_stamp_file(path)
        except (OSError, BuildingStampError) as exc:
            messagebox.showerror("Building stamp", str(exc), parent=self)
            return False
        self.data = building_stamp_data(stamp)
        self.path = path.resolve()
        self.floor_z = int(stamp.floors[0].z)
        self.dirty = False
        self._refresh_document()
        self.app.refresh_title()
        self.set_shell_status(f"Opened {self.services.game.display_path(self.path)}")
        return True

    def save_document(self, *, save_as: bool = False) -> bool:
        try:
            stamp = parse_building_stamp_data(self.data, source=str(self.path or "<editor>"))
        except BuildingStampError as exc:
            messagebox.showerror("Cannot save building stamp", str(exc), parent=self)
            return False
        target = self.path
        if save_as or target is None:
            root = self._domain_root()
            if root is None:
                messagebox.showerror("Building stamp", "Set a Bakerrrr root before saving.", parent=self)
                return False
            root.mkdir(parents=True, exist_ok=True)
            chosen = filedialog.asksaveasfilename(
                parent=self,
                title="Save building stamp",
                initialdir=str(root),
                initialfile=f"{stamp.stamp_id}.json",
                defaultextension=".json",
                filetypes=(("Building stamp JSON", "*.json"),),
            )
            if not chosen:
                return False
            target = Path(chosen).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                messagebox.showerror("Building stamp", f"Save inside {root}", parent=self)
                return False
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(serialize_building_stamp(stamp))
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, target)
        except OSError as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            messagebox.showerror("Building stamp", str(exc), parent=self)
            return False
        self.path = target
        self.data = building_stamp_data(stamp)
        self.dirty = False
        self.reload_catalog()
        self._refresh_document()
        self.app.refresh_title()
        self.set_shell_status(f"Saved {self.services.game.display_path(target)}")
        return True

    def maybe_save_changes(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved building stamp", "Save this building stamp?", parent=self)
        if answer is None:
            return False
        return self.save_document() if answer else True

    def handle_action(self, action: str, event=None) -> bool:
        actions = {
            "new": self.new_document,
            "open": self.open_document,
            "save": self.save_document,
            "save_as": lambda: self.save_document(save_as=True),
        }
        callback = actions.get(action)
        if callback is None:
            return False
        callback()
        return True

    def _floors(self) -> list[dict]:
        return [floor for floor in self.data.get("floors", []) if isinstance(floor, dict)]

    def _current_floor(self) -> dict | None:
        return next((floor for floor in self._floors() if int(floor.get("z", 0)) == self.floor_z), None)

    def _floor_selected(self, _event=None) -> None:
        try:
            self.floor_z = int(self.floor_var.get())
        except ValueError:
            self.floor_z = 0
        self.redraw()

    def _tool_selected(self) -> None:
        self.tool = self.tool_var.get()

    def add_room_type(self) -> None:
        room_id = simpledialog.askstring("Room type", "Room ID", initialvalue="stock_room", parent=self)
        if not room_id:
            return
        room_id = str(room_id).strip().lower().replace("-", "_").replace(" ", "_")
        legend = self.data.setdefault("zone_legend", {})
        used = set(legend)
        glyph = next((candidate for candidate in "abcdefghijklmnopqrstuvwxyz0123456789" if candidate not in used), "")
        if not glyph:
            messagebox.showerror("Room type", "This stamp has no free room symbols.", parent=self)
            return
        legend[glyph] = room_id
        self.dirty = True
        self._refresh_room_tools()
        self.tool_var.set(f"zone:{glyph}")
        self._tool_selected()
        self.app.refresh_title()

    def _paint_cell(self, event) -> None:
        cell = next((cell for cell, rect in self._cell_rects.items() if rect[0] <= event.x < rect[2] and rect[1] <= event.y < rect[3]), None)
        floor = self._current_floor()
        if cell is None or floor is None:
            return
        x, y = cell
        width = int(self.data["size"]["width"])
        shell = list(floor["shell"])
        zones = list(floor["zones"])
        if self.tool.startswith("zone:"):
            glyph = self.tool.removeprefix("zone:")
            if shell[y][x] not in {".", "D", "S", "F"} and glyph != " ":
                self.set_shell_status("Rooms can only be painted onto walkable cells")
                return
            row = list(zones[y])
            row[x] = glyph
            zones[y] = "".join(row)
        else:
            glyph = next(value for tool_id, _label, value in SHELL_TOOLS if tool_id == self.tool)
            if self.tool == "entry" and x not in {0, width - 1} and y not in {0, int(self.data["size"]["height"]) - 1}:
                self.set_shell_status("Entry must sit on the outside edge")
                return
            row = list(shell[y])
            row[x] = glyph
            shell[y] = "".join(row)
            if glyph not in {".", "D", "S", "F"}:
                zone_row = list(zones[y])
                zone_row[x] = " "
                zones[y] = "".join(zone_row)
            if self.tool == "entry":
                side = "north" if y == 0 else "west" if x == 0 else "east" if x == width - 1 else "south"
                self.data["entry"] = {"x": x, "y": y, "z": self.floor_z, "side": side}
        floor["shell"] = shell
        floor["zones"] = zones
        self.dirty = True
        self._validate_document()
        self.redraw()
        self.app.refresh_title()

    def _refresh_document(self) -> None:
        self.identity_var.set(str(self.data.get("id", "untitled")))
        floor_values = [str(int(floor.get("z", 0))) for floor in self._floors()]
        self.floor_box.configure(values=floor_values)
        if str(self.floor_z) not in floor_values and floor_values:
            self.floor_z = int(floor_values[0])
        self.floor_var.set(str(self.floor_z))
        self._refresh_room_tools()
        self._validate_document()
        self.redraw()

    def _refresh_room_tools(self) -> None:
        for child in self.room_frame.winfo_children():
            child.destroy()
        for glyph, room_id in sorted(self.data.get("zone_legend", {}).items(), key=lambda item: str(item[1])):
            ttk.Radiobutton(
                self.room_frame,
                text=str(room_id).replace("_", " ").title(),
                value=f"zone:{glyph}",
                variable=self.tool_var,
                command=self._tool_selected,
            ).pack(anchor="w")

    def _validate_document(self) -> bool:
        try:
            stamp = parse_building_stamp_data(self.data, source=str(self.path or "<editor>"))
        except BuildingStampError as exc:
            self.validation_var.set(f"Needs attention: {exc}")
            return False
        room_count = len(stamp.zone_legend)
        aperture_count = sum(row.count("D") + row.count("W") for floor in stamp.floors for row in floor.shell)
        self.validation_var.set(
            f"Valid · {stamp.width}×{stamp.height} · {len(stamp.floors)} floor(s) · "
            f"{aperture_count} aperture(s) · {room_count} room type(s)"
        )
        return True

    def redraw(self) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        self._cell_rects.clear()
        floor = self._current_floor()
        if floor is None:
            return
        width = int(self.data["size"]["width"])
        height = int(self.data["size"]["height"])
        canvas_w = max(120, self.canvas.winfo_width())
        canvas_h = max(120, self.canvas.winfo_height())
        cell_px = max(12, min((canvas_w - 32) // width, (canvas_h - 32) // height))
        origin_x = (canvas_w - cell_px * width) // 2
        origin_y = (canvas_h - cell_px * height) // 2
        legend = self.data.get("zone_legend", {})
        zone_color = {glyph: ZONE_COLORS[index % len(ZONE_COLORS)] for index, glyph in enumerate(sorted(legend))}
        entry = self.data.get("entry", {})
        anchors = {
            (int(anchor.get("x", -1)), int(anchor.get("y", -1)), int(anchor.get("z", 0))): anchor
            for anchor in self.data.get("anchors", [])
            if isinstance(anchor, dict)
        }
        for y in range(height):
            for x in range(width):
                left = origin_x + x * cell_px
                top = origin_y + y * cell_px
                rect = (left, top, left + cell_px, top + cell_px)
                self._cell_rects[(x, y)] = rect
                glyph = floor["shell"][y][x]
                zone_glyph = floor["zones"][y][x]
                fill = SHELL_COLORS.get(glyph, "#ff00ff")
                if zone_glyph != " " and glyph in {".", "D", "S", "F"}:
                    fill = zone_color.get(zone_glyph, fill)
                self.canvas.create_rectangle(*rect, fill=fill, outline="#343a43", width=1)
                label = zone_glyph.upper() if zone_glyph != " " else glyph if glyph != " " else ""
                if label:
                    self.canvas.create_text(
                        left + cell_px // 2,
                        top + cell_px // 2,
                        text=label,
                        fill="#16191e" if zone_glyph != " " or glyph in {".", "S", "F"} else "#f4f1e8",
                        font=("TkDefaultFont", max(8, cell_px // 3), "bold"),
                    )
                if int(entry.get("x", -1)) == x and int(entry.get("y", -1)) == y and int(entry.get("z", 0)) == self.floor_z:
                    self.canvas.create_rectangle(left + 3, top + 3, left + cell_px - 3, top + cell_px - 3, outline="#ffe277", width=3)
                if (x, y, self.floor_z) in anchors:
                    self.canvas.create_oval(left + 5, top + 5, left + cell_px - 5, top + cell_px - 5, outline="#ff6fd8", width=2)

        self.canvas.create_text(
            origin_x,
            max(9, origin_y - 10),
            anchor="w",
            text=f"z {self.floor_z} · {self.data.get('id', 'untitled')}",
            fill="#dce2e9",
            font=("TkDefaultFont", 10, "bold"),
        )
