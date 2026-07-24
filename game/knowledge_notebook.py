"""Player-facing notification helpers for durable notebook knowledge.

Knowledge producers should keep owning the facts they discover.  This module
owns the smaller, shared question of whether a mutation is meaningful enough
to teach the player that the fact became durable and where it can be found.
"""

from __future__ import annotations

from collections.abc import Mapping

from engine.events import Event
from game.action_bindings import action_binding_label, default_control_bindings


PROPERTY_CONFIDENCE_BANDS = (0.5, 0.75, 0.9)
PERSON_STANDING_BANDS = (0.34, 0.67)


def _text(value):
    return str(value or "").strip()


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _band(value, thresholds):
    score = _float(value)
    return sum(1 for threshold in tuple(thresholds or ()) if score >= float(threshold))


def notebook_binding_label(sim, *, bindings=None):
    """Return the live notebook action label, falling back to the default key."""

    if not isinstance(bindings, Mapping):
        bindings = getattr(sim, "control_bindings", None)
    if not isinstance(bindings, Mapping):
        bindings = default_control_bindings()
    label = action_binding_label(bindings, "notebooks")
    parts = tuple(part.strip() for part in str(label).split("/") if part.strip())
    if len(parts) == 2 and parts[0].casefold() == parts[1].casefold():
        return parts[0].upper()
    return label


def emit_notebook_knowledge_update(
    sim,
    viewer_eid,
    *,
    notebook_kind,
    subject_id,
    subject_name,
    change_kind,
    significance="major",
    hidden=False,
):
    """Emit one source-independent notification for a durable knowledge change."""

    if sim is None or viewer_eid is None:
        return False
    notebook_kind = _text(notebook_kind).lower()
    change_kind = _text(change_kind).lower()
    significance = _text(significance).lower() or "major"
    if not notebook_kind or not change_kind:
        return False
    sim.emit(Event(
        "knowledge_notebook_updated",
        eid=viewer_eid,
        notebook_kind=notebook_kind,
        subject_id=_text(subject_id),
        subject_name=_text(subject_name),
        change_kind=change_kind,
        significance="major" if significance == "major" else "minor",
        hidden=bool(hidden),
    ))
    return True


def note_property_notebook_mutation(
    sim,
    viewer_eid,
    prop,
    *,
    before=None,
    after=None,
    hidden_before=False,
    hidden_after=False,
):
    """Classify and announce a meaningful locations-notebook mutation.

    A new place, a public/hidden reclassification, a new kind of actionable
    lead, an unknown-to-known location anchor, or a confidence refinement can
    all change how the player navigates the world. Presentation keeps every
    real locations mutation in the default log; this classifier still keeps
    the mutation label and significance useful to other consumers.
    """

    if not isinstance(prop, Mapping) or not isinstance(after, Mapping):
        return False
    before = dict(before) if isinstance(before, Mapping) else None
    hidden_before = bool(hidden_before)
    hidden_after = bool(hidden_after)

    if before is None:
        change_kind = "recorded"
        significance = "major"
    elif hidden_before != hidden_after:
        change_kind = "refiled"
        significance = "major"
    else:
        prior_kind = _text(before.get("lead_kind")).lower()
        next_kind = _text(after.get("lead_kind")).lower()
        prior_confidence = _float(before.get("confidence"))
        next_confidence = _float(after.get("confidence"))
        confidence_band_changed = _band(prior_confidence, PROPERTY_CONFIDENCE_BANDS) != _band(
            next_confidence,
            PROPERTY_CONFIDENCE_BANDS,
        )
        lead_kind_changed = prior_kind != next_kind and bool(next_kind)
        source_changed = before.get("source_eid") != after.get("source_eid")
        ownership_changed = any((
            before.get("owner_eid") != after.get("owner_eid"),
            before.get("owner_tag") != after.get("owner_tag"),
        ))
        anchor_changed = any((
            bool(before.get("anchored")) != bool(after.get("anchored")),
            _text(before.get("anchor_kind")).lower() != _text(after.get("anchor_kind")).lower(),
        ))
        confidence_improved = next_confidence > prior_confidence + 0.001
        if lead_kind_changed or confidence_band_changed or ownership_changed or anchor_changed:
            change_kind = "updated"
            significance = "major"
        elif source_changed or confidence_improved:
            change_kind = "updated"
            significance = "minor"
        else:
            return False

    property_id = _text(prop.get("id"))
    property_name = _text(prop.get("name")) or property_id or "a location"
    return emit_notebook_knowledge_update(
        sim,
        viewer_eid,
        notebook_kind="locations",
        subject_id=property_id,
        subject_name=property_name,
        change_kind=change_kind,
        significance=significance,
        hidden=hidden_after,
    )


def _benefits(entry):
    if not isinstance(entry, Mapping):
        return set()
    return {
        _text(value).lower()
        for value in tuple(entry.get("benefits", ()) or ())
        if _text(value)
    }


def _person_name(entry):
    if not isinstance(entry, Mapping):
        return ""
    benefits = _benefits(entry)
    if "known_name" not in benefits and not bool(entry.get("introduced")):
        return ""
    snapshot = entry.get("identity_snapshot")
    if not isinstance(snapshot, Mapping):
        return ""
    return _text(snapshot.get("personal_name")) or _text(snapshot.get("common_name"))


def note_person_notebook_mutation(sim, viewer_eid, person_eid, *, before=None, after=None):
    """Classify and announce a durable people-notebook mutation."""

    if not isinstance(after, Mapping):
        return False
    before = dict(before) if isinstance(before, Mapping) else None
    after = dict(after)
    prior_benefits = _benefits(before)
    next_benefits = _benefits(after)
    prior_name = _person_name(before)
    next_name = _person_name(after)

    if before is None:
        change_kind = "recorded"
        significance = "major"
    elif not prior_name and next_name:
        change_kind = "identified"
        significance = "major"
    else:
        connection_changed = any((
            before.get("relation_kind") != after.get("relation_kind"),
            before.get("property_id") != after.get("property_id"),
            bool(before.get("introduced")) != bool(after.get("introduced")),
            bool(before.get("met_directly")) != bool(after.get("met_directly")),
        ))
        identity_changed = before.get("identity_snapshot") != after.get("identity_snapshot")
        benefits_changed = next_benefits != prior_benefits
        standing_changed = _float(after.get("standing")) > _float(before.get("standing")) + 0.001
        standing_band_changed = _band(before.get("standing"), PERSON_STANDING_BANDS) != _band(
            after.get("standing"),
            PERSON_STANDING_BANDS,
        )
        if connection_changed or identity_changed or benefits_changed or standing_band_changed:
            change_kind = "updated"
            significance = "major"
        elif standing_changed:
            change_kind = "updated"
            significance = "minor"
        else:
            return False

    subject_name = next_name
    if not subject_name:
        subject_name = "someone you met" if bool(after.get("met_directly")) else "an unknown person"
    return emit_notebook_knowledge_update(
        sim,
        viewer_eid,
        notebook_kind="people",
        subject_id=person_eid,
        subject_name=subject_name,
        change_kind=change_kind,
        significance=significance,
    )


__all__ = [
    "emit_notebook_knowledge_update",
    "notebook_binding_label",
    "note_person_notebook_mutation",
    "note_property_notebook_mutation",
]
