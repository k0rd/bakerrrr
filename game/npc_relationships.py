"""NPC-only romantic relationship runtime.

This layer is intentionally small: it records durable pair state while the
existing NPCSocial bond machinery remains the thing other systems can read.
"""

import random

from engine.events import Event
from engine.systems import System
from engine.visibility import has_line_of_sight
from game.components import (
    AI,
    CreatureIdentity,
    NPCMemory,
    NPCNeeds,
    NPCRoutine,
    NPCSettlement,
    NPCSocial,
    NPCTraits,
    NPCWill,
    Position,
    Vitality,
)
from game.human_identity import is_human_identity, normalize_gender_identity
from game.property_runtime import property_focus_position
from game.system_support.actor_attention_runtime import (
    mark_actor_urgent as _mark_actor_urgent,
    schedule_actor_due as _schedule_actor_due,
)
from game.system_support.entity_naming import _entity_display_name


RELATIONSHIP_STAGES = ("dating", "partner", "spouse")
_STAGE_RANK = {stage: index for index, stage in enumerate(RELATIONSHIP_STAGES)}
_ACK_COOLDOWN_TICKS = 90

_TASTE_WEIGHTS = (
    ("any", 38),
    ("women", 18),
    ("men", 18),
    ("nonbinary", 6),
    ("women_and_nonbinary", 10),
    ("men_and_nonbinary", 10),
)

_ACK_LINES = (
    "There you are.",
    "Hey. I kept a little room for you.",
    "I was just wondering where you got to.",
    "Come here a second.",
    "You made it back in one piece.",
    "Good, I was hoping to see you.",
    "Walk with me a minute?",
    "I saved you the easy side of the street.",
    "There is my steady trouble.",
    "I knew that step was yours.",
    "You look like you found weather out there.",
    "I was about to come looking.",
    "Hey, stay close a little.",
    "I missed your face in the noise.",
    "You owe me the short version.",
    "I was keeping an eye out.",
    "Good timing, as usual.",
    "Do not vanish that quietly on me.",
    "I am glad you are here.",
    "You look better where I can see you.",
    "There you go, making the room easier.",
    "I had half a thought to save this for you.",
    "Come on, before the day gets clever.",
    "I know that look. What happened?",
    "You are late enough to be charming.",
    "I was listening for you.",
    "The place got dull without you.",
    "Hey. Breathe first, story second.",
    "I like seeing you turn the corner.",
    "Hold up. Let me look at you.",
    "There is the person I wanted.",
    "You made my shift kinder.",
    "Stay where I can fuss at you.",
    "You always arrive like you planned the light.",
    "I kept the good half of the silence.",
    "You are a sight, and I mean that kindly.",
    "I had a feeling you were near.",
    "Do not make me admit I worried.",
    "The whole block sounds better now.",
    "You found me. That counts.",
    "I was saving that smile for later.",
    "Come close before someone asks us for work.",
    "You and your timing.",
    "I know. I am glad too.",
    "That is better.",
    "I can work with this now.",
    "You bring the room back down.",
    "I was about to blame the weather for missing you.",
)

_SPOUSE_ACK_LINES = (
    "There is my home walking in.",
    "Hey, love. I kept your place.",
    "That is the face I wanted today.",
    "Come here, married trouble.",
    "I was counting steps without meaning to.",
    "Good. The day can behave now.",
    "I saved you a corner of the quiet.",
    "You made it. That is all I needed first.",
)


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _clamp(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return max(0.0, min(1.0, number))


def relationship_state(sim):
    state = getattr(sim, "npc_relationships", None)
    if not isinstance(state, dict):
        state = {}
        sim.npc_relationships = state
    return state


def relationship_taste_state(sim):
    state = getattr(sim, "npc_relationship_tastes", None)
    if not isinstance(state, dict):
        state = {}
        sim.npc_relationship_tastes = state
    return state


def relationship_pair_key(left_eid, right_eid):
    left = _int(left_eid)
    right = _int(right_eid)
    if left <= 0 or right <= 0 or left == right:
        return ""
    a, b = sorted((left, right))
    return f"{a}:{b}"


def _stage(stage, default="dating"):
    text = str(stage or default).strip().lower()
    return text if text in _STAGE_RANK else default


def _stage_at_least(stage, minimum):
    return _STAGE_RANK.get(_stage(stage), 0) >= _STAGE_RANK.get(_stage(minimum), 0)


def _player_id(sim):
    return _int(getattr(sim, "player_eid", 0), 0)


def _is_player(sim, eid):
    player_id = _player_id(sim)
    return player_id > 0 and _int(eid) == player_id


def _identity(sim, eid):
    return sim.ecs.get(CreatureIdentity).get(eid)


def _is_human_npc(sim, eid):
    if _is_player(sim, eid):
        return False
    identity = _identity(sim, eid)
    if not is_human_identity(identity):
        return False
    ai = sim.ecs.get(AI).get(eid)
    if ai is not None and str(getattr(ai, "role", "") or "").strip().lower() == "wildlife":
        return False
    vitality = sim.ecs.get(Vitality).get(eid)
    if vitality is not None and (bool(getattr(vitality, "dead", False)) or bool(getattr(vitality, "downed", False))):
        return False
    return True


def actor_presentation_gender(sim, eid):
    identity = _identity(sim, eid)
    return normalize_gender_identity(
        getattr(identity, "gender_identity", "") if identity is not None else "",
        default="nonbinary",
    )


def romantic_taste_for_actor(sim, eid):
    eid = _int(eid)
    if eid <= 0 or _is_player(sim, eid):
        return "unavailable"
    state = relationship_taste_state(sim)
    key = str(eid)
    existing = str(state.get(key, "") or "").strip().lower()
    if existing:
        return existing
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:npc-romantic-taste:{eid}")
    total = sum(weight for _taste, weight in _TASTE_WEIGHTS)
    roll = rng.uniform(0, total)
    cursor = 0.0
    for taste, weight in _TASTE_WEIGHTS:
        cursor += float(weight)
        if roll <= cursor:
            state[key] = taste
            return taste
    state[key] = "any"
    return "any"


def presentation_satisfies_taste(taste, presentation):
    taste = str(taste or "").strip().lower()
    presentation = normalize_gender_identity(presentation, default="nonbinary")
    if taste == "any":
        return True
    if taste == "women":
        return presentation == "woman"
    if taste == "men":
        return presentation == "man"
    if taste == "nonbinary":
        return presentation == "nonbinary"
    if taste == "women_and_nonbinary":
        return presentation in {"woman", "nonbinary"}
    if taste == "men_and_nonbinary":
        return presentation in {"man", "nonbinary"}
    return False


def mutual_presentation_taste_match(sim, left_eid, right_eid):
    left_presentation = actor_presentation_gender(sim, left_eid)
    right_presentation = actor_presentation_gender(sim, right_eid)
    return (
        presentation_satisfies_taste(romantic_taste_for_actor(sim, left_eid), right_presentation)
        and presentation_satisfies_taste(romantic_taste_for_actor(sim, right_eid), left_presentation)
    )


def relationship_between(sim, left_eid, right_eid):
    key = relationship_pair_key(left_eid, right_eid)
    if not key:
        return None
    row = relationship_state(sim).get(key)
    return row if isinstance(row, dict) and str(row.get("status", "active") or "active") == "active" else None


def current_relationship_for_actor(sim, eid, *, minimum_stage="dating"):
    eid = _int(eid)
    if eid <= 0:
        return None
    for key, row in tuple(relationship_state(sim).items()):
        if not isinstance(row, dict) or str(row.get("status", "active") or "active") != "active":
            continue
        if not _stage_at_least(row.get("stage"), minimum_stage):
            continue
        left = _int(row.get("left_eid"))
        right = _int(row.get("right_eid"))
        if eid in {left, right}:
            return dict(row, relationship_key=key)
    return None


def relationship_partner_eid(sim, eid, *, minimum_stage="dating"):
    row = current_relationship_for_actor(sim, eid, minimum_stage=minimum_stage)
    if not row:
        return None
    eid = _int(eid)
    left = _int(row.get("left_eid"))
    right = _int(row.get("right_eid"))
    return right if left == eid else left if right == eid else None


def are_romantic_partners(sim, left_eid, right_eid, *, minimum_stage="dating"):
    row = relationship_between(sim, left_eid, right_eid)
    return bool(row and _stage_at_least(row.get("stage"), minimum_stage))


def _social(sim, eid):
    socials = sim.ecs.get(NPCSocial)
    social = socials.get(eid)
    if social is None:
        social = NPCSocial()
        sim.ecs.add(eid, social)
    return social


def _upsert_partner_bond(sim, left_eid, right_eid, *, stage, closeness, trust):
    stage = _stage(stage)
    protectiveness = 1.0 if stage == "spouse" else 0.96 if stage == "partner" else 0.88
    for source, target in ((_int(left_eid), _int(right_eid)), (_int(right_eid), _int(left_eid))):
        social = _social(sim, source)
        existing = social.bonds.get(target) if isinstance(getattr(social, "bonds", None), dict) else None
        if not isinstance(existing, dict):
            social.add_bond(target, kind="partner", closeness=closeness, trust=trust, protectiveness=protectiveness)
            existing = social.bonds.get(target)
        if isinstance(existing, dict):
            existing["kind"] = "partner"
            existing["closeness"] = max(float(existing.get("closeness", 0.0) or 0.0), float(closeness))
            existing["trust"] = max(float(existing.get("trust", 0.0) or 0.0), float(trust))
            existing["protectiveness"] = max(float(existing.get("protectiveness", 0.0) or 0.0), float(protectiveness))
            existing["relationship_stage"] = stage


def _bond_metrics(sim, left_eid, right_eid):
    left_social = sim.ecs.get(NPCSocial).get(left_eid)
    right_social = sim.ecs.get(NPCSocial).get(right_eid)
    left = (left_social.bonds or {}).get(right_eid) if left_social is not None else {}
    right = (right_social.bonds or {}).get(left_eid) if right_social is not None else {}
    closeness = min(_clamp((left or {}).get("closeness"), 0.0), _clamp((right or {}).get("closeness"), 0.0))
    trust = min(_clamp((left or {}).get("trust"), 0.0), _clamp((right or {}).get("trust"), 0.0))
    if closeness <= 0.0 and isinstance(left, dict):
        closeness = _clamp(left.get("closeness"), 0.0)
    if trust <= 0.0 and isinstance(left, dict):
        trust = _clamp(left.get("trust"), 0.0)
    return closeness, trust


def _shared_place_bonus(sim, left_eid, right_eid):
    settlements = sim.ecs.get(NPCSettlement)
    left_settlement = settlements.get(left_eid)
    right_settlement = settlements.get(right_eid)
    bonus = 0.0
    if left_settlement is not None and right_settlement is not None:
        if str(getattr(left_settlement, "home_property_id", "") or "").strip() and (
            str(getattr(left_settlement, "home_property_id", "") or "").strip()
            == str(getattr(right_settlement, "home_property_id", "") or "").strip()
        ):
            bonus += 0.12
        if str(getattr(left_settlement, "work_property_id", "") or "").strip() and (
            str(getattr(left_settlement, "work_property_id", "") or "").strip()
            == str(getattr(right_settlement, "work_property_id", "") or "").strip()
        ):
            bonus += 0.05
    left_routine = sim.ecs.get(NPCRoutine).get(left_eid)
    right_routine = sim.ecs.get(NPCRoutine).get(right_eid)
    if left_routine and right_routine and getattr(left_routine, "home", None) and getattr(right_routine, "home", None):
        if tuple(left_routine.home) == tuple(right_routine.home):
            bonus += 0.08
    return min(0.2, bonus)


def attraction_score(sim, left_eid, right_eid):
    if not _is_human_npc(sim, left_eid) or not _is_human_npc(sim, right_eid):
        return {"eligible": False, "score": 0.0, "reason": "not_human_npc"}
    if left_eid == right_eid:
        return {"eligible": False, "score": 0.0, "reason": "same_actor"}
    pair_key = relationship_pair_key(left_eid, right_eid)
    existing_left = current_relationship_for_actor(sim, left_eid)
    existing_right = current_relationship_for_actor(sim, right_eid)
    if existing_left and str(existing_left.get("relationship_key", "") or "") != pair_key:
        return {"eligible": False, "score": 0.0, "reason": "left_unavailable"}
    if existing_right and str(existing_right.get("relationship_key", "") or "") != pair_key:
        return {"eligible": False, "score": 0.0, "reason": "right_unavailable"}
    if not mutual_presentation_taste_match(sim, left_eid, right_eid):
        return {"eligible": False, "score": 0.0, "reason": "presentation_taste"}
    closeness, trust = _bond_metrics(sim, left_eid, right_eid)
    left_traits = sim.ecs.get(NPCTraits).get(left_eid) or NPCTraits()
    right_traits = sim.ecs.get(NPCTraits).get(right_eid) or NPCTraits()
    trait_fit = 1.0 - min(1.0, (
        abs(float(getattr(left_traits, "empathy", 0.5) or 0.5) - float(getattr(right_traits, "empathy", 0.5) or 0.5))
        + abs(float(getattr(left_traits, "discipline", 0.5) or 0.5) - float(getattr(right_traits, "discipline", 0.5) or 0.5))
    ) / 2.0)
    positions = sim.ecs.get(Position)
    left_pos = positions.get(left_eid)
    right_pos = positions.get(right_eid)
    local_bonus = 0.0
    if left_pos and right_pos and int(left_pos.z) == int(right_pos.z):
        distance = abs(int(left_pos.x) - int(right_pos.x)) + abs(int(left_pos.y) - int(right_pos.y))
        local_bonus = max(0.0, 0.08 - min(0.08, distance * 0.01))
    score = (
        closeness * 0.42
        + trust * 0.32
        + trait_fit * 0.1
        + _shared_place_bonus(sim, left_eid, right_eid)
        + local_bonus
        + 0.08
    )
    return {
        "eligible": True,
        "score": round(min(1.0, score), 4),
        "closeness": round(closeness, 4),
        "trust": round(trust, 4),
        "trait_fit": round(trait_fit, 4),
        "reason": "eligible",
    }


def _home_prop_for_actor(sim, eid):
    settlement = sim.ecs.get(NPCSettlement).get(eid)
    prop_id = str(getattr(settlement, "home_property_id", "") or "").strip() if settlement else ""
    prop = sim.properties.get(prop_id) if prop_id else None
    return prop if isinstance(prop, dict) else None


def _home_kind_for_actor(sim, eid, prop):
    settlement = sim.ecs.get(NPCSettlement).get(eid)
    kind = str(getattr(settlement, "housing_status", "") or "").strip().lower() if settlement else ""
    if kind:
        return kind
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    archetype = str(metadata.get("archetype", "") or "").strip().lower()
    if archetype in {"hotel", "inn", "motel", "boarding_house"}:
        return "lodging"
    if archetype in {"shelter", "field_camp", "ranger_hut", "ruin_shelter"}:
        return "shelter"
    return "housing"


def try_relationship_cohabitation(sim, left_eid, right_eid, row=None):
    left_prop = _home_prop_for_actor(sim, left_eid)
    right_prop = _home_prop_for_actor(sim, right_eid)
    chosen_owner = None
    chosen = None
    if left_prop and right_prop:
        left_focus = property_focus_position(left_prop)
        right_focus = property_focus_position(right_prop)
        if left_focus and right_focus:
            left_work = getattr(sim.ecs.get(NPCRoutine).get(left_eid), "work", None)
            right_work = getattr(sim.ecs.get(NPCRoutine).get(right_eid), "work", None)

            def _commute_cost(focus):
                cost = 0
                for work in (left_work, right_work):
                    if isinstance(work, (tuple, list)) and len(work) >= 3:
                        cost += abs(int(focus[0]) - int(work[0])) + abs(int(focus[1]) - int(work[1]))
                return cost

            chosen_owner, chosen = (left_eid, left_prop) if _commute_cost(left_focus) <= _commute_cost(right_focus) else (right_eid, right_prop)
        else:
            chosen_owner, chosen = left_eid, left_prop
    elif left_prop:
        chosen_owner, chosen = left_eid, left_prop
    elif right_prop:
        chosen_owner, chosen = right_eid, right_prop
    if not chosen:
        return False
    focus = property_focus_position(chosen)
    if not focus:
        return False
    home_kind = _home_kind_for_actor(sim, chosen_owner, chosen)
    for eid in (_int(left_eid), _int(right_eid)):
        routine = sim.ecs.get(NPCRoutine).get(eid)
        if routine is None:
            routine = NPCRoutine()
            sim.ecs.add(eid, routine)
        routine.home = tuple(int(v) for v in focus[:3])
        settlement = sim.ecs.get(NPCSettlement).get(eid)
        if settlement is None:
            settlement = NPCSettlement()
            sim.ecs.add(eid, settlement)
        settlement.home_property_id = str(chosen.get("id", "") or "").strip()
        settlement.housing_status = home_kind
        settlement.phase = "settling" if home_kind == "housing" else "lodged"
        settlement.last_housing_tick = int(getattr(sim, "tick", 0) or 0)
    if isinstance(row, dict):
        row["shared_home_property_id"] = str(chosen.get("id", "") or "").strip()
        row["cohabitation_tick"] = int(getattr(sim, "tick", 0) or 0)
    return True


def _surname(name):
    text = str(name or "").strip()
    if " " not in text:
        return ""
    return text.rsplit(" ", 1)[-1].strip()


def _replace_surname(name, surname):
    text = str(name or "").strip()
    surname = str(surname or "").strip()
    if not text or not surname:
        return text
    if " " not in text:
        return f"{text} {surname}"
    first = text.rsplit(" ", 1)[0].strip()
    return f"{first} {surname}".strip()


def maybe_share_surname_on_marriage(sim, left_eid, right_eid, row):
    if not isinstance(row, dict) or row.get("surname_mode"):
        return False
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:npc-marriage-surname:{relationship_pair_key(left_eid, right_eid)}")
    roll = rng.random()
    mode = "kept"
    changed = False
    if roll < 0.24:
        left_identity = _identity(sim, left_eid)
        right_identity = _identity(sim, right_eid)
        left_name = str(getattr(left_identity, "personal_name", "") or "").strip() if left_identity else ""
        right_name = str(getattr(right_identity, "personal_name", "") or "").strip() if right_identity else ""
        left_surname = _surname(left_name)
        right_surname = _surname(right_name)
        if left_surname and right_identity:
            right_identity.personal_name = _replace_surname(right_name, left_surname)
            sim.remember_entity_identity(right_eid, reason="relationship_surname_changed")
            mode = "right_took_left"
            changed = True
        elif right_surname and left_identity:
            left_identity.personal_name = _replace_surname(left_name, right_surname)
            sim.remember_entity_identity(left_eid, reason="relationship_surname_changed")
            mode = "left_took_right"
            changed = True
    row["surname_mode"] = mode
    return changed


def ensure_relationship(sim, left_eid, right_eid, *, stage="dating", reason="", attraction=None, cohabit=True):
    left = _int(left_eid)
    right = _int(right_eid)
    key = relationship_pair_key(left, right)
    if not key or _is_player(sim, left) or _is_player(sim, right):
        return None
    stage = _stage(stage)
    state = relationship_state(sim)
    now = int(getattr(sim, "tick", 0) or 0)
    existing = state.get(key)
    if isinstance(existing, dict) and str(existing.get("status", "active") or "active") == "active":
        old_stage = _stage(existing.get("stage"))
        if _STAGE_RANK[stage] < _STAGE_RANK[old_stage]:
            stage = old_stage
        row = existing
    else:
        a, b = sorted((left, right))
        row = {
            "left_eid": a,
            "right_eid": b,
            "formed_tick": now,
            "status": "active",
            "acknowledgement": {},
        }
        state[key] = row
    old_stage = _stage(row.get("stage", stage))
    row["stage"] = stage
    row["stage_tick"] = now if old_stage != stage else _int(row.get("stage_tick"), now)
    row["last_progress_tick"] = now
    row["reason"] = str(reason or row.get("reason", "") or "social_contact")
    row["attraction_score"] = round(float((attraction or {}).get("score", row.get("attraction_score", 0.0)) or 0.0), 4) if isinstance(attraction, dict) else round(float(row.get("attraction_score", 0.0) or 0.0), 4)
    row["left_taste"] = romantic_taste_for_actor(sim, row["left_eid"])
    row["right_taste"] = romantic_taste_for_actor(sim, row["right_eid"])
    baseline = {
        "dating": (0.72, 0.68),
        "partner": (0.84, 0.8),
        "spouse": (0.92, 0.9),
    }[stage]
    _upsert_partner_bond(sim, left, right, stage=stage, closeness=baseline[0], trust=baseline[1])
    if cohabit and stage in {"partner", "spouse"}:
        try_relationship_cohabitation(sim, left, right, row)
    if stage == "spouse":
        maybe_share_surname_on_marriage(sim, left, right, row)
    return dict(row, relationship_key=key)


def seed_relationship_from_home_bond(sim, left_eid, right_eid, *, closeness=0.78, trust=0.74, home_property_id=""):
    if _is_player(sim, left_eid) or _is_player(sim, right_eid):
        return None
    key = relationship_pair_key(left_eid, right_eid)
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:seeded-npc-relationship:{key}:{home_property_id}")
    stage = "spouse" if rng.random() < 0.16 and min(float(closeness), float(trust)) >= 0.78 else "partner"
    row = ensure_relationship(
        sim,
        left_eid,
        right_eid,
        stage=stage,
        reason="shared_home_seed",
        attraction={"score": min(1.0, (float(closeness) * 0.55) + (float(trust) * 0.45))},
        cohabit=True,
    )
    if row and home_property_id:
        relationship_state(sim)[key]["shared_home_property_id"] = str(home_property_id)
    return row


def maybe_progress_relationship_after_socialized(sim, left_eid, right_eid):
    if _is_player(sim, left_eid) or _is_player(sim, right_eid):
        return None
    existing = relationship_between(sim, left_eid, right_eid)
    attraction = attraction_score(sim, left_eid, right_eid)
    if not bool(attraction.get("eligible")):
        return None
    score = float(attraction.get("score", 0.0) or 0.0)
    closeness = float(attraction.get("closeness", 0.0) or 0.0)
    trust = float(attraction.get("trust", 0.0) or 0.0)
    now = int(getattr(sim, "tick", 0) or 0)
    if existing is None:
        if score >= 0.72 and closeness >= 0.62 and trust >= 0.58:
            return ensure_relationship(sim, left_eid, right_eid, stage="dating", reason="mutual_social_contact", attraction=attraction, cohabit=False)
        return None
    stage = _stage(existing.get("stage"))
    formed = _int(existing.get("formed_tick"), now)
    stage_tick = _int(existing.get("stage_tick"), formed)
    if stage == "dating" and score >= 0.8 and closeness >= 0.76 and trust >= 0.72 and now - formed >= 90:
        return ensure_relationship(sim, left_eid, right_eid, stage="partner", reason="steady_social_contact", attraction=attraction, cohabit=True)
    if stage == "partner" and score >= 0.9 and closeness >= 0.88 and trust >= 0.86 and now - stage_tick >= 900:
        rng = random.Random(f"{getattr(sim, 'seed', 0)}:npc-marriage-progress:{relationship_pair_key(left_eid, right_eid)}:{now // 300}")
        if rng.random() < 0.22:
            return ensure_relationship(sim, left_eid, right_eid, stage="spouse", reason="long_term_partner", attraction=attraction, cohabit=True)
    return None


def incident_relationship_override(sim, observer_eid, incident):
    offender = _int((incident or {}).get("primary_actor_eid"), 0)
    victim = _int((incident or {}).get("victim_eid"), 0)
    if offender > 0 and are_romantic_partners(sim, observer_eid, offender):
        return {
            "kind": "look_away",
            "score": 1.0,
            "reason": "partner_loyalty_no_report",
            "target_eid": offender,
            "preferred_methods": (),
        }
    if victim > 0 and are_romantic_partners(sim, observer_eid, victim):
        return {
            "kind": "help_victim",
            "score": 1.0,
            "reason": "partner_in_danger",
            "target_eid": victim,
            "preferred_methods": ("reach_partner", "intervene", "first_aid"),
        }
    return None


def record_partner_combat_witnesses(sim, source_eid, target_eid, *, damage=0, x=None, y=None, z=None):
    source_partner = relationship_partner_eid(sim, source_eid)
    target_partner = relationship_partner_eid(sim, target_eid)
    positions = sim.ecs.get(Position)
    source_pos = positions.get(source_eid)
    target_pos = positions.get(target_eid)
    rows = (
        (target_partner, target_eid, source_eid, "ally_threatened"),
        (source_partner, source_eid, target_eid, "conflict_side"),
    )
    changed = 0
    now = int(getattr(sim, "tick", 0) or 0)
    for witness_eid, side_eid, against_eid, kind in rows:
        if witness_eid is None or witness_eid in {source_eid, target_eid}:
            continue
        witness_pos = positions.get(witness_eid)
        against_pos = positions.get(against_eid)
        side_pos = positions.get(side_eid)
        if not witness_pos or not against_pos or int(witness_pos.z) != int(against_pos.z):
            continue
        if source_pos and int(witness_pos.z) == int(source_pos.z):
            can_see_source = has_line_of_sight(sim, int(witness_pos.x), int(witness_pos.y), int(witness_pos.z), int(source_pos.x), int(source_pos.y), int(source_pos.z))
        else:
            can_see_source = False
        if target_pos and int(witness_pos.z) == int(target_pos.z):
            can_see_target = has_line_of_sight(sim, int(witness_pos.x), int(witness_pos.y), int(witness_pos.z), int(target_pos.x), int(target_pos.y), int(target_pos.z))
        else:
            can_see_target = False
        if not (can_see_source or can_see_target):
            continue
        memory = sim.ecs.get(NPCMemory).get(witness_eid)
        if memory is None:
            memory = NPCMemory()
            sim.ecs.add(witness_eid, memory)
        strength = min(1.0, 0.62 + (float(damage or 0) / 30.0))
        data = {
            "side_eid": side_eid,
            "against_eid": against_eid,
            "ally_eid": side_eid,
            "x": int(x if x is not None else getattr(against_pos, "x", 0)),
            "y": int(y if y is not None else getattr(against_pos, "y", 0)),
            "z": int(z if z is not None else getattr(against_pos, "z", 0)),
            "via": "partner_combat_loyalty",
        }
        memory.remember(tick=now, kind=kind, strength=strength, **data)
        ai = sim.ecs.get(AI).get(witness_eid)
        if ai is not None:
            ai.state = "protecting"
            ai.target_eid = against_eid
            ai.target = (int(getattr(against_pos, "x", data["x"])), int(getattr(against_pos, "y", data["y"])), int(getattr(against_pos, "z", data["z"])))
        will = sim.ecs.get(NPCWill).get(witness_eid)
        if will is not None:
            will.intent = "protecting"
            will.score = max(float(getattr(will, "score", 0.0) or 0.0), 96.0)
            will.target_eid = against_eid
            will.target = (int(getattr(against_pos, "x", data["x"])), int(getattr(against_pos, "y", data["y"])), int(getattr(against_pos, "z", data["z"])))
            will.last_tick = now
        _mark_actor_urgent(sim, witness_eid, family="will", reason="partner_combat_loyalty", ttl_ticks=18)
        _mark_actor_urgent(sim, witness_eid, family="move", reason="partner_combat_loyalty", ttl_ticks=18)
        _schedule_actor_due(sim, witness_eid, "will", delay_ticks=0, reason="partner_combat_loyalty")
        _schedule_actor_due(sim, witness_eid, "move", delay_ticks=0, reason="partner_combat_loyalty")
        changed += 1
    return changed


_HOMICIDE_CLOSE_RELATIONS = {
    "family",
    "partner",
    "spouse",
    "lover",
    "sibling",
    "parent",
    "child",
}
_HOMICIDE_WITNESS_RANGE = 14


def _homicide_bond_stake(bond):
    if not isinstance(bond, dict) or not bond:
        return 0.0, ""
    kind = str(bond.get("kind", "") or "").strip().lower()
    try:
        closeness = float(bond.get("closeness", 0.0) or 0.0)
        trust = float(bond.get("trust", 0.0) or 0.0)
        protectiveness = float(bond.get("protectiveness", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0, kind
    if kind in _HOMICIDE_CLOSE_RELATIONS:
        return max(0.72, closeness, trust, protectiveness), kind
    if kind in {"friend", "best_friend"}:
        stake = (closeness * 0.42) + (trust * 0.28) + (protectiveness * 0.3)
        return (stake if stake >= 0.68 else 0.0), kind
    if kind in {"crew", "gang", "cult"}:
        stake = (closeness * 0.32) + (trust * 0.24) + (protectiveness * 0.44)
        return (stake if stake >= 0.76 else 0.0), kind
    if kind in {"coworker", "neighbor"}:
        stake = (closeness * 0.35) + (trust * 0.25) + (protectiveness * 0.4)
        return (stake if stake >= 0.84 else 0.0), kind
    stake = (closeness * 0.3) + (trust * 0.25) + (protectiveness * 0.45)
    return (stake if stake >= 0.88 else 0.0), kind


def _clean_explicit_witness_eids(values):
    if values is None:
        return set()
    if not isinstance(values, (list, tuple, set)):
        values = (values,)
    cleaned = set()
    for value in values:
        try:
            cleaned.add(int(value))
        except (TypeError, ValueError):
            continue
    return cleaned


def record_homicide_social_ripples(
    sim,
    source_eid,
    target_eid,
    *,
    x=None,
    y=None,
    z=None,
    reason=None,
    explicit_witness_eids=(),
):
    try:
        source_eid = int(source_eid)
        target_eid = int(target_eid)
    except (TypeError, ValueError):
        return 0
    if source_eid == target_eid:
        return 0

    positions = sim.ecs.get(Position)
    socials = sim.ecs.get(NPCSocial)
    source_pos = positions.get(source_eid)
    fallback_z = getattr(source_pos, "z", 0)
    try:
        death_x = int(x if x is not None else getattr(source_pos, "x", 0))
        death_y = int(y if y is not None else getattr(source_pos, "y", 0))
        death_z = int(z if z is not None else fallback_z)
    except (TypeError, ValueError):
        death_x = int(getattr(source_pos, "x", 0))
        death_y = int(getattr(source_pos, "y", 0))
        death_z = int(fallback_z or 0)

    explicit = _clean_explicit_witness_eids(explicit_witness_eids)
    now = int(getattr(sim, "tick", 0) or 0)
    changed = 0
    source_name = _entity_display_name(sim, source_eid, title_case=True) or "someone"
    target_name = _entity_display_name(sim, target_eid, title_case=True) or "someone"

    for witness_eid, social in list(socials.items()):
        if witness_eid in {source_eid, target_eid}:
            continue
        bond = social.bonds.get(target_eid)
        stake, relation = _homicide_bond_stake(bond)
        if stake <= 0.0:
            continue

        witness_pos = positions.get(witness_eid)
        if not witness_pos or int(witness_pos.z) != death_z:
            continue
        if abs(int(witness_pos.x) - death_x) + abs(int(witness_pos.y) - death_y) > _HOMICIDE_WITNESS_RANGE:
            continue

        knows_source = witness_eid in explicit
        if not knows_source and source_pos and int(getattr(source_pos, "z", death_z)) == death_z:
            if (
                abs(int(witness_pos.x) - int(source_pos.x))
                + abs(int(witness_pos.y) - int(source_pos.y))
                > _HOMICIDE_WITNESS_RANGE
            ):
                continue
            knows_source = has_line_of_sight(
                sim,
                int(witness_pos.x),
                int(witness_pos.y),
                int(witness_pos.z),
                int(source_pos.x),
                int(source_pos.y),
                int(source_pos.z),
            ) and has_line_of_sight(
                sim,
                int(witness_pos.x),
                int(witness_pos.y),
                int(witness_pos.z),
                death_x,
                death_y,
                death_z,
            )
        if not knows_source:
            continue

        memory = sim.ecs.get(NPCMemory).get(witness_eid)
        if memory is None:
            memory = NPCMemory()
            sim.ecs.add(witness_eid, memory)
        strength = min(1.0, 0.78 + (stake * 0.22))
        common = {
            "side_eid": target_eid,
            "against_eid": source_eid,
            "ally_eid": target_eid,
            "victim_eid": target_eid,
            "killer_eid": source_eid,
            "source_eid": source_eid,
            "target_eid": target_eid,
            "x": death_x,
            "y": death_y,
            "z": death_z,
            "relation": relation,
            "via": "witnessed_homicide",
            "source_event": "npc_killed",
            "context": "homicide",
            "action": "homicide",
            "danger": "high",
            "permanent": True,
        }
        memory.remember(tick=now, kind="homicide_grief", strength=strength, **common)
        memory.remember(tick=now, kind="conflict_side", strength=strength, **common)
        memory.remember(
            tick=now,
            kind="actor_reputation",
            strength=strength,
            actor_eid=source_eid,
            approval=-1.0,
            against_eid=target_eid,
            victim_eid=target_eid,
            killer_eid=source_eid,
            x=death_x,
            y=death_y,
            z=death_z,
            relation=relation,
            via="witnessed_homicide",
            source_event="npc_killed",
            context="homicide",
            permanent=True,
        )

        will = sim.ecs.get(NPCWill).get(witness_eid)
        if will is not None:
            will.last_tick = now - 1
        _mark_actor_urgent(sim, witness_eid, family="will", reason="known_homicide", ttl_ticks=30)
        _mark_actor_urgent(sim, witness_eid, family="move", reason="known_homicide", ttl_ticks=30)
        _schedule_actor_due(sim, witness_eid, "will", delay_ticks=0, reason="known_homicide")
        _schedule_actor_due(sim, witness_eid, "move", delay_ticks=0, reason="known_homicide")
        sim.emit(Event(
            "npc_homicide_social_ripple",
            npc_eid=witness_eid,
            victim_eid=target_eid,
            killer_eid=source_eid,
            relation=relation,
            strength=strength,
            source_name=source_name,
            target_name=target_name,
            reason=str(reason or "").strip().lower(),
            x=death_x,
            y=death_y,
            z=death_z,
        ))
        changed += 1
    return changed


def _memory_has_homicide_grief(memory, *, incident_id=None, victim_eid=None, killer_eid=None):
    if memory is None:
        return False
    try:
        incident_key = int(incident_id) if incident_id is not None else None
    except (TypeError, ValueError):
        incident_key = None
    try:
        victim_key = int(victim_eid) if victim_eid is not None else None
        killer_key = int(killer_eid) if killer_eid is not None else None
    except (TypeError, ValueError):
        victim_key = None
        killer_key = None
    for entry in list(getattr(memory, "entries", ()) or ()):
        if str(entry.get("kind", "") or "").strip().lower() != "homicide_grief":
            continue
        data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
        try:
            if incident_key is not None and int(data.get("incident_id")) == incident_key:
                return True
        except (TypeError, ValueError):
            pass
        try:
            if (
                victim_key is not None
                and killer_key is not None
                and int(data.get("victim_eid")) == victim_key
                and int(data.get("killer_eid")) == killer_key
            ):
                return True
        except (TypeError, ValueError):
            pass
    return False


def record_homicide_incident_knowledge(
    sim,
    learner_eid,
    incident,
    *,
    source_kind="",
    source_eid=None,
    confidence=1.0,
    propagation_depth=0,
):
    if not isinstance(incident, dict):
        return 0
    if str(incident.get("kind", "") or "").strip().lower() != "homicide":
        return 0
    try:
        learner_eid = int(learner_eid)
        victim_eid = int(incident.get("victim_eid"))
        killer_eid = int(incident.get("primary_actor_eid"))
    except (TypeError, ValueError):
        return 0
    if learner_eid in {victim_eid, killer_eid} or victim_eid == killer_eid:
        return 0

    social = sim.ecs.get(NPCSocial).get(learner_eid)
    bond = social.bonds.get(victim_eid) if social is not None else None
    stake, relation = _homicide_bond_stake(bond)
    if stake <= 0.0:
        return 0

    memory = sim.ecs.get(NPCMemory).get(learner_eid)
    if memory is None:
        memory = NPCMemory()
        sim.ecs.add(learner_eid, memory)
    incident_id = incident.get("id")
    if _memory_has_homicide_grief(memory, incident_id=incident_id, victim_eid=victim_eid, killer_eid=killer_eid):
        return 0

    try:
        depth = max(0, int(propagation_depth))
    except (TypeError, ValueError):
        depth = 0
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.5
    x = int(incident.get("x", 0) or 0)
    y = int(incident.get("y", 0) or 0)
    z = int(incident.get("z", 0) or 0)
    strength = max(0.62, min(0.96, 0.6 + (stake * 0.24) + (confidence * 0.12) - (depth * 0.04)))
    now = int(getattr(sim, "tick", 0) or 0)
    common = {
        "incident_id": incident_id,
        "side_eid": victim_eid,
        "against_eid": killer_eid,
        "ally_eid": victim_eid,
        "victim_eid": victim_eid,
        "killer_eid": killer_eid,
        "source_eid": source_eid,
        "target_eid": victim_eid,
        "x": x,
        "y": y,
        "z": z,
        "relation": relation,
        "via": "incident_homicide_rumor",
        "source_kind": str(source_kind or "").strip().lower(),
        "source_event": "knowledge_incident_learned",
        "context": "homicide",
        "action": "homicide",
        "danger": "high",
        "confidence": round(confidence, 3),
        "propagation_depth": depth,
        "permanent": True,
    }
    memory.remember(tick=now, kind="homicide_grief", strength=strength, **common)
    memory.remember(tick=now, kind="conflict_side", strength=strength, **common)
    memory.remember(
        tick=now,
        kind="actor_reputation",
        strength=strength,
        actor_eid=killer_eid,
        approval=round(max(-0.98, -0.74 - (strength * 0.18)), 3),
        against_eid=victim_eid,
        victim_eid=victim_eid,
        killer_eid=killer_eid,
        incident_id=incident_id,
        x=x,
        y=y,
        z=z,
        relation=relation,
        via="incident_homicide_rumor",
        source_kind=str(source_kind or "").strip().lower(),
        source_event="knowledge_incident_learned",
        context="homicide",
        confidence=round(confidence, 3),
        propagation_depth=depth,
        permanent=True,
    )
    will = sim.ecs.get(NPCWill).get(learner_eid)
    if will is not None:
        will.last_tick = now - 1
    _mark_actor_urgent(sim, learner_eid, family="will", reason="known_homicide_rumor", ttl_ticks=30)
    _mark_actor_urgent(sim, learner_eid, family="move", reason="known_homicide_rumor", ttl_ticks=30)
    _schedule_actor_due(sim, learner_eid, "will", delay_ticks=0, reason="known_homicide_rumor")
    _schedule_actor_due(sim, learner_eid, "move", delay_ticks=0, reason="known_homicide_rumor")
    sim.emit(Event(
        "npc_homicide_social_ripple",
        npc_eid=learner_eid,
        victim_eid=victim_eid,
        killer_eid=killer_eid,
        relation=relation,
        strength=strength,
        source_kind=str(source_kind or "").strip().lower(),
        propagation_depth=depth,
        confidence=round(confidence, 3),
        reason="incident_knowledge",
        x=x,
        y=y,
        z=z,
    ))
    return 1


def should_block_solo_vehicle_for_partner(sim, eid, target=None):
    partner_eid = relationship_partner_eid(sim, eid, minimum_stage="dating")
    if partner_eid is None:
        return False
    positions = sim.ecs.get(Position)
    pos = positions.get(eid)
    partner_pos = positions.get(partner_eid)
    if not pos or not partner_pos or int(pos.z) != int(partner_pos.z):
        return False
    distance = abs(int(pos.x) - int(partner_pos.x)) + abs(int(pos.y) - int(partner_pos.y))
    if distance > 3:
        return False
    actor_ai = sim.ecs.get(AI).get(eid)
    partner_ai = sim.ecs.get(AI).get(partner_eid)
    actor_state = str(getattr(actor_ai, "state", "") or "").strip().lower() if actor_ai else ""
    partner_state = str(getattr(partner_ai, "state", "") or "").strip().lower() if partner_ai else ""
    if actor_state in {"seeking_social", "following"} and _int(getattr(actor_ai, "target_eid", 0), 0) == _int(partner_eid):
        return True
    if partner_state in {"seeking_social", "following"} and _int(getattr(partner_ai, "target_eid", 0), 0) == _int(eid):
        return True
    if target is not None and isinstance(target, (tuple, list)) and len(target) >= 3:
        partner_target = getattr(partner_ai, "target", None) if partner_ai else None
        if isinstance(partner_target, (tuple, list)) and len(partner_target) >= 3:
            return tuple(int(v) for v in partner_target[:3]) == tuple(int(v) for v in target[:3])
    return False


def acknowledgement_quote(sim, speaker_eid, target_eid, stage):
    stage = _stage(stage)
    bank = _SPOUSE_ACK_LINES + _ACK_LINES if stage == "spouse" else _ACK_LINES
    key = relationship_pair_key(speaker_eid, target_eid)
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:partner-ack:{key}:{speaker_eid}:{target_eid}:{int(getattr(sim, 'tick', 0) or 0) // 30}")
    return rng.choice(bank)


class NPCRelationshipSystem(System):
    """Runtime glue for pair acknowledgements and relationship progression."""

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("entity_moved", self.on_entity_moved)
        self.sim.events.subscribe("npc_socialized", self.on_npc_socialized)

    def on_npc_socialized(self, event):
        left = event.data.get("npc_eid")
        right = event.data.get("partner_eid")
        if left is None or right is None:
            return
        maybe_progress_relationship_after_socialized(self.sim, _int(left), _int(right))

    def on_entity_moved(self, event):
        moved = _int(event.data.get("eid"), 0)
        if moved <= 0 or _is_player(self.sim, moved):
            return
        row = current_relationship_for_actor(self.sim, moved)
        if not row:
            return
        partner = _int(row.get("right_eid"), 0) if _int(row.get("left_eid"), 0) == moved else _int(row.get("left_eid"), 0)
        if partner <= 0:
            return
        positions = self.sim.ecs.get(Position)
        moved_pos = positions.get(moved)
        partner_pos = positions.get(partner)
        if not moved_pos or not partner_pos or int(moved_pos.z) != int(partner_pos.z):
            return
        old_z = _int(event.data.get("old_z"), int(moved_pos.z))
        if old_z != int(partner_pos.z):
            old_visible = False
        else:
            old_visible = has_line_of_sight(
                self.sim,
                int(partner_pos.x),
                int(partner_pos.y),
                int(partner_pos.z),
                _int(event.data.get("old_x"), int(moved_pos.x)),
                _int(event.data.get("old_y"), int(moved_pos.y)),
                old_z,
            )
        new_visible = has_line_of_sight(
            self.sim,
            int(partner_pos.x),
            int(partner_pos.y),
            int(partner_pos.z),
            int(moved_pos.x),
            int(moved_pos.y),
            int(moved_pos.z),
        )
        if old_visible or not new_visible:
            return
        key = str(row.get("relationship_key") or relationship_pair_key(moved, partner))
        live = relationship_state(self.sim).get(key)
        if not isinstance(live, dict):
            return
        ack = live.setdefault("acknowledgement", {})
        now = int(getattr(self.sim, "tick", 0) or 0)
        last = _int(ack.get("last_tick"), -10_000)
        if now - last < _ACK_COOLDOWN_TICKS:
            return
        ack["last_tick"] = now
        stage = _stage(live.get("stage"))
        quote = acknowledgement_quote(self.sim, partner, moved, stage)
        self.sim.emit(Event(
            "npc_partner_acknowledged",
            speaker_eid=partner,
            partner_eid=moved,
            relationship_stage=stage,
            quote=quote,
            x=int(partner_pos.x),
            y=int(partner_pos.y),
            z=int(partner_pos.z),
            speaker_name=_entity_display_name(self.sim, partner, title_case=True),
            partner_name=_entity_display_name(self.sim, moved, title_case=True),
        ))


__all__ = [
    "NPCRelationshipSystem",
    "RELATIONSHIP_STAGES",
    "actor_presentation_gender",
    "are_romantic_partners",
    "attraction_score",
    "current_relationship_for_actor",
    "ensure_relationship",
    "incident_relationship_override",
    "maybe_progress_relationship_after_socialized",
    "mutual_presentation_taste_match",
    "presentation_satisfies_taste",
    "record_homicide_incident_knowledge",
    "record_homicide_social_ripples",
    "record_partner_combat_witnesses",
    "relationship_between",
    "relationship_pair_key",
    "relationship_partner_eid",
    "relationship_state",
    "relationship_taste_state",
    "romantic_taste_for_actor",
    "seed_relationship_from_home_bond",
    "should_block_solo_vehicle_for_partner",
    "try_relationship_cohabitation",
]
