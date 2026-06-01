"""Reusable property interaction, discovery, and purchase runtime.

This module extracts the remaining player-facing property action flow out of
``game/systems.py`` so door interaction, property discovery, generic property
interaction, and purchase logic can evolve on a focused seam.
"""

from engine.events import Event
from game.components import PlayerAssets, PropertyKnowledge
from game.property_door_wait import _door_knock_attempt
from game.property_doors import (
    _door_action_text,
    _door_close_attempt,
    _door_interaction_candidate,
    _door_lock_action_text,
    _door_open_attempt,
    _set_door_locked_state,
    _set_property_locked_override,
)
from game.property_access import property_access_controller as _property_access_controller
from game.property_access import (
    finance_services_for_property as _finance_services_for_property,
    property_is_storefront as _property_is_storefront,
    site_services_for_property as _site_services_for_property,
)
from game.property_keys import property_lock_state
from game.property_runtime import (
    controller_access_requirement_text as _controller_access_requirement_text,
    property_covering as _property_covering,
    property_display_position as _property_display_position,
    property_focus_position as _property_focus_position,
    property_infrastructure_role as _property_infrastructure_role,
    remember_property_lead_for_actor as _remember_property_lead_for_actor,
)
from game.system_support.interaction_ordering import (
    _interaction_target_order_key,
    _manhattan,
    _normalized_direction,
)
from game.system_support.player_feedback import _log_player_feedback


class PropertyActionRuntime:
    """Shared player-side property action runtime owned by ``PlayerActionSystem``."""

    def __init__(self, action_system):
        self.action_system = action_system
        self.sim = action_system.sim

    def player_owns_property(self, eid, prop):
        if not prop:
            return False

        if prop.get("owner_eid") == eid:
            return True

        assets = self.sim.ecs.get(PlayerAssets).get(eid)
        return bool(assets and prop["id"] in assets.owned_property_ids)

    def property_for_player_action(self, pos, radius=1, actor_eid=None):
        prop = _property_covering(self.sim, pos.x, pos.y, pos.z)
        if prop:
            return prop

        nearby = self.sim.properties_in_radius(pos.x, pos.y, pos.z, r=radius)
        if not nearby:
            return None

        preferred_dir = self.action_system._player_interact_direction(actor_eid, pos) if actor_eid is not None else None
        nearby = sorted(
            nearby,
            key=lambda current: _interaction_target_order_key(
                pos.x,
                pos.y,
                int(current.get("x", 0)),
                int(current.get("y", 0)),
                preferred_dir=preferred_dir,
                stable_tiebreaker=(str(current.get("id", "")),),
            ),
        )
        return nearby[0]

    def counts_as_known_location(self, prop):
        if not isinstance(prop, dict):
            return False
        kind = str(prop.get("kind", "") or "").strip().lower()
        if kind in {"asset", "fixture", "vehicle"}:
            return False
        if _property_infrastructure_role(prop) in {"access_panel", "security_post", "service_terminal"}:
            return False
        return True

    def discovery_property_at(self, x, y, z):
        try:
            x = int(x)
            y = int(y)
            z = int(z)
        except (TypeError, ValueError):
            return None

        if self.sim.detail_for_xy(x, y) == "unloaded":
            return None

        prop = self.sim.property_at(x, y, z) or _property_covering(self.sim, x, y, z)
        if self.counts_as_known_location(prop):
            return prop

        for candidate in self.sim.properties.values():
            if not self.counts_as_known_location(candidate):
                continue
            display_pos = _property_display_position(candidate)
            if display_pos and (
                int(display_pos[0]),
                int(display_pos[1]),
                int(display_pos[2]),
            ) == (x, y, z):
                return candidate
            focus = _property_focus_position(candidate)
            if focus and (
                int(focus[0]),
                int(focus[1]),
                int(focus[2]),
            ) == (x, y, z):
                return candidate
        return None

    def remember_player_property_discovery(self, eid, prop, *, discovery_mode="sight", confidence=None):
        if eid != getattr(self.sim, "player_eid", None):
            return False
        if not self.counts_as_known_location(prop):
            return False

        knowledge = self.sim.ecs.get(PropertyKnowledge).get(eid)
        if not knowledge:
            return False

        existing = knowledge.known.get(prop["id"]) if isinstance(knowledge.known, dict) else None
        try:
            prior_confidence = float((existing or {}).get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            prior_confidence = 0.0

        if confidence is None:
            confidence = self.action_system.PLAYER_DISCOVERY_CONFIDENCE.get(
                str(discovery_mode or "sight").strip().lower(),
                0.58,
            )
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.58
        confidence = max(0.0, min(1.0, confidence))
        if prior_confidence + 0.01 >= confidence:
            return False

        _remember_property_lead_for_actor(
            self.sim,
            eid,
            prop,
            confidence=confidence,
        )

        updated = knowledge.known.get(prop["id"]) if isinstance(knowledge.known, dict) else None
        if isinstance(updated, dict):
            updated["anchored"] = True
            updated["anchor_kind"] = str(discovery_mode or "sight").strip().lower() or "sight"
            if updated.get("first_tick") is None:
                updated["first_tick"] = int(getattr(self.sim, "tick", 0))
        try:
            new_confidence = float((updated or {}).get("confidence", prior_confidence) or prior_confidence)
        except (TypeError, ValueError):
            new_confidence = prior_confidence
        if prior_confidence < 0.5 <= new_confidence:
            self.sim.emit(Event(
                "property_self_discovered",
                eid=eid,
                property_id=prop.get("id"),
                property_name=str(prop.get("name", prop.get("id", "location"))).strip() or "location",
                discovery_mode=str(discovery_mode or "sight").strip().lower() or "sight",
                confidence=new_confidence,
            ))
        return new_confidence > prior_confidence + 0.01

    def active_interact_property_near(self, pos):
        for quest in self.sim.quests["active"]:
            objective = quest.get("objective", {})
            if objective.get("type") != "interact_property":
                continue

            property_id = objective.get("property_id")
            prop = self.sim.properties.get(property_id) if property_id else None
            if not prop or prop["z"] != pos.z:
                continue

            focus = _property_focus_position(prop)
            if focus and _manhattan(pos.x, pos.y, focus[0], focus[1]) <= 1:
                return prop
        return None

    def _emit_property_interact(self, eid, prop, *, interaction_mode=None, **extra):
        payload = {
            "eid": eid,
            "property_id": prop["id"],
            "x": prop["x"],
            "y": prop["y"],
            "z": prop["z"],
        }
        if interaction_mode:
            payload["interaction_mode"] = str(interaction_mode).strip().lower()
        if isinstance(extra, dict):
            payload.update(extra)
        self.sim.emit(Event("property_interact", **payload))

    def _emit_interact_empty(self, eid, pos, *, interaction_mode=None):
        payload = {
            "eid": eid,
            "x": pos.x,
            "y": pos.y,
            "z": pos.z,
        }
        if interaction_mode:
            payload["interaction_mode"] = str(interaction_mode).strip().lower()
        self.sim.emit(Event("interact_empty", **payload))

    def _property_supports_services(self, prop):
        if not isinstance(prop, dict):
            return False
        if _property_infrastructure_role(prop) == "service_terminal":
            return True
        if _property_is_storefront(prop):
            return True
        if _finance_services_for_property(prop):
            return True
        if _site_services_for_property(prop):
            return True
        services = [
            str(service).strip().lower()
            for service in list(prop.get("services", ()) or ())
            if str(service).strip()
        ]
        return bool(services)

    def same_space_service_property(self, pos):
        candidates = []
        seen = set()
        for candidate in (
            self.sim.property_at(pos.x, pos.y, pos.z),
            _property_covering(self.sim, pos.x, pos.y, pos.z),
        ):
            if not isinstance(candidate, dict):
                continue
            prop_id = str(candidate.get("id", "")).strip()
            if not prop_id or prop_id in seen:
                continue
            seen.add(prop_id)
            if not self._property_supports_services(candidate):
                continue
            candidates.append(candidate)
        if not candidates:
            return None
        candidates.sort(
            key=lambda prop: (
                0 if _property_infrastructure_role(prop) == "service_terminal" else 1,
                0 if int(prop.get("x", pos.x)) == int(pos.x) and int(prop.get("y", pos.y)) == int(pos.y) else 1,
                str(prop.get("id", "")),
            )
        )
        return candidates[0]

    def hard_traversal_property_at(self, pos):
        if pos is None:
            return None
        prop = self.sim.property_at(pos.x, pos.y, pos.z)
        if not isinstance(prop, dict):
            return None
        metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata"), dict) else {}
        if not bool(metadata.get("hard_traversal")):
            return None
        services = {
            str(service).strip().lower()
            for service in tuple(metadata.get("site_services", ()) or ())
            if str(service).strip()
        }
        if not services:
            return None
        return prop

    def handle_door_interaction(self, eid, pos):
        candidate = _door_interaction_candidate(
            self.sim,
            pos,
            preferred_dir=self.action_system._player_interact_direction(eid, pos),
        )
        if not candidate:
            return False

        prop = candidate.get("prop")
        if prop:
            self.remember_player_property_discovery(eid, prop, discovery_mode="interact")

        x = int(candidate["x"])
        y = int(candidate["y"])
        z = int(candidate["z"])
        state = candidate.get("state") or {}
        is_open = bool(state.get("open", False))

        if is_open:
            success, reason = _door_close_attempt(self.sim, eid, x, y, z)
            _log_player_feedback(
                self.sim,
                _door_action_text(reason, opening=False),
                kind="interaction",
            )
            return bool(success or reason)

        success, reason = _door_open_attempt(
            self.sim,
            eid,
            x,
            y,
            z,
            allow_override=False,
        )
        if not success and str(reason or "").strip().lower() in {"locked_property", "closed_property", "door_access_denied"}:
            knock = _door_knock_attempt(
                self.sim,
                eid,
                x,
                y,
                z,
                reason=reason,
                source="interact",
            )
            if bool((knock or {}).get("handled")):
                _log_player_feedback(
                    self.sim,
                    str((knock or {}).get("message", "")).strip() or _door_action_text(reason, opening=True),
                    kind="interaction",
                )
                return True
        _log_player_feedback(
            self.sim,
            _door_action_text(reason, opening=True),
            kind="interaction",
        )
        return bool(success or reason)

    def handle_door_lock_toggle(self, eid, pos):
        candidate = _door_interaction_candidate(
            self.sim,
            pos,
            preferred_dir=self.action_system._player_interact_direction(eid, pos),
        )
        if not candidate:
            _log_player_feedback(
                self.sim,
                "No door nearby to lock.",
                kind="interaction",
            )
            return True

        prop = candidate.get("prop")
        if prop:
            self.remember_player_property_discovery(eid, prop, discovery_mode="interact")

        access_entry = self.action_system._property_lock_access_for(eid, prop)

        x = int(candidate["x"])
        y = int(candidate["y"])
        z = int(candidate["z"])
        state = candidate.get("state") or {}
        if not isinstance(prop, dict):
            currently_locked = bool(state.get("locked", False))
            if bool(state.get("open", False)):
                success, reason = _door_close_attempt(self.sim, eid, x, y, z)
                if not success:
                    _log_player_feedback(
                        self.sim,
                        _door_lock_action_text(reason),
                        kind="interaction",
                    )
                    return True
                if currently_locked:
                    _log_player_feedback(
                        self.sim,
                        _door_lock_action_text("closed_locked"),
                        kind="interaction",
                    )
                    return True
                success = _set_door_locked_state(self.sim, x, y, z, True)
                _log_player_feedback(
                    self.sim,
                    _door_lock_action_text("closed_then_locked" if success else "not_property_door"),
                    kind="interaction",
                )
                return True

            success = _set_door_locked_state(self.sim, x, y, z, not currently_locked)
            _log_player_feedback(
                self.sim,
                _door_lock_action_text(
                    "unlocked" if currently_locked and success else "locked" if success else "not_property_door"
                ),
                kind="interaction",
            )
            return True

        lock_state = property_lock_state(prop)
        currently_locked = bool(lock_state.get("locked"))
        access_mode = str((access_entry or {}).get("mode", "authorized")).strip().lower() or "authorized"

        if bool(state.get("open", False)):
            if not access_entry:
                controller = _property_access_controller(self.sim, prop)
                _log_player_feedback(
                    self.sim,
                    _door_lock_action_text(
                        "lock_access_denied",
                        requirement=_controller_access_requirement_text(controller),
                    ),
                    kind="interaction",
                )
                return True
            success, reason = _door_close_attempt(self.sim, eid, x, y, z)
            if not success:
                _log_player_feedback(
                    self.sim,
                    _door_lock_action_text(reason),
                    kind="interaction",
                )
                return True
            if currently_locked:
                _log_player_feedback(
                    self.sim,
                    _door_lock_action_text("closed_locked"),
                    kind="interaction",
                )
                return True
            success = _set_property_locked_override(
                prop,
                locked=True,
                tick=self.sim.tick,
                method=f"{access_mode}_manual_lock",
            )
            _log_player_feedback(
                self.sim,
                _door_lock_action_text("closed_then_locked" if success else "not_property_door"),
                kind="interaction",
            )
            return True

        if currently_locked:
            if not access_entry:
                success, reason = self.action_system._attempt_locked_property_entry(
                    eid,
                    prop,
                    target_x=x,
                    target_y=y,
                    target_z=z,
                )
                if success:
                    _log_player_feedback(
                        self.sim,
                        _door_lock_action_text("unlocked"),
                        kind="interaction",
                    )
                    return True
                controller = _property_access_controller(self.sim, prop)
                _log_player_feedback(
                    self.sim,
                    _door_lock_action_text(
                        reason,
                        requirement=_controller_access_requirement_text(controller),
                    ),
                    kind="interaction",
                )
                return True
            success = _set_property_locked_override(
                prop,
                locked=False,
                tick=self.sim.tick,
                method=f"{access_mode}_manual_unlock",
            )
            _log_player_feedback(
                self.sim,
                _door_lock_action_text("unlocked" if success else "not_property_door"),
                kind="interaction",
            )
            return True

        if not access_entry:
            controller = _property_access_controller(self.sim, prop)
            _log_player_feedback(
                self.sim,
                _door_lock_action_text(
                    "lock_access_denied",
                    requirement=_controller_access_requirement_text(controller),
                ),
                kind="interaction",
            )
            return True

        success = _set_property_locked_override(
            prop,
            locked=True,
            tick=self.sim.tick,
            method=f"{access_mode}_manual_lock",
        )
        _log_player_feedback(
            self.sim,
            _door_lock_action_text("locked" if success else "not_property_door"),
            kind="interaction",
        )
        return True

    def _emit_npc_interact(self, eid, npc_eid, pos, **extra):
        payload = {
            "eid": eid,
            "npc_eid": npc_eid,
            "x": pos.x,
            "y": pos.y,
            "z": pos.z,
        }
        if isinstance(extra, dict):
            payload.update(extra)
        self.sim.emit(Event(
            "npc_interact",
            **payload,
        ))

    def _door_candidate_for_player(self, eid, pos, *, preferred_dir=None):
        if preferred_dir is None:
            preferred_dir = self.action_system._player_interact_direction(eid, pos)
        return _door_interaction_candidate(
            self.sim,
            pos,
            preferred_dir=preferred_dir,
        )

    def _door_candidate_is_open(self, candidate):
        return bool(isinstance(candidate, dict) and bool((candidate.get("state") or {}).get("open", False)))

    def _door_candidate_matches_direction(self, candidate, pos, preferred_dir):
        if not isinstance(candidate, dict) or preferred_dir is None:
            return False
        step = _normalized_direction(
            int(candidate.get("x", pos.x)) - int(pos.x),
            int(candidate.get("y", pos.y)) - int(pos.y),
        )
        return step == tuple(preferred_dir)

    def _force_interact_in_last_direction(self, eid, pos):
        preferred_dir = self.action_system._player_interact_direction(eid, pos)
        if preferred_dir is None:
            return False

        candidate = self._door_candidate_for_player(
            eid,
            pos,
            preferred_dir=preferred_dir,
        )
        if self._door_candidate_matches_direction(candidate, pos, preferred_dir) and not self._door_candidate_is_open(candidate):
            return self.handle_door_interaction(eid, pos)

        vehicle_prop = self.action_system._vehicle_for_player_action(
            eid=eid,
            pos=pos,
            radius=1,
            preferred_dir=preferred_dir,
            exact_direction=True,
        )
        if vehicle_prop is not None:
            self.action_system._enter_vehicle(eid=eid, pos=pos, vehicle_prop=vehicle_prop)
            return True

        if self._door_candidate_matches_direction(candidate, pos, preferred_dir):
            return self.handle_door_interaction(eid, pos)

        target_x = int(pos.x) + int(preferred_dir[0])
        target_y = int(pos.y) + int(preferred_dir[1])
        prop = self.sim.property_at(target_x, target_y, pos.z)
        if not prop:
            prop = _property_covering(self.sim, target_x, target_y, pos.z)
        if not prop:
            return False

        self.remember_player_property_discovery(eid, prop, discovery_mode="interact")
        self._emit_property_interact(eid, prop, interaction_mode="physical")
        return True

    def handle_interact_action(self, eid, pos, *, force_direction=False):
        if force_direction and self._force_interact_in_last_direction(eid, pos):
            return

        preferred_dir = self.action_system._player_interact_direction(eid, pos)
        prop = self.active_interact_property_near(pos)
        door_candidate = self._door_candidate_for_player(
            eid,
            pos,
            preferred_dir=preferred_dir,
        )

        if door_candidate and not self._door_candidate_is_open(door_candidate) and self.handle_door_interaction(eid, pos):
            return

        if not prop:
            vehicle_prop = self.action_system._vehicle_for_player_action(
                eid=eid,
                pos=pos,
                radius=1,
                preferred_dir=preferred_dir,
            )
            if vehicle_prop is not None:
                self.action_system._enter_vehicle(eid=eid, pos=pos, vehicle_prop=vehicle_prop)
                return

        if door_candidate and self.handle_door_interaction(eid, pos):
            return

        if not prop:
            prop = self.sim.property_at(pos.x, pos.y, pos.z)
        if not prop:
            prop = self.property_for_player_action(pos, radius=1, actor_eid=eid)
        if not prop:
            self._emit_interact_empty(eid, pos, interaction_mode="physical")
            return

        self.remember_player_property_discovery(eid, prop, discovery_mode="interact")
        self._emit_property_interact(eid, prop, interaction_mode="physical")

    def handle_service_interact_action(self, eid, pos):
        prop = self.same_space_service_property(pos)
        if not isinstance(prop, dict):
            self._emit_interact_empty(eid, pos, interaction_mode="service")
            return False
        self.remember_player_property_discovery(eid, prop, discovery_mode="interact")
        self._emit_property_interact(eid, prop, interaction_mode="service")
        return True

    def handle_talk_action(self, eid, pos):
        npc_eid = self.action_system._talk_npc_for_player_action(eid, pos)
        if npc_eid is None:
            self._emit_interact_empty(eid, pos, interaction_mode="talk")
            return False
        self._emit_npc_interact(eid, npc_eid, pos, allow_distant=True)
        return True

    def handle_purchase(self, eid, pos, *, target_property_id=None):
        context = self.purchase_context(eid, pos, target_property_id=target_property_id)
        reason = str(context.get("reason", "") or "").strip().lower()
        prop = context.get("prop")
        if reason == "no_property":
            self.sim.emit(Event(
                "property_purchase_blocked",
                eid=eid,
                reason="no_property",
            ))
            return False

        if reason == "not_for_sale" and not isinstance(prop, dict):
            self.sim.emit(Event(
                "property_purchase_blocked",
                eid=eid,
                reason="not_for_sale",
            ))
            return False

        if reason == "already_owner":
            self.sim.emit(Event(
                "property_purchase_blocked",
                eid=eid,
                reason="already_owner",
                property_id=context.get("property_id"),
            ))
            return False

        if reason == "missing_assets":
            self.sim.emit(Event(
                "property_purchase_blocked",
                eid=eid,
                reason="missing_assets",
                property_id=context.get("property_id"),
            ))
            return False

        if reason == "not_for_sale":
            self.sim.emit(Event(
                "property_purchase_blocked",
                eid=eid,
                reason="not_for_sale",
                property_id=context.get("property_id"),
                owner_eid=context.get("owner_eid"),
                owner_tag=context.get("owner_tag"),
            ))
            self.action_system._emit_action_offense(
                eid=eid,
                action="purchase_property",
                context="not_for_sale_attempt",
                x=prop["x"],
                y=prop["y"],
                z=prop["z"],
            )
            return False

        if reason == "insufficient_funds":
            self.sim.emit(Event(
                "property_purchase_blocked",
                eid=eid,
                reason="insufficient_funds",
                property_id=context.get("property_id"),
                price=int(context.get("price", 0) or 0),
                credits=int(context.get("credits", 0) or 0),
            ))
            return False

        assets = context.get("assets")
        if assets is None or not isinstance(prop, dict):
            self.sim.emit(Event(
                "property_purchase_blocked",
                eid=eid,
                reason="missing_assets",
                property_id=context.get("property_id"),
            ))
            return False

        price = int(context.get("price", 0) or 0)
        old_owner = context.get("owner_eid")
        assets.credits -= price
        self.sim.assign_property_owner(prop["id"], owner_eid=eid, owner_tag="player")

        self.sim.emit(Event(
            "property_owner_changed",
            property_id=prop["id"],
            old_owner_eid=old_owner,
            new_owner_eid=eid,
        ))
        self.sim.emit(Event(
            "property_purchased",
            eid=eid,
            property_id=prop["id"],
            price=price,
        ))
        self.action_system._emit_action_offense(
            eid=eid,
            action="purchase_property",
            context="ordinary",
            x=prop["x"],
            y=prop["y"],
            z=prop["z"],
        )
        return True

    def purchase_context(self, eid, pos, *, target_property_id=None):
        prop = None
        if target_property_id:
            prop = self.sim.properties.get(target_property_id)
        if not isinstance(prop, dict):
            prop = self.property_for_player_action(pos, radius=1, actor_eid=eid)
        if not isinstance(prop, dict):
            return {
                "allowed": False,
                "reason": "no_property",
                "prop": None,
                "property_id": "",
                "property_name": "",
                "archetype": "",
                "price": 0,
                "credits": 0,
                "owner_eid": None,
                "owner_tag": "",
                "assets": None,
            }

        property_id = str(prop.get("id", "") or "").strip()
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        archetype = str(metadata.get("archetype", prop.get("kind", "")) or "").strip().lower()
        property_name = str(prop.get("name", property_id or "property")).strip() or property_id or "property"
        assets = self.sim.ecs.get(PlayerAssets).get(eid)
        credits = int(max(0, getattr(assets, "credits", 0) or 0)) if assets is not None else 0
        owner_eid = prop.get("owner_eid")
        owner_tag = prop.get("owner_tag")
        price = max(1, int(metadata.get("purchase_cost", 150)))

        if str(prop.get("kind", "")).strip().lower() != "building":
            reason = "not_for_sale"
        elif self.player_owns_property(eid, prop):
            reason = "already_owner"
        elif assets is None:
            reason = "missing_assets"
        elif not (owner_eid is None or owner_tag in {None, "city"}):
            reason = "not_for_sale"
        elif credits < price:
            reason = "insufficient_funds"
        else:
            reason = ""

        return {
            "allowed": not bool(reason),
            "reason": reason,
            "prop": prop,
            "property_id": property_id,
            "property_name": property_name,
            "archetype": archetype,
            "price": int(price),
            "credits": int(credits),
            "owner_eid": owner_eid,
            "owner_tag": str(owner_tag or "").strip(),
            "assets": assets,
        }


__all__ = ["PropertyActionRuntime"]
