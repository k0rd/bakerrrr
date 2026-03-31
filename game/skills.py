from __future__ import annotations

import random

from game.components import CoreStats, InsightStats, Inventory, SkillProfile, StatusEffects
from game.items import ITEM_CATALOG, item_instance_condition


SKILL_DEFS = {
    "athletics": {
        "label": "Athletics",
        "short": "at",
    },
    "perception": {
        "label": "Perception",
        "short": "pe",
    },
    "conversation": {
        "label": "Conversation",
        "short": "cv",
    },
    "streetwise": {
        "label": "Streetwise",
        "short": "sw",
    },
    "intrusion": {
        "label": "Intrusion",
        "short": "in",
    },
    "mechanics": {
        "label": "Mechanics",
        "short": "me",
    },
}

SKILL_ALIASES = {
    "access": "intrusion",
    "charisma": "conversation",
    "social": "conversation",
    "awareness": "perception",
}

TOOL_CONTEXT_ALIASES = {
    "lock": "mechanical_lock",
    "property_lock": "mechanical_lock",
    "vehicle_hotwire": "vehicle_ignition",
    "hotwire": "vehicle_ignition",
    "badge": "badge_controller",
    "biometric": "biometric_controller",
    "schedule": "schedule_controller",
    "schedule_relay": "schedule_controller",
    "timer": "relay_controller",
    "relay": "relay_controller",
    "timer_relay": "relay_controller",
    "side_door": "side_entry",
}

HUD_SKILL_IDS = ("perception", "conversation", "streetwise", "intrusion", "mechanics")

ROLE_SKILL_MODS = {
    "player": {"intrusion": 0.3, "streetwise": 0.2, "perception": 0.15},
    "civilian": {"conversation": 0.2, "streetwise": 0.1},
    "worker": {"mechanics": 0.75, "intrusion": 0.35, "athletics": 0.2},
    "guard": {"perception": 1.1, "athletics": 0.7, "streetwise": 0.25},
    "scout": {"perception": 0.95, "athletics": 0.55, "streetwise": 0.4},
}

CAREER_KEYWORD_SKILL_MODS = {
    "mechanic": {"mechanics": 1.0, "intrusion": 0.45},
    "tech": {"mechanics": 0.8, "intrusion": 0.35},
    "engineer": {"mechanics": 0.9, "intrusion": 0.3},
    "repair": {"mechanics": 0.75, "intrusion": 0.25},
    "tool": {"mechanics": 0.65, "intrusion": 0.25},
    "broker": {"conversation": 0.9, "streetwise": 0.45},
    "manager": {"conversation": 0.7, "streetwise": 0.35},
    "consult": {"conversation": 0.7, "streetwise": 0.35},
    "recruit": {"conversation": 0.8, "perception": 0.25},
    "clerk": {"conversation": 0.45},
    "host": {"conversation": 0.55},
    "bartender": {"conversation": 0.6, "streetwise": 0.45},
    "dj": {"conversation": 0.35, "streetwise": 0.4},
    "courier": {"athletics": 0.6, "perception": 0.45},
    "dispatch": {"perception": 0.45, "conversation": 0.25},
    "guard": {"perception": 0.75, "athletics": 0.4},
    "patrol": {"perception": 0.7, "athletics": 0.4},
    "bailiff": {"perception": 0.6, "conversation": 0.25},
    "security": {"perception": 0.7, "intrusion": 0.2},
    "lookout": {"perception": 0.75, "streetwise": 0.25},
    "scout": {"perception": 0.8, "athletics": 0.35},
    "salvage": {"streetwise": 0.6, "mechanics": 0.3},
    "scrap": {"streetwise": 0.55, "mechanics": 0.35},
    "chop": {"streetwise": 0.55, "mechanics": 0.45},
    "fence": {"streetwise": 0.8, "conversation": 0.35},
    "medic": {"perception": 0.45, "conversation": 0.2},
    "nurse": {"perception": 0.4, "conversation": 0.2},
    "pharmac": {"perception": 0.35, "conversation": 0.2},
}


def _num(value, default=5.0):
    try:
        if value is None:
            raise TypeError
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp_skill(value, default=5.0):
    return max(1.0, min(10.0, _num(value, default=default)))


def normalize_skill_id(skill_id):
    key = str(skill_id or "").strip().lower()
    if not key:
        return ""
    return SKILL_ALIASES.get(key, key)


def skill_label(skill_id):
    key = normalize_skill_id(skill_id)
    return str(SKILL_DEFS.get(key, {}).get("label", key.replace("_", " ").title())).strip()


def skill_short_label(skill_id):
    key = normalize_skill_id(skill_id)
    return str(SKILL_DEFS.get(key, {}).get("short", key[:2] or "sk")).strip()


def normalize_tool_context(context):
    key = str(context or "").strip().lower()
    if not key:
        return ""
    return TOOL_CONTEXT_ALIASES.get(key, key)


def _derive_axes(core=None, insight=None):
    common_sense = _num(getattr(core, "common_sense", None), 5.0)
    if insight is not None:
        common_sense = _num(getattr(insight, "common_sense", None), common_sense)
    dexterity = _num(getattr(core, "dexterity", None), 5.0)
    brawn = _num(getattr(core, "brawn", None), 5.0)
    athleticism = _num(getattr(core, "athleticism", None), 5.0)
    access = _num(getattr(core, "access", None), (dexterity + common_sense) / 2.0)
    charm = _num(getattr(core, "charm", None), 5.0)
    perception = _num(getattr(insight, "perception", None), common_sense)
    streetwise = _num(getattr(insight, "streetwise", None), common_sense)
    charisma = _num(getattr(insight, "charisma", None), _num(getattr(insight, "charm", None), charm))
    return {
        "common_sense": common_sense,
        "dexterity": dexterity,
        "brawn": brawn,
        "athleticism": athleticism,
        "access": access,
        "charm": charm,
        "perception": perception,
        "streetwise": streetwise,
        "charisma": charisma,
    }


def derived_skill_value(skill_id, *, core=None, insight=None, default=5.0):
    key = normalize_skill_id(skill_id)
    axes = _derive_axes(core=core, insight=insight)

    if key == "athletics":
        value = (axes["athleticism"] * 0.65) + (axes["brawn"] * 0.2) + (axes["dexterity"] * 0.15)
    elif key == "perception":
        value = (axes["perception"] * 0.65) + (axes["common_sense"] * 0.35)
    elif key == "conversation":
        value = (axes["charisma"] * 0.65) + (axes["charm"] * 0.2) + (axes["common_sense"] * 0.15)
    elif key == "streetwise":
        value = (axes["streetwise"] * 0.55) + (axes["common_sense"] * 0.3) + (axes["charisma"] * 0.15)
    elif key == "intrusion":
        value = (axes["access"] * 0.55) + (axes["dexterity"] * 0.25) + (axes["common_sense"] * 0.2)
    elif key == "mechanics":
        value = (axes["dexterity"] * 0.45) + (axes["common_sense"] * 0.3) + (axes["access"] * 0.25)
    else:
        value = default
    return _clamp_skill(value, default=default)


def profile_skill(skill_id, *, profile=None, core=None, insight=None, default=5.0):
    key = normalize_skill_id(skill_id)
    if not key:
        return _clamp_skill(default, default=default)

    if isinstance(profile, SkillProfile):
        explicit = profile.get(key)
        if explicit is not None:
            return _clamp_skill(explicit, default=default)

    if insight is None and isinstance(profile, InsightStats):
        insight = profile
    if core is None and isinstance(profile, CoreStats):
        core = profile
    if insight is None and hasattr(profile, "perception") and hasattr(profile, "streetwise"):
        insight = profile
    if core is None and any(hasattr(profile, attr) for attr in ("brawn", "athleticism", "dexterity", "access", "charm", "common_sense")):
        core = profile

    return derived_skill_value(key, core=core, insight=insight, default=default)


def actor_skill(sim, eid, skill_id, default=5.0):
    if sim is None or eid is None:
        return _clamp_skill(default, default=default)

    profiles = sim.ecs.get(SkillProfile)
    profile = profiles.get(eid) if profiles else None
    insights = sim.ecs.get(InsightStats)
    insight = insights.get(eid) if insights else None
    cores = sim.ecs.get(CoreStats)
    core = cores.get(eid) if cores else None
    base = profile_skill(skill_id, profile=profile, core=core, insight=insight, default=default)

    effects_map = sim.ecs.get(StatusEffects)
    effects = effects_map.get(eid) if effects_map else None
    if effects:
        buff_key = f"{normalize_skill_id(skill_id)}_buff"
        modifiers = effects.modifiers_sum()
        buff = float(modifiers.get(buff_key, 0.0))
        if buff:
            base = _clamp_skill(base + buff, default=default)

    return base


def actor_skill_bundle(sim, eid, skill_ids=HUD_SKILL_IDS):
    bundle = {}
    for skill_id in skill_ids:
        key = normalize_skill_id(skill_id)
        if not key:
            continue
        bundle[key] = actor_skill(sim, eid, key)
    return bundle


def _service_edge(score, baseline=5.0):
    try:
        value = (float(score) - float(baseline)) / 5.0
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(1.0, value))


def _service_note(channel, conversation, streetwise, perception, edge):
    if float(edge) < 0.12:
        return ""

    channel = str(channel or "").strip().lower()
    if channel == "insurance":
        if perception >= max(conversation, streetwise):
            return "you spot the policy angle"
        return "your pitch helps on rates"

    if streetwise >= conversation + 0.45 and streetwise >= perception:
        return "your streetwise helps on price"
    if perception >= max(conversation, streetwise):
        return "you read the room well"
    return "your pitch helps on price"


def trade_skill_terms(sim, eid):
    conversation = actor_skill(sim, eid, "conversation")
    streetwise = actor_skill(sim, eid, "streetwise")
    perception = actor_skill(sim, eid, "perception")
    score = (conversation * 0.46) + (streetwise * 0.36) + (perception * 0.18)
    edge = _service_edge(score, baseline=5.1)
    return {
        "score": score,
        "buy_mult": max(0.92, 1.0 - (edge * 0.08)),
        "sell_mult": min(1.06, 1.0 + (edge * 0.06)),
        "note": _service_note("trade", conversation, streetwise, perception, edge),
    }


def insurance_skill_terms(sim, eid):
    conversation = actor_skill(sim, eid, "conversation")
    streetwise = actor_skill(sim, eid, "streetwise")
    perception = actor_skill(sim, eid, "perception")
    score = (conversation * 0.54) + (perception * 0.28) + (streetwise * 0.18)
    edge = _service_edge(score, baseline=5.0)
    return {
        "score": score,
        "premium_mult": max(0.9, 1.0 - (edge * 0.1)),
        "note": _service_note("insurance", conversation, streetwise, perception, edge),
    }


def _tool_terms_template(context_key):
    return {
        "context": context_key,
        "enabled": False,
        "intrusion_bonus": 0.0,
        "mechanics_bonus": 0.0,
        "perception_bonus": 0.0,
        "score_bonus": 0.0,
        "requirement_delta": 0.0,
        "item_ids": (),
        "enabled_item_ids": (),
        "selected_item_id": "",
        "selected_instance_id": "",
    }


def _tool_terms_utility(sim, eid, context_key, terms):
    ignition = context_key == "vehicle_ignition"
    intrusion = actor_skill(sim, eid, "intrusion") + _num(terms.get("intrusion_bonus"), 0.0)
    mechanics = actor_skill(sim, eid, "mechanics") + _num(terms.get("mechanics_bonus"), 0.0)
    perception = actor_skill(sim, eid, "perception") + _num(terms.get("perception_bonus"), 0.0)

    score = intrusion
    score += max(0.0, intrusion - 5.0) * 0.28
    score += max(0.0, mechanics - 5.0) * (0.4 if ignition else 0.18)
    score += max(0.0, perception - 5.0) * 0.16
    score += _num(terms.get("score_bonus"), 0.0)
    score -= _num(terms.get("requirement_delta"), 0.0)
    if bool(terms.get("enabled")):
        score += 3.0
    return float(score)


def actor_tool_terms(sim, eid, context):
    context_key = normalize_tool_context(context)
    terms = _tool_terms_template(context_key)
    if sim is None or eid is None or not context_key:
        return terms

    inventories = sim.ecs.get(Inventory)
    inventory = inventories.get(eid) if inventories else None
    if not inventory or not inventory.items:
        return terms

    best_terms = None
    best_utility = None
    for entry in inventory.items:
        item_id = str(entry.get("item_id", "")).strip().lower()
        if not item_id or int(entry.get("quantity", 0)) <= 0:
            continue

        item_def = ITEM_CATALOG.get(item_id, {})
        candidate = _tool_terms_template(context_key)
        for profile in item_def.get("tool_profiles", ()):
            contexts = tuple(profile.get("contexts", ()))
            if context_key not in contexts and "any" not in contexts:
                continue
            candidate["intrusion_bonus"] += _num(profile.get("intrusion_bonus"), 0.0)
            candidate["mechanics_bonus"] += _num(profile.get("mechanics_bonus"), 0.0)
            candidate["perception_bonus"] += _num(profile.get("perception_bonus"), 0.0)
            candidate["score_bonus"] += _num(profile.get("score_bonus"), 0.0)
            candidate["requirement_delta"] += _num(profile.get("requirement_delta"), 0.0)

            enable_contexts = tuple(profile.get("enable_contexts", ()))
            if context_key in enable_contexts or "any" in enable_contexts:
                candidate["enabled"] = True

        condition = item_instance_condition(item_id, metadata=entry.get("metadata"), item_catalog=ITEM_CATALOG)
        if not bool(condition.get("usable", True)):
            continue
        candidate["score_bonus"] += float(condition.get("score_bonus", 0.0))
        candidate["requirement_delta"] += float(condition.get("requirement_delta", 0.0))

        if not any(
            (
                candidate["enabled"],
                candidate["intrusion_bonus"],
                candidate["mechanics_bonus"],
                candidate["perception_bonus"],
                candidate["score_bonus"],
                candidate["requirement_delta"],
            )
        ):
            continue

        candidate["requirement_delta"] = max(-3.5, float(candidate["requirement_delta"]))
        candidate["selected_item_id"] = item_id
        candidate["selected_instance_id"] = str(entry.get("instance_id", "")).strip()
        candidate["item_ids"] = (item_id,)
        if candidate["enabled"]:
            candidate["enabled_item_ids"] = (item_id,)

        utility = _tool_terms_utility(sim, eid, context_key, candidate)
        if (
            best_terms is None
            or utility > best_utility
            or (
                utility == best_utility
                and bool(candidate["enabled"])
                and not bool(best_terms.get("enabled"))
            )
            or (
                utility == best_utility
                and bool(candidate.get("enabled")) == bool(best_terms.get("enabled"))
                and (
                    str(candidate.get("selected_instance_id", "")) < str(best_terms.get("selected_instance_id", ""))
                    or (
                        str(candidate.get("selected_instance_id", "")) == str(best_terms.get("selected_instance_id", ""))
                        and item_id < str(best_terms.get("selected_item_id", ""))
                    )
                )
            )
        ):
            best_terms = dict(candidate)
            best_utility = float(utility)

    return best_terms or terms


def seed_skill_profile(rng, *, role="", career="", core=None, insight=None, jitter=0.35):
    if rng is None:
        rng = random.Random(0)

    role_key = str(role or "").strip().lower()
    career_text = str(career or "").strip().lower().replace(" ", "_")
    ratings = {}
    for skill_id in SKILL_DEFS:
        value = derived_skill_value(skill_id, core=core, insight=insight, default=5.0)
        value += float(ROLE_SKILL_MODS.get(role_key, {}).get(skill_id, 0.0))
        for keyword, mods in CAREER_KEYWORD_SKILL_MODS.items():
            if keyword in career_text:
                value += float(mods.get(skill_id, 0.0))
        value += float(rng.uniform(-abs(float(jitter)), abs(float(jitter))))
        ratings[skill_id] = _clamp_skill(value)
    return SkillProfile(ratings=ratings)
