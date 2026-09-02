"""Incremental chunk housing supply, occupancy, and pressure.

Housing is intentionally separate from lodging/service demand.  Every public
read consumes cached totals; property and settlement mutation call sites own
the small updates that keep those totals true.
"""

from __future__ import annotations

from game.components import NPCSettlement, NPCRoutine, Position
from game.property_runtime import property_focus_position, resolve_property_record


HOUSING_MARKET_SCHEMA = 2
PERMANENT_HOUSING_ARCHETYPES = frozenset({"house", "apartment", "tenement"})
TEMPORARY_HOUSING_STATUSES = frozenset({
    "shelter", "temporary", "lodged", "lodging", "hotel", "motel", "worksite", "workplace",
})
PERMANENT_HOUSING_STATUSES = frozenset({"housing", "housed", "permanent", "house", "apartment", "tenement"})

HOUSING_MARKET_TUNING = {
    "house_daily_cost": 30,
    "apartment_daily_cost": 14,
    "tenement_daily_cost": 8,
    "rent_pressure_gain": 0.15,
    "rent_index_cap": 2.5,
    "growth_pressure": 1.25,
    "growth_survey_streak": 3,
    "growth_vacancy_ratio": 0.10,
}


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _state(sim, *, create=True):
    state = getattr(sim, "neighborhood_housing", None)
    if not isinstance(state, dict):
        if not create:
            return {}
        state = {
            "schema": HOUSING_MARKET_SCHEMA,
            "revision": 0,
            "chunks": {},
            "properties": {},
            "temporary_properties": {},
            "convertible": {},
            "actors": {},
        }
        sim.neighborhood_housing = state
    state.setdefault("schema", HOUSING_MARKET_SCHEMA)
    state.setdefault("revision", 0)
    state.setdefault("chunks", {})
    state.setdefault("properties", {})
    state.setdefault("temporary_properties", {})
    state.setdefault("convertible", {})
    state.setdefault("actors", {})
    return state


def neighborhood_housing_state(sim, *, create=True):
    return _state(sim, create=create)


def _chunk_key(sim, prop=None, fallback=None, eid=None):
    candidates = []
    if isinstance(prop, dict):
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        candidates.append(metadata.get("chunk"))
    candidates.append(fallback)
    for candidate in candidates:
        try:
            return (int(candidate[0]), int(candidate[1]))
        except (TypeError, ValueError, IndexError):
            pass
    if isinstance(prop, dict):
        try:
            return tuple(int(value) for value in sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))[:2])
        except (TypeError, ValueError, AttributeError):
            pass
    if eid is not None:
        pos = sim.ecs.get(Position).get(int(eid))
        if pos is not None:
            try:
                return tuple(int(value) for value in sim.chunk_coords(int(pos.x), int(pos.y))[:2])
            except (TypeError, ValueError, AttributeError):
                pass
    return None


def _archetype(prop):
    metadata = prop.get("metadata") if isinstance(prop, dict) and isinstance(prop.get("metadata"), dict) else {}
    return str(metadata.get("archetype", "") or "").strip().lower()


def _levels(prop):
    metadata = prop.get("metadata") if isinstance(prop, dict) and isinstance(prop.get("metadata"), dict) else {}
    for key in ("total_levels", "level_count", "floors", "stories"):
        if key in metadata:
            return max(1, _int(metadata.get(key), 1))
    levels = metadata.get("levels")
    if isinstance(levels, (list, tuple, dict)):
        return max(1, len(levels))
    return 1


def housing_capacity_for_property(prop):
    if not isinstance(prop, dict):
        return 0
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    configured = _int(metadata.get("housing_capacity"), 0)
    if configured > 0:
        return configured
    archetype = _archetype(prop)
    if archetype == "house":
        return 1
    if archetype == "apartment":
        return max(4, 2 * _levels(prop))
    if archetype == "tenement":
        return max(6, 3 * _levels(prop))
    return 0


def housing_daily_cost_for_property(prop):
    if not isinstance(prop, dict):
        return 0
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    configured = _int(metadata.get("housing_daily_cost", metadata.get("rent_daily", 0)), 0)
    if configured > 0:
        return configured
    archetype = _archetype(prop)
    return max(0, _int(HOUSING_MARKET_TUNING.get(f"{archetype}_daily_cost"), 0))


def _chunk_row(state, chunk):
    return state["chunks"].setdefault(chunk, {
        "properties": {},
        "capacity": 0,
        "occupied": 0,
        "vacancies": 0,
        "unhoused": 0,
        "temporary": 0,
        "worksite": 0,
        "daily_cost_capacity_total": 0,
        "rent_index": 1.0,
        "pressure": 0.0,
    })


def _refresh_chunk_totals(row):
    properties = row.get("properties") if isinstance(row.get("properties"), dict) else {}
    capacity = sum(max(0, _int(value.get("capacity"), 0)) for value in properties.values() if isinstance(value, dict))
    occupied = sum(len(value.get("residents", {}) or {}) for value in properties.values() if isinstance(value, dict))
    cost_total = sum(
        max(0, _int(value.get("daily_cost"), 0)) * max(0, _int(value.get("capacity"), 0))
        for value in properties.values()
        if isinstance(value, dict)
    )
    row["capacity"] = capacity
    row["occupied"] = occupied
    row["vacancies"] = max(0, capacity - occupied)
    row["daily_cost_capacity_total"] = cost_total
    pressure_mass = max(0, _int(row.get("unhoused"), 0)) + max(0, _int(row.get("temporary"), 0)) + max(0, _int(row.get("worksite"), 0))
    row["pressure"] = round(float(pressure_mass) / float(max(1, row["vacancies"])), 4)
    row["rent_index"] = round(min(
        _float(HOUSING_MARKET_TUNING["rent_index_cap"], 2.5),
        1.0 + (_float(HOUSING_MARKET_TUNING["rent_pressure_gain"], 0.15) * row["pressure"]),
    ), 4)
    return row


def forget_housing_property(sim, property_id):
    state = _state(sim, create=False)
    old = state.get("properties", {}).pop(str(property_id), None)
    temporary = state.get("temporary_properties", {}).pop(str(property_id), None)
    convertible = state.get("convertible", {}).pop(str(property_id), None)
    if not isinstance(old, dict) and not isinstance(temporary, dict) and not isinstance(convertible, dict):
        return False
    if not isinstance(old, dict) and isinstance(temporary, dict):
        try:
            chunk = (int(temporary["chunk"][0]), int(temporary["chunk"][1]))
        except (TypeError, ValueError, KeyError, IndexError):
            return False
        row = state.get("chunks", {}).get(chunk)
        if isinstance(row, dict):
            row.setdefault("temporary_property_ids", {}).pop(str(property_id), None)
        state["revision"] = _int(state.get("revision"), 0) + 1
        return True
    if not isinstance(old, dict):
        try:
            chunk = (int(convertible["chunk"][0]), int(convertible["chunk"][1]))
        except (TypeError, ValueError, KeyError, IndexError):
            return False
        row = state.get("chunks", {}).get(chunk)
        if isinstance(row, dict):
            row.setdefault("convertible_property_ids", {}).pop(str(property_id), None)
        state["revision"] = _int(state.get("revision"), 0) + 1
        return True
    try:
        chunk = (int(old["chunk"][0]), int(old["chunk"][1]))
    except (TypeError, ValueError, KeyError, IndexError):
        return False
    row = state.get("chunks", {}).get(chunk)
    if isinstance(row, dict):
        row.get("properties", {}).pop(str(property_id), None)
        _refresh_chunk_totals(row)
    state["revision"] = _int(state.get("revision"), 0) + 1
    return True


def record_housing_property(sim, prop, *, chunk=None):
    """Replace one permanent-housing contribution incrementally."""

    if sim is None or not isinstance(prop, dict):
        return None
    property_id = str(prop.get("id", "") or "").strip()
    if not property_id:
        return None
    state = _state(sim)
    old = state.get("properties", {}).get(property_id)
    if not isinstance(old, dict):
        old = state.get("temporary_properties", {}).get(property_id)
    old_residents = dict(old.get("residents", {}) or {}) if isinstance(old, dict) else {}
    forget_housing_property(sim, property_id)
    capacity = housing_capacity_for_property(prop)
    if capacity <= 0:
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        property_chunk = _chunk_key(sim, prop, fallback=chunk)
        from game.property_runtime import property_services
        services = {
            str(service or "").strip().lower()
            for service in tuple(property_services(prop) or ())
            if str(service or "").strip()
        }
        archetype = _archetype(prop)
        temporary_capacity = 0
        if archetype in {"hotel", "flophouse"}:
            temporary_capacity = 10
        elif archetype in {"ruin_shelter", "barracks"} or "shelter" in services:
            temporary_capacity = 12
        elif "rest" in services:
            temporary_capacity = 8
        if temporary_capacity > 0 and property_chunk is not None:
            record = {
                "property_id": property_id,
                "chunk": property_chunk,
                "archetype": archetype,
                "capacity": temporary_capacity,
                "daily_cost": max(0, _int(metadata.get("housing_daily_cost", metadata.get("rent_daily", 8)), 8)),
                "status": "shelter" if "shelter" in services or archetype in {"ruin_shelter", "barracks"} else "lodging",
                "residents": old_residents,
            }
            state["temporary_properties"][property_id] = record
            _chunk_row(state, property_chunk).setdefault("temporary_property_ids", {})[property_id] = True
            state["revision"] = _int(state.get("revision"), 0) + 1
            return dict(record)
        structurally_suitable = (
            str(prop.get("kind", "") or "").strip().lower() == "building"
            and property_chunk is not None
            and not bool(metadata.get("structurally_unsuitable"))
            and bool(metadata.get("economic_closed") or metadata.get("vacant") or metadata.get("abandoned"))
        )
        if structurally_suitable:
            from game.service_category_registry import property_has_protected_market_capability
            if not property_has_protected_market_capability(prop):
                convertible = {
                    "property_id": property_id,
                    "chunk": property_chunk,
                    "archetype": _archetype(prop),
                    "owner_eid": prop.get("owner_eid"),
                    "purchase_cost": max(80, _int(metadata.get("purchase_cost"), 150)),
                }
                state["convertible"][property_id] = convertible
                _chunk_row(state, property_chunk).setdefault("convertible_property_ids", {})[property_id] = True
                state["revision"] = _int(state.get("revision"), 0) + 1
        return None
    property_chunk = _chunk_key(sim, prop, fallback=chunk)
    if property_chunk is None:
        return None
    record = {
        "property_id": property_id,
        "chunk": property_chunk,
        "archetype": _archetype(prop),
        "capacity": capacity,
        "daily_cost": housing_daily_cost_for_property(prop),
        "residents": old_residents,
    }
    state["properties"][property_id] = record
    row = _chunk_row(state, property_chunk)
    row["properties"][property_id] = record
    if str(row.get("conversion_plan_property_id", "") or "") == property_id:
        row["conversion_plan_property_id"] = ""
    _refresh_chunk_totals(row)
    state["revision"] = _int(state.get("revision"), 0) + 1
    return dict(record)


def _remove_actor_pressure(state, eid):
    old = state.get("actors", {}).get(int(eid))
    if not isinstance(old, dict):
        return
    try:
        chunk = (int(old["chunk"][0]), int(old["chunk"][1]))
    except (TypeError, ValueError, KeyError, IndexError):
        return
    row = state.get("chunks", {}).get(chunk)
    if not isinstance(row, dict):
        return
    status = str(old.get("status", "") or "").strip().lower()
    if status in {"unhoused", "drifting"}:
        row["unhoused"] = max(0, _int(row.get("unhoused"), 0) - 1)
    elif status in {"worksite", "workplace"}:
        row["worksite"] = max(0, _int(row.get("worksite"), 0) - 1)
    elif status in TEMPORARY_HOUSING_STATUSES:
        row["temporary"] = max(0, _int(row.get("temporary"), 0) - 1)
    property_id = str(old.get("property_id", "") or "").strip()
    prop_row = state.get("properties", {}).get(property_id)
    if isinstance(prop_row, dict):
        prop_row.get("residents", {}).pop(int(eid), None)
    temporary_row = state.get("temporary_properties", {}).get(property_id)
    if isinstance(temporary_row, dict):
        temporary_row.get("residents", {}).pop(int(eid), None)
    _refresh_chunk_totals(row)


def set_actor_home(
    sim,
    actor_eid,
    property_id="",
    *,
    housing_status=None,
    phase=None,
    reason="",
    update_routine=True,
):
    """Atomically update settlement, routine, occupancy, and housing pressure."""

    eid = int(actor_eid)
    state = _state(sim)
    property_id = str(property_id or "").strip()
    prop = resolve_property_record(sim, property_id, include_saved=False) if property_id else None
    if isinstance(prop, dict) and housing_capacity_for_property(prop) > 0 and property_id not in state["properties"]:
        record_housing_property(sim, prop)

    settlement = sim.ecs.get(NPCSettlement).get(eid)
    if settlement is None:
        settlement = NPCSettlement()
        sim.ecs.add(eid, settlement)
    status = str(housing_status or "").strip().lower()
    if not status:
        status = "housing" if isinstance(prop, dict) and housing_capacity_for_property(prop) > 0 else "unhoused"
    chunk = _chunk_key(sim, prop, eid=eid)
    old_actor = state.get("actors", {}).get(eid)
    same_cached_home = bool(
        isinstance(old_actor, dict)
        and tuple(old_actor.get("chunk", ()) or ()) == tuple(chunk or ())
        and str(old_actor.get("property_id", "") or "").strip() == property_id
        and str(old_actor.get("status", "") or "").strip().lower() == status
        and str(getattr(settlement, "home_property_id", "") or "").strip() == property_id
        and str(getattr(settlement, "housing_status", "") or "").strip().lower() == status
    )
    settlement.home_property_id = property_id
    settlement.housing_status = status
    if phase is not None:
        settlement.phase = str(phase or "").strip().lower()

    if update_routine and isinstance(prop, dict):
        focus = property_focus_position(prop)
        if focus is not None:
            routine = sim.ecs.get(NPCRoutine).get(eid)
            if routine is None:
                routine = NPCRoutine()
                sim.ecs.add(eid, routine)
            routine.home = tuple(int(value) for value in focus[:3])

    if same_cached_home:
        return settlement
    _remove_actor_pressure(state, eid)
    settlement.last_housing_tick = _int(getattr(sim, "tick", 0), 0)
    if chunk is None:
        return settlement
    actor_row = {
        "eid": eid,
        "chunk": chunk,
        "property_id": property_id,
        "status": status,
        "reason": str(reason or "").strip().lower(),
        "tick": _int(getattr(sim, "tick", 0), 0),
    }
    state["actors"][eid] = actor_row
    chunk_row = _chunk_row(state, chunk)
    if status in PERMANENT_HOUSING_STATUSES and property_id in state["properties"]:
        state["properties"][property_id].setdefault("residents", {})[eid] = status
    elif status in {"worksite", "workplace"}:
        chunk_row["worksite"] = _int(chunk_row.get("worksite"), 0) + 1
    elif status in TEMPORARY_HOUSING_STATUSES:
        chunk_row["temporary"] = _int(chunk_row.get("temporary"), 0) + 1
        temporary_row = state.get("temporary_properties", {}).get(property_id)
        if isinstance(temporary_row, dict):
            temporary_row.setdefault("residents", {})[eid] = status
    else:
        chunk_row["unhoused"] = _int(chunk_row.get("unhoused"), 0) + 1
    _refresh_chunk_totals(chunk_row)
    state["revision"] = _int(state.get("revision"), 0) + 1
    return settlement


def neighborhood_housing_read(sim, chunk):
    """Return one cached housing-market row without scanning actors or sites."""

    try:
        chunk = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError, IndexError):
        return {}
    row = _state(sim, create=False).get("chunks", {}).get(chunk)
    if not isinstance(row, dict):
        return {
            "chunk": chunk,
            "capacity": 0,
            "occupied": 0,
            "vacancies": 0,
            "unhoused": 0,
            "temporary": 0,
            "worksite": 0,
            "pressure": 0.0,
            "rent_index": 1.0,
            "average_daily_cost": 0.0,
            "vacant_property_ids": (),
            "convertible_property_ids": (),
            "temporary_property_ids": (),
            "growth_streak": 0,
        }
    properties = row.get("properties") if isinstance(row.get("properties"), dict) else {}
    capacity = max(0, _int(row.get("capacity"), 0))
    return {
        "chunk": chunk,
        "capacity": capacity,
        "occupied": max(0, _int(row.get("occupied"), 0)),
        "vacancies": max(0, _int(row.get("vacancies"), 0)),
        "unhoused": max(0, _int(row.get("unhoused"), 0)),
        "temporary": max(0, _int(row.get("temporary"), 0)),
        "worksite": max(0, _int(row.get("worksite"), 0)),
        "pressure": round(max(0.0, _float(row.get("pressure"))), 4),
        "rent_index": round(max(0.0, _float(row.get("rent_index"), 1.0)), 4),
        "average_daily_cost": round(
            _float(row.get("daily_cost_capacity_total")) / float(max(1, capacity)), 2
        ),
        "property_ids": tuple(sorted(properties)),
        "vacant_property_ids": tuple(sorted(
            property_id
            for property_id, prop_row in properties.items()
            if isinstance(prop_row, dict)
            and len(prop_row.get("residents", {}) or {}) < max(0, _int(prop_row.get("capacity"), 0))
        )),
        "convertible_property_ids": tuple(sorted((row.get("convertible_property_ids") or {}).keys())),
        "temporary_property_ids": tuple(sorted((row.get("temporary_property_ids") or {}).keys())),
        "growth_streak": max(0, _int(row.get("growth_streak"), 0)),
        "conversion_plan_property_id": str(row.get("conversion_plan_property_id", "") or ""),
    }


def record_housing_survey_completion(sim, chunk):
    """Advance chunk housing-growth hysteresis from one completed survey."""

    try:
        chunk = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError, IndexError):
        return None
    state = _state(sim)
    row = _chunk_row(state, chunk)
    _refresh_chunk_totals(row)
    capacity = max(0, _int(row.get("capacity"), 0))
    vacancies = max(0, _int(row.get("vacancies"), 0))
    vacancy_ratio = float(vacancies) / float(max(1, capacity))
    strained = (
        _float(row.get("pressure"), 0.0) > _float(HOUSING_MARKET_TUNING["growth_pressure"], 1.25)
        and vacancy_ratio < _float(HOUSING_MARKET_TUNING["growth_vacancy_ratio"], 0.10)
    )
    row["growth_streak"] = _int(row.get("growth_streak"), 0) + 1 if strained else 0
    row["last_completed_survey_tick"] = _int(getattr(sim, "tick", 0), 0)
    if row["growth_streak"] >= _int(HOUSING_MARKET_TUNING["growth_survey_streak"], 3) and not str(row.get("conversion_plan_property_id", "") or ""):
        candidates = []
        for property_id in sorted((row.get("convertible_property_ids") or {}).keys()):
            cached = state.get("convertible", {}).get(property_id)
            prop = resolve_property_record(sim, property_id, include_saved=False)
            if not isinstance(cached, dict) or not isinstance(prop, dict) or prop.get("owner_eid") is None:
                continue
            candidates.append((_int(cached.get("purchase_cost"), 150), property_id, prop))
        candidates.sort(key=lambda item: (item[0], item[1]))
        if candidates:
            from game.neighborhood_businesses import start_housing_conversion_plan
            _cost, property_id, prop = candidates[0]
            target = "tenement" if _float(row.get("pressure"), 0.0) >= 2.5 else "apartment"
            if start_housing_conversion_plan(sim, prop, target_archetype=target):
                row["conversion_plan_property_id"] = property_id
                row["growth_streak"] = 0
    state["revision"] = _int(state.get("revision"), 0) + 1
    return neighborhood_housing_read(sim, chunk)


def housing_property_read(sim, property_id):
    """Return one cached permanent or temporary housing provider."""

    property_id = str(property_id or "").strip()
    state = _state(sim, create=False)
    row = state.get("properties", {}).get(property_id)
    if not isinstance(row, dict):
        row = state.get("temporary_properties", {}).get(property_id)
    return dict(row) if isinstance(row, dict) else {}


def housing_candidate_property_ids(sim, chunk, *, permanent_only=False):
    """Return cached chunk-local home candidates without a property scan."""

    read = neighborhood_housing_read(sim, chunk)
    rows = list(read.get("property_ids", ()) or ())
    if not permanent_only:
        rows.extend(read.get("temporary_property_ids", ()) or ())
    return tuple(dict.fromkeys(str(value) for value in rows if str(value)))


__all__ = [
    "HOUSING_MARKET_TUNING",
    "PERMANENT_HOUSING_ARCHETYPES",
    "forget_housing_property",
    "housing_capacity_for_property",
    "housing_daily_cost_for_property",
    "housing_candidate_property_ids",
    "housing_property_read",
    "neighborhood_housing_read",
    "neighborhood_housing_state",
    "record_housing_property",
    "record_housing_survey_completion",
    "set_actor_home",
]
