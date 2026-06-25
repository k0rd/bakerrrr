"""Runtime-only vision scenes used by dreams and future vision services."""

from __future__ import annotations

import copy
import random
from typing import Any

from game.components import AI, CreatureIdentity, Position, Vitality


VISION_SCENE_SCHEMA_VERSION = 1
VISION_STEP_TICKS = 7
VISION_MIN_ACTORS = 5
VISION_MAX_ACTORS = 14

_BOARD_W = 48
_BOARD_H = 18

_RECIPE_PROFILES = (
    {
        "id": "quiet_wrong_room",
        "weight": 18,
        "stressor": "none",
        "layout": "room",
        "behaviors": ("wander", "gather", "pause"),
        "palette": ("floor", "shadow", "door"),
    },
    {
        "id": "shared_hall_after_close",
        "weight": 16,
        "stressor": "trespass",
        "layout": "hall",
        "behaviors": ("wander", "flee", "protect", "gather"),
        "palette": ("floor", "counter", "door", "window"),
    },
    {
        "id": "market_after_close",
        "weight": 15,
        "stressor": "market",
        "layout": "market",
        "behaviors": ("wander", "gather", "pause"),
        "palette": ("floor", "counter", "table", "shadow"),
    },
    {
        "id": "rubber_hose_squad",
        "weight": 8,
        "stressor": "fake_justice",
        "layout": "station",
        "behaviors": ("patrol", "flee", "protect", "pause"),
        "palette": ("floor", "table", "door", "shadow"),
    },
    {
        "id": "animal_at_the_door",
        "weight": 8,
        "stressor": "animal_pressure",
        "layout": "yard",
        "behaviors": ("flee", "gather", "wander"),
        "palette": ("floor", "grass", "door", "shadow"),
    },
    {
        "id": "long_service_corridor",
        "weight": 12,
        "stressor": "maze",
        "layout": "corridor",
        "behaviors": ("wander", "patrol", "pause"),
        "palette": ("floor", "door", "window", "shadow"),
    },
    {
        "id": "empty_counter_light",
        "weight": 10,
        "stressor": "none",
        "layout": "counter",
        "behaviors": ("pause", "wander"),
        "palette": ("floor", "counter", "table", "window"),
    },
)

_DREAM_ONLY_FIGURES = (
    {"glyph": "D", "color": "rodent", "semantic_id": "npc_animal", "behavior": "chase", "taxonomy": "rodent"},
    {"glyph": "C", "color": "canine", "semantic_id": "npc_animal", "behavior": "chase", "taxonomy": "canine"},
    {"glyph": "@", "color": "guard", "semantic_id": "npc_guard", "behavior": "patrol", "taxonomy": "hominid"},
    {"glyph": "?", "color": "objective", "semantic_id": "npc_civilian", "behavior": "wander", "taxonomy": "hominid"},
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _event_data(event_or_data: Any) -> dict:
    if isinstance(event_or_data, dict):
        return event_or_data
    data = getattr(event_or_data, "data", None)
    return data if isinstance(data, dict) else {}


def event_is_vision_only(event_or_data: Any) -> bool:
    """Return True when an event/record belongs to an isolated vision scene."""
    data = _event_data(event_or_data)
    if not data:
        return False
    if bool(data.get("vision_only")) or bool(data.get("consequence_ineligible")):
        return True
    if _text(data.get("vision_scene_id")):
        return True
    if _text(data.get("dream_actor_id")):
        return True
    return False


def vision_scene_active(sim) -> bool:
    scene = getattr(sim, "vision_scene", None)
    return isinstance(scene, dict) and bool(scene.get("active"))


def _current_tick(sim) -> int:
    try:
        return int(getattr(sim, "tick", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _seed_text(sim, *parts: Any) -> str:
    return ":".join(str(part) for part in (getattr(sim, "seed", 0), *parts))


def _weighted_choice(rng: random.Random, rows: tuple[dict, ...]) -> dict:
    total = sum(max(0, int(row.get("weight", 1) or 1)) for row in rows)
    if total <= 0:
        return dict(rows[0])
    roll = rng.randrange(total)
    cursor = 0
    for row in rows:
        cursor += max(0, int(row.get("weight", 1) or 1))
        if roll < cursor:
            return dict(row)
    return dict(rows[-1])


def _base_tiles(layout: str) -> list[list[str]]:
    tiles = [["floor" for _x in range(_BOARD_W)] for _y in range(_BOARD_H)]
    for x in range(_BOARD_W):
        tiles[0][x] = "wall"
        tiles[_BOARD_H - 1][x] = "wall"
    for y in range(_BOARD_H):
        tiles[y][0] = "wall"
        tiles[y][_BOARD_W - 1] = "wall"

    layout = _text(layout).lower() or "room"
    if layout == "hall":
        for y in range(2, _BOARD_H - 2):
            if y not in {5, 11, 14}:
                tiles[y][10] = "wall"
                tiles[y][_BOARD_W - 11] = "wall"
        for x in range(14, _BOARD_W - 14):
            tiles[5][x] = "door" if x % 9 == 0 else "shadow"
            tiles[12][x] = "window" if x % 8 == 0 else "floor"
    elif layout == "market":
        for x in range(5, _BOARD_W - 5, 7):
            for y in range(4, _BOARD_H - 4):
                if y % 5 in {0, 1}:
                    tiles[y][x] = "counter"
                    if x + 1 < _BOARD_W - 1:
                        tiles[y][x + 1] = "table"
    elif layout == "station":
        for x in range(8, _BOARD_W - 8):
            tiles[6][x] = "table" if x % 2 == 0 else "shadow"
        for y in range(3, _BOARD_H - 3):
            tiles[y][5] = "wall"
            tiles[y][_BOARD_W - 6] = "wall"
        tiles[9][5] = "door"
        tiles[9][_BOARD_W - 6] = "door"
    elif layout == "yard":
        for y in range(1, _BOARD_H - 1):
            for x in range(1, _BOARD_W - 1):
                if (x * 7 + y * 11) % 13 in {0, 1, 2}:
                    tiles[y][x] = "grass"
        for x in range(16, 32):
            tiles[9][x] = "wall"
        tiles[9][23] = "door"
    elif layout == "corridor":
        for y in range(3, _BOARD_H - 3):
            for x in range(4, _BOARD_W - 4):
                if y in {3, _BOARD_H - 4} and x % 6 != 0:
                    tiles[y][x] = "wall"
                elif x in {8, _BOARD_W - 9} and y % 5 != 0:
                    tiles[y][x] = "wall"
        for x in range(10, _BOARD_W - 10, 8):
            tiles[3][x] = "door"
            tiles[_BOARD_H - 4][x] = "window"
    elif layout == "counter":
        for x in range(8, _BOARD_W - 8):
            tiles[7][x] = "counter"
        for x in range(12, _BOARD_W - 12, 9):
            tiles[4][x] = "window"
            tiles[12][x] = "table"
    else:
        for x in range(12, _BOARD_W - 12):
            if x % 5 != 0:
                tiles[4][x] = "window"
        for x in range(17, 31):
            tiles[11][x] = "table" if x % 3 else "shadow"
        tiles[_BOARD_H - 1][24] = "door"
    return tiles


def _walkable(scene: dict, x: int, y: int) -> bool:
    if x <= 0 or y <= 0 or x >= int(scene.get("width", _BOARD_W)) - 1 or y >= int(scene.get("height", _BOARD_H)) - 1:
        return False
    tiles = scene.get("tiles")
    if not isinstance(tiles, list) or y >= len(tiles) or x >= len(tiles[y]):
        return False
    return str(tiles[y][x]) not in {"wall", "window"}


def _actor_snapshot(sim, eid: int, *, player_eid=None) -> dict | None:
    positions = sim.ecs.get(Position)
    identities = sim.ecs.get(CreatureIdentity)
    pos = positions.get(eid)
    identity = identities.get(eid)
    if pos is None or identity is None:
        return None
    vitality = sim.ecs.get(Vitality).get(eid)
    if vitality is not None and (bool(getattr(vitality, "downed", False)) or int(getattr(vitality, "hp", 1) or 0) <= 0):
        return None
    appearance = None
    try:
        appearance = sim.appearance.entity(eid, player_eid=player_eid)
    except Exception:
        appearance = None
    ai = sim.ecs.get(AI).get(eid)
    glyph = getattr(appearance, "glyph", None) or identity.taxonomy_glyph("@")
    color = getattr(appearance, "color", None) or ("human" if identity.taxonomy_class == "hominid" else "animal")
    return {
        "source_eid": int(eid),
        "source_x": int(pos.x),
        "source_y": int(pos.y),
        "source_z": int(pos.z),
        "taxonomy": _text(getattr(identity, "taxonomy_class", "")) or "hominid",
        "role": _text(getattr(ai, "role", "")) or _text(getattr(identity, "creature_type", "")) or "actor",
        "glyph": str(glyph)[:1] or "@",
        "color": color,
        "semantic_id": getattr(appearance, "semantic_id", None) or ("npc_civilian" if identity.taxonomy_class == "hominid" else "npc_animal"),
        "effects": tuple(getattr(appearance, "effects", ()) or ()),
        "overlays": tuple(copy.deepcopy(getattr(appearance, "overlays", ()) or ())),
    }


def _candidate_actor_snapshots(sim, *, player_eid=None, limit=VISION_MAX_ACTORS) -> list[dict]:
    positions = sim.ecs.get(Position)
    player_pos = positions.get(player_eid) if player_eid is not None else None
    rows = []
    for raw_eid in tuple(sim.ecs.get(CreatureIdentity).keys()):
        try:
            eid = int(raw_eid)
        except (TypeError, ValueError):
            continue
        if player_eid is not None and eid == int(player_eid):
            continue
        snap = _actor_snapshot(sim, eid, player_eid=player_eid)
        if not snap:
            continue
        pos = positions.get(eid)
        dist = 9999
        if player_pos is not None and pos is not None and int(pos.z) == int(player_pos.z):
            dist = abs(int(pos.x) - int(player_pos.x)) + abs(int(pos.y) - int(player_pos.y))
        rank = (0 if dist <= 24 else 1, dist, eid)
        rows.append((rank, snap))
    rows.sort(key=lambda row: row[0])
    return [snap for _rank, snap in rows[: max(0, int(limit))]]


def _spawn_point(rng: random.Random, scene: dict) -> tuple[int, int]:
    for _attempt in range(200):
        x = rng.randint(2, int(scene.get("width", _BOARD_W)) - 3)
        y = rng.randint(2, int(scene.get("height", _BOARD_H)) - 3)
        if _walkable(scene, x, y):
            return x, y
    return int(scene.get("width", _BOARD_W)) // 2, int(scene.get("height", _BOARD_H)) // 2


def _dream_actor_from_snapshot(rng: random.Random, scene: dict, snap: dict, idx: int, behavior_pool: tuple[str, ...]) -> dict:
    x, y = _spawn_point(rng, scene)
    behavior = rng.choice(tuple(behavior_pool or ("wander",)))
    if _text(snap.get("role")).lower() in {"guard", "security", "watcher", "justice"}:
        behavior = rng.choice(("patrol", "protect", behavior))
    return {
        "dream_actor_id": f"a{idx:02d}",
        "source_eid": snap.get("source_eid"),
        "x": x,
        "y": y,
        "prev_x": x,
        "prev_y": y,
        "glyph": snap.get("glyph", "@"),
        "color": snap.get("color", "human"),
        "semantic_id": snap.get("semantic_id", "npc_civilian"),
        "effects": tuple(snap.get("effects", ()) or ()),
        "overlays": tuple(copy.deepcopy(snap.get("overlays", ()) or ())),
        "taxonomy": snap.get("taxonomy", "hominid"),
        "role": snap.get("role", "actor"),
        "behavior": behavior,
        "state": "watching" if behavior == "pause" else behavior,
    }


def _add_dream_only_figure(rng: random.Random, scene: dict, idx: int, *, stressor: str) -> dict:
    if stressor == "fake_justice":
        template = _DREAM_ONLY_FIGURES[2]
    elif stressor == "animal_pressure":
        template = rng.choice(_DREAM_ONLY_FIGURES[:2])
    else:
        template = rng.choice(_DREAM_ONLY_FIGURES)
    x, y = _spawn_point(rng, scene)
    return {
        "dream_actor_id": f"d{idx:02d}",
        "source_eid": None,
        "x": x,
        "y": y,
        "prev_x": x,
        "prev_y": y,
        "glyph": template["glyph"],
        "color": template["color"],
        "semantic_id": template["semantic_id"],
        "effects": (),
        "overlays": (),
        "taxonomy": template["taxonomy"],
        "role": "dream",
        "behavior": template["behavior"],
        "state": template["behavior"],
    }


def _scene_id(sim, *, profile_kind: str, service: str, started_tick: int, property_id: str) -> str:
    seed = _seed_text(sim, "vision", profile_kind, service, started_tick, property_id)
    value = random.Random(seed).getrandbits(40)
    return f"vision_{value:010x}"


def start_vision_scene(
    sim,
    *,
    profile_kind: str = "dream_rest",
    service: str = "",
    property_id: str | None = None,
    property_name: str = "",
    started_tick: int | None = None,
    target_end_tick: int | None = None,
    player_eid=None,
) -> dict | None:
    """Start a runtime-only vision scene and return the scene state."""
    service_key = _text(service).lower()
    if profile_kind == "dream_rest" and service_key not in {"rest", "shelter"}:
        return None
    started = _current_tick(sim) if started_tick is None else int(started_tick)
    target = started if target_end_tick is None else int(target_end_tick)
    if target - started <= 0:
        return None

    property_id_text = _text(property_id)
    scene_id = _scene_id(
        sim,
        profile_kind=profile_kind,
        service=service_key,
        started_tick=started,
        property_id=property_id_text,
    )
    rng = random.Random(_seed_text(sim, scene_id, "start"))
    recipe = _weighted_choice(rng, _RECIPE_PROFILES)
    tiles = _base_tiles(str(recipe.get("layout", "room")))
    scene = {
        "schema_version": VISION_SCENE_SCHEMA_VERSION,
        "active": True,
        "vision_only": True,
        "consequence_ineligible": True,
        "profile_kind": profile_kind,
        "scene_id": scene_id,
        "service": service_key,
        "property_id": property_id_text,
        "property_name": _text(property_name),
        "started_tick": int(started),
        "target_end_tick": int(target),
        "last_step": 0,
        "step_ticks": VISION_STEP_TICKS,
        "recipe_id": recipe.get("id"),
        "stressor": recipe.get("stressor", "none"),
        "layout": recipe.get("layout", "room"),
        "width": _BOARD_W,
        "height": _BOARD_H,
        "tiles": tiles,
        "actors": [],
        "events": [],
    }

    behavior_pool = tuple(recipe.get("behaviors", ()) or ("wander",))
    snapshots = _candidate_actor_snapshots(sim, player_eid=player_eid, limit=VISION_MAX_ACTORS)
    rng.shuffle(snapshots)
    target_count = rng.randint(VISION_MIN_ACTORS, VISION_MAX_ACTORS)
    actors = []
    for idx, snap in enumerate(snapshots[:target_count], start=1):
        actors.append(_dream_actor_from_snapshot(rng, scene, snap, idx, behavior_pool))
    while len(actors) < max(3, min(target_count, VISION_MIN_ACTORS)):
        actors.append(_add_dream_only_figure(rng, scene, len(actors) + 1, stressor=str(recipe.get("stressor", "none"))))
    if str(recipe.get("stressor", "none")) in {"fake_justice", "animal_pressure"}:
        actors.append(_add_dream_only_figure(rng, scene, len(actors) + 1, stressor=str(recipe.get("stressor", "none"))))
    scene["actors"] = actors[:VISION_MAX_ACTORS]
    scene["focus"] = {
        "x": _BOARD_W // 2,
        "y": _BOARD_H // 2,
    }
    sim.vision_scene = scene
    return scene


def _move_toward(actor: dict, target_x: int, target_y: int) -> tuple[int, int]:
    x = int(actor.get("x", 0))
    y = int(actor.get("y", 0))
    dx = 0 if x == target_x else (1 if target_x > x else -1)
    dy = 0 if y == target_y else (1 if target_y > y else -1)
    if abs(target_x - x) >= abs(target_y - y):
        return x + dx, y
    return x, y + dy


def _move_away(actor: dict, target_x: int, target_y: int) -> tuple[int, int]:
    x = int(actor.get("x", 0))
    y = int(actor.get("y", 0))
    dx = 0 if x == target_x else (-1 if target_x > x else 1)
    dy = 0 if y == target_y else (-1 if target_y > y else 1)
    if abs(target_x - x) >= abs(target_y - y):
        return x + dx, y
    return x, y + dy


def _advance_actor(scene: dict, actor: dict, step: int, rng: random.Random):
    actor["prev_x"] = int(actor.get("x", 0))
    actor["prev_y"] = int(actor.get("y", 0))
    behavior = _text(actor.get("behavior")).lower() or "wander"
    focus = scene.get("focus") if isinstance(scene.get("focus"), dict) else {}
    focus_x = int(focus.get("x", int(scene.get("width", _BOARD_W)) // 2) or 0)
    focus_y = int(focus.get("y", int(scene.get("height", _BOARD_H)) // 2) or 0)
    x = int(actor.get("x", 0))
    y = int(actor.get("y", 0))

    if behavior == "pause" and step % 4:
        return
    if behavior in {"gather", "protect"}:
        nx, ny = _move_toward(actor, focus_x, focus_y)
    elif behavior == "flee":
        nx, ny = _move_away(actor, focus_x, focus_y)
    elif behavior == "chase":
        target = None
        for other in scene.get("actors", ()):
            if other is actor:
                continue
            if _text(other.get("taxonomy")).lower() == "hominid":
                target = other
                break
        if target:
            nx, ny = _move_toward(actor, int(target.get("x", x)), int(target.get("y", y)))
        else:
            nx, ny = x + rng.choice((-1, 0, 1)), y + rng.choice((-1, 0, 1))
    elif behavior == "patrol":
        try:
            actor_index = int(_text(actor.get("dream_actor_id"))[-2:] or 0)
        except (TypeError, ValueError):
            actor_index = 0
        direction = (step + actor_index) % 4
        deltas = ((1, 0), (0, 1), (-1, 0), (0, -1))
        dx, dy = deltas[direction]
        nx, ny = x + dx, y + dy
    else:
        nx, ny = x + rng.choice((-1, 0, 1)), y + rng.choice((-1, 0, 1))

    if not _walkable(scene, nx, ny):
        alternatives = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1), (x, y)]
        rng.shuffle(alternatives)
        for ax, ay in alternatives:
            if _walkable(scene, ax, ay):
                nx, ny = ax, ay
                break
    actor["x"] = int(nx)
    actor["y"] = int(ny)
    actor["state"] = behavior


def advance_vision_scene(sim, *, current_tick: int | None = None) -> dict | None:
    scene = getattr(sim, "vision_scene", None)
    if not isinstance(scene, dict) or not bool(scene.get("active")):
        return None
    tick = _current_tick(sim) if current_tick is None else int(current_tick)
    started = int(scene.get("started_tick", tick) or tick)
    elapsed = max(0, tick - started)
    step_ticks = max(1, int(scene.get("step_ticks", VISION_STEP_TICKS) or VISION_STEP_TICKS))
    target_step = elapsed // step_ticks
    last_step = int(scene.get("last_step", 0) or 0)
    if target_step <= last_step:
        return scene
    for step in range(last_step + 1, target_step + 1):
        rng = random.Random(_seed_text(sim, scene.get("scene_id"), "step", step))
        for actor in tuple(scene.get("actors", ()) or ()):
            if isinstance(actor, dict):
                _advance_actor(scene, actor, step, rng)
        if step % 11 == 0:
            scene.setdefault("events", []).append({
                "vision_only": True,
                "consequence_ineligible": True,
                "vision_scene_id": scene.get("scene_id"),
                "step": int(step),
                "stressor": scene.get("stressor", "none"),
            })
            if len(scene["events"]) > 12:
                scene["events"] = scene["events"][-12:]
    scene["last_step"] = int(target_step)
    return scene


def end_vision_scene(sim, *, reason: str = "") -> dict | None:
    scene = getattr(sim, "vision_scene", None)
    if not isinstance(scene, dict):
        sim.vision_scene = {}
        return None
    scene["active"] = False
    scene["ended_tick"] = _current_tick(sim)
    scene["end_reason"] = _text(reason) or "ended"
    sim.vision_scene = {}
    return scene


def vision_scene_render_state(sim) -> dict | None:
    scene = getattr(sim, "vision_scene", None)
    if not isinstance(scene, dict) or not bool(scene.get("active")):
        return None
    return scene
