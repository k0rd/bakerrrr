"""Shared witness and observer notice helpers."""

from game.components import AI, Position


VALID_ACCOUNTABLE_OBSERVATION_CHANNELS = frozenset({
    "actor_witness",
    "camera_owner_feed",
    "authority_report",
    "official_report",
})


def _observer_support():
    from game import systems as _systems

    return _systems


def _normalize_observer_eids(values):
    if values is None:
        return ()
    if isinstance(values, (int, str)):
        values = (values,)
    observers = []
    seen = set()
    for raw in values:
        if isinstance(raw, (list, tuple, set, frozenset)):
            for eid in _normalize_observer_eids(raw):
                if eid in seen:
                    continue
                seen.add(eid)
                observers.append(eid)
            continue
        try:
            eid = int(raw)
        except (TypeError, ValueError):
            continue
        if eid in seen:
            continue
        seen.add(eid)
        observers.append(eid)
    return tuple(observers)


def _combined_excluded_observer_eids(*values):
    excluded = []
    for value in values:
        excluded.extend(_normalize_observer_eids(value))
    return frozenset(excluded)


def _filter_excluded_observers(observer_eids, excluded_eids=()):
    observers = _normalize_observer_eids(observer_eids)
    excluded = _combined_excluded_observer_eids(excluded_eids)
    if not excluded:
        return observers
    return tuple(observer_eid for observer_eid in observers if observer_eid not in excluded)


def _observer_ignores_offender(sim, observer_eid, offender_eid):
    if offender_eid is None:
        return False
    try:
        return bool(_observer_support()._observer_is_active_contractor_ally(sim, observer_eid, offender_eid))
    except AttributeError:
        return False


def _observer_is_private_bodyguard(sim, observer_eid):
    try:
        return bool(_observer_support()._observer_is_active_bodyguard(sim, observer_eid))
    except AttributeError:
        return False


def _filter_observers_for_offender(sim, observer_eids, excluded_eids=(), *, offender_eid=None):
    observers = _filter_excluded_observers(observer_eids, excluded_eids)
    if offender_eid is None:
        return observers
    return tuple(
        observer_eid
        for observer_eid in observers
        if _observer_is_private_bodyguard(sim, observer_eid)
        or not _observer_ignores_offender(sim, observer_eid, offender_eid)
    )


def _event_excluded_observer_eids(data, *, event_type=""):
    if not isinstance(data, dict):
        return ()
    excluded = list(_normalize_observer_eids(data.get("excluded_observer_eids")))
    # Victims remember what happened to them, but they are not an independent
    # public witness to their own assault for immediate heat/justice pressure.
    if str(event_type or "").strip().lower() in {"action_offense", "npc_killed"}:
        excluded.extend(_normalize_observer_eids(data.get("victim_eid")))
    return tuple(dict.fromkeys(excluded))


def _event_reporter_observer_eids(data, *, event_type=""):
    if not isinstance(data, dict):
        return ()
    if str(event_type or "").strip().lower() != "incident_authority_reported":
        return ()
    reporters = _normalize_observer_eids((
        data.get("npc_eid"),
        data.get("reporter_eid"),
        data.get("reported_by_eid"),
    ))
    return tuple(reporter_eid for reporter_eid in reporters if int(reporter_eid) > 0)


def _normalize_observation_channels(values):
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    channels = []
    seen = set()
    for raw in values:
        channel = str(raw or "").strip().lower().replace(" ", "_")
        if not channel or channel in seen:
            continue
        seen.add(channel)
        channels.append(channel)
    return tuple(channels)


def _observer_role(sim, observer_eid):
    ai = sim.ecs.get(AI).get(int(observer_eid))
    return str(getattr(ai, "role", "") or "").strip().lower()


def _observer_is_accountable(sim, observer_eid, *, offender_eid=None, allow_player_accountable=False):
    try:
        observer_eid = int(observer_eid)
    except (TypeError, ValueError):
        return False
    if offender_eid is not None:
        try:
            if observer_eid == int(offender_eid):
                return False
        except (TypeError, ValueError):
            pass
    if not allow_player_accountable and observer_eid == getattr(sim, "player_eid", None):
        return False
    if _observer_ignores_offender(sim, observer_eid, offender_eid):
        return False
    if _observer_is_private_bodyguard(sim, observer_eid):
        return False
    return _observer_role(sim, observer_eid) != "wildlife"


def _filter_accountable_observers(
    sim,
    observer_eids,
    excluded_eids=(),
    *,
    offender_eid=None,
    allow_player_accountable=False,
):
    return tuple(
        observer_eid
        for observer_eid in _filter_observers_for_offender(
            sim,
            observer_eids,
            excluded_eids,
            offender_eid=offender_eid,
        )
        if _observer_is_accountable(
            sim,
            observer_eid,
            offender_eid=offender_eid,
            allow_player_accountable=allow_player_accountable,
        )
    )


def observation_payload_from_observers(
    sim,
    observer_eids,
    *,
    offender_eid=None,
    exclude_eids=(),
    observation_channels=("actor_witness",),
    allow_player_accountable=False,
    max_legacy_witnesses=4,
):
    observers = _filter_observers_for_offender(
        sim,
        observer_eids,
        exclude_eids,
        offender_eid=offender_eid,
    )
    accountable = _filter_accountable_observers(
        sim,
        observers,
        (),
        offender_eid=offender_eid,
        allow_player_accountable=allow_player_accountable,
    )
    channels = _normalize_observation_channels(observation_channels)
    if not channels and observers:
        channels = ("actor_witness",)
    return {
        "observer_eids": observers,
        "observer_count": len(observers),
        "accountable_observer_eids": accountable,
        "accountable_observer_count": len(accountable),
        "observation_channels": channels,
        "witnessed": bool(accountable),
        "witness_count": len(accountable),
        "witnesses": tuple(accountable[: max(0, int(max_legacy_witnesses))]),
    }


def observation_payload_for_position(
    sim,
    x,
    y,
    z,
    *,
    exclude_eid=None,
    exclude_eids=(),
    offender_eid=None,
    observation_channels=("actor_witness",),
    allow_player_accountable=False,
    max_legacy_witnesses=4,
):
    excluded = _combined_excluded_observer_eids(exclude_eid, exclude_eids)
    if x is None or y is None or z is None:
        return observation_payload_from_observers(
            sim,
            (),
            offender_eid=offender_eid,
            exclude_eids=excluded,
            observation_channels=observation_channels,
            allow_player_accountable=allow_player_accountable,
            max_legacy_witnesses=max_legacy_witnesses,
        )
    observers = _watchers_for_position(
        sim,
        x,
        y,
        z,
        exclude_eids=excluded,
        offender_eid=offender_eid,
    )
    return observation_payload_from_observers(
        sim,
        observers,
        offender_eid=offender_eid,
        exclude_eids=excluded,
        observation_channels=observation_channels,
        allow_player_accountable=allow_player_accountable,
        max_legacy_witnesses=max_legacy_witnesses,
    )


def event_observation_accountability(
    sim,
    event_or_data,
    *,
    offender_eid=None,
    default_channels=("actor_witness",),
    use_legacy_witness_fallback=False,
    allow_position_backfill=True,
):
    data = getattr(event_or_data, "data", event_or_data)
    event_type = str(getattr(event_or_data, "type", "") or "").strip().lower()
    if not isinstance(data, dict):
        data = {}

    reporter_observers = _event_reporter_observer_eids(data, event_type=event_type)
    has_explicit_observers = "observer_eids" in data or bool(reporter_observers)
    has_explicit_accountable = "accountable_observer_eids" in data
    excluded_eids = _event_excluded_observer_eids(data, event_type=event_type)

    observers = _filter_observers_for_offender(
        sim,
        (
            tuple(_normalize_observer_eids(data.get("observer_eids"))) + tuple(reporter_observers)
            if has_explicit_observers
            else data.get("witnesses")
        ),
        excluded_eids,
        offender_eid=offender_eid,
    )
    channels = _normalize_observation_channels(data.get("observation_channels"))
    if not channels and observers:
        if event_type == "incident_authority_reported":
            channels = ("official_report",)
        else:
            channels = _normalize_observation_channels(default_channels) or ("actor_witness",)

    if has_explicit_accountable:
        accountable = _filter_accountable_observers(
            sim,
            data.get("accountable_observer_eids"),
            excluded_eids,
            offender_eid=offender_eid,
        )
    else:
        accountable = _filter_accountable_observers(
            sim,
            observers,
            (),
            offender_eid=offender_eid,
        )

    legacy_witnessed = bool(data.get("witnessed", False))
    legacy_fallback = False
    if (
        use_legacy_witness_fallback
        and legacy_witnessed
        and not has_explicit_observers
        and not has_explicit_accountable
        and not observers
        and not accountable
    ):
        channels = channels or (_normalize_observation_channels(default_channels) or ("actor_witness",))
        accountable = _filter_accountable_observers(
            sim,
            data.get("witnesses"),
            excluded_eids,
            offender_eid=offender_eid,
        )
        legacy_fallback = bool(accountable)
    elif (
        allow_position_backfill
        and not has_explicit_observers
        and not has_explicit_accountable
        and not observers
        and not accountable
    ):
        backfilled = observation_payload_for_position(
            sim,
            data.get("x"),
            data.get("y"),
            data.get("z", 0),
            exclude_eid=offender_eid,
            exclude_eids=excluded_eids,
            offender_eid=offender_eid,
            observation_channels=default_channels,
        )
        observers = tuple(backfilled.get("observer_eids", ()))
        accountable = tuple(backfilled.get("accountable_observer_eids", ()))
        channels = tuple(backfilled.get("observation_channels", ()))

    has_accountable = bool(accountable) or legacy_fallback
    accountable_channels = tuple(
        channel
        for channel in channels
        if channel in VALID_ACCOUNTABLE_OBSERVATION_CHANNELS
    )

    return {
        "observer_eids": observers,
        "observer_count": len(observers),
        "accountable_observer_eids": accountable,
        "accountable_observer_count": len(accountable),
        "observation_channels": channels,
        "accountable_observation_channels": accountable_channels,
        "has_accountable_observation": bool(has_accountable),
        "legacy_fallback": bool(legacy_fallback),
        "witnessed": bool(has_accountable),
        "witness_count": len(accountable),
        "witnesses": tuple(accountable),
    }


def _watchers_for_position(sim, x, y, z, exclude_eid=None, exclude_eids=(), offender_eid=None):
    positions = sim.ecs.get(Position)
    support = _observer_support()
    excluded = _combined_excluded_observer_eids(exclude_eid, exclude_eids)

    watchers = []
    for observer_eid, observer_pos in positions.items():
        if observer_eid in excluded:
            continue
        if (
            offender_eid is not None
            and support._observer_is_active_contractor_ally(sim, observer_eid, offender_eid)
            and not _observer_is_private_bodyguard(sim, observer_eid)
        ):
            continue
        if int(observer_pos.z) != int(z):
            continue
        if support._observer_can_notice_position(sim, observer_eid, x, y, z):
            watchers.append(observer_eid)
    return watchers
