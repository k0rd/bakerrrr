import random

from game.components import ContactLedger, FinancialProfile, PlayerAssets, PropertyKnowledge
from game.objective_progress import objective_metric_bonuses


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_nonzero(value, default=1):
    return max(1, _safe_int(value, default=default))


def _player_metrics(sim, player_eid, objective_id=""):
    assets = sim.ecs.get(PlayerAssets).get(player_eid) if sim is not None else None
    finance = sim.ecs.get(FinancialProfile).get(player_eid) if sim is not None else None
    ledger = sim.ecs.get(ContactLedger).get(player_eid) if sim is not None else None
    knowledge = sim.ecs.get(PropertyKnowledge).get(player_eid) if sim is not None else None

    wallet = _safe_int(getattr(assets, "credits", 0), default=0)
    bank = _safe_int(getattr(finance, "bank_balance", 0), default=0)
    reserve_credits = max(0, wallet + bank)
    contact_count = len(getattr(ledger, "by_property", {}) or {})
    intel_leads = len(getattr(knowledge, "known", {}) or {})

    visits_by_eid = getattr(sim, "overworld_visit_state_by_eid", {}) if sim is not None else {}
    visited = visits_by_eid.get(player_eid, set()) if isinstance(visits_by_eid, dict) else set()
    if isinstance(visited, set):
        chunks_visited = len(visited)
    elif isinstance(visited, (list, tuple)):
        chunks_visited = len(visited)
    else:
        chunks_visited = 0

    metrics = {
        "wallet_credits": wallet,
        "bank_credits": bank,
        "reserve_credits": reserve_credits,
        "contact_count": int(contact_count),
        "intel_leads": int(intel_leads),
        "chunks_visited": int(chunks_visited),
    }
    bonuses = objective_metric_bonuses(sim, objective_id=objective_id)
    for key in ("reserve_credits", "contact_count", "intel_leads"):
        bonus = max(0, _safe_int(bonuses.get(key), default=0))
        metrics[f"base_{key}"] = int(metrics.get(key, 0))
        metrics[key] = int(metrics.get(key, 0)) + bonus
        metrics[f"bonus_{key}"] = bonus
    metrics["objective_bonus_raw"] = dict(bonuses.get("raw", {}))
    return metrics


def _ratio(progress, target):
    target = _safe_nonzero(target, default=1)
    progress = max(0, _safe_int(progress, default=0))
    return min(1.0, float(progress) / float(target))


def _bonus_raw(metrics):
    raw = metrics.get("objective_bonus_raw", {})
    return raw if isinstance(raw, dict) else {}


def _objective_eval_debt_exit(objective, metrics):
    targets = dict(objective.get("targets", {}))
    reserve_target = _safe_nonzero(targets.get("reserve_credits"), default=520)
    reserve_now = metrics["reserve_credits"]
    reserve_bonus = _safe_int(metrics.get("bonus_reserve_credits"), default=0)
    done = reserve_now >= reserve_target
    progress = _ratio(reserve_now, reserve_target)
    next_step = (
        "Reach a transport-connected district and extract."
        if done
        else "Build reserves via trade, contracts, salvage, or theft."
    )
    summary_line = f"Objective Debt Exit: {reserve_now}/{reserve_target} cr reserve"
    if reserve_bonus > 0:
        summary_line = f"{summary_line} (+{reserve_bonus} objective)"
    why_lines = (
        "You are trying to finance a clean exit before the district closes around you.",
    )
    how_lines = (
        f"Reserve = wallet {metrics['wallet_credits']} + bank {metrics['bank_credits']} + objective bonus {reserve_bonus} = {reserve_now}.",
        "Trade, salvage, theft, and credit-heavy opportunities move this fastest.",
        "Only reserve counts directly here; contacts, leads, and scouting only help indirectly.",
    )
    activity_lines = (
        "Best routes now: storefront margins, salvage-heavy chunks, and high-credit opportunities.",
        "Banked money is still part of reserve, so deposits are safe progress, not lost progress.",
    )
    return {
        "completed": done,
        "progress_ratio": progress,
        "summary_line": summary_line,
        "next_step": next_step,
        "why_lines": why_lines,
        "how_lines": how_lines,
        "activity_lines": activity_lines,
    }


def _objective_eval_networked_extraction(objective, metrics):
    targets = dict(objective.get("targets", {}))
    contact_target = _safe_nonzero(targets.get("contact_count"), default=4)
    reserve_target = _safe_nonzero(targets.get("reserve_credits"), default=240)
    visit_target = _safe_nonzero(targets.get("chunks_visited"), default=6)

    contact_now = metrics["contact_count"]
    reserve_now = metrics["reserve_credits"]
    visit_now = metrics["chunks_visited"]
    contact_bonus = _safe_int(metrics.get("bonus_contact_count"), default=0)
    reserve_bonus = _safe_int(metrics.get("bonus_reserve_credits"), default=0)
    raw_bonus = _bonus_raw(metrics)
    network_marks = _safe_int(raw_bonus.get("network_marks"), default=0)
    reserve_support = _safe_int(raw_bonus.get("reserve_bonus_credits"), default=0)

    contact_ok = contact_now >= contact_target
    reserve_ok = reserve_now >= reserve_target
    visit_ok = visit_now >= visit_target
    done = contact_ok and reserve_ok and visit_ok

    if not contact_ok:
        next_step = "Talk and build local contacts."
    elif not reserve_ok:
        next_step = "Raise reserves for extraction logistics."
    elif not visit_ok:
        next_step = "Scout more chunks to secure routes."
    else:
        next_step = "Route is ready. Move to extraction."

    progress = (
        _ratio(contact_now, contact_target)
        + _ratio(reserve_now, reserve_target)
        + _ratio(visit_now, visit_target)
    ) / 3.0
    summary_line = (
        "Objective Networked Extraction: "
        f"c{contact_now}/{contact_target} "
        f"r{reserve_now}/{reserve_target} "
        f"v{visit_now}/{visit_target}"
    )
    bonus_bits = []
    if contact_bonus > 0:
        bonus_bits.append(f"c+{contact_bonus}")
    if reserve_bonus > 0:
        bonus_bits.append(f"r+{reserve_bonus}")
    if bonus_bits:
        summary_line = f"{summary_line} ({' '.join(bonus_bits)} objective)"
    why_lines = (
        "Extraction needs more than cash: you need people, logistics, and route familiarity.",
    )
    how_lines = (
        f"Contacts = direct {metrics.get('base_contact_count', contact_now - contact_bonus)} + objective bonus {contact_bonus} ({network_marks} network marks) = {contact_now}.",
        f"Reserve = direct {metrics.get('base_reserve_credits', reserve_now - reserve_bonus)} + objective bonus {reserve_bonus} ({reserve_support} reserve support) = {reserve_now}.",
        f"Scouting = {visit_now} visited chunks. This objective does not complete from a single strong lane alone.",
        "Conversion rule: 2 network marks = +1 contact and 2 reserve support = +1 reserve.",
    )
    activity_lines = (
        "Best routes now: talk to locals, secure contacts, take district-contract style opportunities, and keep scouting.",
        "If one track is lagging, the whole extraction plan is still incomplete.",
    )
    return {
        "completed": done,
        "progress_ratio": progress,
        "summary_line": summary_line,
        "next_step": next_step,
        "why_lines": why_lines,
        "how_lines": how_lines,
        "activity_lines": activity_lines,
    }


def _objective_eval_high_value_retrieval(objective, metrics):
    targets = dict(objective.get("targets", {}))
    lead_target = _safe_nonzero(targets.get("intel_leads"), default=4)
    visit_target = _safe_nonzero(targets.get("chunks_visited"), default=7)

    leads_now = metrics["intel_leads"]
    visit_now = metrics["chunks_visited"]
    lead_bonus = _safe_int(metrics.get("bonus_intel_leads"), default=0)
    raw_bonus = _bonus_raw(metrics)
    intel_marks = _safe_int(raw_bonus.get("intel_marks"), default=0)
    leads_ok = leads_now >= lead_target
    visit_ok = visit_now >= visit_target
    done = leads_ok and visit_ok

    if not leads_ok:
        next_step = "Gather leads from locals and service intel points."
    elif not visit_ok:
        next_step = "Scout additional chunks to find target paths."
    else:
        next_step = "Target chain identified. Move to retrieval."

    progress = (
        _ratio(leads_now, lead_target)
        + _ratio(visit_now, visit_target)
    ) / 2.0
    summary_line = (
        "Objective High-Value Retrieval: "
        f"leads {leads_now}/{lead_target} "
        f"scout {visit_now}/{visit_target}"
    )
    if lead_bonus > 0:
        summary_line = f"{summary_line} (leads +{lead_bonus} objective)"
    why_lines = (
        "This run is about building a lead chain before you commit to the retrieval strike.",
    )
    how_lines = (
        f"Leads = direct {metrics.get('base_intel_leads', leads_now - lead_bonus)} + objective bonus {lead_bonus} ({intel_marks} intel marks) = {leads_now}.",
        f"Scouting = {visit_now} visited chunks. You need both stronger leads and broader route coverage.",
        "Conversion rule: 2 intel marks = +1 lead.",
    )
    activity_lines = (
        "Best routes now: intel services, discovery-heavy scouting, local talk, and lead-followup opportunities.",
        "Pure money does not directly solve this objective unless it helps you reach more intel or more city coverage.",
    )
    return {
        "completed": done,
        "progress_ratio": progress,
        "summary_line": summary_line,
        "next_step": next_step,
        "why_lines": why_lines,
        "how_lines": how_lines,
        "activity_lines": activity_lines,
    }


def evaluate_run_objective(sim, player_eid, objective=None):
    if not isinstance(objective, dict):
        traits = getattr(sim, "world_traits", {}) if sim is not None else {}
        objective = traits.get("run_objective") if isinstance(traits, dict) else None
    if not isinstance(objective, dict):
        return None

    objective_id = str(objective.get("id", "")).strip().lower()
    if not objective_id:
        return None

    metrics = _player_metrics(sim, player_eid, objective_id=objective_id)
    title = str(objective.get("title", "")).strip() or "Run Objective"
    summary = str(objective.get("summary", "")).strip()

    if objective_id == "debt_exit":
        result = _objective_eval_debt_exit(objective, metrics)
    elif objective_id == "networked_extraction":
        result = _objective_eval_networked_extraction(objective, metrics)
    elif objective_id == "high_value_retrieval":
        result = _objective_eval_high_value_retrieval(objective, metrics)
    else:
        return None

    return {
        "id": objective_id,
        "title": title,
        "summary": summary,
        "metrics": metrics,
        "completed": bool(result["completed"]),
        "progress_ratio": float(result["progress_ratio"]),
        "summary_line": str(result["summary_line"]),
        "next_step": str(result["next_step"]),
        "why_lines": tuple(str(line).strip() for line in result.get("why_lines", ()) if str(line).strip()),
        "how_lines": tuple(str(line).strip() for line in result.get("how_lines", ()) if str(line).strip()),
        "activity_lines": tuple(str(line).strip() for line in result.get("activity_lines", ()) if str(line).strip()),
    }


def seed_run_objective(sim, rng):
    if not isinstance(rng, random.Random):
        rng = random.Random(str(rng))

    objective_roll = rng.choice(
        ("debt_exit", "networked_extraction", "high_value_retrieval")
    )

    if objective_roll == "debt_exit":
        objective = {
            "id": "debt_exit",
            "title": "Debt Exit",
            "summary": "Build enough reserve credits to buy a clean way out.",
            "targets": {
                "reserve_credits": rng.randint(440, 760),
            },
        }
    elif objective_roll == "networked_extraction":
        objective = {
            "id": "networked_extraction",
            "title": "Networked Extraction",
            "summary": "Build trusted contacts, reserves, and route familiarity for extraction.",
            "targets": {
                "contact_count": rng.randint(3, 5),
                "reserve_credits": rng.randint(180, 320),
                "chunks_visited": rng.randint(5, 8),
            },
        }
    else:
        objective = {
            "id": "high_value_retrieval",
            "title": "High-Value Retrieval",
            "summary": "Gather strong leads, scout the city, and locate a retrieval chain.",
            "targets": {
                "intel_leads": rng.randint(3, 5),
                "chunks_visited": rng.randint(6, 10),
            },
        }

    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
    sim.world_traits["run_objective"] = objective
    return objective
