"""NPC memory and rumor runtime extracted from ``game/systems.py``.

This seam keeps witness memory, social rumor spread, and related runtime
behavior together while ``game/systems.py`` remains the compatibility
surface for the rest of the project.
"""

import random

from engine.events import Event
from engine.systems import System
from game import systems as _systems
from game.system_support.actor_runtime import _detail_tick_allowed
from game.system_support.offense_runtime import (
    _offense_notice_radius,
    _offense_tier,
)

AI = _systems.AI
JusticeProfile = _systems.JusticeProfile
NPCMemory = _systems.NPCMemory
NPCNeeds = _systems.NPCNeeds
NPCSocial = _systems.NPCSocial
NPCTraits = _systems.NPCTraits
Position = _systems.Position
PropertyKnowledge = _systems.PropertyKnowledge
CreatureIdentity = _systems.CreatureIdentity
_clamp = _systems._clamp
_crime_sensitivity = _systems._crime_sensitivity
_degrade_player_disguise = _systems._degrade_player_disguise
_justice_level = _systems._justice_level
_manhattan = _systems._manhattan
_noise_attention_context_from_event = _systems._noise_attention_context_from_event
_noise_merits_attention = _systems._noise_merits_attention
_npc_conflict_alignment = _systems._npc_conflict_alignment
_npc_disguise_scrutiny_profile = _systems._npc_disguise_scrutiny_profile
_npc_recognizes_player = _systems._npc_recognizes_player
_observer_can_notice_position = _systems._observer_can_notice_position
_observer_turns_blind_eye_to_offense = _systems._observer_turns_blind_eye_to_offense
_pressure_effects = _systems._pressure_effects
_property_claim_reason = _systems._property_claim_reason
_property_covering = _systems._property_covering
_property_focus_position = _systems._property_focus_position
_world_trait_claim_value = _systems._world_trait_claim_value


def _target_is_wildlife_or_animal(sim, target_eid):
    ai = sim.ecs.get(AI).get(target_eid)
    identity = sim.ecs.get(CreatureIdentity).get(target_eid)
    role = str(getattr(ai, "role", "") or "").strip().lower()
    creature_type = str(getattr(identity, "creature_type", "") or "").strip().lower()
    return role == "wildlife" or creature_type == "animal"


class NPCMemorySystem(System):

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("noise", self.on_noise)
        self.sim.events.subscribe("action_offense", self.on_action_offense)
        self.sim.events.subscribe("npc_offended", self.on_npc_offended)
        self.sim.events.subscribe("dialogue_guard_resolution", self.on_dialogue_guard_resolution)
        self.sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        self.sim.events.subscribe("npc_protect_ally", self.on_npc_protect_ally)
        self.sim.events.subscribe("npc_warn_property", self.on_npc_warn_property)
        self.sim.events.subscribe("npc_defend_property", self.on_npc_defend_property)
        self.sim.events.subscribe("property_threatened", self.on_property_threatened)
        self.sim.events.subscribe("creature_hazard_triggered", self.on_creature_hazard_triggered)
        self.sim.events.subscribe("world_condition_triggered", self.on_world_condition_triggered)
        self.sim.events.subscribe("flora_natural_rumor_seeded", self.on_flora_natural_rumor_seeded)

    def on_noise(self, event):
        source_eid = event.data.get("source_eid")
        nx = event.data.get("x")
        ny = event.data.get("y")
        nz = event.data.get("z")
        radius = event.data.get("radius", 0)
        cause = event.data.get("cause")
        attention_context = None

        positions = self.sim.ecs.get(Position)
        memories = self.sim.ecs.get(NPCMemory)
        needs = self.sim.ecs.get(NPCNeeds)

        nearby_eids = self.sim.entity_ids_in_radius(nx, ny, nz, int(radius) + 4)
        for eid in nearby_eids:
            memory = memories.get(eid)
            if memory is None:
                continue
            pos = positions.get(eid)
            if not pos:
                continue

            dist = _manhattan(pos.x, pos.y, nx, ny)
            if attention_context is None:
                attention_context = _noise_attention_context_from_event(self.sim, event)
            if not _noise_merits_attention(
                self.sim,
                eid,
                source_eid,
                nx,
                ny,
                nz,
                cause,
                context=attention_context,
            ):
                continue

            intensity = max(0.1, 1.0 - (dist / float(max(1, radius + 1))))
            memory.remember(
                tick=self.sim.tick,
                kind="noise",
                strength=intensity,
                source_eid=source_eid,
                x=nx,
                y=ny,
                z=nz,
                cause=cause,
            )

            if source_eid != eid:
                memory.remember(
                    tick=self.sim.tick,
                    kind="threat",
                    strength=intensity * 0.75,
                    source_eid=source_eid,
                    x=nx,
                    y=ny,
                    z=nz,
                )

                npc_needs = needs.get(eid)
                if npc_needs:
                    npc_needs.safety = _clamp(npc_needs.safety - (intensity * 4.0))

    def on_action_offense(self, event):
        offender_eid = event.data.get("offender_eid")
        action = event.data.get("action")
        context = event.data.get("context", "ordinary")
        offense_score = int(event.data.get("offense_score", 0))
        offense_tier = event.data.get("offense_tier", _offense_tier(offense_score))
        incident_id = event.data.get("knowledge_incident_id")
        context_key = str(context or "ordinary").strip().lower() or "ordinary"
        action_key = str(action or "").strip().lower()
        ox = event.data.get("x")
        oy = event.data.get("y")
        oz = event.data.get("z")
        radius = max(1, int(event.data.get("radius", _offense_notice_radius(offense_score))))
        offense_prop = _property_covering(self.sim, ox, oy, oz)
        offense_property_id = offense_prop.get("id") if isinstance(offense_prop, dict) else None

        if offense_score <= 0:
            return
        if ox is None or oy is None or oz is None:
            return

        positions = self.sim.ecs.get(Position)
        memories = self.sim.ecs.get(NPCMemory)
        needs_map = self.sim.ecs.get(NPCNeeds)
        socials = self.sim.ecs.get(NPCSocial)
        traits_map = self.sim.ecs.get(NPCTraits)
        justices = self.sim.ecs.get(JusticeProfile)

        for eid, memory in memories.items():
            if eid == offender_eid:
                continue

            pos = positions.get(eid)
            if not pos or pos.z != oz:
                continue
            if _observer_turns_blind_eye_to_offense(
                self.sim,
                eid,
                offender_eid,
                action=action,
                context=context_key,
                offense_score=offense_score,
            ):
                continue
            if not _observer_can_notice_position(self.sim, eid, ox, oy, oz):
                continue

            dist = _manhattan(pos.x, pos.y, ox, oy)
            if dist > radius:
                continue

            distance_modifier = max(0.05, 1.0 - (dist / float(radius + 1)))

            relation_modifier = 1.0
            social = socials.get(eid)
            if social and offender_eid in social.bonds:
                bond = social.bonds[offender_eid]
                relation_modifier = max(
                    0.3,
                    1.0 - ((bond["trust"] * 0.45) + (bond["closeness"] * 0.25)),
                )
                if bond["kind"] in {"family", "partner"}:
                    relation_modifier *= 0.8

            justice_modifier = 1.0
            sensitivity_modifier = 1.0
            justice = justices.get(eid)
            if justice:
                justice_modifier = 0.8 + (_justice_level(justice) * 0.45)
                sensitivity_modifier = 0.65 + (_crime_sensitivity(justice) * 0.7)
                if justice.enforce_all:
                    sensitivity_modifier += 0.12
                corruption_modifier = max(0.2, 1.0 - (_clamp(justice.corruption, lo=0.0, hi=1.0) * 0.6))
                justice_modifier *= corruption_modifier
                sensitivity_modifier *= max(0.35, 1.0 - (_clamp(justice.corruption, lo=0.0, hi=1.0) * 0.35))

            traits = traits_map.get(eid) or NPCTraits()
            trait_modifier = 0.75 + (traits.discipline * 0.35) + (traits.empathy * 0.15)

            perceived = (offense_score / 100.0) * distance_modifier * relation_modifier
            perceived *= justice_modifier * sensitivity_modifier * trait_modifier
            if offender_eid == getattr(self.sim, "player_eid", None):
                disguise_profile = None
                if (
                    offense_prop
                    and context_key in {"ordinary", "trespass"}
                    and action_key not in {"fire_weapon", "tamper", "vehicle_theft"}
                    and offense_score <= 24
                ):
                    disguise_profile = _npc_disguise_scrutiny_profile(
                        self.sim,
                        eid,
                        offense_prop,
                        offender_eid=offender_eid,
                    )
                    if disguise_profile:
                        perceived *= float(disguise_profile.get("suspicion_mult", 1.0))
                perceived *= float(_pressure_effects(self.sim).get("suspicion_mult", 1.0))
                # NPCs who have previously warned or confronted the player
                # recognize them faster and read their actions more harshly.
                # Matching cover suppresses this longer; bad cover lets it cut through faster.
                disguise = getattr(self.sim, "disguise_state", None)
                disguise_strength = float(disguise.get("strength", 0.0)) if isinstance(disguise, dict) else 0.0
                recognition = _npc_recognizes_player(memory, offender_eid)
                recognition_floor = float(disguise_profile.get("recognition_floor", 0.35)) if disguise_profile else 0.35
                if recognition > 0.0 and disguise_strength < recognition_floor:
                    perceived = min(1.0, perceived + recognition * 0.28)
            perceived = _clamp(perceived, lo=0.0, hi=1.0)
            if perceived < 0.08:
                continue

            has_property_stake = False
            if offense_prop and offense_property_id:
                _, claim_reason = _property_claim_reason(
                    self.sim,
                    eid,
                    offense_prop,
                    x=pos.x,
                    y=pos.y,
                    z=pos.z,
                    min_standing=0.58,
                )
                has_property_stake = bool(claim_reason)

            memory.remember(
                tick=self.sim.tick,
                kind="offense",
                strength=perceived,
                offender_eid=offender_eid,
                action=action,
                context=context,
                offense_score=offense_score,
                offense_tier=offense_tier,
                x=ox,
                y=oy,
                z=oz,
                property_id=offense_property_id,
                has_property_stake=has_property_stake,
                incident_id=incident_id,
            )
            approval = -min(
                1.0,
                perceived
                * (
                    0.34
                    + min(0.44, offense_score / 95.0)
                    + (0.14 if has_property_stake else 0.0)
                ),
            )
            memory.remember(
                tick=self.sim.tick,
                kind="actor_reputation",
                strength=max(0.08, min(1.0, perceived * 0.92)),
                actor_eid=offender_eid,
                approval=round(float(approval), 3),
                action=action,
                context=context,
                offense_score=offense_score,
                offense_tier=offense_tier,
                property_id=offense_property_id,
                has_property_stake=has_property_stake,
                via="witnessed_offense",
                incident_id=incident_id,
            )

            if offense_score >= 35:
                memory.remember(
                    tick=self.sim.tick,
                    kind="threat",
                    strength=min(1.0, perceived * 0.9),
                    source_eid=offender_eid,
                    action=action,
                    context=context,
                    offense_score=offense_score,
                    x=ox,
                    y=oy,
                    z=oz,
                    property_id=offense_property_id,
                    has_property_stake=has_property_stake,
                    incident_id=incident_id,
                )

            npc_needs = needs_map.get(eid)
            if npc_needs:
                safety_penalty = perceived * (2.0 + (offense_score / 20.0))
                npc_needs.safety = _clamp(npc_needs.safety - safety_penalty)

            if perceived >= 0.35:
                self.sim.emit(Event(
                    "npc_offended",
                    npc_eid=eid,
                    offender_eid=offender_eid,
                    action=action,
                    context=context,
                    offense_score=offense_score,
                    offense_tier=offense_tier,
                    perceived=round(perceived, 3),
                    incident_id=incident_id,
                ))

    def on_npc_offended(self, event):
        offender_eid = event.data.get("offender_eid")
        offended_eid = event.data.get("npc_eid")
        if offender_eid is None or offended_eid is None or offender_eid == offended_eid:
            return

        try:
            perceived = float(event.data.get("perceived", 0.0) or 0.0)
        except (TypeError, ValueError):
            perceived = 0.0
        offense_score = int(event.data.get("offense_score", 0) or 0)
        if perceived <= 0.0 and offense_score <= 0:
            return
        action_key = str(event.data.get("action", "") or "").strip().lower()
        context_key = str(event.data.get("context", "") or "").strip().lower()
        dialogue_offense = action_key == "talk" or context_key.startswith("dialogue_")
        violence_eligible = bool(event.data.get("violence_eligible", False))

        positions = self.sim.ecs.get(Position)
        memories = self.sim.ecs.get(NPCMemory)
        socials = self.sim.ecs.get(NPCSocial)
        traits_map = self.sim.ecs.get(NPCTraits)
        justices = self.sim.ecs.get(JusticeProfile)
        needs_map = self.sim.ecs.get(NPCNeeds)
        offended_pos = positions.get(offended_eid)
        offender_pos = positions.get(offender_eid)
        if not offended_pos or not memories:
            return

        for eid, memory in memories.items():
            if eid == offender_eid:
                continue
            pos = positions.get(eid)
            if not pos or int(pos.z) != int(offended_pos.z):
                continue
            if eid != offended_eid:
                if not _observer_can_notice_position(self.sim, eid, offended_pos.x, offended_pos.y, offended_pos.z):
                    continue
                dist = _manhattan(pos.x, pos.y, offended_pos.x, offended_pos.y)
                if dist > 8:
                    continue
                distance_mult = max(0.24, 1.0 - (dist / 9.0))
            else:
                distance_mult = 1.0

            social = socials.get(eid)
            traits = traits_map.get(eid) or NPCTraits()
            justice = justices.get(eid)
            alignment = _npc_conflict_alignment(
                self.sim,
                eid,
                offender_eid,
                offended_eid,
                memory=memory,
                social=social,
                traits=traits,
                justice=justice,
            )
            impact = min(
                1.0,
                (0.08 + (max(0.0, perceived) * 0.44) + (max(0, offense_score) / 180.0))
                * distance_mult,
            )
            if impact <= 0.06:
                continue

            offender_approval = _clamp(-alignment * (0.76 + (impact * 0.18)), lo=-1.0, hi=1.0)
            offended_approval = _clamp(alignment * (0.64 + (impact * 0.12)), lo=-1.0, hi=1.0)
            memory.remember(
                tick=self.sim.tick,
                kind="actor_reputation",
                strength=max(0.08, impact),
                actor_eid=offender_eid,
                approval=round(float(offender_approval), 3),
                against_eid=offended_eid,
                action=event.data.get("action"),
                context=event.data.get("context"),
                offense_score=offense_score,
                via="npc_offended",
                incident_id=event.data.get("incident_id"),
            )
            memory.remember(
                tick=self.sim.tick,
                kind="actor_reputation",
                strength=max(0.08, impact * 0.88),
                actor_eid=offended_eid,
                approval=round(float(offended_approval), 3),
                against_eid=offender_eid,
                action=event.data.get("action"),
                context=event.data.get("context"),
                offense_score=offense_score,
                via="npc_offended",
                incident_id=event.data.get("incident_id"),
            )
            if dialogue_offense and eid == offended_eid:
                memory.remember(
                    tick=self.sim.tick,
                    kind="social_irritation",
                    strength=max(0.12, min(1.0, impact * 1.15)),
                    actor_eid=offender_eid,
                    action=event.data.get("action"),
                    context=event.data.get("context"),
                    offense_score=offense_score,
                    via="npc_offended",
                    incident_id=event.data.get("incident_id"),
                )

            if dialogue_offense and not violence_eligible:
                continue

            if (offense_score >= 20 or perceived >= 0.62) and abs(alignment) >= 0.18:
                side_eid = offended_eid if alignment >= 0.0 else offender_eid
                against_eid = offender_eid if alignment >= 0.0 else offended_eid
                target_pos = offender_pos if alignment >= 0.0 and offender_pos and int(offender_pos.z) == int(offended_pos.z) else offended_pos
                memory.remember(
                    tick=self.sim.tick,
                    kind="conflict_side",
                    strength=min(1.0, abs(alignment) * max(0.22, impact)),
                    side_eid=side_eid,
                    against_eid=against_eid,
                    source_eid=offender_eid,
                    target_eid=offended_eid,
                    x=target_pos.x if target_pos else offended_pos.x,
                    y=target_pos.y if target_pos else offended_pos.y,
                    z=target_pos.z if target_pos else offended_pos.z,
                    via="npc_offended",
                    incident_id=event.data.get("incident_id"),
                )
            if (offense_score >= 26 or perceived >= 0.72) and alignment >= 0.28:
                target_pos = offender_pos if offender_pos and int(offender_pos.z) == int(offended_pos.z) else offended_pos
                memory.remember(
                    tick=self.sim.tick,
                    kind="ally_threatened",
                    strength=min(1.0, alignment * max(0.24, impact)),
                    ally_eid=offended_eid,
                    against_eid=offender_eid,
                    x=target_pos.x if target_pos else offended_pos.x,
                    y=target_pos.y if target_pos else offended_pos.y,
                    z=target_pos.z if target_pos else offended_pos.z,
                    via="npc_offended",
                    incident_id=event.data.get("incident_id"),
                )

            npc_needs = needs_map.get(eid)
            if npc_needs and alignment >= 0.12:
                npc_needs.safety = _clamp(npc_needs.safety - (impact * 1.2))

    def on_dialogue_guard_resolution(self, event):
        player_eid = event.data.get("eid")
        if player_eid is None:
            player_eid = getattr(self.sim, "player_eid", None)
        if player_eid is None:
            return

        npc_eid = event.data.get("npc_eid")
        if npc_eid is None:
            return
        memories = self.sim.ecs.get(NPCMemory)
        memory = memories.get(npc_eid) if memories else None
        if memories is not None and memory is None:
            self.sim.ecs.add(npc_eid, NPCMemory())
            memory = self.sim.ecs.get(NPCMemory).get(npc_eid)
        if not memory:
            return

        outcome = str(event.data.get("outcome", "wary") or "wary").strip().lower() or "wary"
        tactic = str(event.data.get("tactic", "dialogue") or "dialogue").strip().lower() or "dialogue"
        approval_by_outcome = {
            "deescalated": 0.66,
            "wary": 0.08,
            "aggravated": -0.54,
        }
        strength_by_outcome = {
            "deescalated": 0.68,
            "wary": 0.32,
            "aggravated": 0.6,
        }
        memory.remember(
            tick=self.sim.tick,
            kind="actor_reputation",
            strength=float(strength_by_outcome.get(outcome, 0.3)),
            actor_eid=player_eid,
            approval=float(approval_by_outcome.get(outcome, 0.0)),
            tactic=tactic,
            outcome=outcome,
            via="dialogue_guard_resolution",
        )

        if outcome == "deescalated" and getattr(memory, "entries", None):
            trimmed = []
            for entry in list(memory.entries):
                if not isinstance(entry, dict):
                    trimmed.append(entry)
                    continue
                kind = str(entry.get("kind", "")).strip().lower()
                data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
                against_eid = data.get("against_eid")
                offender_eid = data.get("offender_eid")
                source_eid = data.get("source_eid")
                if kind in {"conflict_side", "ally_threatened"} and against_eid == player_eid:
                    continue
                if kind == "threat" and source_eid == player_eid:
                    continue
                if kind == "offense" and offender_eid == player_eid and str(data.get("context", "")).strip().lower().startswith("dialogue_"):
                    continue
                trimmed.append(entry)
            memory.entries = trimmed

    def on_entity_damaged(self, event):
        source_eid = event.data.get("source_eid")
        target_eid = event.data.get("target_eid")
        damage = int(event.data.get("damage", 0) or 0)
        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z")
        if source_eid is None or target_eid is None or source_eid == target_eid:
            return
        if damage <= 0 or x is None or y is None or z is None:
            return
        if _target_is_wildlife_or_animal(self.sim, target_eid):
            return

        positions = self.sim.ecs.get(Position)
        memories = self.sim.ecs.get(NPCMemory)
        socials = self.sim.ecs.get(NPCSocial)
        traits_map = self.sim.ecs.get(NPCTraits)
        justices = self.sim.ecs.get(JusticeProfile)
        needs_map = self.sim.ecs.get(NPCNeeds)
        if not memories:
            return

        for eid, memory in memories.items():
            if eid in {source_eid, target_eid}:
                continue
            pos = positions.get(eid)
            if not pos or int(pos.z) != int(z):
                continue
            if not _observer_can_notice_position(self.sim, eid, x, y, z):
                continue
            dist = _manhattan(pos.x, pos.y, x, y)
            if dist > 9:
                continue

            distance_mult = max(0.22, 1.0 - (dist / 10.0))
            social = socials.get(eid)
            traits = traits_map.get(eid) or NPCTraits()
            justice = justices.get(eid)
            alignment = _npc_conflict_alignment(
                self.sim,
                eid,
                source_eid,
                target_eid,
                memory=memory,
                social=social,
                traits=traits,
                justice=justice,
            )
            impact = min(1.0, (0.16 + (damage / 12.0)) * distance_mult)
            if impact <= 0.05:
                continue

            source_approval = _clamp(-alignment, lo=-1.0, hi=1.0)
            target_approval = _clamp(alignment * 0.85, lo=-1.0, hi=1.0)
            memory.remember(
                tick=self.sim.tick,
                kind="actor_reputation",
                strength=impact,
                actor_eid=source_eid,
                approval=round(source_approval, 3),
                target_eid=target_eid,
                damage=damage,
                damage_kind=str(event.data.get("damage_kind", "harm") or "harm"),
                via="witnessed_damage",
            )
            memory.remember(
                tick=self.sim.tick,
                kind="actor_reputation",
                strength=max(0.08, impact * 0.84),
                actor_eid=target_eid,
                approval=round(target_approval, 3),
                source_eid=source_eid,
                damage=damage,
                damage_kind=str(event.data.get("damage_kind", "harm") or "harm"),
                via="witnessed_damage",
            )

            if abs(alignment) >= 0.22:
                side_eid = target_eid if alignment >= 0.0 else source_eid
                against_eid = source_eid if alignment >= 0.0 else target_eid
                memory.remember(
                    tick=self.sim.tick,
                    kind="conflict_side",
                    strength=min(1.0, abs(alignment) * 0.86 + (impact * 0.28)),
                    side_eid=side_eid,
                    against_eid=against_eid,
                    source_eid=source_eid,
                    target_eid=target_eid,
                    x=x,
                    y=y,
                    z=z,
                    via="witnessed_damage",
                )

            if alignment >= 0.34:
                memory.remember(
                    tick=self.sim.tick,
                    kind="ally_threatened",
                    strength=min(1.0, alignment * 0.82),
                    ally_eid=target_eid,
                    against_eid=source_eid,
                    x=x,
                    y=y,
                    z=z,
                )

            npc_needs = needs_map.get(eid)
            if npc_needs:
                npc_needs.safety = _clamp(npc_needs.safety - (impact * 2.2))

    def on_npc_warn_property(self, event):
        npc_eid = event.data.get("npc_eid")
        offender_eid = event.data.get("offender_eid")
        player_eid = getattr(self.sim, "player_eid", None)
        if offender_eid != player_eid or npc_eid is None:
            return
        memory = self.sim.ecs.get(NPCMemory).get(npc_eid)
        if memory is None:
            return
        # Warn escalates recognition strength gently.
        current = _npc_recognizes_player(memory, player_eid)
        memory.remember(
            tick=self.sim.tick,
            kind="recognized",
            strength=min(1.0, current + 0.35),
            player_eid=player_eid,
            source="warn",
        )
        # Being warned degrades an active disguise — the NPC saw through it.
        _degrade_player_disguise(self.sim, player_eid, amount=0.35)

    def on_npc_defend_property(self, event):
        npc_eid = event.data.get("npc_eid")
        offender_eid = event.data.get("offender_eid")
        player_eid = getattr(self.sim, "player_eid", None)
        if offender_eid != player_eid or npc_eid is None:
            return
        memory = self.sim.ecs.get(NPCMemory).get(npc_eid)
        if memory is None:
            return
        # Active defense burns the face in at full strength.
        memory.remember(
            tick=self.sim.tick,
            kind="recognized",
            strength=0.85,
            player_eid=player_eid,
            source="defend",
        )
        # Active confrontation blows the disguise completely.
        _degrade_player_disguise(self.sim, player_eid, amount=1.0)

    def on_npc_protect_ally(self, event):
        protector = event.data.get("npc_eid")
        memories = self.sim.ecs.get(NPCMemory)
        memory = memories.get(protector)
        if not memory:
            return

        memory.remember(
            tick=self.sim.tick,
            kind="ally_threatened",
            strength=0.9,
            ally_eid=event.data.get("ally_eid"),
            against_eid=event.data.get("against_eid"),
        )

    def on_property_threatened(self, event):
        offender_eid = event.data.get("offender_eid")
        px = event.data.get("x")
        py = event.data.get("y")
        pz = event.data.get("z")
        property_id = event.data.get("property_id")

        positions = self.sim.ecs.get(Position)
        memories = self.sim.ecs.get(NPCMemory)
        knowledges = self.sim.ecs.get(PropertyKnowledge)
        justices = self.sim.ecs.get(JusticeProfile)
        prop = self.sim.properties.get(property_id)
        focus = _property_focus_position(prop) if prop else None
        if focus is not None:
            px, py, pz = focus

        for eid, memory in memories.items():
            pos = positions.get(eid)
            if not pos or pos.z != pz:
                continue

            dist = _manhattan(pos.x, pos.y, px, py)
            if dist > 12:
                continue

            intensity = max(0.2, 1.0 - (dist / 12.0))
            if prop:
                _, claim_reason = _property_claim_reason(
                    self.sim,
                    eid,
                    prop,
                    x=pos.x,
                    y=pos.y,
                    z=pos.z,
                    min_standing=0.58,
                )
                if not claim_reason:
                    profile = justices.get(eid)
                    if not profile:
                        continue
                    if profile.corruption > 0.75 and not profile.enforce_all:
                        continue

                    law_drive = (_justice_level(profile) * 0.65) + (_crime_sensitivity(profile) * 0.35)
                    if law_drive < 0.74:
                        continue

                    knowledge = knowledges.get(eid)
                    known = knowledge.known.get(prop["id"]) if knowledge else None
                    if not profile.enforce_all and not (known and known["confidence"] >= 0.5):
                        continue
                    intensity *= 0.78

            memory.remember(
                tick=self.sim.tick,
                kind="property_threat",
                strength=intensity,
                offender_eid=offender_eid,
                property_id=property_id,
                x=px,
                y=py,
                z=pz,
            )

    def on_creature_hazard_triggered(self, event):
        source_eid = event.data.get("source_eid")
        target_eid = event.data.get("target_eid")
        hx = event.data.get("x")
        hy = event.data.get("y")
        hz = event.data.get("z")
        coat_variant = str(event.data.get("coat_variant", "")).strip().lower()
        hazard_kind = str(event.data.get("hazard_kind", "toxic_cat") or "toxic_cat").strip().lower()
        species = str(event.data.get("species", "") or "").strip().lower()
        if hx is None or hy is None or hz is None:
            return
        if hazard_kind == "toxic_cat" and not coat_variant:
            return
        if hazard_kind == "venom" and not species:
            return

        positions = self.sim.ecs.get(Position)
        memories = self.sim.ecs.get(NPCMemory)
        if not positions or not memories:
            return

        for eid, memory in memories.items():
            pos = positions.get(eid)
            if not pos or pos.z != hz:
                continue
            dist = _manhattan(pos.x, pos.y, hx, hy)
            if dist > 9:
                continue

            intensity = max(0.25, 1.0 - (dist / 10.0))
            memory.remember(
                tick=self.sim.tick,
                kind="threat",
                strength=min(1.0, intensity * 0.82),
                source_eid=source_eid,
                target_eid=target_eid,
                action="venom_contact" if hazard_kind == "venom" else "toxic_contact",
                x=hx,
                y=hy,
                z=hz,
            )
            if hazard_kind == "venom":
                continue
            memory.remember(
                tick=self.sim.tick,
                kind="world_trait",
                strength=min(1.0, intensity * 0.95),
                topic="cat_toxin_coat",
                claimed_value=coat_variant,
                is_true=True,
                via="witnessed_hazard",
                tone="danger",
                source_eid=source_eid,
                target_eid=target_eid,
            )

    def on_world_condition_triggered(self, event):
        topic = str(event.data.get("topic", "")).strip().lower()
        claim = str(event.data.get("target_value", "")).strip().lower()
        wx = event.data.get("x")
        wy = event.data.get("y")
        wz = event.data.get("z")
        is_positive = bool(event.data.get("is_positive", False))
        if not topic or not claim or wx is None or wy is None or wz is None:
            return

        positions = self.sim.ecs.get(Position)
        memories = self.sim.ecs.get(NPCMemory)
        for eid, memory in memories.items():
            pos = positions.get(eid)
            if not pos or pos.z != wz:
                continue
            dist = _manhattan(pos.x, pos.y, wx, wy)
            if dist > 10:
                continue
            strength = max(0.22, 1.0 - (dist / 11.0))
            memory.remember(
                tick=self.sim.tick,
                kind="world_trait",
                strength=min(1.0, strength * 0.9),
                topic=topic,
                claimed_value=claim,
                is_true=True,
                via="witnessed_world_condition",
                tone="boon" if is_positive else "danger",
            )

    def on_flora_natural_rumor_seeded(self, event):
        topic = str(event.data.get("topic", "")).strip().lower()
        claim = str(event.data.get("claimed_value", "")).strip().lower()
        rx = event.data.get("x")
        ry = event.data.get("y")
        rz = event.data.get("z")
        if not topic or not claim or rx is None or ry is None or rz is None:
            return

        positions = self.sim.ecs.get(Position)
        memories = self.sim.ecs.get(NPCMemory)
        for eid, memory in memories.items():
            pos = positions.get(eid)
            if not pos or pos.z != rz:
                continue
            dist = _manhattan(pos.x, pos.y, rx, ry)
            if dist > 14:
                continue
            strength = max(0.26, 1.0 - (dist / 15.0))
            memory.remember(
                tick=self.sim.tick,
                kind="world_trait",
                strength=min(1.0, strength * 0.82),
                topic=topic,
                claimed_value=claim,
                is_true=bool(event.data.get("is_true", True)),
                via="natural_flora_rumor",
                tone=str(event.data.get("tone") or "danger").strip().lower(),
                plant_id=event.data.get("plant_id"),
                plant_name=event.data.get("plant_name"),
                notability=event.data.get("notability"),
                hybrid_signature=event.data.get("hybrid_signature"),
                parent_line_name=event.data.get("parent_line_name"),
                source="natural_crossbreed",
            )

    def update(self):
        memories = self.sim.ecs.get(NPCMemory)
        positions = self.sim.ecs.get(Position)

        decay_by_kind = {
            # Transient sensory traces.
            "noise": 0.01,
            # Immediate danger should cool off, but not instantly.
            "threat": 0.001,
            "ally_threatened": 0.001,
            "conflict_side": 0.0012,
            # A social read of conspicuous sneaking should last long enough to
            # color the encounter, but not become a permanent obsession.
            "suspicious_behavior": 0.012,
            # Consequence memory should linger.
            "offense": 0.0001,
            "property_threat": 0.0002,
            "player_reputation": 0.0003,
            "actor_reputation": 0.00035,
            # Shared world beliefs persist for a while.
            "world_trait": 0.00025,
        }

        for eid, memory in memories.items():
            pos = positions.get(eid)
            if pos and not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=4):
                continue

            def _stake_decay(entry, base_amount):
                kind = str(entry.get("kind", "")).strip().lower()
                data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
                if bool(data.get("permanent")):
                    return 0.0
                property_id = data.get("property_id")
                if not property_id:
                    return base_amount
                if kind not in {"offense", "property_threat"}:
                    return base_amount
                if bool(data.get("has_property_stake")):
                    return base_amount
                return max(base_amount, 0.006)

            memory.decay(amount=0.004, by_kind=decay_by_kind, entry_decay=_stake_decay)

class RumorSystem(System):

    def __init__(self, sim):
        super().__init__(sim)
        self.max_age_ticks = 70
        self.ambient_check_divisor = 5
        self.share_cooldown_ticks = 7
        self.recent_offenses = []
        self.last_share_tick = {}
        self.rng = random.Random(f"{sim.seed}:rumor_system")

        if not hasattr(self.sim, "rumor_stats"):
            self.sim.rumor_stats = {
                "active": 0,
                "shares_last_tick": 0,
            }

        self.sim.events.subscribe("action_offense", self.on_action_offense)

    def on_action_offense(self, event):
        offense_score = int(event.data.get("offense_score", 0))
        if offense_score < 20:
            return

        ox = event.data.get("x")
        oy = event.data.get("y")
        oz = event.data.get("z")
        if ox is None or oy is None or oz is None:
            return

        self.recent_offenses.append({
            "tick": self.sim.tick,
            "offender_eid": event.data.get("offender_eid"),
            "action": event.data.get("action"),
            "context": event.data.get("context", "ordinary"),
            "offense_score": offense_score,
            "offense_tier": event.data.get("offense_tier", _offense_tier(offense_score)),
            "incident_id": event.data.get("knowledge_incident_id"),
            "x": ox,
            "y": oy,
            "z": oz,
        })
        if len(self.recent_offenses) > 128:
            self.recent_offenses = self.recent_offenses[-128:]

    def _recent_offense_strength(self, memory, offender_eid, max_age=35):
        best = 0.0
        for entry in memory.entries:
            if entry["kind"] != "offense":
                continue
            if self.sim.tick - entry["tick"] > max_age:
                continue
            if entry["data"].get("offender_eid") != offender_eid:
                continue
            best = max(best, float(entry["strength"]))
        return best

    def _strongest_recent_offense(self, memory):
        best = None
        for entry in memory.entries:
            if entry["kind"] != "offense":
                continue
            if self.sim.tick - entry["tick"] > self.max_age_ticks:
                continue
            if best is None or float(entry["strength"]) > float(best["strength"]):
                best = entry
        return best

    def _recent_world_trait_strength(self, memory, topic, claimed_value, max_age=220):
        best = 0.0
        for entry in memory.entries:
            if entry["kind"] != "world_trait":
                continue
            if self.sim.tick - entry["tick"] > max_age:
                continue
            if str(entry["data"].get("topic", "")) != str(topic):
                continue
            if _world_trait_claim_value(entry["data"]) != str(claimed_value):
                continue
            best = max(best, float(entry["strength"]))
        return best

    def _strongest_recent_world_trait(self, memory, topic=None, max_age=220):
        best = None
        for entry in memory.entries:
            if entry["kind"] != "world_trait":
                continue
            if self.sim.tick - entry["tick"] > max_age:
                continue
            if topic is not None and str(entry["data"].get("topic", "")) != str(topic):
                continue
            if best is None or float(entry["strength"]) > float(best["strength"]):
                best = entry
        return best

    def _recent_actor_reputation_strength(self, memory, actor_eid, *, approval_sign=0, max_age=220):
        best = 0.0
        for entry in memory.entries:
            if entry["kind"] != "actor_reputation":
                continue
            if self.sim.tick - entry["tick"] > max_age:
                continue
            data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
            if data.get("actor_eid") != actor_eid:
                continue
            try:
                approval = float(data.get("approval", 0.0) or 0.0)
            except (TypeError, ValueError):
                approval = 0.0
            if approval_sign > 0 and approval <= 0.0:
                continue
            if approval_sign < 0 and approval >= 0.0:
                continue
            score = abs(approval) * float(entry.get("strength", 0.0) or 0.0)
            best = max(best, score)
        return best

    def _strongest_recent_actor_reputation(self, memory, max_age=320):
        best = None
        best_score = 0.0
        for entry in memory.entries:
            if entry["kind"] != "actor_reputation":
                continue
            if self.sim.tick - entry["tick"] > max_age:
                continue
            data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
            try:
                approval = float(data.get("approval", 0.0) or 0.0)
            except (TypeError, ValueError):
                approval = 0.0
            score = abs(approval) * float(entry.get("strength", 0.0) or 0.0)
            if score < 0.12:
                continue
            if best is None or score > best_score:
                best = entry
                best_score = score
        return best

    def _recent_conflict_side_strength(self, memory, side_eid, against_eid, max_age=140):
        best = 0.0
        for entry in memory.entries:
            if entry["kind"] != "conflict_side":
                continue
            if self.sim.tick - entry["tick"] > max_age:
                continue
            data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
            if data.get("side_eid") != side_eid or data.get("against_eid") != against_eid:
                continue
            best = max(best, float(entry.get("strength", 0.0) or 0.0))
        return best

    def _strongest_recent_conflict_side(self, memory, max_age=140):
        best = None
        for entry in memory.entries:
            if entry["kind"] != "conflict_side":
                continue
            if self.sim.tick - entry["tick"] > max_age:
                continue
            if best is None or float(entry.get("strength", 0.0) or 0.0) > float(best.get("strength", 0.0) or 0.0):
                best = entry
        return best

    def _actor_role_label(self, eid):
        if eid is None:
            return ""
        if eid == getattr(self.sim, "player_eid", None):
            return "player"
        ai = self.sim.ecs.get(AI).get(eid)
        return str(getattr(ai, "role", "") or "").strip().lower()

    def _rumor_worldview_profile(self, eid):
        traits = self.sim.ecs.get(NPCTraits).get(eid) or NPCTraits()
        justice = self.sim.ecs.get(JusticeProfile).get(eid)
        role = self._actor_role_label(eid) or "civilian"

        corruption = _clamp(getattr(justice, "corruption", 0.0) if justice else 0.0, lo=0.0, hi=1.0)
        order = _clamp(
            (float(getattr(traits, "discipline", 0.5) or 0.5) * 0.38)
            + (_justice_level(justice, default=0.5) * 0.38)
            + ((1.0 - corruption) * 0.24),
            lo=0.0,
            hi=1.0,
        )
        chaos = _clamp(
            ((1.0 - float(getattr(traits, "discipline", 0.5) or 0.5)) * 0.3)
            + (corruption * 0.44)
            + ((1.0 - _justice_level(justice, default=0.5)) * 0.26),
            lo=0.0,
            hi=1.0,
        )
        care = _clamp(
            (float(getattr(traits, "empathy", 0.5) or 0.5) * 0.58)
            + (float(getattr(traits, "loyalty", 0.5) or 0.5) * 0.24)
            + ((1.0 - corruption) * 0.18),
            lo=0.0,
            hi=1.0,
        )
        share = 0.42 + (float(getattr(traits, "empathy", 0.5) or 0.5) * 0.12)

        if role in {"guard", "scout"}:
            order = _clamp(order + 0.22, lo=0.0, hi=1.0)
            care = _clamp(care + 0.04, lo=0.0, hi=1.0)
            share = min(1.0, share + 0.04)
        elif role in {"worker", "clerk", "cashier", "merchant", "shopkeeper", "resident", "civilian", "manager"}:
            care = _clamp(care + 0.12, lo=0.0, hi=1.0)
            share = min(1.0, share + 0.07)
        elif role in {"runner", "thief", "dealer", "drunk", "pit_boss"}:
            chaos = _clamp(chaos + 0.24, lo=0.0, hi=1.0)
            order = _clamp(order - 0.08, lo=0.0, hi=1.0)
            share = min(1.0, share + 0.05)
        elif role in {"medic", "doctor", "nurse", "dispatcher"}:
            care = _clamp(care + 0.16, lo=0.0, hi=1.0)
            order = _clamp(order + 0.05, lo=0.0, hi=1.0)
            share = min(1.0, share + 0.04)

        return {
            "role": role,
            "order": order,
            "chaos": chaos,
            "care": care,
            "share": _clamp(share, lo=0.35, hi=1.0),
        }

    def _actor_reputation_rumor_interest(self, speaker_eid, entry):
        if not isinstance(entry, dict):
            return 0.0
        profile = self._rumor_worldview_profile(speaker_eid)
        data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
        actor_role = self._actor_role_label(data.get("actor_eid"))
        via = str(data.get("via", "") or "").strip().lower()
        context = str(data.get("context", "") or "").strip().lower()
        outcome = str(data.get("outcome", "") or "").strip().lower()
        worldview = str(data.get("worldview", "") or "").strip().lower()
        try:
            approval = float(data.get("approval", 0.0) or 0.0)
        except (TypeError, ValueError):
            approval = 0.0

        frame_order = 0.0
        frame_chaos = 0.0
        frame_care = 0.0
        if via == "job_completion":
            if worldview == "order":
                frame_order = 0.76
            elif worldview == "chaos":
                frame_chaos = 0.76
            else:
                frame_care = 0.72
                frame_order = 0.22
        elif via == "dialogue_guard_resolution":
            if outcome == "deescalated":
                frame_care = 0.78
                frame_order = 0.52
            elif outcome == "aggravated":
                frame_order = 0.72
                frame_care = 0.24
            else:
                frame_care = 0.34
                frame_order = 0.32
        elif via in {"witnessed_damage", "npc_offended"}:
            frame_care = 0.68
            frame_order = 0.42
        elif via == "witnessed_offense":
            if context.startswith("dialogue_"):
                frame_care = 0.56
                frame_order = 0.2
            else:
                frame_order = 0.72
                frame_care = 0.18
        else:
            frame_order = 0.44
            frame_care = 0.28

        if actor_role in {"guard", "scout"}:
            if approval < 0.0:
                frame_chaos += 0.36
                frame_care += 0.12
                frame_order *= 0.82
            else:
                frame_order += 0.22
        elif actor_role in {"worker", "resident", "civilian", "clerk", "cashier", "merchant", "shopkeeper", "manager"} and approval < 0.0:
            frame_care += 0.24

        interest = (
            (frame_order * profile["order"])
            + (frame_chaos * profile["chaos"])
            + (frame_care * profile["care"])
        ) * profile["share"]
        if (
            via == "witnessed_offense"
            and not context.startswith("dialogue_")
            and approval < 0.0
            and actor_role in {"player", "runner", "thief", "dealer", "drunk", "civilian", "resident"}
            and profile["chaos"] > profile["order"]
        ):
            interest *= 0.42
        if approval > 0.0:
            interest += 0.06 * profile["care"]
        else:
            interest += 0.04 * max(profile["order"], profile["chaos"])
        return _clamp(interest, lo=0.0, hi=1.2)

    def _conflict_side_rumor_interest(self, speaker_eid, entry):
        if not isinstance(entry, dict):
            return 0.0
        profile = self._rumor_worldview_profile(speaker_eid)
        data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
        side_role = self._actor_role_label(data.get("side_eid"))
        against_role = self._actor_role_label(data.get("against_eid"))

        frame_order = 0.0
        frame_chaos = 0.0
        frame_care = 0.34
        if against_role in {"guard", "scout"} and side_role in {"player", "runner", "thief", "dealer", "drunk", "civilian", "resident"}:
            frame_chaos = 0.78
            frame_care += 0.12
        else:
            frame_care += 0.28
            frame_order = 0.36

        if side_role in {"worker", "resident", "civilian", "clerk", "cashier", "merchant", "shopkeeper", "manager"}:
            frame_care += 0.22
        if against_role in {"worker", "resident", "civilian", "clerk", "cashier", "merchant", "shopkeeper", "manager"}:
            frame_care += 0.28
            frame_chaos *= 0.8

        interest = (
            (frame_order * profile["order"])
            + (frame_chaos * profile["chaos"])
            + (frame_care * profile["care"])
        ) * profile["share"]
        if against_role in {"guard", "scout"}:
            if profile["role"] in {"guard", "scout"}:
                interest *= 0.28
            elif profile["order"] > (profile["chaos"] + 0.18):
                interest *= 0.72
        return _clamp(interest, lo=0.0, hi=1.2)

    def _mutate_trait_claim(self, claimed_value, topic):
        traits = getattr(self.sim, "world_traits", {}) or {}
        claim_pools = traits.get("rumor_claim_pools", {}) if isinstance(traits, dict) else {}
        pool = []
        if isinstance(claim_pools, dict):
            pool = list(claim_pools.get(topic, ()) or ())
        if not pool and topic == "cat_toxin_coat":
            pool = list(traits.get("cat_coat_pool", ()) or ())
        pool = [str(value).strip().lower() for value in pool if str(value).strip()]
        if len(pool) <= 1:
            return claimed_value

        try:
            misguided_chance = float(traits.get("misguided_rumor_chance", 0.28))
        except (TypeError, ValueError):
            misguided_chance = 0.28
        misguided_chance = max(0.0, min(0.95, misguided_chance))
        if self.rng.random() >= misguided_chance:
            return claimed_value

        alternatives = [value for value in pool if value != claimed_value]
        if not alternatives:
            return claimed_value
        return self.rng.choice(alternatives)

    def _ambient_rumor_pass(self, memories, positions):
        for eid, memory in memories.items():
            pos = positions.get(eid)
            if not pos:
                continue
            if not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=4):
                continue
            if (self.sim.tick + eid) % self.ambient_check_divisor != 0:
                continue

            nearest = None
            nearest_dist = None
            for rumor in self.recent_offenses:
                if rumor["offender_eid"] == eid:
                    continue
                if rumor["z"] != pos.z:
                    continue
                dist = _manhattan(pos.x, pos.y, rumor["x"], rumor["y"])
                if dist > 8:
                    continue
                if nearest is None or dist < nearest_dist:
                    nearest = rumor
                    nearest_dist = dist

            if not nearest:
                continue

            offender_eid = nearest["offender_eid"]
            if _observer_turns_blind_eye_to_offense(
                self.sim,
                eid,
                offender_eid,
                action=nearest["action"],
                context=nearest["context"],
                offense_score=nearest["offense_score"],
            ):
                continue
            existing = self._recent_offense_strength(memory, offender_eid, max_age=35)
            base = (nearest["offense_score"] / 100.0) * max(0.15, 0.48 - (nearest_dist * 0.045))
            rumor_strength = max(0.08, min(0.65, base))
            if existing >= rumor_strength - 0.04:
                continue

            memory.remember(
                tick=self.sim.tick,
                kind="offense",
                strength=rumor_strength,
                offender_eid=offender_eid,
                action=nearest["action"],
                context=nearest["context"],
                offense_score=nearest["offense_score"],
                offense_tier=nearest["offense_tier"],
                x=nearest["x"],
                y=nearest["y"],
                z=nearest["z"],
                via="ambient_rumor",
                incident_id=nearest.get("incident_id"),
            )

    def _social_rumor_pass(self, memories, socials, positions):
        shares = 0
        for from_eid, social in socials.items():
            source_memory = memories.get(from_eid)
            source_pos = positions.get(from_eid)
            if not source_memory or not source_pos:
                continue
            if not _detail_tick_allowed(self.sim, source_pos, from_eid, coarse_divisor=4):
                continue
            if (self.sim.tick + from_eid) % 4 != 0:
                continue

            strongest = self._strongest_recent_offense(source_memory)
            if not strongest:
                continue

            data = strongest["data"]
            offender_eid = data.get("offender_eid")
            incident_id = data.get("incident_id")
            if offender_eid is None:
                continue

            ranked_bonds = sorted(
                social.bonds.items(),
                key=lambda row: (row[1]["trust"] * 0.65) + (row[1]["closeness"] * 0.35),
                reverse=True,
            )
            for to_eid, bond in ranked_bonds:
                if bond["trust"] < 0.55 or bond["closeness"] < 0.45:
                    continue

                target_memory = memories.get(to_eid)
                target_pos = positions.get(to_eid)
                if not target_memory or not target_pos:
                    continue
                if target_pos.z != source_pos.z:
                    continue
                if _manhattan(source_pos.x, source_pos.y, target_pos.x, target_pos.y) > 6:
                    continue

                key = (from_eid, to_eid, incident_id if incident_id is not None else offender_eid)
                last_tick = self.last_share_tick.get(key, -10_000)
                if self.sim.tick - last_tick < self.share_cooldown_ticks:
                    continue

                source_strength = float(strongest["strength"])
                shared_strength = source_strength * (0.52 + (bond["trust"] * 0.32))
                shared_strength = max(0.08, min(0.9, shared_strength))
                if _observer_turns_blind_eye_to_offense(
                    self.sim,
                    to_eid,
                    offender_eid,
                    action=data.get("action"),
                    context=data.get("context", "ordinary"),
                    offense_score=int(data.get("offense_score", 0) or 0),
                ):
                    continue

                existing = self._recent_offense_strength(target_memory, offender_eid, max_age=35)
                if existing >= shared_strength - 0.03:
                    continue

                target_memory.remember(
                    tick=self.sim.tick,
                    kind="offense",
                    strength=shared_strength,
                    offender_eid=offender_eid,
                    action=data.get("action"),
                    context=data.get("context", "ordinary"),
                    offense_score=int(data.get("offense_score", 0)),
                    offense_tier=data.get("offense_tier"),
                    x=data.get("x", source_pos.x),
                    y=data.get("y", source_pos.y),
                    z=data.get("z", source_pos.z),
                    via="social_rumor",
                    source_eid=from_eid,
                    incident_id=incident_id,
                )

                self.last_share_tick[key] = self.sim.tick
                shares += 1
                self.sim.emit(Event(
                    "rumor_shared",
                    incident_id=incident_id,
                    from_eid=from_eid,
                    to_eid=to_eid,
                    offender_eid=offender_eid,
                    strength=round(shared_strength, 3),
                    offense_tier=data.get("offense_tier"),
                ))
                break

        return shares

    def _social_actor_reputation_pass(self, memories, socials, positions):
        shares = 0
        for from_eid, social in socials.items():
            source_memory = memories.get(from_eid)
            source_pos = positions.get(from_eid)
            if not source_memory or not source_pos:
                continue
            if not _detail_tick_allowed(self.sim, source_pos, from_eid, coarse_divisor=4):
                continue
            if (self.sim.tick + from_eid) % 4 != 0:
                continue

            strongest = self._strongest_recent_actor_reputation(source_memory, max_age=320)
            if not strongest:
                continue

            source_data = strongest.get("data", {}) if isinstance(strongest.get("data"), dict) else {}
            actor_eid = source_data.get("actor_eid")
            if actor_eid is None:
                continue
            try:
                approval = float(source_data.get("approval", 0.0) or 0.0)
            except (TypeError, ValueError):
                approval = 0.0
            if abs(approval) < 0.12:
                continue

            ranked_bonds = sorted(
                social.bonds.items(),
                key=lambda row: (row[1]["trust"] * 0.65) + (row[1]["closeness"] * 0.35),
                reverse=True,
            )
            for to_eid, bond in ranked_bonds:
                if bond["trust"] < 0.58 or bond["closeness"] < 0.46:
                    continue
                if actor_eid == to_eid:
                    continue
                interest = self._actor_reputation_rumor_interest(from_eid, strongest)
                if interest < 0.18:
                    continue

                target_memory = memories.get(to_eid)
                target_pos = positions.get(to_eid)
                if not target_memory or not target_pos:
                    continue
                if target_pos.z != source_pos.z:
                    continue
                if _manhattan(source_pos.x, source_pos.y, target_pos.x, target_pos.y) > 6:
                    continue

                sign = 1 if approval > 0.0 else -1
                key = (from_eid, to_eid, "actor_reputation", actor_eid, sign)
                last_tick = self.last_share_tick.get(key, -10_000)
                if self.sim.tick - last_tick < self.share_cooldown_ticks:
                    continue

                source_strength = float(strongest.get("strength", 0.0) or 0.0)
                shared_strength = max(
                    0.08,
                    min(0.86, source_strength * (0.42 + (bond["trust"] * 0.24)) * (0.7 + (interest * 0.55))),
                )
                shared_approval = _clamp(approval * (0.78 + (bond["trust"] * 0.08) + (min(1.0, interest) * 0.18)), lo=-1.0, hi=1.0)
                incoming_score = abs(shared_approval) * shared_strength
                existing = self._recent_actor_reputation_strength(
                    target_memory,
                    actor_eid,
                    approval_sign=sign,
                    max_age=220,
                )
                if existing >= incoming_score - 0.03:
                    continue

                target_memory.remember(
                    tick=self.sim.tick,
                    kind="actor_reputation",
                    strength=shared_strength,
                    actor_eid=actor_eid,
                    approval=round(shared_approval, 3),
                    against_eid=source_data.get("against_eid"),
                    source_eid=from_eid,
                    via="social_rumor",
                )

                self.last_share_tick[key] = self.sim.tick
                shares += 1
                break

        return shares

    def _social_conflict_side_pass(self, memories, socials, positions):
        shares = 0
        for from_eid, social in socials.items():
            source_memory = memories.get(from_eid)
            source_pos = positions.get(from_eid)
            if not source_memory or not source_pos:
                continue
            if not _detail_tick_allowed(self.sim, source_pos, from_eid, coarse_divisor=4):
                continue
            if (self.sim.tick + from_eid) % 5 != 0:
                continue

            strongest = self._strongest_recent_conflict_side(source_memory, max_age=140)
            if not strongest:
                continue

            source_data = strongest.get("data", {}) if isinstance(strongest.get("data"), dict) else {}
            side_eid = source_data.get("side_eid")
            against_eid = source_data.get("against_eid")
            if side_eid is None or against_eid is None or side_eid == against_eid:
                continue

            ranked_bonds = sorted(
                social.bonds.items(),
                key=lambda row: (row[1]["trust"] * 0.68) + (row[1]["closeness"] * 0.32),
                reverse=True,
            )
            for to_eid, bond in ranked_bonds:
                if bond["trust"] < 0.62 or bond["closeness"] < 0.5:
                    continue
                if to_eid in {side_eid, against_eid}:
                    continue
                interest = self._conflict_side_rumor_interest(from_eid, strongest)
                if interest < 0.22:
                    continue

                target_memory = memories.get(to_eid)
                target_pos = positions.get(to_eid)
                if not target_memory or not target_pos:
                    continue
                if target_pos.z != source_pos.z:
                    continue
                if _manhattan(source_pos.x, source_pos.y, target_pos.x, target_pos.y) > 6:
                    continue

                key = (from_eid, to_eid, "conflict_side", side_eid, against_eid)
                last_tick = self.last_share_tick.get(key, -10_000)
                if self.sim.tick - last_tick < self.share_cooldown_ticks:
                    continue

                source_strength = float(strongest.get("strength", 0.0) or 0.0)
                shared_strength = max(
                    0.1,
                    min(0.9, source_strength * (0.4 + (bond["trust"] * 0.28)) * (0.72 + (interest * 0.52))),
                )
                existing = self._recent_conflict_side_strength(
                    target_memory,
                    side_eid,
                    against_eid,
                    max_age=140,
                )
                if existing >= shared_strength - 0.03:
                    continue

                target_memory.remember(
                    tick=self.sim.tick,
                    kind="conflict_side",
                    strength=shared_strength,
                    side_eid=side_eid,
                    against_eid=against_eid,
                    source_eid=source_data.get("source_eid", from_eid),
                    target_eid=source_data.get("target_eid"),
                    x=source_data.get("x", source_pos.x),
                    y=source_data.get("y", source_pos.y),
                    z=source_data.get("z", source_pos.z),
                    via="social_rumor",
                )

                existing_side_view = self._recent_actor_reputation_strength(
                    target_memory,
                    side_eid,
                    approval_sign=1,
                    max_age=220,
                )
                side_score = 0.34 * max(0.1, shared_strength)
                if existing_side_view < side_score - 0.02:
                    target_memory.remember(
                        tick=self.sim.tick,
                        kind="actor_reputation",
                        strength=max(0.08, shared_strength * 0.72),
                        actor_eid=side_eid,
                        approval=round(min(0.68, 0.28 + (shared_strength * 0.24)), 3),
                        against_eid=against_eid,
                        source_eid=from_eid,
                        via="social_rumor",
                    )

                existing_against_view = self._recent_actor_reputation_strength(
                    target_memory,
                    against_eid,
                    approval_sign=-1,
                    max_age=220,
                )
                against_score = 0.4 * max(0.1, shared_strength)
                if existing_against_view < against_score - 0.02:
                    target_memory.remember(
                        tick=self.sim.tick,
                        kind="actor_reputation",
                        strength=max(0.08, shared_strength * 0.78),
                        actor_eid=against_eid,
                        approval=round(max(-0.74, -0.34 - (shared_strength * 0.26)), 3),
                        against_eid=side_eid,
                        source_eid=from_eid,
                        via="social_rumor",
                    )

                self.last_share_tick[key] = self.sim.tick
                shares += 1
                break

        return shares

    def _social_world_trait_pass(self, memories, socials, positions):
        shares = 0
        for from_eid, social in socials.items():
            source_memory = memories.get(from_eid)
            source_pos = positions.get(from_eid)
            if not source_memory or not source_pos:
                continue
            if not _detail_tick_allowed(self.sim, source_pos, from_eid, coarse_divisor=4):
                continue
            if (self.sim.tick + from_eid) % 5 != 0:
                continue

            strongest = self._strongest_recent_world_trait(source_memory, topic=None, max_age=220)
            if not strongest:
                continue

            source_data = strongest["data"]
            topic = str(source_data.get("topic", "world_trait")).strip().lower()
            claimed_value = _world_trait_claim_value(source_data)
            if not topic or not claimed_value:
                continue

            ranked_bonds = sorted(
                social.bonds.items(),
                key=lambda row: (row[1]["trust"] * 0.65) + (row[1]["closeness"] * 0.35),
                reverse=True,
            )
            for to_eid, bond in ranked_bonds:
                if bond["trust"] < 0.5 or bond["closeness"] < 0.4:
                    continue

                target_memory = memories.get(to_eid)
                target_pos = positions.get(to_eid)
                if not target_memory or not target_pos:
                    continue
                if target_pos.z != source_pos.z:
                    continue
                if _manhattan(source_pos.x, source_pos.y, target_pos.x, target_pos.y) > 6:
                    continue

                spread_claim = self._mutate_trait_claim(claimed_value, topic=topic)
                key = (from_eid, to_eid, topic, spread_claim)
                last_tick = self.last_share_tick.get(key, -10_000)
                if self.sim.tick - last_tick < self.share_cooldown_ticks:
                    continue

                source_strength = float(strongest["strength"])
                shared_strength = source_strength * (0.5 + (bond["trust"] * 0.32))
                shared_strength = max(0.08, min(0.9, shared_strength))

                existing = self._recent_world_trait_strength(
                    target_memory,
                    topic=topic,
                    claimed_value=spread_claim,
                    max_age=220,
                )
                if existing >= shared_strength - 0.04:
                    continue

                target_memory.remember(
                    tick=self.sim.tick,
                    kind="world_trait",
                    strength=shared_strength,
                    topic=topic,
                    claimed_value=spread_claim,
                    is_true=bool(source_data.get("is_true", False)) and spread_claim == claimed_value,
                    via="social_rumor",
                    source_eid=from_eid,
                    tone=source_data.get("tone", "rumor"),
                )

                self.last_share_tick[key] = self.sim.tick
                shares += 1
                break

        return shares

    def update(self):
        self.recent_offenses = [
            rumor
            for rumor in self.recent_offenses
            if self.sim.tick - rumor["tick"] <= self.max_age_ticks
        ]

        memories = self.sim.ecs.get(NPCMemory)
        positions = self.sim.ecs.get(Position)
        socials = self.sim.ecs.get(NPCSocial)

        self._ambient_rumor_pass(memories, positions)
        shares = self._social_rumor_pass(memories, socials, positions)
        shares += self._social_actor_reputation_pass(memories, socials, positions)
        shares += self._social_conflict_side_pass(memories, socials, positions)
        shares += self._social_world_trait_pass(memories, socials, positions)

        self.sim.rumor_stats["active"] = len(self.recent_offenses)
        self.sim.rumor_stats["shares_last_tick"] = shares
