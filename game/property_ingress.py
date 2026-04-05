"""Reusable property ingress runtime.

This module extracts the ingress candidate, profiling, and execution path out
of ``game/systems.py`` so entry attempts can evolve as a shared gameplay seam
instead of living only as inline player-action code.
"""

from engine.events import Event
from engine.tilemap import Tile
from game.components import Position
from game.property_access import (
    PropertyIngressResult,
    _boundary_tile as _property_boundary_tile,
    evaluate_property_access as _evaluate_property_access,
    property_claim_reason as _property_claim_reason,
    property_ingress_context as _property_ingress_context,
)
from game.property_keys import property_lock_state
from game.property_runtime import (
    property_aperture_at as _property_aperture_at,
    property_covering as _property_covering,
)
from game.skills import actor_skill as _actor_skill


class PropertyIngressRuntime:
    """Shared ingress runtime owned by ``PlayerActionSystem`` for now."""

    def __init__(self, action_system):
        self.action_system = action_system
        self.sim = action_system.sim

    def _support(self):
        # Late import keeps this extraction seam usable while the remaining
        # ingress-adjacent helpers still live in ``game.systems``.
        from game import systems as _systems

        return _systems

    def locked_ordinary_entry_property(self, eid, pos, target_x, target_y, target_z):
        prop = _property_covering(self.sim, target_x, target_y, target_z)
        if not prop or str(prop.get("kind", "")).strip().lower() != "building":
            return None

        ingress = _property_ingress_context(
            prop,
            from_x=pos.x,
            from_y=pos.y,
            from_z=pos.z,
            to_x=target_x,
            to_y=target_y,
            to_z=target_z,
        )
        if ingress.ingress_kind != "ordinary_entry":
            return None

        lock_state = property_lock_state(prop)
        if not lock_state["locked"]:
            return None
        if self.action_system._property_credential_access_for(eid, prop):
            return None
        return prop

    def attempt_locked_property_entry(self, eid, prop, *, target_x, target_y, target_z):
        support = self._support()
        return support._attempt_locked_property_entry_with_sim(
            self.sim,
            eid,
            prop,
            target_x=target_x,
            target_y=target_y,
            target_z=target_z,
        )

    def ingress_method_profile(self, eid, prop, ingress, claim_reason):
        support = self._support()
        modes = self.action_system._mode_state_for(eid)
        sneak_active = bool(modes and modes.sneak)
        ingress_kind = str(getattr(ingress, "ingress_kind", "") or "").strip().lower()
        aperture_kind = str(getattr(ingress, "aperture_kind", "") or "").strip().lower()
        side_entry_terms = self.action_system._access_tool_terms_for(eid, prop, context="side_entry")
        door_like_ingress = (
            ingress_kind == "ordinary_entry"
            or (ingress_kind == "alternate_aperture" and support._is_side_aperture(aperture_kind))
        )

        if ingress_kind == "deep_breach":
            return "deep_breach", 10, 12
        if ingress_kind == "boundary_breach":
            return "forced_breach", 8, 10

        if ingress_kind == "alternate_aperture" and support._is_window_aperture(aperture_kind):
            if side_entry_terms.get("enabled") and sneak_active:
                return "quiet_window_entry", 2, 4
            if sneak_active:
                return "careful_window_entry", 4, 6
            return "crash_window_entry", 8, 10

        if door_like_ingress:
            if claim_reason:
                return "authorized_side_entry", 0, 0
            if (
                not side_entry_terms.get("enabled")
                and self.action_system._access_override_score(eid, tool_terms=side_entry_terms)
                >= self.action_system._lock_override_required(prop, tool_terms=side_entry_terms)
            ):
                return "manual_side_entry", 2, 4
            if side_entry_terms.get("enabled"):
                return "jimmied_side_entry", 1, 2
            return "forced_side_entry", 6, 8

        if claim_reason:
            return "authorized_side_entry", 0, 0
        return "forced_side_entry", 5, 7

    def ingress_attempt_profile(self, eid, prop, ingress, claim_reason):
        support = self._support()
        ingress_method, severity_bonus, offense_bonus = self.ingress_method_profile(
            eid,
            prop,
            ingress,
            claim_reason,
        )
        profile = {
            "method": ingress_method,
            "severity_bonus": severity_bonus,
            "offense_bonus": offense_bonus,
            "hostile": ingress_method in {
                "quiet_window_entry",
                "careful_window_entry",
                "crash_window_entry",
                "forced_breach",
                "deep_breach",
            },
            "unauthorized": ingress_method in {
                "manual_side_entry",
                "jimmied_side_entry",
                "forced_side_entry",
            },
            "automatic": ingress_method == "authorized_side_entry",
        }
        if profile["automatic"]:
            return profile

        tool_terms = self.action_system._access_tool_terms_for(eid, prop, context="side_entry")
        score = self.action_system._access_override_score(eid, tool_terms=tool_terms)
        required = self.action_system._lock_override_required(prop, tool_terms=tool_terms)
        ingress_kind = str(getattr(ingress, "ingress_kind", "") or "").strip().lower()
        aperture_kind = str(getattr(ingress, "aperture_kind", "") or "").strip().lower()
        breach_severity = max(0.0, float(getattr(ingress, "breach_severity", 0.0) or 0.0))
        athletics = _actor_skill(self.sim, eid, "athletics")

        if ingress_kind == "alternate_aperture" and support._is_window_aperture(aperture_kind):
            score += max(0.0, athletics - 5.0) * 0.24
            if ingress_method == "quiet_window_entry":
                score += 0.35
            elif ingress_method == "careful_window_entry":
                score += 0.18
            required += 0.35 + (breach_severity * 1.2)
            context = "window_entry"
            channel = "window_entry"
        elif ingress_kind in {"boundary_breach", "deep_breach"}:
            mechanics = _actor_skill(self.sim, eid, "mechanics")
            score += max(0.0, athletics - 5.0) * 0.36
            score += max(0.0, mechanics - 5.0) * 0.14
            required += 0.75 + (breach_severity * 1.9)
            context = "wall_breach"
            channel = "wall_breach"
        else:
            required += 0.2 + (breach_severity * 0.9)
            if ingress_method == "manual_side_entry":
                score += 0.15
            elif ingress_method == "forced_side_entry":
                required += 0.2
            context = "side_entry"
            channel = "door_breach"

        profile["context"] = context
        profile["channel"] = channel
        profile["tool_terms"] = tool_terms
        profile["attempt"] = support._resolve_access_skill_check(
            self.sim,
            eid=eid,
            prop=prop,
            context=context,
            channel=channel,
            score=score,
            required=required,
            tool_terms=tool_terms,
            allow_fumble=True,
        )
        return profile

    def failed_ingress_attempt_text(self, ingress_mode, ingress_method, prop, *, fumbled=False, eid=None):
        support = self._support()
        prop_name = str((prop or {}).get("name", (prop or {}).get("id", "property"))).strip() or "property"
        method = str(ingress_method or "").strip().lower()

        if method in {"quiet_window_entry", "careful_window_entry", "crash_window_entry"}:
            base = f"You {'botch' if fumbled else 'fail'} the window entry at {prop_name}."
        elif method in {"forced_breach", "deep_breach"}:
            base = f"You {'botch' if fumbled else 'fail'} the wall breach at {prop_name}."
        else:
            mode_text = support._ingress_mode_label(ingress_mode)
            if fumbled:
                base = f"You botch the {mode_text} at {prop_name}."
            else:
                base = f"You fail to make the {mode_text} at {prop_name}."

        hint = self.ingress_tool_hint(eid, ingress_mode)
        if hint:
            return f"{base} {hint}".strip()
        return base

    def emit_failed_ingress_attempt(self, eid, candidate, prop, ingress, ingress_method, *, severity_bonus=0, offense_bonus=0):
        support = self._support()
        access = _evaluate_property_access(
            self.sim,
            eid,
            prop,
            x=candidate["x"],
            y=candidate["y"],
            z=candidate["z"],
            breach_severity=ingress.breach_severity,
        )
        witnesses = support._watchers_for_position(
            self.sim,
            candidate["x"],
            candidate["y"],
            candidate["z"],
            exclude_eid=eid,
        )
        severity_score = max(
            18,
            int(access.severity_score) + int(round(float(ingress.breach_severity) * 10.0)),
        )
        severity_score = min(100, severity_score + int(max(0, severity_bonus)))
        self.sim.emit(Event(
            "property_tamper",
            offender_eid=eid,
            property_id=prop["id"],
            owner_eid=prop.get("owner_eid"),
            x=candidate["x"],
            y=candidate["y"],
            z=candidate["z"],
            witnessed=bool(witnesses),
            witness_count=len(witnesses),
            witnesses=tuple(witnesses[:4]),
            access_level=access.access_level,
            severity_score=severity_score,
            severity_label=support._trespass_label_from_score(severity_score),
            standing_reason=access.standing_reason,
            ingress_kind=ingress.ingress_kind,
            aperture_kind=ingress.aperture_kind,
            ingress_method=ingress_method,
            breach_severity=ingress.breach_severity,
        ))
        offense_score = min(
            100,
            self.action_system._offense_score_for("tamper", context="ordinary")
            + int(round(float(ingress.breach_severity) * 12.0))
            + int(max(0, offense_bonus)),
        )
        self.action_system._emit_action_offense(
            eid=eid,
            action="tamper",
            context="ordinary",
            score=offense_score,
            x=candidate["x"],
            y=candidate["y"],
            z=candidate["z"],
        )

    def ingress_mode_matches(self, candidate, ingress_mode):
        support = self._support()
        ingress_mode = str(ingress_mode or "").strip().lower()
        ingress = candidate.get("ingress")
        aperture_kind = str(getattr(ingress, "aperture_kind", "") or "").strip().lower()
        ingress_kind = str(getattr(ingress, "ingress_kind", "") or "").strip().lower()

        if ingress_mode == "side_entry":
            return ingress_kind == "ordinary_entry" or (
                ingress_kind == "alternate_aperture" and support._is_side_aperture(aperture_kind)
            )
        if ingress_mode == "window_entry":
            return ingress_kind == "alternate_aperture" and support._is_window_aperture(aperture_kind)
        if ingress_mode == "forced_breach":
            return ingress_kind in {"boundary_breach", "deep_breach"}
        return True

    def internal_ingress_candidate(self, pos, prop, target_x, target_y, target_z, *, tile=None, aperture=None):
        origin_prop = _property_covering(self.sim, pos.x, pos.y, pos.z)
        if not origin_prop or origin_prop.get("id") != prop.get("id"):
            return None

        if aperture is None:
            aperture = _property_aperture_at(prop, target_x, target_y, target_z)
        if aperture and not bool(aperture.get("ordinary")):
            kind = str(aperture.get("kind", "") or "").strip().lower()
            if kind in {"window", "skylight"}:
                severity = 0.45
            elif kind in {"side_door", "service_door", "employee_door"}:
                severity = 0.22
            else:
                severity = 0.32
            return PropertyIngressResult(
                property_id=prop.get("id") if isinstance(prop, dict) else None,
                from_inside=True,
                to_inside=True,
                entered_bounds=False,
                ingress_kind="alternate_aperture",
                aperture_kind=kind,
                breach_severity=severity,
            )

        if tile is None:
            tile = self.sim.tilemap.tile_at(target_x, target_y, target_z)
        if tile and not tile.walkable and _property_boundary_tile(prop, target_x, target_y, target_z):
            return PropertyIngressResult(
                property_id=prop.get("id") if isinstance(prop, dict) else None,
                from_inside=True,
                to_inside=True,
                entered_bounds=False,
                ingress_kind="boundary_breach",
                aperture_kind="",
                breach_severity=0.58,
            )
        return None

    def adjacent_ingress_candidates(self, pos, ingress_mode=None):
        candidates = []
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            tx = pos.x + dx
            ty = pos.y + dy
            tz = pos.z

            prop = _property_covering(self.sim, tx, ty, tz)
            if not prop or str(prop.get("kind", "") or "").strip().lower() != "building":
                continue

            ingress = _property_ingress_context(
                prop,
                from_x=pos.x,
                from_y=pos.y,
                from_z=pos.z,
                to_x=tx,
                to_y=ty,
                to_z=tz,
            )
            tile = self.sim.tilemap.tile_at(tx, ty, tz)
            aperture = _property_aperture_at(prop, tx, ty, tz)
            if not ingress.entered_bounds:
                ingress = self.internal_ingress_candidate(
                    pos,
                    prop,
                    tx,
                    ty,
                    tz,
                    tile=tile,
                    aperture=aperture,
                )
                if not ingress:
                    continue
            if ingress.ingress_kind in {"ordinary_entry", "alternate_aperture"}:
                priority = 0
            elif tile and not tile.walkable:
                priority = 1
            else:
                continue

            candidates.append({
                "priority": priority,
                "prop": prop,
                "x": tx,
                "y": ty,
                "z": tz,
                "tile": tile,
                "aperture": aperture,
                "ingress": ingress,
            })

        if ingress_mode:
            candidates = [candidate for candidate in candidates if self.ingress_mode_matches(candidate, ingress_mode)]

        candidates.sort(
            key=lambda row: (
                int(row["priority"]),
                float(row["ingress"].breach_severity),
                row["prop"].get("id", ""),
                row["y"],
                row["x"],
            )
        )
        return candidates

    def authorized_side_entry_reason(self, eid, candidate):
        support = self._support()
        pos = self.sim.ecs.get(Position).get(eid)
        prop = candidate["prop"]
        ingress = candidate["ingress"]
        aperture_kind = str(ingress.aperture_kind or "").strip().lower()
        if support._is_window_aperture(aperture_kind):
            return ""
        if not (
            str(ingress.ingress_kind or "").strip().lower() == "ordinary_entry"
            or support._is_side_aperture(aperture_kind)
        ):
            return ""

        access = _evaluate_property_access(
            self.sim,
            eid,
            prop,
            x=candidate["x"],
            y=candidate["y"],
            z=candidate["z"],
            breach_severity=ingress.breach_severity,
        )
        if not access.permitted or not pos:
            return ""

        _, claim_reason = _property_claim_reason(
            self.sim,
            eid,
            prop,
            x=pos.x,
            y=pos.y,
            z=pos.z,
            min_standing=0.52,
        )
        return claim_reason

    def open_ingress_tile(self, candidate, hostile=False):
        support = self._support()
        tile = candidate.get("tile")
        if tile and tile.walkable:
            return

        ingress = candidate["ingress"]
        aperture_kind = str(ingress.aperture_kind or "").strip().lower()
        if (
            str(ingress.ingress_kind or "").strip().lower() == "ordinary_entry"
            or (ingress.ingress_kind == "alternate_aperture" and support._is_side_aperture(aperture_kind))
        ):
            if support._set_door_open_state(
                self.sim,
                int(candidate["x"]),
                int(candidate["y"]),
                int(candidate["z"]),
                True,
            ):
                return
        if not hostile and ingress.ingress_kind == "alternate_aperture" and support._is_window_aperture(aperture_kind):
            glyph = '"'
        elif not hostile and ingress.ingress_kind == "alternate_aperture":
            glyph = "+"
        else:
            glyph = "/"
        self.sim.tilemap.set_tile(
            int(candidate["x"]),
            int(candidate["y"]),
            Tile(walkable=True, transparent=True, glyph=glyph),
            z=int(candidate["z"]),
        )

    def ingress_tool_hint(self, eid, ingress_mode):
        mode = str(ingress_mode or "").strip().lower()
        if mode not in {"side_entry", "window_entry"}:
            return ""
        side_terms = self.action_system._access_tool_terms_for(eid, context="side_entry")
        if side_terms.get("enabled"):
            return "Sneak plus your current tools improve your odds."
        return "A lockpick kit or prybar can help with door breaches and window ingress."

    def missing_ingress_text(self, ingress_mode, *, eid=None):
        ingress_mode = str(ingress_mode or "").strip().lower()
        if ingress_mode == "side_entry":
            base = "No adjacent door to breach."
            hint = self.ingress_tool_hint(eid, ingress_mode)
            return f"{base} {hint}".strip()
        if ingress_mode == "window_entry":
            base = "No adjacent window to climb through."
            hint = self.ingress_tool_hint(eid, ingress_mode)
            return f"{base} {hint}".strip()
        if ingress_mode == "forced_breach":
            return "No adjacent wall to breach."
        return "No adjacent ingress point."

    def ingress_blocked_text(self, reason, ingress_mode, prop, *, eid=None):
        support = self._support()
        mode_text = support._ingress_mode_label(ingress_mode)
        prop_name = str((prop or {}).get("name", (prop or {}).get("id", "property"))).strip() or "property"
        reason_key = str(reason or "").strip().lower()

        if reason_key.startswith("blocked_entity"):
            base = f"Your {mode_text} path into {prop_name} is blocked by someone in the way."
        elif reason_key == "blocked_tile":
            base = f"That {mode_text} entry into {prop_name} is obstructed."
        elif reason_key == "out_of_bounds":
            base = f"That {mode_text} approach is out of bounds."
        else:
            base = f"{mode_text.title()} ingress into {prop_name} is blocked."

        hint = self.ingress_tool_hint(eid, ingress_mode)
        if hint:
            return f"{base} {hint}".strip()
        return base

    def handle_ingress_action(self, eid, pos, ingress_mode):
        support = self._support()
        cover = self.action_system._cover_state_for(eid)
        had_cover = bool(cover and cover.active)
        candidates = self.adjacent_ingress_candidates(pos, ingress_mode=ingress_mode)
        if not candidates:
            support._log_player_feedback(
                self.sim,
                self.missing_ingress_text(ingress_mode, eid=eid),
                kind="movement",
            )
            return

        candidate = candidates[0]
        prop = candidate["prop"]
        ingress = candidate["ingress"]
        claim_reason = self.authorized_side_entry_reason(eid, candidate)
        ingress_profile = self.ingress_attempt_profile(eid, prop, ingress, claim_reason)
        ingress_method = ingress_profile["method"]
        severity_bonus = ingress_profile["severity_bonus"]
        offense_bonus = ingress_profile["offense_bonus"]
        hostile = bool(ingress_profile["hostile"])
        unauthorized_entry = bool(ingress_profile["unauthorized"])

        if not ingress_profile["automatic"]:
            attempt = ingress_profile.get("attempt") or {}
            if not bool(attempt.get("success")):
                self.emit_failed_ingress_attempt(
                    eid,
                    candidate,
                    prop,
                    ingress,
                    ingress_method,
                    severity_bonus=severity_bonus,
                    offense_bonus=offense_bonus,
                )
                support._maybe_damage_access_tool(
                    self.sim,
                    eid,
                    ingress_profile.get("tool_terms") or {},
                    prop=prop,
                    score=attempt.get("score", 0.0),
                    required=attempt.get("required", 0.0),
                    context=ingress_profile.get("context") or "side_entry",
                    channel=ingress_profile.get("channel") or "ingress_attempt",
                    fumbled=bool(attempt.get("fumbled")),
                )
                support._log_player_feedback(
                    self.sim,
                    self.failed_ingress_attempt_text(
                        ingress_mode,
                        ingress_method,
                        prop,
                        fumbled=bool(attempt.get("fumbled")),
                        eid=eid,
                    ),
                    kind="movement",
                )
                return

        self.open_ingress_tile(
            candidate,
            hostile=bool(hostile or ingress_method == "forced_side_entry"),
        )

        moved, reason = support.try_move_entity(
            self.sim,
            eid=eid,
            new_x=candidate["x"],
            new_y=candidate["y"],
            new_z=candidate["z"],
            reason=str(ingress_mode or "ingress"),
        )
        if not moved:
            support._log_player_feedback(
                self.sim,
                self.ingress_blocked_text(reason, ingress_mode, prop, eid=eid),
                kind="movement",
            )
            return

        new_pos = self.sim.ecs.get(Position).get(eid)
        access = _evaluate_property_access(
            self.sim,
            eid,
            prop,
            x=candidate["x"],
            y=candidate["y"],
            z=candidate["z"],
            breach_severity=ingress.breach_severity,
        )
        witnesses = support._watchers_for_position(
            self.sim,
            candidate["x"],
            candidate["y"],
            candidate["z"],
            exclude_eid=eid,
        )

        if hostile:
            severity_score = max(
                24,
                int(access.severity_score) + int(round(float(ingress.breach_severity) * 12.0)),
            )
            severity_score = min(100, severity_score + int(max(0, severity_bonus)))
            severity_label = support._trespass_label_from_score(severity_score)
            self.sim.emit(Event(
                "property_tamper",
                offender_eid=eid,
                property_id=prop["id"],
                owner_eid=prop.get("owner_eid"),
                x=candidate["x"],
                y=candidate["y"],
                z=candidate["z"],
                witnessed=bool(witnesses),
                witness_count=len(witnesses),
                witnesses=tuple(witnesses[:4]),
                access_level=access.access_level,
                severity_score=severity_score,
                severity_label=severity_label,
                standing_reason=access.standing_reason,
                ingress_kind=ingress.ingress_kind,
                aperture_kind=ingress.aperture_kind,
                ingress_method=ingress_method,
                breach_severity=ingress.breach_severity,
            ))
            offense_score = min(
                100,
                self.action_system._offense_score_for("tamper", context="ordinary")
                + int(round(float(ingress.breach_severity) * 14.0))
                + int(max(0, offense_bonus)),
            )
            self.action_system._emit_action_offense(
                eid=eid,
                action="tamper",
                context="ordinary",
                score=offense_score,
                x=candidate["x"],
                y=candidate["y"],
                z=candidate["z"],
            )
        elif unauthorized_entry:
            severity_score = max(
                16,
                int(access.severity_score) + int(round(float(ingress.breach_severity) * 10.0)),
            )
            severity_score = min(100, severity_score + int(max(0, severity_bonus)))
            severity_label = support._trespass_label_from_score(severity_score)
            self.sim.emit(Event(
                "property_trespass",
                offender_eid=eid,
                property_id=prop["id"],
                owner_eid=prop.get("owner_eid"),
                x=candidate["x"],
                y=candidate["y"],
                z=candidate["z"],
                witnessed=bool(witnesses),
                witness_count=len(witnesses),
                witnesses=tuple(witnesses[:4]),
                access_level=access.access_level,
                severity_score=severity_score,
                severity_label=severity_label,
                standing_reason=access.standing_reason,
                currently_open=access.currently_open,
                current_hour=access.current_hour,
                ingress_kind=ingress.ingress_kind,
                aperture_kind=ingress.aperture_kind,
                ingress_method=ingress_method,
                breach_severity=ingress.breach_severity,
            ))
            offense_score = min(
                100,
                max(
                    self.action_system._offense_score_for("move", context="trespass"),
                    14,
                )
                + int(round(float(ingress.breach_severity) * 10.0))
                + int(max(0, offense_bonus)),
            )
            self.action_system._emit_action_offense(
                eid=eid,
                action="move",
                context="trespass",
                score=offense_score,
                x=candidate["x"],
                y=candidate["y"],
                z=candidate["z"],
            )
        else:
            name = prop.get("name", prop.get("id", "property"))
            reason_text = support._standing_reason_label(claim_reason)
            mode_text = support._ingress_mode_label(ingress_mode)
            method_text = support._ingress_method_label(ingress_method)
            if reason_text:
                if method_text and method_text != "authorized":
                    support._log_player_feedback(
                        self.sim,
                        f"Used {mode_text} into {name} ({reason_text}, {method_text}).",
                        kind="movement",
                    )
                else:
                    support._log_player_feedback(
                        self.sim,
                        f"Used {mode_text} into {name} ({reason_text}).",
                        kind="movement",
                    )
            else:
                if method_text and method_text != "authorized":
                    support._log_player_feedback(
                        self.sim,
                        f"Used {mode_text} into {name} ({method_text}).",
                        kind="movement",
                    )
                else:
                    support._log_player_feedback(self.sim, f"Used {mode_text} into {name}.", kind="movement")

        self.action_system._refresh_cover_after_move(eid, new_pos, had_cover=had_cover)
