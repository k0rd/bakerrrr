"""Shared combat targeting, projectile, and aim-preview helpers."""

from dataclasses import replace

from engine.events import Event
from engine.tilemap import Tile
from game.components import AI, Collider, NPCTraits, Position, SuppressionState, Vitality, WeaponLoadout
from game.property_access import property_access_level as _property_access_level
from game.property_runtime import property_aperture_at as _property_aperture_at
from game.property_runtime import property_covering as _property_covering
from game.skills import actor_skill as _actor_skill
from game.system_support.actor_runtime import _entity_is_downed
from game.system_support.awareness_runtime import _watchers_for_position
from game.system_support.combat_pacing_runtime import _combat_turn_pacing_active
from game.system_support.entity_naming import _entity_display_name
from game.system_support.intrusion_runtime import _is_window_aperture, _trespass_label_from_score
from game.system_support.item_runtime import _weapon_uses_ammo
from game.weapons import weapon_by_id

THREAT_STATES = {"protecting", "investigating"}

QUIET_NOISE_CAUSES = {
    "move",
    "wait",
    "interact",
    "pickup_item",
    "drop_item",
    "use_item",
    "cover_hop",
    "toggle_door_lock",
    "floor_change",
    "banking",
    "insurance",
    "trade_buy",
    "trade_sell",
    "overworld_travel",
    "zoom_overworld",
    "zoom_city_enter",
}


def _facade():
    from game import systems as facade

    return facade


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or_default(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _grid_distance(ax, ay, bx, by):
    return max(abs(ax - bx), abs(ay - by))


def _clamp(value, lo=0.0, hi=100.0):
    return max(lo, min(hi, value))


def _dir_label(step, short=False):
    mapping = {
        (1, 0): ("east", "E"),
        (-1, 0): ("west", "W"),
        (0, 1): ("south", "S"),
        (0, -1): ("north", "N"),
        (1, 1): ("southeast", "SE"),
        (1, -1): ("northeast", "NE"),
        (-1, 1): ("southwest", "SW"),
        (-1, -1): ("northwest", "NW"),
    }
    label = mapping.get(tuple(step) if step is not None else None)
    if not label:
        return "?" if short else "unknown"
    return label[1] if short else label[0]


def _line_points(ax, ay, bx, by):
    x0 = int(ax)
    y0 = int(ay)
    x1 = int(bx)
    y1 = int(by)

    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = err * 2
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy

    return points


def _entity_is_weapon_targetable(sim, eid, *, current_tick=None):
    if sim is None or eid is None:
        return False

    vitality = sim.ecs.get(Vitality).get(eid)
    suppression = sim.ecs.get(SuppressionState).get(eid)
    if suppression and bool(getattr(suppression, "surrendered", False)):
        if vitality and bool(getattr(vitality, "downed", False)):
            return True
        if not vitality or int(getattr(vitality, "hp", 0) or 0) <= 0:
            return False

        try:
            surrender_tick = int(getattr(suppression, "surrender_tick", -1))
        except (TypeError, ValueError):
            surrender_tick = -1

        if current_tick is None:
            try:
                current_tick = int(getattr(sim, "tick", -1))
            except (TypeError, ValueError):
                current_tick = -1
        else:
            try:
                current_tick = int(current_tick)
            except (TypeError, ValueError):
                current_tick = -1

        if surrender_tick >= 0 and current_tick >= 0 and surrender_tick >= current_tick:
            return False
        return True

    collider = sim.ecs.get(Collider).get(eid)
    if collider and collider.blocks:
        return True

    if vitality and bool(getattr(vitality, "downed", False)):
        return True

    return False


def _first_targetable_entity_at(sim, x, y, z, exclude_eid=None, *, current_tick=None):
    for other_eid in sorted(sim.tilemap.entities_at(x, y, z)):
        if other_eid == exclude_eid:
            continue
        if _entity_is_weapon_targetable(sim, other_eid, current_tick=current_tick):
            return other_eid
    return None


def _projectile_endpoint(sx, sy, tx, ty, max_steps):
    max_steps = int(max(1, max_steps))
    dx = int(tx) - int(sx)
    dy = int(ty) - int(sy)
    distance = max(abs(dx), abs(dy))
    if distance <= 0:
        return None

    scale = float(max_steps) / float(distance)
    ex = int(round(int(sx) + (dx * scale)))
    ey = int(round(int(sy) + (dy * scale)))
    if (ex, ey) == (int(sx), int(sy)):
        ex = int(sx) + (1 if dx > 0 else -1 if dx < 0 else 0)
        ey = int(sy) + (1 if dy > 0 else -1 if dy < 0 else 0)
    return ex, ey


def _projectile_path_points(sx, sy, tx, ty, max_steps, spread=0, rng=None):
    sx = int(sx)
    sy = int(sy)
    tx = int(tx)
    ty = int(ty)
    max_steps = int(max(1, max_steps))

    if spread > 0 and rng is not None:
        tx += int(rng.randint(-spread, spread))
        ty += int(rng.randint(-spread, spread))

    endpoint = _projectile_endpoint(sx, sy, tx, ty, max_steps=max_steps)
    if endpoint is None:
        return []

    ex, ey = endpoint
    return [(int(px), int(py)) for px, py in _line_points(sx, sy, ex, ey)[1 : max_steps + 1]]


def _trace_projectile_path(sim, source_eid, path, z, ignore_walls=False):
    traveled = []
    for px, py in path or ():
        px = int(px)
        py = int(py)
        traveled.append((px, py))

        tile = sim.tilemap.tile_at(px, py, z)
        if tile and not tile.walkable and not ignore_walls:
            return {
                "path": traveled,
                "blocked": True,
                "block_kind": "tile",
                "block_x": px,
                "block_y": py,
                "block_eid": None,
            }

        blocker_eid = _first_targetable_entity_at(
            sim,
            px,
            py,
            z,
            exclude_eid=source_eid,
            current_tick=getattr(sim, "tick", None),
        )
        if blocker_eid is not None:
            return {
                "path": traveled,
                "blocked": True,
                "block_kind": "entity",
                "block_x": px,
                "block_y": py,
                "block_eid": blocker_eid,
            }

    return {
        "path": traveled,
        "blocked": False,
        "block_kind": None,
        "block_x": None,
        "block_y": None,
        "block_eid": None,
    }


def _weapon_target_viability(sim, source_eid, source_pos, weapon, target_x, target_y, target_z, target_eid=None):
    if source_pos is None:
        return {
            "ok": False,
            "reason": "missing_position",
            "path": [],
        }

    try:
        tx = int(target_x)
        ty = int(target_y)
        tz = int(target_z)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "reason": "invalid_target",
            "path": [],
        }

    if int(source_pos.z) != tz:
        return {
            "ok": False,
            "reason": "wrong_floor",
            "path": [],
        }

    max_range = int(max(1, weapon.get("range", 1)))
    path = _projectile_path_points(source_pos.x, source_pos.y, tx, ty, max_steps=max_range)
    if not path:
        return {
            "ok": False,
            "reason": "no_direction",
            "path": [],
        }

    ignore_walls = str(weapon.get("trajectory", "ballistic")).lower() == "lobbed"
    trace = _trace_projectile_path(sim, source_eid, path, tz, ignore_walls=ignore_walls)

    if target_eid is not None:
        for px, py in trace["path"]:
            if trace["blocked"] and (px, py) == (trace["block_x"], trace["block_y"]):
                return {
                    "ok": trace["block_kind"] == "entity" and trace["block_eid"] == target_eid,
                    "reason": None if (trace["block_kind"] == "entity" and trace["block_eid"] == target_eid) else "blocked_line",
                    "path": trace["path"],
                    "block_kind": trace["block_kind"],
                    "block_eid": trace["block_eid"],
                    "block_x": trace["block_x"],
                    "block_y": trace["block_y"],
                }
            if (px, py) == (tx, ty):
                return {
                    "ok": True,
                    "reason": None,
                    "path": trace["path"],
                    "block_kind": trace["block_kind"],
                    "block_eid": trace["block_eid"],
                    "block_x": trace["block_x"],
                    "block_y": trace["block_y"],
                }
        return {
            "ok": False,
            "reason": "off_line",
            "path": trace["path"],
            "block_kind": trace["block_kind"],
            "block_eid": trace["block_eid"],
            "block_x": trace["block_x"],
            "block_y": trace["block_y"],
        }

    if trace["blocked"]:
        return {
            "ok": False,
            "reason": "blocked_line",
            "path": trace["path"],
            "block_kind": trace["block_kind"],
            "block_eid": trace["block_eid"],
            "block_x": trace["block_x"],
            "block_y": trace["block_y"],
        }

    return {
        "ok": True,
        "reason": None,
        "path": trace["path"],
        "block_kind": None,
        "block_eid": None,
        "block_x": None,
        "block_y": None,
    }


def _weapon_context_for_entity(sim, eid):
    loadout = sim.ecs.get(WeaponLoadout).get(eid)
    if not loadout:
        return None, None, {}

    weapon_id = loadout.current_weapon()
    if not weapon_id:
        return loadout, None, {}

    weapon = weapon_by_id(weapon_id)
    instance = loadout.weapon_instances.get(weapon_id, {})
    if not isinstance(instance, dict):
        instance = {}
    return loadout, weapon, instance


def _weapon_tags(weapon):
    if not isinstance(weapon, dict):
        return set()
    return {
        str(tag).strip().lower()
        for tag in weapon.get("tags", ())
        if str(tag).strip()
    }


def _weapon_is_melee(weapon):
    if not isinstance(weapon, dict):
        return True
    if "melee" in _weapon_tags(weapon):
        return True
    try:
        return int(weapon.get("range", 1)) <= 1
    except (TypeError, ValueError):
        return True


def _npc_weapon_preferred_band(weapon, profile=None):
    if not isinstance(weapon, dict) or _weapon_is_melee(weapon):
        return (1, 1, 1)

    try:
        max_range = int(max(1, weapon.get("range", 1)))
    except (TypeError, ValueError):
        max_range = 1
    profile_max = int(max_range)
    if profile is not None:
        try:
            profile_max = int(max(1, getattr(profile, "max_range", max_range)))
        except (TypeError, ValueError):
            profile_max = int(max_range)
    profile_max = max(1, min(max_range, profile_max))

    tags = _weapon_tags(weapon)
    if "shotgun" in tags:
        ideal_min = 2
        ideal_max = min(profile_max, 4)
    elif "smg" in tags or "burst" in tags:
        ideal_min = 2
        ideal_max = min(profile_max, 6)
    elif "precision" in tags or "rifle" in tags:
        ideal_min = min(profile_max, max(3, int(round(max_range * 0.45))))
        ideal_max = profile_max
    else:
        ideal_min = max(2, int(round(max_range * 0.3)))
        ideal_max = min(profile_max, max(ideal_min, int(round(max_range * 0.75))))

    ideal_min = max(1, min(int(ideal_min), profile_max))
    ideal_max = max(ideal_min, min(int(ideal_max), profile_max))
    return ideal_min, ideal_max, max_range


def _npc_combat_metrics(
    *,
    needs=None,
    traits=None,
    vitality=None,
    suppression=None,
    weapon=None,
    pressure_mult=1.0,
    retreat_bias_delta=0.0,
    assault_bias_delta=0.0,
):
    traits = traits or NPCTraits()
    hp_ratio = 1.0
    if vitality:
        hp_ratio = max(0.0, min(1.0, float(vitality.hp) / float(max(1, vitality.max_hp))))

    pressure = 0.0
    if suppression:
        try:
            pressure = float(suppression.pressure)
        except (TypeError, ValueError):
            pressure = 0.0
    pressure = max(0.0, min(1.0, pressure * _float_or_default(pressure_mult, 1.0)))

    safety = 75.0
    if needs:
        try:
            safety = float(needs.safety)
        except (TypeError, ValueError):
            safety = 75.0
    safety = max(0.0, min(100.0, safety))

    has_ranged = bool(isinstance(weapon, dict) and not _weapon_is_melee(weapon))
    low_health = max(0.0, 0.6 - hp_ratio)
    low_safety = max(0.0, (48.0 - safety) / 48.0)

    retreat_bias = _clamp(
        (pressure * 0.72)
        + (low_health * 1.05)
        + (low_safety * 0.45)
        + (0.16 if not has_ranged else 0.0)
        - (float(traits.bravery) * 0.52)
        - (float(traits.discipline) * 0.18),
        lo=0.0,
        hi=1.0,
    )
    retreat_bias = _clamp(retreat_bias + _float_or_default(retreat_bias_delta, 0.0), lo=0.0, hi=1.0)
    assault_bias = _clamp(
        0.28
        + (float(traits.bravery) * 0.58)
        + (0.18 if has_ranged else 0.0)
        - (pressure * 0.45)
        - (low_health * 0.65)
        - (0.14 if not has_ranged else 0.0),
        lo=0.0,
        hi=1.0,
    )
    assault_bias = _clamp(assault_bias + _float_or_default(assault_bias_delta, 0.0), lo=0.0, hi=1.0)

    return {
        "hp_ratio": hp_ratio,
        "pressure": pressure,
        "safety": safety,
        "has_ranged": has_ranged,
        "retreat_bias": retreat_bias,
        "assault_bias": assault_bias,
    }


def _entity_uses_melee_aim(sim, eid):
    loadout = sim.ecs.get(WeaponLoadout).get(eid)
    if not loadout:
        return True
    weapon_id = loadout.current_weapon()
    if not weapon_id:
        return True
    weapon = weapon_by_id(weapon_id)
    tags = {str(tag).strip().lower() for tag in weapon.get("tags", ()) if str(tag).strip()}
    return "melee" in tags


def _aim_open_label(sim, eid):
    return "F aim/strike" if _entity_uses_melee_aim(sim, eid) else "F aim"


def _aim_confirm_label(sim, eid):
    return "Enter strike" if _entity_uses_melee_aim(sim, eid) else "Enter fire"


def _appearance_with_effect(appearance, effect):
    if appearance is None:
        return None
    effect = str(effect or "").strip().lower()
    if not effect:
        return appearance
    effects = tuple(getattr(appearance, "effects", ()) or ())
    if effect in effects:
        return appearance
    return replace(appearance, effects=tuple(dict.fromkeys(effects + (effect,))))


def _entity_should_blink_in_combat(sim, eid, *, player_eid=None):
    if eid is None or (player_eid is not None and int(eid) == int(player_eid)):
        return False
    if not _combat_turn_pacing_active(sim):
        return False
    ai = sim.ecs.get(AI).get(eid)
    if not ai or str(ai.state or "").strip().lower() not in THREAT_STATES:
        return False
    if _entity_is_downed(sim, eid):
        return False
    player_pos = sim.ecs.get(Position).get(player_eid) if player_eid is not None else None
    pos = sim.ecs.get(Position).get(eid)
    if player_pos and pos and int(pos.z) != int(player_pos.z):
        return False
    return True


def _manual_fire_preview(sim, eid, x, y, z):
    positions = sim.ecs.get(Position)
    pos = positions.get(eid)
    loadout, weapon, _instance = _weapon_context_for_entity(sim, eid)
    if not pos or not loadout or not weapon:
        return {
            "ok": False,
            "reason": "no_weapon",
            "summary": "aim:no weapon",
            "path": [],
        }

    x = int(x)
    y = int(y)
    z = int(z)
    if z != int(pos.z):
        return {
            "ok": False,
            "reason": "wrong_floor",
            "summary": f"aim:wrong floor z{z}",
            "path": [],
        }

    max_range = int(max(1, weapon.get("range", 1)))
    dist = _grid_distance(pos.x, pos.y, x, y)
    if dist <= 0:
        return {
            "ok": False,
            "reason": "no_direction",
            "summary": "aim:pick a tile",
            "path": [],
            "max_range": max_range,
        }

    path = _projectile_path_points(pos.x, pos.y, x, y, max_steps=max_range)
    if not path:
        return {
            "ok": False,
            "reason": "no_direction",
            "summary": "aim:no direction",
            "path": [],
            "max_range": max_range,
        }

    first_x, first_y = path[0]
    step = (int(first_x) - int(pos.x), int(first_y) - int(pos.y))
    direction = _dir_label(step, short=True)
    ignore_walls = str(weapon.get("trajectory", "ballistic")).lower() == "lobbed"

    trace = _trace_projectile_path(sim, eid, path, z, ignore_walls=ignore_walls)
    impact_label = "clear"
    impact_eid = None
    if trace["blocked"]:
        if trace["block_kind"] == "tile":
            impact_label = f"blocked@{trace['block_x']},{trace['block_y']}"
        elif trace["block_kind"] == "entity" and trace["block_eid"] is not None:
            impact_eid = trace["block_eid"]
            blocker_name = _entity_display_name(sim, impact_eid, title_case=False)
            impact_label = f"hit:{blocker_name}#{impact_eid}"

    target_eid = _first_targetable_entity_at(sim, x, y, z, exclude_eid=eid)
    target_label = ""
    if target_eid is not None:
        target_label = f"{_entity_display_name(sim, target_eid, title_case=False)}#{target_eid}"

    in_range = dist <= max_range
    range_text = f"{dist}/{max_range}"
    summary_bits = [f"aim {direction}", range_text]
    if not in_range:
        summary_bits.append("out")
    if impact_label and impact_label != "clear":
        summary_bits.append(impact_label)
    elif target_label:
        summary_bits.append(target_label)
    elif impact_label:
        summary_bits.append(impact_label)

    return {
        "ok": in_range,
        "reason": None if in_range else "out_of_range",
        "summary": " ".join(summary_bits),
        "path": trace["path"],
        "target_x": x,
        "target_y": y,
        "target_z": z,
        "target_eid": target_eid,
        "target_label": target_label,
        "impact_eid": impact_eid,
        "impact_label": impact_label,
        "max_range": max_range,
        "distance": dist,
        "direction_step": step,
        "direction_short": direction,
        "trajectory": str(weapon.get("trajectory", "ballistic")).lower(),
        "projectile_glyph": str(weapon.get("projectile_glyph", "."))[:1] or ".",
    }


def _target_condition_descriptor(sim, observer_eid, target_eid, *, include_uncertainty=False):
    if sim is None or target_eid is None:
        return ""
    vitality = sim.ecs.get(Vitality).get(target_eid)
    if not vitality:
        return ""
    if vitality.downed or int(vitality.hp) <= 0:
        return "downed"
    suppression = sim.ecs.get(SuppressionState).get(target_eid)
    if suppression and bool(getattr(suppression, "surrendered", False)):
        return "surrendered"

    max_hp = max(1, int(vitality.max_hp))
    hp = int(max(0, min(max_hp, int(vitality.hp))))
    ratio = float(hp) / float(max_hp)
    perception = float(_actor_skill(sim, observer_eid, "perception")) if observer_eid is not None else 5.0

    if perception >= 8.0:
        bands = (
            (0.10, "about to drop"),
            (0.25, "bleeding out"),
            (0.45, "hurt bad"),
            (0.70, "rattled"),
            (0.90, "holding steady"),
            (1.01, "untouched"),
        )
    elif perception >= 5.0:
        bands = (
            (0.20, "on borrowed time"),
            (0.50, "banged up"),
            (0.80, "still standing"),
            (1.01, "steady"),
        )
    else:
        bands = (
            (0.33, "in trouble"),
            (0.75, "worn down"),
            (1.01, "steady"),
        )

    label = "steady"
    for threshold, text in bands:
        if ratio <= float(threshold):
            label = str(text)
            break

    if include_uncertainty and perception < 4.0 and label not in {"downed", "about to drop"}:
        return f"{label} (hard to read)"
    return label


def _weapon_ammo_type_label(weapon):
    if not _weapon_uses_ammo(weapon):
        return "melee"
    tags = {str(tag).strip().lower() for tag in weapon.get("tags", ()) if str(tag).strip()}
    if "launcher" in tags or "explosive" in tags:
        return "rockets"
    if "shotgun" in tags:
        return "shells"
    if "rifle" in tags or "carbine" in tags or "precision" in tags:
        return "rifle"
    if "handgun" in tags or "smg" in tags or "burst" in tags:
        return "light"
    return "ammo"


def _weapon_reserve_ammo(loadout, weapon_id):
    if not loadout or not weapon_id:
        return None
    if weapon_id not in loadout.reserve_ammo:
        return None
    try:
        return int(loadout.reserve_ammo.get(weapon_id, 0))
    except (TypeError, ValueError):
        return None


def _shatter_window_for_projectile(sim, offender_eid, x, y, z):
    prop = _property_covering(sim, x, y, z)
    aperture = _property_aperture_at(prop, x, y, z) if isinstance(prop, dict) else None
    if not isinstance(aperture, dict) or not _is_window_aperture(aperture.get("kind", "")):
        return False

    sim.tilemap.set_tile(
        int(x),
        int(y),
        Tile(walkable=True, transparent=True, glyph="/"),
        z=int(z),
    )

    if offender_eid is None:
        return True

    offender_pos = sim.ecs.get(Position).get(offender_eid)
    witnesses = []
    for observer_eid in _watchers_for_position(
        sim,
        int(x),
        int(y),
        int(z),
        exclude_eid=offender_eid,
        offender_eid=offender_eid,
    ):
        if not offender_pos:
            continue
        if _facade()._observer_can_notice_position(
            sim,
            observer_eid,
            offender_pos.x,
            offender_pos.y,
            offender_pos.z,
        ):
            witnesses.append(observer_eid)
    access_level = _property_access_level(prop)
    severity_score = 28 + (6 if access_level == "restricted" else 0)
    sim.emit(Event(
        "property_tamper",
        offender_eid=offender_eid,
        property_id=prop.get("id"),
        owner_eid=prop.get("owner_eid"),
        x=int(x),
        y=int(y),
        z=int(z),
        witnessed=bool(witnesses),
        witness_count=len(witnesses),
        witnesses=tuple(witnesses[:6]),
        access_level=access_level,
        severity_score=min(100, severity_score),
        severity_label=_trespass_label_from_score(severity_score),
        standing_reason="none",
        ingress_kind="alternate_aperture",
        aperture_kind=str(aperture.get("kind", "window") or "window").strip().lower() or "window",
        ingress_method="window_shot",
        breach_severity=0.82,
        defender_witnesses_only=True,
        require_witnessed_identity=True,
    ))
    return True
