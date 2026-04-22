"""Reusable property interaction, discovery, and purchase runtime.

This module extracts the remaining player-facing property action flow out of
``game/systems.py`` so door interaction, property discovery, generic property
interaction, and purchase logic can evolve on a focused seam.
"""

from engine.events import Event
from game.components import PlayerAssets, PropertyKnowledge
from game.property_access import property_access_controller as _property_access_controller
from game.property_keys import property_lock_state
from game.property_runtime import (
    controller_access_requirement_text as _controller_access_requirement_text,
    property_covering as _property_covering,
    property_display_position as _property_display_position,
    property_focus_position as _property_focus_position,
    property_infrastructure_role as _property_infrastructure_role,
)


class PropertyActionRuntime:
    """Shared player-side property action runtime owned by ``PlayerActionSystem``."""

    def __init__(self, action_system):
        self.action_system = action_system
        self.sim = action_system.sim

    def _support(self):
        # Late import keeps the seam usable while several support helpers still
        # live in ``game.systems``.
        from game import systems as _systems

        return _systems

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

        support = self._support()
        preferred_dir = self.action_system._player_interact_direction(actor_eid) if actor_eid is not None else None
        nearby = sorted(
            nearby,
            key=lambda current: support._interaction_target_order_key(
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
        support = self._support()
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

        support._remember_property_lead_for_actor(
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
            if focus and self._support()._manhattan(pos.x, pos.y, focus[0], focus[1]) <= 1:
                return prop
        return None

    def handle_door_interaction(self, eid, pos):
        support = self._support()
        candidate = support._door_interaction_candidate(
            self.sim,
            pos,
            preferred_dir=self.action_system._player_interact_direction(eid),
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
            success, reason = support._door_close_attempt(self.sim, eid, x, y, z)
            support._log_player_feedback(
                self.sim,
                support._door_action_text(reason, opening=False),
                kind="interaction",
            )
            return bool(success or reason)

        success, reason = support._door_open_attempt(
            self.sim,
            eid,
            x,
            y,
            z,
            allow_override=False,
        )
        if not success and str(reason or "").strip().lower() in {"locked_property", "closed_property", "door_access_denied"}:
            knock = support._door_knock_attempt(
                self.sim,
                eid,
                x,
                y,
                z,
                reason=reason,
                source="interact",
            )
            if bool((knock or {}).get("handled")):
                support._log_player_feedback(
                    self.sim,
                    str((knock or {}).get("message", "")).strip() or support._door_action_text(reason, opening=True),
                    kind="interaction",
                )
                return True
        support._log_player_feedback(
            self.sim,
            support._door_action_text(reason, opening=True),
            kind="interaction",
        )
        return bool(success or reason)

    def handle_door_lock_toggle(self, eid, pos):
        support = self._support()
        candidate = support._door_interaction_candidate(
            self.sim,
            pos,
            preferred_dir=self.action_system._player_interact_direction(eid),
        )
        if not candidate:
            support._log_player_feedback(
                self.sim,
                "No door nearby to lock.",
                kind="interaction",
            )
            return True

        prop = candidate.get("prop")
        if prop:
            self.remember_player_property_discovery(eid, prop, discovery_mode="interact")
        if not isinstance(prop, dict):
            support._log_player_feedback(
                self.sim,
                support._door_lock_action_text("not_property_door"),
                kind="interaction",
            )
            return True

        access_entry = self.action_system._property_lock_access_for(eid, prop)

        x = int(candidate["x"])
        y = int(candidate["y"])
        z = int(candidate["z"])
        state = candidate.get("state") or {}
        lock_state = property_lock_state(prop)
        currently_locked = bool(lock_state.get("locked"))
        access_mode = str((access_entry or {}).get("mode", "authorized")).strip().lower() or "authorized"

        if bool(state.get("open", False)):
            if not access_entry:
                controller = _property_access_controller(self.sim, prop)
                support._log_player_feedback(
                    self.sim,
                    support._door_lock_action_text(
                        "lock_access_denied",
                        requirement=_controller_access_requirement_text(controller),
                    ),
                    kind="interaction",
                )
                return True
            success, reason = support._door_close_attempt(self.sim, eid, x, y, z)
            if not success:
                support._log_player_feedback(
                    self.sim,
                    support._door_lock_action_text(reason),
                    kind="interaction",
                )
                return True
            if currently_locked:
                support._log_player_feedback(
                    self.sim,
                    support._door_lock_action_text("closed_locked"),
                    kind="interaction",
                )
                return True
            success = support._set_property_locked_override(
                prop,
                locked=True,
                tick=self.sim.tick,
                method=f"{access_mode}_manual_lock",
            )
            support._log_player_feedback(
                self.sim,
                support._door_lock_action_text("closed_then_locked" if success else "not_property_door"),
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
                    support._log_player_feedback(
                        self.sim,
                        support._door_lock_action_text("unlocked"),
                        kind="interaction",
                    )
                    return True
                controller = _property_access_controller(self.sim, prop)
                support._log_player_feedback(
                    self.sim,
                    support._door_lock_action_text(
                        reason,
                        requirement=_controller_access_requirement_text(controller),
                    ),
                    kind="interaction",
                )
                return True
            success = support._set_property_locked_override(
                prop,
                locked=False,
                tick=self.sim.tick,
                method=f"{access_mode}_manual_unlock",
            )
            support._log_player_feedback(
                self.sim,
                support._door_lock_action_text("unlocked" if success else "not_property_door"),
                kind="interaction",
            )
            return True

        if not access_entry:
            controller = _property_access_controller(self.sim, prop)
            support._log_player_feedback(
                self.sim,
                support._door_lock_action_text(
                    "lock_access_denied",
                    requirement=_controller_access_requirement_text(controller),
                ),
                kind="interaction",
            )
            return True

        success = support._set_property_locked_override(
            prop,
            locked=True,
            tick=self.sim.tick,
            method=f"{access_mode}_manual_lock",
        )
        support._log_player_feedback(
            self.sim,
            support._door_lock_action_text("locked" if success else "not_property_door"),
            kind="interaction",
        )
        return True

    def handle_interact_action(self, eid, pos):
        prop = self.active_interact_property_near(pos)
        npc_eid = None if prop else self.action_system._npc_for_player_action(eid, pos, radius=1)
        if npc_eid is not None:
            self.sim.emit(Event(
                "npc_interact",
                eid=eid,
                npc_eid=npc_eid,
                x=pos.x,
                y=pos.y,
                z=pos.z,
            ))
            return

        if self.handle_door_interaction(eid, pos):
            return

        if not prop:
            vehicle_prop = self.action_system._vehicle_for_player_action(eid=eid, pos=pos, radius=1)
            if vehicle_prop is not None:
                self.action_system._enter_vehicle(eid=eid, pos=pos, vehicle_prop=vehicle_prop)
                return

        if not prop:
            prop = self.sim.property_at(pos.x, pos.y, pos.z)
        if not prop:
            prop = self.property_for_player_action(pos, radius=1, actor_eid=eid)
        if not prop:
            self.sim.emit(Event("interact_empty", eid=eid, x=pos.x, y=pos.y, z=pos.z))
            return

        self.remember_player_property_discovery(eid, prop, discovery_mode="interact")
        self.sim.emit(Event(
            "property_interact",
            eid=eid,
            property_id=prop["id"],
            x=prop["x"],
            y=prop["y"],
            z=prop["z"],
        ))

    def handle_purchase(self, eid, pos):
        prop = self.property_for_player_action(pos, radius=1, actor_eid=eid)
        if not prop:
            self.sim.emit(Event(
                "property_purchase_blocked",
                eid=eid,
                reason="no_property",
            ))
            return

        if str(prop.get("kind", "")).strip().lower() != "building":
            self.sim.emit(Event(
                "property_purchase_blocked",
                eid=eid,
                reason="not_for_sale",
                property_id=prop["id"],
            ))
            return

        if self.player_owns_property(eid, prop):
            self.sim.emit(Event(
                "property_purchase_blocked",
                eid=eid,
                reason="already_owner",
                property_id=prop["id"],
            ))
            return

        assets = self.sim.ecs.get(PlayerAssets).get(eid)
        if not assets:
            self.sim.emit(Event(
                "property_purchase_blocked",
                eid=eid,
                reason="missing_assets",
                property_id=prop["id"],
            ))
            return

        owner_eid = prop.get("owner_eid")
        owner_tag = prop.get("owner_tag")
        for_sale = owner_eid is None or owner_tag in {None, "city"}
        if not for_sale:
            self.sim.emit(Event(
                "property_purchase_blocked",
                eid=eid,
                reason="not_for_sale",
                property_id=prop["id"],
                owner_eid=owner_eid,
                owner_tag=owner_tag,
            ))
            self.action_system._emit_action_offense(
                eid=eid,
                action="purchase_property",
                context="not_for_sale_attempt",
                x=prop["x"],
                y=prop["y"],
                z=prop["z"],
            )
            return

        metadata = prop.get("metadata", {})
        price = max(1, int(metadata.get("purchase_cost", 150)))
        if assets.credits < price:
            self.sim.emit(Event(
                "property_purchase_blocked",
                eid=eid,
                reason="insufficient_funds",
                property_id=prop["id"],
                price=price,
                credits=assets.credits,
            ))
            return

        old_owner = owner_eid
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


__all__ = ["PropertyActionRuntime"]
