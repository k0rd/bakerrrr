import random

from game.components import ContactLedger, FinancialProfile, PlayerAssets, PropertyKnowledge
from game.objective_progress import objective_metric_bonuses
from game.player_businesses import player_business_state, property_supports_player_business


RUN_OBJECTIVE_VARIANTS = {
    "debt_exit": (
        {
            "id": "clean_break",
            "title": "A Clean Break",
            "summary": "Leaving cleanly will take passage money and enough reserve to land on your feet.",
            "culmination_title": "Departure",
        },
        {
            "id": "bought_time",
            "title": "Bought Time",
            "summary": "You have a little room to move. Turn it into enough money to leave on your own terms.",
            "culmination_title": "The Way Out",
        },
        {
            "id": "last_fare",
            "title": "The Last Fare",
            "summary": "A route out exists, but the fare and a safe landing cost more than you have.",
            "culmination_title": "Last Departure",
        },
    ),
    "networked_extraction": (
        {
            "id": "quiet_arrangement",
            "title": "A Quiet Arrangement",
            "summary": "A safe departure needs trusted people, money behind it, and a route everyone understands.",
            "culmination_title": "The Rendezvous",
        },
        {
            "id": "chain_of_favors",
            "title": "A Chain of Favors",
            "summary": "No single contact can get you clear. Build the chain, finance it, and learn the way through.",
            "culmination_title": "The Handoff",
        },
        {
            "id": "people_who_answer",
            "title": "People Who Answer",
            "summary": "Find people who will answer when it matters, then give them the resources and route to move.",
            "culmination_title": "The Meeting Place",
        },
    ),
    "high_value_retrieval": (
        {
            "id": "buried_lead",
            "title": "The Buried Lead",
            "summary": "A valuable asset is out there. Build a reliable lead chain before committing to the recovery.",
            "culmination_title": "The Recovery",
        },
        {
            "id": "marked_asset",
            "title": "The Marked Asset",
            "summary": "Enough fragments point toward something valuable, but not yet toward the right door.",
            "culmination_title": "The Retrieval",
        },
        {
            "id": "missing_piece",
            "title": "The Missing Piece",
            "summary": "Somewhere in the city is the piece that makes this run worthwhile. Find the trail before the site.",
            "culmination_title": "The Final Lead",
        },
    ),
    "neighborhood_control": (
        {
            "id": "put_down_roots",
            "title": "Put Down Roots",
            "summary": "Turn a handful of nearby properties into a place where your name has weight.",
            "culmination_title": "Home Ground",
        },
        {
            "id": "hold_the_corner",
            "title": "Hold the Corner",
            "summary": "Scattered holdings are not a neighborhood. Build a block you can return to and call yours.",
            "culmination_title": "Back on the Block",
        },
        {
            "id": "block_of_your_own",
            "title": "A Block of Your Own",
            "summary": "Acquire a real local foothold: several holdings close enough to reinforce one another.",
            "culmination_title": "The Front Door",
        },
    ),
    "working_owner": (
        {
            "id": "keep_the_lights_on",
            "title": "Keep the Lights On",
            "summary": "Take over a real business, keep a full crew paid, and leave enough in the account for the next hour.",
            "culmination_title": "Closing Time",
        },
        {
            "id": "first_payroll",
            "title": "First Payroll",
            "summary": "Ownership only counts once the doors open, the crew gets paid, and the business can carry itself forward.",
            "culmination_title": "End of Shift",
        },
        {
            "id": "your_own_counter",
            "title": "Your Own Counter",
            "summary": "Put your name on a working storefront and prove it can earn through an ordinary staffed hour.",
            "culmination_title": "The Owner's Door",
        },
    ),
}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_nonzero(value, default=1):
    return max(1, _safe_int(value, default=default))


def _manhattan(a, b):
    if not isinstance(a, (tuple, list)) or not isinstance(b, (tuple, list)):
        return 0
    return abs(_safe_int(a[0]) - _safe_int(b[0])) + abs(_safe_int(a[1]) - _safe_int(b[1]))


def _visibility_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("run_objective_visibility")
    if not isinstance(state, dict):
        state = {}
        traits["run_objective_visibility"] = state
    state.setdefault("player_visible", True)
    state.setdefault("revealed_tick", 0 if state.get("player_visible", True) else -1)
    state.setdefault("source", "default")
    return state


def set_run_objective_visibility(sim, *, visible=True, source=""):
    state = _visibility_state(sim)
    state["player_visible"] = bool(visible)
    if visible:
        state["revealed_tick"] = _safe_int(getattr(sim, "tick", 0), default=0)
    else:
        state["revealed_tick"] = -1
    state["source"] = str(source or ("startup" if not visible else "reveal")).strip().lower() or (
        "startup" if not visible else "reveal"
    )
    return dict(state)


def reveal_run_objective(sim, source=""):
    state = _visibility_state(sim)
    if bool(state.get("player_visible", True)):
        return False
    set_run_objective_visibility(sim, visible=True, source=source or "live_reveal")
    return True


def is_run_objective_visible_to_player(sim, player_eid=None):
    del player_eid
    state = _visibility_state(sim)
    return bool(state.get("player_visible", True))


def _owned_property_cluster_metrics(sim, player_eid):
    owned_ids = set()
    assets = sim.ecs.get(PlayerAssets).get(player_eid) if sim is not None else None
    if assets:
        owned_ids.update(
            str(raw_id or "").strip()
            for raw_id in getattr(assets, "owned_property_ids", set()) or set()
            if str(raw_id or "").strip()
        )

    owned_props = []
    for prop_id, prop in getattr(sim, "properties", {}).items():
        if not isinstance(prop, dict):
            continue
        current_id = str(prop_id or prop.get("id") or "").strip()
        if not current_id:
            continue
        if prop.get("owner_eid") == player_eid:
            owned_ids.add(current_id)
        if current_id not in owned_ids:
            continue
        owned_props.append((current_id, prop))

    chunk_counts = {}
    for _property_id, prop in owned_props:
        try:
            chunk = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
        except (TypeError, ValueError):
            continue
        chunk_counts[chunk] = chunk_counts.get(chunk, 0) + 1

    best_anchor = None
    best_cluster = 0
    best_chunks = 0
    for anchor in chunk_counts:
        cluster_total = 0
        cluster_chunks = 0
        for chunk, count in chunk_counts.items():
            if _manhattan(anchor, chunk) <= 1:
                cluster_total += int(count)
                cluster_chunks += 1
        if cluster_total > best_cluster or (
            cluster_total == best_cluster and cluster_chunks > best_chunks
        ):
            best_anchor = anchor
            best_cluster = cluster_total
            best_chunks = cluster_chunks

    business_rows = []
    for property_id, prop in owned_props:
        if not property_supports_player_business(prop):
            continue
        state = player_business_state(prop, create=False)
        if not isinstance(state, dict):
            continue
        required_staff = max(1, _safe_int(state.get("required_staff"), default=1))
        staff_ids = {
            _safe_int(raw_eid)
            for raw_eid in list(state.get("staff_roster", ()) or ())
            if _safe_int(raw_eid) > 0
        }
        raw_roles = state.get("staff_roles")
        if isinstance(raw_roles, dict):
            staff_ids.update(
                _safe_int(raw_eid)
                for raw_eid in raw_roles
                if _safe_int(raw_eid) > 0
            )
        staff_total = len(staff_ids)
        fully_staffed = staff_total >= required_staff
        last_summary = state.get("last_summary")
        last_summary = last_summary if isinstance(last_summary, dict) else {}
        realized_revenue = max(0, _safe_int(last_summary.get("realized_revenue"), default=0))
        completed_open_cycle = "hour" in last_summary and bool(last_summary.get("open_now"))
        clean_cycle = bool(
            completed_open_cycle
            and realized_revenue > 0
            and _safe_int(last_summary.get("staff_total"), default=0) >= required_staff
            and "unpaid_wages" in last_summary
            and "unpaid_upkeep" in last_summary
            and _safe_int(last_summary.get("unpaid_wages"), default=0) <= 0
            and _safe_int(last_summary.get("unpaid_upkeep"), default=0) <= 0
        )
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        business_rows.append({
            "property_id": property_id,
            "property_name": (
                str(metadata.get("business_name", "")).strip()
                or str(prop.get("name", "")).strip()
                or property_id
                or "your business"
            ),
            "account_balance": max(0, _safe_int(state.get("account_balance"), default=0)),
            "required_staff": required_staff,
            "staff_total": staff_total,
            "fully_staffed": fully_staffed,
            "clean_operating_cycle": clean_cycle,
            "last_realized_revenue": realized_revenue,
        })

    business_rows.sort(key=lambda row: (
        -int(bool(row["fully_staffed"] and row["clean_operating_cycle"])),
        -int(bool(row["clean_operating_cycle"])),
        -int(bool(row["fully_staffed"])),
        -int(row["account_balance"]),
        -int(row["last_realized_revenue"]),
        str(row["property_name"]).casefold(),
        str(row["property_id"]),
    ))
    best_business = business_rows[0] if business_rows else {}

    return {
        "owned_property_count": len(owned_ids),
        "owned_property_chunks": len(chunk_counts),
        "largest_property_cluster": int(best_cluster),
        "largest_property_cluster_chunks": int(best_chunks),
        "largest_property_cluster_anchor": best_anchor,
        "owned_business_count": len(business_rows),
        "fully_staffed_business_count": sum(1 for row in business_rows if row["fully_staffed"]),
        "clean_operating_business_count": sum(1 for row in business_rows if row["clean_operating_cycle"]),
        "best_business_property_id": str(best_business.get("property_id", "")),
        "best_business_property_name": str(best_business.get("property_name", "")),
        "best_business_account_balance": _safe_int(best_business.get("account_balance"), default=0),
        "best_business_required_staff": _safe_int(best_business.get("required_staff"), default=1),
        "best_business_staff_total": _safe_int(best_business.get("staff_total"), default=0),
        "best_business_fully_staffed": bool(best_business.get("fully_staffed", False)),
        "best_business_clean_operating_cycle": bool(best_business.get("clean_operating_cycle", False)),
        "best_business_last_realized_revenue": _safe_int(best_business.get("last_realized_revenue"), default=0),
    }


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
    metrics.update(_owned_property_cluster_metrics(sim, player_eid))
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
    summary_line = f"Exit reserve: {reserve_now} of {reserve_target} credits ready"
    if reserve_bonus > 0:
        summary_line = f"{summary_line}, including {reserve_bonus} earned through completed work"
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
        "Extraction preparations: "
        f"{contact_now} of {contact_target} trusted contacts, "
        f"{reserve_now} of {reserve_target} credits, "
        f"{visit_now} of {visit_target} districts scouted"
    )
    bonus_bits = []
    if contact_bonus > 0:
        bonus_bits.append(f"c+{contact_bonus}")
    if reserve_bonus > 0:
        bonus_bits.append(f"r+{reserve_bonus}")
    if bonus_bits:
        summary_line = f"{summary_line} ({', '.join(bonus_bits)} from completed work)"
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
        "Lead chain: "
        f"{leads_now} of {lead_target} useful leads, "
        f"{visit_now} of {visit_target} districts searched"
    )
    if lead_bonus > 0:
        summary_line = f"{summary_line} ({lead_bonus} leads came from completed work)"
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


def _objective_eval_neighborhood_control(objective, metrics):
    targets = dict(objective.get("targets", {}))
    owned_target = _safe_nonzero(targets.get("owned_property_count"), default=5)
    cluster_target = _safe_nonzero(targets.get("largest_property_cluster"), default=4)

    owned_now = max(0, _safe_int(metrics.get("owned_property_count"), default=0))
    cluster_now = max(0, _safe_int(metrics.get("largest_property_cluster"), default=0))
    cluster_chunks = max(0, _safe_int(metrics.get("largest_property_cluster_chunks"), default=0))
    anchor = metrics.get("largest_property_cluster_anchor")
    anchor_text = ""
    if isinstance(anchor, (tuple, list)) and len(anchor) == 2:
        anchor_text = f" around chunk ({_safe_int(anchor[0])}, {_safe_int(anchor[1])})"

    owned_ok = owned_now >= owned_target
    cluster_ok = cluster_now >= cluster_target
    done = owned_ok and cluster_ok

    if not cluster_ok:
        next_step = "Buy adjacent properties and tighten your local footprint."
    elif not owned_ok:
        next_step = "Add one more property without scattering too far from your core block."
    else:
        next_step = "Local footprint is secure. Turn it into real neighborhood control."

    progress = (
        _ratio(owned_now, owned_target)
        + _ratio(cluster_now, cluster_target)
    ) / 2.0
    summary_line = (
        "Local foothold: "
        f"{owned_now} of {owned_target} properties owned, "
        f"strongest cluster {cluster_now} of {cluster_target}"
    )
    if cluster_chunks > 0:
        summary_line = f"{summary_line} ({cluster_chunks} local chunks{anchor_text})"

    why_lines = (
        "This run is about turning scattered assets into a block you can actually lean on and defend.",
    )
    how_lines = (
        f"Owned properties = {owned_now}. Total holdings still matter, but they do not prove local control on their own.",
        f"Neighborhood cluster = {cluster_now}. It counts the densest owned patch inside a 3x3 local chunk spread{anchor_text}.",
        "Scattered purchases help the total, but only nearby holdings push the control cluster forward.",
    )
    activity_lines = (
        "Best routes now: cash-positive local work, nearby service leads, and property buys that sit close to what you already own.",
        "If a purchase would sit far from your current cluster, it is growth, but not the fastest control progress.",
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


def _objective_eval_working_owner(objective, metrics):
    targets = dict(objective.get("targets", {}))
    reserve_target = _safe_nonzero(targets.get("operating_reserve"), default=24)

    business_count = max(0, _safe_int(metrics.get("owned_business_count"), default=0))
    property_name = str(metrics.get("best_business_property_name", "")).strip() or "your business"
    staff_total = max(0, _safe_int(metrics.get("best_business_staff_total"), default=0))
    required_staff = _safe_nonzero(metrics.get("best_business_required_staff"), default=1)
    reserve_now = max(0, _safe_int(metrics.get("best_business_account_balance"), default=0))
    realized_revenue = max(0, _safe_int(metrics.get("best_business_last_realized_revenue"), default=0))
    fully_staffed = bool(metrics.get("best_business_fully_staffed", False))
    clean_cycle = bool(metrics.get("best_business_clean_operating_cycle", False))

    owns_business = business_count > 0
    reserve_ok = reserve_now >= reserve_target
    done = owns_business and fully_staffed and clean_cycle and reserve_ok
    if not owns_business:
        next_step = "Buy a working business and take over its operating account."
    elif not fully_staffed:
        next_step = f"Bring {property_name} up to its full working crew."
    elif not clean_cycle:
        next_step = f"Fund {property_name}, then let it trade through an open hour with payroll and upkeep paid."
    elif not reserve_ok:
        next_step = f"Leave at least {reserve_target} credits in {property_name}'s operating account."
    else:
        next_step = f"{property_name} can carry itself. Return there at the end of the shift."

    progress = (
        (1.0 if owns_business else 0.0)
        + _ratio(staff_total, required_staff)
        + (1.0 if clean_cycle else 0.0)
        + _ratio(reserve_now, reserve_target)
    ) / 4.0
    cycle_text = (
        f"last open hour earned {realized_revenue} credits with payroll and upkeep clear"
        if clean_cycle
        else "still needs a profitable open hour with payroll and upkeep clear"
    )
    summary_line = (
        f"Working business: {property_name}; crew {staff_total} of {required_staff}, "
        f"{cycle_text}, reserve {reserve_now} of {reserve_target} credits"
    )
    why_lines = (
        "This run is about making one owned business work as a place, a crew, and an operating account rather than treating the deed as the finish line.",
    )
    how_lines = (
        f"Crew = {staff_total} of {required_staff} required at {property_name}.",
        f"Last clean open hour revenue = {realized_revenue}; unpaid wages and upkeep must both be zero.",
        f"Operating reserve = {reserve_now} of {reserve_target} credits in that same business account.",
        "All requirements must belong to one business; several partial businesses do not combine into a win.",
    )
    activity_lines = (
        "Best routes now: acquire a storefront, retain or hire its full crew, fund the operating account, and stay close enough to see an open hour through.",
        "Trade and supply opportunities can finance the shop, but the ordinary hourly business simulation decides whether it actually works.",
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
    elif objective_id == "neighborhood_control":
        result = _objective_eval_neighborhood_control(objective, metrics)
    elif objective_id == "working_owner":
        result = _objective_eval_working_owner(objective, metrics)
    else:
        return None

    return {
        "id": objective_id,
        "variant_id": str(objective.get("variant_id", "")).strip().lower(),
        "title": title,
        "summary": summary,
        "culmination_title": str(objective.get("culmination_title", "")).strip() or "Final Move",
        "metrics": metrics,
        "completed": bool(result["completed"]),
        "progress_ratio": float(result["progress_ratio"]),
        "summary_line": str(result["summary_line"]),
        "next_step": str(result["next_step"]),
        "why_lines": tuple(str(line).strip() for line in result.get("why_lines", ()) if str(line).strip()),
        "how_lines": tuple(str(line).strip() for line in result.get("how_lines", ()) if str(line).strip()),
        "activity_lines": tuple(str(line).strip() for line in result.get("activity_lines", ()) if str(line).strip()),
    }


def evaluate_visible_run_objective(sim, player_eid, objective=None):
    if not is_run_objective_visible_to_player(sim, player_eid=player_eid):
        return None
    return evaluate_run_objective(sim, player_eid, objective=objective)


def seed_run_objective(sim, rng, *, visible=True):
    if not isinstance(rng, random.Random):
        rng = random.Random(str(rng))

    objective_roll = rng.choice(
        ("debt_exit", "networked_extraction", "high_value_retrieval", "neighborhood_control", "working_owner")
    )
    variant = dict(rng.choice(RUN_OBJECTIVE_VARIANTS[objective_roll]))

    if objective_roll == "debt_exit":
        objective = {
            "id": "debt_exit",
            "targets": {
                "reserve_credits": rng.randint(440, 760),
            },
        }
    elif objective_roll == "networked_extraction":
        objective = {
            "id": "networked_extraction",
            "targets": {
                "contact_count": rng.randint(3, 5),
                "reserve_credits": rng.randint(180, 320),
                "chunks_visited": rng.randint(5, 8),
            },
        }
    elif objective_roll == "neighborhood_control":
        objective = {
            "id": "neighborhood_control",
            "targets": {
                "owned_property_count": rng.randint(4, 6),
                "largest_property_cluster": rng.randint(3, 5),
            },
        }
    elif objective_roll == "working_owner":
        objective = {
            "id": "working_owner",
            "targets": {
                "operating_reserve": rng.randint(18, 34),
            },
        }
    else:
        objective = {
            "id": "high_value_retrieval",
            "targets": {
                "intel_leads": rng.randint(3, 5),
                "chunks_visited": rng.randint(6, 10),
            },
        }

    objective.update({
        "variant_id": str(variant.get("id", "")).strip().lower(),
        "title": str(variant.get("title", "")).strip() or "A Way Forward",
        "summary": str(variant.get("summary", "")).strip(),
        "culmination_title": str(variant.get("culmination_title", "")).strip() or "Final Move",
    })

    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
    sim.world_traits["run_objective"] = objective
    set_run_objective_visibility(sim, visible=bool(visible), source="seed")
    return objective
