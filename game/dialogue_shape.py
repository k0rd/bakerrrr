"""Context-shaped NPC dialogue helpers.

This module is intentionally small and read-only.  It does not decide gameplay;
it turns already-known NPC state into short conversational surfaces so the
player can feel the social simulation without every line becoming exposition.
"""

from __future__ import annotations

import random

from game.components import AI, CreatureIdentity, IncidentKnowledge, NPCMemory, NPCNeeds, NPCSocial, NPCTraits, Occupation, Position, SkillProfile
from game.human_identity import is_human_identity, normalize_gender_identity, pronoun_format_slots
from game.incident_runtime import incident_knowledge_label, incident_record


_AUTHORITY_ROLES = {"guard", "security", "officer", "police", "deputy", "marshal"}
_SERVICE_ROLES = {"clerk", "cashier", "merchant", "shopkeeper", "manager", "worker"}
_TRADE_ROLES = {
    "bartender",
    "barista",
    "broker",
    "cashier",
    "clerk",
    "contractor",
    "doctor",
    "mechanic",
    "merchant",
    "server",
    "shopkeeper",
    "vendor",
    "worker",
}
_MANAGEMENT_ROLES = {"boss", "manager", "owner", "supervisor"}
_LOGISTICS_ROLES = {"courier", "driver", "hauler", "rail_worker", "transit_worker"}
_DIALOGUE_KNOWLEDGE_DOMAINS = (
    "local_economy",
    "business_reputation",
    "services",
    "security",
    "opportunities",
    "social_graph",
    "incident",
    "workplace",
)
_DIALOGUE_COMPETENCE_TIERS = ("none", "rumor", "familiar", "skilled")
_DIALOGUE_COMPETENCE_RANK = {name: index for index, name in enumerate(_DIALOGUE_COMPETENCE_TIERS)}
_RAPPORT_REACTION_TOPICS = {"rapport", "check_in", "day_feel", "job_feel", "roots", "off_shift", "care_about", "read_player"}
_MISSTEP_REACTION_TOPICS = {"pry", "provoke", "intimidate", "insult", "weird"}
_SOCIAL_ACCESS_REACTION_TOPICS = {"contacts", "introduction", "vouch"}
_DEEP_REACTION_TOPICS = {"care_about", "read_player"}
_REFLECTIVE_REACTION_TOPICS = {"job_feel", "roots"}
_LIGHT_REACTION_TOPICS = {"rapport", "check_in", "day_feel", "off_shift"}
_TRIVIAL_RELATIONSHIP_EPISODES = {"met_directly", "introduced_to_me"}
_POSITIVE_RELATIONSHIP_EPISODES = {
    "opened_up_about_work",
    "opened_up_about_roots",
    "opened_up_personally",
    "told_me_how_they_see_me",
    "offered_contact",
    "offered_introduction",
    "offered_vouch",
}
_NEGATIVE_RELATIONSHIP_EPISODES = {
    "warned_me_off",
    "i_pushed_too_far",
    "i_pried_into_them",
    "i_provoked_them",
    "i_threatened_them",
    "i_insulted_them",
}


def _text(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _clamp01(value):
    return max(0.0, min(1.0, _float(value, 0.0)))


def _tier_at_least(current, candidate):
    current = _text(current, "none").lower() or "none"
    candidate = _text(candidate, "none").lower() or "none"
    if _DIALOGUE_COMPETENCE_RANK.get(candidate, 0) > _DIALOGUE_COMPETENCE_RANK.get(current, 0):
        return candidate
    return current


def dialogue_knowledge_domains():
    return tuple(_DIALOGUE_KNOWLEDGE_DOMAINS)


def dialogue_competence_tiers():
    return tuple(_DIALOGUE_COMPETENCE_TIERS)


def dialogue_persona_domain_competence(persona_agenda, domain):
    persona_agenda = persona_agenda if isinstance(persona_agenda, dict) else {}
    domain = _text(domain).lower()
    if not domain:
        return "none"
    domains = persona_agenda.get("domain_competence")
    domains = domains if isinstance(domains, dict) else {}
    tier = _text(domains.get(domain, "none"), "none").lower()
    return tier if tier in _DIALOGUE_COMPETENCE_RANK else "none"


def _seeded_unit(seed_text):
    return random.Random(str(seed_text or "0")).random()


def _entity_name(sim, eid, *, fallback="someone"):
    if eid is None:
        return fallback
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if identity is None:
        return fallback
    for attr in ("personal_name", "common_name", "species"):
        name = _text(getattr(identity, attr, ""))
        if name:
            return name
    return fallback


def _distance_to_player(sim, x, y, z=0):
    player_eid = getattr(sim, "player_eid", None)
    if player_eid is None:
        return None
    player_pos = sim.ecs.get(Position).get(player_eid)
    if not player_pos:
        return None
    if _int(getattr(player_pos, "z", 0)) != _int(z, 0):
        return None
    return abs(_int(x) - _int(getattr(player_pos, "x", 0))) + abs(_int(y) - _int(getattr(player_pos, "y", 0)))


def _direction_from_player(sim, x, y, z=0):
    player_eid = getattr(sim, "player_eid", None)
    if player_eid is None:
        return "nearby"
    player_pos = sim.ecs.get(Position).get(player_eid)
    if not player_pos or _int(getattr(player_pos, "z", 0)) != _int(z, 0):
        return "nearby"
    dx = _int(x) - _int(getattr(player_pos, "x", 0))
    dy = _int(y) - _int(getattr(player_pos, "y", 0))
    if abs(dx) <= 1 and abs(dy) <= 1:
        return "right here"
    horiz = "east" if dx > 0 else "west" if dx < 0 else ""
    vert = "south" if dy > 0 else "north" if dy < 0 else ""
    if horiz and vert:
        return f"{vert}-{horiz}"
    return horiz or vert or "nearby"


def _incident_label(record, incident):
    return incident_knowledge_label(record, incident)


def _rapport_chunk_profile(sim, npc_eid, context):
    context = context if isinstance(context, dict) else {}
    area_type = _text(context.get("area_type", "")).lower()
    district_type = _text(context.get("district_type", "")).lower()
    if area_type and district_type:
        return area_type, district_type
    pos = sim.ecs.get(Position).get(npc_eid) if sim is not None else None
    if pos is not None and hasattr(sim, "world") and hasattr(sim, "chunk_coords"):
        try:
            chunk = sim.world.get_chunk(*sim.chunk_coords(int(pos.x), int(pos.y)))
        except Exception:
            chunk = {}
        district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
        if isinstance(district, dict):
            area_type = area_type or _text(district.get("area_type", "city")).lower() or "city"
            district_type = district_type or _text(district.get("district_type", "unknown")).lower() or "unknown"
    return area_type or "city", district_type or "unknown"


def _best_incident_context(sim, npc_eid):
    knowledge = sim.ecs.get(IncidentKnowledge).get(npc_eid)
    if not knowledge or not isinstance(getattr(knowledge, "records", None), dict):
        return None
    best = None
    for incident_id, record in knowledge.records.items():
        if not isinstance(record, dict):
            continue
        incident = incident_record(sim, incident_id) or {}
        severity = max(_int(record.get("severity"), 0), _int(incident.get("severity"), 0) if isinstance(incident, dict) else 0)
        urgency = _float(record.get("urgency"), 0.0)
        social = _float(record.get("social_interest"), 0.0)
        firsthand = bool(record.get("firsthand"))
        confidence = _float(record.get("confidence"), 0.0)
        score = (severity / 100.0) * 0.36 + urgency * 0.34 + social * 0.2 + confidence * 0.08 + (0.08 if firsthand else 0.0)
        learned_tick = _int(record.get("last_learned_tick", record.get("learned_tick", 0)), 0)
        candidate = (score, learned_tick, incident_id, record, incident)
        if best is None or candidate > best:
            best = candidate
    if best is None:
        return None
    _score, _tick, incident_id, record, incident = best
    return {
        "incident_id": incident_id,
        "record": record,
        "incident": incident if isinstance(incident, dict) else {},
        "label": _incident_label(record, incident if isinstance(incident, dict) else {}),
        "firsthand": bool(record.get("firsthand")),
        "confidence": _float(record.get("confidence"), 0.0),
        "urgency": _float(record.get("urgency"), 0.0),
        "social_interest": _float(record.get("social_interest"), 0.0),
        "severity": max(_int(record.get("severity"), 0), _int((incident or {}).get("severity"), 0) if isinstance(incident, dict) else 0),
        "source_kind": _text(record.get("source_kind", "")).lower(),
        "propagation_depth": _int(record.get("propagation_depth"), 0),
        "officially_reported": bool((incident or {}).get("officially_reported")) if isinstance(incident, dict) else False,
        "x": record.get("x", (incident or {}).get("x") if isinstance(incident, dict) else None),
        "y": record.get("y", (incident or {}).get("y") if isinstance(incident, dict) else None),
        "z": record.get("z", (incident or {}).get("z") if isinstance(incident, dict) else 0),
    }


def build_dialogue_shape(sim, npc_eid, *, context=None):
    """Return short, player-facing dialogue facts for an NPC.

    The result is a dict because the monolithic dialogue system already passes
    a context dict around.  Keep this read-only and deterministic.
    """
    context = dict(context or {})
    ai = sim.ecs.get(AI).get(npc_eid)
    role = _text(getattr(ai, "role", context.get("role_id", "local"))).lower() or "local"
    tone = _text(context.get("tone", "neutral")).lower() or "neutral"
    pressure = _text(context.get("pressure_tier", "low")).lower() or "low"
    incident = _best_incident_context(sim, npc_eid)
    shape = {
        "role": role,
        "tone": tone,
        "pressure_tier": pressure,
        "has_incident": bool(incident),
        "opening_lines": [],
        "local_line": "",
        "concern_line": "",
        "debug_tags": [],
    }
    if incident:
        label = incident["label"]
        firsthand = incident["firsthand"]
        urgency = incident["urgency"]
        social = incident["social_interest"]
        confidence = incident["confidence"]
        source_kind = incident["source_kind"]
        depth = incident["propagation_depth"]
        reported = incident["officially_reported"]
        where = "nearby"
        if incident.get("x") is not None and incident.get("y") is not None:
            direction = _direction_from_player(sim, incident.get("x"), incident.get("y"), incident.get("z", 0))
            dist = _distance_to_player(sim, incident.get("x"), incident.get("y"), incident.get("z", 0))
            if dist is not None and dist > 1:
                where = f"{direction}, about {dist} blocks"
            else:
                where = direction

        if urgency >= 0.62:
            if role in _AUTHORITY_ROLES:
                line = f"Stay clear. I am checking out {label} {where}, and I do not need another witness in the way."
            elif reported:
                line = f"People already called this in. If you are not tied to that {label}, do not linger."
            else:
                line = f"Something ugly happened {where}. Keep moving and keep your hands empty."
            shape["opening_lines"].append(line)
            shape["concern_line"] = line
            shape["debug_tags"].append("urgent_incident")
        elif social >= 0.34:
            if source_kind == "participant":
                shape["debug_tags"].append("participant_incident_suppressed")
            else:
                if source_kind == "victim":
                    line = f"That {label} was done to me. I am not making it smaller just because the room went quiet."
                elif firsthand:
                    line = f"I saw enough of that {label} to keep my voice down."
                elif depth > 0 or source_kind in {"social_rumor", "rumor"}:
                    line = f"People are talking about some {label} {where}. Could be bent by now, but they keep repeating it."
                elif confidence < 0.48:
                    line = f"Something about {label} is going around, but I would not put my name under it."
                else:
                    line = f"Word is there was {label} {where}, and the quiet after it feels worked-over."
                shape["local_line"] = line
                if tone in {"friendly", "open", "neutral"}:
                    shape["opening_lines"].append(line)
                shape["debug_tags"].append("social_incident")

    if not shape["opening_lines"]:
        if role in _SERVICE_ROLES and pressure == "high":
            shape["opening_lines"].append("If you need something, make it quick.")
            shape["debug_tags"].append("service_pressure")
        elif role in _AUTHORITY_ROLES and tone in {"wary", "guarded"}:
            shape["opening_lines"].append("Keep your hands where I can see them and talk plain.")
            shape["debug_tags"].append("authority_guarded")

    # Deterministically avoid always choosing the same extra line if several
    # future producers add lines.
    if len(shape["opening_lines"]) > 1:
        rng = random.Random(f"{getattr(sim, 'seed', 0)}:dialogue-shape:{npc_eid}:{getattr(sim, 'tick', 0)}")
        rng.shuffle(shape["opening_lines"])
    shape["opening_lines"] = tuple(line for line in shape["opening_lines"] if _text(line))[:2]
    return shape


def build_rapport_shape(sim, npc_eid, *, context=None):
    """Return a lightweight deterministic conversational-style profile."""
    context = dict(context or {})
    identity = sim.ecs.get(CreatureIdentity).get(npc_eid)
    if not is_human_identity(identity):
        return {}

    ai = context.get("ai") or sim.ecs.get(AI).get(npc_eid)
    occupation = context.get("occupation") or sim.ecs.get(Occupation).get(npc_eid)
    needs = context.get("npc_needs") or sim.ecs.get(NPCNeeds).get(npc_eid)
    traits = context.get("npc_traits") or sim.ecs.get(NPCTraits).get(npc_eid) or NPCTraits()
    role_id = _text(getattr(ai, "role", context.get("role_id", "local"))).lower() or "local"
    career_text = _text(getattr(occupation, "career", context.get("career_text", ""))).lower()
    gender_identity = normalize_gender_identity(getattr(identity, "gender_identity", ""), default="nonbinary")
    area_type, district_type = _rapport_chunk_profile(sim, npc_eid, context)
    seed_base = (
        f"{getattr(sim, 'seed', 0)}:rapport:{npc_eid}:{gender_identity}:"
        f"{role_id}:{career_text}:{area_type}:{district_type}"
    )

    empathy = _clamp01(getattr(traits, "empathy", 0.5))
    discipline = _clamp01(getattr(traits, "discipline", 0.5))
    bravery = _clamp01(getattr(traits, "bravery", 0.5))
    social_need = _float(getattr(needs, "social", 55.0), 55.0)
    energy_need = _float(getattr(needs, "energy", 60.0), 60.0)
    safety_need = _float(getattr(needs, "safety", 70.0), 70.0)
    hunger_need = _float(getattr(needs, "hunger", 86.0), 86.0)
    thirst_need = _float(getattr(needs, "thirst", 90.0), 90.0)
    social_hunger = _clamp01((52.0 - social_need) / 52.0)
    fatigue = _clamp01((46.0 - energy_need) / 46.0)
    safety_stress = _clamp01((54.0 - safety_need) / 54.0)
    survival_pressure = max(
        _clamp01((54.0 - hunger_need) / 54.0),
        _clamp01((54.0 - thirst_need) / 54.0),
    )
    guarded = bool(context.get("guarded"))
    pressure_tier = _text(context.get("pressure_tier", "low")).lower() or "low"
    pressure_penalty = {
        "low": 0.0,
        "medium": 0.06,
        "high": 0.14,
    }.get(pressure_tier, 0.0)

    role_pride_bonus = 0.0
    if role_id in {"guard", "security", "officer", "manager"}:
        role_pride_bonus += 0.1
    elif role_id in {"worker", "merchant", "clerk", "shopkeeper"}:
        role_pride_bonus += 0.06

    local_bonus = 0.0
    if role_id in {"resident", "neighbor"}:
        local_bonus += 0.16
    if context.get("home_name"):
        local_bonus += 0.12
    if context.get("workplace_name"):
        local_bonus += 0.08

    chattiness = _clamp01(
        0.16
        + (_seeded_unit(f"{seed_base}:chat") * 0.56)
        + (empathy * 0.16)
        - (discipline * 0.08)
        + (social_hunger * 0.18)
        - (0.11 if guarded else 0.0)
        - pressure_penalty
        - (survival_pressure * 0.12)
    )
    privacy = _clamp01(
        0.18
        + (_seeded_unit(f"{seed_base}:privacy") * 0.58)
        + (discipline * 0.12)
        + (safety_stress * 0.18)
        + (0.14 if guarded else 0.0)
        - (social_hunger * 0.08)
        + (survival_pressure * 0.08)
    )
    profession_pride = _clamp01(
        0.14
        + (_seeded_unit(f"{seed_base}:pride") * 0.56)
        + role_pride_bonus
        + (discipline * 0.14)
        + (0.08 if career_text else 0.0)
        - (fatigue * 0.08)
    )
    local_attachment = _clamp01(
        0.12
        + (_seeded_unit(f"{seed_base}:local") * 0.54)
        + local_bonus
        - (0.06 if district_type in {"tourist", "transit"} else 0.0)
    )
    playfulness = _clamp01(
        0.08
        + (_seeded_unit(f"{seed_base}:play") * 0.58)
        + (empathy * 0.12)
        - (discipline * 0.08)
        - (fatigue * 0.1)
        - (safety_stress * 0.1)
        - (survival_pressure * 0.12)
        - pressure_penalty
    )

    mood_score = _clamp01(
        0.28
        + (_seeded_unit(f"{seed_base}:mood") * 0.34)
        + (social_hunger * 0.1)
        - (fatigue * 0.16)
        - (safety_stress * 0.16)
        - (survival_pressure * 0.16)
        - pressure_penalty
        + (empathy * 0.06)
    )
    if mood_score < 0.24:
        day_mood = "frayed"
    elif mood_score < 0.42:
        day_mood = "tired"
    elif mood_score < 0.62:
        day_mood = "steady"
    elif mood_score < 0.78:
        day_mood = "light"
    else:
        day_mood = "warm"

    work_score = _clamp01(
        0.22
        + (_seeded_unit(f"{seed_base}:work") * 0.34)
        + (profession_pride * 0.26)
        + (discipline * 0.08)
        - (fatigue * 0.1)
    )
    if not career_text:
        work_attitude = "improvised"
    elif work_score >= 0.76:
        work_attitude = "proud"
    elif discipline >= 0.64 and role_id in {"guard", "security", "officer", "manager"}:
        work_attitude = "duty_bound"
    elif work_score >= 0.56:
        work_attitude = "practical"
    elif fatigue >= 0.52 or day_mood in {"tired", "frayed"}:
        work_attitude = "worn"
    elif playfulness >= 0.62 and local_attachment < 0.44:
        work_attitude = "restless"
    else:
        work_attitude = "stuck"

    return {
        "chattiness": chattiness,
        "privacy": privacy,
        "profession_pride": profession_pride,
        "local_attachment": local_attachment,
        "playfulness": playfulness,
        "day_mood": day_mood,
        "work_attitude": work_attitude,
    }


def _skill_rating(sim, npc_eid, skill_id):
    profile = sim.ecs.get(SkillProfile).get(npc_eid) if sim is not None else None
    ratings = getattr(profile, "ratings", None)
    if isinstance(ratings, dict):
        return _float(ratings.get(skill_id), 0.0)
    return 0.0


def build_dialogue_persona_agenda(sim, npc_eid, *, context=None):
    """Return deterministic agenda and knowledge reads for dialogue routing.

    This is deliberately a read model, not a life-sim state machine.  It
    projects enough occupation, role, needs, and pressure texture for dialogue
    to feel self-interested without persisting new per-NPC goals.
    """
    context = dict(context or {})
    identity = sim.ecs.get(CreatureIdentity).get(npc_eid) if sim is not None else None
    if not is_human_identity(identity):
        return {}

    ai = context.get("ai") or sim.ecs.get(AI).get(npc_eid)
    occupation = context.get("occupation") or sim.ecs.get(Occupation).get(npc_eid)
    needs = context.get("npc_needs") or sim.ecs.get(NPCNeeds).get(npc_eid) or NPCNeeds()
    traits = context.get("npc_traits") or sim.ecs.get(NPCTraits).get(npc_eid) or NPCTraits()
    role_id = _text(getattr(ai, "role", context.get("role_id", "local"))).lower() or "local"
    career_text = _text(getattr(occupation, "career", context.get("career_text", ""))).lower()
    organization_role = _text(context.get("organization_role", "")).lower()
    area_type, district_type = _rapport_chunk_profile(sim, npc_eid, context)

    role_tokens = {
        token
        for source in (role_id, career_text, organization_role)
        for token in str(source or "").replace("-", "_").split("_")
        if token
    }
    domain_competence = {domain: "none" for domain in _DIALOGUE_KNOWLEDGE_DOMAINS}

    def raise_domain(domain, tier):
        if domain in domain_competence:
            domain_competence[domain] = _tier_at_least(domain_competence.get(domain), tier)

    if career_text or context.get("workplace_name") or context.get("workplace_prop"):
        raise_domain("workplace", "familiar")
        raise_domain("services", "rumor")
    if organization_role in _MANAGEMENT_ROLES or role_id in _MANAGEMENT_ROLES or "owner" in role_tokens:
        raise_domain("workplace", "skilled")
        raise_domain("local_economy", "skilled")
        raise_domain("business_reputation", "skilled")
        raise_domain("services", "familiar")
    if role_id in _SERVICE_ROLES or role_id in _TRADE_ROLES or career_text in _TRADE_ROLES or role_tokens & _TRADE_ROLES:
        raise_domain("local_economy", "familiar")
        raise_domain("business_reputation", "familiar")
        raise_domain("services", "skilled" if role_id in {"clerk", "merchant", "shopkeeper", "cashier"} else "familiar")
        raise_domain("workplace", "familiar")
    if role_id in _AUTHORITY_ROLES or career_text in _AUTHORITY_ROLES or role_tokens & _AUTHORITY_ROLES:
        raise_domain("security", "skilled")
        raise_domain("incident", "familiar")
        raise_domain("business_reputation", "rumor")
        raise_domain("local_economy", "rumor")
    if role_id in _LOGISTICS_ROLES or career_text in _LOGISTICS_ROLES or role_tokens & _LOGISTICS_ROLES:
        raise_domain("services", "familiar")
        raise_domain("opportunities", "rumor")
        raise_domain("local_economy", "rumor")
    if role_id in {"resident", "neighbor", "local", "civilian"} or context.get("home_name"):
        raise_domain("local_economy", "rumor")
        raise_domain("business_reputation", "rumor")
        raise_domain("social_graph", "rumor")
    if context.get("social_leads"):
        raise_domain("social_graph", "familiar")
    if context.get("opportunity_rows") or context.get("primary_opportunity_title"):
        raise_domain("opportunities", "familiar" if context.get("is_rival_operator") else "rumor")
    if context.get("is_rival_operator"):
        raise_domain("opportunities", "skilled")
        raise_domain("security", "familiar")
        raise_domain("business_reputation", "rumor")

    incident = _best_incident_context(sim, npc_eid) if sim is not None else None
    if incident:
        raise_domain("incident", "skilled" if incident.get("firsthand") else "familiar")

    if _skill_rating(sim, npc_eid, "streetwise") >= 7.0:
        raise_domain("business_reputation", "familiar")
        raise_domain("opportunities", "familiar")
        raise_domain("local_economy", "familiar")
    if _skill_rating(sim, npc_eid, "mechanics") >= 7.0:
        raise_domain("services", "familiar")
    if _skill_rating(sim, npc_eid, "tactics") >= 7.0:
        raise_domain("security", "familiar")

    rapport_shape = context.get("rapport_shape") if isinstance(context.get("rapport_shape"), dict) else build_rapport_shape(sim, npc_eid, context=context)
    privacy = _clamp01(rapport_shape.get("privacy", 0.5))
    local_attachment = _clamp01(rapport_shape.get("local_attachment", 0.5))
    work_attitude = _text(rapport_shape.get("work_attitude", "practical")).lower() or "practical"
    pressure_tier = _text(context.get("pressure_tier", "low")).lower() or "low"
    state_text = _text(context.get("state_text", "")).lower()
    safety_need = _float(getattr(needs, "safety", 70.0), 70.0)
    social_need = _float(getattr(needs, "social", 55.0), 55.0)
    discipline = _clamp01(getattr(traits, "discipline", 0.5))
    empathy = _clamp01(getattr(traits, "empathy", 0.5))

    if bool(context.get("guarded")) or pressure_tier == "high" or safety_need < 36:
        agenda_kind = "avoid_heat"
    elif role_id in _AUTHORITY_ROLES or "protect" in state_text:
        agenda_kind = "keep_order"
    elif context.get("owner_place_name") and (local_attachment >= 0.6 or discipline >= 0.62):
        agenda_kind = "protect_place"
    elif context.get("trade_available") or role_id in _TRADE_ROLES or role_tokens & _TRADE_ROLES:
        agenda_kind = "keep_trade_moving"
    elif context.get("player_business_hire_option") or social_need < 28:
        agenda_kind = "find_work_or_contact"
    elif work_attitude in {"restless", "improvised"}:
        agenda_kind = "look_for_angle"
    elif empathy >= 0.68 and local_attachment >= 0.52:
        agenda_kind = "watch_for_neighbors"
    else:
        agenda_kind = "get_through_shift"

    bias_by_agenda = {
        "avoid_heat": "safety",
        "keep_order": "safety",
        "protect_place": "protect_place",
        "keep_trade_moving": "trade",
        "find_work_or_contact": "work",
        "look_for_angle": "opportunity",
        "watch_for_neighbors": "reputation",
        "get_through_shift": "practical",
    }
    self_interest_bias = bias_by_agenda.get(agenda_kind, "practical")
    if privacy >= 0.72 and self_interest_bias in {"practical", "reputation", "opportunity", "work"}:
        self_interest_bias = "privacy"

    role_family = "local"
    if role_id in _AUTHORITY_ROLES or role_tokens & _AUTHORITY_ROLES:
        role_family = "authority"
    elif organization_role in _MANAGEMENT_ROLES or role_id in _MANAGEMENT_ROLES:
        role_family = "management"
    elif role_id in _TRADE_ROLES or role_tokens & _TRADE_ROLES:
        role_family = "trade"
    elif role_id in _LOGISTICS_ROLES or role_tokens & _LOGISTICS_ROLES:
        role_family = "logistics"

    known_domains = tuple(
        domain
        for domain in _DIALOGUE_KNOWLEDGE_DOMAINS
        if _DIALOGUE_COMPETENCE_RANK.get(domain_competence.get(domain, "none"), 0) > 0
    )
    return {
        "agenda_kind": agenda_kind,
        "self_interest_bias": self_interest_bias,
        "role_family": role_family,
        "role_id": role_id,
        "career_text": career_text,
        "organization_role": organization_role,
        "area_type": area_type,
        "district_type": district_type,
        "knowledge_domains": known_domains,
        "domain_competence": dict(domain_competence),
        "privacy": privacy,
        "local_attachment": local_attachment,
        "work_attitude": work_attitude,
    }


def relationship_read_profile(sim, player_eid, person_eid, entry=None):
    """Return the truthful player-facing relationship read for a known person."""
    entry = entry if isinstance(entry, dict) else {}
    if not bool(entry.get("met_directly", False)):
        return {
            "summary": "<unknown>",
            "detail": "<unknown>",
            "read_key": "unknown",
            "evidence": 0.0,
            "relation_kind": str(entry.get("relation_kind", "") or "").strip().lower() or "contact",
            "trust": 0.0,
            "closeness": 0.0,
            "protectiveness": 0.0,
        }

    contact_standing = _clamp01(entry.get("standing", 0.0))
    relation_kind = str(entry.get("relation_kind", "") or "").strip().lower() or "contact"
    trust = closeness = protectiveness = 0.0

    social = sim.ecs.get(NPCSocial).get(person_eid) if person_eid is not None else None
    bond = social.bonds.get(player_eid) if social and isinstance(getattr(social, "bonds", None), dict) else None
    if isinstance(bond, dict):
        trust = _clamp01(bond.get("trust", 0.0))
        closeness = _clamp01(bond.get("closeness", 0.0))
        protectiveness = _clamp01(bond.get("protectiveness", 0.0))
        relation_kind = str(bond.get("kind", "") or relation_kind).strip().lower() or relation_kind

    base_score = max(contact_standing, (trust * 0.55) + (closeness * 0.35) + (protectiveness * 0.10))
    positive_score = contact_standing
    negative_score = 0.0
    recent_offense = None

    memory = sim.ecs.get(NPCMemory).get(person_eid) if person_eid is not None else None
    if memory and getattr(memory, "entries", None):
        for record in tuple(memory.entries or ()):
            if not isinstance(record, dict):
                continue
            age = _int(getattr(sim, "tick", 0), 0) - _int(record.get("tick"), 0)
            kind = _text(record.get("kind", "")).lower()
            data = record.get("data", {}) if isinstance(record.get("data"), dict) else {}
            strength = _clamp01(record.get("strength", 0.0))
            if kind == "offense" and data.get("offender_eid") == player_eid and age <= 220:
                if recent_offense is None or strength > _clamp01(recent_offense.get("strength", 0.0)):
                    recent_offense = record
                negative_score = max(negative_score, max(0.38, strength * 0.9))
            elif kind == "threat" and data.get("source_eid") == player_eid and age <= 220:
                negative_score = max(negative_score, max(0.42, strength * 0.95))
            elif kind == "actor_reputation" and _int(data.get("actor_eid"), -1) == _int(player_eid, -1) and age <= 220:
                approval = max(-1.0, min(1.0, _float(data.get("approval", 0.0))))
                score = abs(approval) * max(0.08, strength)
                if approval >= 0.18:
                    positive_score = max(positive_score, score)
                elif approval <= -0.18:
                    negative_score = max(negative_score, score)
            elif kind == "player_reputation" and _int(data.get("player_eid"), -1) == _int(player_eid, -1) and age <= 320:
                approval = max(-1.0, min(1.0, _float(data.get("approval", 0.0), 1.0)))
                score = max(0.12, strength * 0.82)
                if approval >= 0.0:
                    positive_score = max(positive_score, score)

    evidence = max(base_score, positive_score, negative_score)
    result = {
        "summary": "<unknown>",
        "detail": "<unknown>",
        "read_key": "unknown",
        "evidence": evidence,
        "relation_kind": relation_kind,
        "trust": trust,
        "closeness": closeness,
        "protectiveness": protectiveness,
    }
    if evidence < 0.36:
        return result

    if negative_score >= max(0.42, positive_score + 0.08):
        if negative_score >= 0.62 or (recent_offense and _clamp01(recent_offense.get("strength", 0.0)) >= 0.34):
            result.update({
                "summary": "do not trust you",
                "detail": "You get the sense they do not trust you.",
                "read_key": "distrust",
            })
            return result
        result.update({
            "summary": "on edge around you",
            "detail": "They seem on edge around you.",
            "read_key": "wary",
        })
        return result

    if max(base_score, positive_score) >= 0.62:
        if relation_kind == "family":
            result.update({"summary": "family", "detail": "You think they see you as family.", "read_key": "family"})
            return result
        if relation_kind == "partner":
            result.update({"summary": "partner", "detail": "You think they see you as a partner.", "read_key": "partner"})
            return result
        if relation_kind == "friend":
            result.update({"summary": "friend", "detail": "You think they see you as a friend.", "read_key": "friend"})
            return result
        if relation_kind == "coworker":
            result.update({
                "summary": "trusted coworker",
                "detail": "You think they see you as a coworker they trust.",
                "read_key": "trusted_coworker",
            })
            return result
        if relation_kind in {"neighbor", "contact", "local"}:
            result.update({
                "summary": "trusted local",
                "detail": "You think they see you as a familiar, trusted local.",
                "read_key": "trusted_local",
            })
            return result

    if protectiveness >= 0.52:
        result.update({"summary": "protective", "detail": "They seem protective of you.", "read_key": "protective"})
        return result
    if trust >= 0.48 or positive_score >= 0.48:
        result.update({"summary": "seems to trust you", "detail": "They seem to trust you.", "read_key": "trust"})
        return result
    result.update({
        "summary": "comfortable around you",
        "detail": "They seem comfortable around you.",
        "read_key": "comfortable",
    })
    return result


def relationship_episode_records(entry, *, include_trivial=False, limit=None):
    entry = entry if isinstance(entry, dict) else {}
    cleaned = []
    for raw in tuple(entry.get("episodes", ()) or ()):
        if not isinstance(raw, dict):
            continue
        kind = _text(raw.get("kind", "")).lower()
        summary = _text(raw.get("summary", ""))
        if not kind or not summary:
            continue
        if not include_trivial and kind in _TRIVIAL_RELATIONSHIP_EPISODES:
            continue
        valence = _text(raw.get("valence", "neutral")).lower() or "neutral"
        if valence not in {"positive", "negative", "neutral"}:
            valence = "neutral"
        cleaned.append({
            "kind": kind,
            "tick": _int(raw.get("tick"), 0),
            "valence": valence,
            "summary": summary,
            "property_id": _text(raw.get("property_id", "")),
            "other_person_eid": raw.get("other_person_eid"),
            "source_topic": _text(raw.get("source_topic", "")).lower(),
        })
    cleaned.sort(key=lambda record: int(record.get("tick", 0) or 0), reverse=True)
    if limit is not None:
        cleaned = cleaned[: max(1, int(limit))]
    return tuple(cleaned)


def relationship_anchor_episode(entry, *, tone="neutral", include_trivial=False):
    records = list(relationship_episode_records(entry, include_trivial=include_trivial))
    if not records:
        return None
    tone = _text(tone, "neutral").lower() or "neutral"
    prefer_negative = tone in {"wary", "guarded"}

    def _episode_score(record):
        kind = _text(record.get("kind", "")).lower()
        valence = _text(record.get("valence", "neutral")).lower() or "neutral"
        tick = _int(record.get("tick"), 0)
        score = float(tick) / 100000.0
        if prefer_negative:
            if valence == "negative":
                score += 4.0
            elif valence == "positive":
                score -= 0.8
        else:
            if valence == "positive":
                score += 4.0
            elif valence == "negative":
                score -= 0.2
        if kind in {"told_me_how_they_see_me", "opened_up_personally", "offered_vouch"}:
            score += 1.6
        elif kind in {"offered_introduction", "offered_contact", "opened_up_about_roots", "opened_up_about_work"}:
            score += 1.1
        elif kind in _NEGATIVE_RELATIONSHIP_EPISODES:
            score += 1.2 if prefer_negative else 0.3
        return score

    records.sort(key=_episode_score, reverse=True)
    return dict(records[0]) if records else None


def _social_reaction_scope(topic_id):
    topic_id = _text(topic_id).lower()
    if topic_id in _RAPPORT_REACTION_TOPICS:
        return "rapport"
    if topic_id in _MISSTEP_REACTION_TOPICS:
        return "misstep"
    if topic_id in _SOCIAL_ACCESS_REACTION_TOPICS:
        return "social_access"
    return ""


def _social_reaction_outcome_key(outcome):
    outcome = _text(outcome).lower()
    if outcome in {"warm", "open", "reserved", "rebuff"}:
        return outcome
    if outcome == "soft":
        return "open"
    if outcome == "wary":
        return "reserved"
    if outcome in {"fail", "aggravated", "hard_no"}:
        return "rebuff"
    return ""


def _social_reaction_allowed(topic_id, outcome_key, context, rapport_shape):
    topic_id = _text(topic_id).lower()
    if not _social_reaction_scope(topic_id):
        return False
    if topic_id == "weird" and outcome_key == "reserved":
        return False

    if outcome_key in {"warm", "rebuff"}:
        return True
    if topic_id in {"provoke", "intimidate"} and outcome_key in {"open", "reserved"}:
        return True

    context = context if isinstance(context, dict) else {}
    rapport_shape = rapport_shape if isinstance(rapport_shape, dict) else {}
    social_standing = _clamp01(context.get("social_standing", 0.0))
    privacy = _clamp01(rapport_shape.get("privacy", 0.0))
    chattiness = _clamp01(rapport_shape.get("chattiness", 0.0))
    playfulness = _clamp01(rapport_shape.get("playfulness", 0.0))
    tone = _text(context.get("tone", "neutral")).lower() or "neutral"
    pressure_tier = _text(context.get("pressure_tier", "low")).lower() or "low"

    if outcome_key == "open":
        if topic_id in _DEEP_REACTION_TOPICS:
            return True
        if topic_id == "weird":
            return playfulness >= 0.68 or social_standing >= 0.64
        if topic_id in _SOCIAL_ACCESS_REACTION_TOPICS:
            return social_standing >= 0.46 or chattiness >= 0.58
        return social_standing >= 0.54 or _text(rapport_shape.get("day_mood", "")).lower() in {"light", "warm"}

    if outcome_key == "reserved":
        if topic_id in _DEEP_REACTION_TOPICS or topic_id in {"pry", "provoke", "intimidate", "insult"}:
            return True
        return privacy >= 0.62 or tone in {"wary", "guarded"} or pressure_tier == "high"

    return False


def _social_reaction_candidates(topic_id, outcome_key, rapport_shape, context):
    topic_id = _text(topic_id).lower()
    context = context if isinstance(context, dict) else {}
    rapport_shape = rapport_shape if isinstance(rapport_shape, dict) else {}
    playfulness = _clamp01(rapport_shape.get("playfulness", 0.0))
    privacy = _clamp01(rapport_shape.get("privacy", 0.0))
    chattiness = _clamp01(rapport_shape.get("chattiness", 0.0))
    day_mood = _text(rapport_shape.get("day_mood", "")).lower()
    pressure_tier = _text(context.get("pressure_tier", "low")).lower() or "low"
    tone = _text(context.get("tone", "neutral")).lower() or "neutral"

    if outcome_key == "warm":
        candidates = [
            "{npc_subject_cap} smiles at you.",
            "{npc_subject_cap} relaxes a little.",
            "{npc_possessive_adj_cap} eyes brighten.",
            "{npc_subject_cap} {npc_be} already half smiling.",
        ]
    elif outcome_key == "open":
        candidates = [
            "{npc_subject_cap} tilts {npc_possessive_adj} head.",
            "{npc_subject_cap} considers that for a moment.",
            "{npc_subject_cap} nods once.",
            "{npc_subject_cap} {npc_be} thoughtful about the answer.",
        ]
    elif outcome_key == "reserved":
        candidates = [
            "{npc_subject_cap} keeps {npc_possessive_adj} expression even.",
            "{npc_subject_cap} glances aside for a moment.",
            "{npc_subject_cap} folds {npc_possessive_adj} arms loosely.",
            "{npc_subject_cap} {npc_be} careful with the answer.",
        ]
    elif outcome_key == "rebuff":
        candidates = [
            "{npc_possessive_adj_cap} expression tightens.",
            "{npc_subject_cap} narrows {npc_possessive_adj} eyes.",
            "{npc_subject_cap} goes still.",
            "{npc_subject_cap} {npc_be} done softening the point.",
        ]
    else:
        return ()

    if topic_id in _REFLECTIVE_REACTION_TOPICS and outcome_key in {"warm", "open", "reserved"}:
        candidates.extend((
            "{npc_subject_cap} pauses, weighing the question.",
            "{npc_subject_cap} looks off for a second, thinking.",
        ))
    if topic_id in _DEEP_REACTION_TOPICS:
        if outcome_key in {"warm", "open"}:
            candidates.extend((
                "{npc_subject_cap} hesitates, then meets your eyes.",
                "{npc_subject_cap} holds your gaze for a moment.",
            ))
        else:
            candidates.extend((
                "{npc_subject_cap} looks away before answering.",
                "{npc_subject_cap} takes a beat before answering.",
            ))
    if topic_id in _LIGHT_REACTION_TOPICS and outcome_key in {"warm", "open"}:
        candidates.extend((
            "{npc_subject_cap} loosens up a little.",
            "{npc_subject_cap} seems easier for a moment.",
        ))
    if topic_id in _SOCIAL_ACCESS_REACTION_TOPICS:
        if outcome_key in {"warm", "open"}:
            candidates.extend((
                "{npc_subject_cap} seems to weigh the risk for a moment.",
                "{npc_subject_cap} glances around before answering.",
            ))
        else:
            candidates.extend((
                "{npc_subject_cap} checks the room before answering.",
                "{npc_subject_cap} keeps the answer tight.",
            ))
    if topic_id == "weird":
        if outcome_key == "open":
            candidates.append("{npc_subject_cap} lets out a quiet laugh.")
        elif outcome_key == "rebuff":
            candidates.append("{npc_subject_cap} looks at you like the question curdled on contact.")
    elif topic_id == "provoke":
        if outcome_key == "open":
            candidates.extend((
                "{npc_subject_cap} meets your eyes and lets the politeness drop.",
                "{npc_possessive_adj_cap} mouth tightens before {npc_subject} answers.",
            ))
        elif outcome_key in {"reserved", "rebuff"}:
            candidates.append("{npc_subject_cap} recognizes the bait and goes still.")
    elif topic_id == "intimidate":
        if outcome_key == "open":
            candidates.extend((
                "{npc_subject_cap} glances for an exit before answering.",
                "{npc_possessive_adj_cap} shoulders tighten.",
            ))
        elif outcome_key in {"reserved", "rebuff"}:
            candidates.extend((
                "{npc_subject_cap} settles into {npc_possessive_adj} stance.",
                "{npc_subject_cap} looks past you toward the room.",
            ))

    if playfulness >= 0.68 and outcome_key in {"warm", "open"}:
        candidates.append("{npc_subject_cap} lets out a quiet laugh.")
    if day_mood in {"warm", "light"} and outcome_key == "warm":
        candidates.append("{npc_subject_cap} {npc_have} a little spark in {npc_possessive_adj} eyes.")
    if privacy >= 0.7 and topic_id in _DEEP_REACTION_TOPICS and outcome_key in {"reserved", "rebuff"}:
        candidates.extend((
            "{npc_subject_cap} closes {npc_possessive_adj} posture off a little.",
            "{npc_subject_cap} answers without really opening up.",
        ))
    if chattiness <= 0.32 and outcome_key in {"reserved", "rebuff"}:
        candidates.append("{npc_subject_cap} keeps the answer clipped.")
    if pressure_tier == "high" and outcome_key in {"reserved", "rebuff"}:
        candidates.append("{npc_subject_cap} looks like {npc_subject} would rather end the subject there.")
    if tone == "friendly" and outcome_key == "warm":
        candidates.append("{npc_subject_cap} meets your eyes with an easy look.")

    ordered = []
    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return tuple(ordered)


def social_reaction_narration(sim, npc_eid, *, topic_id="", outcome="", ask_count=1, context=None, rapport_shape=None):
    """Return one short narration beat for a socially meaningful reply."""
    if sim is None or npc_eid is None:
        return ""
    identity = sim.ecs.get(CreatureIdentity).get(npc_eid)
    if not is_human_identity(identity):
        return ""

    topic_id = _text(topic_id).lower()
    outcome_key = _social_reaction_outcome_key(outcome)
    context = dict(context or {})
    rapport_shape = rapport_shape if isinstance(rapport_shape, dict) else context.get("rapport_shape")
    if not isinstance(rapport_shape, dict):
        rapport_shape = build_rapport_shape(sim, npc_eid, context=context)
    if not _social_reaction_allowed(topic_id, outcome_key, context, rapport_shape):
        return ""

    personal_name = _text(getattr(identity, "personal_name", ""))
    slots = pronoun_format_slots(
        identity,
        prefix="npc",
        default="they",
        personal_name=personal_name,
        seed_token=f"{getattr(sim, 'seed', 0)}:dialogue-pronouns:{npc_eid}:{topic_id}",
    )
    candidates = _social_reaction_candidates(topic_id, outcome_key, rapport_shape, context)
    if not candidates:
        return ""

    opened_count = _int(context.get("opened_count", 0), 0)
    seed_text = (
        f"{getattr(sim, 'seed', 0)}:dialogue-reaction:{npc_eid}:{topic_id}:{outcome_key}:"
        f"{_int(ask_count, 1)}:{opened_count}:{_text(rapport_shape.get('day_mood', ''))}:"
        f"{_text(rapport_shape.get('work_attitude', ''))}:{_text(context.get('tone', 'neutral'))}:"
        f"{_text(context.get('pressure_tier', 'low'))}"
    )
    line = random.Random(seed_text).choice(tuple(candidates)).format(**slots)
    return _text(line)


def shaped_opening_lines(context, *, limit=1):
    shape = context.get("dialogue_shape") if isinstance(context, dict) else None
    if not isinstance(shape, dict):
        return ()
    return tuple(_text(line) for line in tuple(shape.get("opening_lines", ()) or ()) if _text(line))[: max(0, int(limit))]


def shaped_local_line(context):
    shape = context.get("dialogue_shape") if isinstance(context, dict) else None
    if not isinstance(shape, dict):
        return ""
    return _text(shape.get("local_line", ""))


def shaped_concern_line(context):
    shape = context.get("dialogue_shape") if isinstance(context, dict) else None
    if not isinstance(shape, dict):
        return ""
    return _text(shape.get("concern_line", ""))
