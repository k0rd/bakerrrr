from __future__ import annotations

from game.organizations import organization_profile, property_organization_eid


MAX_HISTORY = 64


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


def _text(value):
    return str(value or "").strip()


def _clamp(value, low, high):
    return max(low, min(high, value))


def organization_heat_tier(heat):
    value = max(0, min(100, _safe_int(heat, default=0)))
    if value >= 55:
        return "burned"
    if value >= 30:
        return "hot"
    if value >= 12:
        return "watchful"
    return "quiet"


def organization_standing_tier(standing):
    value = _clamp(_safe_float(standing, default=0.0), -1.0, 1.0)
    if value <= -0.6:
        return "blacklisted"
    if value <= -0.2:
        return "hostile"
    if value >= 0.6:
        return "trusted"
    if value >= 0.2:
        return "favored"
    return "neutral"


def _state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits

    state = traits.get("organization_reputation")
    if not isinstance(state, dict):
        state = {}
        traits["organization_reputation"] = state

    organizations = state.get("organizations")
    if not isinstance(organizations, dict):
        organizations = {}
        state["organizations"] = organizations

    state["last_decay_tick"] = _safe_int(state.get("last_decay_tick"), default=-10_000)
    return state


def _record_key(profile, organization_eid):
    profile_key = _text(getattr(profile, "key", ""))
    if profile_key:
        return profile_key
    return f"org:{_safe_int(organization_eid, default=0)}"


def _normalize_entry(entry):
    if not isinstance(entry, dict):
        entry = {}
    entry["organization_eid"] = _safe_int(entry.get("organization_eid"), default=0) or None
    entry["organization_key"] = _text(entry.get("organization_key"))
    entry["organization_name"] = _text(entry.get("organization_name")) or "Organization"
    entry["organization_kind"] = _text(entry.get("organization_kind")).lower() or "organization"
    entry["standing"] = _clamp(_safe_float(entry.get("standing"), default=0.0), -1.0, 1.0)
    entry["heat"] = max(0, min(100, _safe_int(entry.get("heat"), default=0)))
    entry["peak_heat"] = max(int(entry["heat"]), _safe_int(entry.get("peak_heat"), default=int(entry["heat"])))
    entry["last_update_tick"] = _safe_int(entry.get("last_update_tick"), default=-10_000)
    entry["last_heat_change_tick"] = _safe_int(entry.get("last_heat_change_tick"), default=-10_000)
    entry["last_standing_change_tick"] = _safe_int(entry.get("last_standing_change_tick"), default=-10_000)
    history = entry.get("history")
    if not isinstance(history, list):
        history = []
    if len(history) > MAX_HISTORY:
        del history[:-MAX_HISTORY]
    entry["history"] = history
    return entry


def ensure_organization_reputation(sim, organization_eid=None, prop=None):
    if organization_eid is None and isinstance(prop, dict):
        organization_eid = property_organization_eid(sim, prop, ensure=True)
    if organization_eid is None:
        return None

    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return None

    state = _state(sim)
    organizations = state["organizations"]
    key = _record_key(profile, organization_eid)
    entry = _normalize_entry(organizations.get(key))
    organizations[key] = entry

    entry["organization_eid"] = int(organization_eid)
    entry["organization_key"] = _text(getattr(profile, "key", "")) or key
    entry["organization_name"] = _text(getattr(profile, "name", "")) or "Organization"
    entry["organization_kind"] = _text(getattr(profile, "kind", "")).lower() or "organization"
    entry["peak_heat"] = max(int(entry["peak_heat"]), int(entry["heat"]))
    return entry


def organization_snapshot(sim, organization_eid=None, prop=None, ensure=False):
    if organization_eid is None and isinstance(prop, dict):
        organization_eid = property_organization_eid(sim, prop, ensure=ensure)
    if organization_eid is None:
        return None

    entry = ensure_organization_reputation(sim, organization_eid=organization_eid)
    if entry is None:
        return None

    profile = organization_profile(sim, organization_eid)
    site_count = len(getattr(profile, "site_property_ids", ())) if profile is not None else 0
    member_count = len(getattr(profile, "member_eids", ())) if profile is not None else 0
    standing = float(entry.get("standing", 0.0))
    heat = int(entry.get("heat", 0))
    return {
        "organization_eid": int(organization_eid),
        "organization_key": _text(entry.get("organization_key")),
        "name": _text(entry.get("organization_name")) or "Organization",
        "kind": _text(entry.get("organization_kind")).lower() or "organization",
        "standing": standing,
        "standing_tier": organization_standing_tier(standing),
        "heat": heat,
        "heat_tier": organization_heat_tier(heat),
        "peak_heat": int(entry.get("peak_heat", heat)),
        "last_update_tick": _safe_int(entry.get("last_update_tick"), default=-10_000),
        "last_heat_change_tick": _safe_int(entry.get("last_heat_change_tick"), default=-10_000),
        "last_standing_change_tick": _safe_int(entry.get("last_standing_change_tick"), default=-10_000),
        "site_count": int(site_count),
        "member_count": int(member_count),
    }


def organization_snapshots(sim):
    state = _state(sim)
    rows = []
    for entry in state["organizations"].values():
        entry = _normalize_entry(entry)
        organization_eid = entry.get("organization_eid")
        if organization_eid is not None:
            snapshot = organization_snapshot(sim, organization_eid=organization_eid, ensure=False)
        else:
            snapshot = {
                "organization_eid": None,
                "organization_key": _text(entry.get("organization_key")),
                "name": _text(entry.get("organization_name")) or "Organization",
                "kind": _text(entry.get("organization_kind")).lower() or "organization",
                "standing": float(entry.get("standing", 0.0)),
                "standing_tier": organization_standing_tier(entry.get("standing", 0.0)),
                "heat": int(entry.get("heat", 0)),
                "heat_tier": organization_heat_tier(entry.get("heat", 0)),
                "peak_heat": int(entry.get("peak_heat", entry.get("heat", 0))),
                "last_update_tick": _safe_int(entry.get("last_update_tick"), default=-10_000),
                "last_heat_change_tick": _safe_int(entry.get("last_heat_change_tick"), default=-10_000),
                "last_standing_change_tick": _safe_int(entry.get("last_standing_change_tick"), default=-10_000),
                "site_count": 0,
                "member_count": 0,
            }
        if snapshot is not None:
            rows.append(snapshot)
    return rows


def top_organization_snapshots(sim, *, limit=3, sort_by="heat"):
    rows = list(organization_snapshots(sim))
    key = str(sort_by or "heat").strip().lower() or "heat"
    if key == "standing":
        rows.sort(
            key=lambda row: (
                -abs(float(row.get("standing", 0.0))),
                -float(row.get("standing", 0.0)),
                -int(row.get("heat", 0)),
                str(row.get("name", "")).lower(),
            )
        )
    elif key == "positive_standing":
        rows = [row for row in rows if float(row.get("standing", 0.0)) > 0.0]
        rows.sort(
            key=lambda row: (
                -float(row.get("standing", 0.0)),
                -int(row.get("heat", 0)),
                str(row.get("name", "")).lower(),
            )
        )
    elif key == "negative_standing":
        rows = [row for row in rows if float(row.get("standing", 0.0)) < 0.0]
        rows.sort(
            key=lambda row: (
                float(row.get("standing", 0.0)),
                -int(row.get("heat", 0)),
                str(row.get("name", "")).lower(),
            )
        )
    else:
        rows.sort(
            key=lambda row: (
                -int(row.get("heat", 0)),
                -abs(float(row.get("standing", 0.0))),
                str(row.get("name", "")).lower(),
            )
        )
    return rows[: max(0, int(limit))]


def organization_terms_for_property(sim, prop):
    snapshot = organization_snapshot(sim, prop=prop, ensure=True)
    if snapshot is None:
        return {
            "organization_eid": None,
            "organization_name": "",
            "standing": 0.0,
            "standing_tier": "neutral",
            "heat": 0,
            "heat_tier": "quiet",
            "buy_mult": 1.0,
            "sell_mult": 1.0,
            "premium_mult": 1.0,
            "note": "",
        }

    standing = float(snapshot.get("standing", 0.0))
    heat = int(snapshot.get("heat", 0))
    heat_ratio = max(0.0, min(1.0, float(heat) / 100.0))

    buy_mult = 1.0
    sell_mult = 1.0
    premium_mult = 1.0

    if standing > 0.0:
        buy_mult *= 1.0 - min(0.08, standing * 0.06)
        sell_mult *= 1.0 + min(0.06, standing * 0.05)
        premium_mult *= 1.0 - min(0.1, standing * 0.08)
    elif standing < 0.0:
        hostility = abs(standing)
        buy_mult *= 1.0 + min(0.12, hostility * 0.09)
        sell_mult *= 1.0 - min(0.08, hostility * 0.06)
        premium_mult *= 1.0 + min(0.14, hostility * 0.1)

    if heat_ratio > 0.0:
        buy_mult *= 1.0 + min(0.1, heat_ratio * 0.12)
        sell_mult *= 1.0 - min(0.08, heat_ratio * 0.08)
        premium_mult *= 1.0 + min(0.12, heat_ratio * 0.12)

    note_bits = []
    if abs(standing) >= 0.18:
        note_bits.append(str(snapshot.get("standing_tier", "neutral")))
    if heat >= 12:
        note_bits.append(f"heat {str(snapshot.get('heat_tier', 'quiet'))}")

    note = ""
    if note_bits:
        note = f"{snapshot.get('name', 'Organization')}: {', '.join(note_bits)}"

    return {
        "organization_eid": snapshot.get("organization_eid"),
        "organization_name": snapshot.get("name", ""),
        "standing": standing,
        "standing_tier": snapshot.get("standing_tier", "neutral"),
        "heat": heat,
        "heat_tier": snapshot.get("heat_tier", "quiet"),
        "buy_mult": max(0.82, min(1.2, buy_mult)),
        "sell_mult": max(0.84, min(1.12, sell_mult)),
        "premium_mult": max(0.84, min(1.2, premium_mult)),
        "note": note,
    }


def apply_organization_reputation_delta(
    sim,
    *,
    organization_eid=None,
    prop=None,
    heat_delta=0,
    standing_delta=0.0,
    source="",
    reason="",
    source_event="",
):
    entry = ensure_organization_reputation(sim, organization_eid=organization_eid, prop=prop)
    if entry is None:
        return None

    organization_eid = entry.get("organization_eid")
    before_heat = int(entry.get("heat", 0))
    before_standing = float(entry.get("standing", 0.0))
    actual_heat = max(-100, min(100, _safe_int(heat_delta, default=0)))
    requested_standing = _safe_float(standing_delta, default=0.0)
    after_heat = max(0, min(100, before_heat + actual_heat))
    after_standing = _clamp(before_standing + requested_standing, -1.0, 1.0)
    actual_heat = int(after_heat - before_heat)
    actual_standing = float(after_standing - before_standing)
    if actual_heat == 0 and abs(actual_standing) < 1e-9:
        return None

    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    before_heat_tier = organization_heat_tier(before_heat)
    after_heat_tier = organization_heat_tier(after_heat)
    before_standing_tier = organization_standing_tier(before_standing)
    after_standing_tier = organization_standing_tier(after_standing)

    entry["heat"] = int(after_heat)
    entry["standing"] = float(after_standing)
    entry["peak_heat"] = max(int(entry.get("peak_heat", 0)), int(after_heat))
    entry["last_update_tick"] = tick
    if actual_heat != 0:
        entry["last_heat_change_tick"] = tick
    if abs(actual_standing) >= 1e-9:
        entry["last_standing_change_tick"] = tick

    history_entry = {
        "tick": tick,
        "heat_delta": int(actual_heat),
        "standing_delta": float(actual_standing),
        "before_heat": int(before_heat),
        "after_heat": int(after_heat),
        "before_standing": float(before_standing),
        "after_standing": float(after_standing),
        "source": _text(source).lower() or "unknown",
        "reason": _text(reason).lower(),
        "source_event": _text(source_event).lower(),
    }
    entry["history"].append(history_entry)
    if len(entry["history"]) > MAX_HISTORY:
        del entry["history"][:-MAX_HISTORY]

    return {
        "organization_eid": organization_eid,
        "organization_key": _text(entry.get("organization_key")),
        "organization_name": _text(entry.get("organization_name")) or "Organization",
        "organization_kind": _text(entry.get("organization_kind")).lower() or "organization",
        "heat_delta": int(actual_heat),
        "standing_delta": float(actual_standing),
        "before_heat": int(before_heat),
        "after_heat": int(after_heat),
        "before_heat_tier": before_heat_tier,
        "after_heat_tier": after_heat_tier,
        "before_standing": float(before_standing),
        "after_standing": float(after_standing),
        "before_standing_tier": before_standing_tier,
        "after_standing_tier": after_standing_tier,
        "heat_tier_changed": before_heat_tier != after_heat_tier,
        "standing_tier_changed": before_standing_tier != after_standing_tier,
        "source": history_entry["source"],
        "reason": history_entry["reason"],
        "source_event": history_entry["source_event"],
        "tick": tick,
    }


def decay_organization_heat(sim, *, interval=120, idle_ticks=90, amount=1):
    state = _state(sim)
    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    interval = max(1, _safe_int(interval, default=120))
    idle_ticks = max(0, _safe_int(idle_ticks, default=90))
    amount = max(1, _safe_int(amount, default=1))

    if tick - int(state.get("last_decay_tick", -10_000)) < interval:
        return []
    state["last_decay_tick"] = tick

    changes = []
    for snapshot in list(organization_snapshots(sim)):
        organization_eid = snapshot.get("organization_eid")
        if organization_eid is None or int(snapshot.get("heat", 0)) <= 0:
            continue
        if tick - int(snapshot.get("last_heat_change_tick", -10_000)) < idle_ticks:
            continue
        change = apply_organization_reputation_delta(
            sim,
            organization_eid=organization_eid,
            heat_delta=-amount,
            source="passive_decay",
            reason="time_passed",
            source_event="organization_reputation_tick",
        )
        if change is not None:
            changes.append(change)
    return changes
