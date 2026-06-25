from __future__ import annotations

from engine.events import Event
from engine.systems import System

from game.incident_runtime import incident_record
from game.organization_reputation import organization_snapshot as _organization_snapshot
from game.system_support.awareness_runtime import event_observation_accountability
from game.system_support.intrusion_runtime import (
    _is_window_aperture,
)
from game.system_support.offense_runtime import _offense_tier
from game.vision_scene_runtime import event_is_vision_only


MAX_ATTENTION = 100
MAX_HISTORY = 64
TIER_EFFECTS = {
    "low": {
        "suspicion_mult": 1.0,
        "goodwill_mult": 1.0,
        "trade_buy_mult": 1.0,
        "trade_sell_mult": 1.0,
        "insurance_premium_mult": 1.0,
        "defense_severity_bias": 0,
        "protect_threshold_shift": 0,
    },
    "medium": {
        "suspicion_mult": 1.12,
        "goodwill_mult": 0.88,
        "trade_buy_mult": 1.04,
        "trade_sell_mult": 0.97,
        "insurance_premium_mult": 1.06,
        "defense_severity_bias": 1,
        "protect_threshold_shift": 1,
    },
    "high": {
        "suspicion_mult": 1.26,
        "goodwill_mult": 0.74,
        "trade_buy_mult": 1.1,
        "trade_sell_mult": 0.93,
        "insurance_premium_mult": 1.12,
        "defense_severity_bias": 3,
        "protect_threshold_shift": 2,
    },
}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def pressure_tier_for(value):
    number = max(0, min(MAX_ATTENTION, _safe_int(value, default=0)))
    if number >= 70:
        return "high"
    if number >= 35:
        return "medium"
    return "low"


def _state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits

    state = traits.get("run_pressure")
    if not isinstance(state, dict):
        state = {}
        traits["run_pressure"] = state

    attention = max(0, min(MAX_ATTENTION, _safe_int(state.get("attention"), default=0)))
    state["attention"] = attention
    state["peak_attention"] = max(attention, _safe_int(state.get("peak_attention"), default=attention))
    state["tier"] = pressure_tier_for(attention)
    state["last_raise_tick"] = _safe_int(state.get("last_raise_tick"), default=-10_000)
    state["last_decay_tick"] = _safe_int(state.get("last_decay_tick"), default=-10_000)
    state["last_change_tick"] = _safe_int(state.get("last_change_tick"), default=-10_000)
    state["mitigation_count"] = max(0, _safe_int(state.get("mitigation_count"), default=0))

    history = state.get("history")
    if not isinstance(history, list):
        history = []
        state["history"] = history
    if len(history) > MAX_HISTORY:
        del history[:-MAX_HISTORY]
    return state


def pressure_snapshot(sim):
    state = _state(sim)
    attention = int(state["attention"])
    tier = pressure_tier_for(attention)
    return {
        "attention": attention,
        "tier": tier,
        "peak_attention": int(state["peak_attention"]),
        "last_raise_tick": int(state["last_raise_tick"]),
        "last_decay_tick": int(state["last_decay_tick"]),
        "last_change_tick": int(state["last_change_tick"]),
        "mitigation_count": int(state["mitigation_count"]),
        "effects": dict(TIER_EFFECTS.get(tier, TIER_EFFECTS["low"])),
    }


def pressure_effects(sim):
    return dict(pressure_snapshot(sim).get("effects", {}))


def apply_pressure_delta(
    sim,
    *,
    delta,
    source,
    reason="",
    source_event="",
):
    state = _state(sim)
    delta = _safe_int(delta, default=0)
    if delta == 0:
        return None

    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    before = int(state["attention"])
    before_tier = pressure_tier_for(before)
    after = max(0, min(MAX_ATTENTION, before + delta))
    actual = int(after - before)
    if actual == 0:
        return None

    after_tier = pressure_tier_for(after)
    state["attention"] = after
    state["peak_attention"] = max(int(state["peak_attention"]), after)
    state["tier"] = after_tier
    state["last_change_tick"] = tick
    if actual > 0:
        state["last_raise_tick"] = tick
    else:
        state["last_decay_tick"] = tick

    key = str(source or "unknown").strip().lower() or "unknown"
    if actual < 0 and key in {"shelter", "banking", "insurance", "lay_low", "passive_decay"}:
        state["mitigation_count"] = int(state["mitigation_count"]) + 1

    entry = {
        "tick": tick,
        "source": key,
        "delta": actual,
        "before": before,
        "after": after,
        "before_tier": before_tier,
        "after_tier": after_tier,
    }
    if reason:
        entry["reason"] = str(reason).strip()
    if source_event:
        entry["source_event"] = str(source_event).strip()
    state["history"].append(entry)
    if len(state["history"]) > MAX_HISTORY:
        del state["history"][:-MAX_HISTORY]

    return {
        "delta": actual,
        "before": before,
        "after": after,
        "before_tier": before_tier,
        "after_tier": after_tier,
        "tier_changed": before_tier != after_tier,
        "source": key,
        "reason": entry.get("reason", ""),
        "source_event": entry.get("source_event", ""),
    }


class RunPressureSystem(System):

    PASSIVE_DECAY_INTERVAL = 24
    PASSIVE_DECAY_DELAY = 44
    WAIT_DECAY_COOLDOWN = 4
    PRESSURE_EVENT_COOLDOWN = 2
    PRESSURE_REPEAT_WINDOW = 10
    PRESSURE_REPEAT_SCALARS = (1.0, 0.75, 0.55, 0.4)
    BANKING_MITIGATION_COOLDOWN = 90
    BANKING_MITIGATION_MIN_AMOUNT = 20

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.last_wait_decay_tick = -10_000
        self.last_pressure_event_tick = {}
        self.pressure_event_streak = {}
        self.last_banking_mitigation_tick = {}
        self.sim.events.subscribe("action_offense", self.on_action_offense)
        self.sim.events.subscribe("property_trespass", self.on_property_trespass)
        self.sim.events.subscribe("property_tamper", self.on_property_tamper)
        self.sim.events.subscribe("incident_authority_reported", self.on_incident_authority_reported)
        self.sim.events.subscribe("npc_warn_property", self.on_npc_warn_property)
        self.sim.events.subscribe("npc_defend_property", self.on_npc_defend_property)
        self.sim.events.subscribe("dialogue_guard_resolution", self.on_dialogue_guard_resolution)
        self.sim.events.subscribe("site_service_used", self.on_site_service_used)
        self.sim.events.subscribe("bank_transaction", self.on_bank_transaction)
        self.sim.events.subscribe("insurance_policy_purchased", self.on_insurance_policy_purchased)
        self.sim.events.subscribe("player_action", self.on_player_action)

    def _event_cooldown_for(self, source):
        source = str(source or "").strip().lower()
        if source in {"offense", "warning", "defense"}:
            return max(2, int(self.PRESSURE_EVENT_COOLDOWN) + 1)
        if source in {"trespass", "tamper"}:
            return max(2, int(self.PRESSURE_EVENT_COOLDOWN) + 2)
        return max(1, int(self.PRESSURE_EVENT_COOLDOWN))

    def _repeat_scalar_for_count(self, count):
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 1
        count = max(1, count)
        scalars = tuple(self.PRESSURE_REPEAT_SCALARS)
        if not scalars:
            return 1.0
        index = min(len(scalars) - 1, count - 1)
        try:
            return float(scalars[index])
        except (TypeError, ValueError):
            return 1.0

    def _emit_pressure(
        self,
        *,
        delta,
        source,
        reason="",
        source_event="",
        category="escalation",
        extra=None,
    ):
        try:
            delta = int(delta)
        except (TypeError, ValueError):
            return None
        if delta == 0:
            return None

        tick = int(getattr(self.sim, "tick", 0))
        if delta > 0:
            key = (str(source or "unknown").strip().lower(), str(reason or "").strip().lower())
            last_tick = int(self.last_pressure_event_tick.get(key, -10_000))
            cooldown = self._event_cooldown_for(key[0])
            if tick - last_tick < cooldown:
                if delta <= 2:
                    delta = max(0, delta - 1)
                else:
                    delta = max(1, int(round(float(delta) * 0.65)))
                if delta <= 0:
                    return None
            self.last_pressure_event_tick[key] = tick

            streak_count = 1
            streak = self.pressure_event_streak.get(key)
            if isinstance(streak, tuple) and len(streak) == 2:
                prev_count = max(1, int(streak[0]))
                prev_tick = int(streak[1])
                if tick - prev_tick <= int(self.PRESSURE_REPEAT_WINDOW):
                    streak_count = prev_count + 1
            self.pressure_event_streak[key] = (streak_count, tick)

            scalar = self._repeat_scalar_for_count(streak_count)
            if scalar < 0.999:
                scaled_delta = int(round(float(delta) * scalar))
                if scaled_delta < delta and scaled_delta > 0:
                    delta = scaled_delta
                elif delta > 1:
                    delta = max(1, delta - 1)
                else:
                    delta = 0
                if delta <= 0:
                    return None

            if len(self.last_pressure_event_tick) > 256:
                stale_before = tick - max(12, int(self.PRESSURE_REPEAT_WINDOW) * 3)
                self.last_pressure_event_tick = {
                    k: int(v)
                    for k, v in self.last_pressure_event_tick.items()
                    if int(v) >= stale_before
                }
            if len(self.pressure_event_streak) > 256:
                stale_before = tick - max(12, int(self.PRESSURE_REPEAT_WINDOW) * 3)
                self.pressure_event_streak = {
                    k: (int(v[0]), int(v[1]))
                    for k, v in self.pressure_event_streak.items()
                    if isinstance(v, tuple) and len(v) == 2 and int(v[1]) >= stale_before
                }

        change = apply_pressure_delta(
            self.sim,
            delta=delta,
            source=source,
            reason=reason,
            source_event=source_event,
        )
        if not change:
            return None

        payload = {
            "eid": self.player_eid,
            "delta": int(change["delta"]),
            "before": int(change["before"]),
            "after": int(change["after"]),
            "tier": str(change["after_tier"]),
            "before_tier": str(change["before_tier"]),
            "source": str(change["source"]),
            "reason": str(change.get("reason", "")),
            "source_event": str(change.get("source_event", "")),
            "category": str(category or "escalation"),
        }
        if isinstance(extra, dict):
            payload.update(extra)

        self.sim.emit(Event("run_pressure_changed", **payload))
        if bool(change.get("tier_changed")):
            self.sim.emit(Event("run_pressure_tier_changed", **payload))
        if int(change["delta"]) < 0 and str(category).strip().lower() in {"mitigation", "recovery"}:
            self.sim.emit(Event("run_pressure_mitigated", **payload))
        return payload

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
        incident["run_pressure_accounted"] = True
        incident["run_pressure_accounted_tick"] = int(getattr(self.sim, "tick", 0))
        return incident

    def _offense_delta(self, offense_score, context):
        offense_score = max(0, int(offense_score))
        context = str(context or "ordinary").strip().lower() or "ordinary"
        if offense_score < 8 and context == "ordinary":
            return 0

        base = max(1, offense_score // 14)
        context_bonus = {
            "ordinary": 0,
            "trespass": 1,
            "tamper": 3,
            "item_theft": 3,
            "contraband_use": 2,
            "wildlife_harassment": 1,
            "wildlife_hunting": 2,
            "unarmed_assault": 2,
            "melee_assault": 3,
            "armed_assault": 4,
            "explosive_discharge": 5,
            "homicide": 7,
            "not_for_sale_attempt": 1,
        }.get(context, 0)

        snapshot = pressure_snapshot(self.sim)
        tier = str(snapshot.get("tier", "low"))
        tier_bonus = 0
        if tier == "high":
            tier_bonus = 1
        return max(0, min(16, base + context_bonus + tier_bonus))

    def _apply_action_offense_pressure(self, data, *, source_event="action_offense"):
        offense_score = int(data.get("offense_score", 0) or 0)
        context = str(data.get("context", "ordinary") or "ordinary").strip().lower()
        action = str(data.get("action", "action") or "action").strip().lower()
        delta = self._offense_delta(offense_score, context=context)
        if delta <= 0:
            return None
        return self._emit_pressure(
            delta=delta,
            source="offense",
            reason=f"{action}/{context}",
            source_event=source_event,
            category="escalation",
            extra={
                "offense_score": int(offense_score),
                "offense_tier": str(data.get("offense_tier", _offense_tier(offense_score))),
                "context": context,
                "x": data.get("x"),
                "y": data.get("y"),
                "z": data.get("z"),
            },
        )

    def _apply_trespass_pressure(self, data, *, source_event="property_trespass"):
        property_id = str(data.get("property_id", "") or "").strip()
        prop = self.sim.properties.get(property_id) if property_id else None
        severity_label = str(data.get("severity_label", "trespass") or "trespass").strip().lower()
        severity_score = max(0, int(data.get("severity_score", 0) or 0))
        ingress_kind = str(data.get("ingress_kind", "") or "").strip().lower()
        aperture_kind = str(data.get("aperture_kind", "") or "").strip().lower()
        ingress_method = str(data.get("ingress_method", "") or "").strip().lower()
        base = 1 if severity_label == "suspicious" else 3
        if severity_label == "serious_trespass":
            base = 6
        delta = base + max(0, severity_score // 24)
        if ingress_kind in {"boundary_breach", "deep_breach"}:
            delta += 2
        elif ingress_kind == "alternate_aperture" and _is_window_aperture(aperture_kind):
            delta += 1
        if ingress_method in {"forced_breach", "deep_breach", "crash_window_entry"}:
            delta += 1
        return self._emit_pressure(
            delta=min(14, delta),
            source="trespass",
            reason=severity_label or "trespass",
            source_event=source_event,
            category="escalation",
            extra={
                "property_id": property_id,
                "property_name": str((prop or {}).get("name", "") or "").strip(),
                "severity_label": severity_label,
                "severity_score": severity_score,
                "ingress_kind": ingress_kind,
                "ingress_method": ingress_method,
                "witnessed": True,
                "obvious_breach": False,
            },
        )

    def _apply_tamper_pressure(self, data, *, source_event="property_tamper"):
        property_id = str(data.get("property_id", "") or "").strip()
        prop = self.sim.properties.get(property_id) if property_id else None
        severity_score = max(0, int(data.get("severity_score", 0) or 0))
        ingress_kind = str(data.get("ingress_kind", "") or "").strip().lower()
        ingress_method = str(data.get("ingress_method", "") or "").strip().lower()
        delta = 7 + max(0, severity_score // 16)
        if ingress_kind in {"boundary_breach", "deep_breach"}:
            delta += 2
        if ingress_method in {"forced_breach", "deep_breach", "crash_window_entry"}:
            delta += 2
        return self._emit_pressure(
            delta=min(20, delta),
            source="tamper",
            reason="property_tamper",
            source_event=source_event,
            category="escalation",
            extra={
                "property_id": property_id,
                "property_name": str((prop or {}).get("name", "") or "").strip(),
                "severity_score": severity_score,
                "ingress_kind": ingress_kind,
                "ingress_method": ingress_method,
                "witnessed": True,
            },
        )

    def _banking_mitigation_key(self, event):
        property_id = str(event.data.get("property_id", "") or "").strip()
        if property_id:
            prop = self.sim.properties.get(property_id)
            if isinstance(prop, dict):
                snapshot = _organization_snapshot(self.sim, prop=prop, ensure=True)
                org_key = str((snapshot or {}).get("organization_key", "") or "").strip().lower()
                if org_key:
                    return f"org:{org_key}"
            return f"prop:{property_id}"

        provider = str(event.data.get("provider_name", "") or "").strip().lower()
        if provider:
            return f"provider:{provider}"
        return "banking"

    def _banking_mitigation_ready(self, event):
        try:
            amount = int(event.data.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0
        if amount < int(self.BANKING_MITIGATION_MIN_AMOUNT):
            return False

        key = self._banking_mitigation_key(event)
        tick = int(getattr(self.sim, "tick", 0))
        last_tick = int(self.last_banking_mitigation_tick.get(key, -10_000))
        if tick - last_tick < int(self.BANKING_MITIGATION_COOLDOWN):
            return False

        self.last_banking_mitigation_tick[key] = tick
        if len(self.last_banking_mitigation_tick) > 256:
            stale_before = tick - (int(self.BANKING_MITIGATION_COOLDOWN) * 4)
            self.last_banking_mitigation_tick = {
                bank_key: int(bank_tick)
                for bank_key, bank_tick in self.last_banking_mitigation_tick.items()
                if int(bank_tick) >= stale_before
            }
        return True

    def on_action_offense(self, event):
        if event_is_vision_only(event):
            return
        if event.data.get("offender_eid") != self.player_eid:
            return
        observation = self._event_accountability(event, offender_eid=self.player_eid)
        if not bool(observation.get("has_accountable_observation")):
            return
        change = self._apply_action_offense_pressure(event.data, source_event="action_offense")
        if change is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))

    def on_property_trespass(self, event):
        if event_is_vision_only(event):
            return
        if event.data.get("offender_eid") != self.player_eid:
            return
        observation = self._event_accountability(event, offender_eid=self.player_eid)
        if not bool(observation.get("has_accountable_observation")):
            return
        change = self._apply_trespass_pressure(event.data, source_event="property_trespass")
        if change is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))

    def on_property_tamper(self, event):
        if event_is_vision_only(event):
            return
        if event.data.get("offender_eid") != self.player_eid:
            return
        observation = self._event_accountability(event, offender_eid=self.player_eid)
        if not bool(observation.get("has_accountable_observation")):
            return
        change = self._apply_tamper_pressure(event.data, source_event="property_tamper")
        if change is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))

    def on_incident_authority_reported(self, event):
        if event_is_vision_only(event):
            return
        incident = incident_record(self.sim, event.data.get("incident_id"))
        if not isinstance(incident, dict):
            return
        if event_is_vision_only(incident):
            return
        if incident.get("primary_actor_eid") != self.player_eid:
            return
        if bool(incident.get("run_pressure_accounted")):
            return
        report_observation = self._event_accountability(event, offender_eid=self.player_eid)
        if not bool(report_observation.get("has_accountable_observation")):
            return
        kind = str(incident.get("kind", "") or "").strip().lower()
        if kind == "property_trespass":
            change = self._apply_trespass_pressure(incident, source_event="incident_authority_reported")
        elif kind == "property_tamper":
            change = self._apply_tamper_pressure(incident, source_event="incident_authority_reported")
        elif kind == "item_stolen":
            change = self._apply_action_offense_pressure(
                {
                    "action": "pickup_item",
                    "context": "item_theft",
                    "offense_score": max(48, int(incident.get("severity", 0) or 0)),
                    "offense_tier": incident.get("offense_tier", _offense_tier(max(48, int(incident.get("severity", 0) or 0)))),
                    "x": incident.get("x"),
                    "y": incident.get("y"),
                    "z": incident.get("z"),
                },
                source_event="incident_authority_reported",
            )
        elif kind == "action_offense":
            change = self._apply_action_offense_pressure(incident, source_event="incident_authority_reported")
        elif kind == "camera_alert":
            change = self._apply_trespass_pressure(incident, source_event="incident_authority_reported")
        else:
            return
        if change is not None:
            self._mark_incident_accounted(incident.get("id"))

    def on_npc_warn_property(self, event):
        if event_is_vision_only(event):
            return
        if event.data.get("offender_eid") != self.player_eid:
            return
        self._emit_pressure(
            delta=1,
            source="warning",
            reason="npc_warn_property",
            source_event="npc_warn_property",
            category="escalation",
        )

    def on_npc_defend_property(self, event):
        if event_is_vision_only(event):
            return
        if event.data.get("offender_eid") != self.player_eid:
            return
        self._emit_pressure(
            delta=1,
            source="defense",
            reason="npc_defend_property",
            source_event="npc_defend_property",
            category="escalation",
        )

    def on_dialogue_guard_resolution(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        delta = int(event.data.get("pressure_delta", 0))
        if delta == 0:
            return
        tactic = str(event.data.get("tactic", "dialogue")).strip().lower() or "dialogue"
        outcome = str(event.data.get("outcome", "wary")).strip().lower() or "wary"
        property_id = str(event.data.get("property_id", "") or "").strip()
        prop = self.sim.properties.get(property_id) if property_id else None
        self._emit_pressure(
            delta=delta,
            source="dialogue",
            reason=f"{tactic}/{outcome}",
            source_event="dialogue_guard_resolution",
            category="mitigation" if delta < 0 else "escalation",
            extra={
                "npc_eid": event.data.get("npc_eid"),
                "property_id": property_id,
                "property_name": str((prop or {}).get("name", "") or "").strip(),
                "tactic": tactic,
                "outcome": outcome,
            },
        )

    def on_site_service_used(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        service = str(event.data.get("service", "")).strip().lower()
        if service != "shelter":
            return
        snapshot = pressure_snapshot(self.sim)
        if int(snapshot.get("attention", 0)) <= 0:
            return
        self._emit_pressure(
            delta=-6,
            source="shelter",
            reason="lay_low",
            source_event="site_service_used",
            category="mitigation",
            extra={
                "service": service,
                "property_id": str(event.data.get("property_id", "") or "").strip(),
                "property_name": str(event.data.get("property_name", "") or "").strip(),
            },
        )

    def on_bank_transaction(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if not self._banking_mitigation_ready(event):
            return
        snapshot = pressure_snapshot(self.sim)
        if int(snapshot.get("attention", 0)) < 12:
            return
        kind = str(event.data.get("kind", "transaction")).strip().lower()
        tier = str(snapshot.get("tier", "low"))
        reduction = 2 if tier == "medium" else 4 if tier == "high" else 1
        self._emit_pressure(
            delta=-reduction,
            source="banking",
            reason=f"{kind}_paperwork",
            source_event="bank_transaction",
            category="mitigation",
            extra={
                "transaction_kind": kind,
                "property_id": str(event.data.get("property_id", "") or "").strip(),
                "provider_name": str(event.data.get("provider_name", "") or "").strip(),
                "account_kind": str(event.data.get("account_kind", "") or "").strip().lower(),
            },
        )

    def on_insurance_policy_purchased(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        snapshot = pressure_snapshot(self.sim)
        if int(snapshot.get("attention", 0)) <= 0:
            return
        tier = str(snapshot.get("tier", "low"))
        reduction = 2 if tier == "low" else 4 if tier == "medium" else 6
        self._emit_pressure(
            delta=-reduction,
            source="insurance",
            reason="policy_cover",
            source_event="insurance_policy_purchased",
            category="mitigation",
            extra={
                "policy_key": str(event.data.get("policy_key", "")),
                "policy_name": str(event.data.get("policy_name", "") or "").strip(),
                "property_id": str(event.data.get("property_id", "") or "").strip(),
                "provider_name": str(event.data.get("provider_name", "") or "").strip(),
            },
        )

    def on_player_action(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        action = str(event.data.get("action", "")).strip().lower()
        if action != "wait":
            return

        if bool(getattr(self.sim, "combat_overlay", {}).get("active")):
            return

        snapshot = pressure_snapshot(self.sim)
        if int(snapshot.get("attention", 0)) <= 0:
            return
        if self.sim.tick - int(self.last_wait_decay_tick) < self.WAIT_DECAY_COOLDOWN:
            return
        self.last_wait_decay_tick = int(self.sim.tick)
        tier = str(snapshot.get("tier", "low")).strip().lower()
        reduction = 1 if tier in {"low", "medium"} else 2
        self._emit_pressure(
            delta=-reduction,
            source="lay_low",
            reason="waited_out",
            source_event="player_action",
            category="recovery",
        )

    def update(self):
        snapshot = pressure_snapshot(self.sim)
        attention = int(snapshot.get("attention", 0))
        if attention <= 0:
            return

        tick = int(getattr(self.sim, "tick", 0))
        last_raise_tick = int(snapshot.get("last_raise_tick", -10_000))
        last_decay_tick = int(snapshot.get("last_decay_tick", -10_000))
        if tick - last_raise_tick < self.PASSIVE_DECAY_DELAY:
            return
        if tick - last_decay_tick < self.PASSIVE_DECAY_INTERVAL:
            return

        reduction = 1
        tier = str(snapshot.get("tier", "low")).strip().lower()
        if tier == "high":
            reduction += 1
        stealth_state = getattr(self.sim, "player_stealth_state", {})
        if isinstance(stealth_state, dict) and bool(stealth_state.get("hidden")):
            reduction += 1
        self._emit_pressure(
            delta=-reduction,
            source="passive_decay",
            reason="time_passed",
            source_event="run_pressure_tick",
            category="recovery",
        )
