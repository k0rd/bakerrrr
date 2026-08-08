"""Two-way dialogue adapters for the Social Fact Graph.

This first vertical slice lets a player bring actor-owned incident knowledge to
one particular NPC.  Resolution compares the player's claim with the NPC's own
knowledge and graph perspective.  It never reads the canonical incident
registry, so an NPC cannot react to truth they have not encountered.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from engine.events import Event

from game.components import (
    AI,
    CreatureIdentity,
    FinancialProfile,
    IncidentKnowledge,
    JusticeProfile,
    NPCNeeds,
    NPCRoutine,
    NPCSocial,
    NPCTraits,
    Occupation,
    Position,
    PlayerAssets,
    PropertyKnowledge,
)
from game.identity_evidence import (
    actor_identity_snapshot,
    build_witness_subject_account,
    ensure_contact_ledger,
)
from game.incident_silencing import (
    apply_incident_silence_pressure,
    apply_incident_witness_resolution,
    incident_prior_spread_state,
    incident_witness_resolution,
    player_known_firsthand_witness,
)
from game.knowledge_notebook import note_person_notebook_mutation
from game.social_fact_incidents import (
    ensure_actor_incident_perspective,
    incident_knowledge_for,
)
from game.social_fact_consequences import (
    mark_social_fact_action_progress_reported,
    mark_social_fact_action_reported,
    mark_social_fact_correction_relay_reported,
    mark_social_fact_warning_progress_reported,
    request_incident_corroboration,
    request_social_fact_warning_correction,
    social_fact_action_for_thread,
    social_fact_warning_report_for_thread,
)
from game.social_fact_graph import (
    apply_social_effect,
    actor_perspective,
    advance_social_thread,
    ensure_social_edge,
    occurrence_record,
    open_social_thread,
    record_claim,
    record_correction,
    record_occurrence,
    social_fact_graph_state,
    social_thread,
    social_threads_for_actor,
)
from game.skills import actor_skill
from game.system_support.npc_income_runtime import npc_hourly_wage
from game.system_support.awareness_runtime import (
    observation_payload_for_position,
    observation_payload_from_observers,
)
from game.system_support.offense_runtime import _offense_notice_radius, _offense_tier


SOCIAL_FACT_TOPIC_PREFIX = "sfg_"
_EXCHANGE_KIND = "incident_report"
_WITNESS_EXCHANGE_KIND = "witness_resolution"
_FINISHED_THREAD_STATUSES = {"closed", "retracted"}
_TELLABLE_INCIDENT_MAX_AGE_DAYS = 14
_WITNESS_FORBEARANCE_HOURS = 24
_DUTY_ROLES = {
    "guard", "detective", "inspector", "investigator", "officer", "police",
    "deputy", "marshal", "security",
}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _unit(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = float(default)
    return max(0.0, min(1.0, result))


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _token(value: Any) -> str:
    return _text(value).lower().replace(" ", "_")


def _actor_name(sim, actor_eid: Any, fallback: str = "someone") -> str:
    identity = sim.ecs.get(CreatureIdentity).get(_int(actor_eid, 0))
    return _text(
        getattr(identity, "personal_name", "")
        or getattr(identity, "common_name", "")
    ) or fallback


def _ticks_per_hour(sim) -> int:
    world_traits = getattr(sim, "world_traits", {})
    clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
    return max(60, _int((clock or {}).get("ticks_per_hour"), 600))


def _incident_age_ticks(sim, record: Mapping[str, Any]) -> int:
    learned = _int(record.get("last_learned_tick"), _int(record.get("learned_tick"), 0))
    return max(0, _int(getattr(sim, "tick", 0), 0) - learned)


def _incident_implicates_player(record: Mapping[str, Any], player_eid: int) -> bool:
    """Return whether ordinary neutral reporting would conceal player involvement."""

    if _token(record.get("source_kind")) == "self":
        return True
    account = record.get("subject_account") if isinstance(record.get("subject_account"), Mapping) else {}
    return _int(account.get("suspect_eid"), 0) == player_eid


def _witness_resolution_record(
    sim,
    player_eid: int,
    npc_eid: int,
    incident_id: Any,
) -> dict[str, Any] | None:
    incident = _int(incident_id, 0)
    player_knowledge = incident_knowledge_for(sim, player_eid)
    npc_knowledge = incident_knowledge_for(sim, npc_eid)
    player_record = (player_knowledge.records or {}).get(incident) if player_knowledge is not None else None
    npc_record = (npc_knowledge.records or {}).get(incident) if npc_knowledge is not None else None
    if not isinstance(player_record, dict) or not isinstance(npc_record, dict):
        return None
    if _token(player_record.get("source_kind")) != "self":
        return None
    if _token(player_record.get("context")) in {"witness_intimidation", "witness_bribery"}:
        return None
    if not bool(npc_record.get("firsthand", False)):
        return None
    if not isinstance(
        player_known_firsthand_witness(sim, player_eid, npc_eid, incident),
        dict,
    ):
        return None
    return player_record


def _witness_threat_record(
    sim,
    player_eid: int,
    npc_eid: int,
    incident_id: Any,
) -> dict[str, Any] | None:
    """Compatibility name retained for the already-shipped threat resolver."""

    return _witness_resolution_record(sim, player_eid, npc_eid, incident_id)


def _incident_age_label(sim, record: Mapping[str, Any]) -> str:
    age = _incident_age_ticks(sim, record)
    ticks_per_hour = _ticks_per_hour(sim)
    if age < ticks_per_hour:
        return "<1h ago"
    if age < ticks_per_hour * 24:
        return f"{max(1, int(age // ticks_per_hour))}h ago"
    days = max(1, int((age + (ticks_per_hour * 12)) // (ticks_per_hour * 24)))
    return f"{days}d ago"


def _relative_direction(dx: int, dy: int) -> str:
    horizontal = "east" if dx > 0 else "west" if dx < 0 else ""
    vertical = "south" if dy > 0 else "north" if dy < 0 else ""
    if not horizontal:
        return vertical
    if not vertical:
        return horizontal
    if abs(dx) >= abs(dy) * 2:
        return horizontal
    if abs(dy) >= abs(dx) * 2:
        return vertical
    return f"{vertical}{horizontal}"


def _known_incident_place_name(sim, player_eid: int, x: int, y: int, z: int) -> str:
    covering = sim.property_covering(x, y, z) if hasattr(sim, "property_covering") else None
    if not isinstance(covering, dict):
        return ""
    property_id = _text(covering.get("id"))
    knowledge = sim.ecs.get(PropertyKnowledge).get(player_eid)
    if not property_id or knowledge is None or not isinstance(knowledge.property_entry(property_id), dict):
        return ""
    return _text(covering.get("name"))


def _incident_location_label(sim, player_eid: int, record: Mapping[str, Any]) -> str:
    if record.get("x") is None or record.get("y") is None:
        return "location unclear"
    x = _int(record.get("x"), 0)
    y = _int(record.get("y"), 0)
    z = _int(record.get("z"), 0)
    place_name = _known_incident_place_name(sim, player_eid, x, y, z)
    if place_name:
        return f"at {place_name}"
    player_pos = sim.ecs.get(Position).get(player_eid)
    if player_pos is None:
        return "at a remembered location"
    dx = x - _int(player_pos.x, 0)
    dy = y - _int(player_pos.y, 0)
    dz = z - _int(player_pos.z, 0)
    direction = _relative_direction(dx, dy)
    distance = max(abs(dx), abs(dy))
    if dz and distance <= 2:
        return "above here" if dz > 0 else "below here"
    if distance <= 2:
        return "near here"
    if not direction:
        return "on another level"
    if dz:
        return f"{direction}, on another level"
    if distance <= 8:
        return f"nearby {direction}"
    if distance <= 20:
        return f"{direction} of here"
    return f"farther {direction}"


def _incident_choice_detail(sim, player_eid: int, adapted: Mapping[str, Any]) -> str:
    record = adapted.get("record") if isinstance(adapted.get("record"), Mapping) else {}
    return f"{_incident_age_label(sim, record)}, {_incident_location_label(sim, player_eid, record)}"


def _location_matches_property(sim, record: Mapping[str, Any], property_id: Any) -> bool:
    property_key = _text(property_id)
    if not property_key or record.get("x") is None or record.get("y") is None:
        return False
    covering = (
        sim.property_covering(
            _int(record.get("x"), 0),
            _int(record.get("y"), 0),
            _int(record.get("z"), 0),
        )
        if hasattr(sim, "property_covering")
        else None
    )
    return isinstance(covering, dict) and _text(covering.get("id")) == property_key


def _social_fact_reaction_lens(
    sim,
    npc_eid: int,
    player_view: Mapping[str, Any],
    bond: Mapping[str, Any] | None,
) -> str:
    """Choose a durable actor-specific lens without reading incident truth."""

    record = player_view.get("record") if isinstance(player_view.get("record"), Mapping) else {}
    occupation = sim.ecs.get(Occupation).get(npc_eid)
    workplace = getattr(occupation, "workplace", None)
    workplace_id = workplace.get("property_id") if isinstance(workplace, Mapping) else None
    if _location_matches_property(sim, record, workplace_id):
        return "workplace_stake"

    routine = sim.ecs.get(NPCRoutine).get(npc_eid)
    home = getattr(routine, "home", None)
    if (
        isinstance(home, (tuple, list))
        and len(home) >= 3
        and record.get("x") is not None
        and record.get("y") is not None
        and _int(home[2], 0) == _int(record.get("z"), 0)
        and abs(_int(home[0], 0) - _int(record.get("x"), 0))
        + abs(_int(home[1], 0) - _int(record.get("y"), 0))
        <= 8
    ):
        return "home_stake"

    ai = sim.ecs.get(AI).get(npc_eid)
    role = _token(getattr(ai, "role", ""))
    career = _token(getattr(occupation, "career", ""))
    if role in {"guard", "officer", "police", "deputy", "marshal", "scout"} or any(
        token in career for token in ("guard", "officer", "police", "investigator", "marshal", "deputy")
    ):
        return "duty_triage"

    traits = sim.ecs.get(NPCTraits).get(npc_eid)
    empathy = _unit(getattr(traits, "empathy", 0.5), 0.5)
    loyalty = _unit(getattr(traits, "loyalty", 0.5), 0.5)
    discipline = _unit(getattr(traits, "discipline", 0.5), 0.5)
    danger = max(
        _unit(record.get("urgency"), 0.0),
        _unit(record.get("social_interest"), 0.0) * 0.75,
        min(1.0, _int(record.get("severity"), 0) / 100.0),
    )
    if danger >= 0.58 and (empathy >= 0.72 or loyalty >= 0.78):
        return "protective_concern"
    trust = _bond_trust(bond)
    confidence = _unit(record.get("confidence"), 0.5)
    if not bool(record.get("firsthand", False)) and (
        discipline >= 0.74 or trust < 0.24 or confidence < 0.52
    ):
        return "source_skepticism"
    return "neutral"


def _reaction_copy(sim, reaction_shape: str, reaction_lens: str, warning_record: Mapping[str, Any]) -> tuple[str, str]:
    if reaction_shape == "warning_recognition":
        warning_source_name = _actor_name(sim, warning_record.get("heard_from_eid"), "Someone")
        return (
            "They recognize the account immediately, then study you instead.",
            f"{warning_source_name} already came to me about it and said you were the first one to raise it. "
            "What are you trying to add now?",
        )

    prefix = "I know the one. " if reaction_shape == "recognition" else ""
    if reaction_lens == "workplace_stake":
        return (
            "Their attention sharpens at the place you described.",
            f"{prefix}That's where I work. How certain are you about where it happened?",
        )
    if reaction_lens == "home_stake":
        return (
            "Their attention sharpens at the place you described.",
            f"{prefix}That's close to where I live. How certain are you about the place?",
        )
    if reaction_lens == "duty_triage":
        return (
            "They begin sorting your account into particulars.",
            f"{prefix}Did you see it yourself, and can you place where it happened?",
        )
    if reaction_lens == "protective_concern":
        return (
            "Concern reaches their face before they contain it.",
            f"{prefix}Is anyone still in danger, or is this already over?",
        )
    if reaction_lens == "source_skepticism":
        return (
            "They hold your account at arm's length.",
            f"{prefix}How much of that did you see yourself?",
        )
    if reaction_shape == "recognition":
        return "Recognition crosses their face before they answer.", "I know the one. What made you bring it to me?"
    if reaction_shape == "different_account":
        return (
            "They hesitate, as though fitting your account against another one.",
            "I've heard something about it, though not quite that way. Why bring it to me?",
        )
    return "Their attention settles fully on what you just said.", "That's new to me. Why are you telling me?"


def _remember_spoken_warning_reference(
    sim,
    viewer_eid: int,
    speaker_eid: int,
    warning: Mapping[str, Any],
    spoken_text: str,
    *,
    label: str,
) -> None:
    """Make a name used in actual speech unilateral player knowledge.

    This is deliberately not a presented identity or an introduction: the
    warned person has not met the player, and may not know the player's name.
    """

    if _token(warning.get("warning_status")) != "delivered":
        return
    subject_eid = _int(warning.get("warning_recipient_eid"), 0)
    subject_name = _text(warning.get("warning_recipient_name"))
    if subject_eid <= 0 or not subject_name or subject_name.lower() not in _text(spoken_text).lower():
        return
    ledger = ensure_contact_ledger(sim, viewer_eid)
    if ledger is None:
        return
    existing = ledger.person_entry(subject_eid)
    before = dict(existing) if isinstance(existing, dict) else None
    existing = existing or {}
    benefits = {
        _token(bit)
        for bit in tuple(existing.get("benefits", ()) or ())
        if _token(bit)
    }
    benefits.update({"known_name", "social_fact_warning_reference"})
    ledger.remember_person(
        subject_eid,
        source_eid=existing.get("source_eid") if existing.get("source_eid") is not None else speaker_eid,
        relation_kind=_text(existing.get("relation_kind")) or "named_warning_contact",
        standing=max(0.0, _unit(existing.get("standing"), 0.0)),
        tick=_int(getattr(sim, "tick", 0), 0),
        property_id=existing.get("property_id"),
        benefits=benefits,
        introduced=False,
        met_directly=None,
        identity_snapshot=actor_identity_snapshot(sim, subject_eid),
    )
    ledger.remember_person_episode(
        subject_eid,
        kind="social_fact_warning_reference",
        tick=_int(getattr(sim, "tick", 0), 0),
        valence="neutral",
        summary=(
            f"{_actor_name(sim, speaker_eid, 'Someone')} said they warned {subject_name} "
            f"about the {_text(label) or 'incident'}."
        ),
        other_person_eid=speaker_eid,
        source_topic="social_fact_warning",
    )
    note_person_notebook_mutation(
        sim,
        viewer_eid,
        subject_eid,
        before=before,
        after=ledger.person_entry(subject_eid),
    )


def is_social_fact_dialogue_topic(topic_id: Any) -> bool:
    return _token(topic_id).startswith(SOCIAL_FACT_TOPIC_PREFIX)


def _incident_rank(record: Mapping[str, Any]) -> tuple[float, int, int]:
    score = (
        _unit(record.get("social_interest"), 0.0) * 0.48
        + _unit(record.get("urgency"), 0.0) * 0.27
        + _unit(record.get("confidence"), 0.5) * 0.15
        + (0.1 if bool(record.get("firsthand")) else 0.0)
    )
    return (
        score,
        _int(record.get("last_learned_tick"), _int(record.get("learned_tick"), 0)),
        _int(record.get("incident_id"), 0),
    )


def _exchange_threads(sim, player_eid: int, npc_eid: int) -> tuple[dict[str, Any], ...]:
    rows = []
    for thread in social_threads_for_actor(sim, player_eid):
        metadata = thread.get("metadata") if isinstance(thread.get("metadata"), dict) else {}
        if metadata.get("exchange_kind") != _EXCHANGE_KIND:
            continue
        if _int(metadata.get("player_eid"), 0) != player_eid:
            continue
        if _int(metadata.get("npc_eid"), 0) != npc_eid:
            continue
        rows.append(thread)
    return tuple(rows)


def _witness_resolution_threads(sim, player_eid: int, npc_eid: int) -> tuple[dict[str, Any], ...]:
    rows = []
    for thread in social_threads_for_actor(sim, player_eid):
        metadata = thread.get("metadata") if isinstance(thread.get("metadata"), dict) else {}
        if metadata.get("exchange_kind") != _WITNESS_EXCHANGE_KIND:
            continue
        if _int(metadata.get("player_eid"), 0) != player_eid:
            continue
        if _int(metadata.get("npc_eid"), 0) != npc_eid:
            continue
        rows.append(thread)
    return tuple(rows)


def _witness_resolution_thread_for_incident(
    sim,
    player_eid: int,
    npc_eid: int,
    incident_id: Any,
) -> dict[str, Any] | None:
    incident = _int(incident_id, 0)
    for thread in _witness_resolution_threads(sim, player_eid, npc_eid):
        metadata = thread.get("metadata") if isinstance(thread.get("metadata"), dict) else {}
        if _int(metadata.get("incident_id"), 0) == incident:
            return thread
    return None


def specific_witness_matter_exists(sim, player_eid: Any, npc_eid: Any) -> bool:
    """Whether this pair has an incident-specific witness matter to discuss.

    This is intentionally based on the two actors' ledgers and the player's
    grounded witness awareness, not on the canonical incident registry.
    """

    player = _int(player_eid, 0)
    npc = _int(npc_eid, 0)
    knowledge = incident_knowledge_for(sim, player)
    if player <= 0 or npc <= 0 or knowledge is None:
        return False
    for record in (knowledge.records or {}).values():
        if not isinstance(record, dict):
            continue
        incident_id = _int(record.get("incident_id"), 0)
        if _witness_resolution_record(sim, player, npc, incident_id) is None:
            continue
        if _incident_age_ticks(sim, record) <= _TELLABLE_INCIDENT_MAX_AGE_DAYS * 24 * _ticks_per_hour(sim):
            return True
    return False


def _thread_has_correction(sim, thread: Mapping[str, Any]) -> bool:
    claim_id = _text(thread.get("origin_occurrence_id"))
    for occurrence_id in tuple(thread.get("occurrence_ids", ()) or ()):
        occurrence = occurrence_record(sim, occurrence_id)
        if not isinstance(occurrence, dict) or occurrence.get("kind") != "correction":
            continue
        if claim_id in set(occurrence.get("source_occurrence_ids", ()) or ()):
            return True
    return False


def _row(topic_id: str, action: str, label: str, player_line: str, **data: Any) -> dict[str, Any]:
    return {
        "id": topic_id,
        "label": label,
        "prompt_text": label,
        "player_line": player_line,
        "social_fact_action": action,
        **data,
    }


def social_fact_dialogue_rows(
    sim,
    player_eid: Any,
    npc_eid: Any,
    *,
    limit: int = 4,
) -> tuple[dict[str, Any], ...]:
    """Build actor-grounded exchange rows for one player/NPC pair."""

    player = _int(player_eid, 0)
    npc = _int(npc_eid, 0)
    if player <= 0 or npc <= 0 or player == npc:
        return ()
    rows = []
    threads = _exchange_threads(sim, player, npc)
    claimed_propositions = set()
    now = max(0, _int(getattr(sim, "tick", 0), 0))

    for thread in threads:
        metadata = thread.get("metadata") if isinstance(thread.get("metadata"), dict) else {}
        proposition_id = _text(metadata.get("proposition_id"))
        if proposition_id:
            claimed_propositions.add(proposition_id)
        thread_id = _text(thread.get("id"))
        label = _text(metadata.get("label")) or "incident"
        status = _token(thread.get("status"))
        corrected = _thread_has_correction(sim, thread)
        consequence = social_fact_action_for_thread(sim, thread_id, owner_eid=npc)
        consequence_status = _token((consequence or {}).get("status"))
        warning_status = _token((consequence or {}).get("warning_status"))
        correction_relay_status = _token((consequence or {}).get("correction_relay_status"))

        if status == "awaiting_response" and _int(thread.get("awaiting_actor_eid"), 0) == player:
            rows.append(_row(
                f"sfg_answer_{thread_id}",
                "answer_motive",
                f"Explain why you brought up the {label}.",
                "I thought it might matter to you.",
                social_fact_thread_id=thread_id,
            ))
            rows.append(_row(
                f"sfg_take_{thread_id}",
                "ask_take",
                f"Ask what they make of the {label}.",
                "What do you make of it?",
                social_fact_thread_id=thread_id,
            ))
            rows.append(_row(
                f"sfg_check_{thread_id}",
                "ask_corroboration",
                f"Ask whether they can check the {label} with someone they trust.",
                "Could you check with someone you trust and see whether they heard anything separately?",
                social_fact_thread_id=thread_id,
            ))
            if (
                _token(metadata.get("reaction_shape")) in {"recognition", "different_account", "warning_recognition"}
                or _token(metadata.get("reaction_lens")) not in {"", "neutral"}
            ):
                rows.append(_row(
                    f"sfg_reaction_{thread_id}",
                    "ask_reaction",
                    "Ask about the way they reacted.",
                    "You reacted like you already knew something about it.",
                    social_fact_thread_id=thread_id,
                ))
            rows.append(_row(
                f"sfg_withdraw_{thread_id}",
                "withdraw",
                "Leave that subject there.",
                "Never mind. I just wanted you to know.",
                social_fact_thread_id=thread_id,
            ))
        elif (
            isinstance(consequence, dict)
            and consequence_status not in {"completed", "failed"}
            and not bool(consequence.get("progress_reported", False))
            and _int(thread.get("last_tick"), 0) < now
        ):
            rows.append(_row(
                f"sfg_progress_{thread_id}",
                "ask_corroboration_progress",
                f"Ask whether they have found anyone to check the {label} with.",
                "Have you managed to ask anyone about it?",
                social_fact_thread_id=thread_id,
            ))
        elif (
            isinstance(consequence, dict)
            and consequence_status == "completed"
            and warning_status in {"requested", "seeking"}
            and not bool(consequence.get("warning_progress_reported", False))
            and _int(consequence.get("completed_tick"), 0) < now
        ):
            rows.append(_row(
                f"sfg_warning_progress_{thread_id}",
                "ask_warning_progress",
                f"Ask whether checking the {label} led anywhere.",
                "Did that check lead anywhere?",
                social_fact_thread_id=thread_id,
            ))
        elif (
            status == "considering"
            and not isinstance(consequence, dict)
            and _int(thread.get("last_tick"), 0) < now
        ):
            rows.append(_row(
                f"sfg_followup_{thread_id}",
                "follow_up",
                f"Ask whether they have thought about the {label}.",
                f"Have you given any more thought to that {label}?",
                social_fact_thread_id=thread_id,
            ))

        if (
            isinstance(consequence, dict)
            and consequence_status in {"completed", "failed"}
            and warning_status in {"delivered", "failed", "not_applicable"}
            and not bool(consequence.get("report_delivered", False))
            and _int(consequence.get("completed_tick"), now) < now
        ):
            already_heard_progress = bool(consequence.get("warning_progress_reported", False))
            rows.append(_row(
                f"sfg_consequence_{thread_id}",
                "ask_corroboration_result",
                f"Ask what happened after their check of the {label}.",
                "What happened after that?" if already_heard_progress else "Did you manage to check that with anyone?",
                social_fact_thread_id=thread_id,
            ))

        if (
            isinstance(consequence, dict)
            and bool(consequence.get("report_delivered", False))
            and correction_relay_status in {"delivered", "failed"}
            and not bool(consequence.get("correction_relay_report_delivered", False))
            and _int(consequence.get("correction_relay_completed_tick"), now) < now
        ):
            rows.append(_row(
                f"sfg_correction_relay_{thread_id}",
                "ask_correction_relay_result",
                "Ask whether they passed your correction on.",
                "Did you tell them I corrected myself?",
                social_fact_thread_id=thread_id,
            ))

        if status not in _FINISHED_THREAD_STATUSES and not corrected:
            rows.append(_row(
                f"sfg_correct_{thread_id}",
                "correct_claim",
                f"Correct what you said about the {label}.",
                f"I need to correct what I said about that {label}. I wasn't as certain as I sounded.",
                social_fact_thread_id=thread_id,
            ))

    knowledge = incident_knowledge_for(sim, player)
    witness_threads = _witness_resolution_threads(sim, player, npc)
    threaded_incidents = set()
    active_witness_resolution = False
    for thread in witness_threads:
        metadata = thread.get("metadata") if isinstance(thread.get("metadata"), dict) else {}
        incident_id = _int(metadata.get("incident_id"), 0)
        if incident_id <= 0:
            continue
        threaded_incidents.add(incident_id)
        label = _text(metadata.get("label")) or "incident"
        thread_id = _text(thread.get("id"))
        status = _token(thread.get("status"))
        resolution = incident_witness_resolution(sim, npc, incident_id)
        outcome = _token((resolution or {}).get("outcome"))
        resolution_status = _token((resolution or {}).get("status"))

        if status == "awaiting_response" and not isinstance(resolution, dict):
            active_witness_resolution = True
            amount = _witness_bribe_opening_amount(
                sim,
                player,
                npc,
                _witness_resolution_record(sim, player, npc, incident_id) or {},
            )
            rows.extend((
                _row(
                    f"sfg_witness_threat_{thread_id}",
                    "threaten_witness",
                    f"Threaten them into silence about the {label}. [threat]",
                    f"You saw what happened. Keep the {label} to yourself.",
                    social_fact_thread_id=thread_id,
                    social_fact_incident_id=incident_id,
                ),
                _row(
                    f"sfg_witness_bribe_{thread_id}",
                    "offer_witness_bribe",
                    f"Offer {amount} credits for their discretion. [bribe]",
                    f"I can give you {amount} credits if you stop carrying this any farther.",
                    social_fact_thread_id=thread_id,
                    social_fact_incident_id=incident_id,
                    witness_bribe_amount=amount,
                ),
                _row(
                    f"sfg_witness_confess_{thread_id}",
                    "confess_to_witness",
                    f"Admit what you did and ask what making it right would take. [honest]",
                    "I did it. I'm not asking you to pretend otherwise. Tell me what making this right takes.",
                    social_fact_thread_id=thread_id,
                    social_fact_incident_id=incident_id,
                ),
                _row(
                    f"sfg_witness_leave_{thread_id}",
                    "leave_witness_resolution",
                    "Leave the matter there.",
                    "Never mind.",
                    social_fact_thread_id=thread_id,
                    social_fact_incident_id=incident_id,
                ),
            ))
        elif outcome == "countered" and resolution_status == "awaiting_player":
            active_witness_resolution = True
            counter = max(1, _int((resolution or {}).get("counter_amount"), 0))
            rows.extend((
                _row(
                    f"sfg_witness_counter_accept_{thread_id}",
                    "accept_witness_bribe_counter",
                    f"Pay their counteroffer of {counter} credits.",
                    f"All right. {counter} credits, and you stop helping this go any farther.",
                    social_fact_thread_id=thread_id,
                    social_fact_incident_id=incident_id,
                    witness_bribe_amount=counter,
                ),
                _row(
                    f"sfg_witness_counter_decline_{thread_id}",
                    "decline_witness_bribe_counter",
                    "Refuse their counteroffer.",
                    "No. Keep your price.",
                    social_fact_thread_id=thread_id,
                    social_fact_incident_id=incident_id,
                ),
            ))
        elif (
            outcome == "forbearance"
            and resolution_status == "active"
            and _int((resolution or {}).get("deadline_tick"), now) >= now
        ):
            active_witness_resolution = True
            deadline = _int((resolution or {}).get("deadline_tick"), now)
            hours_left = max(1, (max(0, deadline - now) + _ticks_per_hour(sim) - 1) // _ticks_per_hour(sim))
            rows.append(_row(
                f"sfg_witness_accountability_{thread_id}",
                "fulfill_witness_accountability",
                f"Ask them to come with you while you formally own the {label} ({hours_left}h left).",
                "I'm ready. Come with me and tell them what I admitted to you.",
                social_fact_thread_id=thread_id,
                social_fact_incident_id=incident_id,
            ))

    witness_candidates = []
    if knowledge is not None and not active_witness_resolution:
        witness_candidates = [
            record
            for record in (knowledge.records or {}).values()
            if (
                isinstance(record, dict)
                and _token(record.get("source_kind")) == "self"
                and _witness_resolution_record(sim, player, npc, record.get("incident_id")) is not None
                and incident_witness_resolution(sim, npc, record.get("incident_id")) is None
                and _int(record.get("incident_id"), 0) not in threaded_incidents
                and _incident_age_ticks(sim, record)
                <= _TELLABLE_INCIDENT_MAX_AGE_DAYS * 24 * _ticks_per_hour(sim)
            )
        ]
        witness_candidates.sort(key=_incident_rank, reverse=True)
    for record in witness_candidates[: max(0, int(limit))]:
        adapted = ensure_actor_incident_perspective(sim, player, record.get("incident_id"))
        if not isinstance(adapted, dict):
            continue
        incident_id = adapted["incident_id"]
        label = adapted["label"]
        awareness = player_known_firsthand_witness(sim, player, npc, incident_id) or {}
        rows.append(_row(
            f"sfg_witness_open_{player}_{npc}_{incident_id}",
            "open_witness_resolution",
            f"Talk to them about what they saw of the {label} ({_incident_choice_detail(sim, player, adapted)}).",
            f"I know you saw the {label}. We need to talk about what happens next.",
            social_fact_incident_id=incident_id,
            social_fact_proposition_id=adapted["proposition"]["id"],
            social_fact_witness_awareness_occurrence_id=_text(awareness.get("occurrence_id")),
        ))

    candidates = []
    if knowledge is not None:
        candidates = [
            record
            for record in (knowledge.records or {}).values()
            if (
                isinstance(record, dict)
                and not bool(record.get("dismissed", False))
                and not _incident_implicates_player(record, player)
                and _incident_age_ticks(sim, record)
                <= _TELLABLE_INCIDENT_MAX_AGE_DAYS * 24 * _ticks_per_hour(sim)
            )
        ]
        candidates.sort(key=_incident_rank, reverse=True)
    added = 0
    for record in candidates:
        adapted = ensure_actor_incident_perspective(sim, player, record.get("incident_id"))
        if not isinstance(adapted, dict):
            continue
        proposition_id = adapted["proposition"]["id"]
        if proposition_id in claimed_propositions:
            continue
        incident_id = adapted["incident_id"]
        label = adapted["label"]
        if bool(adapted["snapshot"].get("firsthand")):
            player_line = f"I saw enough of that {label} to think you should know about it."
        elif adapted["snapshot"].get("source_eid"):
            player_line = f"Someone told me about a {label}. I thought you should hear it."
        else:
            player_line = f"I heard about a {label}. I thought you should know."
        rows.append(_row(
            f"sfg_tell_{proposition_id}",
            "tell_incident",
            f"Tell them about the {label} ({_incident_choice_detail(sim, player, adapted)}).",
            player_line,
            social_fact_incident_id=incident_id,
            social_fact_proposition_id=proposition_id,
        ))
        added += 1
        if added >= max(0, int(limit)):
            break
    return tuple(rows)


def _bond_trust(bond: Mapping[str, Any] | None) -> float:
    return _unit((bond or {}).get("trust"), 0.0)


def _thread_for_action(sim, row: Mapping[str, Any], player: int, npc: int) -> dict[str, Any]:
    thread_id = _text(row.get("social_fact_thread_id"))
    thread = social_thread(sim, thread_id)
    if not isinstance(thread, dict):
        raise KeyError(f"unknown social fact dialogue thread: {thread_id}")
    participants = set(thread.get("participants", ()) or ())
    if not {player, npc}.issubset(participants):
        raise ValueError("social fact dialogue thread does not belong to this conversation")
    return thread


def _thread_occurrence(
    sim,
    thread: Mapping[str, Any],
    kind: str,
    *,
    player: int,
    npc: int,
    action: str,
    player_spoken_text: str,
    npc_spoken_text: str,
) -> dict[str, Any]:
    return record_occurrence(
        sim,
        kind,
        actor_eids=(player, npc),
        proposition_ids=tuple(thread.get("proposition_ids", ()) or ()),
        source_occurrence_ids=tuple(
            value
            for value in (thread.get("origin_occurrence_id"),)
            if _text(value)
        ),
        payload={
            "action": action,
            "thread_id": thread.get("id"),
            "player_spoken_text": _text(player_spoken_text),
            "npc_spoken_text": _text(npc_spoken_text),
        },
        flags=("speech", "attributed"),
        dedupe_key=f"social-fact-dialogue:{thread.get('id')}:{action}",
    )


def _is_duty_bound_witness(sim, npc_eid: int) -> bool:
    role = _token(getattr(sim.ecs.get(AI).get(npc_eid), "role", ""))
    occupation = sim.ecs.get(Occupation).get(npc_eid)
    career = _token(getattr(occupation, "career", ""))
    return role in _DUTY_ROLES or any(token in career for token in _DUTY_ROLES)


def _round_credits(value: Any) -> int:
    return max(5, int(round(max(1.0, float(value or 0.0)) / 5.0)) * 5)


def _witness_bribe_opening_amount(
    sim,
    player_eid: int,
    npc_eid: int,
    player_record: Mapping[str, Any],
) -> int:
    """Build the player's single opening offer from information they can own."""

    severity = max(0, min(100, _int(player_record.get("severity"), 0)))
    prior = incident_prior_spread_state(sim, npc_eid, player_record.get("incident_id"))
    exposure_cost = 10 if prior.get("authority_reported") else 5 if prior.get("authority_started") else 0
    # The opening is the player's proposal, so it uses their own incident
    # severity and perceptible prior-spread state. Hidden NPC finances shape
    # only the counter the NPC actually speaks.
    return _round_credits(10 + (severity * 0.65) + exposure_cost)


def _witness_bribe_terms(
    sim,
    npc_eid: int,
    witness_record: Mapping[str, Any],
    opening_amount: int,
    prior: Mapping[str, Any],
) -> tuple[bool, int, str]:
    """Return willingness, one reservation-price counter, and reaction lens."""

    justice = sim.ecs.get(JusticeProfile).get(npc_eid) or JusticeProfile()
    traits = sim.ecs.get(NPCTraits).get(npc_eid) or NPCTraits()
    finances = sim.ecs.get(FinancialProfile).get(npc_eid)
    severity = max(0, min(100, _int(witness_record.get("severity"), 0)))
    corruption = _unit(getattr(justice, "corruption", 0.0), 0.0)
    justice_value = _unit(getattr(justice, "justice", 0.5), 0.5)
    discipline = _unit(getattr(traits, "discipline", 0.5), 0.5)
    debt = max(0, _int(getattr(finances, "debt_balance", 0), 0))
    debt_pressure = min(1.0, debt / 240.0)
    victim = _token(witness_record.get("source_kind")) == "victim"
    duty = _is_duty_bound_witness(sim, npc_eid)

    willingness = (corruption * 0.72) + (debt_pressure * 0.22)
    willingness -= justice_value * 0.30
    willingness -= discipline * 0.22
    willingness -= (severity / 100.0) * 0.18
    willingness -= 0.36 if victim else 0.0
    willingness -= 0.30 if duty else 0.0
    willing = not bool(getattr(justice, "enforce_all", False)) and willingness >= -0.02

    if victim:
        lens = "harmed_target"
    elif duty:
        lens = "duty_bound"
    elif debt_pressure >= 0.55:
        lens = "financial_pressure"
    elif corruption >= 0.65:
        lens = "transactional"
    else:
        lens = "guarded"

    wage = npc_hourly_wage(sim, npc_eid)
    base = (wage * 3.0) + 8 + (severity * 0.95)
    base *= 1.0 + (justice_value * 0.30) + (discipline * 0.18) - (corruption * 0.30)
    if prior.get("authority_reported"):
        base += 12 + (severity * 0.30)
    elif prior.get("authority_started"):
        base += 8
    counter = max(_round_credits(base), _round_credits(opening_amount + 5))
    return willing, counter, lens


def _transfer_witness_bribe(sim, player_eid: int, npc_eid: int, amount: Any) -> bool:
    credits = max(0, _int(amount, 0))
    assets = sim.ecs.get(PlayerAssets).get(player_eid)
    if credits <= 0 or not isinstance(assets, PlayerAssets) or assets.credits < credits:
        return False
    finances = sim.ecs.get(FinancialProfile).get(npc_eid)
    if not isinstance(finances, FinancialProfile):
        finances = FinancialProfile()
        sim.ecs.add(npc_eid, finances)
    assets.credits -= credits
    finances.bank_balance += credits
    sim.emit(Event(
        "witness_bribe_paid",
        player_eid=player_eid,
        npc_eid=npc_eid,
        amount=credits,
    ))
    return True


def _stamp_direct_confession(sim, player_eid: int, npc_eid: int, incident_id: int) -> dict[str, Any] | None:
    """Add only what the witness learned from the player's direct admission."""

    knowledge = sim.ecs.get(IncidentKnowledge).get(npc_eid)
    record = (knowledge.records or {}).get(incident_id) if isinstance(knowledge, IncidentKnowledge) else None
    if not isinstance(record, dict):
        return None
    existing = record.get("subject_account") if isinstance(record.get("subject_account"), dict) else {}
    observed = build_witness_subject_account(
        sim,
        npc_eid,
        player_eid,
        source_kind="self_confession",
        confidence=1.0,
    )
    account = dict(existing)
    existing_identification = _token(existing.get("identification"))
    # The witness need not know a legal name, but in this face-to-face exchange
    # the present speaker directly attributes the act to themself. That grounds
    # the actor identity strongly enough for a formal statement without
    # pretending the earlier scene view was clearer than it was.
    identification = "verified" if existing_identification == "verified" else "recognized"
    account.update({
        "identification": identification,
        "suspect_eid": player_eid,
        "presented_name": (
            _text(existing.get("presented_name"))
            or _text(observed.get("presented_name"))
        ),
        "identity_confidence": 1.0,
        "description": dict(observed.get("description") or existing.get("description") or {}),
        "observation": {
            **dict(observed.get("observation") or {}),
            "source": "self_confession",
            "quality": 1.0,
            "tick": _int(getattr(sim, "tick", 0), 0),
        },
    })
    record["subject_account"] = account
    record["direct_confession_tick"] = _int(getattr(sim, "tick", 0), 0)
    record["direct_confession_by_eid"] = player_eid
    return account


def _confession_outcome(
    sim,
    npc_eid: int,
    witness_record: Mapping[str, Any],
    bond: Mapping[str, Any] | None,
    prior: Mapping[str, Any],
) -> tuple[str, str]:
    severity = max(0, min(100, _int(witness_record.get("severity"), 0)))
    victim = _token(witness_record.get("source_kind")) == "victim"
    duty = _is_duty_bound_witness(sim, npc_eid)
    justice = sim.ecs.get(JusticeProfile).get(npc_eid) or JusticeProfile()
    traits = sim.ecs.get(NPCTraits).get(npc_eid) or NPCTraits()
    empathy = _unit(getattr(traits, "empathy", 0.5), 0.5)
    trust = _unit((bond or {}).get("trust"), 0.0)
    grace = (empathy * 0.45) + (trust * 0.30) + (_unit(getattr(justice, "justice", 0.5), 0.5) * 0.12)
    eligible = (
        severity <= 34
        and not victim
        and not duty
        and not prior.get("authority_reported")
        and not prior.get("authority_started")
        and grace >= 0.34
    )
    if eligible:
        return "forbearance", "accountability_grace"
    if victim:
        return "accountability_required", "harmed_target"
    if duty:
        return "accountability_required", "duty_bound"
    if severity > 34:
        return "accountability_required", "severity_boundary"
    return "accountability_required", "no_grace"


def _shift_witness_transaction_relationship(
    sim,
    player_eid: int,
    npc_eid: int,
    occurrence_id: str,
    *,
    approach: str,
    outcome: str,
) -> None:
    social = sim.ecs.get(NPCSocial).get(npc_eid)
    bond = social.bonds.get(player_eid) if isinstance(social, NPCSocial) else None
    bond = bond if isinstance(bond, dict) else {}
    contexts = ("incident_witness", approach)
    ensure_social_edge(
        sim,
        npc_eid,
        player_eid,
        relation_kind=_token(bond.get("kind")),
        contexts=contexts,
        dimensions={
            "trust": _unit(bond.get("trust"), 0.0),
            "closeness": _unit(bond.get("closeness"), 0.0),
        },
    )
    if approach == "bribe":
        if outcome == "countered":
            effects = (("trust", -0.08), ("resentment", 0.05))
        elif outcome == "accepted_counter":
            effects = (("resentment", 0.02), ("dependence", 0.12))
        elif outcome == "declined_counter":
            effects = ()
        elif outcome == "accepted":
            effects = (("trust", -0.12), ("resentment", 0.08), ("dependence", 0.12))
        else:
            effects = (("trust", -0.20), ("resentment", 0.18))
    else:
        # Confession is not a trust vending machine. Grace creates a debt held
        # by the player; owning the act later merely discharges it.
        effects = (("resentment", 0.04 if outcome == "forbearance" else 0.10),)
    for dimension, delta in effects:
        if not delta:
            continue
        apply_social_effect(
            sim,
            npc_eid,
            player_eid,
            occurrence_id,
            dimension,
            delta,
            effect_kind=f"witness_{approach}_{outcome}",
            effect_key=f"{occurrence_id}:witness-{approach}:{dimension}",
            contexts=contexts,
        )
    if isinstance(bond, dict) and bond:
        if approach == "bribe":
            trust_cost = {
                "accepted": 0.12,
                "countered": 0.08,
                "refused": 0.20,
                "declined": 0.20,
            }.get(outcome, 0.0)
            bond["trust"] = max(0.0, _unit(bond.get("trust"), 0.0) - trust_cost)
        elif approach == "confession" and outcome != "forbearance":
            bond["trust"] = max(0.0, _unit(bond.get("trust"), 0.0) - 0.08)


def _apply_player_obligation(
    sim,
    player_eid: int,
    npc_eid: int,
    occurrence_id: str,
    delta: float,
    *,
    effect_kind: str,
) -> None:
    ensure_social_edge(sim, player_eid, npc_eid, contexts=("incident_witness", "accountability"))
    apply_social_effect(
        sim,
        player_eid,
        npc_eid,
        occurrence_id,
        "obligation",
        delta,
        effect_kind=effect_kind,
        effect_key=f"{occurrence_id}:{effect_kind}:obligation",
        contexts=("incident_witness", "accountability"),
    )


def _witness_threat_outcome(
    sim,
    player_eid: int,
    npc_eid: int,
    witness_record: Mapping[str, Any],
    bond: Mapping[str, Any] | None,
) -> tuple[str, float, float]:
    traits = sim.ecs.get(NPCTraits).get(npc_eid) or NPCTraits()
    needs = sim.ecs.get(NPCNeeds).get(npc_eid) or NPCNeeds()
    justice = sim.ecs.get(JusticeProfile).get(npc_eid) or JusticeProfile()
    role = _token(getattr(sim.ecs.get(AI).get(npc_eid), "role", ""))
    conversation = actor_skill(sim, player_eid, "conversation", default=5.0)
    streetwise = actor_skill(sim, player_eid, "streetwise", default=5.0)
    safety = max(0.0, min(100.0, float(getattr(needs, "safety", 70.0) or 70.0)))
    trust = _unit((bond or {}).get("trust"), 0.0)

    pressure = 0.24
    pressure += (float(streetwise) / 10.0) * 0.26
    pressure += (float(conversation) / 10.0) * 0.10
    pressure += ((100.0 - safety) / 100.0) * 0.12
    pressure += trust * 0.08

    resistance = _unit(getattr(traits, "bravery", 0.5), 0.5) * 0.28
    resistance += _unit(getattr(traits, "discipline", 0.5), 0.5) * 0.22
    resistance += _unit(getattr(justice, "justice", 0.5), 0.5) * 0.14
    resistance -= _unit(getattr(justice, "corruption", 0.0), 0.0) * 0.10
    if _token(witness_record.get("source_kind")) == "victim":
        resistance += 0.18
    if role in {"guard", "detective", "inspector", "investigator", "officer", "police", "deputy", "marshal", "security"}:
        resistance += 0.20
    outcome = "complied" if pressure - resistance >= 0.08 else "refused"
    return outcome, max(0.0, min(1.0, pressure)), max(0.0, min(1.0, resistance))


def _witness_threat_response(
    sim,
    npc_eid: int,
    witness_record: Mapping[str, Any],
    bond: Mapping[str, Any] | None,
    outcome: str,
    prior: Mapping[str, Any],
) -> tuple[str, str]:
    role = _token(getattr(sim.ecs.get(AI).get(npc_eid), "role", ""))
    traits = sim.ecs.get(NPCTraits).get(npc_eid) or NPCTraits()
    needs = sim.ecs.get(NPCNeeds).get(npc_eid) or NPCNeeds()
    trust = _unit((bond or {}).get("trust"), 0.0)
    closeness = _unit((bond or {}).get("closeness"), 0.0)
    if _token(witness_record.get("source_kind")) == "victim":
        lens = "harmed_target"
    elif role in {"guard", "detective", "inspector", "investigator", "officer", "police", "deputy", "marshal", "security"}:
        lens = "duty_bound"
    elif trust >= 0.62 or closeness >= 0.68:
        lens = "betrayed_contact"
    elif float(getattr(needs, "safety", 70.0) or 70.0) < 35.0:
        lens = "afraid"
    elif _unit(getattr(traits, "bravery", 0.5), 0.5) >= 0.72:
        lens = "defiant"
    else:
        lens = "guarded"

    if _token(outcome) == "complied":
        if prior.get("authority_reported"):
            return lens, (
                "You're too late. I already reported what I saw. I won't go around repeating it, "
                "but that report is out of my hands. Stay away from me."
            )
        if int(prior.get("social_shared_count", 0) or 0) > 0:
            return lens, (
                "I already told someone. I won't carry it any farther, but I can't take that "
                "conversation back. Stay away from me."
            )
        if prior.get("authority_started"):
            return lens, "I was already on my way to report it. Fine. I won't finish that—but stay away from me."
        if lens == "harmed_target":
            return lens, "You did it to me, and now you're threatening me over it. Fine. I won't tell anyone—but don't come near me again."
        if lens == "betrayed_contact":
            return lens, "After everything between us, this is what you came to me with? Fine. I won't carry it farther—but we're done."
        if lens == "duty_bound":
            return lens, "I know what I'm supposed to do. Fine. I won't report it—but stay away from me."
        return lens, "I saw what I saw. Fine. I won't carry it any farther—but stay away from me."

    if prior.get("authority_reported"):
        return lens, "Too late. I already reported what I saw, and now I'll report this threat too."
    if int(prior.get("social_shared_count", 0) or 0) > 0:
        return lens, "Too late. I already told someone, and now I'll tell them you threatened me."
    if lens == "harmed_target":
        return lens, "You did it to me. You don't get to decide what I say about it. Now I'm reporting the threat too."
    if lens == "duty_bound":
        return lens, "No. Reporting what I saw is my job. Now I have this threat to report too."
    if lens == "betrayed_contact":
        return lens, "You thought knowing me made this easier? No. Now I have the crime and this threat to tell them about."
    if lens == "defiant":
        return lens, "No. You don't decide what I do with what I saw. Threatening me only gave me more to report."
    return lens, "No. You don't get to decide what I do with what I saw. Now I have two things to report."


def _shift_witness_relationship(
    sim,
    player_eid: int,
    npc_eid: int,
    threat_occurrence_id: str,
    outcome: str,
) -> None:
    social = sim.ecs.get(NPCSocial).get(npc_eid)
    bond = social.bonds.get(player_eid) if isinstance(social, NPCSocial) else None
    bond = bond if isinstance(bond, dict) else {}
    ensure_social_edge(
        sim,
        npc_eid,
        player_eid,
        relation_kind=_token(bond.get("kind")),
        contexts=("incident_witness", "coercion"),
        dimensions={
            "trust": _unit(bond.get("trust"), 0.0),
            "closeness": _unit(bond.get("closeness"), 0.0),
            "protectiveness": _unit(bond.get("protectiveness"), 0.0),
        },
    )
    complied = _token(outcome) == "complied"
    for dimension, delta in (
        ("fear", 0.38 if complied else 0.18),
        ("resentment", 0.30 if complied else 0.42),
        ("trust", -0.20 if complied else -0.28),
    ):
        apply_social_effect(
            sim,
            npc_eid,
            player_eid,
            threat_occurrence_id,
            dimension,
            delta,
            effect_kind="witness_silencing_threat",
            effect_key=f"{threat_occurrence_id}:witness-silencing:{dimension}",
            contexts=("incident_witness", "coercion"),
        )
    if isinstance(bond, dict) and bond:
        bond["trust"] = max(0.0, _unit(bond.get("trust"), 0.0) - (0.20 if complied else 0.28))
        bond["closeness"] = max(0.0, _unit(bond.get("closeness"), 0.0) - (0.08 if complied else 0.14))
        bond["protectiveness"] = max(0.0, _unit(bond.get("protectiveness"), 0.0) - 0.18)


def _witness_intimidation_observation(sim, player_eid: int, npc_eid: int) -> dict[str, Any]:
    positions = sim.ecs.get(Position)
    player_pos = positions.get(player_eid)
    observers = {npc_eid}
    if player_pos is not None:
        local = observation_payload_for_position(
            sim,
            player_pos.x,
            player_pos.y,
            player_pos.z,
            exclude_eid=player_eid,
            offender_eid=player_eid,
            observation_channels=("actor_witness",),
        )
        observers.update(_int(eid, 0) for eid in tuple(local.get("accountable_observer_eids", ()) or ()))
    return observation_payload_from_observers(
        sim,
        tuple(sorted(eid for eid in observers if eid > 0)),
        offender_eid=player_eid,
        observation_channels=("actor_witness",),
    )


def _emit_witness_intimidation_offense(
    sim,
    player_eid: int,
    npc_eid: int,
    original_incident_id: int,
) -> int:
    positions = sim.ecs.get(Position)
    player_pos = positions.get(player_eid)
    npc_pos = positions.get(npc_eid)
    anchor = player_pos or npc_pos
    if anchor is None:
        return 0
    offense_score = 58
    observation = _witness_intimidation_observation(sim, player_eid, npc_eid)
    event = Event(
        "action_offense",
        eid=player_eid,
        offender_eid=player_eid,
        victim_eid=npc_eid,
        target_eid=npc_eid,
        action="threaten_witness",
        context="witness_intimidation",
        offense_score=offense_score,
        offense_tier=_offense_tier(offense_score),
        radius=_offense_notice_radius(offense_score),
        x=int(anchor.x),
        y=int(anchor.y),
        z=int(anchor.z),
        related_incident_id=original_incident_id,
        **observation,
    )
    sim.emit(event)
    return _int(event.data.get("knowledge_incident_id"), 0)


def _emit_witness_bribery_offense(
    sim,
    player_eid: int,
    npc_eid: int,
    original_incident_id: int,
) -> int:
    positions = sim.ecs.get(Position)
    player_pos = positions.get(player_eid)
    npc_pos = positions.get(npc_eid)
    anchor = player_pos or npc_pos
    if anchor is None:
        return 0
    offense_score = 44
    observation = _witness_intimidation_observation(sim, player_eid, npc_eid)
    event = Event(
        "action_offense",
        eid=player_eid,
        offender_eid=player_eid,
        victim_eid=npc_eid,
        target_eid=npc_eid,
        action="bribe_witness",
        context="witness_bribery",
        offense_score=offense_score,
        offense_tier=_offense_tier(offense_score),
        radius=_offense_notice_radius(offense_score),
        x=int(anchor.x),
        y=int(anchor.y),
        z=int(anchor.z),
        related_incident_id=original_incident_id,
        **observation,
    )
    sim.emit(event)
    return _int(event.data.get("knowledge_incident_id"), 0)


def _witness_thread_for_action(
    sim,
    row: Mapping[str, Any],
    player_eid: int,
    npc_eid: int,
) -> dict[str, Any]:
    thread = _thread_for_action(sim, row, player_eid, npc_eid)
    metadata = thread.get("metadata") if isinstance(thread.get("metadata"), dict) else {}
    if metadata.get("exchange_kind") != _WITNESS_EXCHANGE_KIND:
        raise ValueError("witness resolution action does not belong to a witness thread")
    if _int(metadata.get("incident_id"), 0) != _int(row.get("social_fact_incident_id"), 0):
        raise ValueError("witness resolution row no longer matches its incident")
    return thread


def resolve_social_fact_dialogue(
    sim,
    player_eid: Any,
    npc_eid: Any,
    row: Mapping[str, Any],
    *,
    bond: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve one dynamic exchange row from actor-scoped state only."""

    player = _int(player_eid, 0)
    npc = _int(npc_eid, 0)
    action = _token(row.get("social_fact_action"))
    if player <= 0 or npc <= 0 or player == npc or not action:
        return {"npc_lines": ["I lost the thread of what you meant."]}

    if action == "open_witness_resolution":
        incident_id = _int(row.get("social_fact_incident_id"), 0)
        player_record = _witness_resolution_record(sim, player, npc, incident_id)
        awareness = player_known_firsthand_witness(sim, player, npc, incident_id)
        existing_thread = _witness_resolution_thread_for_incident(sim, player, npc, incident_id)
        if not isinstance(player_record, dict) or not isinstance(awareness, dict):
            return {"npc_lines": ("I don't know what you think I saw.",)}
        if isinstance(existing_thread, dict) or incident_witness_resolution(sim, npc, incident_id) is not None:
            return {"npc_lines": ("We've already had this conversation.",)}
        player_view = ensure_actor_incident_perspective(sim, player, incident_id)
        npc_view = ensure_actor_incident_perspective(sim, npc, incident_id)
        if not isinstance(player_view, dict) or not isinstance(npc_view, dict):
            return {"npc_lines": ("I don't know what you think I saw.",)}
        proposition_id = player_view["proposition"]["id"]
        awareness_occurrence_id = _text(awareness.get("occurrence_id"))
        if proposition_id != _text(row.get("social_fact_proposition_id")):
            raise ValueError("witness conversation row no longer matches the player's account")
        if awareness_occurrence_id != _text(row.get("social_fact_witness_awareness_occurrence_id")):
            raise ValueError("witness conversation row no longer matches the player's awareness")
        opening = record_occurrence(
            sim,
            "witness_matter_opened",
            actor_eids=(player, npc),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=(awareness_occurrence_id,),
            payload={
                "incident_id": incident_id,
                "speaker_eid": player,
                "audience_eid": npc,
                "spoken_text": _text(row.get("player_line")),
            },
            flags=("speech", "attributed", "accountability"),
            dedupe_key=f"witness-matter-opened:{player}:{npc}:{incident_id}",
        )
        prior = incident_prior_spread_state(sim, npc, incident_id)
        if prior.get("authority_reported"):
            line = "I already told the authorities what I saw. What are you asking me for now?"
        elif int(prior.get("social_shared_count", 0) or 0) > 0:
            line = "I've already spoken to someone about it. What are you asking me for now?"
        elif prior.get("authority_started"):
            line = "I was going to report it. Say what you came to say."
        else:
            line = "I saw it. What about it?"
        reaction = record_occurrence(
            sim,
            "reaction",
            actor_eids=(npc, player),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=(opening["id"],),
            payload={"shape": "witness_matter_acknowledged", "npc_spoken_text": line},
            flags=("speech", "attributed", "perceptible"),
            dedupe_key=f"witness-matter-opening-reaction:{player}:{npc}:{incident_id}",
        )
        thread = open_social_thread(
            sim,
            participants=(player, npc),
            proposition_ids=(proposition_id,),
            origin_occurrence_id=opening["id"],
            kind="accountability",
            status="awaiting_response",
            awaiting_actor_eid=player,
            tags=("witness_resolution", "incident_witness"),
            metadata={
                "exchange_kind": _WITNESS_EXCHANGE_KIND,
                "player_eid": player,
                "npc_eid": npc,
                "incident_id": incident_id,
                "proposition_id": proposition_id,
                "awareness_occurrence_id": awareness_occurrence_id,
                "label": player_view["label"],
                "choice_detail": _incident_choice_detail(sim, player, player_view),
            },
            thread_key=f"witness-resolution:{player}:{npc}:{incident_id}",
        )
        advance_social_thread(
            sim,
            thread["id"],
            occurrence_id=reaction["id"],
            status="awaiting_response",
            awaiting_actor_eid=player,
        )
        return {"npc_lines": (line,), "social_fact_thread_id": thread["id"]}

    if action == "threaten_witness":
        incident_id = _int(row.get("social_fact_incident_id"), 0)
        thread = _witness_thread_for_action(sim, row, player, npc)
        metadata = thread.get("metadata") if isinstance(thread.get("metadata"), dict) else {}
        player_record = _witness_threat_record(sim, player, npc, incident_id)
        awareness = player_known_firsthand_witness(sim, player, npc, incident_id)
        if not isinstance(player_record, dict) or not isinstance(awareness, dict):
            return {"npc_lines": ("I don't know what you think I saw.",)}
        if incident_witness_resolution(sim, npc, incident_id) is not None:
            return {"npc_lines": ("You already made that threat. Repeating it doesn't change my answer.",), "close": True}
        player_view = ensure_actor_incident_perspective(sim, player, incident_id)
        npc_view = ensure_actor_incident_perspective(sim, npc, incident_id)
        if not isinstance(player_view, dict) or not isinstance(npc_view, dict):
            return {"npc_lines": ("I don't know what you think I saw.",)}
        proposition_id = player_view["proposition"]["id"]
        if proposition_id != _text(metadata.get("proposition_id")):
            raise ValueError("witness threat row no longer matches the player's own account")
        awareness_occurrence_id = _text(awareness.get("occurrence_id"))
        if awareness_occurrence_id != _text(metadata.get("awareness_occurrence_id")):
            raise ValueError("witness threat row no longer matches the player's awareness")

        witness_record = npc_view["record"]
        outcome, pressure, resistance = _witness_threat_outcome(
            sim,
            player,
            npc,
            witness_record,
            bond,
        )
        prior = incident_prior_spread_state(sim, npc, incident_id)
        threat = record_occurrence(
            sim,
            "witness_silencing_threat",
            actor_eids=(player, npc),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=(awareness_occurrence_id,),
            payload={
                "incident_id": incident_id,
                "speaker_eid": player,
                "audience_eid": npc,
                "spoken_text": _text(row.get("player_line")),
            },
            flags=("speech", "attributed", "coercion"),
            dedupe_key=f"witness-silencing-threat:{player}:{npc}:{incident_id}",
        )
        reaction_lens, line = _witness_threat_response(
            sim,
            npc,
            witness_record,
            bond,
            outcome,
            prior,
        )

        reaction = record_occurrence(
            sim,
            "reaction",
            actor_eids=(npc, player),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=(threat["id"],),
            payload={
                "shape": "coerced_compliance" if outcome == "complied" else "defiant_refusal",
                "lens": reaction_lens,
                "outcome": outcome,
                "npc_spoken_text": line,
            },
            flags=("speech", "attributed", "perceptible"),
            dedupe_key=f"witness-silencing-reaction:{player}:{npc}:{incident_id}",
        )
        advance_social_thread(
            sim,
            thread["id"],
            occurrence_id=reaction["id"],
            status="acted",
            awaiting_actor_eid=None,
        )
        _shift_witness_relationship(sim, player, npc, threat["id"], outcome)
        applied = apply_incident_silence_pressure(
            sim,
            npc,
            incident_id,
            threatener_eid=player,
            outcome=outcome,
            occurrence_id=threat["id"],
        )
        if not isinstance(applied, dict):
            return {"npc_lines": ("I don't know what you think I saw.",)}

        threat_incident_id = _emit_witness_intimidation_offense(sim, player, npc, incident_id)
        if outcome == "complied" and threat_incident_id > 0:
            apply_incident_silence_pressure(
                sim,
                npc,
                threat_incident_id,
                threatener_eid=player,
                outcome="complied",
                occurrence_id=threat["id"],
            )
        sim.emit(Event(
            "npc_offended",
            npc_eid=npc,
            offender_eid=player,
            action="talk",
            context="dialogue_witness_intimidation",
            offense_score=58,
            offense_tier=_offense_tier(58),
            perceived=1.0,
            violence_eligible=True,
            suppress_bark=True,
            incident_id=threat_incident_id or incident_id,
        ))
        sim.emit(Event(
            "incident_witness_resolution",
            npc_eid=npc,
            player_eid=player,
            incident_id=incident_id,
            related_offense_incident_id=threat_incident_id or None,
            approach="threat",
            outcome=outcome,
            resolution_occurrence_id=threat["id"],
            pressure=round(pressure, 3),
            resistance=round(resistance, 3),
            prior_spread=prior,
        ))
        return {
            "npc_lines": (line,),
            "close": True,
            "social_fact_thread_id": thread["id"],
            "social_outcome": outcome,
        }

    if action == "offer_witness_bribe":
        incident_id = _int(row.get("social_fact_incident_id"), 0)
        thread = _witness_thread_for_action(sim, row, player, npc)
        player_record = _witness_resolution_record(sim, player, npc, incident_id)
        npc_view = ensure_actor_incident_perspective(sim, npc, incident_id)
        if not isinstance(player_record, dict) or not isinstance(npc_view, dict):
            return {"npc_lines": ("I don't know what you think I saw.",)}
        if incident_witness_resolution(sim, npc, incident_id) is not None:
            return {"npc_lines": ("You already chose how to handle this with me.",), "close": True}
        opening_amount = _witness_bribe_opening_amount(sim, player, npc, player_record)
        if opening_amount != _int(row.get("witness_bribe_amount"), -1):
            raise ValueError("witness bribe row no longer matches the grounded opening offer")
        proposition_id = _text((thread.get("metadata") or {}).get("proposition_id"))
        offer = record_occurrence(
            sim,
            "witness_bribe_offer",
            actor_eids=(player, npc),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=(_text(thread.get("origin_occurrence_id")),),
            payload={
                "incident_id": incident_id,
                "speaker_eid": player,
                "audience_eid": npc,
                "amount": opening_amount,
                "spoken_text": _text(row.get("player_line")),
            },
            flags=("speech", "attributed", "corrupt_offer"),
            dedupe_key=f"witness-bribe-offer:{player}:{npc}:{incident_id}",
        )
        prior = incident_prior_spread_state(sim, npc, incident_id)
        willing, counter_amount, lens = _witness_bribe_terms(
            sim,
            npc,
            npc_view["record"],
            opening_amount,
            prior,
        )
        bribery_incident_id = _emit_witness_bribery_offense(sim, player, npc, incident_id)
        assets = sim.ecs.get(PlayerAssets).get(player)
        if not isinstance(assets, PlayerAssets) or assets.credits < opening_amount:
            outcome = "declined"
            line = "Don't offer me money you don't have. Now I have the offer to remember too."
        elif not willing:
            outcome = "refused"
            if lens == "harmed_target":
                line = "You hurt me and then tried to buy my silence. No. I'm reporting the offer too."
            elif lens == "duty_bound":
                line = "No. You just added an attempted bribe to what I have to report."
            else:
                line = "No. I'm not selling you my silence. Now I have the offer to report too."
        elif opening_amount < counter_amount:
            outcome = "countered"
            if prior.get("authority_reported"):
                line = (
                    f"My first statement already exists. {counter_amount} credits buys no more voluntary help from me—"
                    "it does not erase what I already said."
                )
            else:
                line = f"Not for {opening_amount}. {counter_amount} credits, once, and I carry it no farther."
        elif _transfer_witness_bribe(sim, player, npc, opening_amount):
            outcome = "accepted"
            line = (
                "The report I already made still exists. I won't volunteer anything more."
                if prior.get("authority_reported")
                else "All right. I won't volunteer it or carry it any farther."
            )
        else:
            outcome = "declined"
            line = "You cannot cover the offer. We're done talking about a price."

        reaction = record_occurrence(
            sim,
            "reaction",
            actor_eids=(npc, player),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=(offer["id"],),
            payload={
                "shape": f"bribe_{outcome}",
                "lens": lens,
                "outcome": outcome,
                "opening_amount": opening_amount,
                "counter_amount": counter_amount if outcome == "countered" else None,
                "npc_spoken_text": line,
            },
            flags=("speech", "attributed", "perceptible"),
            dedupe_key=f"witness-bribe-reaction:{player}:{npc}:{incident_id}",
        )
        applied = apply_incident_witness_resolution(
            sim,
            npc,
            incident_id,
            player_eid=player,
            approach="bribe",
            outcome=outcome,
            status="awaiting_player" if outcome == "countered" else "resolved",
            occurrence_id=offer["id"],
            amount=opening_amount,
            counter_amount=counter_amount if outcome == "countered" else None,
            offense_incident_id=bribery_incident_id or None,
        )
        if not isinstance(applied, dict):
            return {"npc_lines": ("I don't know what you think I saw.",)}
        if outcome == "accepted" and bribery_incident_id > 0:
            apply_incident_witness_resolution(
                sim,
                npc,
                bribery_incident_id,
                player_eid=player,
                approach="bribe",
                outcome="accepted",
                occurrence_id=offer["id"],
                amount=opening_amount,
            )
        _shift_witness_transaction_relationship(
            sim,
            player,
            npc,
            offer["id"],
            approach="bribe",
            outcome=outcome,
        )
        advance_social_thread(
            sim,
            thread["id"],
            occurrence_id=reaction["id"],
            status="awaiting_response" if outcome == "countered" else "acted",
            awaiting_actor_eid=player if outcome == "countered" else None,
        )
        sim.emit(Event(
            "incident_witness_resolution",
            npc_eid=npc,
            player_eid=player,
            incident_id=incident_id,
            related_offense_incident_id=bribery_incident_id or None,
            approach="bribe",
            outcome=outcome,
            resolution_occurrence_id=offer["id"],
            prior_spread=prior,
        ))
        return {
            "npc_lines": (line,),
            "close": outcome != "countered",
            "social_fact_thread_id": thread["id"],
            "social_outcome": outcome,
        }

    if action in {"accept_witness_bribe_counter", "decline_witness_bribe_counter"}:
        incident_id = _int(row.get("social_fact_incident_id"), 0)
        thread = _witness_thread_for_action(sim, row, player, npc)
        resolution = incident_witness_resolution(sim, npc, incident_id)
        if (
            not isinstance(resolution, dict)
            or _token(resolution.get("approach")) != "bribe"
            or _token(resolution.get("outcome")) != "countered"
            or _token(resolution.get("status")) != "awaiting_player"
        ):
            return {"npc_lines": ("That offer is no longer open.",), "close": True}
        counter_amount = max(1, _int(resolution.get("counter_amount"), 0))
        if counter_amount != _int(row.get("witness_bribe_amount"), counter_amount):
            raise ValueError("witness counteroffer row no longer matches the stored price")
        accept = action == "accept_witness_bribe_counter"
        if accept and not _transfer_witness_bribe(sim, player, npc, counter_amount):
            return {"npc_lines": (f"You don't have the {counter_amount} credits. The price does not change.",)}
        proposition_id = _text((thread.get("metadata") or {}).get("proposition_id"))
        outcome = "accepted" if accept else "declined"
        line = (
            (
                "The first report stays where it is. I won't volunteer anything more."
                if incident_prior_spread_state(sim, npc, incident_id).get("authority_reported")
                else "Done. I won't volunteer it or carry it any farther."
            )
            if accept
            else "Then there is no deal. I decide what I do with what I saw."
        )
        occurrence = record_occurrence(
            sim,
            "witness_bribe_accepted" if accept else "witness_bribe_declined",
            actor_eids=(player, npc),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=(_text(resolution.get("occurrence_id")),),
            payload={
                "incident_id": incident_id,
                "amount": counter_amount,
                "player_spoken_text": _text(row.get("player_line")),
                "npc_spoken_text": line,
            },
            flags=("speech", "attributed", "transaction" if accept else "refusal"),
            dedupe_key=f"witness-bribe-{outcome}:{player}:{npc}:{incident_id}",
        )
        applied = apply_incident_witness_resolution(
            sim,
            npc,
            incident_id,
            player_eid=player,
            approach="bribe",
            outcome=outcome,
            status="resolved",
            occurrence_id=occurrence["id"],
            amount=counter_amount if accept else resolution.get("amount"),
            counter_amount=counter_amount,
            offense_incident_id=resolution.get("offense_incident_id"),
            allow_transition=True,
        )
        if not bool((applied or {}).get("applied", False)):
            return {"npc_lines": ("That offer is no longer open.",), "close": True}
        bribery_incident_id = _int(resolution.get("offense_incident_id"), 0)
        if accept and bribery_incident_id > 0:
            apply_incident_witness_resolution(
                sim,
                npc,
                bribery_incident_id,
                player_eid=player,
                approach="bribe",
                outcome="accepted",
                occurrence_id=occurrence["id"],
                amount=counter_amount,
            )
        _shift_witness_transaction_relationship(
            sim,
            player,
            npc,
            occurrence["id"],
            approach="bribe",
            outcome="accepted_counter" if accept else "declined_counter",
        )
        advance_social_thread(
            sim,
            thread["id"],
            occurrence_id=occurrence["id"],
            status="acted",
            awaiting_actor_eid=None,
        )
        sim.emit(Event(
            "incident_witness_resolution",
            npc_eid=npc,
            player_eid=player,
            incident_id=incident_id,
            related_offense_incident_id=bribery_incident_id or None,
            approach="bribe",
            outcome=outcome,
            resolution_occurrence_id=occurrence["id"],
            prior_spread=incident_prior_spread_state(sim, npc, incident_id),
        ))
        return {
            "npc_lines": (line,),
            "close": True,
            "social_fact_thread_id": thread["id"],
            "social_outcome": outcome,
        }

    if action == "confess_to_witness":
        incident_id = _int(row.get("social_fact_incident_id"), 0)
        thread = _witness_thread_for_action(sim, row, player, npc)
        npc_view = ensure_actor_incident_perspective(sim, npc, incident_id)
        if not isinstance(npc_view, dict) or incident_witness_resolution(sim, npc, incident_id) is not None:
            return {"npc_lines": ("We've already settled what you were asking of me.",), "close": True}
        prior = incident_prior_spread_state(sim, npc, incident_id)
        outcome, lens = _confession_outcome(sim, npc, npc_view["record"], bond, prior)
        proposition_id = _text((thread.get("metadata") or {}).get("proposition_id"))
        confession = record_occurrence(
            sim,
            "accountable_confession",
            actor_eids=(player, npc),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=(_text(thread.get("origin_occurrence_id")),),
            payload={
                "incident_id": incident_id,
                "speaker_eid": player,
                "audience_eid": npc,
                "spoken_text": _text(row.get("player_line")),
            },
            flags=("speech", "attributed", "self_attribution", "accountability"),
            dedupe_key=f"witness-accountable-confession:{player}:{npc}:{incident_id}",
        )
        _stamp_direct_confession(sim, player, npc, incident_id)
        deadline = None
        if outcome == "forbearance":
            deadline = _int(getattr(sim, "tick", 0), 0) + (_WITNESS_FORBEARANCE_HOURS * _ticks_per_hour(sim))
            line = (
                "All right. One day. You own it formally, with me there, before then. "
                "If you don't, I report what I saw and the promise you broke."
            )
        elif lens == "harmed_target":
            line = "You admitted it to the person you harmed. Making it right starts with reporting it now, not asking me for time."
        elif lens == "duty_bound":
            line = "I heard the admission. My duty is to report it now. You can come willingly."
        elif lens == "severity_boundary":
            line = "I believe that you mean to own it. This is too serious for me to hold privately. We report it now."
        else:
            line = "I heard you. I won't hide it for you; if you mean to own it, come and report it now."
        reaction = record_occurrence(
            sim,
            "reaction",
            actor_eids=(npc, player),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=(confession["id"],),
            payload={
                "shape": outcome,
                "lens": lens,
                "outcome": outcome,
                "deadline_tick": deadline,
                "npc_spoken_text": line,
            },
            flags=("speech", "attributed", "perceptible"),
            dedupe_key=f"witness-confession-reaction:{player}:{npc}:{incident_id}",
        )
        applied = apply_incident_witness_resolution(
            sim,
            npc,
            incident_id,
            player_eid=player,
            approach="confession",
            outcome=outcome,
            status="active" if outcome == "forbearance" else "resolved",
            deadline_tick=deadline,
            occurrence_id=confession["id"],
        )
        if not isinstance(applied, dict):
            return {"npc_lines": ("I don't know what you think I saw.",)}
        _shift_witness_transaction_relationship(
            sim,
            player,
            npc,
            confession["id"],
            approach="confession",
            outcome=outcome,
        )
        if outcome == "forbearance":
            _apply_player_obligation(
                sim,
                player,
                npc,
                confession["id"],
                0.50,
                effect_kind="witness_forbearance_granted",
            )
        advance_social_thread(
            sim,
            thread["id"],
            occurrence_id=reaction["id"],
            status="considering" if outcome == "forbearance" else "acted",
            awaiting_actor_eid=player if outcome == "forbearance" else None,
        )
        sim.emit(Event(
            "incident_witness_resolution",
            npc_eid=npc,
            player_eid=player,
            incident_id=incident_id,
            approach="confession",
            outcome=outcome,
            resolution_occurrence_id=confession["id"],
            prior_spread=prior,
        ))
        return {
            "npc_lines": (line,),
            "close": outcome != "forbearance",
            "social_fact_thread_id": thread["id"],
            "social_outcome": outcome,
        }

    if action == "fulfill_witness_accountability":
        incident_id = _int(row.get("social_fact_incident_id"), 0)
        thread = _witness_thread_for_action(sim, row, player, npc)
        resolution = incident_witness_resolution(sim, npc, incident_id)
        now = _int(getattr(sim, "tick", 0), 0)
        if (
            not isinstance(resolution, dict)
            or _token(resolution.get("approach")) != "confession"
            or _token(resolution.get("outcome")) != "forbearance"
            or _token(resolution.get("status")) != "active"
            or now > _int(resolution.get("deadline_tick"), now)
        ):
            return {"npc_lines": ("That time has passed. I have to handle the broken promise now.",), "close": True}
        proposition_id = _text((thread.get("metadata") or {}).get("proposition_id"))
        attempt = record_occurrence(
            sim,
            "witness_accountability_attempt",
            actor_eids=(player, npc),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=(_text(resolution.get("occurrence_id")),),
            payload={
                "incident_id": incident_id,
                "player_spoken_text": _text(row.get("player_line")),
            },
            flags=("speech", "attributed", "accountability_attempt"),
            dedupe_key=f"witness-accountability-attempt:{player}:{npc}:{incident_id}:{now}",
        )
        route_request = Event(
            "observed_response_cue",
            npc_eid=npc,
            incident_id=incident_id,
            cue_kind="report_authority",
            target=None,
            target_eid=None,
            urgency=0.9,
            reason="witness_accountability_fulfilled",
            preferred_methods=(
                "cell_phone", "radio", "camera_network", "peace_officer",
                "alarm", "work_phone", "home_phone",
            ),
            deferred_report=False,
            followup_statement=True,
            bypass_witness_suppression=True,
        )
        sim.emit(route_request)
        route_status = _token(route_request.data.get("response_route_status"))
        if route_status not in {"started", "completed"}:
            line = (
                "I heard you, but I can't reach anyone from here. Find us a real way to report it "
                "before the time runs out."
            )
            advance_social_thread(
                sim,
                thread["id"],
                occurrence_id=attempt["id"],
                status="considering",
                awaiting_actor_eid=player,
            )
            return {
                "npc_lines": (line,),
                "social_fact_thread_id": thread["id"],
                "social_outcome": "route_unavailable",
            }
        line = "All right. I will come with you and repeat exactly what I saw and what you admitted—no more, no less."
        fulfillment = record_occurrence(
            sim,
            "witness_accountability_fulfilled",
            actor_eids=(player, npc),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=(attempt["id"],),
            payload={
                "incident_id": incident_id,
                "player_spoken_text": _text(row.get("player_line")),
                "npc_spoken_text": line,
            },
            flags=("speech", "attributed", "promise_fulfilled", "accountability"),
            dedupe_key=f"witness-accountability-fulfilled:{player}:{npc}:{incident_id}",
        )
        applied = apply_incident_witness_resolution(
            sim,
            npc,
            incident_id,
            player_eid=player,
            approach="confession",
            outcome="fulfilled",
            status="resolved",
            occurrence_id=fulfillment["id"],
            allow_transition=True,
        )
        if not bool((applied or {}).get("applied", False)):
            return {"npc_lines": ("That promise is no longer open.",), "close": True}
        _apply_player_obligation(
            sim,
            player,
            npc,
            fulfillment["id"],
            -0.50,
            effect_kind="witness_accountability_fulfilled",
        )
        advance_social_thread(
            sim,
            thread["id"],
            occurrence_id=fulfillment["id"],
            status="closed",
            awaiting_actor_eid=None,
        )
        sim.emit(Event(
            "incident_witness_resolution",
            npc_eid=npc,
            player_eid=player,
            incident_id=incident_id,
            approach="confession",
            outcome="fulfilled",
            resolution_occurrence_id=fulfillment["id"],
            prior_spread=incident_prior_spread_state(sim, npc, incident_id),
            followup_statement=True,
            report_already_requested=True,
        ))
        return {
            "npc_lines": (line,),
            "close": True,
            "social_fact_thread_id": thread["id"],
            "social_outcome": "fulfilled",
        }

    if action == "leave_witness_resolution":
        incident_id = _int(row.get("social_fact_incident_id"), 0)
        thread = _witness_thread_for_action(sim, row, player, npc)
        occurrence = record_occurrence(
            sim,
            "witness_matter_deferred",
            actor_eids=(player, npc),
            proposition_ids=tuple(thread.get("proposition_ids", ()) or ()),
            source_occurrence_ids=(_text(thread.get("origin_occurrence_id")),),
            payload={"incident_id": incident_id, "spoken_text": _text(row.get("player_line"))},
            flags=("speech", "attributed", "deferred"),
            dedupe_key=f"witness-matter-deferred:{player}:{npc}:{incident_id}",
        )
        advance_social_thread(
            sim,
            thread["id"],
            occurrence_id=occurrence["id"],
            status="awaiting_response",
            awaiting_actor_eid=player,
        )
        return {"npc_lines": ("All right. But what I saw does not go away.",), "close": True}

    if action == "tell_incident":
        incident_id = _int(row.get("social_fact_incident_id"), 0)
        player_view = ensure_actor_incident_perspective(sim, player, incident_id)
        if not isinstance(player_view, dict):
            return {"npc_lines": ["You stop. You cannot place where you got that story."]}
        proposition_id = player_view["proposition"]["id"]
        if proposition_id != _text(row.get("social_fact_proposition_id")):
            raise ValueError("incident dialogue row no longer matches the player's account")

        npc_view = ensure_actor_incident_perspective(sim, npc, incident_id)
        warning_record = npc_view.get("record") if isinstance(npc_view, dict) else {}
        warned_from_player = (
            _int((warning_record or {}).get("social_fact_warning_requester_eid"), 0) == player
            and _int((warning_record or {}).get("heard_from_eid"), 0) > 0
        )
        if not isinstance(npc_view, dict):
            reaction_shape = "new_information"
        elif warned_from_player and npc_view["proposition"]["id"] == proposition_id:
            reaction_shape = "warning_recognition"
        elif npc_view["proposition"]["id"] == proposition_id:
            reaction_shape = "recognition"
        else:
            reaction_shape = "different_account"
        reaction_lens = _social_fact_reaction_lens(sim, npc, player_view, bond)

        trust = _bond_trust(bond)
        credibility = 0.32 + (trust * 0.5)
        confidence = _unit(player_view["record"].get("confidence"), 0.5)
        claim = record_claim(
            sim,
            player,
            (npc,),
            proposition_id,
            certainty=confidence,
            credibility_by_audience={npc: credibility},
            salience=max(0.3, _unit(player_view["record"].get("social_interest"), 0.0)),
            spoken_text=_text(row.get("player_line")),
            dedupe_key=f"social-fact-dialogue:claim:{player}:{npc}:{proposition_id}",
        )
        thread = open_social_thread(
            sim,
            participants=(player, npc),
            proposition_ids=(proposition_id,),
            origin_occurrence_id=claim["id"],
            kind="conversation",
            status="awaiting_response",
            awaiting_actor_eid=player,
            tags=("two_way_dialogue", "incident_report"),
            metadata={
                "exchange_kind": _EXCHANGE_KIND,
                "player_eid": player,
                "npc_eid": npc,
                "incident_id": incident_id,
                "proposition_id": proposition_id,
                "label": player_view["label"],
                "reaction_shape": reaction_shape,
                "reaction_lens": reaction_lens,
            },
            thread_key=f"incident-dialogue:{player}:{npc}:{proposition_id}",
        )
        cue, line = _reaction_copy(sim, reaction_shape, reaction_lens, warning_record or {})
        reaction = record_occurrence(
            sim,
            "reaction",
            actor_eids=(npc, player),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=(claim["id"],),
            payload={
                "shape": reaction_shape,
                "lens": reaction_lens,
                "perceptible_cue": cue,
                "npc_spoken_text": line,
            },
            flags=("perceptible", "awaits_response"),
            dedupe_key=f"social-fact-dialogue:reaction:{claim['id']}",
        )
        advance_social_thread(
            sim,
            thread["id"],
            occurrence_id=reaction["id"],
            status="awaiting_response",
            awaiting_actor_eid=player,
        )
        return {
            "narration_lines": (cue,),
            "npc_lines": (line,),
            "social_fact_thread_id": thread["id"],
        }

    thread = _thread_for_action(sim, row, player, npc)
    metadata = thread.get("metadata") if isinstance(thread.get("metadata"), dict) else {}
    thread_id = _text(thread.get("id"))
    label = _text(metadata.get("label")) or "incident"
    trust = _bond_trust(bond)
    consequence = social_fact_action_for_thread(sim, thread_id, owner_eid=npc)

    if action == "ask_corroboration":
        if isinstance(consequence, dict):
            return {"npc_lines": ("I already told you I'd see what I could learn.",)}
        perspective = actor_perspective(sim, npc, _text(metadata.get("proposition_id"))) or {}
        stance = _token(perspective.get("stance"))
        if stance in {"doubtful", "rejected"} or (stance == "unknown" and trust < 0.28):
            line = "No. I don't have enough reason to carry that story to somebody else."
            occurrence = _thread_occurrence(
                sim,
                thread,
                "corroboration_declined",
                player=player,
                npc=npc,
                action=action,
                player_spoken_text=_text(row.get("player_line")),
                npc_spoken_text=line,
            )
            advance_social_thread(
                sim,
                thread_id,
                occurrence_id=occurrence["id"],
                status="closed",
                awaiting_actor_eid=None,
            )
            return {"npc_lines": (line,)}

        line = (
            "I'll ask one person I trust. If it's just the same story coming back around, "
            "I won't treat that as a second account."
        )
        occurrence = _thread_occurrence(
            sim,
            thread,
            "corroboration_requested",
            player=player,
            npc=npc,
            action=action,
            player_spoken_text=_text(row.get("player_line")),
            npc_spoken_text=line,
        )
        advance_social_thread(
            sim,
            thread_id,
            occurrence_id=occurrence["id"],
            status="considering",
            awaiting_actor_eid=None,
        )
        request_incident_corroboration(
            sim,
            thread_id=thread_id,
            owner_eid=npc,
            requester_eid=player,
            incident_id=metadata.get("incident_id"),
            proposition_id=metadata.get("proposition_id"),
            label=label,
            request_occurrence_id=occurrence["id"],
        )
        return {"npc_lines": (line,)}

    if action == "ask_corroboration_progress":
        if not isinstance(consequence, dict):
            return {"npc_lines": ("I don't know what check you mean.",)}
        if _token(consequence.get("status")) == "seeking":
            line = "Not yet. I'm trying to catch someone I trust, but I don't have an answer for you."
        else:
            line = "Not yet. I haven't had the right person in front of me, and I won't pretend I've checked."
        occurrence = _thread_occurrence(
            sim,
            thread,
            "dialogue_response",
            player=player,
            npc=npc,
            action=action,
            player_spoken_text=_text(row.get("player_line")),
            npc_spoken_text=line,
        )
        advance_social_thread(
            sim,
            thread_id,
            occurrence_id=occurrence["id"],
            status=_token(thread.get("status")) or "considering",
            awaiting_actor_eid=None,
        )
        mark_social_fact_action_progress_reported(sim, thread_id, owner_eid=npc)
        return {"npc_lines": (line,)}

    if action == "ask_warning_progress":
        if not isinstance(consequence, dict):
            return {"npc_lines": ("I don't know what check you mean.",)}
        warning_status = _token(consequence.get("warning_status"))
        if warning_status == "seeking":
            line = (
                "I got a separate account that held up. There's someone close enough to the place that "
                "I want to warn them myself, but I haven't reached them yet."
            )
        else:
            line = (
                "I got a separate account that held up. I'm deciding whether there's anyone I know who "
                "is close enough to the place to need a warning."
            )
        occurrence = _thread_occurrence(
            sim,
            thread,
            "dialogue_response",
            player=player,
            npc=npc,
            action=action,
            player_spoken_text=_text(row.get("player_line")),
            npc_spoken_text=line,
        )
        advance_social_thread(
            sim,
            thread_id,
            occurrence_id=occurrence["id"],
            status=_token(thread.get("status")) or "considering",
            awaiting_actor_eid=None,
        )
        mark_social_fact_warning_progress_reported(sim, thread_id, owner_eid=npc)
        return {"npc_lines": (line,)}

    if action == "ask_corroboration_result":
        if not isinstance(consequence, dict) or _token(consequence.get("status")) not in {"completed", "failed"}:
            return {"npc_lines": ("I don't have anything new to tell you yet.",)}
        outcome = _token(consequence.get("outcome"))
        lines = {
            "corroborated": (
                "I asked someone I trust. They had their own reason to know, and their account "
                "lined up with yours. I'm taking it seriously now."
            ),
            "different_account": (
                "I asked someone I trust. What they heard doesn't line up cleanly with what you "
                "told me. I'm not calling either version settled."
            ),
            "same_hearsay": (
                "They'd heard it too, but only as a story passed along. That's not a second account."
            ),
            "no_prior_account": "I asked. It was new to them too, so I didn't get a second account.",
            "no_contact": "I couldn't get hold of anyone I trusted to check it. I haven't verified it.",
        }
        line = lines.get(outcome, "I tried, but I didn't get an account I could put weight on.")
        if outcome == "corroborated" and bool(consequence.get("warning_progress_reported", False)):
            line = "The separate account held up. I'm taking it seriously."
        warning = social_fact_warning_report_for_thread(sim, thread_id, owner_eid=npc) or {}
        warning_status = _token(warning.get("warning_status"))
        warning_outcome = _token(warning.get("warning_outcome"))
        warning_name = _text(warning.get("warning_recipient_name")) or "someone I know"
        if warning_status == "delivered":
            warning_lines = {
                "accepted": (
                    f"I also warned {warning_name}, because they were still close to the place. "
                    "They took it seriously enough to put some distance between themselves and it."
                    if _token(warning.get("warning_behavior")) == "started_moving_away"
                    else f"I also warned {warning_name}. They took it seriously and said they'd keep clear."
                ),
                "already_knew": f"I also warned {warning_name}. They already had their own reason to know.",
                "already_warned": (
                    f"I warned {warning_name}, but somebody had already carried the same account to them. "
                    "They wouldn't treat another lap as new evidence."
                ),
                "disputed": (
                    f"I warned {warning_name}, but they had a different account and wouldn't pretend the two fit."
                ),
                "doubtful": (
                    f"I warned {warning_name}. They listened, but they weren't willing to treat one check as settled."
                ),
                "rejected": f"I warned {warning_name}. They didn't think my account was strong enough to move on.",
            }
            line = f"{line} {warning_lines.get(warning_outcome, f'I also warned {warning_name}.')}"
            if bool(warning.get("corrected_at_delivery", False)):
                line = f"{line} I told them you had already backed off your certainty."
        elif warning_status == "failed" and outcome == "corroborated":
            line = (
                f"{line} I didn't find anyone I knew who was close enough to warn without turning it "
                "into a broadcast."
            )
        elif warning_status == "not_applicable" and outcome == "corroborated":
            line = f"{line} I didn't carry it farther than that."
        corrected = _thread_has_correction(sim, thread)
        if corrected:
            line = f"I was already trying when you corrected yourself. {line}"
        occurrence = _thread_occurrence(
            sim,
            thread,
            "corroboration_followup",
            player=player,
            npc=npc,
            action=action,
            player_spoken_text=_text(row.get("player_line")),
            npc_spoken_text=line,
        )
        if corrected:
            next_status = "corroborated" if outcome == "corroborated" else "disputed" if outcome == "different_account" else "retracted"
        else:
            next_status = "corroborated" if outcome == "corroborated" else "disputed" if outcome == "different_account" else "closed"
        advance_social_thread(
            sim,
            thread_id,
            occurrence_id=occurrence["id"],
            status=next_status,
            awaiting_actor_eid=None,
        )
        mark_social_fact_action_reported(sim, thread_id, owner_eid=npc)
        _remember_spoken_warning_reference(
            sim,
            player,
            npc,
            warning,
            line,
            label=_text(metadata.get("label")) or "incident",
        )
        return {"npc_lines": (line,)}

    if action == "ask_correction_relay_result":
        if not isinstance(consequence, dict):
            return {"npc_lines": ("I don't know who you mean.",)}
        relay_status = _token(consequence.get("correction_relay_status"))
        warning = social_fact_warning_report_for_thread(sim, thread_id, owner_eid=npc) or {}
        warning_name = _text(warning.get("warning_recipient_name")) or "them"
        if relay_status == "delivered":
            line = (
                f"Yes. I found {warning_name} and told them you had backed off how certain you were. "
                "I also told them the separate account still exists."
            )
        else:
            line = (
                f"No. I couldn't get back to {warning_name}. I won't tell you they heard the correction "
                "when they didn't."
            )
        occurrence = _thread_occurrence(
            sim,
            thread,
            "correction_relay_followup",
            player=player,
            npc=npc,
            action=action,
            player_spoken_text=_text(row.get("player_line")),
            npc_spoken_text=line,
        )
        advance_social_thread(
            sim,
            thread_id,
            occurrence_id=occurrence["id"],
            status=_token(thread.get("status")) or "retracted",
            awaiting_actor_eid=None,
        )
        mark_social_fact_correction_relay_reported(sim, thread_id, owner_eid=npc)
        _remember_spoken_warning_reference(
            sim,
            player,
            npc,
            warning,
            line,
            label=_text(metadata.get("label")) or "incident",
        )
        return {"npc_lines": (line,)}

    if action == "correct_claim":
        if _thread_has_correction(sim, thread):
            return {"npc_lines": ["I heard you the first time you corrected it."]}
        correction = record_correction(
            sim,
            player,
            (npc,),
            _text(thread.get("origin_occurrence_id")),
            certainty=0.82,
            credibility_by_audience={npc: 0.4 + (trust * 0.45)},
            spoken_text=_text(row.get("player_line")),
            dedupe_key=f"social-fact-dialogue:correction:{thread_id}",
        )
        consequence_status = _token((consequence or {}).get("status")) if isinstance(consequence, dict) else ""
        consequence_outcome = _token((consequence or {}).get("outcome")) if isinstance(consequence, dict) else ""
        warning_status = _token((consequence or {}).get("warning_status")) if isinstance(consequence, dict) else ""
        warning = social_fact_warning_report_for_thread(sim, thread_id, owner_eid=npc) or {}
        warning_name = _text(warning.get("warning_recipient_name")) or "them"
        correction_relay_requested = request_social_fact_warning_correction(
            sim,
            thread_id,
            owner_eid=npc,
            correction_occurrence_id=correction["id"],
        )
        if consequence_status in {"requested", "seeking"}:
            acknowledgement_line = (
                "All right. I was already moving on it, so I can't make that unhappen. "
                "If I reach anyone, I'll make clear that you backed off the claim."
            )
        elif correction_relay_requested:
            acknowledgement_line = (
                f"I hear the correction. I already warned {warning_name}, so I can't make that unhappen. "
                "I'll go tell them you backed off how certain you were."
            )
        elif warning_status in {"requested", "seeking"}:
            acknowledgement_line = (
                "I hear the correction. I haven't warned anyone yet. If I do reach somebody, I'll tell "
                "them you backed off and that the separate account is why I'm still speaking."
            )
        elif consequence_outcome == "corroborated":
            acknowledgement_line = (
                "I hear the correction. I also heard a separate account; yours isn't the only one I have now."
            )
        else:
            acknowledgement_line = (
                "All right. I'd rather you came back and corrected it than let it stand."
            )
        acknowledgement = record_occurrence(
            sim,
            "reaction",
            actor_eids=(npc, player),
            proposition_ids=tuple(thread.get("proposition_ids", ()) or ()),
            source_occurrence_ids=(correction["id"],),
            payload={
                "shape": "acknowledged_correction",
                "npc_spoken_text": acknowledgement_line,
            },
            flags=("speech", "attributed", "repair_acknowledgement"),
            dedupe_key=f"social-fact-dialogue:correction-ack:{thread_id}",
        )
        correction_status = (
            "corroborated"
            if consequence_outcome == "corroborated"
            else "disputed"
            if consequence_outcome == "different_account"
            else "retracted"
        )
        advance_social_thread(
            sim,
            thread_id,
            occurrence_id=correction["id"],
            status=correction_status,
            awaiting_actor_eid=None,
        )
        advance_social_thread(
            sim,
            thread_id,
            occurrence_id=acknowledgement["id"],
            status=correction_status,
            awaiting_actor_eid=None,
        )
        _remember_spoken_warning_reference(
            sim,
            player,
            npc,
            warning,
            acknowledgement_line,
            label=_text(metadata.get("label")) or "incident",
        )
        return {
            "npc_lines": (acknowledgement_line,),
        }

    if action == "answer_motive":
        reaction_lens = _token(metadata.get("reaction_lens"))
        if reaction_lens == "workplace_stake":
            line = "It does matter to me. You put it where I work; I need to know what is still at risk there."
        elif reaction_lens == "home_stake":
            line = "It does matter to me. You put it close to home; I need to decide who else there should hear it."
        elif reaction_lens == "duty_triage":
            line = "It might. First I need to separate what you saw from what reached you secondhand."
        elif reaction_lens == "protective_concern":
            line = "It might. I'm thinking about who could still be exposed and whether a warning would help."
        elif reaction_lens == "source_skepticism":
            line = "Maybe it does. I still need to decide how much of the account rests on you."
        else:
            line = (
                "Then I'm glad you brought it to me. I'll think about who else needs to hear it."
                if trust >= 0.5
                else "Maybe it does. I'll decide what weight to give it."
            )
        status = "considering"
    elif action == "ask_take":
        perspective = actor_perspective(sim, npc, _text(metadata.get("proposition_id"))) or {}
        stance = _token(perspective.get("stance"))
        if stance in {"accepted", "plausible"}:
            line = "It sounds possible. I wouldn't call it settled from one account."
        elif stance == "disputed":
            line = "It doesn't line up cleanly with what I heard before."
        else:
            line = "Right now, it's one account. I'll keep it in mind."
        status = "considering"
    elif action == "ask_reaction":
        shape = _token(metadata.get("reaction_shape"))
        reaction_lens = _token(metadata.get("reaction_lens"))
        npc_perspective = actor_perspective(
            sim,
            npc,
            _text(metadata.get("proposition_id")),
        ) or {}
        exposure = _token(npc_perspective.get("exposure"))
        warning_record = ensure_actor_incident_perspective(sim, npc, metadata.get("incident_id"))
        warning_account = warning_record.get("record") if isinstance(warning_record, dict) else {}
        warning_reaction = _token((warning_account or {}).get("social_fact_warning_reaction"))
        warning_source = _int((warning_account or {}).get("heard_from_eid"), 0)
        if shape == "warning_recognition" and warning_source > 0:
            warning_source_name = _actor_name(sim, warning_source, "Someone")
            warning_behavior = _token((warning_account or {}).get("social_fact_warning_behavior"))
            if warning_reaction == "accepted" and warning_behavior == "started_moving_away":
                line = (
                    f"{warning_source_name} came over in person and said they'd checked it. I moved because "
                    "standing there to test a warning would have been stupid."
                )
            elif warning_reaction == "disputed":
                line = f"{warning_source_name} warned me, but their account doesn't match the one I had."
            else:
                line = f"{warning_source_name} warned me. I listened; that doesn't mean I swallowed every part of it."
        elif reaction_lens == "workplace_stake":
            line = "You put it at my workplace. I need to know whether anyone there is still at risk."
        elif reaction_lens == "home_stake":
            line = "You put it close to where I live. Of course that got my attention."
        elif reaction_lens == "duty_triage":
            line = "You gave me something that might need checking. I was sorting what you saw from what you heard."
        elif reaction_lens == "protective_concern":
            line = "People could still be in danger. I was trying to work out whether warning someone would help."
        elif reaction_lens == "source_skepticism":
            line = "You brought me an account with some distance in it. I was trying to work out how much was yours."
        elif exposure in {"observed", "witnessed", "verified"}:
            line = "I was close enough to recognize it. I'm not ready to tell you more than that."
        elif shape == "different_account":
            line = "I've heard another version. That doesn't mean I owe you the source."
        else:
            line = "I was listening. Don't turn that into a confession for me."
        status = "considering"
    elif action == "withdraw":
        line = "All right. I heard you."
        status = "closed"
    elif action == "follow_up":
        perspective = actor_perspective(sim, npc, _text(metadata.get("proposition_id"))) or {}
        stance = _token(perspective.get("stance"))
        if stance == "disputed":
            line = f"The {label} still doesn't line up cleanly. I haven't dismissed it."
        elif stance in {"accepted", "plausible"}:
            line = f"I've kept the {label} in mind. I still need another account before I act on it."
        else:
            line = f"I haven't found a second account of the {label}. I haven't forgotten it either."
        status = "closed"
    else:
        line = "I don't know what you want me to do with that."
        status = "closed"
    occurrence = _thread_occurrence(
        sim,
        thread,
        "dialogue_response" if action != "ask_reaction" else "pushback",
        player=player,
        npc=npc,
        action=action,
        player_spoken_text=_text(row.get("player_line")),
        npc_spoken_text=line,
    )
    advance_social_thread(
        sim,
        thread_id,
        occurrence_id=occurrence["id"],
        status=status,
        awaiting_actor_eid=None,
    )
    return {"npc_lines": (line,)}


def validate_social_fact_dialogue_boundaries(sim) -> tuple[str, ...]:
    """Return adapter-specific errors for focused regressions and debugging."""

    errors = []
    state = social_fact_graph_state(sim)
    for thread_id, thread in state["threads"].items():
        if not isinstance(thread, dict):
            continue
        metadata = thread.get("metadata") if isinstance(thread.get("metadata"), dict) else {}
        if metadata.get("exchange_kind") != _EXCHANGE_KIND:
            continue
        participants = set(thread.get("participants", ()) or ())
        player = _int(metadata.get("player_eid"), 0)
        npc = _int(metadata.get("npc_eid"), 0)
        if player <= 0 or npc <= 0 or not {player, npc}.issubset(participants):
            errors.append(f"incident exchange {thread_id} has inconsistent participants")
        claim = occurrence_record(sim, thread.get("origin_occurrence_id"))
        if not isinstance(claim, dict) or claim.get("kind") != "claim":
            errors.append(f"incident exchange {thread_id} has no originating claim")
        if _token(metadata.get("reaction_shape")) not in {
            "new_information",
            "recognition",
            "different_account",
        }:
            errors.append(f"incident exchange {thread_id} has no bounded reaction shape")
    return tuple(errors)


__all__ = [
    "SOCIAL_FACT_TOPIC_PREFIX",
    "is_social_fact_dialogue_topic",
    "resolve_social_fact_dialogue",
    "social_fact_dialogue_rows",
    "specific_witness_matter_exists",
    "validate_social_fact_dialogue_boundaries",
]
