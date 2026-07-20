"""Revision-aware runtime cache for facts derived from simulation truth.

The simulation has many legitimate consumers of the same expensive question.
This module lets the owner of a truth expose a small revision counter while
readers materialize reusable answers against that revision.  Cached answers are
runtime accelerators only: they are deliberately excluded from save data and
can always be rebuilt from canonical state.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


DEFAULT_NAMESPACE_LIMIT = 4_096
_MISSING = object()


def _clean_name(value, *, label):
    name = str(value or "").strip().lower()
    if not name:
        raise ValueError(f"derived fact {label} must not be empty")
    return name


def derived_fact_state(sim):
    """Return the simulation-local, noncanonical derived-fact runtime."""

    state = getattr(sim, "_derived_fact_state", None)
    if not isinstance(state, dict):
        state = {}
        sim._derived_fact_state = state
    if not isinstance(state.get("revisions"), dict):
        state["revisions"] = {}
    if not isinstance(state.get("namespaces"), dict):
        state["namespaces"] = {}
    if not isinstance(state.get("stats"), dict):
        state["stats"] = {}
    return state


def derived_fact_revision(sim, domain):
    """Return the current revision for one canonical truth domain."""

    name = _clean_name(domain, label="domain")
    try:
        return max(0, int(derived_fact_state(sim)["revisions"].get(name, 0) or 0))
    except (TypeError, ValueError):
        return 0


def mark_derived_fact_changed(sim, domain):
    """Advance a truth-domain revision after its canonical state mutates."""

    name = _clean_name(domain, label="domain")
    state = derived_fact_state(sim)
    revision = derived_fact_revision(sim, name) + 1
    state["revisions"][name] = revision
    return revision


def derived_fact_revision_signature(sim, domains: Iterable[str] = ()):
    """Return a stable signature for the requested truth domains."""

    return tuple(
        (name, derived_fact_revision(sim, name))
        for name in (_clean_name(domain, label="domain") for domain in tuple(domains or ()))
    )


def _namespace_state(sim, namespace, *, max_entries):
    name = _clean_name(namespace, label="namespace")
    state = derived_fact_state(sim)
    namespaces = state["namespaces"]
    namespace_state = namespaces.get(name)
    if not isinstance(namespace_state, dict):
        namespace_state = {"entries": {}, "max_entries": int(max_entries)}
        namespaces[name] = namespace_state
    entries = namespace_state.get("entries")
    if not isinstance(entries, dict):
        entries = {}
        namespace_state["entries"] = entries
    namespace_state["max_entries"] = max(1, int(max_entries))
    return name, namespace_state, entries


def _note_stat(state, namespace, field):
    stats = state["stats"].setdefault(namespace, {})
    stats[field] = int(stats.get(field, 0) or 0) + 1


def cached_derived_fact(
    sim,
    namespace,
    key,
    builder: Callable[[], Any],
    *,
    domains: Iterable[str] = (),
    signature: Iterable[Any] = (),
    tick_scoped=False,
    max_entries=DEFAULT_NAMESPACE_LIMIT,
):
    """Return one materialized fact until one of its dependencies changes.

    ``domains`` names canonical truth owners whose revisions are advanced at
    mutation sites. ``signature`` carries immutable query inputs or external
    revision tokens. ``tick_scoped`` is appropriate for facts whose answer can
    change simply because simulation time advanced.

    Empty tuples, ``None``, ``False``, and zero are cached normally.
    """

    if not callable(builder):
        raise TypeError("derived fact builder must be callable")
    name = _clean_name(namespace, label="namespace")
    state = derived_fact_state(sim)
    namespace_state = state["namespaces"].get(name)
    if not isinstance(namespace_state, dict):
        namespace_state = {"entries": {}, "max_entries": int(max_entries)}
        state["namespaces"][name] = namespace_state
    entries = namespace_state.get("entries")
    if not isinstance(entries, dict):
        entries = {}
        namespace_state["entries"] = entries
    namespace_state["max_entries"] = max(1, int(max_entries))
    revisions = state["revisions"]
    domain_signature = []
    for domain in tuple(domains or ()):
        domain_name = _clean_name(domain, label="domain")
        try:
            revision = max(0, int(revisions.get(domain_name, 0) or 0))
        except (TypeError, ValueError):
            revision = 0
        domain_signature.append((domain_name, revision))
    dependency_signature = (
        tuple(domain_signature),
        tuple(signature or ()),
        int(getattr(sim, "tick", 0) or 0) if tick_scoped else None,
    )
    cached = entries.get(key, _MISSING)
    if cached is not _MISSING and isinstance(cached, tuple) and len(cached) == 2:
        if cached[0] == dependency_signature:
            _note_stat(state, name, "hits")
            return cached[1]

    _note_stat(state, name, "misses")
    value = builder()
    limit = max(1, int(namespace_state.get("max_entries", max_entries) or max_entries))
    if key not in entries and len(entries) >= limit:
        entries.pop(next(iter(entries)))
        _note_stat(state, name, "evictions")
    entries[key] = (dependency_signature, value)
    return value


def invalidate_derived_facts(sim, namespace=None, *, key=_MISSING):
    """Explicitly discard one query, one namespace, or all materialized facts."""

    state = derived_fact_state(sim)
    namespaces = state["namespaces"]
    if namespace is None:
        namespaces.clear()
        return
    name = _clean_name(namespace, label="namespace")
    namespace_state = namespaces.get(name)
    if not isinstance(namespace_state, dict):
        return
    entries = namespace_state.get("entries")
    if not isinstance(entries, dict):
        return
    if key is _MISSING:
        entries.clear()
    else:
        entries.pop(key, None)


def derived_fact_stats(sim):
    """Return a detached diagnostic snapshot of cache activity."""

    state = derived_fact_state(sim)
    result = {}
    for namespace, row in state["stats"].items():
        if not isinstance(row, dict):
            continue
        namespace_state = state["namespaces"].get(namespace, {})
        entries = namespace_state.get("entries", {}) if isinstance(namespace_state, dict) else {}
        result[namespace] = {
            "hits": int(row.get("hits", 0) or 0),
            "misses": int(row.get("misses", 0) or 0),
            "evictions": int(row.get("evictions", 0) or 0),
            "entries": len(entries) if isinstance(entries, dict) else 0,
        }
    return result


__all__ = [
    "cached_derived_fact",
    "derived_fact_revision",
    "derived_fact_revision_signature",
    "derived_fact_state",
    "derived_fact_stats",
    "invalidate_derived_facts",
    "mark_derived_fact_changed",
]
