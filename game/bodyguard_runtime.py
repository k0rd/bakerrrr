"""Private bodyguard contract runtime.

Bodyguards are protective contractors, not party members.  They hold a
disciplined perimeter around a principal or owned property, warn first when
there is time, and choose their own force response if the warning fails.
"""

from __future__ import annotations

import random

from engine.events import Event
from engine.systems import System
from engine.visibility import has_line_of_sight
from game.appearance_loadout import equip_appearance_item
from game.components import (
    AI,
    Collider,
    CreatureIdentity,
    Inventory,
    NPCSocial,
    NPCWill,
    Occupation,
    PlayerAssets,
    Position,
    Vitality,
    WeaponLoadout,
)
from game.items import ITEM_CATALOG
from game.population import _give_item, _spawn_human
from game.property_runtime import property_covering
from game.purposeful_observation import (
    finish_purposeful_observation,
    is_purposeful_observation,
    observation_watch_position,
    refresh_purposeful_observation,
)
from game.service_runtime import _manhattan
from game.system_support.actor_attention_runtime import mark_actor_urgent
from game.system_support.ai_intent_runtime import _sync_ai_intent


BODYGUARD_JOB = "bodyguard"
BODYGUARD_TIER_PROFILES = {
    "solo": {"label": "solo guard", "count": 1, "cost": 180},
    "pair": {"label": "guard pair", "count": 2, "cost": 320},
    "detail": {"label": "protective detail", "count": 4, "cost": 560},
}

BODYGUARD_SERVICE_ID = "bodyguard_contract"
BODYGUARD_UPDATE_INTERVAL = 3
BODYGUARD_WARNING_RADIUS = 4
BODYGUARD_PROPERTY_WARNING_RADIUS = 3
BODYGUARD_WARNING_COOLDOWN = 34
BODYGUARD_WARNING_PATIENCE = 14
BODYGUARD_URGENCY_TICKS = 36
BODYGUARD_RING_CAPACITY = {
    1: 4,
    2: 6,
    3: 10,
}
BODYGUARD_RING_DISTANCES = {
    1: 2,
    2: 5,
    3: 9,
}
BODYGUARD_FORMATION_BANDS = {
    1: (1, 2, 3),
    2: (4, 5, 6),
    3: (7, 9, 11),
}
BODYGUARD_POST_INTERRUPT_STATES = frozenset({
    "protecting",
    "chasing",
    "seeking_safety",
    "reporting_incident",
    "helping_victim",
    "warning",
    "ejecting_target",
    "leaving_property",
})
BODYGUARD_MAX_WARNING_SUBJECTS = 12
BODYGUARD_MAX_CHANNEL_GUARDS = sum(BODYGUARD_RING_CAPACITY.values())
BODYGUARD_NPC_DEMAND_INTERVAL = 211
_BODYGUARD_REASON_TOKENS = (
    "celebrity",
    "politician",
    "mayor",
    "council",
    "executive",
    "vip",
    "boss",
    "magnate",
)


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _position_xyz(value):
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        try:
            return (int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError):
            return None
    try:
        return (int(value.x), int(value.y), int(value.z))
    except (AttributeError, TypeError, ValueError):
        return None


def _clean_text(value):
    return str(value or "").strip()


def _clean_key(value):
    return _clean_text(value).lower().replace(" ", "_")


def _contractors(sim):
    contractors = getattr(sim, "contractors", None)
    if not isinstance(contractors, dict):
        contractors = {}
        setattr(sim, "contractors", contractors)
    return contractors


def bodyguard_tier_profile(tier):
    return BODYGUARD_TIER_PROFILES.get(_clean_key(tier))


def _terminal_tick(rec):
    if not isinstance(rec, dict):
        return 0
    for key in ("fired_tick", "jailed_tick", "killed_tick", "ended_tick"):
        tick = _safe_int(rec.get(key), 0)
        if tick > 0:
            return tick
    return 0


def bodyguard_contract_active(sim, rec):
    if not isinstance(rec, dict):
        return False
    if _clean_key(rec.get("job")) != BODYGUARD_JOB:
        return False
    if _terminal_tick(rec) > 0:
        return False
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    if bool(rec.get("indefinite", False)):
        return True
    return _safe_int(rec.get("until"), 0) > tick


def active_bodyguard_contracts(
    sim,
    *,
    hired_by_eid=None,
    assignment_kind=None,
    target_property_id=None,
    principal_eid=None,
    team_id=None,
    protection_channel_id=None,
):
    rows = []
    for raw_eid, rec in _contractors(sim).items():
        if not bodyguard_contract_active(sim, rec):
            continue
        try:
            guard_eid = int(raw_eid)
        except (TypeError, ValueError):
            guard_eid = raw_eid
        if hired_by_eid is not None and _int_or_none(rec.get("hired_by_eid")) != _int_or_none(hired_by_eid):
            continue
        if assignment_kind is not None and _clean_key(rec.get("assignment_kind")) != _clean_key(assignment_kind):
            continue
        if target_property_id is not None and _clean_text(rec.get("property_id")) != _clean_text(target_property_id):
            continue
        if principal_eid is not None and _int_or_none(rec.get("principal_eid")) != _int_or_none(principal_eid):
            continue
        if team_id is not None and _clean_text(rec.get("team_id")) != _clean_text(team_id):
            continue
        if protection_channel_id is not None and _clean_text(rec.get("protection_channel_id")) != _clean_text(protection_channel_id):
            continue
        rows.append((guard_eid, rec))
    rows.sort(key=lambda row: (
        str(row[1].get("protection_channel_id", "")),
        _safe_int(row[1].get("protection_ring"), 99),
        _safe_int(row[1].get("protection_slot"), 999),
        _safe_int(row[1].get("hired_tick"), 0),
        str(row[1].get("team_id", "")),
        int(row[0]) if isinstance(row[0], int) else 0,
    ))
    return tuple(rows)


def protection_channel_id_for_assignment(assignment_kind, *, principal_eid=None, property_id=None):
    kind = _clean_key(assignment_kind)
    if kind == "principal":
        principal = _int_or_none(principal_eid)
        if principal is None:
            return ""
        return f"principal:{principal}"
    if kind == "property":
        prop_id = _clean_text(property_id)
        if not prop_id:
            return ""
        return f"property:{prop_id}"
    return ""


def _channel_members(sim, protection_channel_id):
    channel = _clean_text(protection_channel_id)
    if not channel:
        return ()
    return active_bodyguard_contracts(sim, protection_channel_id=channel)


def _ring_slot_from_ordinal(index):
    idx = max(0, int(index))
    cursor = 0
    for ring, capacity in sorted(BODYGUARD_RING_CAPACITY.items()):
        cap = int(capacity)
        if idx < cursor + cap:
            return ring, idx - cursor
        cursor += cap
    return 3, max(0, BODYGUARD_RING_CAPACITY[3] - 1)


def bodyguard_channel_summary(sim, *, assignment_kind, principal_eid=None, property_id=None):
    channel_id = protection_channel_id_for_assignment(
        assignment_kind,
        principal_eid=principal_eid,
        property_id=property_id,
    )
    rows = _channel_members(sim, channel_id)
    rings = {ring: 0 for ring in BODYGUARD_RING_CAPACITY}
    for _guard_eid, rec in rows:
        ring = _safe_int(rec.get("protection_ring"), 0)
        if ring in rings:
            rings[ring] += 1
    active = len(rows)
    return {
        "protection_channel_id": channel_id,
        "active_count": active,
        "available_slots": max(0, BODYGUARD_MAX_CHANNEL_GUARDS - active),
        "max_slots": BODYGUARD_MAX_CHANNEL_GUARDS,
        "rings": rings,
        "ring_capacity": dict(BODYGUARD_RING_CAPACITY),
    }


def _has_item(sim, eid, item_id):
    inventory = sim.ecs.get(Inventory).get(eid)
    if inventory is None:
        return False
    for row in tuple(getattr(inventory, "items", ()) or ()):
        if isinstance(row, dict) and row.get("item_id") == item_id:
            return True
    return False


def _issue_security_earpiece(sim, eid):
    if "security_earpiece" not in ITEM_CATALOG or _has_item(sim, eid, "security_earpiece"):
        return
    inventory = sim.ecs.get(Inventory).get(eid)
    if inventory is None:
        return
    item_def = ITEM_CATALOG.get("security_earpiece", {})
    added, instance_id = inventory.add_item(
        "security_earpiece",
        quantity=1,
        stack_max=int(item_def.get("stack_max", 1) or 1),
        instance_factory=sim.new_item_instance_id,
        owner_eid=eid,
        owner_tag="npc",
        metadata={"ambient_spawn": True, "bodyguard_issue": True},
    )
    if added and instance_id:
        equip_appearance_item(sim, eid, instance_id, preferred_slot="earrings")


def _ensure_channel_comms(sim, protection_channel_id):
    rows = _channel_members(sim, protection_channel_id)
    if len(rows) <= 1:
        return
    for guard_eid, _rec in rows:
        _issue_security_earpiece(sim, guard_eid)


def _rebalance_protection_channel(sim, protection_channel_id):
    channel = _clean_text(protection_channel_id)
    if not channel:
        return
    rows = list(_channel_members(sim, channel))
    rows.sort(key=lambda row: (
        _safe_int(row[1].get("protection_ring"), 99),
        _safe_int(row[1].get("protection_slot"), 999),
        _safe_int(row[1].get("hired_tick"), 0),
        str(row[1].get("team_id", "")),
        int(row[0]) if isinstance(row[0], int) else 0,
    ))
    for ordinal, (_guard_eid, rec) in enumerate(rows[:BODYGUARD_MAX_CHANNEL_GUARDS]):
        ring, slot = _ring_slot_from_ordinal(ordinal)
        rec["protection_ring"] = ring
        rec["protection_slot"] = slot
        rec["protection_channel_index"] = ordinal
    _ensure_channel_comms(sim, channel)


def _entity_name(sim, eid, fallback="someone"):
    if eid is None:
        return fallback
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if identity:
        name = _clean_text(getattr(identity, "personal_name", "") or getattr(identity, "common_name", ""))
        if name:
            return name
    return fallback


def _property_name(prop, fallback="property"):
    if isinstance(prop, dict):
        return _clean_text(prop.get("name") or prop.get("id") or fallback) or fallback
    return fallback


def _is_player_owned_property(sim, actor_eid, prop):
    if not isinstance(prop, dict):
        return False
    prop_id = _clean_text(prop.get("id"))
    if not prop_id:
        return False
    assets = sim.ecs.get(PlayerAssets).get(actor_eid)
    if assets and prop_id in getattr(assets, "owned_property_ids", set()):
        return True
    owner = prop.get("owner_eid")
    return _int_or_none(owner) == _int_or_none(actor_eid)


def _walkable(sim, x, y, z):
    tile = sim.tilemap.tile_at(x, y, z)
    if tile and not bool(getattr(tile, "walkable", True)):
        return False
    for eid in tuple(sim.tilemap.entities_at(x, y, z) or ()):
        vitality = sim.ecs.get(Vitality).get(eid)
        if vitality and getattr(vitality, "downed", False):
            continue
        collider = sim.ecs.get(Collider).get(eid)
        if collider and getattr(collider, "blocks", False):
            return False
    return True


def _spawn_near(sim, x, y, z, *, radius=2):
    try:
        x = int(x)
        y = int(y)
        z = int(z)
    except (TypeError, ValueError):
        x, y, z = 0, 0, 0
    candidates = [(x, y, z)]
    for r in range(1, max(1, int(radius)) + 1):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if abs(dx) + abs(dy) != r:
                    continue
                candidates.append((x + dx, y + dy, z))
    for cx, cy, cz in candidates:
        if _walkable(sim, cx, cy, cz):
            return (cx, cy, cz)
    return (x, y, z)


def _prop_focus(prop):
    if not isinstance(prop, dict):
        return (0, 0, 0)
    return (
        _safe_int(prop.get("x"), 0),
        _safe_int(prop.get("y"), 0),
        _safe_int(prop.get("z"), 0),
    )


def _property_bounds(prop):
    x, y, z = _prop_focus(prop)
    if not isinstance(prop, dict):
        return x, y, x, y, z
    metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata"), dict) else {}
    footprint = metadata.get("footprint") if isinstance(metadata.get("footprint"), dict) else {}
    left = _safe_int(footprint.get("left"), x)
    right = _safe_int(footprint.get("right"), x)
    top = _safe_int(footprint.get("top"), y)
    bottom = _safe_int(footprint.get("bottom"), y)
    cells = metadata.get("footprint_cells")
    if isinstance(cells, (list, tuple)) and cells:
        xs = [_int_or_none(cell.get("x")) for cell in cells if isinstance(cell, dict)]
        ys = [_int_or_none(cell.get("y")) for cell in cells if isinstance(cell, dict)]
        xs = [value for value in xs if value is not None]
        ys = [value for value in ys if value is not None]
        if xs and ys:
            left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
    return left, top, right, bottom, z


def _expanded_property_guard_candidates(sim, prop, *, ring=1):
    left, top, right, bottom, z = _property_bounds(prop)
    margin = {1: 1, 2: 3, 3: 6}.get(max(1, int(ring)), 1)
    candidates = []
    for x in range(left - margin, right + margin + 1):
        for y in (top - margin, bottom + margin):
            candidates.append((x, y, z))
    for y in range(top - margin + 1, bottom + margin):
        for x in (left - margin, right + margin):
            candidates.append((x, y, z))
    return candidates


def _property_guard_points(sim, prop, count=1, *, ring=1, inside=False):
    x, y, z = _prop_focus(prop)
    metadata = prop.get("metadata", {}) if isinstance(prop, dict) and isinstance(prop.get("metadata"), dict) else {}
    points = []
    ring = max(1, min(3, _safe_int(ring, 1)))
    entries = metadata.get("entries")
    if ring == 1 and isinstance(entries, (list, tuple)):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            ex = _int_or_none(entry.get("x"))
            ey = _int_or_none(entry.get("y"))
            ez = _int_or_none(entry.get("z", z))
            if ex is None or ey is None or ez is None:
                continue
            for nx, ny, nz in ((ex, ey - 1, ez), (ex, ey + 1, ez), (ex - 1, ey, ez), (ex + 1, ey, ez), (ex, ey, ez)):
                in_prop = property_covering(sim, nx, ny, nz) is prop
                if bool(inside) != bool(in_prop):
                    continue
                if _walkable(sim, nx, ny, nz):
                    points.append((nx, ny, nz))
                    break
    near_points = ((x, y + 1, z), (x + 1, y, z), (x - 1, y, z), (x, y - 1, z), (x + 1, y + 1, z), (x - 1, y + 1, z))
    for nx, ny, nz in (near_points if ring == 1 else ()):
        in_prop = property_covering(sim, nx, ny, nz) is prop
        if bool(inside) != bool(in_prop):
            continue
        if _walkable(sim, nx, ny, nz):
            points.append((nx, ny, nz))
    if ring == 1 and inside:
        cells = metadata.get("footprint_cells")
        cell_points = []
        if isinstance(cells, (list, tuple)):
            for cell in cells:
                if not isinstance(cell, dict):
                    continue
                cx = _int_or_none(cell.get("x"))
                cy = _int_or_none(cell.get("y"))
                cz = _int_or_none(cell.get("z", z))
                if cx is None or cy is None or cz is None:
                    continue
                if property_covering(sim, cx, cy, cz) is prop and _walkable(sim, cx, cy, cz):
                    cell_points.append((cx, cy, cz))
        cell_points.sort(key=lambda point: (_manhattan(point[0], point[1], x, y), point[1], point[0]))
        points.extend(cell_points)
    for nx, ny, nz in _expanded_property_guard_candidates(sim, prop, ring=ring):
        if ring == 1 and inside:
            continue
        if property_covering(sim, nx, ny, nz) is prop:
            continue
        if _walkable(sim, nx, ny, nz):
            points.append((nx, ny, nz))
    if not points:
        points = [_spawn_near(sim, x, y, z, radius={1: 3, 2: 5, 3: 8}.get(ring, 3))]
    deduped = []
    seen = set()
    for point in points:
        if point in seen:
            continue
        seen.add(point)
        deduped.append(point)
    if not deduped:
        deduped = [(x, y, z)]
    return tuple(deduped[:max(1, int(count))])


def _principal_guard_point(sim, principal_pos, *, ring=1, slot=0):
    ring = max(1, min(3, _safe_int(ring, 1)))
    radius = BODYGUARD_RING_DISTANCES.get(ring, 2)
    offsets = []
    for dx, dy in (
        (-radius, 0),
        (radius, 0),
        (0, radius),
        (0, -radius),
        (-radius, -1),
        (radius, 1),
        (-1, radius),
        (1, -radius),
        (-radius, radius),
        (radius, -radius),
    ):
        offsets.append((dx, dy))
    dx, dy = offsets[_safe_int(slot, 0) % len(offsets)]
    return _spawn_near(
        sim,
        int(principal_pos.x) + dx,
        int(principal_pos.y) + dy,
        int(principal_pos.z),
        radius=max(2, ring + 1),
    )


def _principal_guard_slot_anchor(principal_pos, *, ring=1, slot=0):
    ring = max(1, min(3, _safe_int(ring, 1)))
    radius = BODYGUARD_RING_DISTANCES.get(ring, 2)
    principal_xyz = _position_xyz(principal_pos)
    if principal_xyz is None:
        return None
    offsets = (
        (-radius, 0),
        (radius, 0),
        (0, radius),
        (0, -radius),
        (-radius, -1),
        (radius, 1),
        (-1, radius),
        (1, -radius),
        (-radius, radius),
        (radius, -radius),
    )
    dx, dy = offsets[_safe_int(slot, 0) % len(offsets)]
    return (
        principal_xyz[0] + dx,
        principal_xyz[1] + dy,
        principal_xyz[2],
    )


def _give_bodyguard_kit(sim, eid, *, tier, team_size):
    inventory = sim.ecs.get(Inventory).get(eid)
    if inventory is None:
        return
    for item_id in ("security_jacket", "trail_machete"):
        _give_item(sim, eid, item_id, owner_tag="npc")
    weapon = sim.ecs.get(WeaponLoadout).get(eid)
    if weapon:
        if tier in {"pair", "detail"} and "patrol_carbine" in ITEM_CATALOG:
            weapon.add_weapon("patrol_carbine")
            weapon.equip("patrol_carbine")
        elif "rust_revolver" in ITEM_CATALOG:
            weapon.add_weapon("rust_revolver")
            weapon.equip("rust_revolver")
    if team_size > 1:
        if "security_earpiece" in ITEM_CATALOG:
            _issue_security_earpiece(sim, eid)
        else:
            _give_item(sim, eid, "two_way_radio", owner_tag="npc")


def _spawn_bodyguard(sim, rng, provider_prop, *, tier, team_size, assignment_kind, principal_eid=None, property_id=None):
    px, py, pz = _prop_focus(provider_prop)
    position = _spawn_near(sim, px, py, pz, radius=3)
    guard_eid = _spawn_human(
        sim,
        rng,
        "guard",
        position,
        career="bodyguard",
        workplace=provider_prop.get("id") if isinstance(provider_prop, dict) else None,
        workplace_prop=provider_prop if isinstance(provider_prop, dict) else None,
    )
    inventory = sim.ecs.get(Inventory).get(guard_eid)
    if inventory is not None:
        inventory.capacity = max(int(getattr(inventory, "capacity", 0) or 0), 10)
    _give_bodyguard_kit(sim, guard_eid, tier=tier, team_size=team_size)
    social = sim.ecs.get(NPCSocial).get(guard_eid)
    if social and principal_eid is not None:
        social.add_bond(principal_eid, kind="contract", closeness=0.42, trust=0.56, protectiveness=0.9)
    return guard_eid


def _next_team_id(sim):
    counter = _safe_int(getattr(sim, "next_bodyguard_team_id", 1), 1)
    setattr(sim, "next_bodyguard_team_id", counter + 1)
    return f"bodyguard-{counter}"


def hire_bodyguard_contract(sim, hirer_eid, provider_prop, *, tier, assignment_kind, principal_eid=None, property_id=None):
    tier = _clean_key(tier)
    profile = bodyguard_tier_profile(tier)
    if profile is None:
        return {"ok": False, "reason": "invalid_tier", "service": BODYGUARD_SERVICE_ID}
    assignment_kind = _clean_key(assignment_kind)
    if assignment_kind not in {"principal", "property"}:
        return {"ok": False, "reason": "invalid_assignment", "service": BODYGUARD_SERVICE_ID}
    if assignment_kind == "principal":
        principal_eid = _int_or_none(principal_eid if principal_eid is not None else hirer_eid)
        if principal_eid is None or principal_eid not in sim.ecs.get(Position):
            return {"ok": False, "reason": "invalid_target", "service": BODYGUARD_SERVICE_ID}
        target_name = _entity_name(sim, principal_eid, "you")
        property_id = None
    else:
        prop = sim.properties.get(property_id)
        if not _is_player_owned_property(sim, hirer_eid, prop):
            return {"ok": False, "reason": "invalid_target", "service": BODYGUARD_SERVICE_ID}
        target_name = _property_name(prop)
        principal_eid = None
    protection_channel_id = protection_channel_id_for_assignment(
        assignment_kind,
        principal_eid=principal_eid,
        property_id=property_id,
    )
    if not protection_channel_id:
        return {"ok": False, "reason": "invalid_target", "service": BODYGUARD_SERVICE_ID}

    cost = int(profile.get("cost", 0) or 0)
    assets = sim.ecs.get(PlayerAssets).get(hirer_eid)
    credits = int(getattr(assets, "credits", 0) or 0) if assets else 0
    if assets is None or credits < cost:
        return {
            "ok": False,
            "reason": "no_credits",
            "service": BODYGUARD_SERVICE_ID,
            "cost": cost,
            "credits": credits,
        }
    current_count = len(_channel_members(sim, protection_channel_id))
    count = int(profile.get("count", 1) or 1)
    available_slots = max(0, BODYGUARD_MAX_CHANNEL_GUARDS - current_count)
    if count > available_slots:
        return {
            "ok": False,
            "reason": "assignment_full",
            "service": BODYGUARD_SERVICE_ID,
            "cost": cost,
            "credits": credits,
            "available_slots": available_slots,
            "max_slots": BODYGUARD_MAX_CHANNEL_GUARDS,
            "active_count": current_count,
        }

    assets.credits = max(0, credits - cost)
    team_id = _next_team_id(sim)
    principal_pos = sim.ecs.get(Position).get(principal_eid) if principal_eid is not None else None
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:bodyguard:{team_id}:{tier}:{assignment_kind}:{principal_eid}:{property_id}")
    guard_eids = []
    for index in range(count):
        guard_eid = _spawn_bodyguard(
            sim,
            rng,
            provider_prop,
            tier=tier,
            team_size=count,
            assignment_kind=assignment_kind,
            principal_eid=principal_eid if principal_eid is not None else hirer_eid,
            property_id=property_id,
        )
        rec = {
            "job": BODYGUARD_JOB,
            "assignment_kind": assignment_kind,
            "principal_eid": principal_eid,
            "property_id": property_id,
            "team_id": team_id,
            "protection_channel_id": protection_channel_id,
            "tier": tier,
            "provider_property_id": provider_prop.get("id") if isinstance(provider_prop, dict) else None,
            "provider_property_name": _property_name(provider_prop, "contractor desk"),
            "hired_by_eid": hirer_eid,
            "ally_eid": principal_eid if principal_eid is not None else hirer_eid,
            "indefinite": True,
            "until": 10**12,
            "hired_tick": _safe_int(getattr(sim, "tick", 0), 0),
            "team_size": count,
            "team_index": index,
            "protection_ring": 3,
            "protection_slot": 0,
            "protection_channel_index": current_count + index,
            "cost": cost,
            "warning_state": {},
            "guard_point": None,
            "principal_known_position": (
                (int(principal_pos.x), int(principal_pos.y), int(principal_pos.z))
                if principal_pos is not None
                else None
            ),
        }
        _contractors(sim)[guard_eid] = rec
        mark_actor_urgent(sim, guard_eid, reason="bodyguard_contract", ttl_ticks=BODYGUARD_URGENCY_TICKS)
        guard_eids.append(guard_eid)
    _rebalance_protection_channel(sim, protection_channel_id)
    summary = bodyguard_channel_summary(
        sim,
        assignment_kind=assignment_kind,
        principal_eid=principal_eid,
        property_id=property_id,
    )

    payload = {
        "eid": hirer_eid,
        "service": BODYGUARD_SERVICE_ID,
        "property_id": provider_prop.get("id") if isinstance(provider_prop, dict) else None,
        "property_name": _property_name(provider_prop, "contractor desk"),
        "tier": tier,
        "tier_label": str(profile.get("label", tier)).strip() or tier,
        "assignment_kind": assignment_kind,
        "principal_eid": principal_eid,
        "target_property_id": property_id,
        "target_name": target_name,
        "guard_eids": tuple(guard_eids),
        "guard_count": len(guard_eids),
        "team_id": team_id,
        "protection_channel_id": protection_channel_id,
        "active_guard_count": int(summary.get("active_count", len(guard_eids)) or 0),
        "available_slots": int(summary.get("available_slots", 0) or 0),
        "max_slots": BODYGUARD_MAX_CHANNEL_GUARDS,
        "ring_counts": dict(summary.get("rings", {}) or {}),
        "credits_spent": cost,
        "credits_after": int(getattr(assets, "credits", 0) or 0),
    }
    sim.emit(Event("bodyguard_hired", **payload))
    return {"ok": True, **payload}


def create_bodyguard_detail_for_principal(
    sim,
    principal_eid,
    provider_prop=None,
    *,
    count=2,
    tier="pair",
    hired_by_eid=None,
    source_kind="system",
    source_id="",
):
    """Create non-player protective contractors without charging the principal.

    This is the internal seam used by systems that need disciplined protection
    without exposing player command authority or banking semantics.
    """
    principal = _int_or_none(principal_eid)
    if principal is None or principal not in sim.ecs.get(Position):
        return {"ok": False, "reason": "invalid_principal", "service": BODYGUARD_SERVICE_ID}
    tier = _clean_key(tier) or "pair"
    profile = bodyguard_tier_profile(tier) or BODYGUARD_TIER_PROFILES["pair"]
    count = max(1, int(count or profile.get("count", 1) or 1))
    protection_channel_id = protection_channel_id_for_assignment("principal", principal_eid=principal)
    current_count = len(_channel_members(sim, protection_channel_id))
    available_slots = max(0, BODYGUARD_MAX_CHANNEL_GUARDS - current_count)
    if count > available_slots:
        count = available_slots
    if count <= 0:
        return {
            "ok": False,
            "reason": "assignment_full",
            "service": BODYGUARD_SERVICE_ID,
            "active_count": current_count,
            "max_slots": BODYGUARD_MAX_CHANNEL_GUARDS,
        }
    principal_pos = sim.ecs.get(Position).get(principal)
    if not isinstance(provider_prop, dict):
        provider_prop = {
            "id": f"{_clean_key(source_kind) or 'system'}:{principal}",
            "name": "private detail",
            "x": int(getattr(principal_pos, "x", 0) or 0),
            "y": int(getattr(principal_pos, "y", 0) or 0),
            "z": int(getattr(principal_pos, "z", 0) or 0),
            "metadata": {},
        }
    team_id = _next_team_id(sim)
    rng = random.Random(
        f"{getattr(sim, 'seed', 0)}:bodyguard-internal:{team_id}:{tier}:{principal}:{source_kind}:{source_id}"
    )
    guard_eids = []
    for index in range(count):
        guard_eid = _spawn_bodyguard(
            sim,
            rng,
            provider_prop,
            tier=tier,
            team_size=count,
            assignment_kind="principal",
            principal_eid=principal,
        )
        rec = {
            "job": BODYGUARD_JOB,
            "assignment_kind": "principal",
            "principal_eid": principal,
            "property_id": None,
            "team_id": team_id,
            "protection_channel_id": protection_channel_id,
            "tier": tier,
            "provider_property_id": provider_prop.get("id") if isinstance(provider_prop, dict) else None,
            "provider_property_name": _property_name(provider_prop, "private detail"),
            "hired_by_eid": _int_or_none(hired_by_eid),
            "ally_eid": principal,
            "indefinite": True,
            "until": 10**12,
            "hired_tick": _safe_int(getattr(sim, "tick", 0), 0),
            "team_size": count,
            "team_index": index,
            "protection_ring": 3,
            "protection_slot": 0,
            "protection_channel_index": current_count + index,
            "cost": 0,
            "warning_state": {},
            "guard_point": None,
            "principal_known_position": (
                int(principal_pos.x),
                int(principal_pos.y),
                int(principal_pos.z),
            ),
            "source_kind": _clean_key(source_kind),
            "source_id": _clean_text(source_id),
        }
        _contractors(sim)[guard_eid] = rec
        mark_actor_urgent(sim, guard_eid, reason="bodyguard_contract", ttl_ticks=BODYGUARD_URGENCY_TICKS)
        guard_eids.append(guard_eid)
    _rebalance_protection_channel(sim, protection_channel_id)
    summary = bodyguard_channel_summary(sim, assignment_kind="principal", principal_eid=principal)
    payload = {
        "eid": _int_or_none(hired_by_eid),
        "service": BODYGUARD_SERVICE_ID,
        "property_id": provider_prop.get("id") if isinstance(provider_prop, dict) else None,
        "property_name": _property_name(provider_prop, "private detail"),
        "tier": tier,
        "tier_label": str(profile.get("label", tier)).strip() or tier,
        "assignment_kind": "principal",
        "principal_eid": principal,
        "target_property_id": None,
        "target_name": _entity_name(sim, principal, "the principal"),
        "guard_eids": tuple(guard_eids),
        "guard_count": len(guard_eids),
        "team_id": team_id,
        "protection_channel_id": protection_channel_id,
        "active_guard_count": int(summary.get("active_count", len(guard_eids)) or 0),
        "available_slots": int(summary.get("available_slots", 0) or 0),
        "max_slots": BODYGUARD_MAX_CHANNEL_GUARDS,
        "ring_counts": dict(summary.get("rings", {}) or {}),
        "credits_spent": 0,
        "credits_after": 0,
        "source_kind": _clean_key(source_kind),
        "source_id": _clean_text(source_id),
    }
    sim.emit(Event("bodyguard_hired", **payload))
    return {"ok": True, **payload}


def fire_bodyguard_contract(sim, hirer_eid, *, team_id=None, guard_eid=None, protection_channel_id=None):
    team = _clean_text(team_id)
    channel = _clean_text(protection_channel_id)
    target_guard = _int_or_none(guard_eid)
    ended = []
    affected_channels = set()
    for npc_eid, rec in list(_contractors(sim).items()):
        if _clean_key(rec.get("job")) != BODYGUARD_JOB:
            continue
        if _int_or_none(rec.get("hired_by_eid")) != _int_or_none(hirer_eid):
            continue
        if team and _clean_text(rec.get("team_id")) != team:
            continue
        if channel and _clean_text(rec.get("protection_channel_id")) != channel:
            continue
        if target_guard is not None and _int_or_none(npc_eid) != target_guard:
            continue
        channel_id = _clean_text(rec.get("protection_channel_id"))
        if channel_id:
            affected_channels.add(channel_id)
        rec["fired_tick"] = _safe_int(getattr(sim, "tick", 0), 0)
        rec["ended_reason"] = "fired"
        _contractors(sim).pop(npc_eid, None)
        ai = sim.ecs.get(AI).get(npc_eid)
        will = sim.ecs.get(NPCWill).get(npc_eid)
        pos = sim.ecs.get(Position).get(npc_eid)
        if ai:
            target = (int(pos.x), int(pos.y), int(pos.z)) if pos else None
            _sync_ai_intent(ai, will, getattr(sim, "tick", 0), "idle", score=0.0, target=target, target_eid=None)
        ended.append(npc_eid)
    for channel_id in affected_channels:
        _rebalance_protection_channel(sim, channel_id)
    if ended:
        sim.emit(Event(
            "bodyguard_fired",
            eid=hirer_eid,
            team_id=team,
            protection_channel_id=channel or next(iter(affected_channels), ""),
            guard_eids=tuple(ended),
            guard_count=len(ended),
        ))
    return {
        "ok": bool(ended),
        "reason": "" if ended else "invalid_target",
        "guard_eids": tuple(ended),
        "guard_count": len(ended),
        "protection_channel_id": channel or next(iter(affected_channels), ""),
    }


def _is_living_actor(sim, eid):
    if eid is None:
        return False
    pos = sim.ecs.get(Position).get(eid)
    vit = sim.ecs.get(Vitality).get(eid)
    if pos is None or vit is None:
        return False
    if int(getattr(vit, "hp", 0) or 0) <= 0 or bool(getattr(vit, "downed", False)):
        return False
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    return bool(identity and str(getattr(identity, "taxonomy_class", "") or "").lower() == "hominid")


def _same_eid(a, b):
    ia = _int_or_none(a)
    ib = _int_or_none(b)
    if ia is not None and ib is not None:
        return ia == ib
    return a == b


def _bodyguard_runtime_state(sim):
    state = getattr(sim, "bodyguard_runtime", None)
    if not isinstance(state, dict):
        state = {}
        setattr(sim, "bodyguard_runtime", state)
    state.setdefault("high_profile_seeded", {})
    state.setdefault("npc_demand_cooldowns", {})
    return state


def _property_is_bodyguard_provider(prop):
    if not isinstance(prop, dict):
        return False
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    archetype = _clean_key(metadata.get("archetype") or prop.get("archetype"))
    if archetype in {"contractor_office", "bounty_office"}:
        return True
    services = metadata.get("site_services") or metadata.get("services") or ()
    if isinstance(services, str):
        services = (services,)
    return BODYGUARD_SERVICE_ID in {_clean_key(service) for service in tuple(services or ())}


def _nearest_bodyguard_provider(sim, pos, *, max_distance=42):
    if pos is None:
        return None
    candidates = []
    for prop in tuple(getattr(sim, "properties", {}).values()):
        if not _property_is_bodyguard_provider(prop):
            continue
        px, py, pz = _prop_focus(prop)
        if int(pz) != int(getattr(pos, "z", 0)):
            continue
        distance = _manhattan(int(getattr(pos, "x", 0)), int(getattr(pos, "y", 0)), int(px), int(py))
        if distance <= int(max_distance):
            candidates.append((distance, _clean_text(prop.get("id")), prop))
    return sorted(candidates, key=lambda row: (row[0], row[1]))[0][2] if candidates else None


def _actor_bodyguard_reason(sim, eid):
    ai = sim.ecs.get(AI).get(eid)
    occupation = sim.ecs.get(Occupation).get(eid)
    text = f"{getattr(ai, 'role', '')} {getattr(occupation, 'career', '')}".lower()
    if any(token in text for token in _BODYGUARD_REASON_TOKENS):
        return "high_profile"
    return ""


class BodyguardSystem(System):
    """Owns bodyguard warning, perimeter, and protective force decisions."""

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        self.sim.events.subscribe("npc_killed", self.on_npc_killed)
        self.sim.events.subscribe("actor_detained", self.on_actor_detained)
        self.sim.events.subscribe("bodyguard_hired", self.on_bodyguard_hired)

    def update(self):
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        if tick % BODYGUARD_UPDATE_INTERVAL != 0:
            return
        self._tick_bodyguards()
        if tick % BODYGUARD_NPC_DEMAND_INTERVAL == 0:
            self._tick_npc_bodyguard_demand()

    def _tick_npc_bodyguard_demand(self):
        state = _bodyguard_runtime_state(self.sim)
        seeded = state.setdefault("high_profile_seeded", {})
        cooldowns = state.setdefault("npc_demand_cooldowns", {})
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        for eid, pos in list(self.sim.ecs.get(Position).items()):
            if _same_eid(eid, getattr(self.sim, "player_eid", None)) or not _is_living_actor(self.sim, eid):
                continue
            if active_bodyguard_contracts(self.sim, assignment_kind="principal", principal_eid=eid):
                continue
            reason = _actor_bodyguard_reason(self.sim, eid)
            if not reason:
                continue
            key = str(eid)
            if _safe_int(cooldowns.get(key), 0) > tick:
                continue
            if not seeded.get(key):
                rng = random.Random(f"{getattr(self.sim, 'seed', 0)}:bodyguard-high-profile:{eid}")
                if rng.random() < 0.18:
                    result = create_bodyguard_detail_for_principal(
                        self.sim,
                        eid,
                        None,
                        count=1,
                        tier="solo",
                        hired_by_eid=eid,
                        source_kind="high_profile",
                        source_id=reason,
                    )
                    seeded[key] = {"tick": tick, "reason": reason, "ok": bool(result.get("ok"))}
                    cooldowns[key] = tick + 2400
                    continue
                seeded[key] = {"tick": tick, "reason": reason, "ok": False}
            provider = _nearest_bodyguard_provider(self.sim, pos, max_distance=36)
            if not isinstance(provider, dict):
                cooldowns[key] = tick + 900
                continue
            current_prop = property_covering(self.sim, pos.x, pos.y, pos.z)
            if current_prop is provider:
                assets = self.sim.ecs.get(PlayerAssets).get(eid)
                if assets and int(getattr(assets, "credits", 0) or 0) >= int(BODYGUARD_TIER_PROFILES["solo"]["cost"]):
                    hire_bodyguard_contract(self.sim, eid, provider, tier="solo", assignment_kind="principal", principal_eid=eid)
                cooldowns[key] = tick + 2400
                continue
            ai = self.sim.ecs.get(AI).get(eid)
            will = self.sim.ecs.get(NPCWill).get(eid)
            if ai is not None:
                _sync_ai_intent(ai, will, tick, "bodyguard_procurement", score=34.0, target=_prop_focus(provider), target_eid=None)
                mark_actor_urgent(self.sim, eid, reason="bodyguard_procurement", ttl_ticks=90)
            cooldowns[key] = tick + 360

    def _tick_bodyguards(self):
        for guard_eid, rec in list(active_bodyguard_contracts(self.sim)):
            if not _is_living_actor(self.sim, guard_eid):
                continue
            target = self._assignment_target(rec, guard_eid=guard_eid)
            if not target:
                self._end_contract(guard_eid, rec, "lost_assignment")
                continue
            threat_eid = _int_or_none(rec.get("focus_threat_eid"))
            if threat_eid is not None and self._valid_threat_for_guard(guard_eid, rec, threat_eid):
                self._set_guard_protecting(guard_eid, rec, threat_eid, "active_threat")
                continue
            rec.pop("focus_threat_eid", None)
            rec.pop("focus_threat_reason", None)
            rec.pop("focus_threat_tick", None)
            if self._guard_post_interrupted(guard_eid):
                mark_actor_urgent(self.sim, guard_eid, reason="bodyguard_interrupted", ttl_ticks=BODYGUARD_URGENCY_TICKS)
                continue
            self._assign_guard_post(guard_eid, rec, target)
            self._scan_guard_zone(guard_eid, rec, target)

    def _guard_post_interrupted(self, guard_eid):
        ai = self.sim.ecs.get(AI).get(guard_eid)
        if ai is None:
            return False
        state = _clean_key(getattr(ai, "state", ""))
        if state not in BODYGUARD_POST_INTERRUPT_STATES:
            return False
        if state in {"protecting", "chasing"}:
            target_eid = _int_or_none(getattr(ai, "target_eid", None))
            return target_eid is not None and _is_living_actor(self.sim, target_eid)
        return getattr(ai, "target", None) is not None or getattr(ai, "target_eid", None) is not None

    def _principal_formation_target(self, guard_eid, rec, principal_pos, *, ring, slot):
        guard_pos = self.sim.ecs.get(Position).get(guard_eid)
        if guard_pos is None:
            return None, None
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        context = rec.get("formation_observation")
        context_is_formation = is_purposeful_observation(context, purpose="bodyguard_formation")
        visible = (
            int(guard_pos.z) == int(principal_pos.z)
            and self._guard_can_see(guard_pos, principal_pos)
        )
        band = BODYGUARD_FORMATION_BANDS.get(ring, BODYGUARD_FORMATION_BANDS[1])

        if visible:
            preferred = _principal_guard_slot_anchor(principal_pos, ring=ring, slot=slot)
            watch_position = observation_watch_position(
                self.sim,
                guard_eid,
                principal_pos,
                purpose="bodyguard_formation",
                distance_band=band,
                preferred_position=preferred,
            )
            if watch_position is None:
                watch_position = (int(guard_pos.x), int(guard_pos.y), int(guard_pos.z))
            context = refresh_purposeful_observation(
                self.sim,
                guard_eid,
                rec.get("principal_eid"),
                purpose="bodyguard_formation",
                subject_pos=principal_pos,
                watch_position=watch_position,
                existing=context if context_is_formation and context.get("active") is not False else None,
                include_subject_account=False,
                distance_band=band,
                preferred_position=preferred,
            )
            rec["formation_observation"] = context
            rec["principal_known_position"] = (
                int(principal_pos.x),
                int(principal_pos.y),
                int(principal_pos.z),
            )
            rec["principal_known_tick"] = tick
            return rec["principal_known_position"], tuple(context.get("watch_position"))

        if context_is_formation:
            context = dict(context)
            lost_since = _int_or_none(context.get("lost_contact_since_tick"))
            if lost_since is None:
                lost_since = tick
                context["lost_contact_since_tick"] = tick
            context["updated_tick"] = tick
            grace = max(0, _safe_int(context.get("lost_contact_grace_ticks"), 0))
            if context.get("active") is not False and tick - lost_since > grace:
                context = finish_purposeful_observation(
                    context,
                    current_tick=tick,
                    reason="lost_principal_contact",
                )
            rec["formation_observation"] = context
            known_position = _position_xyz(context.get("last_seen_position"))
            watch_position = _position_xyz(context.get("watch_position"))
            if known_position is not None and watch_position is not None:
                return known_position, watch_position

        known_position = _position_xyz(rec.get("principal_known_position"))
        if known_position is None:
            return None, None
        preferred = _principal_guard_slot_anchor(known_position, ring=ring, slot=slot)
        watch_position = observation_watch_position(
            self.sim,
            guard_eid,
            known_position,
            purpose="bodyguard_formation",
            distance_band=band,
            preferred_position=preferred,
        )
        return known_position, watch_position or (int(guard_pos.x), int(guard_pos.y), int(guard_pos.z))

    def _assignment_target(self, rec, *, guard_eid=None):
        kind = _clean_key(rec.get("assignment_kind"))
        positions = self.sim.ecs.get(Position)
        ring = max(1, min(3, _safe_int(rec.get("protection_ring"), 1)))
        slot = max(0, _safe_int(rec.get("protection_slot"), 0))
        channel_rows = _channel_members(self.sim, rec.get("protection_channel_id"))
        ring_count = sum(1 for _guard_eid, channel_rec in channel_rows if _safe_int(channel_rec.get("protection_ring"), 0) == ring)
        if kind == "principal":
            principal_eid = _int_or_none(rec.get("principal_eid"))
            principal_pos = positions.get(principal_eid)
            if principal_pos is None:
                return None
            if guard_eid is None:
                point = _principal_guard_point(self.sim, principal_pos, ring=ring, slot=slot)
                known_position = (int(principal_pos.x), int(principal_pos.y), int(principal_pos.z))
            else:
                known_position, point = self._principal_formation_target(
                    guard_eid,
                    rec,
                    principal_pos,
                    ring=ring,
                    slot=slot,
                )
                if known_position is None or point is None:
                    return None
            principal_prop = property_covering(
                self.sim,
                known_position[0],
                known_position[1],
                known_position[2],
            )
            if principal_prop is not None:
                points = _property_guard_points(self.sim, principal_prop, count=max(1, ring_count), ring=ring, inside=False)
                point = points[slot % len(points)]
                return {"kind": "principal_inside", "point": point, "principal_pos": known_position, "property": principal_prop, "ring": ring}
            return {"kind": "principal_outside", "point": point, "principal_pos": known_position, "property": None, "ring": ring}
        prop = self.sim.properties.get(rec.get("property_id"))
        if not isinstance(prop, dict):
            return None
        points = _property_guard_points(self.sim, prop, count=max(1, ring_count), ring=ring, inside=(ring == 1))
        point = points[slot % len(points)]
        rec["guard_point"] = point
        return {"kind": "property", "point": tuple(point[:3]), "property": prop, "ring": ring}

    def _assign_guard_post(self, guard_eid, rec, target):
        ai = self.sim.ecs.get(AI).get(guard_eid)
        will = self.sim.ecs.get(NPCWill).get(guard_eid)
        if ai is None:
            return
        point = target.get("point")
        if not isinstance(point, (tuple, list)) or len(point) < 3:
            return
        ring = max(1, min(3, _safe_int(rec.get("protection_ring"), 1)))
        score = {1: 76.0, 2: 66.0, 3: 58.0}.get(ring, 66.0)
        _sync_ai_intent(ai, will, self.sim.tick, "holding", score=score, target=(int(point[0]), int(point[1]), int(point[2])), target_eid=None)
        mark_actor_urgent(self.sim, guard_eid, reason="bodyguard_post", ttl_ticks=BODYGUARD_URGENCY_TICKS)

    def _scan_guard_zone(self, guard_eid, rec, target):
        if _safe_int(rec.get("protection_ring"), 1) != 1:
            return
        guard_pos = self.sim.ecs.get(Position).get(guard_eid)
        if guard_pos is None:
            return
        self._expire_guard_warnings(rec)
        anchor = target.get("principal_pos") if target.get("kind") == "principal_outside" else None
        if anchor is None:
            point = target.get("point") or (guard_pos.x, guard_pos.y, guard_pos.z)
            anchor = _position_xyz(point)
        else:
            anchor = _position_xyz(anchor)
        if anchor is None:
            return
        radius = BODYGUARD_WARNING_RADIUS if target.get("kind") == "principal_outside" else BODYGUARD_PROPERTY_WARNING_RADIUS
        positions = self.sim.ecs.get(Position)
        for other_eid in self.sim.entity_ids_in_radius(anchor[0], anchor[1], anchor[2], radius):
            other_pos = positions.get(other_eid)
            if other_pos is None:
                continue
            if other_eid == guard_eid or not _is_living_actor(self.sim, other_eid):
                continue
            if int(other_pos.z) != int(guard_pos.z):
                continue
            if _manhattan(other_pos.x, other_pos.y, anchor[0], anchor[1]) > radius:
                continue
            if not self._guard_can_see(guard_pos, other_pos):
                continue
            if self._actor_allowed_to_approach(other_eid, rec, target):
                continue
            if self._interior_activity_outside_contract(guard_pos, other_pos, rec, target):
                continue
            danger = self._actor_is_overt_threat(other_eid, rec)
            property_target = target.get("kind") == "property"
            if property_target and not danger and not self._actor_known_hostile_to_property(other_eid, rec, target):
                continue
            self._warn_or_escalate(guard_eid, rec, other_eid, danger=danger, property_target=target.get("kind") != "principal_outside")

    def _expire_guard_warnings(self, rec):
        state = rec.get("warning_state")
        if not isinstance(state, dict) or not state:
            return
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        expired = []
        for key, warning in tuple(state.items()):
            if not isinstance(warning, dict):
                expired.append(key)
                continue
            observation = warning.get("observation")
            if not is_purposeful_observation(observation, purpose="bodyguard_threat_watch"):
                last_tick = _safe_int(warning.get("last_tick"), tick)
                if tick - last_tick > 6:
                    expired.append(key)
                continue
            last_seen_tick = _safe_int(observation.get("last_seen_tick"), tick)
            grace = max(0, _safe_int(observation.get("lost_contact_grace_ticks"), 0))
            if tick - last_seen_tick <= grace:
                continue
            warning["observation"] = finish_purposeful_observation(
                observation,
                current_tick=tick,
                reason="subject_withdrew",
            )
            expired.append(key)
        for key in expired:
            state.pop(key, None)

    def _guard_can_see(self, guard_pos, other_pos):
        try:
            return has_line_of_sight(
                self.sim,
                int(guard_pos.x),
                int(guard_pos.y),
                int(guard_pos.z),
                int(other_pos.x),
                int(other_pos.y),
                int(other_pos.z),
            )
        except Exception:
            return _manhattan(guard_pos.x, guard_pos.y, other_pos.x, other_pos.y) <= 5

    def _interior_activity_outside_contract(self, guard_pos, other_pos, rec, target):
        """Keep exterior bodyguards from policing activity inside protected walls."""
        target_prop = target.get("property")
        if target_prop is None:
            return False
        guard_prop = property_covering(self.sim, guard_pos.x, guard_pos.y, guard_pos.z)
        other_prop = property_covering(self.sim, other_pos.x, other_pos.y, other_pos.z)
        if other_prop is target_prop and guard_prop is not target_prop:
            return True
        return False

    def _actor_allowed_to_approach(self, actor_eid, rec, target):
        principal_eid = _int_or_none(rec.get("principal_eid")) or _int_or_none(rec.get("hired_by_eid"))
        if _same_eid(actor_eid, principal_eid) or _same_eid(actor_eid, rec.get("hired_by_eid")):
            return True
        actor_rec = _contractors(self.sim).get(actor_eid)
        if isinstance(actor_rec, dict) and _clean_key(actor_rec.get("job")) == BODYGUARD_JOB:
            if _clean_text(actor_rec.get("protection_channel_id")) == _clean_text(rec.get("protection_channel_id")):
                return True
        if principal_eid is not None:
            for source, other in ((principal_eid, actor_eid), (actor_eid, principal_eid)):
                social = self.sim.ecs.get(NPCSocial).get(source)
                bond = social.bonds.get(other) if social else None
                if isinstance(bond, dict):
                    closeness = float(bond.get("closeness", 0.0) or 0.0)
                    trust = float(bond.get("trust", 0.0) or 0.0)
                    if closeness >= 0.42 or trust >= 0.48:
                        return True
        prop = target.get("property")
        if isinstance(prop, dict):
            owner = prop.get("owner_eid")
            if owner is not None and _same_eid(actor_eid, owner):
                return True
        return False

    def _actor_is_overt_threat(self, actor_eid, rec):
        ai = self.sim.ecs.get(AI).get(actor_eid)
        if ai and _clean_key(getattr(ai, "state", "")) in {"protecting", "chasing", "attacking", "hostile", "fighting"}:
            target = getattr(ai, "target_eid", None)
            if _same_eid(target, rec.get("principal_eid")) or _same_eid(target, rec.get("hired_by_eid")):
                return True
            for guard_eid, _team_rec in _channel_members(self.sim, rec.get("protection_channel_id")):
                if _same_eid(target, guard_eid):
                    return True
        weapon = self.sim.ecs.get(WeaponLoadout).get(actor_eid)
        if weapon and getattr(weapon, "equipped_weapon_id", None):
            return True
        return False

    def _actor_known_hostile_to_property(self, actor_eid, rec, target):
        prop = target.get("property") if isinstance(target, dict) else None
        owner_eid = prop.get("owner_eid") if isinstance(prop, dict) else None
        if owner_eid is None:
            owner_eid = rec.get("hired_by_eid")
        owner = _int_or_none(owner_eid)
        actor = _int_or_none(actor_eid)
        if owner is None or actor is None:
            return False
        for source, other in ((owner, actor), (actor, owner)):
            social = self.sim.ecs.get(NPCSocial).get(source)
            bond = social.bonds.get(other) if social else None
            if not isinstance(bond, dict):
                continue
            kind = _clean_key(bond.get("kind"))
            trust = float(bond.get("trust", 0.0) or 0.0)
            closeness = float(bond.get("closeness", 0.0) or 0.0)
            if kind in {"hostile", "enemy", "threat", "rival"} or trust < -0.15 or closeness < -0.15:
                return True
        return False

    def _warn_or_escalate(self, guard_eid, rec, subject_eid, *, danger=False, property_target=False):
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        state = rec.setdefault("warning_state", {})
        key = str(subject_eid)
        warning = state.get(key) if isinstance(state.get(key), dict) else {}
        guard_pos = self.sim.ecs.get(Position).get(guard_eid)
        subject_pos = self.sim.ecs.get(Position).get(subject_eid)
        if guard_pos is None or subject_pos is None or not self._guard_can_see(guard_pos, subject_pos):
            return
        existing_observation = warning.get("observation")
        warning["observation"] = refresh_purposeful_observation(
            self.sim,
            guard_eid,
            subject_eid,
            purpose="bodyguard_threat_watch",
            subject_pos=subject_pos,
            watch_position=(int(guard_pos.x), int(guard_pos.y), int(guard_pos.z)),
            existing=existing_observation,
        )
        last_tick = _safe_int(warning.get("last_tick"), -100000)
        has_first_tick = "first_tick" in warning
        warned_tick = _safe_int(warning.get("first_tick"), tick)
        if danger or (has_first_tick and tick - warned_tick >= BODYGUARD_WARNING_PATIENCE):
            self._team_focus_threat(rec, subject_eid, reason="ignored_warning" if not danger else "overt_threat")
            self._emit_threat_response(guard_eid, rec, subject_eid, reason="overt_threat" if danger else "ignored_warning")
            return
        if tick - last_tick < BODYGUARD_WARNING_COOLDOWN:
            state[key] = warning
            return
        warning["first_tick"] = warned_tick if has_first_tick else tick
        warning["last_tick"] = tick
        warning["count"] = _safe_int(warning.get("count"), 0) + 1
        state[key] = warning
        while len(state) > BODYGUARD_MAX_WARNING_SUBJECTS:
            # Keep the subject currently in front of the guard even if an old
            # save or clock rollback left other rows with future timestamps.
            eviction_candidates = [warning_key for warning_key in state if warning_key != key] or list(state)
            oldest = min(
                eviction_candidates,
                key=lambda warning_key: _safe_int(
                    state.get(warning_key, {}).get("last_tick") if isinstance(state.get(warning_key), dict) else -1,
                    -1,
                ),
            )
            state.pop(oldest, None)
        self.sim.emit(Event(
            "bodyguard_warning",
            guard_eid=guard_eid,
            subject_eid=subject_eid,
            team_id=rec.get("team_id"),
            protection_channel_id=rec.get("protection_channel_id"),
            protection_ring=rec.get("protection_ring"),
            assignment_kind=rec.get("assignment_kind"),
            property_target=bool(property_target),
            principal_eid=rec.get("principal_eid"),
            property_id=rec.get("property_id"),
        ))

    def _team_focus_threat(self, rec, threat_eid, *, reason):
        channel_id = rec.get("protection_channel_id")
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        members = _channel_members(self.sim, channel_id) or ()
        for guard_eid, team_rec in members:
            team_rec["focus_threat_eid"] = threat_eid
            team_rec["focus_threat_reason"] = reason
            team_rec["focus_threat_tick"] = tick
            self._set_guard_protecting(guard_eid, team_rec, threat_eid, reason)

    def _set_guard_protecting(self, guard_eid, rec, threat_eid, reason):
        if not self._valid_threat_for_guard(guard_eid, rec, threat_eid):
            return False
        ai = self.sim.ecs.get(AI).get(guard_eid)
        will = self.sim.ecs.get(NPCWill).get(guard_eid)
        threat_pos = self.sim.ecs.get(Position).get(threat_eid)
        if ai is None or threat_pos is None:
            return False
        _sync_ai_intent(
            ai,
            will,
            self.sim.tick,
            "protecting",
            score=96.0,
            target=(int(threat_pos.x), int(threat_pos.y), int(threat_pos.z)),
            target_eid=threat_eid,
        )
        mark_actor_urgent(self.sim, guard_eid, reason=f"bodyguard_{reason}", ttl_ticks=BODYGUARD_URGENCY_TICKS)
        return True

    def _valid_threat_for_guard(self, guard_eid, rec, threat_eid):
        if not _is_living_actor(self.sim, threat_eid) or threat_eid == guard_eid:
            return False
        guard_pos = self.sim.ecs.get(Position).get(guard_eid)
        threat_pos = self.sim.ecs.get(Position).get(threat_eid)
        if guard_pos is None or threat_pos is None or int(guard_pos.z) != int(threat_pos.z):
            return False
        target = self._assignment_target(rec, guard_eid=guard_eid)
        if target and self._interior_activity_outside_contract(guard_pos, threat_pos, rec, target):
            return False
        ring = max(1, min(3, _safe_int(rec.get("protection_ring"), 1)))
        max_distance = {1: 14, 2: 18, 3: 24}.get(ring, 14)
        if _manhattan(guard_pos.x, guard_pos.y, threat_pos.x, threat_pos.y) > max_distance:
            return False
        if (
            ring >= 2
            and _int_or_none(rec.get("focus_threat_eid")) == _int_or_none(threat_eid)
            and _safe_int(getattr(self.sim, "tick", 0), 0) - _safe_int(rec.get("focus_threat_tick"), 0) <= 45
        ):
            return True
        return self._guard_can_see(guard_pos, threat_pos)

    def _emit_threat_response(self, guard_eid, rec, threat_eid, *, reason):
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        last = _safe_int(rec.get("last_threat_response_tick"), -100000)
        if tick - last < 8:
            return
        rec["last_threat_response_tick"] = tick
        self.sim.emit(Event(
            "bodyguard_threat_response",
            guard_eid=guard_eid,
            threat_eid=threat_eid,
            team_id=rec.get("team_id"),
            protection_channel_id=rec.get("protection_channel_id"),
            protection_ring=rec.get("protection_ring"),
            assignment_kind=rec.get("assignment_kind"),
            principal_eid=rec.get("principal_eid"),
            property_id=rec.get("property_id"),
            reason=reason,
        ))

    def _end_contract(self, guard_eid, rec, reason):
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        channel_id = _clean_text(rec.get("protection_channel_id"))
        rec["ended_tick"] = tick
        rec["ended_reason"] = reason
        _contractors(self.sim).pop(guard_eid, None)
        if channel_id:
            _rebalance_protection_channel(self.sim, channel_id)
        self.sim.emit(Event(
            "bodyguard_contract_ended",
            guard_eid=guard_eid,
            team_id=rec.get("team_id"),
            protection_channel_id=channel_id,
            protection_ring=rec.get("protection_ring"),
            reason=reason,
            assignment_kind=rec.get("assignment_kind"),
            principal_eid=rec.get("principal_eid"),
            property_id=rec.get("property_id"),
        ))

    def on_bodyguard_hired(self, event):
        for guard_eid in tuple(event.data.get("guard_eids", ()) or ()):
            rec = _contractors(self.sim).get(guard_eid)
            if isinstance(rec, dict):
                target = self._assignment_target(rec, guard_eid=guard_eid)
                if target:
                    self._assign_guard_post(guard_eid, rec, target)

    def on_entity_damaged(self, event):
        target_eid = event.data.get("target_eid")
        source_eid = event.data.get("source_eid")
        if source_eid is None or target_eid is None:
            return
        for guard_eid, rec in list(active_bodyguard_contracts(self.sim)):
            if _same_eid(target_eid, rec.get("principal_eid")) or _same_eid(target_eid, guard_eid):
                if self._valid_threat_for_guard(guard_eid, rec, source_eid):
                    self._team_focus_threat(rec, source_eid, reason="attack_observed")
                    self._emit_threat_response(guard_eid, rec, source_eid, reason="attack_observed")

    def on_npc_killed(self, event):
        target_eid = event.data.get("target_eid")
        rec = _contractors(self.sim).get(target_eid)
        if isinstance(rec, dict) and _clean_key(rec.get("job")) == BODYGUARD_JOB:
            rec["killed_tick"] = _safe_int(getattr(self.sim, "tick", 0), 0)
            self._end_contract(target_eid, rec, "killed")

    def on_actor_detained(self, event):
        target_eid = event.data.get("eid") or event.data.get("target_eid") or event.data.get("actor_eid")
        rec = _contractors(self.sim).get(target_eid)
        if isinstance(rec, dict) and _clean_key(rec.get("job")) == BODYGUARD_JOB:
            rec["jailed_tick"] = _safe_int(getattr(self.sim, "tick", 0), 0)
            self._end_contract(target_eid, rec, "jailed")


__all__ = [
    "BODYGUARD_JOB",
    "BODYGUARD_MAX_CHANNEL_GUARDS",
    "BODYGUARD_RING_CAPACITY",
    "BODYGUARD_SERVICE_ID",
    "BODYGUARD_TIER_PROFILES",
    "BodyguardSystem",
    "active_bodyguard_contracts",
    "bodyguard_contract_active",
    "bodyguard_channel_summary",
    "bodyguard_tier_profile",
    "create_bodyguard_detail_for_principal",
    "fire_bodyguard_contract",
    "hire_bodyguard_contract",
    "protection_channel_id_for_assignment",
]
