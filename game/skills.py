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
ALL_SKILL_IDS = tuple(SKILL_DEFS.keys())
SKILL_FLOOR_RATIO = float(getattr(SkillProfile, "DEFAULT_FLOOR_RATIO", 0.7) or 0.7)

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

PLAYER_BIRTH_SPECIALIZATION_MODS = (
    0.45,
    0.2,
    -0.4,
    -0.25,
)


def _num(value, default=5.0):
    try:
        if value is None:
            raise TypeError
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp_skill(value, default=5.0):
    return max(1.0, min(10.0, _num(value, default=default)))


def _player_birth_skill_biases(birth_key):
    birth_key = str(birth_key or "").strip()
    if not birth_key:
        return {}

    skill_ids = list(ALL_SKILL_IDS)
    if len(skill_ids) < len(PLAYER_BIRTH_SPECIALIZATION_MODS):
        return {}

    rng = random.Random(f"{birth_key}:player_birth_specialization")
    rng.shuffle(skill_ids)
    biases = {}
    for skill_id, delta in zip(skill_ids, PLAYER_BIRTH_SPECIALIZATION_MODS):
        biases[skill_id] = float(delta)
    return biases


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


def ensure_actor_skill_profile(sim, eid, *, skill_ids=ALL_SKILL_IDS, default=5.0):
    if sim is None or eid is None:
        return None

    profiles = sim.ecs.get(SkillProfile)
    profile = profiles.get(eid) if profiles else None
    if isinstance(profile, SkillProfile):
        for skill_id in tuple(skill_ids or ALL_SKILL_IDS):
            key = normalize_skill_id(skill_id)
            if not key:
                continue
            profile.ensure_baseline(key, value=profile.get(key, default=default))
        return profile

    ratings = {}
    for skill_id in tuple(skill_ids or ALL_SKILL_IDS):
        key = normalize_skill_id(skill_id)
        if not key:
            continue
        ratings[key] = actor_skill(sim, eid, key, default=default)
    profile = SkillProfile(ratings=ratings)
    sim.ecs.add(eid, profile)
    return profile


def profile_skill_baseline(skill_id, *, profile=None, core=None, insight=None, default=5.0):
    key = normalize_skill_id(skill_id)
    if not key:
        return _clamp_skill(default, default=default)

    if isinstance(profile, SkillProfile):
        baseline = profile.ensure_baseline(key, value=profile.get(key, default=default))
        if baseline is not None:
            return _clamp_skill(baseline, default=default)

    return profile_skill(key, profile=profile, core=core, insight=insight, default=default)


def actor_skill_baseline(sim, eid, skill_id, default=5.0):
    if sim is None or eid is None:
        return _clamp_skill(default, default=default)

    profiles = sim.ecs.get(SkillProfile)
    profile = profiles.get(eid) if profiles else None
    insights = sim.ecs.get(InsightStats)
    insight = insights.get(eid) if insights else None
    cores = sim.ecs.get(CoreStats)
    core = cores.get(eid) if cores else None
    return profile_skill_baseline(skill_id, profile=profile, core=core, insight=insight, default=default)


def skill_floor_value(baseline, floor_ratio=SKILL_FLOOR_RATIO):
    try:
        ratio = float(floor_ratio)
    except (TypeError, ValueError):
        ratio = float(SKILL_FLOOR_RATIO)
    ratio = max(0.1, min(1.0, ratio))
    return max(1.0, min(10.0, float(_clamp_skill(baseline)) * ratio))


def actor_skill_floor(sim, eid, skill_id, default=5.0, floor_ratio=SKILL_FLOOR_RATIO):
    baseline = actor_skill_baseline(sim, eid, skill_id, default=default)
    return skill_floor_value(baseline, floor_ratio=floor_ratio)


def actor_skill_bundle(sim, eid, skill_ids=HUD_SKILL_IDS):
    bundle = {}
    for skill_id in skill_ids:
        key = normalize_skill_id(skill_id)
        if not key:
            continue
        bundle[key] = actor_skill(sim, eid, key)
    return bundle


def profile_recent_skill_changes(profile, *, tick=None, skill_ids=ALL_SKILL_IDS, recent_window=None, limit=None):
    if not isinstance(profile, SkillProfile):
        return ()

    try:
        current_tick = int(tick) if tick is not None else None
    except (TypeError, ValueError):
        current_tick = None
    try:
        window = int(recent_window) if recent_window is not None else None
    except (TypeError, ValueError):
        window = None

    rows = []
    seen = set()
    for skill_id in tuple(skill_ids or profile.skill_ids() or ALL_SKILL_IDS):
        key = normalize_skill_id(skill_id)
        if not key or key in seen:
            continue
        seen.add(key)
        entry = profile.recent_change(key)
        if not isinstance(entry, dict):
            continue
        try:
            entry_tick = int(entry.get("tick", 0))
        except (TypeError, ValueError):
            entry_tick = 0
        if current_tick is not None and window is not None and window >= 0 and (current_tick - entry_tick) > window:
            continue
        delta = _num(entry.get("delta", 0.0), 0.0)
        if abs(delta) <= 1e-9:
            continue
        value = _clamp_skill(entry.get("value", profile.get(key, default=5.0)), default=5.0)
        baseline = profile.ensure_baseline(key, value=value)
        floor = profile.floor(key)
        rows.append({
            "skill_id": key,
            "label": skill_label(key),
            "delta": float(delta),
            "tick": int(entry_tick),
            "age_ticks": None if current_tick is None else max(0, int(current_tick) - int(entry_tick)),
            "value": float(value),
            "baseline": float(baseline if baseline is not None else value),
            "floor": float(floor),
            "reason": str(entry.get("reason", "") or "").strip().lower(),
        })

    rows.sort(key=lambda row: (-int(row["tick"]), -abs(float(row["delta"])), str(row["skill_id"])))
    if limit is not None:
        try:
            max_items = max(0, int(limit))
        except (TypeError, ValueError):
            max_items = 0
        rows = rows[:max_items]
    return tuple(rows)


def profile_neglect_pressure(profile, *, tick, skill_ids=ALL_SKILL_IDS, grace_ticks, warning_ticks=0, limit=None):
    if not isinstance(profile, SkillProfile):
        return ()
    try:
        current_tick = int(tick)
        grace = int(grace_ticks)
    except (TypeError, ValueError):
        return ()
    try:
        warning = int(warning_ticks)
    except (TypeError, ValueError):
        warning = 0
    warning = max(0, warning)
    if grace <= 0:
        return ()

    rows = []
    seen = set()
    for skill_id in tuple(skill_ids or profile.skill_ids() or ALL_SKILL_IDS):
        key = normalize_skill_id(skill_id)
        if not key or key in seen:
            continue
        seen.add(key)
        current = profile.get(key)
        if current is None:
            continue
        floor = profile.floor(key)
        if float(current) <= float(floor) + 1e-9:
            continue
        last_practiced = profile.last_practiced_tick(key)
        if last_practiced is None:
            continue
        idle_ticks = max(0, current_tick - int(last_practiced))
        due_in = int(grace) - int(idle_ticks)
        if due_in > warning:
            continue
        baseline = profile.ensure_baseline(key, value=current)
        rows.append({
            "skill_id": key,
            "label": skill_label(key),
            "status": "overdue" if due_in <= 0 else "warning",
            "idle_ticks": int(idle_ticks),
            "due_in": int(due_in),
            "last_practiced_tick": int(last_practiced),
            "value": float(_clamp_skill(current, default=5.0)),
            "baseline": float(baseline if baseline is not None else current),
            "floor": float(floor),
        })

    rows.sort(
        key=lambda row: (
            0 if str(row.get("status", "")) == "overdue" else 1,
            int(row.get("due_in", 0)),
            str(row.get("skill_id", "")),
        )
    )
    if limit is not None:
        try:
            max_items = max(0, int(limit))
        except (TypeError, ValueError):
            max_items = 0
        rows = rows[:max_items]
    return tuple(rows)


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


def _mobility_service_note(mechanics, conversation, streetwise, perception, edge):
    if float(edge) < 0.12:
        return ""
    if mechanics >= max(conversation, streetwise, perception):
        return "you talk like you know the machine"
    if streetwise >= max(mechanics, conversation, perception):
        return "you know the local rate"
    if perception >= max(mechanics, conversation, streetwise):
        return "you catch the padded fees"
    return "your pitch softens the quote"


def mobility_service_skill_terms(sim, eid):
    mechanics = actor_skill(sim, eid, "mechanics")
    conversation = actor_skill(sim, eid, "conversation")
    streetwise = actor_skill(sim, eid, "streetwise")
    perception = actor_skill(sim, eid, "perception")
    score = (mechanics * 0.44) + (conversation * 0.24) + (streetwise * 0.2) + (perception * 0.12)
    edge = _service_edge(score, baseline=5.0)
    return {
        "score": score,
        "price_mult": max(0.93, 1.0 - (edge * 0.07)),
        "note": _mobility_service_note(mechanics, conversation, streetwise, perception, edge),
    }


def _intel_note(perception, conversation, streetwise, edge):
    if float(edge) < 0.12:
        return ""
    if perception >= max(conversation, streetwise):
        return "you catch the useful details"
    if streetwise >= max(perception, conversation):
        return "you know which leads are worth chasing"
    return "you know what questions to ask"


def intel_skill_terms(sim, eid):
    perception = actor_skill(sim, eid, "perception")
    conversation = actor_skill(sim, eid, "conversation")
    streetwise = actor_skill(sim, eid, "streetwise")
    score = (perception * 0.56) + (streetwise * 0.28) + (conversation * 0.16)
    edge = _service_edge(score, baseline=5.0)
    radius_bonus = 0
    if score >= 6.2:
        radius_bonus += 1
    if score >= 8.1:
        radius_bonus += 1
    line_limit = 4
    if score >= 5.8:
        line_limit += 1
    if score >= 7.8:
        line_limit += 1
    detail_level = 0
    if edge >= 0.12:
        detail_level = 1
    if score >= 7.8:
        detail_level = 2
    return {
        "score": score,
        "radius_bonus": radius_bonus,
        "line_limit": line_limit,
        "detail_level": detail_level,
        "note": _intel_note(perception, conversation, streetwise, edge),
    }


def access_prep_skill_terms(sim, eid):
    intrusion = actor_skill(sim, eid, "intrusion")
    mechanics = actor_skill(sim, eid, "mechanics")
    perception = actor_skill(sim, eid, "perception")
    streetwise = actor_skill(sim, eid, "streetwise")
    score = (intrusion * 0.38) + (mechanics * 0.24) + (perception * 0.24) + (streetwise * 0.14)
    edge = _service_edge(score, baseline=5.0)
    reveal_tier = 0
    if score >= 5.9:
        reveal_tier = 1
    if score >= 7.8:
        reveal_tier = 2

    if edge < 0.12:
        note = ""
    elif intrusion >= max(mechanics, perception, streetwise):
        note = "you map the clean entry route"
    elif mechanics >= max(intrusion, perception, streetwise):
        note = "you read the hardware fast"
    elif perception >= max(intrusion, mechanics, streetwise):
        note = "you spot the useful seams"
    else:
        note = "you read the place like a local job"

    return {
        "score": score,
        "reveal_tier": reveal_tier,
        "note": note,
    }


def dialogue_prep_skill_terms(sim, eid):
    conversation = actor_skill(sim, eid, "conversation")
    intrusion = actor_skill(sim, eid, "intrusion")
    perception = actor_skill(sim, eid, "perception")
    streetwise = actor_skill(sim, eid, "streetwise")
    mechanics = actor_skill(sim, eid, "mechanics")
    score = (
        (conversation * 0.28)
        + (intrusion * 0.24)
        + (perception * 0.18)
        + (streetwise * 0.18)
        + (mechanics * 0.12)
    )
    edge = _service_edge(score, baseline=5.0)
    detail_level = 0
    if score >= 5.9:
        detail_level = 1
    if score >= 7.9:
        detail_level = 2

    if edge < 0.12:
        note = ""
    elif conversation >= max(intrusion, perception, streetwise, mechanics):
        note = "you ask the right way"
    elif intrusion >= max(conversation, perception, streetwise, mechanics):
        note = "you probe for the clean bypass"
    elif perception >= max(conversation, intrusion, streetwise, mechanics):
        note = "you catch the useful seams"
    elif streetwise >= max(conversation, intrusion, perception, mechanics):
        note = "you steer toward routines and blind spots"
    else:
        note = "you read the hardware underneath the answer"

    return {
        "score": score,
        "detail_level": detail_level,
        "note": note,
    }


def scan_skill_terms(sim, eid):
    perception = actor_skill(sim, eid, "perception")
    conversation = actor_skill(sim, eid, "conversation")
    streetwise = actor_skill(sim, eid, "streetwise")
    score = (perception * 0.7) + (streetwise * 0.2) + (conversation * 0.1)
    edge = _service_edge(score, baseline=5.05)
    radius_bonus = 0
    if score >= 6.0:
        radius_bonus += 1
    if score >= 8.4:
        radius_bonus += 1
    detail_level = 0
    if edge >= 0.12:
        detail_level = 1
    if score >= 7.7:
        detail_level = 2
    return {
        "score": score,
        "radius_bonus": radius_bonus,
        "detail_level": detail_level,
        "display_limit": 5 + (1 if score >= 7.2 else 0),
        "note": _intel_note(perception, conversation, streetwise, edge),
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


def seed_skill_profile(rng, *, role="", career="", core=None, insight=None, jitter=0.35, birth_key=""):
    if rng is None:
        rng = random.Random(0)

    role_key = str(role or "").strip().lower()
    career_text = str(career or "").strip().lower().replace(" ", "_")
    birth_biases = _player_birth_skill_biases(birth_key) if role_key == "player" else {}
    ratings = {}
    for skill_id in SKILL_DEFS:
        value = derived_skill_value(skill_id, core=core, insight=insight, default=5.0)
        value += float(ROLE_SKILL_MODS.get(role_key, {}).get(skill_id, 0.0))
        for keyword, mods in CAREER_KEYWORD_SKILL_MODS.items():
            if keyword in career_text:
                value += float(mods.get(skill_id, 0.0))
        value += float(rng.uniform(-abs(float(jitter)), abs(float(jitter))))
        value += float(birth_biases.get(skill_id, 0.0))
        ratings[skill_id] = _clamp_skill(value)
    return SkillProfile(ratings=ratings, birth_biases=birth_biases)


def access_skill_practice_awards(context, *, success, fumbled=False):
    context_key = normalize_tool_context(context)
    success = bool(success)
    fumbled = bool(fumbled)

    intrusion = 0.42 if success else 0.26
    mechanics = 0.12 if success else 0.08
    perception = 0.05 if success else 0.03

    if context_key in {"vehicle_ignition", "relay_controller"}:
        mechanics += 0.14 if success else 0.1
    elif context_key in {"schedule_controller", "biometric_controller"}:
        mechanics += 0.1 if success else 0.07
    elif context_key in {"mechanical_lock", "side_entry"}:
        mechanics += 0.06 if success else 0.04
    elif context_key == "badge_controller":
        perception += 0.03 if success else 0.02

    if fumbled:
        intrusion *= 0.7
        mechanics *= 0.65
        perception *= 0.6

    return {
        "intrusion": max(0.0, float(intrusion)),
        "mechanics": max(0.0, float(mechanics)),
        "perception": max(0.0, float(perception)),
    }
