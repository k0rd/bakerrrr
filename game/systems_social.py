"""NPC social and eavesdrop runtime extracted from ``game/systems.py``.

This seam keeps day-to-day socialization, overheard chatter, and related
opportunity surfacing together while ``game/systems.py`` remains the
compatibility surface during the monolith peel.
"""

import math
import random

from engine.events import Event
from engine.systems import System
from game import systems as _systems

AI = _systems.AI
CreatureIdentity = _systems.CreatureIdentity
NPCMemory = _systems.NPCMemory
NPCRoutine = _systems.NPCRoutine
NPCSocial = _systems.NPCSocial
NPCTraits = _systems.NPCTraits
NPCWill = _systems.NPCWill
Occupation = _systems.Occupation
Position = _systems.Position
PropertyKnowledge = _systems.PropertyKnowledge
SPECIALTY_OPPORTUNITY_THEMES = _systems.SPECIALTY_OPPORTUNITY_THEMES
_apply_downed_actor_state = _systems._apply_downed_actor_state
_controller_access_requirement_text = _systems._controller_access_requirement_text
_dialogue_hours_text = _systems._dialogue_hours_text
_dialogue_human_join = _systems._dialogue_human_join
_dialogue_lower_start = _systems._dialogue_lower_start
_dialogue_security_tier_text = _systems._dialogue_security_tier_text
_dialogue_speaker_style = _systems._dialogue_speaker_style
_entity_display_name = _systems._entity_display_name
_entity_is_downed = _systems._entity_is_downed
_home_property = _systems._home_property
_int_or_default = _systems._int_or_default
_manhattan = _systems._manhattan
_property_access_controller = _systems._property_access_controller
_property_access_level = _systems._property_access_level
_property_covering = _systems._property_covering
_property_is_storefront = _systems._property_is_storefront
_remember_property_lead_for_actor = _systems._remember_property_lead_for_actor
_shared_observer_can_see_position = _systems._shared_observer_can_see_position
_storefront_illegal_goods_signal = _systems._storefront_illegal_goods_signal
_workplace_property = _systems._workplace_property
_world_trait_claim_text = _systems._world_trait_claim_text
_world_trait_claim_value = _systems._world_trait_claim_value
choose_dialogue_line = _systems.choose_dialogue_line
evaluate_opportunity_facts = _systems.evaluate_opportunity_facts
opportunity_distance_text = _systems.opportunity_distance_text
opportunity_intel_for_observer = _systems.opportunity_intel_for_observer
organization_name = _systems.organization_name
property_org_members = _systems.property_org_members
reveal_opportunity_to_observer = _systems.reveal_opportunity_to_observer

class NPCSocialDynamicsSystem(System):

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.npc_social_dynamics_system = self
        self.sim.events.subscribe("npc_investigate", self.on_npc_investigate)

    def _social_bond(self, speaker_eid, partner_eid):
        social = self.sim.ecs.get(NPCSocial).get(speaker_eid)
        if not social:
            return None
        return social.bonds.get(partner_eid)

    def _social_speaker_style(self, speaker_eid, partner_eid, tone):
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        traits_map = self.sim.ecs.get(NPCTraits)
        pos = positions.get(speaker_eid)
        if not pos:
            return {}
        world = getattr(self.sim, "world", None)
        chunk = world.get_chunk(*self.sim.chunk_coords(pos.x, pos.y)) if world is not None else {}
        district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
        if not isinstance(district, dict):
            district = {}
        area_type = str(district.get("area_type", "city")).strip().lower() or "city"
        district_type = str(district.get("district_type", "unknown")).strip().lower() or "unknown"
        ai = ais.get(speaker_eid)
        role_id = str(getattr(ai, "role", "") or "").strip().lower()
        bond = self._social_bond(speaker_eid, partner_eid) or {}
        bond_score = float(bond.get("trust", 0.0)) + float(bond.get("closeness", 0.0))
        tone_key = "friendly" if bond_score >= 1.0 or tone == "check_in" else "neutral"
        traits = traits_map.get(speaker_eid) or NPCTraits()
        return _dialogue_speaker_style(
            self.sim.seed,
            speaker_eid,
            area_type=area_type,
            district_type=district_type,
            role_id=role_id,
            tone=tone_key,
            empathy=getattr(traits, "empathy", 0.5),
            discipline=getattr(traits, "discipline", 0.5),
        )

    def _say_social(self, bank_id, speaker_eid, partner_eid, tone, *, topic_id="", salt="", **slots):
        return choose_dialogue_line(
            bank_id,
            seed=self.sim.seed,
            npc_eid=speaker_eid,
            topic_id=topic_id,
            count=max(0, int(self.sim.tick // 6)),
            salt=salt,
            style_profile=self._social_speaker_style(speaker_eid, partner_eid, tone),
            **slots,
        )

    def _recent_offense_entry(self, npc_eid, *, max_age=90):
        memory = self.sim.ecs.get(NPCMemory).get(npc_eid)
        if not memory:
            return None
        best = None
        for entry in memory.entries:
            if entry.get("kind") != "offense":
                continue
            if self.sim.tick - int(entry.get("tick", 0)) > max_age:
                continue
            if best is None or float(entry.get("strength", 0.0)) > float(best.get("strength", 0.0)):
                best = entry
        return best

    def _recent_world_trait_entry(self, npc_eid, *, max_age=240):
        memory = self.sim.ecs.get(NPCMemory).get(npc_eid)
        if not memory:
            return None
        best = None
        for entry in memory.entries:
            if entry.get("kind") != "world_trait":
                continue
            if self.sim.tick - int(entry.get("tick", 0)) > max_age:
                continue
            if best is None or float(entry.get("strength", 0.0)) > float(best.get("strength", 0.0)):
                best = entry
        return best

    def _recent_actor_reputation_entry(self, npc_eid, *, max_age=220):
        memory = self.sim.ecs.get(NPCMemory).get(npc_eid)
        if not memory:
            return None
        best = None
        best_score = 0.0
        player_eid = getattr(self.sim, "player_eid", None)
        for entry in list(getattr(memory, "entries", ()) or ()):
            if str(entry.get("kind", "")).strip().lower() != "actor_reputation":
                continue
            age = self.sim.tick - int(entry.get("tick", 0) or 0)
            if age > max_age:
                continue
            data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
            actor_eid = _int_or_default(data.get("actor_eid"), 0)
            if actor_eid <= 0 or actor_eid == int(npc_eid):
                continue
            try:
                approval = float(data.get("approval", 0.0) or 0.0)
            except (TypeError, ValueError):
                approval = 0.0
            if abs(approval) < 0.18:
                continue
            score = abs(approval) * max(0.08, float(entry.get("strength", 0.0) or 0.0))
            via = str(data.get("via", "") or "").strip().lower()
            if via == "job_completion":
                score *= 0.78
            if actor_eid == int(player_eid or -1):
                score += 0.06
            if best is None or score > best_score:
                best = entry
                best_score = score
        return best

    def _recent_conflict_side_entry(self, npc_eid, *, max_age=160):
        memory = self.sim.ecs.get(NPCMemory).get(npc_eid)
        if not memory:
            return None
        best = None
        best_score = 0.0
        for entry in list(getattr(memory, "entries", ()) or ()):
            if str(entry.get("kind", "")).strip().lower() != "conflict_side":
                continue
            age = self.sim.tick - int(entry.get("tick", 0) or 0)
            if age > max_age:
                continue
            data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
            side_eid = _int_or_default(data.get("side_eid"), 0)
            against_eid = _int_or_default(data.get("against_eid"), 0)
            if side_eid <= 0 or against_eid <= 0 or side_eid == against_eid:
                continue
            score = max(0.08, float(entry.get("strength", 0.0) or 0.0))
            if best is None or score > best_score:
                best = entry
                best_score = score
        return best

    def _social_actor_name(self, actor_eid):
        actor_int = _int_or_default(actor_eid, 0)
        if actor_int <= 0:
            return ""
        player_eid = _int_or_default(getattr(self.sim, "player_eid", None), 0)
        if actor_int == player_eid:
            identity = self.sim.ecs.get(CreatureIdentity).get(actor_int)
            if identity:
                label = str(identity.display_name()).replace("_", " ").strip()
                if label and label.lower() not in {"entity", "player"}:
                    return label.title()
            ai = self.sim.ecs.get(AI).get(actor_int)
            role = str(getattr(ai, "role", "") or "").strip().lower()
            if role and role not in {"entity", "player"}:
                return f"that {role.replace('_', ' ')}"
            return "that runner"
        return _entity_display_name(self.sim, actor_int, title_case=True) or "someone"

    def _actor_reputation_chatter_payload(self, speaker_eid, partner_eid, tone):
        entry = self._recent_actor_reputation_entry(speaker_eid)
        if not entry:
            return None
        data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
        actor_eid = _int_or_default(data.get("actor_eid"), 0)
        if actor_eid <= 0 or actor_eid in {_int_or_default(speaker_eid, 0), _int_or_default(partner_eid, 0)}:
            return None
        actor_name = self._social_actor_name(actor_eid)
        if not actor_name:
            return None
        try:
            approval = float(data.get("approval", 0.0) or 0.0)
        except (TypeError, ValueError):
            approval = 0.0
        if abs(approval) < 0.18:
            return None
        via = str(data.get("via", "") or "").strip().lower()
        offense_score = _int_or_default(data.get("offense_score"), 0)
        if approval <= -0.5 or via == "witnessed_damage" or offense_score >= 30:
            reputation_read = "they are getting read like bad news whenever a room gets tense."
        elif approval < 0.0:
            reputation_read = "they have a rough name around the block."
        elif via == "job_completion":
            reputation_read = "people keep saying they come through when work needs doing."
        elif approval >= 0.5:
            reputation_read = "they are getting a solid name with people nearby."
        else:
            reputation_read = "their name is landing a little better than it used to."
        summary = f"{actor_name} {reputation_read}".strip().rstrip(".")
        quote = self._say_social(
            "chatter_actor_reputation",
            speaker_eid,
            partner_eid,
            tone,
            topic_id="chatter_actor_reputation",
            actor_name=actor_name,
            reputation_read=reputation_read,
            reputation_read_lc=_dialogue_lower_start(reputation_read),
        )
        return {
            "topic": "actor_reputation",
            "quote": quote,
            "summary": summary,
            "detail": f"People around here keep reading {actor_name} that way.",
            "channel": "social",
            "priority": "normal" if actor_eid == _int_or_default(getattr(self.sim, "player_eid", None), 0) else "low",
            "actor_eid": actor_eid,
        }

    def _conflict_side_chatter_payload(self, speaker_eid, partner_eid, tone):
        entry = self._recent_conflict_side_entry(speaker_eid)
        if not entry:
            return None
        data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
        side_eid = _int_or_default(data.get("side_eid"), 0)
        against_eid = _int_or_default(data.get("against_eid"), 0)
        if side_eid <= 0 or against_eid <= 0 or side_eid == against_eid:
            return None
        side_name = self._social_actor_name(side_eid)
        against_name = self._social_actor_name(against_eid)
        if not side_name or not against_name or side_name == against_name:
            return None
        conflict_summary = f"people around here are taking {side_name}'s side over {against_name}"
        quote = self._say_social(
            "chatter_conflict_side",
            speaker_eid,
            partner_eid,
            tone,
            topic_id="chatter_conflict_side",
            conflict_summary=conflict_summary,
            conflict_summary_lc=_dialogue_lower_start(conflict_summary),
        )
        return {
            "topic": "conflict_side",
            "quote": quote,
            "summary": conflict_summary[:1].upper() + conflict_summary[1:],
            "detail": f"The room still sounds tilted toward {side_name} against {against_name}.",
            "channel": "social",
            "priority": "normal" if _int_or_default(getattr(self.sim, "player_eid", None), 0) in {side_eid, against_eid} else "low",
            "side_eid": side_eid,
            "against_eid": against_eid,
        }

    def _shared_workplace_prop(self, speaker_eid, partner_eid):
        occupations = self.sim.ecs.get(Occupation)
        speaker_occ = occupations.get(speaker_eid)
        partner_occ = occupations.get(partner_eid)
        speaker_prop = _workplace_property(self.sim, occupation=speaker_occ)
        partner_prop = _workplace_property(self.sim, occupation=partner_occ)
        if not speaker_prop:
            return None
        if partner_prop and str(partner_prop.get("id")) == str(speaker_prop.get("id")):
            return speaker_prop
        return speaker_prop

    def _workplace_supervisor_name(self, prop, speaker_eid, partner_eid):
        if not prop:
            return ""
        members = list(property_org_members(self.sim, prop)) or []
        boss_name = ""
        best_rank = -1
        for row in members:
            row_eid = row.get("eid")
            if row_eid in {speaker_eid, partner_eid}:
                continue
            role = str(row.get("role", "")).strip().lower()
            rank = 0
            if role == "owner":
                rank = 3
            elif role == "manager":
                rank = 2
            elif role:
                rank = 1
            if rank <= best_rank:
                continue
            name = _entity_display_name(self.sim, row_eid, title_case=True)
            if not name:
                continue
            boss_name = name
            best_rank = rank
        if boss_name:
            return boss_name
        owner_eid = prop.get("owner_eid")
        if owner_eid not in {None, speaker_eid, partner_eid}:
            return _entity_display_name(self.sim, owner_eid, title_case=True)
        return ""

    def _social_roll(self, speaker_eid, partner_eid, tone, salt):
        seed = f"{self.sim.seed}:social-roll:{speaker_eid}:{partner_eid}:{self.sim.tick // 6}:{tone}:{salt}"
        return random.Random(seed).random()

    def _social_opportunity_rows_for(self, speaker_eid, *, limit=5):
        player_eid = getattr(self.sim, "player_eid", None)
        if player_eid is None:
            return ()
        rows = evaluate_opportunity_facts(
            self.sim,
            player_eid,
            limit=max(1, int(limit)),
            observer_eid=speaker_eid,
        )
        scoped = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            distance = int(row.get("distance", 99) or 99)
            if distance > 4:
                continue
            scoped.append(row)
        return tuple(scoped)

    def _opportunity_chatter_anchor_name(self, row):
        if not isinstance(row, dict):
            return ""
        requirements = dict(row.get("requirements", {}) or {})
        property_id = str(requirements.get("property_id", "")).strip()
        if property_id:
            prop = self.sim.properties.get(property_id)
            if isinstance(prop, dict):
                return str(prop.get("name", prop.get("id", "site"))).strip()
        return str(requirements.get("property_name", "")).strip()

    def _opportunity_followthrough_chatter_tier(self, row):
        if not isinstance(row, dict):
            return 0
        awareness = str(row.get("awareness_state", "heard")).strip().lower() or "heard"
        source = str(row.get("source", "")).strip().lower()
        try:
            confidence = float(row.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        tier = 0
        if source == "business_scene":
            tier += 2
        elif source == "specialty_theme":
            tier += 1
        if awareness == "confirmed":
            tier += 1
        if confidence >= 0.86:
            tier += 2
        elif confidence >= 0.74:
            tier += 1
        return tier

    def _opportunity_followthrough_chatter_tail(self, row):
        if not isinstance(row, dict):
            return ""
        place_name = str(row.get("anchor_site_name", "")).strip() or self._opportunity_chatter_anchor_name(row)
        organization_name = str(row.get("organization_name", "")).strip()
        contact_name = str(row.get("contact_name", "")).strip()
        contact_role = str(row.get("contact_role", "")).strip().replace("_", " ")
        tier = self._opportunity_followthrough_chatter_tier(row)
        if tier <= 0:
            return ""
        place_lc = place_name.lower()
        org_lc = organization_name.lower()
        if organization_name and place_name and org_lc and org_lc != place_lc and tier >= 3:
            return f"{place_name} runs under {organization_name}."
        if contact_role and place_name and organization_name and org_lc and org_lc != place_lc and tier >= 4:
            return f"The {contact_role} there answers to {organization_name}."
        if contact_role and place_name and tier >= 3:
            return f"The {contact_role} there is the face that repeats."
        if contact_name and place_name and organization_name and org_lc and org_lc != place_lc and tier >= 5:
            return f"{contact_name} is the face there for {organization_name}."
        if contact_name and place_name and tier >= 4:
            return f"{contact_name} is the repeat face at {place_name}."
        return ""

    def _specialty_opportunity_chatter_summary(self, row):
        if not isinstance(row, dict):
            return ""
        kind = str(row.get("kind", "")).strip().lower()
        if kind not in SPECIALTY_OPPORTUNITY_THEMES:
            return ""

        anchor_name = self._opportunity_chatter_anchor_name(row)
        anchor_text = f" around {anchor_name}" if anchor_name else ""

        summary = ""
        if kind == "layover_shuffle":
            summary = f"Traveler turnover{anchor_text} is still hiding small favors, cover, and quick handoffs."
        elif kind == "route_stash":
            summary = f"A route stash{anchor_text} is still hot before the next line turns it over."
        elif kind == "yard_strip":
            summary = f"The hot salvage edge{anchor_text} is still open, and the working crew has not cleaned it out yet."
        elif kind == "field_repair_call":
            summary = f"A quiet repair call{anchor_text} is still moving because somebody cannot afford a public breakdown."
        elif kind == "sightline_check":
            summary = f"The sightline read{anchor_text} is still paying if you want to know who owns the dead ground."
        elif kind == "relay_watch":
            summary = f"The relay watch{anchor_text} is still live after dark if you want the repeat faces."
        elif kind == "refuge_resupply":
            summary = f"Refuge stops{anchor_text} are still short enough that people will trade goodwill for basics."
        elif kind == "spring_run":
            summary = f"The spring run{anchor_text} is still moving if you want to follow who cannot miss the water leg."
        tail = self._opportunity_followthrough_chatter_tail(row)
        return f"{summary} {tail}".strip() if summary and tail else summary

    def _opportunity_chatter_payload(self, speaker_eid, partner_eid, tone):
        rows = list(self._social_opportunity_rows_for(speaker_eid, limit=5))
        if not rows:
            return None

        weighted = []
        for row in rows:
            distance = int(row.get("distance", 0) or 0)
            awareness = str(row.get("awareness_state", "heard")).strip().lower() or "heard"
            risk = str(row.get("risk", "low")).strip().lower() or "low"
            kind = str(row.get("kind", "")).strip().lower()
            weight = 1.0
            weight += max(0.0, 1.8 - (distance * 0.28))
            if awareness == "confirmed":
                weight += 0.4
            if tone == "conspiring" and risk in {"exposed", "hazardous"}:
                weight += 0.45
            if kind == "contract_kill" and tone != "conspiring":
                weight *= 0.4
            weighted.append((max(0.1, weight), row))

        if not weighted:
            return None

        chooser = random.Random(f"{self.sim.seed}:social-opportunity:{speaker_eid}:{partner_eid}:{self.sim.tick // 6}:{tone}")
        total = sum(weight for weight, _row in weighted)
        pick = chooser.uniform(0.0, total)
        running = 0.0
        selected = weighted[-1][1]
        for weight, row in weighted:
            running += weight
            if pick <= running:
                selected = row
                break

        title = str(selected.get("title", "Opportunity")).strip() or "Opportunity"
        summary = self._specialty_opportunity_chatter_summary(selected)
        if not summary:
            summary = str(selected.get("summary", "")).strip() or "might be worth a look"
        followthrough_tail = self._opportunity_followthrough_chatter_tail(selected)
        if followthrough_tail and followthrough_tail.lower() not in summary.lower():
            summary = f"{summary} {followthrough_tail}".strip()
        distance_phrase = opportunity_distance_text(selected.get("distance", 0), selected.get("direction", "HERE"))
        quote = self._say_social(
            "chatter_opportunity",
            speaker_eid,
            partner_eid,
            tone,
            topic_id="chatter_opportunity",
            opportunity_title=title,
            opportunity_summary=summary,
            distance_phrase=distance_phrase,
        )
        confidence = min(0.84, max(0.58, float(selected.get("confidence", 0.58)) + 0.06))
        priority = "high" if str(selected.get("risk", "low")).strip().lower() == "hazardous" else "normal"
        return {
            "topic": "opportunity",
            "quote": quote,
            "summary": f"{title} {distance_phrase}: {summary}",
            "detail": summary,
            "channel": "opportunity",
            "priority": priority,
            "opportunity_id": int(selected.get("id", 0) or 0),
            "confidence_hint": confidence,
        }

    def _illegal_goods_chatter_payload(self, speaker_eid, partner_eid, tone):
        candidates = []
        shared_prop = self._shared_workplace_prop(speaker_eid, partner_eid)
        if shared_prop:
            candidates.append(shared_prop)
        speaker_occ = self.sim.ecs.get(Occupation).get(speaker_eid)
        speaker_routine = self.sim.ecs.get(NPCRoutine).get(speaker_eid)
        work_prop = _workplace_property(self.sim, occupation=speaker_occ, routine=speaker_routine)
        if work_prop and all(str(prop.get("id")) != str(work_prop.get("id")) for prop in candidates):
            candidates.append(work_prop)

        pos = self.sim.ecs.get(Position).get(speaker_eid)
        if pos:
            for prop in self.sim.properties_in_radius(pos.x, pos.y, pos.z, r=3):
                if not _property_is_storefront(prop):
                    continue
                if any(str(existing.get("id")) == str(prop.get("id")) for existing in candidates):
                    continue
                candidates.append(prop)

        best = None
        for prop in candidates:
            signal = _storefront_illegal_goods_signal(self.sim, prop)
            if not signal:
                continue
            score = float(signal.get("confidence", 0.0))
            if best is None or score > best[0]:
                best = (score, prop, signal)
        if best is None:
            return None

        _score, prop, signal = best
        place_name = str(prop.get("name", prop.get("id", "the place"))).strip() or "the place"
        examples = tuple(str(label).strip() for label in signal.get("examples", ()) if str(label).strip())
        example_text = ""
        if examples:
            example_text = _dialogue_human_join(examples[:2])
        quote = self._say_social(
            "chatter_illegal_goods",
            speaker_eid,
            partner_eid,
            tone,
            topic_id="chatter_illegal_goods",
            topic_place=place_name,
        )
        summary = f"{place_name} might move illegal goods"
        detail = f"{place_name} has a quiet reputation for hot goods."
        if example_text:
            detail = f"{place_name} gets mentioned for hot goods like {example_text}."
        return {
            "topic": "illegal_goods",
            "quote": quote,
            "summary": summary,
            "detail": detail,
            "channel": "opportunity",
            "priority": "normal",
            "property_id": prop.get("id"),
            "confidence_hint": float(signal.get("confidence", 0.56)),
            "property_lead_kind": "contraband",
        }

    def _offense_chatter_payload(self, speaker_eid, partner_eid, tone):
        entry = self._recent_offense_entry(speaker_eid)
        if not entry:
            return None
        data = entry.get("data", {})
        offense_tier = str(data.get("offense_tier", "") or "").strip().lower() or "some"
        x = data.get("x")
        y = data.get("y")
        z = data.get("z")
        prop = None
        if x is not None and y is not None and z is not None:
            prop = _property_covering(self.sim, x, y, z) or self.sim.property_at(x, y, z)
        place_name = str(prop.get("name", prop.get("id", "that place"))).strip() if prop else "that place"
        action_text = str(data.get("action", "trouble") or "trouble").replace("_", " ").strip() or "trouble"
        trouble_summary = f"{offense_tier} {action_text} trouble at {place_name}"
        quote = self._say_social(
            "chatter_offense",
            speaker_eid,
            partner_eid,
            tone,
            topic_id="chatter_offense",
            topic_place=place_name,
            trouble_summary=trouble_summary,
        )
        return {
            "topic": "offense",
            "quote": quote,
            "summary": trouble_summary,
            "detail": f"People are still talking about {action_text} trouble at {place_name}.",
            "channel": "opportunity",
            "priority": "normal",
            "property_id": prop.get("id") if isinstance(prop, dict) else None,
        }

    def _world_trait_chatter_payload(self, speaker_eid, partner_eid, tone):
        entry = self._recent_world_trait_entry(speaker_eid)
        if not entry:
            return None
        data = entry.get("data", {})
        topic = str(data.get("topic", "")).strip().lower()
        claim_text = _world_trait_claim_text(topic, _world_trait_claim_value(data)).strip()
        if not claim_text:
            return None
        summary = claim_text.rstrip(".!?")
        quote = self._say_social(
            "chatter_world_trait",
            speaker_eid,
            partner_eid,
            tone,
            topic_id="chatter_world_trait",
            trait_claim=claim_text,
            trait_claim_lc=_dialogue_lower_start(claim_text),
        )
        return {
            "topic": "world_trait",
            "quote": quote,
            "summary": summary,
            "detail": claim_text,
            "channel": "social",
            "priority": "low",
        }

    def _security_chatter_payload(self, speaker_eid, partner_eid, tone):
        prop = self._shared_workplace_prop(speaker_eid, partner_eid)
        if not prop:
            return None
        controller = _property_access_controller(self.sim, prop)
        if not isinstance(controller, dict) or not controller:
            return None
        place_name = str(prop.get("name", prop.get("id", "the place"))).strip() or "the place"
        hours_text = _dialogue_hours_text(controller.get("opening_window"))
        requirement = _controller_access_requirement_text(controller)
        security_text = _dialogue_security_tier_text(controller.get("security_tier"))
        access_level = _property_access_level(prop)
        if access_level == "public" and hours_text:
            security_summary = f"public hours {hours_text}, then {requirement} with {security_text}"
        elif hours_text:
            security_summary = f"{hours_text} with {requirement} and {security_text}"
        else:
            security_summary = f"{requirement} with {security_text}"
        quote = self._say_social(
            "chatter_security",
            speaker_eid,
            partner_eid,
            tone,
            topic_id="chatter_security",
            topic_place=place_name,
            security_summary=security_summary,
            security_summary_lc=_dialogue_lower_start(security_summary),
        )
        return {
            "topic": "security",
            "quote": quote,
            "summary": f"{place_name} runs {security_summary}",
            "detail": f"{place_name} uses {security_summary}.",
            "channel": "opportunity",
            "priority": "normal",
            "property_id": prop.get("id"),
            "confidence_hint": 0.62,
            "property_lead_kind": "access",
        }

    def _supervisor_chatter_payload(self, speaker_eid, partner_eid, tone):
        prop = self._shared_workplace_prop(speaker_eid, partner_eid)
        if not prop:
            return None
        supervisor_name = self._workplace_supervisor_name(prop, speaker_eid, partner_eid)
        if not supervisor_name:
            return None
        place_name = str(prop.get("name", prop.get("id", "the place"))).strip() or "the place"
        quote = self._say_social(
            "chatter_supervisor",
            speaker_eid,
            partner_eid,
            tone,
            topic_id="chatter_supervisor",
            supervisor_name=supervisor_name,
            topic_place=place_name,
        )
        return {
            "topic": "supervisor",
            "quote": quote,
            "summary": f"{supervisor_name} runs {place_name}",
            "detail": f"{supervisor_name} seems to be the one running {place_name}.",
            "channel": "social",
            "priority": "low",
        }

    def _schedule_chatter_payload(self, speaker_eid, partner_eid, tone):
        occupations = self.sim.ecs.get(Occupation)
        occupation = occupations.get(speaker_eid)
        prop = self._shared_workplace_prop(speaker_eid, partner_eid)
        if not occupation or not prop:
            return None
        shift_start = getattr(occupation, "shift_start", None)
        shift_end = getattr(occupation, "shift_end", None)
        shift_text = _dialogue_hours_text((shift_start, shift_end)) if shift_start is not None and shift_end is not None else ""
        controller = _property_access_controller(self.sim, prop)
        public_text = _dialogue_hours_text(controller.get("opening_window")) if isinstance(controller, dict) else ""
        schedule_text = shift_text or public_text
        if not schedule_text:
            return None
        place_name = str(prop.get("name", prop.get("id", "the place"))).strip() or "the place"
        bank_id = "chatter_shift" if shift_text else "chatter_schedule"
        summary = f"staff shift at {place_name} usually runs {schedule_text}" if shift_text else f"{place_name} keeps public hours {schedule_text}"
        detail = f"People on shift at {place_name} usually work {schedule_text}." if shift_text else f"{place_name} keeps public hours around {schedule_text}."
        quote = self._say_social(
            bank_id,
            speaker_eid,
            partner_eid,
            tone,
            topic_id=bank_id,
            topic_place=place_name,
            schedule_text=schedule_text,
        )
        return {
            "topic": "schedule",
            "quote": quote,
            "summary": summary,
            "detail": detail,
            "channel": "opportunity",
            "priority": "low",
            "property_id": prop.get("id"),
            "confidence_hint": 0.58 if shift_text else 0.62,
            "property_lead_kind": "hours",
        }

    def _check_in_chatter_payload(self, speaker_eid, partner_eid, tone):
        occupation = self.sim.ecs.get(Occupation).get(speaker_eid)
        routine = self.sim.ecs.get(NPCRoutine).get(speaker_eid)
        prop = _home_property(self.sim, routine=routine) or _workplace_property(self.sim, occupation=occupation, routine=routine)
        if not prop:
            return None
        place_name = str(prop.get("name", prop.get("id", "things"))).strip() or "things"
        quote = self._say_social(
            "chatter_check_in",
            speaker_eid,
            partner_eid,
            tone,
            topic_id="chatter_check_in",
            topic_place=place_name,
        )
        return {
            "topic": "check_in",
            "quote": quote,
            "summary": f"things at {place_name}",
            "detail": f"They seem to be checking in about {place_name}.",
            "channel": "social",
            "priority": "low",
        }

    def _social_chatter_payload(self, speaker_eid, partner_eid, relation, tone):
        relation = str(relation or "friend").strip().lower() or "friend"
        opportunistic_roll = self._social_roll(speaker_eid, partner_eid, tone, "opportunity")
        contraband_roll = self._social_roll(speaker_eid, partner_eid, tone, "contraband")
        bonus_builders = []
        if tone == "conspiring":
            bonus_builders.extend((
                self._illegal_goods_chatter_payload,
                self._opportunity_chatter_payload,
            ))
        else:
            if opportunistic_roll < 0.18:
                bonus_builders.append(self._opportunity_chatter_payload)
            if contraband_roll < 0.09:
                bonus_builders.append(self._illegal_goods_chatter_payload)
        if tone == "conspiring":
            builders = (
                self._conflict_side_chatter_payload,
                self._actor_reputation_chatter_payload,
                self._security_chatter_payload,
                self._offense_chatter_payload,
                self._supervisor_chatter_payload,
            )
        elif tone == "rambling":
            builders = (
                self._world_trait_chatter_payload,
                self._actor_reputation_chatter_payload,
                self._offense_chatter_payload,
                self._check_in_chatter_payload,
            )
        elif tone == "check_in" or relation in {"family", "partner"}:
            builders = (
                self._check_in_chatter_payload,
                self._conflict_side_chatter_payload,
                self._schedule_chatter_payload,
                self._supervisor_chatter_payload,
            )
        else:
            builders = (
                self._offense_chatter_payload,
                self._actor_reputation_chatter_payload,
                self._conflict_side_chatter_payload,
                self._world_trait_chatter_payload,
                self._schedule_chatter_payload,
                self._supervisor_chatter_payload,
                self._security_chatter_payload,
            )
        for builder in tuple(bonus_builders) + tuple(builders):
            payload = builder(speaker_eid, partner_eid, tone)
            if payload:
                return payload
        return None

    def on_npc_investigate(self, event):
        ally_eid = event.data.get("npc_eid")
        against_eid = event.data.get("source_eid")

        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        socials = self.sim.ecs.get(NPCSocial)
        traits_map = self.sim.ecs.get(NPCTraits)
        wills = self.sim.ecs.get(NPCWill)

        ally_pos = positions.get(ally_eid)
        against_pos = positions.get(against_eid)
        if not ally_pos:
            return

        for npc_eid, social in socials.items():
            if npc_eid == ally_eid:
                continue

            bond = social.bonds.get(ally_eid)
            if not bond:
                continue

            ai = ais.get(npc_eid)
            pos = positions.get(npc_eid)
            if not ai or not pos:
                continue
            if _entity_is_downed(self.sim, npc_eid):
                _apply_downed_actor_state(self.sim, npc_eid, tick=self.sim.tick)
                continue

            if pos.z != ally_pos.z:
                continue

            if _manhattan(pos.x, pos.y, ally_pos.x, ally_pos.y) > 10:
                continue

            traits = traits_map.get(npc_eid) or NPCTraits()
            protect_score = (bond["protectiveness"] * 0.7) + (traits.loyalty * 0.3)
            if protect_score < 0.62:
                continue

            if against_pos and against_pos.z == pos.z:
                target = (against_pos.x, against_pos.y, against_pos.z)
            else:
                target = (ally_pos.x, ally_pos.y, ally_pos.z)

            if ai.state == "protecting" and ai.target_eid == against_eid:
                continue

            ai.state = "protecting"
            ai.target = target
            ai.target_eid = against_eid

            will = wills.get(npc_eid)
            if will:
                will.intent = "protecting"
                will.score = protect_score * 100.0
                will.target = target
                will.target_eid = against_eid
                will.last_tick = self.sim.tick

            self.sim.emit(Event(
                "npc_protect_ally",
                npc_eid=npc_eid,
                ally_eid=ally_eid,
                against_eid=against_eid,
                relation=bond["kind"],
            ))

class EavesdropSystem(System):

    HEARING_RADIUS = 8
    NEW_OPPORTUNITY_MENTIONS = 2
    MENTION_COOLDOWN = 80

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.runs_without_turn = True
        self.sim.events.subscribe("npc_socialized", self.on_npc_socialized)

    def _state(self):
        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            self.sim.world_traits = {}
            traits = self.sim.world_traits
        state = traits.get("eavesdrop_intel")
        if not isinstance(state, dict):
            state = {
                "opportunity_mentions": {},
                "property_mentions": {},
                "recent_mentions": {},
            }
            traits["eavesdrop_intel"] = state
        return state

    def _player_pos(self):
        return self.sim.ecs.get(Position).get(self.player_eid)

    def _can_overhear_position(self, pos, *, radius=None):
        player_pos = self._player_pos()
        if not player_pos or not pos:
            return False
        listen_radius = int(max(1, radius if radius is not None else self.HEARING_RADIUS))
        if int(player_pos.z) == int(pos.z) and _manhattan(player_pos.x, player_pos.y, pos.x, pos.y) <= listen_radius:
            return True
        return bool(_shared_observer_can_see_position(
            self.sim,
            observer_eid=self.player_eid,
            observer_x=player_pos.x,
            observer_y=player_pos.y,
            observer_z=player_pos.z,
            target_x=pos.x,
            target_y=pos.y,
            target_z=pos.z,
            radius=listen_radius,
        ))

    def _can_overhear_social_event(self, npc_eid, partner_eid):
        positions = self.sim.ecs.get(Position)
        npc_pos = positions.get(npc_eid)
        partner_pos = positions.get(partner_eid)
        return self._can_overhear_position(npc_pos) or self._can_overhear_position(partner_pos)

    def _note_mention(self, bucket, key, speaker_eid):
        record = bucket.get(str(key))
        if not isinstance(record, dict):
            record = {"count": 0, "last_tick": -99999, "last_speaker_eid": None}
        count = int(record.get("count", 0))
        last_tick = int(record.get("last_tick", -99999))
        last_speaker = record.get("last_speaker_eid")
        if int(self.sim.tick) - last_tick > self.MENTION_COOLDOWN or last_speaker != speaker_eid:
            count += 1
        record["count"] = count
        record["last_tick"] = int(self.sim.tick)
        record["last_speaker_eid"] = speaker_eid
        bucket[str(key)] = record
        return record

    def _recently_processed(self, dedupe_key):
        state = self._state()
        recent = state.setdefault("recent_mentions", {})
        last_tick = int(recent.get(dedupe_key, -99999))
        if int(self.sim.tick) - last_tick <= 12:
            return True
        recent[dedupe_key] = int(self.sim.tick)
        return False

    def _property_from_event(self, event):
        property_id = event.data.get("property_id")
        if not property_id:
            return None
        return self.sim.properties.get(property_id)

    def _handle_opportunity_hint(self, event, speaker_eid):
        opportunity_id = int(event.data.get("opportunity_id", 0) or 0)
        if opportunity_id <= 0:
            return
        summary = str(event.data.get("summary", "")).strip()
        detail = str(event.data.get("detail", "")).strip()
        priority = str(event.data.get("priority", "low") or "").strip().lower() or "low"
        try:
            hinted_confidence = float(event.data.get("confidence_hint", 0.0) or 0.0)
        except (TypeError, ValueError):
            hinted_confidence = 0.0

        state = self._state()
        mention = self._note_mention(state.setdefault("opportunity_mentions", {}), opportunity_id, speaker_eid)
        current = opportunity_intel_for_observer(self.sim, self.player_eid, opportunity_id)
        previous_confidence = float((current or {}).get("confidence", 0.0))

        if current is None:
            if int(mention.get("count", 0)) < self.NEW_OPPORTUNITY_MENTIONS and priority != "high":
                return
            next_confidence = max(0.58, min(0.78, hinted_confidence or 0.62))
        else:
            next_confidence = max(previous_confidence + 0.08, hinted_confidence, 0.58)
            next_confidence = min(0.92, next_confidence)
            if next_confidence <= previous_confidence + 0.02:
                return

        reveal_opportunity_to_observer(
            self.sim,
            self.player_eid,
            opportunity_id,
            awareness_state="heard",
            confidence=next_confidence,
            source="eavesdrop",
        )
        self.sim.emit(Event(
            "eavesdrop_opportunity_hint",
            eid=self.player_eid,
            npc_eid=speaker_eid,
            opportunity_id=opportunity_id,
            summary=summary,
            detail=detail,
            confidence=next_confidence,
            previous_confidence=previous_confidence,
            mention_count=int(mention.get("count", 0)),
        ))

    def _handle_property_hint(self, event, speaker_eid):
        prop = self._property_from_event(event)
        if not prop:
            return
        lead_kind = str(event.data.get("property_lead_kind", "") or "").strip().lower()
        if not lead_kind:
            topic = str(event.data.get("topic", "") or "").strip().lower()
            lead_kind = {
                "schedule": "hours",
                "security": "access",
                "illegal_goods": "contraband",
            }.get(topic, "")
        if not lead_kind:
            return

        summary = str(event.data.get("summary", "")).strip()
        detail = str(event.data.get("detail", "")).strip()
        try:
            hinted_confidence = float(event.data.get("confidence_hint", 0.0) or 0.0)
        except (TypeError, ValueError):
            hinted_confidence = 0.0

        state = self._state()
        mention = self._note_mention(state.setdefault("property_mentions", {}), prop.get("id"), speaker_eid)
        knowledge = self.sim.ecs.get(PropertyKnowledge).get(self.player_eid)
        existing = knowledge.known.get(prop["id"]) if knowledge else None
        existing_confidence = float(existing.get("confidence", 0.0)) if isinstance(existing, dict) else 0.0
        next_confidence = max(existing_confidence + 0.05, hinted_confidence, 0.52 + (0.06 * max(0, int(mention.get("count", 1)) - 1)))
        next_confidence = min(0.86, next_confidence)
        changed = _remember_property_lead_for_actor(
            self.sim,
            self.player_eid,
            prop,
            source_eid=speaker_eid,
            lead_kind=lead_kind,
            confidence=next_confidence,
        )
        if not changed:
            return
        self.sim.emit(Event(
            "eavesdrop_property_hint",
            eid=self.player_eid,
            npc_eid=speaker_eid,
            property_id=prop.get("id"),
            property_name=str(prop.get("name", prop.get("id", "property"))).strip() or "property",
            lead_kind=lead_kind,
            summary=summary,
            detail=detail,
            confidence=next_confidence,
            mention_count=int(mention.get("count", 0)),
        ))

    def on_npc_socialized(self, event):
        speaker_eid = event.data.get("npc_eid")
        partner_eid = event.data.get("partner_eid")
        if speaker_eid is None or partner_eid is None:
            return
        if not self._can_overhear_social_event(speaker_eid, partner_eid):
            return

        topic = str(event.data.get("topic", "") or "").strip().lower()
        opportunity_id = int(event.data.get("opportunity_id", 0) or 0)
        property_id = event.data.get("property_id")
        dedupe_key = f"{topic}:{opportunity_id}:{property_id}:{speaker_eid}"
        if self._recently_processed(dedupe_key):
            return

        if opportunity_id > 0:
            self._handle_opportunity_hint(event, speaker_eid)
        if property_id is not None and topic in {"schedule", "security", "illegal_goods"}:
            self._handle_property_hint(event, speaker_eid)
