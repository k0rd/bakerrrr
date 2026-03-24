from dataclasses import dataclass

from game.components import (
    AI,
    CoreStats,
    CreatureIdentity,
    InsightStats,
    JusticeProfile,
    NPCTraits,
    SkillProfile,
)
from game.skills import actor_skill as _actor_skill, profile_skill as _profile_skill


def _clamp(value, lo=0.0, hi=1.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(lo)
    return max(lo, min(hi, number))


def _num(value, default):
    try:
        if value is None:
            raise TypeError
        return float(value)
    except (TypeError, ValueError):
        return float(default)


@dataclass(frozen=True)
class ContestResult:
    kind: str
    power: float
    resistance: float
    margin: float
    mode: str = "default"

    @property
    def rating(self):
        if self.margin < -0.14:
            return "poor"
        if self.margin < 0.02:
            return "thin"
        if self.margin < 0.22:
            return "solid"
        return "strong"


@dataclass(frozen=True)
class CrimeReadResult:
    contest: ContestResult
    sensitivity: float
    justice: float
    text: str
    sentence_text: str


def resolve_contest(kind, power, resistance, mode="default"):
    power = max(0.0, float(power))
    resistance = max(0.0, float(resistance))
    return ContestResult(
        kind=str(kind or "generic"),
        power=power,
        resistance=resistance,
        margin=power - resistance,
        mode=str(mode or "default"),
    )


def social_read_axes(profile):
    if not profile:
        return 5.0, 5.0, 5.0

    perception = _profile_skill("perception", profile=profile, default=5.0)
    conversation = _profile_skill("conversation", profile=profile, default=5.0)
    streetwise = _profile_skill("streetwise", profile=profile, default=5.0)
    return perception, conversation, streetwise


def observer_social_profile(sim, eid):
    profile = sim.ecs.get(SkillProfile).get(eid)
    if profile:
        return profile
    insight = sim.ecs.get(InsightStats).get(eid)
    if insight:
        return insight
    return sim.ecs.get(CoreStats).get(eid)


def justice_level(profile, default=0.5):
    if not profile:
        return float(default)
    return float(_clamp(getattr(profile, "justice", default), lo=0.0, hi=1.0))


def crime_sensitivity(profile, default=0.5):
    if not profile:
        return float(default)
    fallback = justice_level(profile, default=default)
    return float(_clamp(getattr(profile, "crime_sensitivity", fallback), lo=0.0, hi=1.0))


def rumor_truth_read(insight, rumor_entry):
    if not rumor_entry:
        return "unclear"
    data = rumor_entry.get("data", {}) if isinstance(rumor_entry, dict) else {}
    is_true = bool(data.get("is_true", False))
    strength = (
        float(max(0.0, min(1.0, rumor_entry.get("strength", 0.0))))
        if isinstance(rumor_entry, dict)
        else 0.0
    )

    if not insight:
        if strength < 0.4:
            return "unclear"
        return "plausible"

    perception, charisma, streetwise = social_read_axes(insight)
    read_power = ((perception * 0.45) + (streetwise * 0.45) + (charisma * 0.1)) / 10.0
    read_power = max(0.15, min(1.2, read_power))
    certainty = read_power * (0.62 + (strength * 0.38))

    if certainty < 0.4:
        return "unclear"
    if certainty < 0.62:
        return "plausible"
    return "likely true" if is_true else "likely false"


def crime_read_power(sim, observer_eid, mode="look"):
    perception = _actor_skill(sim, observer_eid, "perception")
    conversation = _actor_skill(sim, observer_eid, "conversation")
    streetwise = _actor_skill(sim, observer_eid, "streetwise")
    mode = str(mode or "look").strip().lower()
    if mode == "talk":
        power = ((conversation * 0.45) + (perception * 0.22) + (streetwise * 0.33)) / 10.0
        return max(0.18, min(1.25, power + 0.08))
    power = ((perception * 0.48) + (streetwise * 0.37) + (conversation * 0.15)) / 10.0
    return max(0.14, min(1.15, power))


def _read_resistance_role_bonus(role):
    role = str(role or "").strip().lower()
    bonuses = {
        "guard": 0.18,
        "scout": 0.14,
        "fixer": 0.12,
        "merchant": 0.07,
        "courier": 0.05,
        "technician": 0.05,
        "mechanic": 0.04,
        "bartender": 0.03,
    }
    return float(bonuses.get(role, 0.0))


def npc_read_resistance(sim, target_eid):
    ai = sim.ecs.get(AI).get(target_eid)
    traits = sim.ecs.get(NPCTraits).get(target_eid) or NPCTraits()
    justice = sim.ecs.get(JusticeProfile).get(target_eid)

    state_bonus = 0.0
    state = str(ai.state if ai else "idle").strip().lower()
    if state == "protecting":
        state_bonus = 0.16
    elif state == "investigating":
        state_bonus = 0.1
    elif state == "patrolling":
        state_bonus = 0.05

    discipline = float(_clamp(getattr(traits, "discipline", 0.5), lo=0.0, hi=1.0))
    sensitivity = crime_sensitivity(justice, default=0.5)
    justice = justice_level(justice, default=0.5)
    role_bonus = _read_resistance_role_bonus(ai.role if ai else "")

    resistance = 0.34 + (discipline * 0.32) + (sensitivity * 0.16) + (justice * 0.08)
    resistance += role_bonus + state_bonus
    return max(0.18, min(1.2, resistance))


def crime_read_result(sim, observer_eid, target_eid, mode="look"):
    ai = sim.ecs.get(AI).get(target_eid)
    if not ai:
        return None

    identity = sim.ecs.get(CreatureIdentity).get(target_eid)
    if identity and identity.taxonomy_class != "hominid":
        return None

    traits = sim.ecs.get(NPCTraits).get(target_eid) or NPCTraits()
    justice = sim.ecs.get(JusticeProfile).get(target_eid)

    sensitivity = crime_sensitivity(justice, default=0.5)
    justice_value = justice_level(justice, default=0.5)
    contest = resolve_contest(
        kind="crime_read",
        power=crime_read_power(sim, observer_eid, mode=mode),
        resistance=npc_read_resistance(sim, target_eid),
        mode=mode,
    )

    role = str(ai.role or "").strip().lower()
    opsec_style = role in {"guard", "scout", "fixer"} or float(getattr(traits, "discipline", 0.0)) >= 0.78

    if contest.margin < -0.14:
        text = "keep a professional poker face" if opsec_style else "are hard to size up"
    elif contest.margin < 0.02:
        if sensitivity >= 0.68 and justice_value >= 0.68:
            text = "seem like trouble if they clock you"
        elif sensitivity >= 0.68:
            text = "seem quick to notice trouble"
        elif justice_value >= 0.68:
            text = "seem serious about rules"
        else:
            text = "seem fairly relaxed"
    elif contest.margin < 0.22:
        if sensitivity - justice_value >= 0.15:
            text = "notice trouble quickly, but may be flexible once they do"
        elif justice_value - sensitivity >= 0.15:
            text = "may miss small trouble, but react hard if they catch it"
        elif sensitivity >= 0.55 and justice_value >= 0.55:
            text = "seem watchful and fairly strict"
        else:
            text = "seem relaxed about minor trouble"
    else:
        if sensitivity >= 0.68 and justice_value >= 0.68:
            text = "are quick to notice trouble and strict about enforcing rules"
        elif sensitivity >= 0.68 and justice_value <= 0.38:
            text = "notice trouble quickly, but are not eager to escalate"
        elif sensitivity <= 0.38 and justice_value >= 0.68:
            text = "are not very watchful, but are strict if they do catch something"
        elif sensitivity <= 0.38 and justice_value <= 0.38:
            text = "are unlikely to notice small trouble and not eager to get involved"
        else:
            sens_text = "fairly alert to trouble" if sensitivity >= 0.5 else "not especially watchful"
            justice_text = "take rules seriously" if justice_value >= 0.5 else "are not especially strict"
            text = f"are {sens_text} and {justice_text}"

    if text.startswith(("are ", "notice ", "keep ", "seem ")):
        sentence_text = f"They {text}."
    else:
        sentence_text = f"They are {text}."

    compact = text
    for prefix in ("are ", "seem ", "keep "):
        if compact.startswith(prefix):
            compact = compact[len(prefix):]
            break

    return CrimeReadResult(
        contest=contest,
        sensitivity=sensitivity,
        justice=justice_value,
        text=compact,
        sentence_text=sentence_text,
    )


def crime_read_summary(sim, observer_eid, target_eid, mode="look", sentence=True):
    result = crime_read_result(sim, observer_eid, target_eid, mode=mode)
    if not result:
        return None
    return result.sentence_text if sentence else result.text
