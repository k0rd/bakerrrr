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
        try:
            eid = int(raw)
        except (TypeError, ValueError):
            continue
        if eid in seen:
            continue
        seen.add(eid)
        observers.append(eid)
    return tuple(observers)


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
    return _observer_role(sim, observer_eid) != "wildlife"


def observation_payload_from_observers(
    sim,
    observer_eids,
    *,
    offender_eid=None,
    observation_channels=("actor_witness",),
    allow_player_accountable=False,
    max_legacy_witnesses=4,
):
    observers = _normalize_observer_eids(observer_eids)
    accountable = tuple(
        observer_eid
        for observer_eid in observers
        if _observer_is_accountable(
            sim,
            observer_eid,
            offender_eid=offender_eid,
            allow_player_accountable=allow_player_accountable,
        )
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
    offender_eid=None,
    observation_channels=("actor_witness",),
    allow_player_accountable=False,
    max_legacy_witnesses=4,
):
    if x is None or y is None or z is None:
        return observation_payload_from_observers(
            sim,
            (),
            offender_eid=offender_eid,
            observation_channels=observation_channels,
            allow_player_accountable=allow_player_accountable,
            max_legacy_witnesses=max_legacy_witnesses,
        )
    observers = _watchers_for_position(
        sim,
        x,
        y,
        z,
        exclude_eid=exclude_eid,
        offender_eid=offender_eid,
    )
    return observation_payload_from_observers(
        sim,
        observers,
        offender_eid=offender_eid,
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
    if not isinstance(data, dict):
        data = {}

    has_explicit_observers = "observer_eids" in data
    has_explicit_accountable = "accountable_observer_eids" in data

    observers = _normalize_observer_eids(
        data.get("observer_eids") if has_explicit_observers else data.get("witnesses")
    )
    channels = _normalize_observation_channels(data.get("observation_channels"))
    if not channels and observers:
        channels = _normalize_observation_channels(default_channels) or ("actor_witness",)

    if has_explicit_accountable:
        accountable = _normalize_observer_eids(data.get("accountable_observer_eids"))
    else:
        accountable = tuple(
            observer_eid
            for observer_eid in observers
            if _observer_is_accountable(sim, observer_eid, offender_eid=offender_eid)
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
        accountable = _normalize_observer_eids(data.get("witnesses"))
        legacy_fallback = True
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


def _watchers_for_position(sim, x, y, z, exclude_eid=None, offender_eid=None):
    positions = sim.ecs.get(Position)
    support = _observer_support()

    watchers = []
    for observer_eid, observer_pos in positions.items():
        if observer_eid == exclude_eid:
            continue
        if offender_eid is not None and support._observer_is_active_contractor_ally(sim, observer_eid, offender_eid):
            continue
        if int(observer_pos.z) != int(z):
            continue
        if support._observer_can_notice_position(sim, observer_eid, x, y, z):
            watchers.append(observer_eid)
    return watchers
