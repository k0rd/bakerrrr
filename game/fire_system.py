"""Spatial fire runtime and loaded-area fire advancement."""

from __future__ import annotations

import random

from engine.events import Event
from engine.systems import System
from engine.tilemap import Tile
from game.components import Collider, NPCNeeds, Render, StatusEffects, Vitality
from game.property_runtime import property_metadata
from game.system_support.actor_runtime import _apply_downed_actor_state
from game.system_support.building_repair_runtime import record_building_damage
from game.system_support.business_event_state import _business_event_seed_state
from game.system_support.environment_hazard_runtime import environment_hazard_player_note, environment_hazard_profile
from game.system_support.fire_runtime import (
    CAMPFIRE_FIXTURE_TYPES,
    ELECTRICAL_FIXTURE_TYPES,
    FUEL_FIXTURE_TYPES,
    RISKY_ARCHETYPES,
    RISKY_ROOM_KINDS,
    active_fire_cells_near,
    chunk_environmental_ignition_day,
    chunk_fire_summary,
    clear_frozen_fire_boundary,
    fire_behavior_for_cell,
    fire_cell_state,
    fire_protected_chunks,
    fire_runtime_day,
    fire_state,
    mark_chunk_environmental_ignition,
    note_frozen_fire_boundary,
    property_fire_summary,
    remove_fire_cell,
    upsert_fire_cell,
)


FIRE_SPREAD_INTERVAL = 5
FIRE_DAMAGE_INTERVAL = 4
SMOKE_DAMAGE_INTERVAL = 6
ENVIRONMENTAL_REVIEW_INTERVAL = 90
ENVIRONMENTAL_CHUNK_IGNITION_CHANCE = 0.05
FIRE_RESPONSE_KEEP_TICKS = 1200
FIRE_AFTERMATH_HOURS = 6.0


def _text(value):
    return str(value or "").strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value, lo=0.0, hi=100.0):
    return max(float(lo), min(float(hi), float(value)))


def _coord_key(x, y, z=0):
    try:
        return (int(x), int(y), int(z))
    except (TypeError, ValueError):
        return None


def _structure_tile_looks_like_wall(sim, x, y, z):
    tile = sim.tilemap.tile_at(int(x), int(y), int(z))
    if tile is None:
        return False
    semantic = _text(getattr(tile, "semantic_id", "")).lower()
    glyph = _text(getattr(tile, "glyph", ""))
    return semantic == "wall_building" or glyph == "#"


def _loaded_chunk_keys(sim):
    loaded = getattr(getattr(sim, "world", None), "loaded_chunks", {})
    if not isinstance(loaded, dict):
        return ()
    keys = []
    for raw in loaded.keys():
        if isinstance(raw, tuple) and len(raw) >= 2:
            try:
                keys.append((int(raw[0]), int(raw[1])))
            except (TypeError, ValueError):
                continue
    return tuple(sorted(set(keys)))


def _chunk_loaded(sim, chunk):
    chunk = tuple(chunk) if isinstance(chunk, (tuple, list)) else None
    return chunk in set(_loaded_chunk_keys(sim))


def _neighbor_coords(x, y, z):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        yield (int(x) + dx, int(y) + dy, int(z))


def _world_ticks_per_hour(sim):
    clock = getattr(sim, "world_traits", {}).get("clock", {})
    try:
        return max(60, int(clock.get("ticks_per_hour", 600) or 600))
    except (TypeError, ValueError):
        return 600


def _record_fire_aftermath(sim, prop, *, severity=0.5):
    if not isinstance(prop, dict):
        return None
    property_id = _text(prop.get("id"))
    if not property_id:
        return None
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    ticks_per_hour = _world_ticks_per_hour(sim)
    state = getattr(sim, "business_event_aftermath_state", None)
    if not isinstance(state, dict):
        state = {"properties": {}}
        sim.business_event_aftermath_state = state
    properties = state.get("properties")
    if not isinstance(properties, dict):
        properties = {}
        state["properties"] = properties
    entry = dict(properties.get(property_id, {}) or {})
    created_tick = _safe_int(entry.get("created_tick"), tick)
    entry.update({
        "property_id": property_id,
        "building_id": _text(property_metadata(prop).get("building_id")),
        "incident_kind": "hazard",
        "damage_kind": "fire",
        "severity": max(_safe_float(entry.get("severity"), 0.0), _safe_float(severity, 0.5)),
        "casualty_count": max(0, _safe_int(entry.get("casualty_count"), 0)),
        "serious_count": max(1, _safe_int(entry.get("serious_count"), 0)),
        "created_tick": min(created_tick, tick),
        "last_tick": tick,
        "expires_tick": max(
            tick + int(ticks_per_hour * FIRE_AFTERMATH_HOURS),
            _safe_int(entry.get("expires_tick"), 0),
        ),
    })
    properties[property_id] = entry
    return entry


def _seed_archetype_category(prop):
    archetype = _text(property_metadata(prop).get("archetype")).lower()
    if archetype in {"clinic", "hospital", "biotech_clinic"}:
        return "medical"
    if archetype in {"apartment", "housing", "tower", "tenement"}:
        return "residential"
    if archetype in {"service_station", "checkpoint", "courthouse", "police_precinct", "military_post"}:
        return "secure"
    if archetype in {"warehouse", "factory", "workshop"}:
        return "industrial"
    if archetype in {"bar", "nightclub", "restaurant", "cafe"}:
        return "hospitality"
    if archetype in {"station", "metro_exchange", "bus_depot"}:
        return "transit"
    return "retail"


class FireSystem(System):

    def __init__(self, sim):
        super().__init__(sim)
        self.runs_without_turn = True
        self.sim.events.subscribe("explosion_triggered", self.on_explosion_triggered)

    def on_explosion_triggered(self, event):
        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z", 0)
        radius = max(0, _safe_int(event.data.get("radius"), 0))
        if x is None or y is None:
            return
        source_eid = event.data.get("source_eid")
        origin = _coord_key(x, y, z)
        if origin is None:
            return

        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if abs(dx) + abs(dy) > max(1, radius):
                    continue
                tx = int(origin[0]) + dx
                ty = int(origin[1]) + dy
                tz = int(origin[2])
                behavior = fire_behavior_for_cell(self.sim, tx, ty, tz)
                if not bool(behavior.get("can_ignite")):
                    continue
                distance = abs(dx) + abs(dy)
                chance = max(0.18, 0.9 - (distance * 0.22))
                roll = random.Random(
                    f"{getattr(self.sim, 'seed', 0)}:fire-explosion:{getattr(self.sim, 'tick', 0)}:{tx}:{ty}:{tz}:{source_eid}"
                ).random()
                if roll > chance:
                    continue
                is_spread = distance > 0
                self._ignite_cell(
                    tx,
                    ty,
                    tz,
                    source_kind="explosion",
                    source_eid=source_eid,
                    spread_from=origin if is_spread else None,
                    intensity=max(2, 4 - distance),
                )

    def _ignite_cell(
        self,
        x,
        y,
        z=0,
        *,
        source_kind="",
        source_eid=None,
        source_property_id=None,
        spread_from=None,
        intensity=2,
    ):
        behavior = fire_behavior_for_cell(self.sim, x, y, z)
        if not bool(behavior.get("can_ignite")):
            return None
        now = _safe_int(getattr(self.sim, "tick", 0), 0)
        intensity = max(1, _safe_int(intensity, 1))
        smoke_intensity = max(1, intensity - 1)
        record = upsert_fire_cell(
            self.sim,
            x,
            y,
            z,
            fire_intensity=intensity,
            smoke_intensity=smoke_intensity,
            source_kind=source_kind,
            source_eid=source_eid,
            source_property_id=source_property_id,
            property_id=behavior.get("property_id"),
            building_id=behavior.get("building_id"),
            burn_tier=behavior.get("burn_tier"),
            burn_budget=max(
                _safe_int(behavior.get("burn_budget"), 0),
                intensity + 1,
            ),
            started_tick=now,
            last_advanced_tick=now,
        )
        if not isinstance(record, dict):
            return None

        event_type = "fire_spread" if spread_from is not None else "fire_started"
        self.sim.emit(
            Event(
                event_type,
                x=int(x),
                y=int(y),
                z=int(z),
                property_id=record.get("property_id"),
                property_name=behavior.get("property_name"),
                building_id=record.get("building_id"),
                source_kind=_text(source_kind).lower(),
                source_eid=source_eid,
                source_property_id=record.get("source_property_id"),
                fire_intensity=_safe_int(record.get("fire_intensity"), intensity),
                smoke_intensity=_safe_int(record.get("smoke_intensity"), smoke_intensity),
                severity=min(100, 18 + (_safe_int(record.get("fire_intensity"), intensity) * 18)),
                public_frontage=bool(behavior.get("property_public")),
                spread_from=spread_from,
                tags=tuple(behavior.get("source_tags", ())),
            )
        )
        return record

    def _loaded_cells(self):
        cells = fire_state(self.sim).get("cells", {})
        for coord, cell in tuple(sorted(cells.items())):
            chunk = self.sim.chunk_coords(coord[0], coord[1])
            if not _chunk_loaded(self.sim, chunk):
                continue
            yield coord, cell

    def _review_environmental_ignitions(self):
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        if tick % ENVIRONMENTAL_REVIEW_INTERVAL != 0:
            return
        day = fire_runtime_day(self.sim)
        for chunk in _loaded_chunk_keys(self.sim):
            if chunk_fire_summary(self.sim, chunk).get("active"):
                continue
            if chunk_environmental_ignition_day(self.sim, chunk) == day:
                continue
            candidates = self._environmental_candidates_for_chunk(chunk)
            if not candidates:
                continue
            roll = random.Random(f"{getattr(self.sim, 'seed', 0)}:fire-env:{day}:{chunk[0]}:{chunk[1]}").random()
            if roll > ENVIRONMENTAL_CHUNK_IGNITION_CHANCE:
                continue
            choice = sorted(candidates)[0]
            started = self._ignite_cell(
                choice[0],
                choice[1],
                choice[2],
                source_kind="environmental_fault",
                source_property_id=choice[3],
                intensity=choice[4],
            )
            if started is not None:
                mark_chunk_environmental_ignition(self.sim, chunk, day=day)

    def _environmental_candidates_for_chunk(self, chunk):
        candidates = []
        cx, cy = int(chunk[0]), int(chunk[1])
        for prop in tuple(getattr(self.sim, "properties", {}).values()):
            if not isinstance(prop, dict):
                continue
            try:
                px = int(prop.get("x", 0))
                py = int(prop.get("y", 0))
                pz = int(prop.get("z", 0))
            except (TypeError, ValueError):
                continue
            if self.sim.chunk_coords(px, py) != (cx, cy):
                continue
            metadata = property_metadata(prop)
            fixture_type = _text(metadata.get("fixture_type", metadata.get("archetype"))).lower()
            hazard_profile = _text(metadata.get("hazard_profile")).lower()
            property_id = _text(prop.get("id"))
            if fixture_type in ELECTRICAL_FIXTURE_TYPES or hazard_profile == "live_wire":
                candidates.append((px, py, pz, property_id, 4))
                continue
            if fixture_type in CAMPFIRE_FIXTURE_TYPES:
                candidates.append((px, py, pz, property_id, 3))
                continue
            if fixture_type in FUEL_FIXTURE_TYPES:
                candidates.append((px, py, pz, property_id, 4))
                continue
            archetype = _text(metadata.get("archetype")).lower()
            if archetype in RISKY_ARCHETYPES:
                candidates.append((px, py, pz, property_id, 3))

        for coord, structure in tuple(getattr(self.sim, "structure_cells", {}).items()):
            if not isinstance(coord, tuple) or len(coord) < 3 or not isinstance(structure, dict):
                continue
            if self.sim.chunk_coords(coord[0], coord[1]) != (cx, cy):
                continue
            room_kind = _text(structure.get("room_kind")).lower()
            if room_kind not in RISKY_ROOM_KINDS:
                continue
            behavior = fire_behavior_for_cell(self.sim, coord[0], coord[1], coord[2])
            if not bool(behavior.get("can_ignite")):
                continue
            candidates.append((int(coord[0]), int(coord[1]), int(coord[2]), behavior.get("property_id"), 3))
        deduped = {}
        for row in candidates:
            coord = (int(row[0]), int(row[1]), int(row[2]))
            if coord not in deduped or int(row[4]) > int(deduped[coord][4]):
                deduped[coord] = row
        return tuple(deduped.values())

    def _apply_damage_to_entity(self, eid, pos, *, profile_id, property_id=None, property_name=""):
        profile = environment_hazard_profile(profile_id)
        if not profile:
            return False

        status_map = self.sim.ecs.get(StatusEffects)
        vitality_map = self.sim.ecs.get(Vitality)
        needs_map = self.sim.ecs.get(NPCNeeds)
        collider_map = self.sim.ecs.get(Collider)
        render_map = self.sim.ecs.get(Render)

        effects = status_map.get(eid) if status_map else None
        vitality = vitality_map.get(eid) if vitality_map else None
        needs = needs_map.get(eid) if needs_map else None
        if vitality is None or bool(getattr(vitality, "downed", False)):
            return False

        if effects is not None:
            effects.add(
                status=_text(profile.get("status")).lower(),
                duration=max(1, _safe_int(profile.get("duration"), 1)),
                modifiers=dict(profile.get("modifiers", {}) or {}),
                source_item=f"fire:{profile_id}",
            )

        immediate_needs = dict(profile.get("immediate_needs", {}) or {})
        if needs is not None:
            if "energy" in immediate_needs:
                needs.energy = _clamp(needs.energy + _safe_float(immediate_needs.get("energy"), 0.0))
            if "safety" in immediate_needs:
                needs.safety = _clamp(needs.safety + _safe_float(immediate_needs.get("safety"), 0.0))
            if "social" in immediate_needs:
                needs.social = _clamp(needs.social + _safe_float(immediate_needs.get("social"), 0.0))

        damage = max(0, _safe_int(profile.get("damage"), 0))
        old_hp = _safe_int(getattr(vitality, "hp", 0), 0)
        new_hp = max(0, old_hp - damage)
        actual_damage = max(0, old_hp - new_hp)
        vitality.hp = int(new_hp)

        self.sim.emit(
            Event(
                "environmental_hazard_triggered",
                eid=eid,
                target_eid=eid,
                property_id=property_id,
                property_name=property_name or _text(profile.get("name")) or "Hazard",
                hazard_profile=profile_id,
                hazard_name=_text(profile.get("name")) or "Hazard",
                hazard_note=environment_hazard_player_note(profile_id, name=property_name),
                damage=actual_damage,
                x=int(pos[0]),
                y=int(pos[1]),
                z=int(pos[2]),
            )
        )

        if actual_damage > 0:
            self.sim.emit(
                Event(
                    "entity_damaged",
                    target_eid=eid,
                    source_eid=None,
                    weapon_id=f"fire:{profile_id}",
                    damage_kind="condition",
                    raw_damage=actual_damage,
                    damage=actual_damage,
                    cover_absorb=0.0,
                    armor_absorb=0.0,
                    hp=int(vitality.hp),
                    max_hp=int(getattr(vitality, "max_hp", old_hp) or old_hp),
                    x=int(pos[0]),
                    y=int(pos[1]),
                    z=int(pos[2]),
                )
            )

        if vitality.hp > 0:
            return True

        vitality.downed = True
        vitality.downed_tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        setattr(vitality, "death_reason", "burned")
        target_name = ""
        if eid == getattr(self.sim, "player_eid", None):
            self.sim.emit(
                Event(
                    "player_killed",
                    target_eid=eid,
                    source_eid=None,
                    source_name="",
                    weapon_id=f"fire:{profile_id}",
                    reason="burned",
                    damage_kind="condition",
                    x=int(pos[0]),
                    y=int(pos[1]),
                    z=int(pos[2]),
                )
            )
            return True

        _apply_downed_actor_state(self.sim, eid, tick=getattr(self.sim, "tick", 0))
        collider = collider_map.get(eid) if collider_map else None
        if collider is not None:
            collider.blocks = False
        render = render_map.get(eid) if render_map else None
        if render is not None:
            render.glyph = "x"
        self.sim.emit(
            Event(
                "npc_downed",
                target_eid=eid,
                source_eid=None,
                weapon_id=f"fire:{profile_id}",
                x=int(pos[0]),
                y=int(pos[1]),
                z=int(pos[2]),
            )
        )
        return True

    def _apply_entity_exposure(self):
        state = fire_state(self.sim)
        cooldowns = state.get("contact_cooldowns", {})
        for coord, cell in self._loaded_cells():
            fire_intensity = _safe_int(cell.get("fire_intensity"), 0)
            smoke_intensity = _safe_int(cell.get("smoke_intensity"), 0)
            if fire_intensity <= 0 and smoke_intensity <= 0:
                continue
            entity_ids = tuple(self.sim.tilemap.entities_at(coord[0], coord[1], coord[2]) or ())
            for eid in entity_ids:
                if fire_intensity > 0:
                    key = ("open_flame", coord, int(eid))
                    if _safe_int(getattr(self.sim, "tick", 0), 0) >= _safe_int(cooldowns.get(key), -1):
                        self._apply_damage_to_entity(
                            eid,
                            coord,
                            profile_id="open_flame",
                            property_id=cell.get("property_id"),
                            property_name=_text(cell.get("property_name")) or _text(cell.get("property_id")),
                        )
                        cooldowns[key] = _safe_int(getattr(self.sim, "tick", 0), 0) + FIRE_DAMAGE_INTERVAL
                elif smoke_intensity > 0:
                    key = ("smoke_choke", coord, int(eid))
                    if _safe_int(getattr(self.sim, "tick", 0), 0) >= _safe_int(cooldowns.get(key), -1):
                        self._apply_damage_to_entity(
                            eid,
                            coord,
                            profile_id="smoke_choke",
                            property_id=cell.get("property_id"),
                            property_name=_text(cell.get("property_name")) or _text(cell.get("property_id")),
                        )
                        cooldowns[key] = _safe_int(getattr(self.sim, "tick", 0), 0) + SMOKE_DAMAGE_INTERVAL

    def _mark_structural_damage(self, coord, cell, behavior):
        if not bool(behavior.get("structural_damage_kind")):
            return
        prop = None
        property_id = _text(cell.get("property_id"))
        if property_id:
            prop = getattr(self.sim, "properties", {}).get(property_id)
        if not isinstance(prop, dict):
            return

        kind = _text(behavior.get("structural_damage_kind")).lower()
        mark_key = (coord, kind)
        state = fire_state(self.sim)
        last_tick = _safe_int(state.get("damage_marks", {}).get(mark_key), -10_000)
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        if tick - last_tick < FIRE_SPREAD_INTERVAL:
            return

        record = record_building_damage(
            self.sim,
            prop,
            coord[0],
            coord[1],
            coord[2],
            kind=kind,
            aperture_kind=_text(behavior.get("aperture_kind")).lower(),
            cause="fire",
            offender_eid=cell.get("source_eid"),
            damage_tick=tick,
        )
        if record is None:
            return
        state["damage_marks"][mark_key] = tick

        if kind == "window":
            self.sim.tilemap.set_tile(
                int(coord[0]),
                int(coord[1]),
                Tile(walkable=True, transparent=True, glyph="/", color="feature_window", semantic_id="feature_window"),
                z=int(coord[2]),
            )
        elif kind == "door":
            self.sim.set_door_state(
                int(coord[0]),
                int(coord[1]),
                int(coord[2]),
                open=True,
                kind=_text(behavior.get("aperture_kind")).lower() or "door",
                property_id=property_id or None,
            )
            self.sim.apply_door_state(int(coord[0]), int(coord[1]), int(coord[2]))
        elif kind == "wall":
            self.sim.tilemap.set_tile(
                int(coord[0]),
                int(coord[1]),
                Tile(walkable=True, transparent=True, glyph="/", color="building_edge", semantic_id="wall_building"),
                z=int(coord[2]),
            )

    def _attempt_spread_to_neighbor(self, source_coord, source_cell, target_coord):
        target_chunk = self.sim.chunk_coords(target_coord[0], target_coord[1])
        if not _chunk_loaded(self.sim, target_chunk):
            note_frozen_fire_boundary(
                self.sim,
                target_coord,
                from_coord=source_coord,
                source_kind="fire_spread",
                pressure=max(1, _safe_int(source_cell.get("fire_intensity"), 1)),
            )
            return False
        behavior = fire_behavior_for_cell(self.sim, target_coord[0], target_coord[1], target_coord[2])
        if not bool(behavior.get("can_ignite")):
            if bool(behavior.get("can_carry_smoke")):
                upsert_fire_cell(
                    self.sim,
                    target_coord[0],
                    target_coord[1],
                    target_coord[2],
                    fire_intensity=0,
                    smoke_intensity=1,
                    source_kind="smoke_drift",
                    source_property_id=source_cell.get("property_id"),
                    property_id=behavior.get("property_id"),
                    building_id=behavior.get("building_id"),
                    burn_tier=behavior.get("burn_tier"),
                    burn_budget=0,
                    started_tick=getattr(self.sim, "tick", 0),
                    last_advanced_tick=getattr(self.sim, "tick", 0),
                )
            return False

        source_behavior = fire_behavior_for_cell(self.sim, source_coord[0], source_coord[1], source_coord[2])
        chance = (
            0.12
            + _safe_float(source_behavior.get("spread_bias"), 0.0) * 0.42
            + _safe_float(behavior.get("spread_bias"), 0.0) * 0.34
            + (0.1 if _text(source_cell.get("building_id")) and _text(source_cell.get("building_id")) == _text(behavior.get("building_id")) else 0.0)
            + (0.08 if _text(source_behavior.get("room_kind")) and _text(source_behavior.get("room_kind")) == _text(behavior.get("room_kind")) else 0.0)
        )
        chance = max(0.0, min(0.96, chance))
        roll = random.Random(
            f"{getattr(self.sim, 'seed', 0)}:fire-spread:{getattr(self.sim, 'tick', 0)}:{source_coord}:{target_coord}"
        ).random()
        if roll > chance:
            upsert_fire_cell(
                self.sim,
                target_coord[0],
                target_coord[1],
                target_coord[2],
                fire_intensity=0,
                smoke_intensity=1,
                source_kind="smoke_drift",
                source_property_id=source_cell.get("property_id"),
                property_id=behavior.get("property_id"),
                building_id=behavior.get("building_id"),
                burn_tier=behavior.get("burn_tier"),
                burn_budget=0,
                started_tick=getattr(self.sim, "tick", 0),
                last_advanced_tick=getattr(self.sim, "tick", 0),
            )
            return False

        return self._ignite_cell(
            target_coord[0],
            target_coord[1],
            target_coord[2],
            source_kind="spread",
            source_eid=source_cell.get("source_eid"),
            source_property_id=source_cell.get("property_id"),
            spread_from=source_coord,
            intensity=max(1, _safe_int(source_cell.get("fire_intensity"), 1) - 1),
        ) is not None

    def _advance_boundary_pressure(self):
        boundaries = dict(fire_state(self.sim).get("frozen_boundaries", {}) or {})
        for target_coord, record in boundaries.items():
            target_chunk = self.sim.chunk_coords(target_coord[0], target_coord[1])
            if not _chunk_loaded(self.sim, target_chunk):
                continue
            from_coord = record.get("from_coord")
            source_cell = fire_cell_state(self.sim, *(from_coord or (None, None, None))) if isinstance(from_coord, tuple) else None
            if not isinstance(source_cell, dict) or _safe_int(source_cell.get("fire_intensity"), 0) <= 0:
                clear_frozen_fire_boundary(self.sim, target_coord)
                continue
            pressure = max(1, _safe_int(record.get("pressure"), 1))
            if pressure >= 2:
                ignited = self._ignite_cell(
                    target_coord[0],
                    target_coord[1],
                    target_coord[2],
                    source_kind="spread",
                    source_eid=source_cell.get("source_eid"),
                    source_property_id=source_cell.get("property_id"),
                    spread_from=from_coord,
                    intensity=min(3, pressure),
                )
                if ignited is not None:
                    clear_frozen_fire_boundary(self.sim, target_coord)
                    continue
            if self._attempt_spread_to_neighbor(from_coord, source_cell, target_coord):
                clear_frozen_fire_boundary(self.sim, target_coord)

    def _advance_cells(self):
        state = fire_state(self.sim)
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        derived_previous_active = {
            property_id
            for property_id, coords in tuple(state.get("property_index", {}).items())
            for coord in tuple(coords or ())
            if _safe_int((state.get("cells", {}).get(coord) or {}).get("fire_intensity"), 0) > 0
        }
        derived_previous_smoke = {
            property_id
            for property_id, coords in tuple(state.get("property_index", {}).items())
            for coord in tuple(coords or ())
            if _safe_int((state.get("cells", {}).get(coord) or {}).get("smoke_intensity"), 0) > 0
        }
        previous_active = set(state.get("last_active_properties", ()) or ()) or derived_previous_active
        previous_smoke = set(state.get("last_smoke_properties", ()) or ()) or derived_previous_smoke

        for coord, cell in tuple(self._loaded_cells()):
            fire_intensity = _safe_int(cell.get("fire_intensity"), 0)
            smoke_intensity = _safe_int(cell.get("smoke_intensity"), 0)
            if fire_intensity <= 0 and smoke_intensity <= 0:
                remove_fire_cell(self.sim, coord[0], coord[1], coord[2])
                continue
            if tick - _safe_int(cell.get("last_advanced_tick"), -10_000) < FIRE_SPREAD_INTERVAL:
                continue
            cell["last_advanced_tick"] = tick
            behavior = fire_behavior_for_cell(self.sim, coord[0], coord[1], coord[2])
            if fire_intensity > 0:
                self._mark_structural_damage(coord, cell, behavior)
                for target in _neighbor_coords(coord[0], coord[1], coord[2]):
                    self._attempt_spread_to_neighbor(coord, cell, target)
                cell["smoke_intensity"] = max(smoke_intensity, max(1, fire_intensity))
                budget = max(0, _safe_int(cell.get("burn_budget"), 0) - 1)
                cell["burn_budget"] = budget
                if budget <= 0:
                    cell["fire_intensity"] = max(0, fire_intensity - 1)
                else:
                    cell["fire_intensity"] = max(fire_intensity, 1)
            elif smoke_intensity > 0:
                cell["smoke_intensity"] = max(0, smoke_intensity - 1)

            if _safe_int(cell.get("fire_intensity"), 0) <= 0 and _safe_int(cell.get("smoke_intensity"), 0) <= 0:
                remove_fire_cell(self.sim, coord[0], coord[1], coord[2])

        current_active = {
            property_id
            for property_id, coords in tuple(fire_state(self.sim).get("property_index", {}).items())
            for coord in tuple(coords or ())
            if _safe_int((fire_state(self.sim).get("cells", {}).get(coord) or {}).get("fire_intensity"), 0) > 0
        }
        current_smoke = {
            property_id
            for property_id, coords in tuple(fire_state(self.sim).get("property_index", {}).items())
            for coord in tuple(coords or ())
            if _safe_int((fire_state(self.sim).get("cells", {}).get(coord) or {}).get("smoke_intensity"), 0) > 0
        }
        state["last_active_properties"] = set(current_active)
        state["last_smoke_properties"] = set(current_smoke)

        for property_id in sorted(previous_active - current_active):
            prop = getattr(self.sim, "properties", {}).get(property_id)
            summary = property_fire_summary(self.sim, prop) if isinstance(prop, dict) else {}
            self.sim.emit(
                Event(
                    "fire_contained",
                    property_id=property_id,
                    property_name=_text((prop or {}).get("name")),
                    building_id=_text((summary or {}).get("building_id")),
                    x=(summary.get("anchor") or (prop or {}).get("x")),
                    y=(summary.get("anchor") or (None, (prop or {}).get("y")))[1] if isinstance(summary.get("anchor"), tuple) else (prop or {}).get("y"),
                    z=(summary.get("anchor") or (None, None, (prop or {}).get("z", 0)))[2] if isinstance(summary.get("anchor"), tuple) else (prop or {}).get("z", 0),
                )
            )
            if isinstance(prop, dict):
                _record_fire_aftermath(
                    self.sim,
                    prop,
                    severity=0.48 + (0.08 * max(1, int(summary.get("max_intensity", 1) or 1))),
                )

        for property_id in sorted(previous_smoke - current_smoke):
            prop = getattr(self.sim, "properties", {}).get(property_id)
            if not isinstance(prop, dict):
                continue
            self.sim.emit(
                Event(
                    "fire_burned_out",
                    property_id=property_id,
                    property_name=_text(prop.get("name")),
                    x=int(prop.get("x", 0)),
                    y=int(prop.get("y", 0)),
                    z=int(prop.get("z", 0)),
                )
            )

    def _sync_fire_response_seeds(self):
        state = fire_state(self.sim)
        seed_state = _business_event_seed_state(self.sim)
        response_seed_ids = state.get("response_seed_ids", {})
        ticks_per_hour = _world_ticks_per_hour(self.sim)

        active_properties = {
            property_id
            for property_id in tuple(state.get("property_index", {}).keys())
            if property_fire_summary(self.sim, getattr(self.sim, "properties", {}).get(property_id)).get("active")
        }

        for property_id in tuple(active_properties):
            prop = getattr(self.sim, "properties", {}).get(property_id)
            if not isinstance(prop, dict):
                continue
            summary = property_fire_summary(self.sim, prop)
            if not summary.get("active") or not summary.get("public_frontage"):
                continue
            seed_id = _text(response_seed_ids.get(property_id)) or f"fire-response:{property_id}"
            response_seed_ids[property_id] = seed_id
            seed_state["active"][seed_id] = {
                "seed_id": seed_id,
                "kind": "fire_response",
                "category": _seed_archetype_category(prop),
                "target_property_id": property_id,
                "source_property_id": property_id,
                "start_tick": min(
                    _safe_int(seed_state["active"].get(seed_id, {}).get("start_tick"), _safe_int(getattr(self.sim, "tick", 0), 0)),
                    _safe_int(getattr(self.sim, "tick", 0), 0),
                ),
                "end_tick": _safe_int(getattr(self.sim, "tick", 0), 0) + max(FIRE_RESPONSE_KEEP_TICKS, ticks_per_hour),
                "priority_score": 24.0 + float(summary.get("active_cells", 0) or 0),
                "blueprint": {
                    "scene_type": "gathering",
                    "fixture_name": "Response Barrier",
                    "fixture_type": "fire_response_barrier",
                    "fixture_glyph": "!",
                    "actor_specs": [
                        {"role": "worker", "career": "response_worker", "linger_ticks": 16, "fixed_position": True},
                        {"role": "guard", "career": "traffic_guard", "linger_ticks": 16, "fixed_position": True},
                    ],
                    "keep_hours": 1,
                    "release_budget": 0,
                    "drift_preferred": False,
                },
                "local_line": f"{_text(prop.get('name', prop.get('id', 'The site')))} is still on fire, and the front is being held while people try to keep the block from feeding it.",
                "detail_line": f"Flame and smoke are still visible at {_text(prop.get('name', prop.get('id', 'the site')))}. Expect a public cordon, live response motion, and a frontage nobody trusts yet.",
                "lead_kind": "access",
                "shared": False,
                "consequence_seed_id": "",
            }

        for property_id, seed_id in tuple(response_seed_ids.items()):
            if property_id in active_properties:
                continue
            seed_state["active"].pop(_text(seed_id), None)
            response_seed_ids.pop(property_id, None)

    def update(self):
        fire_state(self.sim)
        self._review_environmental_ignitions()
        self._advance_boundary_pressure()
        self._advance_cells()
        self._apply_entity_exposure()
        self._sync_fire_response_seeds()
        fire_protected_chunks(self.sim)


__all__ = ["FireSystem"]
