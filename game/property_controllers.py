"""Property controller, access panel, and linked terminal runtime.

This extraction moves ``PropertySystem`` out of ``game/systems.py`` so
controller sync, credential issuance, and exterior panel/terminal handling can
evolve on their own focused seam alongside the now-separate property ingress
runtime.
"""

from engine.events import Event
from engine.systems import System
from game import systems as _systems

Inventory = _systems.Inventory
PlayerAssets = _systems.PlayerAssets
PropertyKnowledge = _systems.PropertyKnowledge
PropertyPortfolio = _systems.PropertyPortfolio
_access_override_score_for_actor = _systems._access_override_score_for_actor
_access_tool_context_for = _systems._access_tool_context_for
_access_tool_terms_for_actor = _systems._access_tool_terms_for_actor
_apply_controller_intrusion = _systems._apply_controller_intrusion
_attempt_locked_property_entry_with_sim = _systems._attempt_locked_property_entry_with_sim
_building_id_from_property = _systems._building_id_from_property
_controller_access_requirement_text = _systems._controller_access_requirement_text
_controller_holder_for_actor = _systems._controller_holder_for_actor
_controller_intrusion_access_for_actor = _systems._controller_intrusion_access_for_actor
_controller_intrusion_state = _systems._controller_intrusion_state
_door_tile_is_occupied = _systems._door_tile_is_occupied
_emit_property_lock_tamper_event = _systems._emit_property_lock_tamper_event
_entity_is_downed = _systems._entity_is_downed
_finance_services_for_property = _systems._finance_services_for_property
_int_or_default = _systems._int_or_default
_is_operable_door_aperture = _systems._is_operable_door_aperture
_lock_override_required_for_prop = _systems._lock_override_required_for_prop
_manhattan = _systems._manhattan
_maybe_damage_access_tool = _systems._maybe_damage_access_tool
_property_access_controller = _systems._property_access_controller
_property_access_level = _systems._property_access_level
_property_apertures = _systems._property_apertures
_property_covering = _systems._property_covering
_property_focus_position = _systems._property_focus_position
_property_infrastructure_role = _systems._property_infrastructure_role
_property_metadata = _systems._property_metadata
_resolve_access_skill_check = _systems._resolve_access_skill_check
_site_services_for_property = _systems._site_services_for_property
_world_hour = _systems._world_hour
ensure_actor_has_property_credential = _systems.ensure_actor_has_property_credential
ensure_property_lock = _systems.ensure_property_lock
inventory_matching_property_credential = _systems.inventory_matching_property_credential
inventory_matching_property_key = _systems.inventory_matching_property_key
property_lock_state = _systems.property_lock_state
remove_actor_property_credentials = _systems.remove_actor_property_credentials
_sync_property_access_controller = _systems._sync_property_access_controller


class PropertySystem(System):

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.initialized = False
        self.last_controller_hour = None
        self.sim.events.subscribe("property_interact", self.on_property_interact)
        self.sim.events.subscribe("property_owner_changed", self.on_property_owner_changed)

    def _building_needs_access_panel(self, prop, controller):
        if not isinstance(prop, dict):
            return False
        if str(prop.get("kind", "")).strip().lower() != "building":
            return False

        metadata = _property_metadata(prop)
        if bool(metadata.get("disable_access_panel")):
            return False

        access_level = _property_access_level(prop)
        controller_kind = str(controller.get("kind", "")).strip().lower()
        credential_mode = str(controller.get("credential_mode", "mechanical_key")).strip().lower()
        security_tier = max(1, _int_or_default(controller.get("security_tier"), 1))
        return bool(
            controller_kind in {"owner_schedule", "auto_timer"}
            or credential_mode in {"badge", "biometric"}
            or access_level == "restricted"
            or security_tier >= 3
        )

    def _building_service_terminal_profile(self, prop):
        if not isinstance(prop, dict):
            return None
        if str(prop.get("kind", "")).strip().lower() != "building":
            return None

        metadata = _property_metadata(prop)
        if bool(metadata.get("disable_service_terminal")):
            return None

        finance_services = []
        for service in _finance_services_for_property(prop):
            label = str(service or "").strip().lower()
            if label in {"banking", "insurance"} and label not in finance_services:
                finance_services.append(label)

        site_services = []
        for service in _site_services_for_property(prop):
            label = str(service or "").strip().lower()
            if label in {"intel"} and label not in site_services:
                site_services.append(label)

        if not finance_services and not site_services:
            return None

        service_set = set(finance_services) | set(site_services)
        if service_set == {"banking"}:
            return {
                "name": "ATM Kiosk",
                "fixture_type": "atm_kiosk",
                "glyph": "$",
                "cover_value": 0.38,
                "finance_services": tuple(finance_services),
                "site_services": tuple(site_services),
            }
        if service_set == {"insurance"}:
            return {
                "name": "Claim Terminal",
                "fixture_type": "claim_terminal",
                "glyph": "c",
                "cover_value": 0.36,
                "finance_services": tuple(finance_services),
                "site_services": tuple(site_services),
            }
        if service_set == {"intel"}:
            return {
                "name": "Info Terminal",
                "fixture_type": "service_terminal",
                "glyph": "i",
                "cover_value": 0.32,
                "finance_services": tuple(finance_services),
                "site_services": tuple(site_services),
            }

        prop_name = str(prop.get("name", prop.get("id", "Property"))).strip() or "Property"
        return {
            "name": f"{prop_name} Service Terminal",
            "fixture_type": "service_terminal",
            "glyph": "t",
            "cover_value": 0.34,
            "finance_services": tuple(finance_services),
            "site_services": tuple(site_services),
        }

    def _service_terminal_anchor(self, prop, existing_terminal=None):
        focus = _property_focus_position(prop)
        if focus is None:
            return None

        ex, ey, ez = focus
        existing_id = existing_terminal.get("id") if isinstance(existing_terminal, dict) else None
        candidates = (
            (ex + 2, ey + 1, ez),
            (ex - 2, ey + 1, ez),
            (ex + 2, ey + 2, ez),
            (ex - 2, ey + 2, ez),
            (ex, ey + 3, ez),
            (ex + 1, ey + 3, ez),
            (ex - 1, ey + 3, ez),
            (ex + 2, ey, ez),
            (ex - 2, ey, ez),
        )
        for x, y, z in candidates:
            tile = self.sim.tilemap.tile_at(x, y, z)
            if not tile or not tile.walkable:
                continue
            anchored = self.sim.property_at(x, y, z)
            if anchored and anchored.get("id") != existing_id:
                continue
            covering = self.sim.property_covering(x, y, z)
            if covering and covering.get("id") != existing_id:
                continue
            return int(x), int(y), int(z)

        if existing_terminal is not None:
            return (
                int(existing_terminal.get("x", ex)),
                int(existing_terminal.get("y", ey + 2)),
                int(existing_terminal.get("z", ez)),
            )
        return None

    def _ensure_service_terminal(self, prop):
        profile = self._building_service_terminal_profile(prop)
        if profile is None:
            return None

        metadata = _property_metadata(prop)
        terminal_id = str(metadata.get("service_terminal_property_id", "") or "").strip()
        terminal = self.sim.properties.get(terminal_id) if terminal_id else None
        if terminal and _property_infrastructure_role(terminal) != "service_terminal":
            terminal = None

        anchor = self._service_terminal_anchor(prop, existing_terminal=terminal)
        if anchor is None:
            return terminal

        owner_eid = prop.get("owner_eid")
        owner_tag = prop.get("owner_tag")
        terminal_metadata = {
            "archetype": str(profile.get("fixture_type", "service_terminal")),
            "fixture_type": str(profile.get("fixture_type", "service_terminal")),
            "interaction_role": "service_terminal",
            "linked_property_id": prop.get("id"),
            "linked_building_id": _building_id_from_property(prop),
            "finance_services": list(profile.get("finance_services", ())),
            "site_services": list(profile.get("site_services", ())),
            "display_glyph": str(profile.get("glyph", "t"))[:1] or "t",
            "display_color": "property_service",
            "cover_kind": "low",
            "cover_value": float(profile.get("cover_value", 0.34) or 0.34),
            "public": True,
            "chunk": metadata.get("chunk"),
        }

        if terminal is not None:
            self.sim.move_property(terminal["id"], anchor[0], anchor[1], z=anchor[2])
            terminal["name"] = str(profile.get("name", terminal.get("name", "Service Terminal"))).strip() or "Service Terminal"
            terminal["owner_eid"] = owner_eid
            terminal["owner_tag"] = owner_tag
            terminal["metadata"] = terminal_metadata
        else:
            terminal_id = self.sim.register_property(
                name=str(profile.get("name", "Service Terminal")).strip() or "Service Terminal",
                kind="asset",
                x=anchor[0],
                y=anchor[1],
                z=anchor[2],
                owner_eid=owner_eid,
                owner_tag=owner_tag,
                metadata=terminal_metadata,
            )
            terminal = self.sim.properties.get(terminal_id)

        metadata["service_terminal_property_id"] = terminal["id"]
        return terminal

    def _access_panel_anchor(self, prop, existing_panel=None):
        focus = _property_focus_position(prop)
        if focus is None:
            return None

        ex, ey, ez = focus
        existing_id = existing_panel.get("id") if isinstance(existing_panel, dict) else None
        candidates = (
            (ex - 1, ey + 1, ez),
            (ex + 1, ey + 1, ez),
            (ex, ey + 1, ez),
            (ex - 2, ey + 1, ez),
            (ex + 2, ey + 1, ez),
            (ex - 1, ey + 2, ez),
            (ex + 1, ey + 2, ez),
            (ex, ey + 2, ez),
        )
        for x, y, z in candidates:
            tile = self.sim.tilemap.tile_at(x, y, z)
            if not tile or not tile.walkable:
                continue
            anchored = self.sim.property_at(x, y, z)
            if anchored and anchored.get("id") != existing_id:
                continue
            covering = self.sim.property_covering(x, y, z)
            if covering and covering.get("id") != existing_id:
                continue
            return int(x), int(y), int(z)

        if existing_panel is not None:
            return (
                int(existing_panel.get("x", ex)),
                int(existing_panel.get("y", ey + 1)),
                int(existing_panel.get("z", ez)),
            )
        return None

    def _ensure_access_panel(self, prop, controller):
        if not self._building_needs_access_panel(prop, controller):
            return None

        metadata = _property_metadata(prop)
        panel_id = str(metadata.get("access_panel_property_id", "") or "").strip()
        panel = self.sim.properties.get(panel_id) if panel_id else None
        if panel and _property_infrastructure_role(panel) != "access_panel":
            panel = None

        anchor = self._access_panel_anchor(prop, existing_panel=panel)
        if anchor is None:
            return panel

        owner_eid = prop.get("owner_eid")
        owner_tag = prop.get("owner_tag")
        prop_name = str(prop.get("name", prop.get("id", "Property"))).strip() or "Property"
        panel_name = f"{prop_name} Access Panel"
        panel_metadata = {
            "archetype": "access_panel",
            "fixture_type": "access_panel",
            "interaction_role": "access_panel",
            "linked_property_id": prop.get("id"),
            "linked_building_id": _building_id_from_property(prop),
            "controller_kind": str(controller.get("kind", "")),
            "controller_fixture": str(controller.get("fixture_label", "")),
            "controller_security_tier": max(1, _int_or_default(controller.get("security_tier"), 1)),
            "controller_requirement": _controller_access_requirement_text(controller),
            "display_glyph": "r",
            "display_color": "property_service" if bool(controller.get("electronic")) else "property_asset",
            "cover_kind": "low",
            "cover_value": 0.24,
            "public": True,
            "chunk": metadata.get("chunk"),
        }

        if panel is not None:
            self.sim.move_property(panel["id"], anchor[0], anchor[1], z=anchor[2])
            panel["name"] = panel_name
            panel["owner_eid"] = owner_eid
            panel["owner_tag"] = owner_tag
            panel["metadata"] = panel_metadata
        else:
            panel_id = self.sim.register_property(
                name=panel_name,
                kind="asset",
                x=anchor[0],
                y=anchor[1],
                z=anchor[2],
                owner_eid=owner_eid,
                owner_tag=owner_tag,
                metadata=panel_metadata,
            )
            panel = self.sim.properties.get(panel_id)

        metadata["access_panel_property_id"] = panel["id"]
        return panel

    def _emit_access_panel_event(self, event_type, *, eid, panel_prop, target_prop, controller, **data):
        panel_name = str(panel_prop.get("name", panel_prop.get("id", "access panel"))).strip() or "access panel"
        target_name = str(target_prop.get("name", target_prop.get("id", "property"))).strip() or "property"
        self.sim.emit(Event(
            event_type,
            eid=eid,
            property_id=panel_prop.get("id"),
            property_name=panel_name,
            target_property_id=target_prop.get("id"),
            target_property_name=target_name,
            requirement=_controller_access_requirement_text(controller),
            credential_mode=str(controller.get("credential_mode", "mechanical_key")).strip().lower() or "mechanical_key",
            security_tier=max(1, _int_or_default(controller.get("security_tier"), 1)),
            open_now=controller.get("open_now"),
            **data,
        ))

    def _property_key_entry_for(self, eid, prop):
        inventory = self.sim.ecs.get(Inventory).get(eid)
        if not inventory or not isinstance(prop, dict):
            return None
        state = property_lock_state(prop)
        if not state["key_id"]:
            return None
        return inventory_matching_property_key(
            inventory,
            property_id=prop.get("id"),
            key_id=state["key_id"],
        )

    def _property_credential_access_for(self, eid, prop):
        if not isinstance(prop, dict):
            return None

        kind = str(prop.get("kind", "")).strip().lower()
        if kind != "building":
            entry = self._property_key_entry_for(eid, prop)
            if not entry:
                return None
            return {
                "mode": "mechanical_key",
                "entry": entry,
                "reason": "key",
            }

        intrusion_access = _controller_intrusion_access_for_actor(self.sim, eid, prop)
        if intrusion_access:
            return {
                "mode": str(intrusion_access.get("mode", "badge")).strip().lower() or "badge",
                "entry": None,
                "reason": str(intrusion_access.get("reason", "spoofed_access")).strip().lower() or "spoofed_access",
            }

        controller = _property_access_controller(self.sim, prop)
        required_tier = max(1, _int_or_default(controller.get("required_credential_tier"), 1))
        inventory = self.sim.ecs.get(Inventory).get(eid)
        if inventory:
            entry = inventory_matching_property_credential(
                inventory,
                property_id=prop.get("id"),
                key_id=property_lock_state(prop)["key_id"],
                allowed_kinds=controller.get("accepted_credentials", ()),
                minimum_tier=required_tier,
            )
            if entry:
                return {
                    "mode": str(controller.get("credential_mode", "mechanical_key")).strip().lower() or "mechanical_key",
                    "entry": entry,
                    "reason": "credential",
                }

        if str(controller.get("credential_mode", "")).strip().lower() == "biometric":
            holder = _controller_holder_for_actor(controller, eid)
            if holder and _int_or_default(holder.get("credential_tier"), 0) >= required_tier:
                return {
                    "mode": "biometric",
                    "entry": None,
                    "reason": "biometric_authorization",
                }
        return None

    def _panel_intrusion_profile(self, controller):
        mode = str((controller or {}).get("credential_mode", "") or "").strip().lower()
        if mode == "badge":
            return {
                "mode": "badge_spoof",
                "label": "badge spoof",
                "method": "badge_reader_spoof",
                "duration_ticks": 84,
                "required_delta": -0.85,
            }
        if mode == "biometric":
            return {
                "mode": "biometric_jam",
                "label": "biometric jam",
                "method": "biometric_jam",
                "duration_ticks": 60,
                "required_delta": -0.55,
            }

        controller_kind = str((controller or {}).get("kind", "") or "").strip().lower()
        if controller_kind == "owner_schedule":
            return {
                "mode": "schedule_latch",
                "label": "schedule latch",
                "method": "schedule_latch",
                "duration_ticks": 90,
                "required_delta": -0.7,
                "tool_context": "schedule_controller",
            }
        if controller_kind == "auto_timer":
            return {
                "mode": "relay_latch",
                "label": "relay latch",
                "method": "relay_latch",
                "duration_ticks": 96,
                "required_delta": -0.8,
                "tool_context": "relay_controller",
            }
        return None

    def _attempt_access_panel_intrusion(self, eid, panel_prop, target_prop, controller):
        profile = self._panel_intrusion_profile(controller)
        if profile is None or not isinstance(target_prop, dict) or not isinstance(panel_prop, dict):
            return None

        entry = _property_focus_position(target_prop)
        if entry is None:
            return {
                "success": False,
                "reason": "offline",
                "profile": profile,
            }

        base_context = _access_tool_context_for(self.sim, target_prop)
        context = str(profile.get("tool_context", "") or "").strip().lower() or base_context
        tool_terms = _access_tool_terms_for_actor(self.sim, eid, target_prop, context=context)
        score = _access_override_score_for_actor(self.sim, eid, tool_terms=tool_terms)
        required = max(
            1.0,
            _lock_override_required_for_prop(self.sim, target_prop, tool_terms=tool_terms)
            + float(profile.get("required_delta", 0.0)),
        )
        if not tool_terms.get("enabled") and score + 1.5 < required:
            return None

        method = str(profile.get("method", profile["mode"])).strip().lower() or profile["mode"]
        _emit_property_lock_tamper_event(
            self.sim,
            eid,
            target_prop,
            x=int(panel_prop.get("x", entry[0])),
            y=int(panel_prop.get("y", entry[1])),
            z=int(panel_prop.get("z", entry[2])),
            method=method,
        )
        attempt = _resolve_access_skill_check(
            self.sim,
            eid=eid,
            prop=target_prop,
            context=context,
            channel="panel_intrusion",
            score=score,
            required=required,
            tool_terms=tool_terms,
            allow_fumble=True,
        )
        if not attempt["success"]:
            _maybe_damage_access_tool(
                self.sim,
                eid,
                tool_terms,
                prop=target_prop,
                score=attempt["score"],
                required=attempt["required"],
                context=context,
                channel="panel_intrusion",
                fumbled=attempt["fumbled"],
            )
            return {
                "success": False,
                "reason": "panel_intrusion_fumble" if attempt["fumbled"] else "panel_intrusion_failed",
                "profile": profile,
                "method": method,
            }

        _apply_controller_intrusion(
            target_prop,
            mode=profile["mode"],
            tick=self.sim.tick,
            duration=profile["duration_ticks"],
            actor_eid=eid if profile["mode"] == "badge_spoof" else None,
            source_item_id=tool_terms.get("selected_item_id", ""),
            method=method,
        )
        metadata = _property_metadata(target_prop)
        metadata["property_locked"] = False
        metadata["property_override_tick"] = int(self.sim.tick)
        metadata["property_override_method"] = method
        intrusion = _controller_intrusion_state(self.sim, target_prop)
        return {
            "success": True,
            "reason": method,
            "profile": profile,
            "method": method,
            "intrusion": intrusion,
            "source_item_id": str(tool_terms.get("selected_item_id", "") or "").strip().lower(),
        }

    def _handle_access_panel_interaction(self, eid, panel_prop):
        target_prop = _systems._infrastructure_target_property(self.sim, panel_prop)
        if not target_prop or str(target_prop.get("kind", "")).strip().lower() != "building":
            self.sim.emit(Event(
                "access_panel_blocked",
                eid=eid,
                property_id=panel_prop.get("id"),
                property_name=str(panel_prop.get("name", panel_prop.get("id", "access panel"))).strip() or "access panel",
                reason="offline",
            ))
            return

        controller = _property_access_controller(self.sim, target_prop)
        entry = _property_focus_position(target_prop)
        lock_state = property_lock_state(target_prop)
        credential = self._property_credential_access_for(eid, target_prop)
        intrusion_state = _controller_intrusion_state(self.sim, target_prop)

        if credential:
            metadata = _property_metadata(target_prop)
            metadata["property_locked"] = False
            metadata["property_override_tick"] = int(self.sim.tick)
            metadata["property_override_method"] = "authorized_panel_access"
            self._emit_access_panel_event(
                "access_panel_used",
                eid=eid,
                panel_prop=panel_prop,
                target_prop=target_prop,
                controller=controller,
                outcome="authorized_open" if lock_state["locked"] or controller.get("open_now") is False else "status",
                method=str(credential.get("reason", "credential")).strip().lower() or "credential",
                intrusion_mode=str(intrusion_state.get("mode", "") or "").strip().lower(),
                intrusion_label=str(intrusion_state.get("label", "") or "").strip(),
                intrusion_remaining_ticks=int(intrusion_state.get("remaining_ticks", 0) or 0),
            )
            return

        if not lock_state["locked"] and controller.get("open_now") is not False:
            self._emit_access_panel_event(
                "access_panel_used",
                eid=eid,
                panel_prop=panel_prop,
                target_prop=target_prop,
                controller=controller,
                outcome="status",
                method="status_check",
                intrusion_mode=str(intrusion_state.get("mode", "") or "").strip().lower(),
                intrusion_label=str(intrusion_state.get("label", "") or "").strip(),
                intrusion_remaining_ticks=int(intrusion_state.get("remaining_ticks", 0) or 0),
            )
            return

        if entry is None:
            self._emit_access_panel_event(
                "access_panel_blocked",
                eid=eid,
                panel_prop=panel_prop,
                target_prop=target_prop,
                controller=controller,
                reason="offline",
            )
            return

        intrusion_attempt = self._attempt_access_panel_intrusion(eid, panel_prop, target_prop, controller)
        if intrusion_attempt is not None:
            if not intrusion_attempt.get("success"):
                profile = intrusion_attempt.get("profile") or {}
                self._emit_access_panel_event(
                    "access_panel_blocked",
                    eid=eid,
                    panel_prop=panel_prop,
                    target_prop=target_prop,
                    controller=controller,
                    reason=str(intrusion_attempt.get("reason", "panel_intrusion_failed")).strip().lower() or "panel_intrusion_failed",
                    intrusion_mode=str(profile.get("mode", "") or "").strip().lower(),
                    intrusion_label=str(profile.get("label", "") or "").strip(),
                    method=str(intrusion_attempt.get("method", profile.get("method", "")) or "").strip().lower(),
                )
                return

            intrusion = intrusion_attempt.get("intrusion") or {}
            controller = _property_access_controller(self.sim, target_prop)
            self._emit_access_panel_event(
                "access_panel_used",
                eid=eid,
                panel_prop=panel_prop,
                target_prop=target_prop,
                controller=controller,
                outcome="intrusion_open",
                method=str(intrusion_attempt.get("method", intrusion.get("method", "")) or "").strip().lower(),
                intrusion_mode=str(intrusion.get("mode", "") or "").strip().lower(),
                intrusion_label=str(intrusion.get("label", "") or "").strip(),
                intrusion_remaining_ticks=int(intrusion.get("remaining_ticks", 0) or 0),
                source_item_id=str(intrusion_attempt.get("source_item_id", "") or "").strip().lower(),
            )
            return

        success, reason = _attempt_locked_property_entry_with_sim(
            self.sim,
            eid,
            target_prop,
            target_x=entry[0],
            target_y=entry[1],
            target_z=entry[2],
        )
        if not success:
            self._emit_access_panel_event(
                "access_panel_blocked",
                eid=eid,
                panel_prop=panel_prop,
                target_prop=target_prop,
                controller=controller,
                reason=reason,
            )
            return

        self._emit_access_panel_event(
            "access_panel_used",
            eid=eid,
            panel_prop=panel_prop,
            target_prop=target_prop,
            controller=controller,
            outcome="override_open",
            method=reason,
        )

    def on_property_interact(self, event):
        eid = event.data.get("eid")
        if eid != self.player_eid:
            return
        prop = self.sim.properties.get(event.data.get("property_id"))
        if _property_infrastructure_role(prop) != "access_panel":
            return
        event.data["handled"] = True
        self._handle_access_panel_interaction(eid, prop)

    def _owned_property_lock_tier(self, prop):
        access_level = _property_access_level(prop)
        metadata = _property_metadata(prop)
        security_features = metadata.get("security_features", ())
        security_bonus = 0
        if isinstance(security_features, (list, tuple, set)):
            security_bonus = min(2, len([feature for feature in security_features if str(feature).strip()]))
        base = 2 if access_level == "protected" else 3
        return max(1, min(5, base + security_bonus))

    def _sync_access_controllers(self, hour=None):
        if hour is None:
            hour = _world_hour(self.sim)
        for prop in list(self.sim.properties.values()):
            if str(prop.get("kind", "")).strip().lower() != "building":
                continue
            controller = _sync_property_access_controller(self.sim, prop, hour=hour)
            self._ensure_access_panel(prop, controller)
            self._ensure_service_terminal(prop)
            self._sync_property_doors(prop, controller, emit_closing_warning=True)

    def _sync_intrusion_properties(self, hour=None):
        if hour is None:
            hour = _world_hour(self.sim)
        for prop in list(self.sim.properties.values()):
            if str(prop.get("kind", "")).strip().lower() != "building":
                continue
            metadata = _property_metadata(prop)
            if not isinstance(metadata, dict):
                continue
            if "controller_intrusion_mode" not in metadata and "controller_intrusion_until_tick" not in metadata:
                continue

            previous_holders = tuple(metadata.get("access_authorized_holders", ()))
            controller = _sync_property_access_controller(self.sim, prop, hour=hour)
            self._ensure_access_panel(prop, controller)
            self._ensure_service_terminal(prop)

            owner_eid = prop.get("owner_eid")
            lock_if_controlled = bool(controller.get("managed_lock") and controller.get("open_now") is not True)
            if owner_eid is not None and not controller.get("managed_lock"):
                lock_if_controlled = True
            ensure_property_lock(
                prop,
                locked=lock_if_controlled,
                lock_tier=self._owned_property_lock_tier(prop),
                key_label=str(prop.get("name", prop.get("id", "Property"))).strip() or "Property",
            )
            credential_state = self._sync_property_credentials(
                prop,
                controller,
                previous_holders=previous_holders,
            )
            if lock_if_controlled and owner_eid is not None and not credential_state["authorized_access"]:
                metadata["property_locked"] = False
            self._sync_property_doors(prop, controller)

    def _sync_property_credentials(self, prop, controller, *, previous_holders=()):
        if not isinstance(prop, dict):
            return {
                "issued_any": False,
                "created_any": False,
                "authorized_access": False,
            }

        previous_map = {}
        if isinstance(previous_holders, (list, tuple)):
            for holder in previous_holders:
                if not isinstance(holder, dict):
                    continue
                holder_eid = holder.get("eid")
                if holder_eid is None:
                    continue
                try:
                    previous_map[int(holder_eid)] = holder
                except (TypeError, ValueError):
                    continue

        current_map = {}
        for holder in controller.get("authorized_holders", ()):
            if not isinstance(holder, dict):
                continue
            holder_eid = holder.get("eid")
            if holder_eid is None:
                continue
            try:
                current_map[int(holder_eid)] = holder
            except (TypeError, ValueError):
                continue

        for holder_eid, previous in previous_map.items():
            current = current_map.get(holder_eid)
            previous_kind = str(previous.get("credential_kind", "mechanical_key")).strip().lower()
            previous_tier = _int_or_default(previous.get("credential_tier"), 1)
            if current:
                current_kind = str(current.get("credential_kind", "mechanical_key")).strip().lower()
                current_tier = _int_or_default(current.get("credential_tier"), 1)
                if current_kind == previous_kind and current_tier == previous_tier:
                    continue
            remove_actor_property_credentials(self.sim, holder_eid, prop)

        issued_any = False
        created_any = False
        direct_authorized = False
        owner_tag = str(prop.get("owner_tag", "")).strip().lower() or "npc"
        for holder_eid, holder in current_map.items():
            credential_kind = str(holder.get("credential_kind", "mechanical_key")).strip().lower() or "mechanical_key"
            credential_tier = _int_or_default(holder.get("credential_tier"), 1)
            holder_role = str(holder.get("role", "staff")).strip().lower() or "staff"
            if credential_kind == "biometric_authorization":
                direct_authorized = True
                continue
            issued, _instance_id, created = ensure_actor_has_property_credential(
                self.sim,
                holder_eid,
                prop,
                owner_tag=owner_tag,
                credential_kind=credential_kind,
                holder_role=holder_role,
                credential_tier=credential_tier,
            )
            issued_any = issued_any or bool(issued)
            created_any = created_any or bool(created)

        return {
            "issued_any": bool(issued_any),
            "created_any": bool(created_any),
            "authorized_access": bool(issued_any or direct_authorized or not current_map),
        }

    def _iter_property_doors(self, prop):
        for aperture in _property_apertures(prop):
            kind = str(aperture.get("kind", "door") or "door").strip().lower() or "door"
            if _is_operable_door_aperture(kind):
                yield aperture

    def _default_door_open_state(self, prop, controller, *, aperture=None):
        kind = str((aperture or {}).get("kind", "door") or "door").strip().lower() or "door"
        ordinary = bool((aperture or {}).get("ordinary", kind == "door"))
        if _property_access_level(prop) == "public" and kind == "door" and ordinary:
            return controller.get("open_now") is not False
        return False

    def _closing_warning_speaker(self, prop, controller):
        if not isinstance(prop, dict):
            return None

        positions = self.sim.ecs.get(_systems.Position)
        focus = _property_focus_position(prop)
        focus_x = int(focus[0]) if focus else int(prop.get("x", 0))
        focus_y = int(focus[1]) if focus else int(prop.get("y", 0))
        focus_z = int(focus[2]) if focus else int(prop.get("z", 0))
        prop_id = str(prop.get("id", "")).strip()

        candidates = []
        for holder in tuple(controller.get("authorized_holders", ()) or ()):
            if not isinstance(holder, dict):
                continue
            holder_eid = holder.get("eid")
            if holder_eid is None:
                continue
            pos = positions.get(holder_eid)
            if not pos or int(pos.z) != focus_z:
                continue
            if _entity_is_downed(self.sim, holder_eid):
                continue

            holder_cover = _property_covering(self.sim, pos.x, pos.y, pos.z)
            nearby = _manhattan(int(pos.x), int(pos.y), focus_x, focus_y) <= 6
            same_property = bool(holder_cover and str(holder_cover.get("id", "")).strip() == prop_id)
            if not same_property and not nearby:
                continue

            role = str(holder.get("role", "staff") or "staff").strip().lower() or "staff"
            role_rank = 0 if role == "owner" else 1 if role == "manager" else 2
            distance = _manhattan(int(pos.x), int(pos.y), focus_x, focus_y)
            candidates.append((role_rank, distance, int(holder_eid)))

        if not candidates:
            return None

        candidates.sort()
        return candidates[0][2]

    def _sync_property_doors(self, prop, controller, *, emit_closing_warning=False):
        if not isinstance(prop, dict):
            return

        auto_managed = _property_access_level(prop) == "public"
        player_pos = self.sim.ecs.get(_systems.Position).get(self.player_eid)
        player_cover = (
            _property_covering(self.sim, player_pos.x, player_pos.y, player_pos.z)
            if player_pos
            else None
        )
        player_inside = bool(player_cover and player_cover.get("id") == prop.get("id"))
        warned = False

        for aperture in self._iter_property_doors(prop):
            ax = int(aperture.get("x", prop.get("x", 0)))
            ay = int(aperture.get("y", prop.get("y", 0)))
            az = int(aperture.get("z", prop.get("z", 0)))
            kind = str(aperture.get("kind", "door") or "door").strip().lower() or "door"
            ordinary = bool(aperture.get("ordinary", kind == "door"))
            existing = self.sim.door_state_at(ax, ay, az)
            default_open = bool(self._default_door_open_state(prop, controller, aperture=aperture))
            previous_open = bool(existing.get("open", default_open)) if isinstance(existing, dict) else bool(default_open)
            previous_auto = bool(existing.get("auto_managed")) if isinstance(existing, dict) else False

            if auto_managed or existing is None or previous_auto != auto_managed or "open" not in existing:
                desired_open = bool(default_open)
            else:
                desired_open = bool(existing.get("open", False))

            if not desired_open and _door_tile_is_occupied(self.sim, ax, ay, az):
                desired_open = True

            self.sim.set_door_state(
                ax,
                ay,
                az,
                open=desired_open,
                kind=kind,
                ordinary=ordinary,
                property_id=prop.get("id"),
                auto_managed=auto_managed,
            )
            self.sim.apply_door_state(ax, ay, az)

            if emit_closing_warning and player_inside and previous_open and not desired_open:
                warned = True

        if warned:
            self.sim.emit(Event(
                "property_closing_time_warning",
                eid=self.player_eid,
                property_id=prop.get("id"),
                property_name=str(prop.get("name", prop.get("id", "property"))).strip() or "property",
                speaker_eid=self._closing_warning_speaker(prop, controller),
            ))

    def _sync_from_registry(self):
        portfolios = self.sim.ecs.get(PropertyPortfolio)
        knowledges = self.sim.ecs.get(PropertyKnowledge)
        assets = self.sim.ecs.get(PlayerAssets).get(self.player_eid)
        current_hour = _world_hour(self.sim)

        for portfolio in portfolios.values():
            portfolio.owned_property_ids.clear()

        if assets:
            assets.owned_property_ids.clear()

        for property_id, prop in list(self.sim.properties.items()):
            owner_eid = prop.get("owner_eid")
            owner_tag = prop.get("owner_tag")
            if str(prop.get("kind", "")).strip().lower() == "building":
                metadata = _property_metadata(prop)
                previous_holders = tuple(metadata.get("access_authorized_holders", ())) if isinstance(metadata, dict) else ()
                controller = _sync_property_access_controller(self.sim, prop, hour=current_hour)
                self._ensure_access_panel(prop, controller)
                self._ensure_service_terminal(prop)
                lock_if_controlled = bool(controller.get("managed_lock") and controller.get("open_now") is not True)
                if owner_eid is not None and not controller.get("managed_lock"):
                    lock_if_controlled = True
                ensure_property_lock(
                    prop,
                    locked=lock_if_controlled,
                    lock_tier=self._owned_property_lock_tier(prop),
                    key_label=str(prop.get("name", prop.get("id", "Property"))).strip() or "Property",
                )
                credential_state = self._sync_property_credentials(
                    prop,
                    controller,
                    previous_holders=previous_holders,
                )
                if lock_if_controlled and owner_eid is not None and not credential_state["authorized_access"]:
                    metadata = prop.get("metadata")
                    if isinstance(metadata, dict):
                        metadata["property_locked"] = False
                self._sync_property_doors(prop, controller)

            if owner_eid is not None:
                owner_portfolio = portfolios.get(owner_eid)
                if owner_portfolio:
                    owner_portfolio.owned_property_ids.add(property_id)

                owner_knowledge = knowledges.get(owner_eid)
                if owner_knowledge:
                    owner_knowledge.remember(
                        property_id,
                        owner_eid=owner_eid,
                        owner_tag=owner_tag,
                        confidence=1.0,
                        tick=self.sim.tick,
                        anchored=True,
                        anchor_kind="owned",
                    )

            if assets and owner_eid == self.player_eid:
                assets.owned_property_ids.add(property_id)

    def on_property_owner_changed(self, event):
        old_owner_eid = event.data.get("old_owner_eid")
        property_id = event.data.get("property_id")
        prop = self.sim.properties.get(property_id)
        if old_owner_eid is not None and isinstance(prop, dict):
            remove_actor_property_credentials(self.sim, old_owner_eid, prop)
        self._sync_from_registry()
        self.sim.property_registry_dirty = False
        self.last_controller_hour = _world_hour(self.sim)

    def update(self):
        current_hour = _world_hour(self.sim)
        registry_dirty = bool(getattr(self.sim, "property_registry_dirty", False))
        if not self.initialized or registry_dirty:
            self._sync_from_registry()
            self.sim.property_registry_dirty = False
            self.last_controller_hour = current_hour
            self.initialized = True
            return

        if current_hour != self.last_controller_hour:
            self._sync_access_controllers(hour=current_hour)
            self.last_controller_hour = current_hour
        else:
            self._sync_intrusion_properties(hour=current_hour)


__all__ = ["PropertySystem"]
