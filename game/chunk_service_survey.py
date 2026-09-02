"""Bounded neighborhood sampling for the authoritative chunk economy.

Active, manifest residents periodically answer the same service-category
vector that dialogue exposes to the player.  Answers are aggregated at the
actor's current chunk and retained as an EMA.  The survey does not directly
choose actions: canonical market, housing, business, travel, and settlement
consumers read its cached result on their own bounded attention schedules.
"""

from __future__ import annotations

import hashlib
import random

from engine.systems import System
from game.components import (
    AI,
    BehaviorProfile,
    CreatureIdentity,
    FinancialProfile,
    Inventory,
    LeisureDrive,
    NPCMemory,
    NPCEmergencyState,
    NPCNeeds,
    NPCSettlement,
    Occupation,
    PlayerControlled,
    Position,
    VehicleState,
    Vitality,
)
from game.service_category_registry import SERVICE_LOCATOR_TOPICS
from game.system_support.npc_income_runtime import inventory_liquid_credits


CHUNK_SERVICE_SURVEY_SCHEMA = 1
CHUNK_SERVICE_SURVEY_SLOTS_PER_DAY = 4
CHUNK_SERVICE_SURVEY_EMA_ALPHA = 0.25
CHUNK_SERVICE_SURVEY_TRACE_LIMIT = 16
CHUNK_SERVICE_SURVEY_RESPONDENT_TRACE_LIMIT = 96
CHUNK_SERVICE_SURVEY_CHECK_STRIDE = 30
NPC_SERVICE_SCORE_PROFILE_KEY = "service_need_profile"

# Central playtest knobs for the cultural-demand sample.
CHUNK_SERVICE_SURVEY_TUNING = {
    "base_floor": -0.22,
    "base_span": 0.62,
    "learned_delta_limit": 0.60,
    "strong_threshold": 0.55,
    "incident_memory_hours": 12.0,
    "survey_jitter_low": 0.15,
    "survey_jitter_high": 0.85,
}

_INCIDENT_TOKENS = frozenset({
    "attack", "combat", "conflict", "crime", "damage", "fight", "gun",
    "homicide", "incident", "murder", "shoot", "threat", "violence",
    "witness",
})
_TRAVEL_STATES = frozenset({
    "commuting", "traveling", "seeking_transit", "boarding_transit",
    "vehicle_fetch", "returning_home", "leaving_property",
})
_WORK_STATES = frozenset({"working", "going_to_work", "at_work", "on_shift"})


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


def _clamp(value, low=-1.0, high=1.0):
    return max(float(low), min(float(high), _float(value)))


def _ticks_per_hour(sim):
    traits = getattr(sim, "world_traits", {})
    clock = traits.get("clock", {}) if isinstance(traits, dict) else {}
    return max(60, _int((clock or {}).get("ticks_per_hour", 600), 600))


def _day_ticks(sim):
    return 24 * _ticks_per_hour(sim)


def _stable_unit(*parts):
    payload = "|".join(str(part) for part in parts).encode("utf-8", "replace")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big") / float(2**64 - 1)


def _state(sim, *, create=True):
    state = getattr(sim, "chunk_service_surveys", None)
    if not isinstance(state, dict):
        if not create:
            return {}
        state = {
            "schema": CHUNK_SERVICE_SURVEY_SCHEMA,
            "revision": 0,
            "chunks": {},
        }
        sim.chunk_service_surveys = state
    state.setdefault("schema", CHUNK_SERVICE_SURVEY_SCHEMA)
    state.setdefault("revision", 0)
    state.setdefault("chunks", {})
    return state


def chunk_service_survey_state(sim, *, create=True):
    """Return persistent survey state without advancing or sampling it."""

    return _state(sim, create=create)


def chunk_service_survey_read(sim, chunk):
    """Read one cached chunk result.  This never schedules or runs a survey."""

    try:
        key = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError, IndexError):
        return {}
    row = _state(sim, create=False).get("chunks", {}).get(key, {})
    return row if isinstance(row, dict) else {}


def survey_ticks_for_day(sim, chunk, day):
    """Return deterministic, day-varying survey ticks inside four time strata."""

    chunk = (int(chunk[0]), int(chunk[1]))
    day = int(day)
    ticks_per_day = _day_ticks(sim)
    stratum = ticks_per_day // CHUNK_SERVICE_SURVEY_SLOTS_PER_DAY
    low = _float(CHUNK_SERVICE_SURVEY_TUNING["survey_jitter_low"], 0.15)
    high = _float(CHUNK_SERVICE_SURVEY_TUNING["survey_jitter_high"], 0.85)
    seed = getattr(sim, "seed", 0)
    ticks = []
    for slot in range(CHUNK_SERVICE_SURVEY_SLOTS_PER_DAY):
        rng = random.Random(f"{seed}:chunk-service-survey:{chunk[0]}:{chunk[1]}:{day}:{slot}")
        fraction = low + ((high - low) * rng.random())
        offset = (slot * stratum) + int(round(fraction * max(1, stratum - 1)))
        ticks.append((day * ticks_per_day) + min(ticks_per_day - 1, offset))
    return tuple(ticks)


def next_chunk_service_survey(sim, chunk, after_tick=None):
    """Return the first scheduled survey strictly after ``after_tick``."""

    after_tick = _int(getattr(sim, "tick", 0) if after_tick is None else after_tick)
    day = max(0, after_tick // _day_ticks(sim))
    for candidate_day in (day, day + 1):
        for slot, tick in enumerate(survey_ticks_for_day(sim, chunk, candidate_day)):
            if tick > after_tick:
                return {"tick": tick, "day": candidate_day, "slot": slot}
    return {"tick": after_tick + _day_ticks(sim), "day": day + 1, "slot": 0}


def _normalize_score_profile(sim, eid, behavior):
    preferences = behavior.preferences if isinstance(behavior.preferences, dict) else {}
    behavior.preferences = preferences
    profile = preferences.get(NPC_SERVICE_SCORE_PROFILE_KEY)
    if not isinstance(profile, dict):
        profile = {}
        preferences[NPC_SERVICE_SCORE_PROFILE_KEY] = profile
    profile.setdefault("schema", 1)
    base = profile.setdefault("base", {})
    learned = profile.setdefault("learned", {})
    if not isinstance(base, dict):
        base = {}
        profile["base"] = base
    if not isinstance(learned, dict):
        learned = {}
        profile["learned"] = learned
    seed = getattr(sim, "seed", 0)
    floor = _float(CHUNK_SERVICE_SURVEY_TUNING["base_floor"], -0.22)
    span = _float(CHUNK_SERVICE_SURVEY_TUNING["base_span"], 0.62)
    for topic_id in SERVICE_LOCATOR_TOPICS:
        if topic_id not in base:
            base[topic_id] = round(floor + (span * _stable_unit(seed, eid, "service-affinity", topic_id)), 4)
        else:
            base[topic_id] = _clamp(base[topic_id])
        learned[topic_id] = _clamp(
            learned.get(topic_id, 0.0),
            -CHUNK_SERVICE_SURVEY_TUNING["learned_delta_limit"],
            CHUNK_SERVICE_SURVEY_TUNING["learned_delta_limit"],
        )
    return profile


def adjust_actor_service_need_score(sim, actor_eid, topic_id, delta, *, reason=""):
    """Mutate an actor's learned category score for future event-driven use."""

    topic_id = str(topic_id or "").strip().lower()
    if topic_id not in SERVICE_LOCATOR_TOPICS:
        return None
    behavior = sim.ecs.get(BehaviorProfile).get(int(actor_eid))
    if behavior is None:
        behavior = BehaviorProfile()
        sim.ecs.add(int(actor_eid), behavior)
    profile = _normalize_score_profile(sim, int(actor_eid), behavior)
    limit = _float(CHUNK_SERVICE_SURVEY_TUNING["learned_delta_limit"], 0.60)
    learned = profile["learned"]
    learned[topic_id] = round(_clamp(_float(learned.get(topic_id)) + _float(delta), -limit, limit), 4)
    if reason:
        profile["last_learning_reason"] = str(reason).strip().lower()
        profile["last_learning_tick"] = _int(getattr(sim, "tick", 0))
    return learned[topic_id]


def _need_pressure(value):
    return _clamp((60.0 - _float(value, 60.0)) / 60.0, 0.0, 1.0)


def _fresh_incident_pressure(sim, memory, now):
    if memory is None:
        return 0.0
    window = max(1, int(_ticks_per_hour(sim) * _float(CHUNK_SERVICE_SURVEY_TUNING["incident_memory_hours"], 12.0)))
    pressure = 0.0
    for entry in tuple(getattr(memory, "entries", ()) or ())[-32:]:
        if not isinstance(entry, dict):
            continue
        age = max(0, now - _int(entry.get("tick"), now))
        if age > window:
            continue
        kind = str(entry.get("kind", "") or "").strip().lower()
        data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
        tokens = set(kind.replace("-", "_").split("_"))
        for value in data.values():
            if isinstance(value, str):
                tokens.update(value.lower().replace("-", "_").split("_"))
        if not tokens.intersection(_INCIDENT_TOKENS):
            continue
        strength = _clamp(entry.get("strength", 0.5), 0.0, 1.0)
        pressure = max(pressure, strength * (1.0 - (age / float(window))))
    return _clamp(pressure, 0.0, 1.0)


def _actor_context(sim, eid, now):
    ecs = sim.ecs
    ai = ecs.get(AI).get(eid)
    needs = ecs.get(NPCNeeds).get(eid)
    settlement = ecs.get(NPCSettlement).get(eid)
    occupation = ecs.get(Occupation).get(eid)
    vitality = ecs.get(Vitality).get(eid)
    finance = ecs.get(FinancialProfile).get(eid)
    inventory = ecs.get(Inventory).get(eid)
    leisure = ecs.get(LeisureDrive).get(eid)
    vehicle = ecs.get(VehicleState).get(eid)
    emergency = ecs.get(NPCEmergencyState).get(eid)
    incident = _fresh_incident_pressure(sim, ecs.get(NPCMemory).get(eid), now)
    if emergency is not None and bool(getattr(emergency, "active", False)):
        incident = max(incident, 0.9)
    state = str(getattr(ai, "state", "idle") or "idle").strip().lower()
    role = str(getattr(ai, "role", "") or "").strip().lower()
    career = str(getattr(occupation, "career", "") or "").strip().lower()
    hp_gap = 0.0
    if vitality is not None:
        hp_gap = _clamp(
            (_float(getattr(vitality, "max_hp", 1), 1) - _float(getattr(vitality, "hp", 1), 1))
            / max(1.0, _float(getattr(vitality, "max_hp", 1), 1)),
            0.0,
            1.0,
        )
    return {
        "state": state,
        "role": role,
        "career": career,
        "hunger": _need_pressure(getattr(needs, "hunger", 100.0)),
        "thirst": _need_pressure(getattr(needs, "thirst", 100.0)),
        "energy": _need_pressure(getattr(needs, "energy", 100.0)),
        "wakefulness": _need_pressure(getattr(needs, "wakefulness", 100.0)),
        "safety": _need_pressure(getattr(needs, "safety", 100.0)),
        "social": _need_pressure(getattr(needs, "social", 100.0)),
        "hp_gap": hp_gap,
        "incident": incident,
        "unhoused": bool(settlement and str(getattr(settlement, "housing_status", "")).lower() in {"unhoused", "shelter", "temporary", "worksite"}),
        "unemployed": bool(settlement and str(getattr(settlement, "employment_status", "")).lower() in {"", "unemployed", "seeking"}),
        "bank_pressure": _clamp(
            (
                _float(inventory_liquid_credits(inventory), 0.0)
                - _float(getattr(finance, "wallet_buffer", 90), 90)
            )
            / max(1.0, _float(getattr(finance, "deposit_step", 48), 48)),
            0.0,
            1.0,
        ) if finance is not None and inventory is not None else 0.0,
        "poker": _clamp(max(
            _float(leisure.affinity_for("poker"), 0.0) if leisure else 0.0,
            _float(leisure.urge_for("poker"), 0.0) if leisure else 0.0,
        ), 0.0, 1.0),
        "has_vehicle": bool(vehicle and (getattr(vehicle, "active_vehicle_id", None) or getattr(vehicle, "last_vehicle_id", None))),
        "in_vehicle": bool(vehicle and getattr(vehicle, "in_vehicle", False)),
    }


def _profile_behavior_adjustments(behavior):
    get = behavior.get if behavior is not None else (lambda _key, default=0.0: default)
    return {
        "trade": 0.25 * max(get("buy_provisions"), get("buy_practical_gear"), get("buy_quirky_items")),
        "social": 0.18 * get("seek_social_contact"),
        "medical": 0.28 * get("seek_medical_aid"),
        "shelter": 0.30 * get("seek_shelter"),
        "covert": 0.24 * get("seek_criminal_affiliation"),
    }


def actor_service_score_vector(sim, eid, *, tick=None):
    """Compute and persist one actor's full signed service score vector."""

    eid = int(eid)
    now = _int(getattr(sim, "tick", 0) if tick is None else tick)
    behavior = sim.ecs.get(BehaviorProfile).get(eid)
    if behavior is None:
        behavior = BehaviorProfile()
        sim.ecs.add(eid, behavior)
    profile = _normalize_score_profile(sim, eid, behavior)
    context = _actor_context(sim, eid, now)
    preference = _profile_behavior_adjustments(behavior)
    modifiers = {topic_id: 0.0 for topic_id in SERVICE_LOCATOR_TOPICS}

    provisions = max(context["hunger"], context["thirst"])
    rest = max(context["energy"], context["wakefulness"], 0.72 if context["unhoused"] else 0.0)
    medical = max(context["hp_gap"], context["incident"] * 0.65, preference["medical"])
    travel = 0.55 if context["state"] in _TRAVEL_STATES else 0.18 if context["in_vehicle"] else 0.0
    work = max(0.72 if context["unemployed"] else 0.0, 0.25 if context["state"] in _WORK_STATES else 0.0)

    modifiers["service_trade"] += (0.52 * provisions) + preference["trade"] + (0.18 * context["social"])
    modifiers["service_rest"] += (0.72 * rest) + preference["shelter"]
    for topic_id in ("service_street_doctor", "service_herbal"):
        modifiers[topic_id] += 0.68 * medical
    modifiers["service_herbal"] += 0.12 * provisions
    modifiers["service_justice"] += (0.30 * context["incident"]) + (0.18 * context["safety"])
    modifiers["service_repair"] += (0.28 * context["incident"]) + (0.22 if context["has_vehicle"] else 0.0)
    modifiers["service_banking"] += (0.42 * context["bank_pressure"]) + (0.12 if context["state"] in _WORK_STATES else 0.0)
    modifiers["service_insurance"] += (0.24 * context["incident"]) + (0.10 if context["has_vehicle"] else 0.0)
    modifiers["service_gaming"] += (0.62 * context["poker"]) + (0.25 * context["social"]) + preference["social"]
    if context["state"] in {"playing_poker", "seeking_poker_table"}:
        modifiers["service_gaming"] += 0.34
    if context["state"] == "shopping":
        modifiers["service_trade"] += 0.34
        modifiers["service_outfitter"] += 0.14
    if context["state"] in {"seeking_shelter", "resting"}:
        modifiers["service_rest"] += 0.32
    if context["state"] == "seeking_medical_aid":
        modifiers["service_street_doctor"] += 0.34
        modifiers["service_herbal"] += 0.24
    if context["state"] == "seeking_bank":
        modifiers["service_banking"] += 0.38
    for topic_id in ("service_work", "service_courier", "service_agency", "service_bounty"):
        modifiers[topic_id] += 0.58 * work
    for topic_id in ("service_transit", "service_rail", "service_bus", "service_shuttle", "service_ferry", "service_coach"):
        modifiers[topic_id] += travel + (0.18 if not context["has_vehicle"] else -0.08)
    if context["has_vehicle"]:
        modifiers["service_fuel"] += 0.32
        modifiers["service_vehicle_fetch"] += 0.16
    else:
        modifiers["service_vehicle_sales"] += 0.22 + (0.18 * travel)
        modifiers["service_used_cars"] += 0.30 + (0.22 * travel)
    modifiers["service_discreet_trade"] += preference["covert"]
    modifiers["service_street_doctor"] += 0.35 * preference["covert"]
    modifiers["service_outfitter"] += 0.20 * max(behavior.get("buy_practical_gear"), behavior.get("buy_quirky_items"))

    career = context["career"]
    if any(token in career for token in ("owner", "manager", "operator", "executive")):
        modifiers["service_business_desk"] += 0.34
        modifiers["service_contractor"] += 0.20
        modifiers["service_banking"] += 0.14
    if any(token in career for token in ("courier", "driver", "mechanic", "transit")):
        modifiers["service_fuel"] += 0.20
        modifiers["service_repair"] += 0.18
    if any(token in career for token in ("guard", "bailiff", "deputy", "corrections", "law")):
        modifiers["service_justice"] += 0.22
        modifiers["service_discreet_trade"] -= 0.26
    if any(token in career for token in ("tech", "electronic", "drone")):
        modifiers["service_drone_parts"] += 0.30
    if any(token in career for token in ("wire", "netrunner", "hacker")):
        modifiers["service_wire_gear"] += 0.34

    scores = {
        topic_id: round(_clamp(
            _float(profile["base"].get(topic_id))
            + _float(profile["learned"].get(topic_id))
            + _float(modifiers.get(topic_id)),
        ), 4)
        for topic_id in SERVICE_LOCATOR_TOPICS
    }
    profile["last_scores"] = scores
    profile["last_survey_tick"] = now
    return scores, context, profile


def _actor_name(sim, eid):
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    for attr in ("personal_name", "common_name"):
        value = str(getattr(identity, attr, "") or "").strip()
        if value:
            return value
    return f"person {eid}"


def _manifest_human_eids(sim, chunk):
    for eid in tuple(sim.entity_ids_in_chunk(chunk) or ()):
        if eid in sim.ecs.get(PlayerControlled):
            continue
        pos = sim.ecs.get(Position).get(eid)
        ai = sim.ecs.get(AI).get(eid)
        identity = sim.ecs.get(CreatureIdentity).get(eid)
        vitality = sim.ecs.get(Vitality).get(eid)
        if pos is None or ai is None or identity is None:
            continue
        if tuple(sim.chunk_coords(int(pos.x), int(pos.y))[:2]) != tuple(chunk):
            continue
        if str(getattr(identity, "creature_type", "") or "").lower() != "human" and str(getattr(identity, "taxonomy_class", "") or "").lower() != "hominid":
            continue
        if vitality is not None and (bool(getattr(vitality, "downed", False)) or _int(getattr(vitality, "hp", 1), 1) <= 0):
            continue
        yield int(eid)


def run_chunk_service_survey(sim, chunk, *, tick=None, scheduled=None):
    """Sample one active chunk now and update its authoritative survey cache."""

    chunk = (int(chunk[0]), int(chunk[1]))
    now = _int(getattr(sim, "tick", 0) if tick is None else tick)
    state = _state(sim)
    chunk_row = state["chunks"].setdefault(chunk, {"categories": {}, "trace": []})
    categories = chunk_row.setdefault("categories", {})
    respondents = []
    sums = {topic_id: 0.0 for topic_id in SERVICE_LOCATOR_TOPICS}
    positive = {topic_id: 0.0 for topic_id in SERVICE_LOCATOR_TOPICS}
    avoidance = {topic_id: 0.0 for topic_id in SERVICE_LOCATOR_TOPICS}
    strong = {topic_id: 0 for topic_id in SERVICE_LOCATOR_TOPICS}
    base_sums = {topic_id: 0.0 for topic_id in SERVICE_LOCATOR_TOPICS}
    learned_sums = {topic_id: 0.0 for topic_id in SERVICE_LOCATOR_TOPICS}
    context_tally = {}
    threshold = _float(CHUNK_SERVICE_SURVEY_TUNING["strong_threshold"], 0.55)

    for eid in _manifest_human_eids(sim, chunk):
        scores, context, profile = actor_service_score_vector(sim, eid, tick=now)
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        low_ranked = sorted(scores.items(), key=lambda item: (item[1], item[0]))
        actor_state = str(context.get("state", "idle") or "idle")
        context_tally[actor_state] = context_tally.get(actor_state, 0) + 1
        respondents.append({
            "eid": eid,
            "name": _actor_name(sim, eid),
            "state": actor_state,
            "career": str(context.get("career", "") or ""),
            "incident": round(_float(context.get("incident")), 3),
            "top": tuple(ranked[:3]),
            "low": tuple(low_ranked[:2]),
        })
        for topic_id, score in scores.items():
            value = _float(score)
            sums[topic_id] += value
            positive[topic_id] += max(0.0, value)
            avoidance[topic_id] += max(0.0, -value)
            base_sums[topic_id] += _float(profile["base"].get(topic_id))
            learned_sums[topic_id] += _float(profile["learned"].get(topic_id))
            if value >= threshold:
                strong[topic_id] += 1

    count = len(respondents)
    alpha = CHUNK_SERVICE_SURVEY_EMA_ALPHA
    for topic_id in SERVICE_LOCATOR_TOPICS:
        if not count:
            continue
        latest_mean = sums[topic_id] / count
        latest_positive = positive[topic_id] / count
        latest_avoidance = avoidance[topic_id] / count
        baseline = base_sums[topic_id] / count
        learned_mean = learned_sums[topic_id] / count
        row = categories.setdefault(topic_id, {"initialized": False})
        if bool(row.get("initialized")):
            row["ema_mean"] = (alpha * latest_mean) + ((1.0 - alpha) * _float(row.get("ema_mean")))
            row["ema_positive"] = (alpha * latest_positive) + ((1.0 - alpha) * _float(row.get("ema_positive")))
            row["ema_avoidance"] = (alpha * latest_avoidance) + ((1.0 - alpha) * _float(row.get("ema_avoidance")))
            row["respondents_ema"] = (alpha * count) + ((1.0 - alpha) * _float(row.get("respondents_ema")))
        else:
            row["ema_mean"] = latest_mean
            row["ema_positive"] = latest_positive
            row["ema_avoidance"] = latest_avoidance
            row["respondents_ema"] = float(count)
            row["initialized"] = True
        row.update({
            "baseline": round(baseline, 4),
            "learned_mean": round(learned_mean, 4),
            "latest_mean": round(latest_mean, 4),
            "latest_positive": round(latest_positive, 4),
            "latest_avoidance": round(latest_avoidance, 4),
            "strong_count": strong[topic_id],
            "respondents": count,
            "last_tick": now,
        })
        if row.get("initialized"):
            for key in ("ema_mean", "ema_positive", "ema_avoidance", "respondents_ema"):
                row[key] = round(_float(row.get(key)), 4)

    ticks_per_hour = _ticks_per_hour(sim)
    day = now // _day_ticks(sim)
    hour = (now % _day_ticks(sim)) / float(ticks_per_hour)
    top_categories = (
        sorted(
            ((topic_id, categories[topic_id].get("latest_mean", 0.0)) for topic_id in SERVICE_LOCATOR_TOPICS),
            key=lambda item: (-_float(item[1]), item[0]),
        )[:5]
        if count
        else []
    )
    trace = chunk_row.setdefault("trace", [])
    trace.append({
        "tick": now,
        "day": day,
        "hour": round(hour, 2),
        "respondents": count,
        "top": tuple(top_categories),
        "contexts": dict(sorted(context_tally.items())),
        "scheduled_day": _int((scheduled or {}).get("day"), day),
        "scheduled_slot": _int((scheduled or {}).get("slot"), -1),
        "scheduled_tick": _int((scheduled or {}).get("tick"), now),
        "delay_ticks": max(0, now - _int((scheduled or {}).get("tick"), now)),
    })
    if len(trace) > CHUNK_SERVICE_SURVEY_TRACE_LIMIT:
        del trace[:-CHUNK_SERVICE_SURVEY_TRACE_LIMIT]
    chunk_row.update({
        "last_attempt_tick": now,
        "respondents": count,
        "confidence": round(min(1.0, count / 12.0), 3),
        "latest_respondents": respondents[-CHUNK_SERVICE_SURVEY_RESPONDENT_TRACE_LIMIT:],
        "contexts": dict(sorted(context_tally.items())),
    })
    if count:
        chunk_row.update({
            "last_survey_tick": now,
            "last_survey_day": day,
            "last_survey_hour": round(hour, 2),
        })
    from game.neighborhood_housing import record_housing_survey_completion
    record_housing_survey_completion(sim, chunk)
    state["revision"] = _int(state.get("revision")) + 1
    return chunk_row


def _active_chunks(sim):
    loaded = getattr(getattr(sim, "world", None), "loaded_chunks", {}) or {}
    chunks = []
    if isinstance(loaded, dict):
        chunks.extend(
            (int(chunk[0]), int(chunk[1]))
            for chunk, data in loaded.items()
            if isinstance(data, dict) and str(data.get("detail", "")).lower() == "active"
        )
    if not chunks:
        active = getattr(sim, "active_chunk_coord", None)
        try:
            chunks.append((int(active[0]), int(active[1])))
        except (TypeError, ValueError, IndexError):
            pass
    return tuple(sorted(set(chunks)))


class ChunkServiceSurveySystem(System):
    """Advance deterministic surveys only for currently active chunks."""

    def __init__(self, sim):
        super().__init__(sim)
        self.next_check_tick = 0

    def update(self):
        now = _int(getattr(self.sim, "tick", 0))
        if now < self.next_check_tick:
            return
        self.next_check_tick = now + CHUNK_SERVICE_SURVEY_CHECK_STRIDE
        state = _state(self.sim)
        for chunk in _active_chunks(self.sim):
            chunk_row = state["chunks"].setdefault(chunk, {"categories": {}, "trace": []})
            due = chunk_row.get("next_survey")
            if not isinstance(due, dict):
                chunk_row["next_survey"] = next_chunk_service_survey(self.sim, chunk, now)
                state["revision"] = _int(state.get("revision")) + 1
                continue
            if now < _int(due.get("tick"), now + 1):
                continue
            run_chunk_service_survey(self.sim, chunk, tick=now, scheduled=due)
            chunk_row["next_survey"] = next_chunk_service_survey(self.sim, chunk, now)
