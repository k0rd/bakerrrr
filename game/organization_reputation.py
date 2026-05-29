from __future__ import annotations

from engine.events import Event
from engine.systems import System

from game.incident_runtime import incident_record
from game.organizations import organization_policy_snapshot, organization_profile, property_organization_eid
from game.property_access import property_access_level as _property_access_level
from game.property_runtime import property_covering as _property_covering
from game.system_support.awareness_runtime import event_observation_accountability


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
    entry["organization_kind"] = _text(entry.get("organization_kind")).lower() or "other"
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
    entry["organization_kind"] = _text(getattr(profile, "kind", "")).lower() or "other"
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
    snapshot = {
        "organization_eid": int(organization_eid),
        "organization_key": _text(entry.get("organization_key")),
        "name": _text(entry.get("organization_name")) or "Organization",
        "kind": _text(entry.get("organization_kind")).lower() or "other",
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
    policy = organization_policy_snapshot(sim, organization_eid=organization_eid)
    if isinstance(policy, dict):
        snapshot.update(
            {
                "family": _text(policy.get("family")).lower() or snapshot.get("kind", "other"),
                "structure": _text(policy.get("structure")).lower() or "flat",
                "org_role": _text(policy.get("org_role")).lower() or "operator",
                "root_organization_eid": _safe_int(policy.get("root_organization_eid"), default=organization_eid) or int(organization_eid),
                "root_organization_key": _text(policy.get("root_organization_key")),
                "root_organization_name": _text(policy.get("root_organization_name")),
                "root_organization_kind": _text(policy.get("root_organization_kind")).lower() or snapshot.get("kind", "other"),
            }
        )
    return snapshot


def organization_instability_profile(sim, organization_eid=None, prop=None, ensure=False):
    snapshot = organization_snapshot(sim, organization_eid=organization_eid, prop=prop, ensure=ensure)
    if snapshot is None:
        return None

    site_count = max(0, int(snapshot.get("site_count", 0) or 0))
    member_count = max(0, int(snapshot.get("member_count", 0) or 0))
    standing = float(snapshot.get("standing", 0.0) or 0.0)
    heat = max(0, int(snapshot.get("heat", 0) or 0))
    family = _text(snapshot.get("family")).lower() or _text(snapshot.get("kind")).lower() or "other"

    coverage_ratio = 1.0
    coverage_pressure = 0.0
    underrepresented = False
    if site_count > 1:
        coverage_ratio = max(0.0, min(2.0, float(member_count) / float(max(1, site_count))))
        underrepresented = member_count < site_count
        coverage_pressure = _clamp((1.0 - min(1.0, coverage_ratio)) * 0.9, 0.0, 0.9)

    standing_pressure = _clamp(abs(min(0.0, standing)), 0.0, 1.0)
    heat_pressure = _clamp(max(0.0, float(heat - 10) / 70.0), 0.0, 1.0)
    instability = _clamp(
        (standing_pressure * 0.42) + (heat_pressure * 0.36) + (coverage_pressure * 0.22),
        0.0,
        1.0,
    )
    operational_pressure = float(instability)
    if family in {"street_gang", "criminal_network", "criminal"}:
        operational_pressure = _clamp(
            operational_pressure + (heat_pressure * 0.12) + (0.08 if underrepresented else 0.0),
            0.0,
            1.0,
        )

    if instability >= 0.6:
        note = "the branch is running ragged"
    elif underrepresented:
        note = "the branch looks thinly staffed"
    elif heat_pressure >= 0.45:
        note = "the branch is working under pressure"
    elif instability >= 0.22:
        note = "the branch looks uneven"
    else:
        note = ""

    return {
        **snapshot,
        "coverage_ratio": float(coverage_ratio),
        "coverage_pressure": float(coverage_pressure),
        "standing_pressure": float(standing_pressure),
        "heat_pressure": float(heat_pressure),
        "instability": float(instability),
        "operational_pressure": float(operational_pressure),
        "underrepresented": bool(underrepresented),
        "unstable": bool(instability >= 0.22 or underrepresented),
        "ragged": bool(instability >= 0.6),
        "note": note,
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
                "kind": _text(entry.get("organization_kind")).lower() or "other",
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
        "organization_kind": _text(entry.get("organization_kind")).lower() or "other",
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


class OrganizationReputationSystem(System):

    HEAT_DECAY_INTERVAL = 60
    HEAT_DECAY_IDLE_TICKS = 90
    BANKING_STANDING_COOLDOWN = 120
    BANKING_STANDING_MIN_AMOUNT = 20

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.last_banking_standing_tick = {}
        self.sim.events.subscribe("property_trespass", self.on_property_trespass)
        self.sim.events.subscribe("property_tamper", self.on_property_tamper)
        self.sim.events.subscribe("item_stolen", self.on_item_stolen)
        self.sim.events.subscribe("incident_authority_reported", self.on_incident_authority_reported)
        self.sim.events.subscribe("trade_bought", self.on_trade_bought)
        self.sim.events.subscribe("trade_sold", self.on_trade_sold)
        self.sim.events.subscribe("bank_transaction", self.on_bank_transaction)
        self.sim.events.subscribe("insurance_policy_purchased", self.on_insurance_policy_purchased)
        self.sim.events.subscribe("site_service_used", self.on_site_service_used)

    def _property_from_event(self, event):
        data = getattr(event, "data", event)
        if not isinstance(data, dict):
            return None
        property_id = str(data.get("property_id", "") or "").strip()
        if property_id:
            prop = self.sim.properties.get(property_id)
            if isinstance(prop, dict):
                return prop

        try:
            x = int(data.get("x"))
            y = int(data.get("y"))
            z = int(data.get("z", 0))
        except (TypeError, ValueError):
            return None

        prop = _property_covering(self.sim, x, y, z)
        if prop is None:
            prop = self.sim.property_at(x, y, z)
        return prop if isinstance(prop, dict) else None

    def _event_accountability(self, event, *, offender_eid=None):
        return event_observation_accountability(
            self.sim,
            event,
            offender_eid=offender_eid,
            default_channels=("actor_witness",),
        )

    def _mark_incident_accounted(self, incident_id):
        incident = incident_record(self.sim, incident_id)
        if not isinstance(incident, dict):
            return None
        incident["organization_reputation_accounted"] = True
        incident["organization_reputation_accounted_tick"] = int(getattr(self.sim, "tick", 0))
        return incident

    def _apply_trespass_reputation(self, prop, data, *, source_event="property_trespass"):
        severity_label = str(data.get("severity_label", "trespass")).strip().lower() or "trespass"
        access_level = str(data.get("access_level", _property_access_level(prop))).strip().lower() or _property_access_level(prop)
        heat_delta = 2 if severity_label == "suspicious" else 4
        standing_delta = -0.03 if severity_label == "suspicious" else -0.06
        if severity_label == "serious_trespass":
            heat_delta = 7
            standing_delta = -0.12
        heat_delta += 2
        standing_delta -= 0.02
        if access_level == "restricted":
            heat_delta += 2
            standing_delta -= 0.02
        return self._apply_org_delta(
            prop,
            heat_delta=min(18, heat_delta),
            standing_delta=max(-0.24, standing_delta),
            source="trespass",
            reason=severity_label,
            source_event=source_event,
        )

    def _apply_tamper_reputation(self, prop, data, *, source_event="property_tamper"):
        access_level = str(data.get("access_level", _property_access_level(prop))).strip().lower() or _property_access_level(prop)
        severity_score = max(0, int(data.get("severity_score", 0) or 0))
        heat_delta = 6 + max(0, severity_score // 30)
        standing_delta = -0.1
        if access_level == "restricted":
            heat_delta += 2
            standing_delta -= 0.03
        return self._apply_org_delta(
            prop,
            heat_delta=min(20, heat_delta),
            standing_delta=max(-0.28, standing_delta),
            source="tamper",
            reason="property_tamper",
            source_event=source_event,
        )

    def _apply_theft_reputation(self, prop, *, source_event="item_stolen"):
        return self._apply_org_delta(
            prop,
            heat_delta=5,
            standing_delta=-0.08,
            source="theft",
            reason="item_stolen",
            source_event=source_event,
        )

    def _emit_org_change_events(self, change, *, property_id=None):
        if not isinstance(change, dict):
            return

        base_payload = {
            "eid": self.player_eid,
            "organization_eid": change.get("organization_eid"),
            "organization_key": str(change.get("organization_key", "")).strip(),
            "organization_name": str(change.get("organization_name", "Organization")).strip() or "Organization",
            "organization_kind": str(change.get("organization_kind", "other")).strip().lower() or "other",
            "property_id": property_id,
            "source": str(change.get("source", "unknown")).strip().lower() or "unknown",
            "reason": str(change.get("reason", "")).strip().lower(),
            "source_event": str(change.get("source_event", "")).strip().lower(),
            "tick": int(change.get("tick", getattr(self.sim, "tick", 0))),
            "heat_delta": int(change.get("heat_delta", 0)),
            "standing_delta": float(change.get("standing_delta", 0.0)),
            "before_heat": int(change.get("before_heat", 0)),
            "after_heat": int(change.get("after_heat", 0)),
            "before_standing": float(change.get("before_standing", 0.0)),
            "after_standing": float(change.get("after_standing", 0.0)),
        }
        self.sim.emit(Event("organization_reputation_changed", **base_payload))

        if bool(change.get("heat_tier_changed")):
            self.sim.emit(Event(
                "organization_heat_tier_changed",
                **base_payload,
                before_tier=str(change.get("before_heat_tier", "quiet")).strip().lower() or "quiet",
                after_tier=str(change.get("after_heat_tier", "quiet")).strip().lower() or "quiet",
            ))

        if bool(change.get("standing_tier_changed")):
            self.sim.emit(Event(
                "organization_standing_tier_changed",
                **base_payload,
                before_tier=str(change.get("before_standing_tier", "neutral")).strip().lower() or "neutral",
                after_tier=str(change.get("after_standing_tier", "neutral")).strip().lower() or "neutral",
            ))

    def _banking_standing_key(self, prop):
        snapshot = organization_snapshot(self.sim, prop=prop, ensure=True)
        org_key = str((snapshot or {}).get("organization_key", "") or "").strip().lower()
        if org_key:
            return f"org:{org_key}"
        property_id = str(prop.get("id", "") or "").strip()
        if property_id:
            return f"prop:{property_id}"
        return "banking"

    def _banking_standing_ready(self, prop, event):
        try:
            amount = int(event.data.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0
        if amount < int(self.BANKING_STANDING_MIN_AMOUNT):
            return False

        key = self._banking_standing_key(prop)
        tick = int(getattr(self.sim, "tick", 0))
        last_tick = int(self.last_banking_standing_tick.get(key, -10_000))
        if tick - last_tick < int(self.BANKING_STANDING_COOLDOWN):
            return False

        self.last_banking_standing_tick[key] = tick
        if len(self.last_banking_standing_tick) > 256:
            stale_before = tick - (int(self.BANKING_STANDING_COOLDOWN) * 4)
            self.last_banking_standing_tick = {
                bank_key: int(bank_tick)
                for bank_key, bank_tick in self.last_banking_standing_tick.items()
                if int(bank_tick) >= stale_before
            }
        return True

    def _apply_org_delta(
        self,
        prop,
        *,
        heat_delta=0,
        standing_delta=0.0,
        source,
        reason="",
        source_event="",
    ):
        if not isinstance(prop, dict):
            return None
        change = apply_organization_reputation_delta(
            self.sim,
            prop=prop,
            heat_delta=heat_delta,
            standing_delta=standing_delta,
            source=source,
            reason=reason,
            source_event=source_event,
        )
        if change is not None:
            self._emit_org_change_events(change, property_id=prop.get("id"))
        return change

    def on_property_trespass(self, event):
        if event.data.get("offender_eid") != self.player_eid:
            return
        prop = self._property_from_event(event)
        if not isinstance(prop, dict):
            return
        observation = self._event_accountability(event, offender_eid=self.player_eid)
        if not bool(observation.get("has_accountable_observation")):
            return
        change = self._apply_trespass_reputation(prop, event.data, source_event="property_trespass")
        if change is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))

    def on_property_tamper(self, event):
        if event.data.get("offender_eid") != self.player_eid:
            return
        prop = self._property_from_event(event)
        if not isinstance(prop, dict):
            return
        observation = self._event_accountability(event, offender_eid=self.player_eid)
        if not bool(observation.get("has_accountable_observation")):
            return
        change = self._apply_tamper_reputation(prop, event.data, source_event="property_tamper")
        if change is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))

    def on_item_stolen(self, event):
        if event.data.get("offender_eid") != self.player_eid:
            return
        prop = self._property_from_event(event)
        if not isinstance(prop, dict):
            return
        observation = self._event_accountability(event, offender_eid=self.player_eid)
        if not bool(observation.get("has_accountable_observation")):
            return
        change = self._apply_theft_reputation(prop, source_event="item_stolen")
        if change is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))

    def on_incident_authority_reported(self, event):
        incident = incident_record(self.sim, event.data.get("incident_id"))
        if not isinstance(incident, dict):
            return
        if incident.get("primary_actor_eid") != self.player_eid:
            return
        if bool(incident.get("organization_reputation_accounted")):
            return
        report_observation = self._event_accountability(event, offender_eid=self.player_eid)
        if not bool(report_observation.get("has_accountable_observation")):
            return
        prop = self._property_from_event(incident)
        if not isinstance(prop, dict):
            return
        kind = str(incident.get("kind", "") or "").strip().lower()
        if kind in {"camera_alert", "property_trespass"}:
            change = self._apply_trespass_reputation(prop, incident, source_event="incident_authority_reported")
        elif kind == "property_tamper":
            change = self._apply_tamper_reputation(prop, incident, source_event="incident_authority_reported")
        elif kind == "item_stolen":
            change = self._apply_theft_reputation(prop, source_event="incident_authority_reported")
        else:
            return
        if change is not None:
            self._mark_incident_accounted(incident.get("id"))

    def on_trade_bought(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if bool(event.data.get("owner_transfer")):
            return
        prop = self._property_from_event(event)
        if not isinstance(prop, dict):
            return
        self._apply_org_delta(
            prop,
            standing_delta=0.025,
            source="trade",
            reason="bought_goods",
            source_event="trade_bought",
        )

    def on_trade_sold(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if bool(event.data.get("owner_transfer")):
            return
        prop = self._property_from_event(event)
        if not isinstance(prop, dict):
            return
        self._apply_org_delta(
            prop,
            standing_delta=0.02,
            source="trade",
            reason="sold_goods",
            source_event="trade_sold",
        )

    def on_bank_transaction(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        prop = self._property_from_event(event)
        if not isinstance(prop, dict):
            return
        if not self._banking_standing_ready(prop, event):
            return
        self._apply_org_delta(
            prop,
            standing_delta=0.02,
            source="banking",
            reason=str(event.data.get("kind", "transaction")).strip().lower() or "transaction",
            source_event="bank_transaction",
        )

    def on_insurance_policy_purchased(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        prop = self._property_from_event(event)
        if not isinstance(prop, dict):
            return
        self._apply_org_delta(
            prop,
            standing_delta=0.04,
            source="insurance",
            reason=str(event.data.get("policy_key", "policy")).strip().lower() or "policy",
            source_event="insurance_policy_purchased",
        )

    def on_site_service_used(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        prop = self._property_from_event(event)
        if not isinstance(prop, dict):
            return
        service = str(event.data.get("service", "")).strip().lower()
        standing_delta = 0.015
        if service in {"rest", "fuel", "repair", "vehicle_fetch"}:
            standing_delta = 0.02
        elif service.startswith("vehicle_sales_"):
            standing_delta = 0.04
        elif service in {"banking", "insurance"}:
            standing_delta = 0.03
        self._apply_org_delta(
            prop,
            standing_delta=standing_delta,
            source="service",
            reason=service or "site_service",
            source_event="site_service_used",
        )

    def update(self):
        for change in decay_organization_heat(
            self.sim,
            interval=self.HEAT_DECAY_INTERVAL,
            idle_ticks=self.HEAT_DECAY_IDLE_TICKS,
            amount=1,
        ):
            self._emit_org_change_events(change)
