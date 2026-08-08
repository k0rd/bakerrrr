"""Shared NPC social-knowledge helpers.

SocialKnowledge is a shareable gossip layer over existing truth systems. It
stores what an actor can plausibly talk about, not the canonical facts.
"""

from __future__ import annotations

import random

from engine.events import Event
from game.components import (
    BusinessKnowledge,
    CreatureIdentity,
    IncidentKnowledge,
    NPCSocial,
    Position,
    SocialKnowledge,
)
from game.incident_runtime import incident_knowledge_label, incident_record
from game.incident_silencing import (
    incident_spread_suppressed,
    social_knowledge_incident_spread_suppressed,
)
from game.system_support.entity_naming import _entity_display_name


SOCIAL_SHARE_COOLDOWN_TICKS = 80


def _text(value):
    return str(value or "").strip()


def _key(value):
    return _text(value).lower()


def _looks_like_machine_label(value):
    text = _text(value)
    if not text:
        return False
    compact = text.replace("_", "").replace("/", "").replace("-", "")
    return ("_" in text or "/" in text) and compact.isalnum()


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


def _clamp(value, default=0.0):
    return max(0.0, min(1.0, _float(value, default=default)))


def _copy_refs(record):
    refs = record.get("refs") if isinstance(record, dict) else None
    return dict(refs or {}) if isinstance(refs, dict) else {}


def _card_material_changed(before, after):
    if not isinstance(after, dict):
        return False
    if not isinstance(before, dict):
        return True
    fields = (
        "summary",
        "detail",
        "source_kind",
        "source_eid",
        "confidence",
        "firsthand",
        "propagation_depth",
        "social_interest",
        "tags",
    )
    for field in fields:
        if before.get(field) != after.get(field):
            return True
    return _copy_refs(before) != _copy_refs(after)


def _emit_social_knowledge_produced(
    sim,
    actor_eid,
    record,
    *,
    source_event="",
    created=False,
    queued=False,
):
    if sim is None or not isinstance(record, dict) or not hasattr(sim, "emit"):
        return
    sim.emit(Event(
        "social_knowledge_produced",
        actor_eid=actor_eid,
        social_knowledge_key=record.get("key"),
        source_domain=record.get("source_domain"),
        subject_key=record.get("subject_key"),
        source_event=_key(source_event) or "social_knowledge",
        created=bool(created),
        queued=bool(queued),
        summary=record.get("summary", ""),
        confidence=round(_clamp(record.get("confidence"), default=0.0), 3),
        social_interest=round(_clamp(record.get("social_interest"), default=0.0), 3),
        refs=_copy_refs(record),
    ))


def _entity_name(sim, eid):
    actor_id = _int(eid, 0)
    if actor_id <= 0:
        return "someone"
    player_eid = _int(getattr(sim, "player_eid", None), 0)
    if actor_id == player_eid:
        identity = sim.ecs.get(CreatureIdentity).get(actor_id)
        if identity:
            label = _text(identity.display_name()).replace("_", " ")
            if label and _key(label) not in {"entity", "player"}:
                return label.title()
        return "that runner"
    return _entity_display_name(sim, actor_id, title_case=True) or "someone"


def _property_name(sim, property_id):
    key = _text(property_id)
    if not key:
        return ""
    prop = getattr(sim, "properties", {}).get(key)
    if isinstance(prop, dict):
        return _text(prop.get("name")) or _text(prop.get("id"))
    return key


def social_knowledge_for(sim, eid, *, create=True):
    actor_id = _int(eid, 0)
    if actor_id <= 0:
        return None
    knowledge = sim.ecs.get(SocialKnowledge).get(actor_id)
    if knowledge is None and create:
        sim.ecs.add(actor_id, SocialKnowledge())
        knowledge = sim.ecs.get(SocialKnowledge).get(actor_id)
    return knowledge


def remember_social_knowledge(
    sim,
    actor_eid,
    source_domain,
    subject_key,
    *,
    score=0.0,
    tick=None,
    queue=True,
    source_event="",
    emit_event=True,
    **kwargs,
):
    knowledge = social_knowledge_for(sim, actor_eid, create=True)
    if not isinstance(knowledge, SocialKnowledge):
        return None
    now = _int(getattr(sim, "tick", 0) if tick is None else tick, 0)
    entry_key = knowledge._entry_key(source_domain, subject_key)
    before = dict(knowledge.entries.get(entry_key) or {}) if entry_key else None
    record = knowledge.remember(
        source_domain,
        subject_key,
        learned_tick=kwargs.pop("learned_tick", now),
        **kwargs,
    )
    queued = False
    if isinstance(record, dict) and queue:
        queued = knowledge.queue_entry(
            record.get("key"),
            score=max(_clamp(score, default=0.0), _clamp(record.get("social_interest"), default=0.0)),
            tick=now,
        )
    if isinstance(record, dict) and emit_event:
        created = not isinstance(before, dict) or not before
        if created or _card_material_changed(before, record):
            _emit_social_knowledge_produced(
                sim,
                actor_eid,
                record,
                source_event=source_event,
                created=created,
                queued=queued,
            )
    return record


def hydrate_incident_social_knowledge(sim, actor_eid, *, limit=3, source_event="incident_social_hydrate"):
    incident_knowledge = sim.ecs.get(IncidentKnowledge).get(actor_eid)
    if not isinstance(incident_knowledge, IncidentKnowledge):
        return 0
    created = 0
    now = _int(getattr(sim, "tick", 0), 0)
    for queue_row in tuple(getattr(incident_knowledge, "social_queue", ()) or ())[: max(1, int(limit or 1))]:
        incident_id = _int(queue_row.get("incident_id"), 0)
        record = (incident_knowledge.records or {}).get(incident_id)
        if incident_id <= 0 or not isinstance(record, dict):
            continue
        if incident_spread_suppressed(sim, actor_eid, incident_id):
            continue
        incident = incident_record(sim, incident_id) or {}
        kind = incident_knowledge_label(record, incident)
        note = _text(record.get("account_note")) or _text(incident.get("note"))
        if _looks_like_machine_label(note):
            note = ""
        place = _property_name(sim, incident.get("property_id") or record.get("property_id"))
        if note:
            summary = note
        elif place:
            summary = f"{kind} around {place}"
        else:
            summary = kind
        detail = summary
        if place and place.lower() not in summary.lower():
            detail = f"{summary} near {place}"
        refs = {
            "incident_id": incident_id,
            "property_id": incident.get("property_id") or record.get("property_id"),
            "x": record.get("x", incident.get("x")),
            "y": record.get("y", incident.get("y")),
            "z": record.get("z", incident.get("z")),
        }
        social_interest = max(_clamp(queue_row.get("score"), default=0.0), _clamp(record.get("social_interest"), default=0.0))
        remembered = remember_social_knowledge(
            sim,
            actor_eid,
            "incident",
            str(incident_id),
            source_kind=record.get("source_kind", ""),
            source_eid=record.get("source_eid"),
            confidence=record.get("confidence", 0.5),
            firsthand=bool(record.get("firsthand", False)),
            propagation_depth=record.get("propagation_depth", 0),
            social_interest=social_interest,
            summary=summary,
            detail=detail,
            tags=tuple(record.get("account_tags", ()) or ()) + tuple(incident.get("tags", ()) or ()),
            refs=refs,
            score=social_interest,
            tick=now,
            source_event=source_event,
        )
        if isinstance(remembered, dict):
            created += 1
    return created


def hydrate_opportunity_social_knowledge(sim, actor_eid, rows, *, limit=3, source_event="opportunity_social_hydrate"):
    created = 0
    now = _int(getattr(sim, "tick", 0), 0)
    for row in tuple(rows or ())[: max(1, int(limit or 1))]:
        if not isinstance(row, dict):
            continue
        opportunity_id = _int(row.get("id"), 0)
        if opportunity_id <= 0:
            continue
        title = _text(row.get("title")) or "Opportunity"
        detail = _text(row.get("summary")) or "might be worth a look"
        distance = _int(row.get("distance"), 0)
        direction = _text(row.get("direction")).upper()
        distance_phrase = "nearby"
        if distance > 0 and direction:
            distance_phrase = f"{distance} blocks {direction}"
        requirements = row.get("requirements") if isinstance(row.get("requirements"), dict) else {}
        property_id = _text(requirements.get("property_id")) or _text(row.get("property_id"))
        summary = f"{title} {distance_phrase}: {detail}"
        risk = _key(row.get("risk")) or "low"
        confidence = max(0.35, min(0.86, _float(row.get("confidence"), 0.58)))
        social_interest = 0.58 + (0.12 if risk in {"exposed", "hazardous"} else 0.0)
        remembered = remember_social_knowledge(
            sim,
            actor_eid,
            "opportunity",
            str(opportunity_id),
            source_kind=_key(row.get("source")) or "observer_intel",
            source_eid=row.get("source_eid"),
            confidence=confidence,
            firsthand=_key(row.get("awareness_state")) == "confirmed",
            propagation_depth=0,
            social_interest=social_interest,
            summary=summary,
            detail=detail,
            tags=("opportunity", _key(row.get("kind")), risk),
            refs={
                "opportunity_id": opportunity_id,
                "property_id": property_id or None,
                "property_lead_kind": "opportunity",
            },
            score=social_interest,
            tick=now,
            source_event=source_event,
        )
        if isinstance(remembered, dict):
            created += 1
    return created


def hydrate_business_social_knowledge(sim, actor_eid, *, limit=3, source_event="business_social_hydrate"):
    business_knowledge = sim.ecs.get(BusinessKnowledge).get(actor_eid)
    if not isinstance(business_knowledge, BusinessKnowledge):
        return 0
    created = 0
    now = _int(getattr(sim, "tick", 0), 0)
    queue_rows = tuple(getattr(business_knowledge, "social_queue", ()) or ())
    if not queue_rows:
        queue_rows = tuple(
            {"property_id": key, "score": record.get("social_interest", 0.0), "queued_tick": record.get("last_learned_tick", 0)}
            for key, record in (business_knowledge.records or {}).items()
            if isinstance(record, dict) and _clamp(record.get("social_interest"), default=0.0) >= 0.35
        )
    for queue_row in queue_rows[: max(1, int(limit or 1))]:
        property_id = _text(queue_row.get("property_id"))
        record = (business_knowledge.records or {}).get(property_id)
        if not property_id or not isinstance(record, dict):
            continue
        place = _property_name(sim, property_id) or property_id
        trust = _clamp(record.get("trust"), default=0.0)
        reliability = _clamp(record.get("reliability"), default=0.0)
        fear = _clamp(record.get("fear"), default=0.0)
        heat = _clamp(record.get("heat"), default=0.0)
        resentment = _clamp(record.get("resentment"), default=0.0)
        price = _float(record.get("price_fairness"), 0.0)
        if max(fear, heat, resentment) >= max(trust, reliability, 0.34):
            summary = f"{place} has people talking like it brings trouble"
            sentiment = "negative"
        elif price <= -0.25:
            summary = f"{place} has people grumbling about the prices"
            sentiment = "negative"
        elif max(trust, reliability) >= 0.35:
            summary = f"{place} has a better street read lately"
            sentiment = "positive"
        else:
            summary = f"{place} keeps coming up in street talk"
            sentiment = "neutral"
        social_interest = max(_clamp(queue_row.get("score"), default=0.0), _clamp(record.get("social_interest"), default=0.0))
        remembered = remember_social_knowledge(
            sim,
            actor_eid,
            "business",
            property_id,
            source_kind=record.get("source_kind", ""),
            source_eid=record.get("source_eid"),
            confidence=record.get("confidence", record.get("coherence", 0.5)),
            firsthand=bool(record.get("firsthand", False)),
            propagation_depth=record.get("propagation_depth", 0),
            social_interest=social_interest,
            summary=summary,
            detail=summary,
            tags=tuple(record.get("tags", ()) or ()) + ("business", sentiment),
            refs={
                "property_id": property_id,
                "property_lead_kind": "business_reputation",
                "sentiment": sentiment,
            },
            score=social_interest,
            tick=now,
            source_event=source_event,
        )
        if isinstance(remembered, dict):
            created += 1
    return created


def hydrate_relationship_social_knowledge(sim, actor_eid, *, partner_eid=None, limit=4, source_event="relationship_bond_hydrate"):
    social = sim.ecs.get(NPCSocial).get(actor_eid)
    if not isinstance(social, NPCSocial):
        return 0
    positions = sim.ecs.get(Position)
    actor_pos = positions.get(actor_eid)
    created = 0
    now = _int(getattr(sim, "tick", 0), 0)
    candidates = []
    for other_eid, bond in (social.bonds or {}).items():
        if not isinstance(bond, dict):
            continue
        other_id = _int(other_eid, 0)
        if other_id <= 0:
            continue
        kind = _key(bond.get("kind")) or "friend"
        closeness = _clamp(bond.get("closeness"), default=0.0)
        trust = _clamp(bond.get("trust"), default=0.0)
        if kind not in {"partner", "family", "friend"} and closeness < 0.82:
            continue
        if kind == "friend" and closeness < 0.78:
            continue
        score = closeness * 0.62 + trust * 0.38
        if other_id == _int(partner_eid, -1):
            score += 0.06
        other_pos = positions.get(other_id)
        if actor_pos and other_pos and int(actor_pos.z) == int(other_pos.z):
            distance = abs(int(actor_pos.x) - int(other_pos.x)) + abs(int(actor_pos.y) - int(other_pos.y))
            if distance <= 10:
                score += 0.05
        candidates.append((score, other_id, kind, bond))

    for score, other_id, kind, bond in sorted(candidates, reverse=True)[: max(1, int(limit or 1))]:
        left = min(_int(actor_eid), other_id)
        right = max(_int(actor_eid), other_id)
        subject_key = f"{left}:{right}:{kind}"
        actor_name = _entity_name(sim, actor_eid)
        other_name = _entity_name(sim, other_id)
        if kind == "partner":
            summary = f"{actor_name} and {other_name} are known as partners"
            interest = 0.72
        elif kind == "family":
            summary = f"{actor_name} and {other_name} read like family"
            interest = 0.62
        else:
            summary = f"{actor_name} and {other_name} keep showing up for each other"
            interest = 0.46
        interest = max(interest, min(0.86, score))
        remembered = remember_social_knowledge(
            sim,
            actor_eid,
            "relationship",
            subject_key,
            source_kind="public_bond",
            source_eid=actor_eid,
            confidence=min(0.9, max(0.5, score)),
            firsthand=True,
            propagation_depth=0,
            social_interest=interest,
            summary=summary,
            detail=summary,
            tags=("relationship", kind),
            refs={"actor_eid": _int(actor_eid), "other_eid": other_id, "relationship_kind": kind},
            score=interest,
            tick=now,
            source_event=source_event,
        )
        if isinstance(remembered, dict):
            created += 1
    return created


def hydrate_social_knowledge(sim, actor_eid, *, partner_eid=None, opportunity_rows=(), source_event="social_hydrate"):
    total = 0
    total += hydrate_incident_social_knowledge(sim, actor_eid, source_event=source_event)
    total += hydrate_opportunity_social_knowledge(sim, actor_eid, opportunity_rows, source_event=source_event)
    total += hydrate_business_social_knowledge(sim, actor_eid, source_event=source_event)
    total += hydrate_relationship_social_knowledge(sim, actor_eid, partner_eid=partner_eid, source_event=source_event)
    return total


def _domain_channel(domain):
    if domain == "opportunity":
        return "opportunity"
    return "social"


def _domain_priority(domain, record):
    if domain == "opportunity":
        return "normal"
    if domain == "incident" and _clamp(record.get("social_interest"), default=0.0) >= 0.74:
        return "normal"
    return "low"


def _confidence_phrase(record):
    source = _key(record.get("source_kind"))
    confidence = _clamp(record.get("confidence"), default=0.5)
    if bool(record.get("firsthand", False)) or source in {"witnessed", "public_bond"}:
        return "I saw enough to say"
    if source == "social_rumor" or _int(record.get("propagation_depth"), 0) > 0:
        return "I keep hearing"
    if confidence >= 0.72:
        return "The read is"
    return "Word is"


def social_knowledge_payload_for_record(sim, speaker_eid, partner_eid, tone, record):
    if not isinstance(record, dict):
        return None
    domain = _key(record.get("source_domain"))
    summary = _text(record.get("summary"))
    detail = _text(record.get("detail")) or summary
    if not domain or not summary:
        return None
    confidence_phrase = _confidence_phrase(record)
    summary_lc = summary[:1].lower() + summary[1:] if summary else summary
    quote_options = (
        f"{confidence_phrase} {summary_lc}.",
        f"{summary}. That is the talk right now.",
        f"People are circling the same thing: {summary_lc}.",
    )
    chooser = random.Random(
        f"{getattr(sim, 'seed', 0)}:social-knowledge-quote:{speaker_eid}:{partner_eid}:{getattr(sim, 'tick', 0) // 6}:{tone}:{record.get('key')}"
    )
    quote = quote_options[chooser.randrange(len(quote_options))]
    refs = record.get("refs") if isinstance(record.get("refs"), dict) else {}
    payload = {
        "topic": f"gossip_{domain}",
        "quote": quote,
        "summary": summary,
        "detail": detail,
        "channel": _domain_channel(domain),
        "priority": _domain_priority(domain, record),
        "social_knowledge_key": record.get("key"),
        "source_domain": domain,
        "confidence_hint": _clamp(record.get("confidence"), default=0.5),
    }
    for key in (
        "incident_id",
        "opportunity_id",
        "property_id",
        "property_lead_kind",
        "actor_eid",
        "other_eid",
        "relationship_kind",
    ):
        if refs.get(key) not in (None, ""):
            payload[key] = refs.get(key)
    return payload


def choose_social_knowledge_payload(sim, speaker_eid, partner_eid, relation, tone, *, opportunity_rows=()):
    hydrate_social_knowledge(
        sim,
        speaker_eid,
        partner_eid=partner_eid,
        opportunity_rows=opportunity_rows,
        source_event="social_chatter_hydrate",
    )
    knowledge = social_knowledge_for(sim, speaker_eid, create=False)
    if not isinstance(knowledge, SocialKnowledge):
        return None

    now = _int(getattr(sim, "tick", 0), 0)
    candidates = []
    for queue_row in tuple(getattr(knowledge, "social_queue", ()) or ()):
        key = _text(queue_row.get("key"))
        record = (knowledge.entries or {}).get(key)
        if not isinstance(record, dict):
            continue
        if social_knowledge_incident_spread_suppressed(sim, speaker_eid, record):
            continue
        shared = knowledge.last_shared.get(key)
        if isinstance(shared, dict):
            last_social = _int(shared.get("social"), -10_000)
            if now - last_social < SOCIAL_SHARE_COOLDOWN_TICKS:
                continue
        domain = _key(record.get("source_domain"))
        score = _clamp(queue_row.get("score"), default=0.0)
        score += _clamp(record.get("social_interest"), default=0.0) * 0.65
        score += _clamp(record.get("confidence"), default=0.0) * 0.25
        if domain == "opportunity" and tone == "conspiring":
            score += 0.16
        if domain == "relationship" and _key(relation) in {"partner", "family", "friend"}:
            score += 0.08
        candidates.append((max(0.01, score), key, record))
    if not candidates:
        return None

    chooser = random.Random(
        f"{getattr(sim, 'seed', 0)}:social-knowledge-pick:{speaker_eid}:{partner_eid}:{now // 6}:{relation}:{tone}"
    )
    total = sum(score for score, _key_value, _record in candidates)
    pick = chooser.uniform(0.0, total)
    running = 0.0
    selected_key = candidates[-1][1]
    selected = candidates[-1][2]
    for score, key, record in candidates:
        running += score
        if pick <= running:
            selected_key = key
            selected = record
            break
    payload = social_knowledge_payload_for_record(sim, speaker_eid, partner_eid, tone, selected)
    if payload:
        knowledge.mark_shared(selected_key, tick=now, channel="social")
    return payload
