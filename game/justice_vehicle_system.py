"""Justice-vehicle misuse detection and immediate response."""

from __future__ import annotations

from engine.events import Event
from engine.systems import System
from engine.visibility import observer_can_see_position

from game.components import AI, JusticeProfile, NPCWill, Occupation, Position, VehicleState
from game.incident_runtime import create_or_merge_incident
from game.quick_travel_ramps import local_interactions_suspended_for_actor
from game.system_support.actor_attention_runtime import mark_actor_urgent
from game.system_support.actor_runtime import _entity_is_downed
from game.system_support.security_disguise_runtime import _degrade_player_disguise


PEACE_ROLES = {"guard", "scout", "officer", "police", "deputy", "marshal", "security"}
JUSTICE_RESTRICTED_USE_VALUES = {"justice", "police", "law_enforcement", "security"}
JUSTICE_VEHICLE_FORCE_ATTACK_TICKS = 10
JUSTICE_VEHICLE_SIGHT_RADIUS = 9


def _text(value):
    return str(value or "").strip()


def _key(value):
    return _text(value).lower()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _dist(a, b):
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def _metadata(prop):
    if not isinstance(prop, dict):
        return {}
    data = prop.get("metadata")
    return data if isinstance(data, dict) else {}


def vehicle_restricted_use(prop):
    metadata = _metadata(prop)
    return _key(
        metadata.get("restricted_use")
        or metadata.get("vehicle_restricted_use")
        or metadata.get("restricted_to")
    )


def vehicle_is_justice_restricted(prop):
    if not isinstance(prop, dict):
        return False
    restricted = vehicle_restricted_use(prop)
    if restricted in JUSTICE_RESTRICTED_USE_VALUES:
        return True
    metadata = _metadata(prop)
    if bool(metadata.get("justice_vehicle")):
        return True
    owner_tag = _key(prop.get("owner_tag") or metadata.get("vehicle_owner_tag"))
    return owner_tag == "justice" and _key(metadata.get("vehicle_role")) in {"police", "patrol", "justice"}


def actor_is_justice_authorized(sim, actor_eid):
    if sim is None or actor_eid is None:
        return False
    try:
        actor_eid = int(actor_eid)
    except (TypeError, ValueError):
        return False
    ai = sim.ecs.get(AI).get(actor_eid)
    role = _key(getattr(ai, "role", ""))
    if role in PEACE_ROLES:
        return True
    justice = sim.ecs.get(JusticeProfile).get(actor_eid)
    if justice and bool(getattr(justice, "enforce_all", False)):
        return True
    occupation = sim.ecs.get(Occupation).get(actor_eid)
    career = _key(getattr(occupation, "career", ""))
    return any(token in career for token in ("police", "patrol", "deputy", "marshal", "security", "guard", "corrections"))


class JusticeVehicleMisuseSystem(System):
    """React when justice actors see unauthorized justice-vehicle use."""

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("vehicle_entered", self.on_vehicle_entered)
        self.sim.events.subscribe("vehicle_local_moved", self.on_vehicle_local_moved)
        self.sim.events.subscribe("vehicle_crash", self.on_vehicle_dirty_event)
        self.sim.events.subscribe("vehicle_collision", self.on_vehicle_dirty_event)

    def on_vehicle_entered(self, event):
        self._handle_vehicle_event(event, event_kind="enter", dirty=bool(event.data.get("stolen")))

    def on_vehicle_local_moved(self, event):
        speed = _int(event.data.get("speed"), 0)
        dirty = speed >= 2 or _key(event.data.get("reason")) in {"vehicle_flee", "ram", "crash", "collision"}
        self._handle_vehicle_event(event, event_kind="move", dirty=dirty)

    def on_vehicle_dirty_event(self, event):
        self._handle_vehicle_event(event, event_kind=_key(event.type) or "dirty", dirty=True)

    def _handle_vehicle_event(self, event, *, event_kind, dirty=False):
        data = dict(getattr(event, "data", {}) or {})
        driver_eid = data.get("eid", data.get("driver_eid", data.get("npc_eid")))
        vehicle_id = _text(data.get("vehicle_id"))
        if not vehicle_id:
            return
        try:
            driver_eid = int(driver_eid)
        except (TypeError, ValueError):
            return
        if local_interactions_suspended_for_actor(self.sim, driver_eid):
            return

        vehicle_prop = self.sim.properties.get(vehicle_id)
        if not vehicle_is_justice_restricted(vehicle_prop):
            return
        if not self._actor_is_active_vehicle_user(driver_eid, vehicle_id):
            return
        if actor_is_justice_authorized(self.sim, driver_eid):
            return

        positions = self.sim.ecs.get(Position)
        driver_pos = positions.get(driver_eid)
        if driver_pos is None:
            x = _int(data.get("x"), _int(vehicle_prop.get("x") if vehicle_prop else 0, 0))
            y = _int(data.get("y"), _int(vehicle_prop.get("y") if vehicle_prop else 0, 0))
            z = _int(data.get("z"), _int(vehicle_prop.get("z") if vehicle_prop else 0, 0))
            driver_pos = type("_Pos", (), {"x": x, "y": y, "z": z})()

        for observer_eid in self._visible_justice_observers(driver_eid, driver_pos):
            if self._recently_confirmed(observer_eid, driver_eid, vehicle_id):
                continue
            if self._disguise_suppresses_sighting(
                observer_eid,
                driver_eid,
                vehicle_id,
                event_kind=event_kind,
                dirty=dirty,
            ):
                continue
            self._mark_confirmed(observer_eid, driver_eid, vehicle_id)
            self._confirm_misuse(
                observer_eid,
                driver_eid,
                vehicle_prop,
                driver_pos,
                event_kind=event_kind,
                dirty=dirty,
            )

    def _actor_is_active_vehicle_user(self, actor_eid, vehicle_id):
        state = self.sim.ecs.get(VehicleState).get(actor_eid)
        if state is None:
            return False
        active_vehicle_id = _text(getattr(state, "active_vehicle_id", ""))
        return bool(getattr(state, "in_vehicle", False)) and active_vehicle_id == _text(vehicle_id)

    def _visible_justice_observers(self, driver_eid, driver_pos):
        ais = self.sim.ecs.get(AI)
        positions = self.sim.ecs.get(Position)
        for eid, ai in list(ais.items()):
            if eid == driver_eid:
                continue
            if not actor_is_justice_authorized(self.sim, eid):
                continue
            if _entity_is_downed(self.sim, eid):
                continue
            observer_pos = positions.get(eid)
            if observer_pos is None or int(observer_pos.z) != int(driver_pos.z):
                continue
            if _dist((observer_pos.x, observer_pos.y), (driver_pos.x, driver_pos.y)) > JUSTICE_VEHICLE_SIGHT_RADIUS:
                continue
            if not observer_can_see_position(
                self.sim,
                eid,
                observer_pos.x,
                observer_pos.y,
                observer_pos.z,
                driver_pos.x,
                driver_pos.y,
                driver_pos.z,
                JUSTICE_VEHICLE_SIGHT_RADIUS,
            ):
                continue
            yield eid

    def _recently_confirmed(self, observer_eid, driver_eid, vehicle_id):
        reports = getattr(self.sim, "world_traits", {}).setdefault("justice_vehicle_misuse_reports", {})
        key = f"{int(observer_eid)}:{int(driver_eid)}:{vehicle_id}"
        last_tick = _int(reports.get(key), -10_000)
        now = _int(getattr(self.sim, "tick", 0), 0)
        return now - last_tick < 20

    def _mark_confirmed(self, observer_eid, driver_eid, vehicle_id):
        reports = getattr(self.sim, "world_traits", {}).setdefault("justice_vehicle_misuse_reports", {})
        reports[f"{int(observer_eid)}:{int(driver_eid)}:{vehicle_id}"] = _int(getattr(self.sim, "tick", 0), 0)

    def _disguise_suppresses_sighting(self, observer_eid, driver_eid, vehicle_id, *, event_kind, dirty=False):
        if dirty:
            self._burn_vehicle_disguise(driver_eid, amount=0.42)
            return False
        if driver_eid != getattr(self.sim, "player_eid", None):
            return False
        disguise = getattr(self.sim, "disguise_state", None)
        if not isinstance(disguise, dict):
            return False
        role_id = _key(disguise.get("role_id"))
        strength = max(0.0, float(disguise.get("strength", 0.0) or 0.0))
        if role_id not in {"guard", "security"} or strength < 0.55:
            return False

        exposures = getattr(self.sim, "world_traits", {}).setdefault("justice_vehicle_misuse_exposure", {})
        key = f"{int(observer_eid)}:{int(driver_eid)}:{vehicle_id}"
        count = _int(exposures.get(key), 0)
        exposures[key] = count + (2 if event_kind == "move" else 1)
        if count <= 0 and event_kind == "enter":
            return True
        return False

    def _burn_vehicle_disguise(self, driver_eid, *, amount=0.35):
        if driver_eid == getattr(self.sim, "player_eid", None):
            _degrade_player_disguise(self.sim, driver_eid, amount=amount)

    def _confirm_misuse(self, observer_eid, driver_eid, vehicle_prop, driver_pos, *, event_kind, dirty=False):
        vehicle_id = _text((vehicle_prop or {}).get("id"))
        vehicle_name = _text((vehicle_prop or {}).get("name")) or "justice vehicle"
        incident, _created = create_or_merge_incident(
            self.sim,
            kind="justice_vehicle_misuse",
            x=int(driver_pos.x),
            y=int(driver_pos.y),
            z=int(driver_pos.z),
            severity=82 if dirty else 74,
            primary_actor_eid=driver_eid,
            property_id=vehicle_id,
            property_name=vehicle_name,
            merge_subject=vehicle_id,
            source_event=f"vehicle_{event_kind}",
            official_reportable=True,
            note=f"Unauthorized use of {vehicle_name}",
            tags=("justice_vehicle_misuse", "vehicle_theft", "justice", "serious"),
        )
        incident_id = _int(incident.get("id"), -1) if isinstance(incident, dict) else -1

        quote = "Police! Out of the vehicle!"
        observer_pos = self.sim.ecs.get(Position).get(observer_eid)
        noise_x = int(getattr(observer_pos, "x", driver_pos.x))
        noise_y = int(getattr(observer_pos, "y", driver_pos.y))
        noise_z = int(getattr(observer_pos, "z", driver_pos.z))
        self.sim.emit(Event(
            "justice_vehicle_misuse_barked",
            npc_eid=observer_eid,
            observer_eid=observer_eid,
            offender_eid=driver_eid,
            eid=driver_eid,
            vehicle_id=vehicle_id,
            vehicle_name=vehicle_name,
            quote=quote,
            incident_id=incident_id,
            x=int(driver_pos.x),
            y=int(driver_pos.y),
            z=int(driver_pos.z),
            dirty=bool(dirty),
            reason=f"vehicle_{event_kind}",
        ))
        self.sim.emit(Event(
            "noise",
            source_eid=observer_eid,
            target_eid=driver_eid,
            x=noise_x,
            y=noise_y,
            z=noise_z,
            radius=8,
            cause="justice_vehicle_misuse_bark",
        ))
        self.sim.emit(Event(
            "observed_response_cue",
            npc_eid=observer_eid,
            incident_id=incident_id,
            cue_kind="report_authority",
            target=(int(driver_pos.x), int(driver_pos.y), int(driver_pos.z)),
            target_eid=driver_eid,
            urgency=0.98,
            reason="justice_vehicle_misuse",
            preferred_methods=("radio", "cell_phone", "peace_officer"),
        ))
        self._force_observer_engagement(observer_eid, driver_eid, driver_pos, incident_id=incident_id)
        self._burn_vehicle_disguise(driver_eid, amount=0.55)

    def _force_observer_engagement(self, observer_eid, driver_eid, driver_pos, *, incident_id=-1):
        ai = self.sim.ecs.get(AI).get(observer_eid)
        if ai is None:
            return
        ai.state = "protecting"
        ai.target = (int(driver_pos.x), int(driver_pos.y), int(driver_pos.z))
        ai.target_eid = driver_eid
        ai.incident_id = incident_id
        ai.response_role = "justice_vehicle_misuse"
        ai.force_attack_until_tick = _int(getattr(self.sim, "tick", 0), 0) + JUSTICE_VEHICLE_FORCE_ATTACK_TICKS
        ai.force_attack_reason = "justice_vehicle_misuse"

        will = self.sim.ecs.get(NPCWill).get(observer_eid)
        if will is not None:
            will.intent = "protecting"
            will.score = 98.0
            will.target = ai.target
            will.target_eid = driver_eid
            will.last_tick = _int(getattr(self.sim, "tick", 0), 0)
        mark_actor_urgent(self.sim, observer_eid, family="all", reason="justice_vehicle_misuse", ttl_ticks=14)
