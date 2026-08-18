"""Status-driven altered perception, control, and pacing helpers."""

import random

from engine.events import Event
from engine.systems import System
from game.components import NPCNeeds, Position, StatusEffects, Vitality
from game.system_support.combat_pacing_runtime import _combat_turn_pacing_active
from game.system_support.sleep_pressure_runtime import sleep_deprivation_hallucination_intensity
from game.system_support.status_runtime import _status_modifier_total, _status_multiplier


SPEED_BONUS_THRESHOLD = 1.10
_DIRECTIONS = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)


def _int_or_default(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _float_or_default(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp01(value):
    return max(0.0, min(1.0, _float_or_default(value, 0.0)))


def altered_state(sim):
    state = getattr(sim, "altered_state", None)
    if not isinstance(state, dict):
        state = {}
        sim.altered_state = state
    state.setdefault("bonus_moves", {})
    state.setdefault("counters", {})
    state.setdefault("control_lapses", {})
    state.setdefault("control_lapse_cooldowns", {})
    state.setdefault("blackout_cooldowns", {})
    return state


def _status_value(sim, eid, key, default=0.0):
    return _float_or_default(_status_modifier_total(sim, eid, key, default=default), default)


def _actor_speed(sim, eid):
    return _status_multiplier(sim, eid, "move_speed_mult", base=1.0, minimum=0.2, maximum=3.0)


def _combat_local_bonus_allowed(sim, eid):
    if eid is None:
        return False
    if not _combat_turn_pacing_active(sim):
        return False
    if control_lapse_active(sim, eid):
        return False
    return _actor_speed(sim, eid) >= SPEED_BONUS_THRESHOLD


def bonus_move_available(sim, eid):
    if not _combat_local_bonus_allowed(sim, eid):
        return False
    state = altered_state(sim)
    rec = state["bonus_moves"].get(str(int(eid)))
    tick = int(getattr(sim, "tick", 0))
    rec_tick = _int_or_default(rec.get("tick", -1), -1) if isinstance(rec, dict) else -1
    return not (isinstance(rec, dict) and rec_tick == tick and bool(rec.get("used")))


def spend_bonus_move(sim, eid, *, source="move"):
    if not bonus_move_available(sim, eid):
        return False
    tick = int(getattr(sim, "tick", 0))
    altered_state(sim)["bonus_moves"][str(int(eid))] = {
        "tick": tick,
        "used": True,
        "source": str(source or "move"),
    }
    sim.emit(Event(
        "bonus_move_used",
        eid=eid,
        tick=tick,
        source=str(source or "move"),
        speed=round(_actor_speed(sim, eid), 3),
    ))
    return True


def _next_counter(sim, eid, key):
    counters = altered_state(sim)["counters"]
    bucket_key = f"{int(eid)}:{key}"
    value = int(counters.get(bucket_key, 0) or 0) + 1
    counters[bucket_key] = value
    return value


def _rng(sim, eid, key, *parts):
    seed = getattr(sim, "seed", 0)
    tick = int(getattr(sim, "tick", 0))
    token = ":".join(str(part) for part in (seed, tick, eid, key) + tuple(parts))
    return random.Random(token)


def maybe_misdirect_move(sim, eid, dx, dy):
    dx = max(-1, min(1, _int_or_default(dx, 0)))
    dy = max(-1, min(1, _int_or_default(dy, 0)))
    if dx == 0 and dy == 0:
        return dx, dy, False
    chance = _clamp01(_status_value(sim, eid, "movement_misdirect_chance", 0.0))
    if chance <= 0.0:
        return dx, dy, False
    counter = _next_counter(sim, eid, "movement_misdirect")
    rng = _rng(sim, eid, "movement_misdirect", counter, dx, dy)
    if rng.random() >= chance:
        return dx, dy, False
    choices = [direction for direction in _DIRECTIONS if direction != (dx, dy)]
    ndx, ndy = choices[rng.randrange(len(choices))]
    sim.emit(Event(
        "movement_misdirected",
        eid=eid,
        from_dx=dx,
        from_dy=dy,
        to_dx=ndx,
        to_dy=ndy,
        chance=round(chance, 3),
    ))
    return ndx, ndy, True


def control_lapse_active(sim, eid):
    if eid is None:
        return False
    lapses = altered_state(sim)["control_lapses"]
    rec = lapses.get(str(int(eid)))
    if not isinstance(rec, dict):
        return False
    until_tick = int(rec.get("until_tick", 0) or 0)
    if until_tick <= int(getattr(sim, "tick", 0)):
        lapses.pop(str(int(eid)), None)
        return False
    return True


def _start_control_lapse(sim, eid, *, duration, source_status=""):
    duration = max(1, _int_or_default(duration, 1))
    tick = int(getattr(sim, "tick", 0))
    until_tick = tick + duration
    state = altered_state(sim)
    key = str(int(eid))
    state["control_lapses"][key] = {
        "started_tick": tick,
        "until_tick": until_tick,
        "source_status": str(source_status or ""),
    }
    state["control_lapse_cooldowns"][key] = until_tick + max(1, duration)
    sim.emit(Event(
        "control_lapse_started",
        eid=eid,
        duration=duration,
        until_tick=until_tick,
        source_status=str(source_status or ""),
    ))
    return True


def _active_status_name_with_modifier(sim, eid, key):
    effects = sim.ecs.get(StatusEffects).get(eid)
    if not effects:
        return ""
    for status, rec in dict(getattr(effects, "active", {}) or {}).items():
        modifiers = rec.get("modifiers", {}) if isinstance(rec, dict) else {}
        if isinstance(modifiers, dict) and key in modifiers:
            return str(status)
    return ""


def maybe_start_control_lapse(sim, eid):
    if control_lapse_active(sim, eid):
        return False
    chance = _clamp01(_status_value(sim, eid, "control_lapse_chance", 0.0))
    if chance <= 0.0:
        return False
    key = str(int(eid))
    cooldown = int(altered_state(sim)["control_lapse_cooldowns"].get(key, 0) or 0)
    if int(getattr(sim, "tick", 0)) < cooldown:
        return False
    counter = _next_counter(sim, eid, "control_lapse")
    if _rng(sim, eid, "control_lapse", counter).random() >= chance:
        return False
    duration = max(1, _int_or_default(round(_status_value(sim, eid, "control_lapse_ticks", 1.0)), 1))
    source_status = _active_status_name_with_modifier(sim, eid, "control_lapse_chance")
    return _start_control_lapse(sim, eid, duration=duration, source_status=source_status)


def _blackout_duration(sim, eid):
    min_ticks = max(1, _int_or_default(round(_status_value(sim, eid, "blackout_min_ticks", 1.0)), 1))
    max_ticks = max(min_ticks, _int_or_default(round(_status_value(sim, eid, "blackout_max_ticks", min_ticks)), min_ticks))
    if max_ticks <= min_ticks:
        return min_ticks
    counter = _next_counter(sim, eid, "blackout_duration")
    return random.Random(f"{getattr(sim, 'seed', 0)}:{int(getattr(sim, 'tick', 0))}:{eid}:blackout-duration:{counter}").randint(min_ticks, max_ticks)


def begin_drug_blackout(sim, eid, *, duration_ticks, source_status=""):
    duration_ticks = max(1, int(duration_ticks))
    pos = sim.ecs.get(Position).get(eid)
    started_tick = int(getattr(sim, "tick", 0))
    state = getattr(sim, "live_timeskip", None)
    if not isinstance(state, dict):
        state = {}
        sim.live_timeskip = state
    state.clear()
    state.update({
        "active": True,
        "owner": "altered_state",
        "kind": "drug_blackout",
        "service": "drug_blackout",
        "property_id": None,
        "property_name": "time slips",
        "title": "Nodding off...",
        "footer": "The city keeps moving without you.",
        "started_tick": started_tick,
        "target_end_tick": started_tick + duration_ticks,
        "elapsed_ticks": 0,
        "total_ticks": duration_ticks,
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
        "result_pending": False,
        "source_status": str(source_status or ""),
    })
    sim.emit(Event(
        "drug_blackout_started",
        eid=eid,
        source_status=str(source_status or ""),
        duration_ticks=duration_ticks,
        started_tick=started_tick,
        target_end_tick=started_tick + duration_ticks,
    ))
    return state


def maybe_start_drug_blackout(sim, eid):
    live_timeskip = getattr(sim, "live_timeskip", None)
    if isinstance(live_timeskip, dict) and bool(live_timeskip.get("active")):
        return False
    chance = _clamp01(_status_value(sim, eid, "blackout_chance", 0.0))
    if chance <= 0.0:
        return False
    key = str(int(eid))
    state = altered_state(sim)
    cooldown = int(state["blackout_cooldowns"].get(key, 0) or 0)
    if int(getattr(sim, "tick", 0)) < cooldown:
        return False
    counter = _next_counter(sim, eid, "blackout")
    if _rng(sim, eid, "blackout", counter).random() >= chance:
        return False
    duration = _blackout_duration(sim, eid)
    cooldown_ticks = max(1, _int_or_default(round(_status_value(sim, eid, "blackout_cooldown_ticks", duration)), duration))
    state["blackout_cooldowns"][key] = int(getattr(sim, "tick", 0)) + duration + cooldown_ticks
    source_status = _active_status_name_with_modifier(sim, eid, "blackout_chance")
    begin_drug_blackout(sim, eid, duration_ticks=duration, source_status=source_status)
    return True


def hallucination_intensity(sim, eid):
    status_intensity = max(0.0, _status_value(sim, eid, "hallucination_intensity", 0.0))
    needs = sim.ecs.get(NPCNeeds).get(eid)
    deprivation_intensity = sleep_deprivation_hallucination_intensity(needs)
    return max(0.0, min(2.0, status_intensity + deprivation_intensity))


def hallucination_read_chance(sim, eid):
    explicit = _status_value(sim, eid, "hallucination_read_chance", -1.0)
    if explicit >= 0.0:
        return _clamp01(explicit)
    return _clamp01(hallucination_intensity(sim, eid) * 0.35)


def _hallucination_roll(sim, eid, channel, x, y, z, chance):
    if chance <= 0.0:
        return None
    rng = _rng(sim, eid, channel, int(x), int(y), int(z))
    if rng.random() >= chance:
        return None
    return rng


_TILE_READS = (
    "wet pavement",
    "breathing wall",
    "soft-lit floor",
    "impossible stair",
    "shivering doorway",
    "painted shadow",
)

_ITEM_READS = (
    "folded packet",
    "bright wrapper",
    "little metal thing",
    "loose card",
    "sealed vial",
    "scrap bundle",
)

_CREATURE_READS = (
    "stranger",
    "watcher",
    "familiar face",
    "guard-shaped figure",
    "person in the corner",
    "moving silhouette",
)


def hallucinated_tile_label(sim, eid, x, y, z, base_text):
    rng = _hallucination_roll(sim, eid, "hallucination_tile_read", x, y, z, hallucination_read_chance(sim, eid))
    if rng is None:
        return str(base_text or "")
    return _TILE_READS[rng.randrange(len(_TILE_READS))]


def hallucinated_item_label(sim, eid, x, y, z, index, base_text):
    rng = _hallucination_roll(sim, eid, f"hallucination_item_read:{index}", x, y, z, hallucination_read_chance(sim, eid))
    if rng is None:
        return str(base_text or "")
    return _ITEM_READS[rng.randrange(len(_ITEM_READS))]


def hallucinated_entity_label(sim, eid, target_eid, x, y, z, base_text):
    if target_eid == eid:
        return str(base_text or "")
    rng = _hallucination_roll(sim, eid, f"hallucination_entity_read:{target_eid}", x, y, z, hallucination_read_chance(sim, eid))
    if rng is None:
        return str(base_text or "")
    return _CREATURE_READS[rng.randrange(len(_CREATURE_READS))]


def hallucinated_tile_visual(sim, eid, x, y, z, *, intensity=None):
    if intensity is None:
        intensity = hallucination_intensity(sim, eid)
    if intensity <= 0.0:
        return None
    chance = _clamp01(0.08 + (float(intensity) * 0.10))
    rng = _hallucination_roll(sim, eid, "hallucination_tile_visual", x, y, z, chance)
    if rng is None:
        return None
    glyphs = ("~", ";", ":", "^", "?")
    colors = ("objective", "projectile", "human", "player")
    return {
        "glyph": glyphs[rng.randrange(len(glyphs))],
        "color": colors[rng.randrange(len(colors))],
        "semantic_id": "hallucinated_tile",
    }


class AlteredStateSystem(System):
    def __init__(self, sim, player_eid=None):
        super().__init__(sim)
        self.player_eid = player_eid

    def _candidate_eids(self):
        effects_map = self.sim.ecs.get(StatusEffects)
        if not effects_map:
            return ()
        return tuple(effects_map.keys())

    def update(self):
        live_timeskip = getattr(self.sim, "live_timeskip", None)
        if isinstance(live_timeskip, dict) and bool(live_timeskip.get("active")):
            return
        vitalities = self.sim.ecs.get(Vitality)
        for eid in self._candidate_eids():
            vitality = vitalities.get(eid)
            if vitality and (bool(getattr(vitality, "downed", False)) or int(getattr(vitality, "hp", 1)) <= 0):
                continue
            maybe_start_control_lapse(self.sim, eid)
        if self.player_eid is not None:
            maybe_start_drug_blackout(self.sim, self.player_eid)
