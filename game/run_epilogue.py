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
from game.components import CreatureIdentity, IncidentKnowledge, Position

try:  # Incident runtime is present in current BAKERRRR, but keep this module soft.
    from game.incident_runtime import incident_records
except Exception:  # pragma: no cover - defensive fallback for older snapshots.
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
    MAX_SUMMARY_LINES = 18

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
        ident = self.sim.ecs.get(CreatureIdentity).get(eid)
        if ident is not None:
            personal = str(getattr(ident, "personal_name", "") or "").strip()
            if personal:
                return f"{personal}#{eid}"
            common = str(getattr(ident, "common_name", "") or "").strip()
            if common:
                return f"{common}#{eid}"
        return f"{fallback}#{eid}"

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
        self._record("look_away", f"{npc} chose not to make an incident official ({reason}).", event, weight=0.75, incident_id=self._event_incident_id(event))

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
        self._record("authority_report", f"{reporter} reported an incident to authority by {method}.", event, weight=0.9, incident_id=self._event_incident_id(event))

    def on_incident_report_cue_suppressed(self, event):
        reason = str(event.data.get("reason", "duplicate") or "duplicate").replace("_", " ")
        self._record("report_suppressed", f"A duplicate authority report was suppressed ({reason}).", event, weight=0.55, incident_id=self._event_incident_id(event))

    def on_incident_dispatch_queued(self, event):
        self._record("dispatch_queued", "An official report created a delayed dispatch opportunity.", event, weight=0.65, incident_id=self._event_incident_id(event))

    def on_incident_dispatch_started(self, event):
        vigil = int(event.data.get("vigil_count", event.data.get("assigned_count", 0)) or 0)
        peace = int(event.data.get("peace_count", 0) or 0)
        if peace > 0:
            text = f"A civic response formed around the incident; {vigil} civilian(s) and {peace} peace/security actor(s) moved."
        else:
            text = f"A civilian vigil response formed around the incident with {vigil} attendee(s)."
        self._record("dispatch_started", text, event, weight=0.9, incident_id=self._event_incident_id(event))

    def on_incident_responder_assigned(self, event):
        responder = self._eid_name(event.data.get("responder_eid", event.data.get("npc_eid")), "responder")
        role = str(event.data.get("response_role", "responder") or "responder").replace("_", " ")
        self._record("responder_assigned", f"{responder} was assigned as {role} for an incident.", event, weight=0.45, incident_id=self._event_incident_id(event))

    def on_incident_dispatch_arrived(self, event):
        responder = self._eid_name(event.data.get("responder_eid", event.data.get("npc_eid")), "responder")
        self._record("dispatch_arrived", f"{responder} reached the reported incident.", event, weight=0.7, incident_id=self._event_incident_id(event))

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
        target = self._eid_name(event.data.get("target_eid"), "target")
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
        target = self._eid_name(event.data.get("target_eid", event.data.get("eid")), "NPC")
        self._record("npc_downed", f"{target} was downed during the run.", event, weight=0.55)

    def on_npc_killed(self, event):
        target = self._eid_name(event.data.get("target_eid", event.data.get("eid")), "NPC")
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
        lines = self.build_summary_lines(outcome=str(event.data.get("outcome", "") or ""))
        if not lines:
            return
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

        if self.casino_rounds > 0:
            net_text = "won" if self.casino_net > 0 else "lost" if self.casino_net < 0 else "broke even on"
            lines.append(f"  Casino ledger: {self.casino_rounds} round(s), {net_text} {abs(self.casino_net)} credits total.")

        if self.visited_chunks:
            lines.append(f"  Route memory: you exposed {len(self.visited_chunks)} chunk-scale map node(s).")

        pressure = self._latest_fact("run_pressure_tier") or self._latest_fact("run_pressure")
        if pressure:
            lines.append(f"  Pressure: {pressure.summary}")

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

    @staticmethod
    def _safe_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)
