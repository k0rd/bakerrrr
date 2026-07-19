"""Player sleep pressure, chemical wake-time, and forced recovery."""

from __future__ import annotations

import math

from engine.events import Event
from engine.systems import System
from game.components import NPCNeeds, Position, Vitality


MAX_WAKEFULNESS = 100.0
AWAKE_HOURS_TO_COLLAPSE = 32.0
SLEEP_HOURS_TO_FULL = 8.0
MAX_CHEMICAL_WAKE_HOURS = 6.0
TIRED_THRESHOLD = 50.0
EXHAUSTED_THRESHOLD = 35.0
HALLUCINATION_THRESHOLD = 25.0
FORCED_WAKE_THRESHOLD = 45.0


def _float_or(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value, lo=0.0, hi=MAX_WAKEFULNESS):
    return max(float(lo), min(float(hi), _float_or(value, lo)))


def ensure_sleep_needs(needs):
    """Migrate old saved ``NPCNeeds`` objects in place."""

    if needs is None:
        return None
    if not hasattr(needs, "wakefulness"):
        needs.wakefulness = float(MAX_WAKEFULNESS)
    if not hasattr(needs, "chemical_wake_reserve"):
        needs.chemical_wake_reserve = 0.0
    needs.wakefulness = _clamp(getattr(needs, "wakefulness", MAX_WAKEFULNESS))
    reserve_ceiling = float(MAX_CHEMICAL_WAKE_HOURS) * wakefulness_points_per_awake_hour()
    needs.chemical_wake_reserve = max(
        0.0,
        min(
            reserve_ceiling,
            _float_or(getattr(needs, "chemical_wake_reserve", 0.0), 0.0),
        ),
    )
    return needs


def wakefulness_points_per_awake_hour():
    return float(MAX_WAKEFULNESS) / float(AWAKE_HOURS_TO_COLLAPSE)


def chemical_wake_reserve_hours(needs):
    needs = ensure_sleep_needs(needs)
    if needs is None:
        return 0.0
    return max(0.0, float(needs.chemical_wake_reserve) / wakefulness_points_per_awake_hour())


def add_chemical_wake_reserve(needs, hours):
    """Add finite masked wake-time without paying down actual sleep debt."""

    needs = ensure_sleep_needs(needs)
    if needs is None:
        return 0.0
    requested_points = max(0.0, _float_or(hours, 0.0)) * wakefulness_points_per_awake_hour()
    ceiling = float(MAX_CHEMICAL_WAKE_HOURS) * wakefulness_points_per_awake_hour()
    before = float(needs.chemical_wake_reserve)
    needs.chemical_wake_reserve = min(ceiling, before + requested_points)
    return max(0.0, (float(needs.chemical_wake_reserve) - before) / wakefulness_points_per_awake_hour())


def restore_wakefulness(needs, points):
    return max(0.0, modify_wakefulness(needs, max(0.0, _float_or(points, 0.0))))


def modify_wakefulness(needs, points):
    """Change actual wakefulness, bypassing the masking chemical reserve."""

    needs = ensure_sleep_needs(needs)
    if needs is None:
        return 0.0
    before = float(needs.wakefulness)
    needs.wakefulness = _clamp(before + _float_or(points, 0.0))
    return float(needs.wakefulness) - before


def wakefulness_stage(value):
    value = _clamp(value)
    if value <= 0.0:
        return "collapsed"
    if value < HALLUCINATION_THRESHOLD:
        return "hallucinating"
    if value < EXHAUSTED_THRESHOLD:
        return "exhausted"
    if value < TIRED_THRESHOLD:
        return "tired"
    return "alert"


def sleep_deprivation_hallucination_intensity(needs):
    needs = ensure_sleep_needs(needs)
    if needs is None:
        return 0.0
    wakefulness = float(needs.wakefulness)
    if wakefulness >= HALLUCINATION_THRESHOLD:
        return 0.0
    depth = (HALLUCINATION_THRESHOLD - wakefulness) / max(1.0, HALLUCINATION_THRESHOLD)
    return max(0.0, min(1.25, depth * 1.25))


def _ticks_per_hour(sim):
    world_traits = getattr(sim, "world_traits", {})
    clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
    try:
        value = int(clock.get("ticks_per_hour", 600))
    except (TypeError, ValueError, AttributeError):
        value = 600
    return max(60, value)


def _sleep_pressure_state(sim):
    state = getattr(sim, "sleep_pressure_state", None)
    if not isinstance(state, dict):
        state = {}
        sim.sleep_pressure_state = state
    state.setdefault("last_tick_by_eid", {})
    state.setdefault("stage_by_eid", {})
    return state


def _recovering_kind(sim, eid):
    vitality = sim.ecs.get(Vitality).get(eid)
    if vitality and bool(getattr(vitality, "downed", False)):
        return "unconscious"
    live = getattr(sim, "live_timeskip", None)
    if not isinstance(live, dict) or not bool(live.get("active")):
        return ""
    service = str(live.get("service", "") or "").strip().lower()
    kind = str(live.get("kind", "") or "").strip().lower()
    if service in {"rest", "shelter", "drug_blackout", "exhaustion_sleep"}:
        return service
    if kind in {"drug_blackout", "exhaustion_sleep"}:
        return kind
    return ""


def begin_exhaustion_sleep(sim, eid):
    live = getattr(sim, "live_timeskip", None)
    if isinstance(live, dict) and bool(live.get("active")):
        return False
    if not isinstance(live, dict):
        live = {}
        sim.live_timeskip = live

    needs = ensure_sleep_needs(sim.ecs.get(NPCNeeds).get(eid))
    if needs is None:
        return False
    ticks_per_hour = _ticks_per_hour(sim)
    recovery_per_tick = float(MAX_WAKEFULNESS) / float(SLEEP_HOURS_TO_FULL * ticks_per_hour)
    points_needed = max(0.0, float(FORCED_WAKE_THRESHOLD) - float(needs.wakefulness))
    # The collapse tick itself was still awake.  Add one tick so the following
    # headless updates deliver the full protected recovery threshold.
    recovery_ticks = max(1, int(math.ceil(points_needed / max(1e-9, recovery_per_tick))) + 1)
    started_tick = int(getattr(sim, "tick", 0) or 0)
    pos = sim.ecs.get(Position).get(eid)
    live.clear()
    live.update({
        "active": True,
        "owner": "sleep_pressure",
        "kind": "exhaustion_sleep",
        "service": "exhaustion_sleep",
        "property_id": None,
        "property_name": "where you fell",
        "title": "Exhaustion takes over...",
        "footer": "Danger will not wake you before your body is ready.",
        "started_tick": started_tick,
        "target_end_tick": started_tick + recovery_ticks,
        "elapsed_ticks": 0,
        "total_ticks": recovery_ticks,
        "player_anchor": (int(pos.x), int(pos.y), int(pos.z)) if pos is not None else None,
        "recovery_plan": {"pulse_index": 0, "pulses": ()},
        "recovery_applied": {"hp_gain": 0, "energy_gain": 0, "safety_gain": 0, "social_gain": 0},
        "planned_recovery": {"hp_gain": 0, "energy_gain": 0, "safety_gain": 0, "social_gain": 0},
        "completed": False,
        "interrupted": False,
        "interruption_reason": "",
        "wake_cause": "",
        "wake_source_eid": None,
        "wake_x": None,
        "wake_y": None,
        "wake_z": None,
        "credits_spent": 0,
        "cooldown_ticks": 0,
        "well_rested_ticks": 0,
        "well_rested_granted": False,
        "practice_note": "",
        "source_status": "",
        "mandatory_rest": True,
        "result_pending": False,
    })
    sim.emit(Event(
        "exhaustion_sleep_started",
        eid=eid,
        wakefulness=round(float(needs.wakefulness), 3),
        recovery_threshold=float(FORCED_WAKE_THRESHOLD),
        duration_ticks=recovery_ticks,
    ))
    return True


class SleepPressureSystem(System):
    """O(1) player-only sleep pressure integrated with live time-skips."""

    def __init__(self, sim, player_eid=None):
        super().__init__(sim)
        self.player_eid = player_eid

    def _elapsed_ticks(self, eid):
        state = _sleep_pressure_state(self.sim)
        ticks = state["last_tick_by_eid"]
        key = str(int(eid))
        current = int(getattr(self.sim, "tick", 0) or 0)
        try:
            last = int(ticks.get(key, current - 1))
        except (TypeError, ValueError):
            last = current - 1
        ticks[key] = current
        return max(0, current - last)

    def _sync_stage(self, eid, needs, *, recovering=False):
        state = _sleep_pressure_state(self.sim)
        stages = state["stage_by_eid"]
        key = str(int(eid))
        current = wakefulness_stage(needs.wakefulness)
        previous = str(stages.get(key, "alert") or "alert")
        stages[key] = current
        if current == previous:
            return
        self.sim.emit(Event(
            "sleep_deprivation_stage_changed",
            eid=eid,
            previous_stage=previous,
            stage=current,
            wakefulness=round(float(needs.wakefulness), 3),
            recovering=bool(recovering),
        ))

    def update(self):
        eid = self.player_eid if self.player_eid is not None else getattr(self.sim, "player_eid", None)
        if eid is None:
            return
        needs = ensure_sleep_needs(self.sim.ecs.get(NPCNeeds).get(eid))
        if needs is None:
            return
        elapsed = self._elapsed_ticks(eid)
        if elapsed <= 0:
            return

        ticks_per_hour = _ticks_per_hour(self.sim)
        awake_drain = (float(MAX_WAKEFULNESS) / float(AWAKE_HOURS_TO_COLLAPSE * ticks_per_hour)) * elapsed
        recovering_kind = _recovering_kind(self.sim, eid)
        if recovering_kind:
            # Chemical wake-time is time-limited even if the actor sleeps
            # through it; it never survives a long rest as free future credit.
            needs.chemical_wake_reserve = max(0.0, float(needs.chemical_wake_reserve) - awake_drain)
            sleep_gain = (float(MAX_WAKEFULNESS) / float(SLEEP_HOURS_TO_FULL * ticks_per_hour)) * elapsed
            restore_wakefulness(needs, sleep_gain)
            self._sync_stage(eid, needs, recovering=True)
            return

        remaining_drain = awake_drain
        if needs.chemical_wake_reserve > 0.0:
            covered = min(float(needs.chemical_wake_reserve), remaining_drain)
            needs.chemical_wake_reserve = max(0.0, float(needs.chemical_wake_reserve) - covered)
            remaining_drain -= covered
        if remaining_drain > 0.0:
            needs.wakefulness = _clamp(float(needs.wakefulness) - remaining_drain)
        self._sync_stage(eid, needs, recovering=False)

        vitality = self.sim.ecs.get(Vitality).get(eid)
        if float(needs.wakefulness) <= 0.0 and not (vitality and bool(getattr(vitality, "downed", False))):
            begin_exhaustion_sleep(self.sim, eid)
