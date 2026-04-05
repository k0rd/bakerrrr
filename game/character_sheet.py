from __future__ import annotations

from game.components import (
    ArmorLoadout,
    CoreStats,
    FinancialProfile,
    Inventory,
    NPCNeeds,
    PlayerAssets,
    SkillProfile,
    StatusEffects,
    Vitality,
    WeaponLoadout,
)
from game.run_pressure import pressure_snapshot
from game.skill_ui import skill_birth_debug_line, skill_change_reason_label
from game.skills import ALL_SKILL_IDS, actor_skill, profile_neglect_pressure, profile_recent_skill_changes, skill_label
from game.weapons import weapon_by_id


def _weapon_uses_ammo(weapon):
    if not isinstance(weapon, dict):
        return False
    tags = {str(tag).strip().lower() for tag in weapon.get("tags", ()) if str(tag).strip()}
    return "melee" not in tags


def _default_weapon_reserve_ammo(weapon):
    if not _weapon_uses_ammo(weapon):
        return 0
    tags = {str(tag).strip().lower() for tag in weapon.get("tags", ()) if str(tag).strip()}
    if "launcher" in tags or "explosive" in tags:
        return 3
    if "shotgun" in tags:
        return 10
    if "rifle" in tags or "carbine" in tags:
        return 14
    if "smg" in tags or "burst" in tags:
        return 24
    if "handgun" in tags:
        return 18
    return 12


def _weapon_ammo_type_label(weapon):
    if not _weapon_uses_ammo(weapon):
        return "melee"
    tags = {str(tag).strip().lower() for tag in weapon.get("tags", ()) if str(tag).strip()}
    if "launcher" in tags or "explosive" in tags:
        return "rockets"
    if "shotgun" in tags:
        return "shells"
    if "rifle" in tags or "carbine" in tags or "precision" in tags:
        return "rifle"
    if "handgun" in tags or "smg" in tags or "burst" in tags:
        return "light"
    return "ammo"


def _weapon_reserve_ammo(loadout, weapon_id):
    if not loadout or not weapon_id:
        return None
    if weapon_id not in getattr(loadout, "reserve_ammo", {}):
        return None
    try:
        return int(loadout.reserve_ammo.get(weapon_id, 0))
    except (TypeError, ValueError):
        return None


def _active_status_text(status_effects, *, duration_label_fn, sim):
    if not status_effects or not getattr(status_effects, "active", None):
        return "-"

    rows = []
    for status_name, state in sorted(status_effects.active.items()):
        tick_until = state.get("expires_tick")
        if tick_until is None:
            rows.append(str(status_name).replace("_", " "))
            continue
        try:
            remaining = max(0, int(tick_until) - int(getattr(sim, "tick", 0)))
        except (TypeError, ValueError):
            remaining = 0
        rows.append(f"{str(status_name).replace('_', ' ')} {duration_label_fn(sim, remaining)}")
    return ", ".join(rows)


def build_character_sheet_pages(sim, player_eid, *, duration_label_fn):
    if sim is None or player_eid is None:
        return (
            {
                "id": "summary",
                "label": "Summary",
                "lines": ["No player data."],
            },
        )

    ecs = sim.ecs
    profile = ecs.get(SkillProfile).get(player_eid)
    core = ecs.get(CoreStats).get(player_eid)
    needs = ecs.get(NPCNeeds).get(player_eid)
    assets = ecs.get(PlayerAssets).get(player_eid)
    finance = ecs.get(FinancialProfile).get(player_eid)
    vitality = ecs.get(Vitality).get(player_eid)
    inventory = ecs.get(Inventory).get(player_eid)
    loadout = ecs.get(WeaponLoadout).get(player_eid)
    armor = ecs.get(ArmorLoadout).get(player_eid)
    status_effects = ecs.get(StatusEffects).get(player_eid)

    pressure = pressure_snapshot(sim)
    credits = int(getattr(assets, "credits", 0) or 0)
    bank_balance = int(getattr(finance, "bank_balance", 0) or 0)
    owned = len(getattr(assets, "owned_property_ids", ()) or ())
    hp_text = "?"
    if vitality is not None:
        hp_text = f"{int(getattr(vitality, 'hp', 0))}/{int(getattr(vitality, 'max_hp', 0))}"

    weapon_name = "unarmed"
    ammo_text = "-"
    if loadout and loadout.current_weapon():
        weapon = weapon_by_id(loadout.current_weapon())
        instance = getattr(loadout, "weapon_instances", {}).get(loadout.current_weapon(), {})
        weapon_name = str(instance.get("custom_name") or weapon.get("name", weapon.get("id", "weapon")))
        if _weapon_uses_ammo(weapon):
            ammo_type = _weapon_ammo_type_label(weapon)
            reserve = _weapon_reserve_ammo(loadout, loadout.current_weapon())
            if reserve is None:
                reserve = int(_default_weapon_reserve_ammo(weapon))
            ammo_text = f"{int(reserve)} {ammo_type}"
        else:
            ammo_text = "melee"

    armor_name = "none"
    if armor and getattr(armor, "equipped_item_id", None):
        armor_name = str(getattr(armor, "equipped_name", "") or getattr(armor, "equipped_item_id", "armor"))

    summary_lines = [
        "OVERVIEW",
        f"Seed {getattr(sim, 'seed', '?')} | Credits {credits} | Bank {bank_balance} | Owned props {owned}",
        f"HP {hp_text} | Heat {str(pressure.get('tier', 'low'))} {int(pressure.get('attention', 0))} | Status {len(getattr(status_effects, 'active', {}) or {})}",
    ]
    if needs is not None:
        summary_lines.append(
            f"Needs Energy {float(getattr(needs, 'energy', 0.0)):.0f} | Safety {float(getattr(needs, 'safety', 0.0)):.0f} | Social {float(getattr(needs, 'social', 0.0)):.0f}"
        )
    summary_lines.append(f"Active effects {_active_status_text(status_effects, duration_label_fn=duration_label_fn, sim=sim)}")

    if core is not None:
        summary_lines.extend([
            "",
            "CORE",
            (
                f"Brawn {int(getattr(core, 'brawn', 0))} | Ath {int(getattr(core, 'athleticism', 0))} | "
                f"Dex {int(getattr(core, 'dexterity', 0))} | Access {int(getattr(core, 'access', 0))}"
            ),
            f"Charm {int(getattr(core, 'charm', 0))} | Sense {int(getattr(core, 'common_sense', 0))}",
        ])

    loadout_lines = [
        "LOADOUT",
        f"Weapon {weapon_name} | Ammo {ammo_text}",
        f"Armor {armor_name}",
    ]
    if inventory is not None:
        loadout_lines.append(f"Inventory slots {inventory.slot_count()}/{int(getattr(inventory, 'capacity', 0) or 0)}")
    loadout_lines.append(f"Active effects {_active_status_text(status_effects, duration_label_fn=duration_label_fn, sim=sim)}")

    skills_lines = ["SKILLS"]
    birth_line = skill_birth_debug_line(profile)
    if birth_line:
        skills_lines.append(birth_line)

    if isinstance(profile, SkillProfile):
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
                grace_ticks=900,
                warning_ticks=900,
                limit=None,
            )
        }
        for skill_id in tuple(profile.skill_ids() or ALL_SKILL_IDS):
            key = str(skill_id or "").strip().lower()
            if not key:
                continue
            current = float(profile.get(key, default=actor_skill(sim, player_eid, key)))
            baseline = float(profile.baseline(key, current))
            floor = float(profile.floor(key))
            recent = recent_rows.get(key)
            if recent:
                recent_text = (
                    f"{float(recent.get('delta', 0.0)):+0.1f} "
                    f"{skill_change_reason_label(recent.get('reason', ''))} "
                    f"{duration_label_fn(sim, int(recent.get('age_ticks', 0) or 0))} ago"
                )
            else:
                recent_text = "-"
            neglect = neglect_rows.get(key)
            if neglect:
                due_in = int(neglect.get("due_in", 0))
                neglect_text = f"active {duration_label_fn(sim, abs(due_in))} overdue" if due_in <= 0 else f"in {duration_label_fn(sim, due_in)}"
            else:
                neglect_text = "-"
            skills_lines.append(
                f"{skill_label(key)} {current:.1f} | base {baseline:.1f} | floor {floor:.1f} | recent {recent_text} | neglect {neglect_text}"
            )
    else:
        for skill_id in ALL_SKILL_IDS:
            skills_lines.append(f"{skill_label(skill_id)} {actor_skill(sim, player_eid, skill_id):.1f}")

    return (
        {
            "id": "summary",
            "label": "Summary",
            "lines": summary_lines,
        },
        {
            "id": "skills",
            "label": "Skills",
            "lines": skills_lines,
        },
        {
            "id": "loadout",
            "label": "Loadout",
            "lines": loadout_lines,
        },
    )


def build_character_sheet_lines(sim, player_eid, *, duration_label_fn):
    pages = build_character_sheet_pages(sim, player_eid, duration_label_fn=duration_label_fn)
    lines = []
    for idx, page in enumerate(tuple(pages or ())):
        page_lines = list(page.get("lines", ()) or ())
        if idx > 0:
            lines.append("")
        lines.extend(page_lines)
    return lines or ["No player data."]
