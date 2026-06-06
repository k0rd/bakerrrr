"""Runtime criminal drive for solo opportunism, crew jobs, and recruitment."""

from __future__ import annotations

from engine.events import Event
from engine.systems import System
from game.components import AI, CriminalDriveState, OrganizationCrimePlans, OrganizationProfile, Position, Vitality
from game.justice_runtime import justice_snapshot
from game.organization_reputation import organization_instability_profile
from game.organizations import (
    actor_assigned_crime_plans,
    actor_org_memberships,
    advance_organization_crime_plan,
    cancel_organization_crime_plan,
    crime_plan_method_for_family,
    crime_plan_method_label,
    organization_crime_plans,
    organization_policy_snapshot,
    organization_profile,
    record_organization_crime_plan,
)
from game.property_runtime import property_focus_position as _property_focus_position
from game.system_support.actor_runtime import _detail_tick_allowed, _entity_is_downed
from game.system_support.criminal_drive_runtime import (
    CRIMINAL_FAMILIES,
    active_crime_plan_actor_index,
    active_plan_for_actor,
    actor_criminal_memberships,
    choose_crime_target,
    clear_criminal_drive_activity,
    criminal_drive_state,
    criminal_affiliation_targets,
    update_criminal_drive_state,
)
from game.system_support.entity_naming import _entity_display_name
from game.system_support.interaction_ordering import _manhattan


ACTOR_REFRESH_INTERVAL = 8
PLAN_REFRESH_INTERVAL = 36
PLAN_EXECUTION_BUFFER = 12
PLAN_EXPIRY_TICKS = 120


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _text(value):
    return str(value or "").strip()


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def _profile_tags(profile):
    return {
        _text(tag).lower()
        for tag in getattr(profile, "tags", ())
        if _text(tag)
    }


def _organization_family(sim, organization_eid):
    policy = organization_policy_snapshot(sim, organization_eid=organization_eid)
    if isinstance(policy, dict):
        family = _text(policy.get("family")).lower()
        if family:
            return family
    profile = organization_profile(sim, organization_eid)
    tags = _profile_tags(profile)
    for family_tag in ("street_gang", "criminal_network", "criminal", "labor_union", "trade_guild"):
        if family_tag in tags:
            return family_tag
    return _text(getattr(profile, "kind", "")).lower() or "other"


def _organization_is_vigilante(sim, organization_eid):
    profile = organization_profile(sim, organization_eid)
    return "gang_posture:vigilante" in _profile_tags(profile)


def _property_contains(prop, x, y, z):
    if not isinstance(prop, dict):
        return False
    try:
        if int(prop.get("z", 0) or 0) != int(z):
            return False
    except (TypeError, ValueError):
        return False
    metadata = prop.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    footprint = metadata.get("footprint")
    if not isinstance(footprint, dict):
        return False
    try:
        left = int(footprint.get("left"))
        right = int(footprint.get("right"))
        top = int(footprint.get("top"))
        bottom = int(footprint.get("bottom"))
        x = int(x)
        y = int(y)
    except (TypeError, ValueError):
        return False
    return left <= x <= right and top <= y <= bottom


def _plan_kind_priority(kind):
    key = _text(kind).lower()
    if key == "burglary":
        return 0
    if key == "petty_theft":
        return 1
    if key == "covert_sale":
        return 2
    if key == "fence_run":
        return 3
    return 4


def _plan_event_fields(plan):
    if not isinstance(plan, dict):
        return {}
    return {
        "plan_method_key": _text(plan.get("method_key")) or None,
        "plan_method_label": _text(plan.get("method_label")) or None,
        "plan_stage": _text(plan.get("stage")).lower() or None,
    }


class CriminalDriveSystem(System):
    def __init__(self, sim):
        super().__init__(sim)
        self._actor_due_by_tick = {}
        self._actor_due_membership = {}
        self._next_actor_due_resync_tick = -1
        self.sim.events.subscribe("npc_crime_attempt_resolved", self.on_crime_attempt_resolved)
        self.sim.events.subscribe("item_stolen", self.on_item_stolen)
        self.sim.events.subscribe("actor_detained", self.on_actor_detained)
        self.sim.events.subscribe("npc_custody_resolved", self.on_npc_custody_resolved)

    def _schedule_actor_refresh(self, actor_eid, due_tick):
        actor_eid = _safe_int(actor_eid, default=0)
        if actor_eid <= 0:
            return None
        due_tick = max(0, _safe_int(due_tick, default=0))
        old_tick = self._actor_due_membership.get(actor_eid)
        if old_tick == due_tick:
            return due_tick
        if old_tick is not None:
            old_bucket = self._actor_due_by_tick.get(old_tick)
            if isinstance(old_bucket, set):
                old_bucket.discard(actor_eid)
                if not old_bucket:
                    self._actor_due_by_tick.pop(old_tick, None)
        self._actor_due_by_tick.setdefault(due_tick, set()).add(actor_eid)
        self._actor_due_membership[actor_eid] = due_tick
        return due_tick

    def _pop_due_actor_refreshes(self, *, current_tick):
        tick = _safe_int(current_tick, default=0)
        ready = set()
        for due_tick in sorted(raw for raw in tuple(self._actor_due_by_tick.keys()) if int(raw) <= tick):
            bucket = self._actor_due_by_tick.pop(due_tick, set())
            for actor_eid in tuple(bucket or ()):
                if self._actor_due_membership.get(actor_eid) == due_tick:
                    self._actor_due_membership.pop(actor_eid, None)
                    ready.add(actor_eid)
        return tuple(sorted(ready))

    def _resync_actor_refresh_due(self, *, current_tick):
        tick = _safe_int(current_tick, default=0)
        if self._next_actor_due_resync_tick >= 0 and tick < self._next_actor_due_resync_tick:
            return
        ais = self.sim.ecs.get(AI)
        live_actor_ids = set()
        for actor_eid, ai in tuple(ais.items()):
            if _text(getattr(ai, "role", "")).lower() == "wildlife":
                continue
            actor_eid = int(actor_eid)
            live_actor_ids.add(actor_eid)
            if actor_eid in self._actor_due_membership:
                continue
            offset = (ACTOR_REFRESH_INTERVAL - ((tick + actor_eid) % ACTOR_REFRESH_INTERVAL)) % ACTOR_REFRESH_INTERVAL
            self._schedule_actor_refresh(actor_eid, tick + offset)
        stale = [
            actor_eid
            for actor_eid in tuple(self._actor_due_membership.keys())
            if actor_eid not in live_actor_ids
        ]
        for actor_eid in stale:
            old_tick = self._actor_due_membership.pop(actor_eid, None)
            if old_tick is None:
                continue
            bucket = self._actor_due_by_tick.get(old_tick)
            if isinstance(bucket, set):
                bucket.discard(actor_eid)
                if not bucket:
                    self._actor_due_by_tick.pop(old_tick, None)
        self._next_actor_due_resync_tick = tick + ACTOR_REFRESH_INTERVAL

    def _actor_ready(self, eid, pos):
        if pos is None or _entity_is_downed(self.sim, eid):
            return False
        if not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=3):
            return False
        return True

    def _organization_candidate_members(self, organization_eid):
        profile = organization_profile(self.sim, organization_eid)
        if profile is None:
            return ()
        positions = self.sim.ecs.get(Position)
        rows = []
        for actor_eid in tuple(getattr(profile, "member_eids", ()) or ()):
            pos = positions.get(actor_eid)
            if pos is None or not self._actor_ready(actor_eid, pos):
                continue
            if justice_snapshot(self.sim, actor_eid).get("in_custody"):
                continue
            for membership in actor_org_memberships(self.sim, actor_eid, active_only=True):
                if _safe_int(membership.get("organization_eid"), default=0) != int(organization_eid):
                    continue
                rows.append(
                    {
                        "actor_eid": int(actor_eid),
                        "position": pos,
                        "authority_rank": _safe_int(membership.get("authority_rank"), default=70),
                        "role": _text(membership.get("role")).lower() or "member",
                        "title": _text(membership.get("title")),
                        "site_property_id": _text(membership.get("site_property_id")) or None,
                    }
                )
                break
        rows.sort(
            key=lambda row: (
                int(row.get("authority_rank", 70)),
                0 if _text(row.get("role")) in {"owner", "leader", "manager"} else 1,
                int(row.get("actor_eid", 0)),
            )
        )
        return tuple(rows)

    def _organization_branch_sites(self, organization_eid):
        profile = organization_profile(self.sim, organization_eid)
        if profile is None:
            return ()
        props = []
        seen = set()
        for property_id in tuple(getattr(profile, "site_property_ids", ()) or ()):
            prop = self.sim.properties.get(property_id)
            if not isinstance(prop, dict):
                continue
            if property_id in seen:
                continue
            seen.add(property_id)
            props.append(prop)
        props.sort(key=lambda prop: _text(prop.get("id")))
        return tuple(props)

    def _linked_staging_property(self, organization_eid):
        for prop in self._organization_branch_sites(organization_eid):
            prop_id = _text(prop.get("id"))
            for membership in organization_crime_plans(self.sim, organization_eid):
                if _text(membership.get("staging_property_id")) == prop_id:
                    return prop
            metadata = prop.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            if _text(metadata.get("hidden_contact_kind")):
                return prop
        props = self._organization_branch_sites(organization_eid)
        return props[0] if props else None

    def _pick_plan_kind(self, organization_eid, *, instability):
        family = _organization_family(self.sim, organization_eid)
        heat = _safe_float((instability or {}).get("heat_pressure"), default=0.0)
        pressure = _safe_float((instability or {}).get("operational_pressure"), default=0.0)
        if family == "criminal_network":
            return "fence_run" if heat >= 0.38 else "covert_sale"
        if family == "street_gang":
            return "petty_theft" if heat >= 0.42 else "burglary" if pressure >= 0.48 else "petty_theft"
        return "petty_theft"

    def _build_plan_row(self, organization_eid, *, current_tick):
        if _organization_is_vigilante(self.sim, organization_eid):
            return None
        family = _organization_family(self.sim, organization_eid)
        if family not in CRIMINAL_FAMILIES:
            return None
        members = self._organization_candidate_members(organization_eid)
        if not members:
            return None
        instability = organization_instability_profile(self.sim, organization_eid=organization_eid, ensure=True)
        pressure = _safe_float((instability or {}).get("operational_pressure"), default=0.0)
        if family == "criminal_network":
            min_pressure = 0.16
        else:
            min_pressure = 0.28
        if pressure < min_pressure and len(members) < 2:
            return None
        kind = self._pick_plan_kind(organization_eid, instability=instability)
        method_key = crime_plan_method_for_family(family, kind)
        required = 2 if kind == "burglary" else 1
        if len(members) < required:
            return None
        leader = members[0]
        target = choose_crime_target(self.sim, leader["actor_eid"], plan_kind=kind)
        staging_prop = self._linked_staging_property(organization_eid)
        if kind in {"petty_theft", "burglary"} and not isinstance(target, dict):
            return None
        if kind in {"covert_sale", "fence_run"} and staging_prop is None:
            return None
        target_property_id = _text((target or {}).get("property_id")) or _text((staging_prop or {}).get("id")) or None
        if not target_property_id:
            return None
        assigned = tuple(int(row["actor_eid"]) for row in members[: max(required, min(3, len(members)))])
        plan_tick = int(current_tick // PLAN_REFRESH_INTERVAL)
        plan_key = f"crime_plan:{organization_eid}:{plan_tick}:{kind}:{target_property_id}"
        target_prop = self.sim.properties.get(target_property_id)
        disposal_property_id = _text((staging_prop or {}).get("id")) or target_property_id
        return {
            "organization_eid": int(organization_eid),
            "plan_key": plan_key,
            "kind": kind,
            "stage": "rendezvous",
            "method_key": method_key,
            "method_label": crime_plan_method_label(method_key, kind=kind),
            "leader_eid": int(leader["actor_eid"]),
            "assigned_member_eids": assigned,
            "target_property_id": target_property_id,
            "target_building_id": _text(((target_prop or {}).get("metadata", {}) or {}).get("building_id")) or None,
            "staging_property_id": _text((staging_prop or {}).get("id")) or target_property_id,
            "disposal_property_id": disposal_property_id,
            "created_tick": int(current_tick),
            "execute_after_tick": int(current_tick + PLAN_EXECUTION_BUFFER),
            "expires_tick": int(current_tick + PLAN_EXPIRY_TICKS),
            "required_member_count": int(required),
            "source_pressure": float(pressure),
            "summary": f"{kind.replace('_', ' ')} plan forming around {(_text((target_prop or {}).get('name')) or target_property_id)}",
        }

    def _members_at_property(self, actor_ids, property_id):
        prop = self.sim.properties.get(_text(property_id))
        if not isinstance(prop, dict):
            return set()
        positions = self.sim.ecs.get(Position)
        present = set()
        for actor_eid in tuple(actor_ids or ()):
            pos = positions.get(actor_eid)
            if pos is None:
                continue
            if _property_contains(prop, pos.x, pos.y, pos.z):
                present.add(int(actor_eid))
        return present

    def _plan_target_position(self, plan):
        property_id = _text(plan.get("target_property_id"))
        prop = self.sim.properties.get(property_id)
        if not isinstance(prop, dict):
            return None
        return _property_focus_position(prop)

    def _advance_org_plans(self, organization_eid, *, current_tick):
        for plan in organization_crime_plans(self.sim, organization_eid, include_inactive=False, current_tick=current_tick):
            plan_key = _text(plan.get("plan_key"))
            stage = _text(plan.get("stage")).lower()
            assigned = tuple(int(eid) for eid in tuple(plan.get("assigned_member_eids", ()) or ()))
            leader_eid = _safe_int(plan.get("leader_eid"), default=0)
            all_actor_ids = tuple({leader_eid, *assigned} - {0})
            if stage in {"cancelled", "resolved"}:
                continue
            if _safe_int(plan.get("expires_tick"), default=current_tick + 1) < int(current_tick):
                cancel_organization_crime_plan(
                    self.sim,
                    organization_eid,
                    plan_key,
                    result="expired",
                    summary="crew plan expired before it came together",
                )
                continue
            if stage == "rendezvous":
                if int(current_tick) < _safe_int(plan.get("execute_after_tick"), default=0):
                    continue
                present = self._members_at_property(all_actor_ids, plan.get("staging_property_id"))
                if len(present) >= max(1, _safe_int(plan.get("required_member_count"), default=1)):
                    advance_organization_crime_plan(
                        self.sim,
                        organization_eid,
                        plan_key,
                        stage="executing",
                        summary="crew has enough hands together to move on the target",
                    )
                    continue
            if stage == "executing":
                if not all_actor_ids:
                    cancel_organization_crime_plan(
                        self.sim,
                        organization_eid,
                        plan_key,
                        result="no_members",
                        summary="no crew members stayed available for the job",
                    )
                    continue
                if not any(self.sim.ecs.get(Position).get(actor_eid) is not None for actor_eid in all_actor_ids):
                    continue
            if stage == "disposing":
                if int(current_tick) >= _safe_int(plan.get("execute_after_tick"), default=current_tick) + 12:
                    advance_organization_crime_plan(
                        self.sim,
                        organization_eid,
                        plan_key,
                        stage="cooldown",
                        result="resolved",
                        resolved_tick=int(current_tick),
                        summary="crew has cleared the handoff and gone quiet for now",
                    )
                    continue
            if stage == "cooldown":
                if int(current_tick) >= _safe_int(plan.get("execute_after_tick"), default=current_tick) + 24:
                    advance_organization_crime_plan(
                        self.sim,
                        organization_eid,
                        plan_key,
                        stage="resolved",
                        result=_text(plan.get("result")) or "resolved",
                        resolved_tick=int(current_tick),
                        summary=_text(plan.get("summary")) or "crew plan wrapped cleanly",
                    )

    def _seed_org_plans(self, *, current_tick):
        profiles = self.sim.ecs.get(OrganizationProfile)
        for organization_eid in tuple(profiles.keys()):
            family = _organization_family(self.sim, organization_eid)
            if family not in CRIMINAL_FAMILIES or _organization_is_vigilante(self.sim, organization_eid):
                continue
            active = organization_crime_plans(self.sim, organization_eid, include_inactive=False, current_tick=current_tick)
            if any(_text(row.get("stage")).lower() in {"rendezvous", "executing", "disposing"} for row in active):
                continue
            plan_row = self._build_plan_row(organization_eid, current_tick=current_tick)
            if not isinstance(plan_row, dict):
                continue
            record_organization_crime_plan(self.sim, **plan_row)

    def _advance_all_active_plans(self, *, current_tick):
        plan_components = self.sim.ecs.get(OrganizationCrimePlans)
        for organization_eid in tuple(plan_components.keys()):
            family = _organization_family(self.sim, organization_eid)
            if family not in CRIMINAL_FAMILIES or _organization_is_vigilante(self.sim, organization_eid):
                continue
            self._advance_org_plans(organization_eid, current_tick=current_tick)

    def _cancel_actor_activity(self, actor_eid, *, reason):
        state = criminal_drive_state(self.sim, actor_eid, create=False)
        if state is None:
            return
        state.cooldown_until_tick = max(_safe_int(getattr(self.sim, "tick", 0), default=0) + 32, _safe_int(state.cooldown_until_tick, default=0))
        state.last_failure_tick = int(getattr(self.sim, "tick", 0))
        clear_criminal_drive_activity(state)
        for row in actor_assigned_crime_plans(self.sim, actor_eid, include_inactive=False, current_tick=getattr(self.sim, "tick", 0)):
            cancel_organization_crime_plan(
                self.sim,
                _safe_int(row.get("organization_eid"), default=0),
                row.get("plan_key"),
                result=reason,
                summary=f"{_entity_display_name(self.sim, actor_eid, title_case=True) or 'A crew hand'} dropped out of the job",
            )

    def on_actor_detained(self, event):
        actor_eid = _safe_int(event.data.get("eid"), default=0)
        if actor_eid > 0:
            self._cancel_actor_activity(actor_eid, reason="detained")

    def on_npc_custody_resolved(self, event):
        actor_eid = _safe_int(event.data.get("eid"), default=0)
        state = criminal_drive_state(self.sim, actor_eid, create=False)
        if state is None:
            return
        state.cooldown_until_tick = max(_safe_int(getattr(self.sim, "tick", 0), default=0) + 40, _safe_int(state.cooldown_until_tick, default=0))
        clear_criminal_drive_activity(state)

    def _mark_attempt_result(self, actor_eid, *, success, reason="", plan_key=None):
        state = criminal_drive_state(self.sim, actor_eid, create=True)
        tick = _safe_int(getattr(self.sim, "tick", 0), default=0)
        state.last_attempt_tick = tick
        state.cooldown_until_tick = tick + (18 if success else 28)
        if success:
            state.last_success_tick = tick
        else:
            state.last_failure_tick = tick
        if plan_key:
            state.current_plan_key = _text(plan_key) or None
        plan = active_plan_for_actor(self.sim, actor_eid, current_tick=tick) if plan_key else None
        self.sim.emit(
            Event(
                "npc_crime_attempt_resolved",
                npc_eid=actor_eid,
                success=bool(success),
                reason=_text(reason),
                plan_key=_text(plan_key) or None,
                **_plan_event_fields(plan),
                x=None,
                y=None,
                z=None,
            )
        )

    def on_item_stolen(self, event):
        actor_eid = _safe_int(event.data.get("offender_eid"), default=0)
        if actor_eid <= 0:
            return
        plan = active_plan_for_actor(self.sim, actor_eid, current_tick=getattr(self.sim, "tick", 0))
        self._mark_attempt_result(
            actor_eid,
            success=True,
            reason="item_stolen",
            plan_key=_text((plan or {}).get("plan_key")),
        )

    def on_crime_attempt_resolved(self, event):
        actor_eid = _safe_int(event.data.get("npc_eid"), default=0)
        if actor_eid <= 0:
            return
        success = bool(event.data.get("success"))
        reason = _text(event.data.get("reason"))
        plan_key = _text(event.data.get("plan_key"))
        state = criminal_drive_state(self.sim, actor_eid, create=True)
        tick = _safe_int(getattr(self.sim, "tick", 0), default=0)
        state.last_attempt_tick = tick
        state.cooldown_until_tick = tick + (18 if success else 28)
        if success:
            state.last_success_tick = tick
        else:
            state.last_failure_tick = tick
        if plan_key:
            state.current_plan_key = plan_key
        if not plan_key:
            return
        plan = active_plan_for_actor(self.sim, actor_eid, current_tick=tick)
        if not isinstance(plan, dict) or _text(plan.get("plan_key")) != plan_key:
            return
        org_eid = _safe_int(plan.get("organization_eid"), default=0)
        if org_eid <= 0:
            return
        if success:
            if _text(plan.get("stage")).lower() == "executing":
                advance_organization_crime_plan(
                    self.sim,
                    org_eid,
                    plan_key,
                    stage="disposing",
                    execute_after_tick=tick,
                    summary="crew has something in hand and is clearing the site",
                )
        else:
            stage = _text(plan.get("stage")).lower()
            if stage in {"disposing", "cooldown", "resolved"} and reason in {"no_loot", "cased_target"}:
                return
            cancel_organization_crime_plan(
                self.sim,
                org_eid,
                plan_key,
                result=reason or "failed",
                summary=f"{_entity_display_name(self.sim, actor_eid, title_case=True) or 'A crew hand'} washed out on the job",
            )

    def _refresh_actor_states(self, *, current_tick):
        self._resync_actor_refresh_due(current_tick=current_tick)
        ais = self.sim.ecs.get(AI)
        positions = self.sim.ecs.get(Position)
        due_actor_ids = self._pop_due_actor_refreshes(current_tick=current_tick)
        if not due_actor_ids:
            return
        active_plan_index = active_crime_plan_actor_index(self.sim, current_tick=current_tick)
        for actor_eid in due_actor_ids:
            ai = ais.get(actor_eid)
            if ai is None:
                continue
            if _text(getattr(ai, "role", "")).lower() == "wildlife":
                continue
            pos = positions.get(actor_eid)
            try:
                if not self._actor_ready(actor_eid, pos):
                    continue
                if justice_snapshot(self.sim, actor_eid).get("in_custody"):
                    self._cancel_actor_activity(actor_eid, reason="custody")
                    continue
                actor_plans = active_plan_index.get(int(actor_eid), ())
                active_plan = actor_plans[0] if actor_plans else None
                state = update_criminal_drive_state(
                    self.sim,
                    actor_eid,
                    current_tick=current_tick,
                    active_plan=active_plan,
                )
                if state is None:
                    continue
            finally:
                if actor_eid in ais and _text(getattr(ai, "role", "")).lower() != "wildlife":
                    self._schedule_actor_refresh(actor_eid, int(current_tick) + ACTOR_REFRESH_INTERVAL)

    def update(self):
        tick = _safe_int(getattr(self.sim, "tick", 0), default=0)
        self._refresh_actor_states(current_tick=tick)
        self._advance_all_active_plans(current_tick=tick)
        if tick % PLAN_REFRESH_INTERVAL == 0:
            self._seed_org_plans(current_tick=tick)


__all__ = ["CriminalDriveSystem"]
