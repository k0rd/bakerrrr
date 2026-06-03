from __future__ import annotations

from engine.events import Event
from engine.systems import System


MAX_RESERVE_BONUS = 420
MAX_NETWORK_MARKS = 36
MAX_INTEL_MARKS = 36
MAX_HISTORY = 40


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits

    state = traits.get("objective_progress")
    if not isinstance(state, dict):
        state = {}
        traits["objective_progress"] = state

    state["reserve_bonus_credits"] = max(0, min(MAX_RESERVE_BONUS, _safe_int(state.get("reserve_bonus_credits"), default=0)))
    state["network_marks"] = max(0, min(MAX_NETWORK_MARKS, _safe_int(state.get("network_marks"), default=0)))
    state["intel_marks"] = max(0, min(MAX_INTEL_MARKS, _safe_int(state.get("intel_marks"), default=0)))

    channel_counts = state.get("channel_counts")
    if not isinstance(channel_counts, dict):
        channel_counts = {}
        state["channel_counts"] = channel_counts

    history = state.get("history")
    if not isinstance(history, list):
        history = []
        state["history"] = history
    if len(history) > MAX_HISTORY:
        del history[:-MAX_HISTORY]
    return state


def _objective_id(sim):
    traits = getattr(sim, "world_traits", {})
    if not isinstance(traits, dict):
        return ""
    objective = traits.get("run_objective", {})
    if not isinstance(objective, dict):
        return ""
    return str(objective.get("id", "")).strip().lower()


def award_objective_progress(
    sim,
    *,
    channel,
    reserve_bonus_credits=0,
    network_marks=0,
    intel_marks=0,
    reason="",
    source_event="",
):
    state = _state(sim)
    reserve_delta = max(0, _safe_int(reserve_bonus_credits, default=0))
    network_delta = max(0, _safe_int(network_marks, default=0))
    intel_delta = max(0, _safe_int(intel_marks, default=0))
    if reserve_delta <= 0 and network_delta <= 0 and intel_delta <= 0:
        return None

    before_reserve = int(state["reserve_bonus_credits"])
    before_network = int(state["network_marks"])
    before_intel = int(state["intel_marks"])

    state["reserve_bonus_credits"] = max(0, min(MAX_RESERVE_BONUS, before_reserve + reserve_delta))
    state["network_marks"] = max(0, min(MAX_NETWORK_MARKS, before_network + network_delta))
    state["intel_marks"] = max(0, min(MAX_INTEL_MARKS, before_intel + intel_delta))

    actual = {
        "reserve_bonus_credits": int(state["reserve_bonus_credits"] - before_reserve),
        "network_marks": int(state["network_marks"] - before_network),
        "intel_marks": int(state["intel_marks"] - before_intel),
    }
    if (
        actual["reserve_bonus_credits"] <= 0
        and actual["network_marks"] <= 0
        and actual["intel_marks"] <= 0
    ):
        return None

    key = str(channel or "").strip().lower() or "unknown"
    counts = state["channel_counts"]
    counts[key] = int(max(0, _safe_int(counts.get(key), default=0))) + 1

    entry = {
        "tick": _safe_int(getattr(sim, "tick", 0), default=0),
        "channel": key,
        "objective_id": _objective_id(sim),
        "reserve_bonus_credits": actual["reserve_bonus_credits"],
        "network_marks": actual["network_marks"],
        "intel_marks": actual["intel_marks"],
    }
    if reason:
        entry["reason"] = str(reason).strip()
    if source_event:
        entry["source_event"] = str(source_event).strip()
    state["history"].append(entry)
    if len(state["history"]) > MAX_HISTORY:
        del state["history"][:-MAX_HISTORY]

    from game.run_objectives import reveal_run_objective

    reveal_run_objective(sim, source=f"objective_progress:{key}")

    totals = {
        "reserve_bonus_credits": int(state["reserve_bonus_credits"]),
        "network_marks": int(state["network_marks"]),
        "intel_marks": int(state["intel_marks"]),
    }
    return {
        "channel": key,
        "objective_id": _objective_id(sim),
        "delta": actual,
        "totals": totals,
        "reason": entry.get("reason", ""),
        "source_event": entry.get("source_event", ""),
    }


def objective_metric_bonuses(sim, objective_id):
    state = _state(sim)
    objective_id = str(objective_id or "").strip().lower()
    reserve = int(state["reserve_bonus_credits"])
    network = int(state["network_marks"])
    intel = int(state["intel_marks"])

    bonuses = {
        "reserve_credits": 0,
        "contact_count": 0,
        "intel_leads": 0,
    }
    if objective_id == "debt_exit":
        bonuses["reserve_credits"] = reserve
    elif objective_id == "networked_extraction":
        bonuses["contact_count"] = network // 2
        bonuses["reserve_credits"] = reserve // 2
    elif objective_id == "high_value_retrieval":
        bonuses["intel_leads"] = intel // 2
    bonuses["raw"] = {
        "reserve_bonus_credits": reserve,
        "network_marks": network,
        "intel_marks": intel,
    }
    return bonuses


def objective_progress_snapshot(sim):
    state = _state(sim)
    return {
        "reserve_bonus_credits": int(state["reserve_bonus_credits"]),
        "network_marks": int(state["network_marks"]),
        "intel_marks": int(state["intel_marks"]),
        "channel_counts": dict(state.get("channel_counts", {})),
        "history": [dict(entry) for entry in state.get("history", ()) if isinstance(entry, dict)],
    }


def objective_progress_recent_history(sim, limit=5):
    limit = max(0, _safe_int(limit, default=5))
    history = objective_progress_snapshot(sim).get("history", [])
    if limit <= 0:
        return []
    return list(reversed(history[-limit:]))


def objective_progress_effects(objective_id, delta):
    objective_id = str(objective_id or "").strip().lower()
    payload = dict(delta or {}) if isinstance(delta, dict) else {}
    reserve = max(0, _safe_int(payload.get("reserve_bonus_credits"), default=0))
    network = max(0, _safe_int(payload.get("network_marks"), default=0))
    intel = max(0, _safe_int(payload.get("intel_marks"), default=0))
    effects = {
        "reserve_credits": 0,
        "contact_count": 0,
        "intel_leads": 0,
    }
    if objective_id == "debt_exit":
        effects["reserve_credits"] = reserve
    elif objective_id == "networked_extraction":
        effects["reserve_credits"] = reserve // 2
        effects["contact_count"] = network // 2
    elif objective_id == "high_value_retrieval":
        effects["intel_leads"] = intel // 2
    return effects


def objective_progress_explain_delta(objective_id, delta):
    objective_id = str(objective_id or "").strip().lower()
    payload = dict(delta or {}) if isinstance(delta, dict) else {}
    reserve = max(0, _safe_int(payload.get("reserve_bonus_credits"), default=0))
    network = max(0, _safe_int(payload.get("network_marks"), default=0))
    intel = max(0, _safe_int(payload.get("intel_marks"), default=0))
    effects = objective_progress_effects(objective_id, payload)
    bits = []

    if objective_id == "debt_exit":
        if reserve > 0:
            bits.append(f"reserve +{effects['reserve_credits']}")
        return bits

    if objective_id == "networked_extraction":
        if network > 0:
            contacts = effects["contact_count"]
            if contacts > 0:
                bits.append(f"contacts +{contacts} from network marks +{network}")
            else:
                bits.append(f"network marks +{network} (2 = +1 contact)")
        if reserve > 0:
            reserve_effect = effects["reserve_credits"]
            if reserve_effect > 0:
                bits.append(f"reserve +{reserve_effect} from support +{reserve}")
            else:
                bits.append(f"reserve support +{reserve} (2 = +1 reserve)")
        return bits

    if objective_id == "high_value_retrieval":
        if intel > 0:
            leads = effects["intel_leads"]
            if leads > 0:
                bits.append(f"leads +{leads} from intel marks +{intel}")
            else:
                bits.append(f"intel marks +{intel} (2 = +1 lead)")
        return bits

    return bits


class ObjectiveProgressSystem(System):

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.sim.events.subscribe("npc_interacted", self.on_npc_interacted)
        self.sim.events.subscribe("dialogue_opportunity_hint", self.on_dialogue_opportunity_hint)
        self.sim.events.subscribe("eavesdrop_opportunity_hint", self.on_eavesdrop_opportunity_hint)
        self.sim.events.subscribe("contact_learned", self.on_contact_learned)
        self.sim.events.subscribe("trade_bought", self.on_trade_bought)
        self.sim.events.subscribe("trade_sold", self.on_trade_sold)
        self.sim.events.subscribe("site_service_used", self.on_site_service_used)
        self.sim.events.subscribe("site_intel_report", self.on_site_intel_report)
        self.sim.events.subscribe("overworld_discovery_found", self.on_overworld_discovery_found)
        self.sim.events.subscribe("opportunity_completed", self.on_opportunity_completed)

    def _emit_award(
        self,
        *,
        channel,
        reserve_bonus_credits=0,
        network_marks=0,
        intel_marks=0,
        reason="",
        source_event="",
    ):
        awarded = award_objective_progress(
            self.sim,
            channel=channel,
            reserve_bonus_credits=reserve_bonus_credits,
            network_marks=network_marks,
            intel_marks=intel_marks,
            reason=reason,
            source_event=source_event,
        )
        if not awarded:
            return
        self.sim.emit(Event(
            "objective_progress_awarded",
            eid=self.player_eid,
            channel=str(awarded.get("channel", channel)),
            objective_id=str(awarded.get("objective_id", "")).strip(),
            delta=dict(awarded.get("delta", {})),
            totals=dict(awarded.get("totals", {})),
            reason=str(awarded.get("reason", reason)).strip(),
            source_event=str(awarded.get("source_event", source_event)).strip(),
        ))

    def on_npc_interacted(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if bool(event.data.get("guarded")):
            return
        self._emit_award(
            channel="talk",
            network_marks=1,
            reason="conversation",
            source_event="npc_interacted",
        )

    def on_contact_learned(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self._emit_award(
            channel="contact",
            network_marks=2,
            intel_marks=1,
            reason="new_contact",
            source_event="contact_learned",
        )

    def on_dialogue_opportunity_hint(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        detail = str(event.data.get("detail", "")).strip()
        self._emit_award(
            channel="talk",
            intel_marks=2 if detail else 1,
            network_marks=1,
            reason="dialogue_opportunity_hint",
            source_event="dialogue_opportunity_hint",
        )

    def on_eavesdrop_opportunity_hint(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        detail = str(event.data.get("detail", "")).strip()
        self._emit_award(
            channel="talk",
            intel_marks=2 if detail else 1,
            network_marks=0,
            reason="eavesdrop_opportunity_hint",
            source_event="eavesdrop_opportunity_hint",
        )

    def on_trade_bought(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        try:
            price = int(event.data.get("price", 0))
        except (TypeError, ValueError):
            price = 0
        network_marks = 1 if price >= 20 else 0
        if network_marks <= 0:
            return
        self._emit_award(
            channel="trade",
            network_marks=network_marks,
            reason="logistics_purchase",
            source_event="trade_bought",
        )

    def on_trade_sold(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        try:
            price = int(event.data.get("price", 0))
        except (TypeError, ValueError):
            price = 0
        reserve_bonus = max(0, min(18, price // 3))
        if reserve_bonus <= 0:
            return
        self._emit_award(
            channel="trade",
            reserve_bonus_credits=reserve_bonus,
            reason="sale_margin",
            source_event="trade_sold",
        )

    def on_site_service_used(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        service = str(event.data.get("service", "")).strip().lower()
        if service == "shelter":
            self._emit_award(
                channel="site_service",
                network_marks=1,
                reason="shelter_stop",
                source_event="site_service_used",
            )
            return
        if service == "intel":
            self._emit_award(
                channel="site_service",
                intel_marks=2,
                reason="site_intel",
                source_event="site_service_used",
            )

    def on_site_intel_report(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        lines = list(event.data.get("lines", ()) or ())
        base_intel_marks = max(1, min(3, (len(lines) // 2) + 1))
        detail_level = max(0, _safe_int(event.data.get("detail_level"), default=0))
        intel_marks = min(3, base_intel_marks + (1 if detail_level >= 1 else 0))
        self._emit_award(
            channel="site_intel",
            intel_marks=intel_marks,
            reason="intel_report",
            source_event="site_intel_report",
        )

    def on_overworld_discovery_found(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        try:
            credits_gain = int(event.data.get("credits_gain", 0))
        except (TypeError, ValueError):
            credits_gain = 0
        reserve_bonus = max(0, min(16, credits_gain // 2))
        kind = str(event.data.get("kind", "")).strip().lower()
        intel_lines = list(event.data.get("intel_lines", ()) or ())
        intel_marks = 0
        if intel_lines:
            intel_marks = max(intel_marks, 1)
        if kind == "landmark":
            intel_marks = max(intel_marks, 2)
        self._emit_award(
            channel="discovery",
            reserve_bonus_credits=reserve_bonus,
            intel_marks=intel_marks,
            reason=kind or "discovery",
            source_event="overworld_discovery_found",
        )

    def on_opportunity_completed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reward = dict(event.data.get("reward", {}) or {})
        try:
            credits = int(reward.get("credits", 0))
        except (TypeError, ValueError):
            credits = 0
        try:
            standing = int(reward.get("standing", 0))
        except (TypeError, ValueError):
            standing = 0
        try:
            intel = int(reward.get("intel", 0))
        except (TypeError, ValueError):
            intel = 0
        reserve_bonus = max(0, min(18, credits // 2))
        network_marks = max(0, min(2, standing))
        intel_marks = max(0, min(3, intel))
        self._emit_award(
            channel="opportunity",
            reserve_bonus_credits=reserve_bonus,
            network_marks=network_marks,
            intel_marks=intel_marks,
            reason="opportunity_completion",
            source_event="opportunity_completed",
        )
