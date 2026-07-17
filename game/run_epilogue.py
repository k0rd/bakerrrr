#!/usr/bin/env python3
"""Run epilogue ledger and post-run narration for BAKERRRR.

This module keeps a small structured ledger of interesting run facts while the
simulation is active, then appends a readable "what happened / what the city
remembered" section to the existing post-run summary when a run concludes.

The system is deliberately conservative: it listens to existing events, records
facts, and renders summary text. It does not change gameplay state.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from engine.systems import System
from game.components import (
    CreatureIdentity,
    FinancialProfile,
    IncidentKnowledge,
    Inventory,
    PlayerAssets,
    Position,
    StatusEffects,
    Vitality,
    WeaponLoadout,
)
from game.items import ITEM_CATALOG
from game.justice_runtime import justice_summary_rows
from game.organization_reputation import top_organization_snapshots
from game.property_runtime import property_covering as _property_covering
from game.run_echoes import archive_run_echoes
from game.run_rewards import export_success_reward_bundle
from game.run_pressure import pressure_snapshot
from game.system_support.entity_naming import _display_label_phrase, _entity_display_name, _entity_display_phrase
from game.weapons import weapon_by_id

try:  # Incident runtime is present in current BAKERRRR, but keep this module soft.
    from game.incident_runtime import incident_record, incident_records
except Exception:  # pragma: no cover - defensive fallback for older snapshots.
    def incident_record(_sim, _incident_id):
        return None

    def incident_records(_sim):
        return ()


CASINO_SERVICE_IDS = {
    "slots",
    "video_poker",
    "keno",
    "roulette",
    "craps",
    "baccarat",
    "three_card_poker",
    "casino_holdem",
    "plinko",
    "twenty_one",
}


@dataclass
class RunFact:
    kind: str
    tick: int
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    weight: float = 0.0


class RunEpilogueLedgerSystem(System):
    """Collects notable run facts and appends an epilogue to run_end.

    The intent is to make hidden systems legible after death/victory without
    turning the live HUD into a spreadsheet. The output is a first-pass human
    readable ledger, not a final prose engine.
    """

    MAX_FACTS = 600
    MAX_NOTABLE_LINES = 7
    MAX_SUMMARY_LINES = 26

    def __init__(self, sim, player_eid=None):
        super().__init__(sim)
        self.player_eid = player_eid
        self.facts: list[RunFact] = []
        self.counts: Counter[str] = Counter()
        self.by_kind: dict[str, list[RunFact]] = defaultdict(list)
        self.casino_net = 0
        self.casino_rounds = 0
        self.casino_biggest_win = 0
        self.visited_chunks: set[tuple[int, int]] = set()
        self._bound_to_sim()
        self._subscribe()

    def _bound_to_sim(self):
        self.sim.run_epilogue_ledger = self
        if not isinstance(getattr(self.sim, "run_epilogue_stats", None), dict):
            self.sim.run_epilogue_stats = {
                "facts": 0,
                "casino_net": 0,
                "casino_rounds": 0,
                "visited_chunks": 0,
            }

    def _subscribe(self):
        pairs = {
            "property_trespass": self.on_property_trespass,
            "property_tamper": self.on_property_tamper,
            "theft_committed": self.on_theft_committed,
            "item_stolen": self.on_theft_committed,
            "incident_looked_away": self.on_incident_looked_away,
            "observed_response_cue": self.on_observed_response_cue,
            "observed_response_dropped": self.on_observed_response_dropped,
            "incident_authority_reported": self.on_incident_authority_reported,
            "incident_report_cue_suppressed": self.on_incident_report_cue_suppressed,
            "incident_dispatch_queued": self.on_incident_dispatch_queued,
            "incident_dispatch_started": self.on_incident_dispatch_started,
            "incident_responder_assigned": self.on_incident_responder_assigned,
            "incident_dispatch_arrived": self.on_incident_dispatch_arrived,
            "incident_dispatch_dropped": self.on_incident_dispatch_dropped,
            "incident_dispatch_ignored": self.on_incident_dispatch_ignored,
            "rumor_shared": self.on_rumor_shared,
            "knowledge_propagated": self.on_knowledge_propagated,
            "rumor_corrupted": self.on_rumor_corrupted,
            "site_service_used": self.on_site_service_used,
            "site_service_blocked": self.on_site_service_blocked,
            "overworld_travelled": self.on_overworld_travelled,
            "overworld_discovery_found": self.on_overworld_discovery_found,
            "weapon_fired": self.on_weapon_fired,
            "melee_attack": self.on_melee_attack,
            "explosion_triggered": self.on_explosion_triggered,
            "player_downed": self.on_player_downed,
            "player_killed": self.on_player_killed,
            "npc_downed": self.on_npc_downed,
            "npc_killed": self.on_npc_killed,
            "alarm_box_cut": self.on_alarm_cut,
            "fixture_alarm_cut": self.on_alarm_cut,
            "alarm_signal_blocked": self.on_alarm_signal_blocked,
            "final_operation_unlocked": self.on_final_operation_unlocked,
            "final_operation_target_identified": self.on_final_operation_target_identified,
            "final_operation_failed": self.on_final_operation_failed,
            "final_operation_completed": self.on_final_operation_completed,
            "run_pressure_changed": self.on_run_pressure_changed,
            "run_pressure_tier_changed": self.on_run_pressure_tier_changed,
            "run_concluded": self.on_run_concluded,
        }
        for event_type, handler in pairs.items():
            self.sim.events.subscribe(event_type, handler)

    def update(self):
        # Event-driven system. Nothing to tick.
        return None

    # ------------------------------------------------------------------
    # Generic helpers

    def _tick(self, event=None):
        value = None
        if event is not None:
            value = event.data.get("tick")
        if value is None:
            value = getattr(self.sim, "tick", 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _record(self, kind, summary, event=None, *, weight=0.0, **data):
        kind = str(kind or "fact").strip().lower() or "fact"
        summary = str(summary or "").strip()
        if not summary:
            return None
        fact = RunFact(kind=kind, tick=self._tick(event), summary=summary, data=dict(data), weight=float(weight or 0.0))
        self.facts.append(fact)
        if len(self.facts) > self.MAX_FACTS:
            self.facts = self.facts[-self.MAX_FACTS:]
        self.counts[kind] += 1
        self.by_kind[kind].append(fact)
        if len(self.by_kind[kind]) > 120:
            self.by_kind[kind] = self.by_kind[kind][-120:]
        self._refresh_stats()
        return fact

    def _refresh_stats(self):
        stats = getattr(self.sim, "run_epilogue_stats", None)
        if not isinstance(stats, dict):
            self.sim.run_epilogue_stats = {}
            stats = self.sim.run_epilogue_stats
        stats["facts"] = len(self.facts)
        stats["casino_net"] = int(self.casino_net)
        stats["casino_rounds"] = int(self.casino_rounds)
        stats["visited_chunks"] = len(self.visited_chunks)

    def _eid_name(self, eid, fallback="someone"):
        try:
            eid = int(eid)
        except (TypeError, ValueError):
            return fallback
        label = _entity_display_name(self.sim, eid, title_case=True)
        if label and str(label).strip().lower() not in {"entity", "someone"}:
            return str(label).strip()
        ident = self.sim.ecs.get(CreatureIdentity).get(eid)
        if ident is not None:
            personal = str(getattr(ident, "personal_name", "") or "").strip()
            if personal:
                return personal
            common = str(getattr(ident, "common_name", "") or "").strip()
            if common:
                return common
        return fallback

    def _eid_phrase(self, eid, fallback="someone"):
        try:
            eid = int(eid)
        except (TypeError, ValueError):
            return fallback
        return _entity_display_phrase(self.sim, eid, title_case=False, article=True, fallback=fallback)

    def _player_component(self, component_cls):
        try:
            return self.sim.ecs.get(component_cls).get(self.player_eid)
        except Exception:  # pragma: no cover - defensive for older snapshots/tests.
            return None

    def _place_label(self, data):
        prop = str(data.get("property_name", "") or "").strip()
        if prop:
            return prop
        loc = self._location(data)
        if loc:
            return loc
        return "the city"

    def _location(self, data):
        try:
            x = int(data.get("x"))
            y = int(data.get("y"))
            z = int(data.get("z", 0) or 0)
            return f"{x},{y},{z}"
        except (TypeError, ValueError):
            return ""

    def _event_incident_id(self, event):
        value = event.data.get("incident_id")
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _incident_entry(self, incident_id):
        if incident_id is None:
            return None
        try:
            record = incident_record(self.sim, incident_id)
        except Exception:  # pragma: no cover - soft fallback for older snapshots/tests.
            return None
        return record if isinstance(record, dict) else None

    def _incident_place_label(self, incident):
        if not isinstance(incident, dict):
            return ""
        name = str(incident.get("property_name", "") or "").strip()
        if name:
            return name
        property_id = str(incident.get("property_id", "") or "").strip()
        props = getattr(self.sim, "properties", None)
        prop = props.get(property_id) if property_id and isinstance(props, dict) else None
        if isinstance(prop, dict):
            name = str(prop.get("name", "") or "").strip()
            if name:
                return name
        return self._location(incident)

    def _incident_participant_name(self, incident):
        if not isinstance(incident, dict):
            return ""
        name = str(incident.get("victim_name", "") or "").strip()
        if name:
            return name
        return self._eid_name(incident.get("victim_eid"), "")

    def _incident_participant_phrase(self, incident):
        if not isinstance(incident, dict):
            return ""
        phrase = self._eid_phrase(incident.get("victim_eid"), "")
        if phrase:
            return phrase
        return _display_label_phrase(self._incident_participant_name(incident), article=True)

    def _action_offense_subject(self, incident):
        note = str((incident or {}).get("note", "") or "").strip().lower()
        action, _, context = note.partition("/")
        labels = {
            "armed_assault": "gunfire",
            "contraband_trade": "visible contraband trade",
            "contraband_use": "visible contraband use",
            "explosive_discharge": "an explosion",
            "fire_weapon": "gunfire",
            "forced_breach": "a forced breach",
            "homicide": "a killing",
            "melee_assault": "a melee assault",
            "melee_attack": "an assault",
            "unarmed_assault": "an assault",
            "use_item": "item use",
        }
        base = labels.get(context) or labels.get(action) or context.replace("_", " ").strip() or action.replace("_", " ").strip() or "violence"
        victim = self._incident_participant_phrase(incident)
        place = self._incident_place_label(incident)
        if victim:
            linker = "involving" if base in {"visible contraband trade", "visible contraband use"} else "against"
            base = f"{base} {linker} {victim}"
        if place:
            base = f"{base} at {place}"
        return base

    def _incident_subject(self, incident_id, fallback="the incident"):
        incident = self._incident_entry(incident_id)
        if not isinstance(incident, dict):
            return fallback
        kind = str(incident.get("kind", "") or "").strip().lower()
        note = str(incident.get("note", "") or "").strip()
        victim = self._incident_participant_name(incident)
        place = self._incident_place_label(incident)

        if kind == "action_offense":
            return self._action_offense_subject(incident) or fallback
        if kind == "property_trespass":
            base = note.replace("_", " ").strip() or "trespass"
        elif kind == "property_tamper":
            base = "tampering"
        elif kind == "item_stolen":
            item = note or "something"
            base = f"theft of {item}"
        elif kind == "camera_alert":
            base = "a camera alert"
        else:
            base = note.replace("_", " ").strip() or kind.replace("_", " ").strip() or fallback
            if victim:
                base = f"{base} involving {victim}"

        if place:
            return f"{base} at {place}"
        return base or fallback

    def _participant_count(self, explicit_value=None, eids_value=None):
        if explicit_value is not None:
            return max(0, self._safe_int(explicit_value, 0))
        if isinstance(eids_value, (tuple, list, set)):
            return sum(1 for eid in eids_value if eid is not None)
        return 0

    # ------------------------------------------------------------------
    # Event handlers

    def on_property_trespass(self, event):
        if event.data.get("eid") != self.player_eid and event.data.get("actor_eid") != self.player_eid:
            return
        self._record(
            "trespass",
            f"You were somewhere you were not supposed to be at {self._place_label(event.data)}.",
            event,
            weight=0.35,
            property_id=event.data.get("property_id"),
        )

    def on_property_tamper(self, event):
        if event.data.get("eid") != self.player_eid and event.data.get("actor_eid") != self.player_eid:
            return
        action = str(event.data.get("action", event.data.get("reason", "tampering")) or "tampering").replace("_", " ")
        self._record("tamper", f"You tampered with infrastructure or property at {self._place_label(event.data)} ({action}).", event, weight=0.45)

    def on_theft_committed(self, event):
        if event.data.get("eid") != self.player_eid and event.data.get("actor_eid") != self.player_eid:
            return
        item = str(event.data.get("item_name", event.data.get("item_id", "something")) or "something").strip()
        self._record("theft", f"You took {item} and the city may not agree it was yours.", event, weight=0.45)

    def on_incident_looked_away(self, event):
        npc = self._eid_name(event.data.get("npc_eid"), "NPC")
        reason = str(event.data.get("reason", "social choice") or "social choice").replace("_", " ")
        subject = self._incident_subject(self._event_incident_id(event))
        self._record("look_away", f"{npc} chose not to make {subject} official ({reason}).", event, weight=0.75, incident_id=self._event_incident_id(event))

    def on_observed_response_cue(self, event):
        cue = str(event.data.get("cue_kind", "response") or "response").strip().lower()
        npc = self._eid_name(event.data.get("npc_eid"), "NPC")
        self._record(f"response_{cue}", f"{npc} decided on a {cue.replace('_', ' ')} response.", event, weight=0.5, incident_id=self._event_incident_id(event))

    def on_observed_response_dropped(self, event):
        reason = str(event.data.get("reason", "unavailable route") or "unavailable route").replace("_", " ")
        self._record("response_dropped", f"A response cue failed before becoming action ({reason}).", event, weight=0.5, incident_id=self._event_incident_id(event))

    def on_incident_authority_reported(self, event):
        method = str(event.data.get("method", event.data.get("route_method", "unknown")) or "unknown").replace("_", " ")
        reporter = self._eid_name(event.data.get("reporter_eid", event.data.get("npc_eid")), "someone")
        subject = self._incident_subject(self._event_incident_id(event))
        self._record("authority_report", f"{reporter} reported {subject} to authority by {method}.", event, weight=0.9, incident_id=self._event_incident_id(event))

    def on_incident_report_cue_suppressed(self, event):
        reason = str(event.data.get("reason", "duplicate") or "duplicate").replace("_", " ")
        self._record("report_suppressed", f"A duplicate authority report was suppressed ({reason}).", event, weight=0.55, incident_id=self._event_incident_id(event))

    def on_incident_dispatch_queued(self, event):
        subject = self._incident_subject(self._event_incident_id(event))
        self._record("dispatch_queued", f"An official report created a delayed dispatch opportunity around {subject}.", event, weight=0.65, incident_id=self._event_incident_id(event))

    def on_incident_dispatch_started(self, event):
        incident_id = self._event_incident_id(event)
        subject = self._incident_subject(incident_id)
        vigil = self._participant_count(event.data.get("vigil_count"), event.data.get("vigil_eids"))
        if vigil <= 0:
            dispatched = self._participant_count(event.data.get("assigned_count"), event.data.get("dispatched_eids"))
            peace_guess = self._participant_count(event.data.get("peace_count"), event.data.get("peace_eids"))
            vigil = max(0, dispatched - peace_guess)
        peace = self._participant_count(event.data.get("peace_count"), event.data.get("peace_eids"))
        if peace > 0:
            text = f"A civic response formed around {subject}; {vigil} civilian(s) and {peace} peace/security actor(s) moved."
        elif vigil <= 0:
            text = f"A civilian vigil response was called around {subject}, but nobody arrived."
        else:
            text = f"A civilian vigil response formed around {subject} with {vigil} attendee(s)."
        self._record("dispatch_started", text, event, weight=0.9, incident_id=incident_id)

    def on_incident_responder_assigned(self, event):
        responder = self._eid_name(event.data.get("responder_eid", event.data.get("npc_eid")), "responder")
        role = str(event.data.get("response_role", "responder") or "responder").replace("_", " ")
        subject = self._incident_subject(self._event_incident_id(event))
        self._record("responder_assigned", f"{responder} was assigned as {role} for {subject}.", event, weight=0.45, incident_id=self._event_incident_id(event))

    def on_incident_dispatch_arrived(self, event):
        responder = self._eid_name(event.data.get("responder_eid", event.data.get("npc_eid")), "responder")
        subject = self._incident_subject(self._event_incident_id(event))
        self._record("dispatch_arrived", f"{responder} reached the scene for {subject}.", event, weight=0.7, incident_id=self._event_incident_id(event))

    def on_incident_dispatch_dropped(self, event):
        reason = str(event.data.get("reason", "no responder") or "no responder").replace("_", " ")
        self._record("dispatch_dropped", f"A dispatch opportunity died before anyone could attend ({reason}).", event, weight=0.65, incident_id=self._event_incident_id(event))

    def on_incident_dispatch_ignored(self, event):
        reason = str(event.data.get("reason", "duplicate") or "duplicate").replace("_", " ")
        self._record("dispatch_ignored", f"A duplicate dispatch request was ignored ({reason}).", event, weight=0.35, incident_id=self._event_incident_id(event))

    def on_rumor_shared(self, event):
        source = self._eid_name(event.data.get("source_eid", event.data.get("speaker_eid")), "someone")
        target = self._eid_name(event.data.get("target_eid", event.data.get("listener_eid")), "someone")
        self._record("rumor_shared", f"A rumor moved from {source} to {target}.", event, weight=0.55, incident_id=self._event_incident_id(event))

    def on_knowledge_propagated(self, event):
        self._record("knowledge_propagated", "Incident knowledge propagated through a non-official channel.", event, weight=0.5, incident_id=self._event_incident_id(event))

    def on_rumor_corrupted(self, event):
        self._record("rumor_corrupted", "A rumor drifted away from its original account as it spread.", event, weight=0.85, incident_id=self._event_incident_id(event))

    def on_site_service_used(self, event):
        service = str(event.data.get("service", "") or "").strip().lower()
        if service not in CASINO_SERVICE_IDS:
            return
        net = self._safe_int(event.data.get("net_credits"), 0)
        wager = self._safe_int(event.data.get("wager", event.data.get("stake")), 0)
        place = str(event.data.get("property_name", "casino") or "casino").strip() or "casino"
        self.casino_rounds += 1
        self.casino_net += net
        self.casino_biggest_win = max(self.casino_biggest_win, net)
        self._refresh_stats()
        verb = "won" if net > 0 else "lost" if net < 0 else "pushed"
        self._record("casino_round", f"At {place}, {service.replace('_', ' ')} {verb} {abs(net)} credits on a {wager} credit stake.", event, weight=0.4 + min(0.4, abs(net) / 250.0))

    def on_site_service_blocked(self, event):
        service = str(event.data.get("service", "") or "").strip().lower()
        if service not in CASINO_SERVICE_IDS:
            return
        reason = str(event.data.get("reason", "blocked") or "blocked").replace("_", " ")
        self._record("casino_blocked", f"A casino round was blocked ({reason}).", event, weight=0.25)

    def on_overworld_travelled(self, event):
        chunk = event.data.get("chunk", event.data.get("target_chunk"))
        if isinstance(chunk, (tuple, list)) and len(chunk) >= 2:
            try:
                self.visited_chunks.add((int(chunk[0]), int(chunk[1])))
                self._refresh_stats()
            except (TypeError, ValueError):
                pass
        self._record("overworld_travel", "You moved through the city at chunk scale.", event, weight=0.2)

    def on_overworld_discovery_found(self, event):
        label = str(event.data.get("label", event.data.get("name", "a site")) or "a site").strip()
        self._record("overworld_discovery", f"You discovered {label} on the route map.", event, weight=0.55)

    def on_weapon_fired(self, event):
        if event.data.get("eid") != self.player_eid and event.data.get("actor_eid") != self.player_eid:
            return
        self._record("weapon_fired", "You fired a weapon; the city had a chance to hear it.", event, weight=0.55)

    def on_melee_attack(self, event):
        if event.data.get("eid") != self.player_eid and event.data.get("actor_eid") != self.player_eid:
            return
        target = self._eid_phrase(event.data.get("target_eid"), "a target")
        self._record("melee_attack", f"You attacked {target} up close.", event, weight=0.55)

    def on_explosion_triggered(self, event):
        self._record("explosion", "An explosion rewrote the situation loudly enough for the city to notice.", event, weight=0.9)

    def on_player_downed(self, event):
        if event.data.get("target_eid") != self.player_eid and event.data.get("eid") != self.player_eid:
            return
        self._record("player_downed", "You were downed before the run was done.", event, weight=1.0)

    def on_player_killed(self, event):
        if event.data.get("target_eid") != self.player_eid and event.data.get("eid") != self.player_eid:
            return
        self._record("player_killed", "You died in the city.", event, weight=1.0)

    def on_npc_downed(self, event):
        target = str(event.data.get("target_name", "") or "").strip() or self._eid_name(event.data.get("target_eid", event.data.get("eid")), "NPC")
        self._record("npc_downed", f"{target} was downed during the run.", event, weight=0.55)

    def on_npc_killed(self, event):
        target = str(event.data.get("target_name", "") or "").strip() or self._eid_name(event.data.get("target_eid", event.data.get("eid")), "NPC")
        self._record("npc_killed", f"{target} died during the run.", event, weight=0.75)

    def on_alarm_cut(self, event):
        where = self._place_label(event.data)
        self._record("alarm_cut", f"An alarm route was cut at {where}.", event, weight=0.8)

    def on_alarm_signal_blocked(self, event):
        reason = str(event.data.get("reason", "cut infrastructure") or "cut infrastructure").replace("_", " ")
        self._record("alarm_blocked", f"An alarm failed to send a signal ({reason}).", event, weight=0.9)

    def on_final_operation_unlocked(self, event):
        self._record("final_operation", "The final operation became available.", event, weight=0.8)

    def on_final_operation_target_identified(self, event):
        name = str(event.data.get("target_property_name", "target site") or "target site").strip()
        self._record("final_operation", f"The final operation target was identified at {name}.", event, weight=0.9)

    def on_final_operation_failed(self, event):
        reason = str(event.data.get("fail_reason", "failure") or "failure").replace("_", " ")
        self._record("final_operation_failed", f"The final operation failed ({reason}).", event, weight=1.0)

    def on_final_operation_completed(self, event):
        self._record("final_operation_completed", "The final operation was completed.", event, weight=1.0)

    def on_run_pressure_changed(self, event):
        delta = self._safe_int(event.data.get("delta"), 0)
        if delta <= 0:
            return
        if delta >= 8:
            self._record("run_pressure", f"Run pressure rose by {delta}; the city was adapting around you.", event, weight=0.45 + min(0.4, delta / 40.0))

    def on_run_pressure_tier_changed(self, event):
        tier = str(event.data.get("tier", event.data.get("new_tier", "pressure")) or "pressure").replace("_", " ")
        self._record("run_pressure_tier", f"Run pressure crossed into {tier} territory.", event, weight=0.75)

    def on_run_concluded(self, event):
        from game.tutorial import tutorial_no_persistence
        from game.fashion_market import flush_fashion_market

        tutorial = tutorial_no_persistence(self.sim)
        lines = self.build_summary_lines(outcome=str(event.data.get("outcome", "") or ""))
        if not lines:
            lines = []
        if tutorial:
            echo_result = {"lines": [], "records": []}
            tutorial_lines = [
                "Tutorial run:",
                "  Final target recovered through the normal final-operation path.",
                "  Controls practiced in this run stay local to the tutorial.",
                "  This tutorial does not affect future runs.",
            ]
            lines = tutorial_lines + [line for line in lines if str(line).strip()]
        else:
            flush_fashion_market(self.sim)
            echo_result = archive_run_echoes(
                self.sim,
                self.player_eid,
                outcome=str(event.data.get("outcome", "") or ""),
                reason=str(event.data.get("reason", "") or ""),
                objective_title=str(event.data.get("objective_title", "") or ""),
                summary_lines=tuple(event.data.get("summary_lines", ()) or ()),
            )
        reward_result = {"summary_lines": [], "files": [], "receipt": None}
        if not tutorial and str(event.data.get("outcome", "") or "").strip().lower() == "success":
            reward_result = export_success_reward_bundle(self.sim, self.player_eid, event.data)
        echo_lines = list((echo_result or {}).get("lines", ()) or ())
        echo_records = list((echo_result or {}).get("records", ()) or ())
        if echo_lines:
            lines = list(lines) + echo_lines
        reward_lines = list((reward_result or {}).get("summary_lines", ()) or ())
        if reward_lines:
            lines = list(lines) + reward_lines
        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            self.sim.world_traits = {}
            traits = self.sim.world_traits
        run_end = traits.get("run_end")
        if not isinstance(run_end, dict):
            run_end = {}
            traits["run_end"] = run_end
        existing = [str(line).strip() for line in run_end.get("summary_lines", ()) if str(line).strip()]
        run_end["summary_lines"] = existing + lines
        run_end["epilogue_lines"] = list(lines)
        run_end["echo_lines"] = list(echo_lines)
        run_end["echo_records"] = list(echo_records)
        reward_files = list((reward_result or {}).get("files", ()) or ())
        reward_receipt = (reward_result or {}).get("receipt")
        run_end["reward_files"] = reward_files
        run_end["reward_receipts"] = [reward_receipt] if isinstance(reward_receipt, dict) else []
        if (reward_result or {}).get("receipt_path"):
            run_end["reward_receipt_paths"] = [str((reward_result or {}).get("receipt_path"))]
        if (reward_result or {}).get("readme_path"):
            run_end["reward_readme_paths"] = [str((reward_result or {}).get("readme_path"))]
        self._record("run_epilogue_rendered", "The run epilogue was rendered.", event, weight=0.0)

    # ------------------------------------------------------------------
    # Summary rendering

    def build_summary_lines(self, *, outcome=""):
        lines: list[str] = []
        facts_count = len(self.facts)
        incident_summary = self._summarize_incidents()
        knowledge_summary = self._summarize_knowledge()

        lines.append("What the city remembered:")

        if facts_count <= 0 and not incident_summary and not knowledge_summary:
            lines.append("  The run left little structured memory behind yet.")
            return lines

        happened_bits = []
        if self.counts.get("trespass"):
            happened_bits.append(f"{self.counts['trespass']} trespass signal(s)")
        if self.counts.get("theft"):
            happened_bits.append(f"{self.counts['theft']} theft signal(s)")
        if self.counts.get("tamper"):
            happened_bits.append(f"{self.counts['tamper']} tamper signal(s)")
        if self.counts.get("weapon_fired"):
            happened_bits.append(f"{self.counts['weapon_fired']} weapon shot(s)")
        if self.counts.get("npc_downed") or self.counts.get("npc_killed"):
            happened_bits.append(f"{self.counts.get('npc_downed', 0)} NPC downing(s), {self.counts.get('npc_killed', 0)} NPC death(s)")
        if happened_bits:
            lines.append("  What happened: " + "; ".join(happened_bits) + ".")

        if incident_summary:
            lines.extend(f"  {line}" for line in incident_summary)
        if knowledge_summary:
            lines.extend(f"  {line}" for line in knowledge_summary)

        civic_bits = []
        if self.counts.get("authority_report"):
            civic_bits.append(f"{self.counts['authority_report']} authority report(s)")
        if self.counts.get("dispatch_started"):
            civic_bits.append(f"{self.counts['dispatch_started']} civic/vigil response(s)")
        if self.counts.get("look_away"):
            civic_bits.append(f"{self.counts['look_away']} looked-away incident(s)")
        if self.counts.get("alarm_cut") or self.counts.get("alarm_blocked"):
            civic_bits.append(f"{self.counts.get('alarm_cut', 0)} alarm cut(s), {self.counts.get('alarm_blocked', 0)} blocked alarm signal(s)")
        if civic_bits:
            lines.append("  Civic aftermath: " + "; ".join(civic_bits) + ".")

        pressure_summary = self._summarize_pressure()
        if pressure_summary:
            lines.extend(f"  {line}" for line in pressure_summary)

        legal_summary = self._summarize_legal()
        if legal_summary:
            lines.extend(f"  {line}" for line in legal_summary)

        organization_summary = self._summarize_organizations()
        if organization_summary:
            lines.extend(f"  {line}" for line in organization_summary)

        player_state = self._summarize_player_state()
        if player_state:
            lines.extend(f"  {line}" for line in player_state)

        loadout_summary = self._summarize_loadout()
        if loadout_summary:
            lines.extend(f"  {line}" for line in loadout_summary)

        if self.casino_rounds > 0:
            net_text = "won" if self.casino_net > 0 else "lost" if self.casino_net < 0 else "broke even on"
            lines.append(f"  Casino ledger: {self.casino_rounds} round(s), {net_text} {abs(self.casino_net)} credits total.")

        if self.visited_chunks:
            lines.append(f"  Route memory: you exposed {len(self.visited_chunks)} chunk-scale map node(s).")

        notable = self._notable_facts()
        if notable:
            lines.append("  Notable traces:")
            for fact in notable[: self.MAX_NOTABLE_LINES]:
                lines.append(f"    - {fact.summary}")

        return lines[: self.MAX_SUMMARY_LINES]

    def _summarize_incidents(self):
        records = [record for record in incident_records(self.sim) if isinstance(record, dict)]
        if not records:
            return []
        total = len(records)
        reported = sum(1 for record in records if bool(record.get("officially_reported")))
        max_depth = 0
        kinds = Counter()
        for record in records:
            kind = str(record.get("kind", "incident") or "incident").replace("_", " ")
            kinds[kind] += 1
            try:
                max_depth = max(max_depth, int(record.get("max_observed_propagation", record.get("propagation_depth", 0)) or 0))
            except (TypeError, ValueError):
                pass
        common = ", ".join(f"{count} {kind}" for kind, count in kinds.most_common(3))
        lines = [f"Incident ledger: {total} incident(s), {reported} officially reported."]
        if common:
            lines.append(f"Incident types: {common}.")
        if max_depth > 0:
            lines.append(f"Deepest rumor/knowledge propagation reached depth {max_depth}.")
        return lines

    def _summarize_knowledge(self):
        holders = 0
        total_records = 0
        firsthand = 0
        rumor = 0
        for knowledge in self.sim.ecs.get(IncidentKnowledge).values():
            records = getattr(knowledge, "records", None)
            if not isinstance(records, dict) or not records:
                continue
            holders += 1
            total_records += len(records)
            for record in records.values():
                if not isinstance(record, dict):
                    continue
                if bool(record.get("firsthand", False)):
                    firsthand += 1
                if int(record.get("propagation_depth", 0) or 0) > 0 or str(record.get("source_kind", "")).strip().lower() in {"rumor", "social_rumor", "gossip"}:
                    rumor += 1
        if holders <= 0:
            return []
        return [f"Knowledge holders: {holders} actor(s) held {total_records} incident account(s): {firsthand} firsthand, {rumor} rumor/propagated."]

    def _notable_facts(self):
        # Prefer high-weight and recent facts, but avoid repeating same broad kind too much.
        ranked = sorted(
            self.facts,
            key=lambda fact: (float(fact.weight), int(fact.tick)),
            reverse=True,
        )
        selected = []
        used = Counter()
        for fact in ranked:
            if fact.kind == "run_epilogue_rendered":
                continue
            broad = fact.kind.split("_", 1)[0]
            if used[broad] >= 2:
                continue
            selected.append(fact)
            used[broad] += 1
            if len(selected) >= self.MAX_NOTABLE_LINES:
                break
        return selected

    def _latest_fact(self, kind):
        facts = self.by_kind.get(kind) or []
        return facts[-1] if facts else None

    def _player_place_label(self):
        pos = self._player_component(Position)
        if pos is None:
            return ""
        prop = _property_covering(self.sim, pos.x, pos.y, pos.z) or self.sim.property_at(pos.x, pos.y, pos.z)
        if isinstance(prop, dict):
            name = str(prop.get("name", "") or "").strip()
            if name:
                return name
        return f"{int(pos.x)},{int(pos.y)},{int(pos.z)}"

    def _summarize_pressure(self):
        snapshot = pressure_snapshot(self.sim)
        attention = int(snapshot.get("attention", 0) or 0)
        peak = int(snapshot.get("peak_attention", 0) or 0)
        mitigations = int(snapshot.get("mitigation_count", 0) or 0)
        if attention <= 0 and peak <= 0 and mitigations <= 0:
            return []
        tier = str(snapshot.get("tier", "low") or "low").strip().lower() or "low"
        line = f"Heat ledger: {tier} {attention} attention at the end; peak {peak}."
        if mitigations > 0:
            line += f" Pressure cooled {mitigations} time(s)."
        return [line]

    def _summarize_player_state(self):
        assets = self._player_component(PlayerAssets)
        finance = self._player_component(FinancialProfile)
        vitality = self._player_component(Vitality)
        statuses = self._player_component(StatusEffects)

        lines = []
        place = self._player_place_label()
        hp_text = ""
        if vitality is not None:
            hp_text = f"HP {int(getattr(vitality, 'hp', 0) or 0)}/{int(getattr(vitality, 'max_hp', 1) or 1)}"
            if bool(getattr(vitality, "downed", False)):
                hp_text += " and downed"
        active = []
        if statuses is not None and isinstance(getattr(statuses, "active", None), dict):
            active = sorted(str(status).replace("_", " ") for status in statuses.active.keys() if str(status).strip())
        status_text = "no active effects"
        if active:
            preview = ", ".join(active[:2])
            if len(active) > 2:
                preview += ", ..."
            noun = "effect" if len(active) == 1 else "effects"
            status_text = f"{len(active)} active {noun} ({preview})"

        if place or hp_text or status_text:
            bits = []
            if place:
                bits.append(f"at {place}")
            if hp_text:
                bits.append(hp_text)
            if status_text:
                bits.append(status_text)
            if bits:
                lines.append("End state: " + "; ".join(bits) + ".")

        credits = int(getattr(assets, "credits", 0) or 0) if assets is not None else 0
        bank = int(getattr(finance, "bank_balance", 0) or 0) if finance is not None else 0
        debt = int(finance.total_debt() if finance and hasattr(finance, "total_debt") else getattr(finance, "debt_balance", 0) or 0)
        owned = len(getattr(assets, "owned_property_ids", ()) or ()) if assets is not None else 0
        if assets is not None or finance is not None:
            line = f"Finances: {credits} credits on hand, {bank} banked, {debt} debt."
            if owned > 0:
                line += f" Owned property {owned}."
            lines.append(line)
        return lines

    def _summarize_loadout(self):
        inventory = self._player_component(Inventory)
        loadout = self._player_component(WeaponLoadout)
        if inventory is None and loadout is None:
            return []

        carried = list(getattr(inventory, "items", ()) or ()) if inventory is not None else []
        stack_count = len(carried)
        hot_count = 0
        medical_count = 0
        for entry in carried:
            if not isinstance(entry, dict):
                continue
            item_id = str(entry.get("item_id", "") or "").strip()
            item_def = ITEM_CATALOG.get(item_id, {})
            legal = str(item_def.get("legal_status", "legal") or "legal").strip().lower()
            if legal in {"illegal", "restricted", "suspicious", "stolen"}:
                hot_count += 1
            if str(item_def.get("category", "") or "").strip().lower() == "medical":
                medical_count += 1

        weapon_text = "unarmed"
        reserve = 0
        arsenal_count = 0
        if loadout is not None:
            current_weapon = loadout.current_weapon() if hasattr(loadout, "current_weapon") else getattr(loadout, "equipped_weapon_id", None)
            if current_weapon:
                weapon = weapon_by_id(current_weapon)
                weapon_text = str(weapon.get("name", current_weapon) or current_weapon).strip() or "armed"
                reserve = int(max(0, getattr(loadout, "reserve_ammo", {}).get(current_weapon, 0) or 0))
            arsenal_count = len(getattr(loadout, "weapon_ids", ()) or ())

        line = (
            f"Loadout residue: {weapon_text} ready, {reserve} reserve round(s), "
            f"{stack_count} carried stack(s)"
        )
        extras = []
        if arsenal_count > 1:
            extras.append(f"{arsenal_count} total weapon slots filled")
        if hot_count > 0:
            extras.append(f"{hot_count} hot/restricted stack(s)")
        if medical_count > 0:
            extras.append(f"{medical_count} medical stack(s)")
        if extras:
            line += "; " + ", ".join(extras)
        line += "."
        return [line]

    def _summarize_legal(self):
        if self.player_eid is None:
            return []
        return [str(line).strip() for line in justice_summary_rows(self.sim, self.player_eid) if str(line).strip()]

    def _summarize_organizations(self):
        rows = [
            row
            for row in top_organization_snapshots(self.sim, limit=2, sort_by="heat")
            if int(row.get("heat", 0) or 0) > 0 or abs(float(row.get("standing", 0.0) or 0.0)) >= 0.2
        ]
        if not rows:
            return []
        parts = []
        for row in rows:
            name = str(row.get("name", "Organization") or "Organization").strip()
            heat = int(row.get("heat", 0) or 0)
            heat_tier = str(row.get("heat_tier", "quiet") or "quiet").strip().lower() or "quiet"
            standing_tier = str(row.get("standing_tier", "neutral") or "neutral").strip().lower() or "neutral"
            part = f"{name} {heat_tier} heat {heat}"
            if standing_tier != "neutral":
                part += f", {standing_tier}"
            parts.append(part)
        return ["Organization fallout: " + "; ".join(parts) + "."]

    @staticmethod
    def _safe_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)
