from __future__ import annotations

from game.components import SkillProfile
from game.skill_progression import SkillProgressionSystem
from game.skills import (
    HUD_SKILL_IDS,
    actor_skill,
    profile_neglect_pressure,
    profile_recent_skill_changes,
    skill_label,
    skill_short_label,
)


def skill_change_reason_label(reason):
    text = str(reason or "").strip().lower()
    if text.startswith("practice_"):
        text = text[len("practice_") :]
    text = text.replace("_", " ").strip()
    return text or "practice"


def _profile_birth_bias_rows(profile):
    if not isinstance(profile, SkillProfile):
        return (), ()

    rows = []
    for skill_id, delta in (getattr(profile, "birth_biases", {}) or {}).items():
        key = str(skill_id or "").strip().lower()
        try:
            amount = float(delta)
        except (TypeError, ValueError):
            continue
        if not key or abs(amount) <= 1e-9:
            continue
        rows.append({
            "skill_id": key,
            "label": skill_label(key),
            "short": skill_short_label(key),
            "delta": amount,
        })

    positives = sorted(
        (row for row in rows if float(row.get("delta", 0.0)) > 0.0),
        key=lambda row: (-float(row.get("delta", 0.0)), str(row.get("label", ""))),
    )
    negatives = sorted(
        (row for row in rows if float(row.get("delta", 0.0)) < 0.0),
        key=lambda row: (float(row.get("delta", 0.0)), str(row.get("label", ""))),
    )
    return tuple(positives), tuple(negatives)


def skill_birth_hud_chunk(profile):
    positives, negatives = _profile_birth_bias_rows(profile)
    if not positives and not negatives:
        return ""

    bits = []
    pos_text = "/".join(str(row.get("short", "")).strip() for row in positives[:2] if str(row.get("short", "")).strip())
    neg_text = "/".join(str(row.get("short", "")).strip() for row in negatives[:2] if str(row.get("short", "")).strip())
    if pos_text:
        bits.append(f"+{pos_text}")
    if neg_text:
        bits.append(f"-{neg_text}")
    if not bits:
        return ""
    return "Birth " + " ".join(bits)


def skill_birth_debug_line(profile):
    positives, negatives = _profile_birth_bias_rows(profile)
    if not positives and not negatives:
        return ""

    bits = []
    for row in positives:
        bits.append(f"{row['label']} +{float(row['delta']):.2f}")
    for row in negatives:
        bits.append(f"{row['label']} {float(row['delta']):.2f}")
    return "Birth tilt " + ", ".join(bits)


def player_skill_visibility(profile, *, tick, skill_ids=HUD_SKILL_IDS):
    recent = profile_recent_skill_changes(
        profile,
        tick=tick,
        skill_ids=skill_ids,
        recent_window=max(
            int(getattr(SkillProgressionSystem, "NEGLECT_INTERVAL_TICKS", 240)),
            int(getattr(SkillProgressionSystem, "NEGLECT_SCAN_INTERVAL_TICKS", 60)),
        ),
        limit=1,
    )
    neglect = profile_neglect_pressure(
        profile,
        tick=tick,
        skill_ids=skill_ids,
        grace_ticks=int(getattr(SkillProgressionSystem, "NEGLECT_GRACE_TICKS", 900)),
        warning_ticks=int(getattr(SkillProgressionSystem, "NEGLECT_INTERVAL_TICKS", 240)),
        limit=1,
    )
    return {
        "recent": recent,
        "neglect": neglect,
    }


def skill_hud_status_chunks(sim, player_eid, profile, *, duration_label_fn):
    if sim is None or player_eid is None or not isinstance(profile, SkillProfile):
        return []

    tick = int(getattr(sim, "tick", 0))
    visibility = player_skill_visibility(profile, tick=tick, skill_ids=HUD_SKILL_IDS)
    chunks = []

    recent = visibility.get("recent") or ()
    if recent:
        row = recent[0]
        label = str(row.get("label", skill_label(row.get("skill_id", "")))).strip() or "Skill"
        value = float(row.get("value", 0.0))
        delta = float(row.get("delta", 0.0))
        if delta > 0.0:
            chunks.append(f"Skill up {label} {value:.1f} (+{abs(delta):.1f})")
        else:
            chunks.append(f"Skill slip {label} {value:.1f} (-{abs(delta):.1f})")

    neglect = visibility.get("neglect") or ()
    if neglect:
        row = neglect[0]
        label = str(row.get("label", skill_label(row.get("skill_id", "")))).strip() or "Skill"
        due_in = int(row.get("due_in", 0))
        if due_in <= 0:
            chunks.append(f"Neglect active {label}")
        else:
            chunks.append(f"Neglect risk {label} in {duration_label_fn(sim, due_in)}")

    return chunks


def skill_debug_lines(sim, player_eid, *, duration_label_fn):
    profiles = sim.ecs.get(SkillProfile)
    profile = profiles.get(player_eid) if profiles else None
    if not isinstance(profile, SkillProfile):
        return []

    tick = int(getattr(sim, "tick", 0))
    recent_rows = {
        str(row.get("skill_id", "")).strip().lower(): row
        for row in profile_recent_skill_changes(
            profile,
            tick=tick,
            skill_ids=profile.skill_ids(),
            recent_window=None,
            limit=None,
        )
    }
    neglect_rows = {
        str(row.get("skill_id", "")).strip().lower(): row
        for row in profile_neglect_pressure(
            profile,
            tick=tick,
            skill_ids=profile.skill_ids(),
            grace_ticks=int(getattr(SkillProgressionSystem, "NEGLECT_GRACE_TICKS", 900)),
            warning_ticks=int(getattr(SkillProgressionSystem, "NEGLECT_GRACE_TICKS", 900)),
            limit=None,
        )
    }

    lines = ["", "SKILLS"]
    birth_line = skill_birth_debug_line(profile)
    if birth_line:
        lines.append(birth_line)
    for skill_id in tuple(profile.skill_ids() or HUD_SKILL_IDS):
        key = str(skill_id or "").strip().lower()
        if not key:
            continue
        current = float(profile.get(key, default=actor_skill(sim, player_eid, key)))
        baseline = float(profile.baseline(key, current))
        floor = float(profile.floor(key))
        practice = float(profile.practice_amount(key, default=0.0))
        last_practiced = profile.last_practiced_tick(key)
        idle_ticks = max(0, tick - int(last_practiced)) if last_practiced is not None else 0

        recent = recent_rows.get(key)
        if recent:
            recent_text = (
                f"{recent.get('delta', 0.0):+0.1f} "
                f"{skill_change_reason_label(recent.get('reason', ''))} "
                f"{duration_label_fn(sim, int(recent.get('age_ticks', 0) or 0))} ago"
            )
        else:
            recent_text = "-"

        neglect = neglect_rows.get(key)
        if neglect:
            due_in = int(neglect.get("due_in", 0))
            if due_in <= 0:
                neglect_text = f"active {duration_label_fn(sim, abs(due_in))} overdue"
            else:
                neglect_text = f"in {duration_label_fn(sim, due_in)}"
        else:
            neglect_text = "-"

        lines.append(
            f"{skill_label(key)} {current:.1f} | base {baseline:.1f} | floor {floor:.1f} | "
            f"practice {practice:.2f} | idle {duration_label_fn(sim, idle_ticks)} | "
            f"recent {recent_text} | neglect {neglect_text}"
        )

    return lines
