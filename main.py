import curses
import faulthandler
import importlib.util
import os
import platform
import random
import signal
import sys
import time
from pathlib import Path

from engine.buildings import layout_chunk_building, world_building_id
from engine.events import Event
from engine.fixtures import generate_chunk_fixture_records
from engine.persistence import (
    SAVE_DIR,
    character_save_exists,
    delete_character_save,
    load_character_run,
    normalize_character_name,
    save_character_run,
)
from engine.sites import layout_chunk_site, site_gameplay_profile, site_layout_reserved_footprints
from engine.sim import Simulation
from engine.tilemap import Tile
from game.systems_observed_events import ObservedIncidentConsequenceSystem
from game.systems_observed_response import ObservedIncidentResponseSystem
from game.systems_observed_dispatch import ObservedIncidentDispatchSystem
from game.system_support.altered_state_runtime import AlteredStateSystem
from game.components import (
    AI,
    ArmorLoadout,
    Collider,
    ContactLedger,
    CoreStats,
    CoverState,
    CreatureIdentity,
    FinancialProfile,
    InsightStats,
    Inventory,
    ItemUseProfile,
    JusticeProfile,
    MovementThrottle,
    NPCMemory,
    NPCNeeds,
    NPCRoutine,
    NPCSocial,
    NPCTraits,
    NPCWill,
    NoiseProfile,
    Occupation,
    PlayerAssets,
    PlayerControlled,
    PlayerModeState,
    Position,
    PropertyKnowledge,
    PropertyPortfolio,
    Render,
    SkillProfile,
    StatusEffects,
    VehicleState,
    Vitality,
    WildlifeBehavior,
    WeaponLoadout,
    WeaponUseProfile,
)
from game.bones import maybe_seed_bones_for_chunk, prime_bones_runtime
from game.economy import (
    LocalTradePressureSystem,
    chunk_economy_profile,
    pick_career_for_workplace,
    workplace_archetype_weight,
)
from game.finance_services import FinanceSystem
from game.custom_content import (
    apply_custom_content,
    load_custom_content_for_new_run,
    validate_custom_content_for_resume,
)
from game.final_notice import show_final_notice, show_run_end_notice
from game.flora_runtime import ensure_chunk_flora
from game.items import ITEM_CATALOG
from game.hunting_runtime import HuntingCarcassSystem
from game.large_span_places import register_large_span_child_properties
from game.npc_names import (
    generate_human_household_names,
    generate_human_personal_name,
    human_descriptor,
)
from game.organizations import (
    ensure_property_organization,
    seed_chunk_organizations,
    seed_property_organization_defaults,
    sync_actor_organization_affiliations,
)
from game.population import human_max_hp_for_role, seed_chunk_items, seed_npc_finance, spawn_chunk_npcs
from game.player_businesses import PlayerBusinessSystem
from game.run_echoes import maybe_seed_run_echo_for_chunk, prime_run_echoes_runtime
from game.systems_incidents import IncidentKnowledgeSystem
from game.systems_business_reputation import BusinessReputationSystem
from game.run_bootstrap import bootstrap_normal_run, _register_justice_station_vehicles
from game.tutorial import (
    TutorialSystem,
    bootstrap_tutorial_run,
    current_tutorial_hint,
    is_tutorial_run,
    tutorial_no_persistence,
)
from game.player_config import load_player_config, mark_tutorial_run_seen, tutorial_requested_from_options
from game.release_runtime import (
    debug_mode_from_options,
    game_build_label,
    install_sigusr2_debug_unlock_handler,
    set_active_debug_sim,
    set_debug_mode,
    write_crash_report,
)
from game.vehicles import (
    generate_chunk_vehicle_records,
    roll_vehicle_profile,
    vehicle_metadata,
    vehicle_services_for_archetype,
)
from game.opportunities import evaluate_opportunity_board, seed_run_opportunities
from game.organization_reputation import OrganizationReputationSystem
from game.organization_response import OrganizationResponseSystem
from game.organization_practice_evolution import OrganizationPracticeEvolutionSystem
from game.criminal_drive_system import CriminalDriveSystem
from game.justice_vehicle_system import JusticeVehicleMisuseSystem
from game.perception_systems import (
    CombatPacingSystem,
    CoverSystem,
    LightingSystem,
    NoiseSystem,
    StealthSystem,
    VisibilitySystem,
)
from game.property_access import COMMON_AREA_ROOM_KINDS, default_site_services_for_archetype
from game.property_controllers import PropertySystem
from game.property_keys import ensure_actor_has_property_key, ensure_property_lock
from game.run_pressure import RunPressureSystem
from game.run_objectives import evaluate_run_objective, seed_run_objective
from game.run_epilogue import RunEpilogueLedgerSystem
from game.service_menu import ServiceMenuSystem
from game.site_services import SiteServiceSystem
from game.skill_progression import SkillProgressionSystem
from game.skills import seed_skill_profile
from game.situation_read import SituationReadSystem
from game.npc_boundary_system import NPCBoundaryEnforcementSystem
from game.npc_interaction_system import NPCInteractionSystem
from game.npc_income_system import NPCIncomeSystem
from game.objective_progress import ObjectiveProgressSystem
from game.criminal_justice_system import CriminalJusticeSystem
from game.trade_system import TradeSystem
from game.cultivation_runtime import CultivationSystem
from game.combat_systems import NPCItemUseSystem, NPCWeaponSystem, StatusEffectSystem, WeaponSystem
from game.environment_hazard_system import EnvironmentalHazardSystem
from game.fire_system import FireSystem
from game.human_identity import normalize_gender_identity, seed_player_identity_profile
from game.world_progression_systems import (
    FinalOperationSystem,
    OpportunitySystem,
    RivalOperatorSystem,
    WorldStreamingSystem,
)
from game.systems import (
    AnimalSocialSystem,
    BusinessPulseAftermathSystem,
    BusinessPulseSceneSystem,
    CameraSystem,
    CreatureHazardSystem,
    DoorWaitSystem,
    EavesdropSystem,
    EventLogSystem,
    ItemSystem,
    InputSystem,
    NPCInvestigateSystem,
    NPCMemorySystem,
    NPCNeedsSystem,
    NPCSettlementSystem,
    NPCRelationshipSystem,
    RumorSystem,
    NPCSocialDynamicsSystem,
    SocialKnowledgeInfluenceSystem,
    NPCWillSystem,
    SuppressionSystem,
    PlayerActionSystem,
    PropertyAwarenessSystem,
    PropertyDefenseSystem,
    RenderSystem,
)
from game.weapons import roll_weapon_instance
from ui.curses_view import CursesView
from ui.pygame_view import PygameView


_PLAYER_IDENTITY_OPTIONS = (
    {
        "value": "man",
        "label": "Man",
        "description": "NPCs use he/him and masculine social address.",
    },
    {
        "value": "woman",
        "label": "Woman",
        "description": "NPCs use she/her and feminine social address.",
    },
    {
        "value": "nonbinary",
        "label": "Nonbinary",
        "description": "NPCs use they/them with no honorific.",
    },
)


def _spawn(sim, *components):
    eid = sim.ecs.create()
    position = None

    for component in components:
        sim.ecs.add(eid, component)
        if isinstance(component, Position):
            position = component

    if position:
        sim.tilemap.add_entity(eid, position.x, position.y, position.z)

    return eid


def _env_flag(name, default):
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _env_int(name, default, minimum=None):
    raw = os.getenv(name)
    value = default
    if raw is not None:
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            value = default
    if minimum is not None:
        value = max(int(minimum), int(value))
    return int(value)


def _resolve_pygame_tile_px(default=24):
    return _env_int("BAKERRRR_TILE_SIZE_PX", default, minimum=8)


def _resolve_run_seed(default=None):
    raw = os.getenv("BAKERRRR_RUN_SEED")
    if raw is not None:
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            pass
    if default is not None:
        return int(default)
    return random.SystemRandom().randrange(1, 2_147_483_648)


def _resolve_ui_backend(argv=None):
    backend = str(os.getenv("BAKERRRR_UI", "curses") or "curses").strip().lower()
    args = list(argv or sys.argv[1:])
    for idx, raw in enumerate(args):
        value = str(raw).strip()
        if value.startswith("--ui="):
            backend = value.split("=", 1)[1].strip().lower() or backend
            continue
        if value == "--ui" and idx + 1 < len(args):
            backend = str(args[idx + 1]).strip().lower() or backend

    if backend in {"pygame", "tile", "tiles"}:
        return "pygame"
    return "curses"


def _resolve_tutorial_flag(argv=None, config=None):
    args = list(sys.argv[1:] if argv is None else argv)
    explicit = False
    tutorial = False
    for raw in args:
        value = str(raw).strip().lower()
        if value == "--tutorial":
            tutorial = True
            explicit = True
        elif value == "--no-tutorial":
            tutorial = False
            explicit = True
    return tutorial_requested_from_options(
        tutorial_flag=tutorial,
        config=config,
        explicit=explicit,
    )


def _argv_has_flag(argv, flag):
    wanted = str(flag or "").strip().lower()
    return any(str(raw).strip().lower() == wanted for raw in list(argv or ()))


def _resolve_debug_flag(argv=None):
    return debug_mode_from_options(list(sys.argv[1:] if argv is None else argv))


def _resource_root():
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root)
    return Path(__file__).resolve().parent


def _doctor_report(argv=None, *, save_dir=None):
    args = list(sys.argv[1:] if argv is None else argv)
    root = _resource_root()
    save_root = Path(save_dir) if save_dir is not None else SAVE_DIR
    backend = _resolve_ui_backend(args)
    tile_px = _resolve_pygame_tile_px()
    ok = True
    lines = [
        game_build_label(),
        f"python: {platform.python_version()} ({'ok' if sys.version_info >= (3, 11) else 'old'})",
        f"platform: {platform.platform()}",
        f"resource_root: {root}",
        f"save_dir: {save_root}",
        f"selected_ui: {backend}",
        f"tile_size_px: {tile_px}",
    ]
    if sys.version_info < (3, 11):
        ok = False

    pygame_available = importlib.util.find_spec("pygame") is not None
    curses_available = importlib.util.find_spec("curses") is not None
    lines.append(f"pygame: {'available' if pygame_available else 'missing'}")
    lines.append(f"curses: {'available' if curses_available else 'missing'}")
    if backend == "pygame" and not pygame_available:
        ok = False
    if backend == "curses" and not curses_available:
        ok = False

    json_paths = [
        root / "game" / "items.json",
        root / "game" / "loot_tables.json",
        root / "game" / "render_semantics.json",
    ]
    for path in json_paths:
        exists = path.is_file()
        lines.append(f"asset_json:{path.relative_to(root) if path.is_absolute() and root in path.parents else path}: {'ok' if exists else 'missing'}")
        if not exists:
            ok = False

    icon_png = root / "assets" / "icons" / "bakerrrr.png"
    lines.append(f"asset_icon:{icon_png.relative_to(root) if icon_png.is_absolute() and root in icon_png.parents else icon_png}: {'ok' if icon_png.is_file() else 'missing'}")
    if not icon_png.is_file():
        ok = False
    icon_ico = root / "assets" / "icons" / "bakerrrr.ico"
    if icon_ico.exists():
        lines.append(f"asset_icon_windows:{icon_ico.relative_to(root)}: ok")

    try:
        save_root.mkdir(parents=True, exist_ok=True)
        probe_path = save_root / ".bakerrrr_doctor_write_test"
        probe_path.write_text("ok\n", encoding="utf-8")
        probe_path.unlink(missing_ok=True)
        lines.append("save_dir_writable: ok")
    except OSError as exc:
        ok = False
        lines.append(f"save_dir_writable: failed ({exc})")

    try:
        config = load_player_config(config_path=save_root / "player_config.json")
        state = "completed" if config.get("tutorial_completed") else ("seen" if config.get("tutorial_seen") else "fresh")
        lines.append(f"player_config: readable ({state})")
    except OSError as exc:
        ok = False
        lines.append(f"player_config: unreadable ({exc})")

    lines.append(f"doctor: {'ok' if ok else 'failed'}")
    return ok, lines


def _install_usr1_stack_dump_handler():
    if not hasattr(signal, "SIGUSR1"):
        return False
    stream = getattr(sys, "__stderr__", None) or getattr(sys, "stderr", None)
    try:
        if not faulthandler.is_enabled():
            faulthandler.enable(file=stream, all_threads=True)
    except (AttributeError, OSError, RuntimeError, ValueError):
        pass
    try:
        faulthandler.register(signal.SIGUSR1, file=stream, all_threads=True, chain=False)
        return True
    except (AttributeError, OSError, RuntimeError, ValueError):
        return False


def _prompt_character_name_text():
    while True:
        try:
            raw = input("Character name: ")
        except EOFError:
            raw = ""
        name = normalize_character_name(raw)
        if name:
            return name
        print("Please enter a valid character name.")


def _prompt_character_name(stdscr):
    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        prompt_x = max(0, min(width - 1, 2))
        prompt_y = max(0, min(height - 1, 2))
        detail_y = min(height - 1, prompt_y + 2)
        input_y = min(height - 1, prompt_y + 4)
        max_text_width = max(0, width - prompt_x)
        prompt_text = "Character name:"[:max_text_width]
        detail_text = "Existing save with this name resumes once, then is deleted on load."[:max_text_width]

        stdscr.addstr(prompt_y, prompt_x, prompt_text)
        stdscr.addstr(detail_y, prompt_x, detail_text)
        stdscr.move(input_y, prompt_x)
        stdscr.clrtoeol()
        stdscr.refresh()

        try:
            curses.echo()
            try:
                curses.curs_set(1)
            except curses.error:
                pass
            raw = stdscr.getstr(input_y, prompt_x, 48)
        finally:
            curses.noecho()
            try:
                curses.curs_set(0)
            except curses.error:
                pass

        name = normalize_character_name(raw)
        if name:
            stdscr.erase()
            stdscr.refresh()
            return name


def _player_identity_default_index(value):
    normalized = normalize_gender_identity(value, default="nonbinary")
    for idx, row in enumerate(_PLAYER_IDENTITY_OPTIONS):
        if str(row.get("value", "")).strip().lower() == normalized:
            return idx
    return 2


def _prompt_choice_text(prompt, options, *, detail="", initial_index=0):
    rows = [dict(row) for row in tuple(options or ()) if isinstance(row, dict) and str(row.get("value", "")).strip()]
    if not rows:
        return None
    selected = max(0, min(int(initial_index), len(rows) - 1))
    while True:
        print(str(prompt or "").strip())
        if detail:
            print(str(detail).strip())
        for idx, row in enumerate(rows, start=1):
            marker = "*" if idx - 1 == selected else " "
            label = str(row.get("label", row.get("value", ""))).strip()
            description = str(row.get("description", "")).strip()
            suffix = f" - {description}" if description else ""
            print(f" {marker} {idx}. {label}{suffix}")
        try:
            raw = input("Choose 1-3 (blank cancels): ")
        except EOFError:
            return None
        choice = str(raw or "").strip()
        if not choice:
            return None
        if choice in {"1", "2", "3"}:
            idx = int(choice) - 1
            if 0 <= idx < len(rows):
                return str(rows[idx].get("value", "")).strip().lower()
        lowered = choice.lower()
        if lowered in {"man", "woman", "nonbinary", "non-binary", "nb", "neutral"}:
            normalized = normalize_gender_identity(choice, default="nonbinary")
            return normalized
        print("Please choose Man, Woman, or Nonbinary.")


def _prompt_choice_curses(
    stdscr,
    prompt,
    options,
    *,
    detail="",
    title="bakerrrr - identity",
    subtitle="Player identity setup",
    initial_index=0,
):
    rows = [dict(row) for row in tuple(options or ()) if isinstance(row, dict) and str(row.get("value", "")).strip()]
    if not rows:
        return None
    selected = max(0, min(int(initial_index), len(rows) - 1))
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    stdscr.keypad(True)
    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        left = max(0, min(width - 1, 2))
        y = 1

        def _draw_line(line, *, attr=0):
            nonlocal y
            if y >= height:
                return
            text = str(line or "")[: max(0, width - left - 1)]
            try:
                stdscr.addstr(y, left, text, attr)
            except curses.error:
                pass
            y += 1

        if title:
            _draw_line(title, attr=getattr(curses, "A_BOLD", 0))
        if subtitle:
            _draw_line(subtitle)
        y += 1
        _draw_line(prompt, attr=getattr(curses, "A_BOLD", 0))
        if detail:
            _draw_line(detail)
        y += 1
        for idx, row in enumerate(rows, start=1):
            label = str(row.get("label", row.get("value", ""))).strip()
            description = str(row.get("description", "")).strip()
            line = f"{idx}. {label}"
            if description:
                line = f"{line} - {description}"
            attr = getattr(curses, "A_REVERSE", 0) if idx - 1 == selected else 0
            _draw_line(line, attr=attr)
        y += 1
        _draw_line("Arrows move | 1-3 choose | Enter confirm | Esc cancel")
        stdscr.refresh()

        key = stdscr.getch()
        if key in (10, 13, getattr(curses, "KEY_ENTER", -1)):
            return str(rows[selected].get("value", "")).strip().lower()
        if key == 27:
            return None
        if key in (curses.KEY_UP, curses.KEY_LEFT):
            selected = (selected - 1) % len(rows)
            continue
        if key in (curses.KEY_DOWN, curses.KEY_RIGHT):
            selected = (selected + 1) % len(rows)
            continue
        if key in (ord("1"), ord("2"), ord("3")):
            idx = key - ord("1")
            if 0 <= idx < len(rows):
                return str(rows[idx].get("value", "")).strip().lower()


def _prompt_player_gender_identity_text(*, initial_value=None, character_name="", resume=False):
    prompt = f"Identity for {character_name or 'this run'}:"
    if resume:
        detail = "This save predates player identity metadata. Choose how NPCs should address you."
    else:
        detail = "Choose the identity NPCs use for pronouns and social address. Assigned sex is rolled separately."
    return _prompt_choice_text(
        prompt,
        _PLAYER_IDENTITY_OPTIONS,
        detail=detail,
        initial_index=_player_identity_default_index(initial_value),
    )


def _prompt_player_gender_identity(
    stdscr,
    *,
    initial_value=None,
    character_name="",
    resume=False,
):
    prompt = f"Identity for {character_name or 'this run'}:"
    if resume:
        detail = "This save predates player identity metadata. Choose how NPCs should address you."
        subtitle = "Resume identity upgrade"
    else:
        detail = "Choose the identity NPCs use for pronouns and social address. Assigned sex is rolled separately."
        subtitle = "Street-level run identity"
    return _prompt_choice_curses(
        stdscr,
        prompt,
        _PLAYER_IDENTITY_OPTIONS,
        detail=detail,
        title="bakerrrr - identity",
        subtitle=subtitle,
        initial_index=_player_identity_default_index(initial_value),
    )


def _prompt_player_gender_identity_view(
    view,
    *,
    initial_value=None,
    character_name="",
    resume=False,
):
    prompt = f"Identity for {character_name or 'this run'}:"
    if resume:
        detail = "This save predates player identity metadata. Choose how NPCs should address you."
        subtitle = "Resume identity upgrade"
    else:
        detail = "Choose the identity NPCs use for pronouns and social address. Assigned sex is rolled separately."
        subtitle = "Street-level run identity"
    if hasattr(view, "prompt_choice"):
        return view.prompt_choice(
            prompt,
            _PLAYER_IDENTITY_OPTIONS,
            detail=detail,
            title="bakerrrr - identity",
            banner="BAKERRRR",
            subtitle=subtitle,
            initial_index=_player_identity_default_index(initial_value),
        )
    return _prompt_player_gender_identity_text(
        initial_value=initial_value,
        character_name=character_name,
        resume=resume,
    )


def _player_identity_seed_token(sim):
    return f"{getattr(sim, 'seed', 0)}:player_identity"


def _player_identity_ready(identity):
    if identity is None:
        return False
    assigned_sex = str(getattr(identity, "assigned_sex", "") or "").strip().lower()
    gender_identity = str(getattr(identity, "gender_identity", "") or "").strip().lower()
    pronoun_set = str(getattr(identity, "pronoun_set", "") or "").strip().lower()
    return assigned_sex in {"male", "female"} and gender_identity in {"man", "woman", "nonbinary"} and pronoun_set in {"he", "she", "they"}


def _apply_player_identity_choice(sim, player_eid, *, character_name, gender_identity):
    if sim is None or player_eid is None:
        return None
    resolved_name = (
        normalize_character_name(character_name)
        or normalize_character_name(getattr(sim, "character_name", None))
        or "operator"
    )
    identities = sim.ecs.get(CreatureIdentity)
    identity = identities.get(player_eid)
    if identity is None:
        identity = CreatureIdentity(
            taxonomy_class="hominid",
            species="homo sapiens",
            creature_type="human",
            common_name="operator",
            personal_name=resolved_name,
        )
        sim.ecs.add(player_eid, identity)
    identity.taxonomy_class = "hominid"
    identity.species = "homo sapiens"
    identity.creature_type = "human"
    identity.common_name = str(getattr(identity, "common_name", "") or "operator").strip() or "operator"
    identity.personal_name = resolved_name
    profile = seed_player_identity_profile(_player_identity_seed_token(sim), gender_identity)
    identity.assigned_sex = str(profile.get("assigned_sex", "") or "").strip().lower() or None
    identity.gender_identity = str(profile.get("gender_identity", "") or "").strip().lower() or None
    identity.pronoun_set = str(profile.get("pronoun_set", "") or "").strip().lower() or None
    identity.name_gender_score = None
    identity.gender_inference_source = None
    return identity


def _ensure_loaded_player_identity(view, sim, character_name):
    player_eid = getattr(sim, "player_eid", None)
    if sim is None or player_eid is None:
        return False
    identities = sim.ecs.get(CreatureIdentity)
    identity = identities.get(player_eid)
    if _player_identity_ready(identity):
        if identity is not None:
            identity.taxonomy_class = str(getattr(identity, "taxonomy_class", "") or "hominid").strip().lower() or "hominid"
            identity.species = str(getattr(identity, "species", "") or "homo sapiens").strip().lower() or "homo sapiens"
            identity.creature_type = str(getattr(identity, "creature_type", "") or "human").strip().lower() or "human"
            identity.common_name = str(getattr(identity, "common_name", "") or "operator").strip() or "operator"
            if not str(getattr(identity, "personal_name", "") or "").strip():
                identity.personal_name = normalize_character_name(character_name) or "operator"
        return True
    selected_identity = _prompt_player_gender_identity_view(
        view,
        initial_value=getattr(identity, "gender_identity", None) if identity is not None else None,
        character_name=character_name,
        resume=True,
    )
    if not selected_identity:
        return False
    _apply_player_identity_choice(
        sim,
        player_eid,
        character_name=character_name,
        gender_identity=selected_identity,
    )
    return True


def _register_runtime_systems(sim, view, player):
    def _live_timeskip_stride(system, stride):
        setattr(system, "live_timeskip_tick_stride", int(stride))
        return system

    input_system = InputSystem(sim, view, player)
    input_system.runtime_tag = "input"
    cover_system = CoverSystem(sim)
    player_action_system = PlayerActionSystem(sim)
    camera_system = CameraSystem(sim, player)
    skill_progression_system = SkillProgressionSystem(sim, player)
    item_system = ItemSystem(sim, player)
    incident_knowledge_system = IncidentKnowledgeSystem(sim)
    observed_incident_consequence_system = ObservedIncidentConsequenceSystem(sim)
    observed_incident_response_system = ObservedIncidentResponseSystem(sim)
    observed_incident_dispatch_system = ObservedIncidentDispatchSystem(sim)
    criminal_justice_system = CriminalJusticeSystem(sim, player)
    service_menu_system = ServiceMenuSystem(sim, player)
    trade_system = TradeSystem(sim, player)
    local_trade_pressure_system = LocalTradePressureSystem(sim)
    weapon_system = WeaponSystem(sim, player)
    finance_system = FinanceSystem(sim, player)
    site_service_system = SiteServiceSystem(sim, player)
    npc_interaction_system = NPCInteractionSystem(sim, player)
    combat_pacing_system = CombatPacingSystem(sim, player, engage_radius=10, danger_radius=6, calm_frames_to_exit=14)
    situation_read_system = SituationReadSystem(sim, player)
    world_streaming_system = WorldStreamingSystem(sim, player)
    noise_system = NoiseSystem(sim)
    lighting_system = LightingSystem(sim, player)
    visibility_system = VisibilitySystem(sim, player)
    stealth_system = StealthSystem(sim, player)
    creature_hazard_system = CreatureHazardSystem(sim, player)
    environmental_hazard_system = EnvironmentalHazardSystem(sim)
    fire_system = FireSystem(sim)
    hunting_carcass_system = HuntingCarcassSystem(sim)
    cultivation_system = CultivationSystem(sim)

    property_system = PropertySystem(sim, player)
    player_business_system = PlayerBusinessSystem(sim, player)
    npc_income_system = NPCIncomeSystem(sim)
    property_awareness_system = PropertyAwarenessSystem(sim)
    property_defense_system = PropertyDefenseSystem(sim)
    npc_boundary_system = NPCBoundaryEnforcementSystem(sim)

    npc_memory_system = NPCMemorySystem(sim)
    animal_social_system = AnimalSocialSystem(sim)
    rumor_system = RumorSystem(sim)
    business_reputation_system = BusinessReputationSystem(sim)
    npc_needs_system = NPCNeedsSystem(sim)
    npc_settlement_system = NPCSettlementSystem(sim)
    status_effect_system = StatusEffectSystem(sim)
    altered_state_system = AlteredStateSystem(sim, player)
    npc_item_use_system = NPCItemUseSystem(sim)
    npc_social_system = NPCSocialDynamicsSystem(sim)
    npc_relationship_system = NPCRelationshipSystem(sim)
    eavesdrop_system = EavesdropSystem(sim, player)
    door_wait_system = DoorWaitSystem(sim)
    criminal_drive_system = CriminalDriveSystem(sim)
    justice_vehicle_misuse_system = JusticeVehicleMisuseSystem(sim)
    social_knowledge_influence_system = SocialKnowledgeInfluenceSystem(sim)
    npc_will_system = NPCWillSystem(sim)
    business_pulse_aftermath_system = BusinessPulseAftermathSystem(sim)
    business_pulse_scene_system = BusinessPulseSceneSystem(sim, player)
    npc_weapon_system = NPCWeaponSystem(sim, player)
    npc_system = NPCInvestigateSystem(sim)

    # Register WorldEventsSystem before SuppressionSystem
    from game.systems import WorldEventsSystem
    world_events_system = WorldEventsSystem(sim, player)

    opportunity_system = OpportunitySystem(sim, player, refresh_interval=20)
    rival_operator_system = RivalOperatorSystem(sim, player)
    objective_progress_system = ObjectiveProgressSystem(sim, player)
    run_pressure_system = RunPressureSystem(sim, player)
    organization_practice_evolution_system = OrganizationPracticeEvolutionSystem(sim)
    organization_reputation_system = OrganizationReputationSystem(sim, player)
    organization_response_system = OrganizationResponseSystem(sim, player)
    final_operation_system = FinalOperationSystem(sim, player)
    run_epilogue_system = RunEpilogueLedgerSystem(sim, player)
    tutorial_system = TutorialSystem(sim, player) if is_tutorial_run(sim) else None

    log_system = EventLogSystem(sim, player)
    render_system = RenderSystem(sim, view, player, hud_lines=10)
    render_system.runtime_tag = "render"
    sim.item_system = item_system
    sim.item_action_system = item_system.item_actions
    sim.site_service_system = site_service_system
    sim.trade_system = trade_system

    _live_timeskip_stride(combat_pacing_system, 0)
    _live_timeskip_stride(situation_read_system, 0)
    _live_timeskip_stride(player_action_system, 0)
    _live_timeskip_stride(skill_progression_system, 0)
    _live_timeskip_stride(service_menu_system, 0)
    _live_timeskip_stride(trade_system, 0)
    _live_timeskip_stride(local_trade_pressure_system, 0)
    _live_timeskip_stride(finance_system, 12)
    _live_timeskip_stride(npc_interaction_system, 0)
    _live_timeskip_stride(weapon_system, 0)
    _live_timeskip_stride(world_streaming_system, 4)
    _live_timeskip_stride(camera_system, 5)
    _live_timeskip_stride(cover_system, 10)
    _live_timeskip_stride(item_system, 1)
    _live_timeskip_stride(incident_knowledge_system, 10)
    _live_timeskip_stride(observed_incident_consequence_system, 10)
    _live_timeskip_stride(observed_incident_response_system, 10)
    _live_timeskip_stride(observed_incident_dispatch_system, 10)
    _live_timeskip_stride(lighting_system, 0)
    _live_timeskip_stride(property_system, 20)
    _live_timeskip_stride(player_business_system, 60)
    _live_timeskip_stride(npc_income_system, 60)
    _live_timeskip_stride(property_awareness_system, 20)
    _live_timeskip_stride(property_defense_system, 20)
    _live_timeskip_stride(npc_boundary_system, 2)
    _live_timeskip_stride(npc_memory_system, 10)
    _live_timeskip_stride(animal_social_system, 60)
    _live_timeskip_stride(rumor_system, 20)
    _live_timeskip_stride(business_reputation_system, 20)
    _live_timeskip_stride(npc_needs_system, 10)
    _live_timeskip_stride(npc_settlement_system, 600)
    _live_timeskip_stride(status_effect_system, 5)
    _live_timeskip_stride(altered_state_system, 0)
    _live_timeskip_stride(hunting_carcass_system, 0)
    _live_timeskip_stride(cultivation_system, 120)
    _live_timeskip_stride(npc_item_use_system, 5)
    _live_timeskip_stride(npc_social_system, 10)
    _live_timeskip_stride(npc_relationship_system, 0)
    _live_timeskip_stride(eavesdrop_system, 0)
    _live_timeskip_stride(social_knowledge_influence_system, 12)
    _live_timeskip_stride(business_pulse_aftermath_system, 60)
    _live_timeskip_stride(world_events_system, 60)
    _live_timeskip_stride(door_wait_system, 10)
    _live_timeskip_stride(criminal_drive_system, 60)
    _live_timeskip_stride(npc_will_system, 12)
    _live_timeskip_stride(business_pulse_scene_system, 0)
    _live_timeskip_stride(npc_weapon_system, 1)
    _live_timeskip_stride(criminal_justice_system, 5)
    _live_timeskip_stride(npc_system, 1)
    _live_timeskip_stride(opportunity_system, 20)
    _live_timeskip_stride(rival_operator_system, 60)
    _live_timeskip_stride(objective_progress_system, 60)
    _live_timeskip_stride(run_pressure_system, 60)
    _live_timeskip_stride(organization_practice_evolution_system, 600)
    _live_timeskip_stride(organization_reputation_system, 60)
    _live_timeskip_stride(organization_response_system, 60)
    _live_timeskip_stride(final_operation_system, 60)
    _live_timeskip_stride(run_epilogue_system, 120)
    if tutorial_system is not None:
        _live_timeskip_stride(tutorial_system, 0)
    _live_timeskip_stride(visibility_system, 10)
    _live_timeskip_stride(stealth_system, 30)
    _live_timeskip_stride(log_system, 0)

    sim.register_system(input_system)
    sim.register_system(cover_system)
    sim.register_system(combat_pacing_system)
    sim.register_system(situation_read_system)
    sim.register_system(player_action_system)
    sim.register_system(camera_system)
    sim.register_system(skill_progression_system)
    sim.register_system(item_system)
    sim.register_system(incident_knowledge_system)
    sim.register_system(observed_incident_consequence_system)
    sim.register_system(observed_incident_response_system)
    sim.register_system(observed_incident_dispatch_system)
    sim.register_system(service_menu_system)
    sim.register_system(trade_system)
    sim.register_system(local_trade_pressure_system)
    sim.register_system(finance_system)
    sim.register_system(site_service_system)
    sim.register_system(npc_interaction_system)
    sim.register_system(weapon_system)
    sim.register_system(world_streaming_system)
    sim.register_system(noise_system)
    sim.register_system(lighting_system)
    sim.register_system(creature_hazard_system)
    sim.register_system(environmental_hazard_system)
    sim.register_system(fire_system)
    sim.register_system(hunting_carcass_system)
    sim.register_system(cultivation_system)

    sim.register_system(property_system)
    sim.register_system(player_business_system)
    sim.register_system(npc_income_system)
    sim.register_system(property_awareness_system)
    sim.register_system(property_defense_system)
    sim.register_system(npc_boundary_system)

    sim.register_system(npc_memory_system)
    sim.register_system(animal_social_system)
    sim.register_system(rumor_system)
    sim.register_system(business_reputation_system)
    sim.register_system(npc_needs_system)
    sim.register_system(npc_settlement_system)
    sim.register_system(status_effect_system)
    sim.register_system(altered_state_system)
    sim.register_system(npc_item_use_system)
    sim.register_system(npc_social_system)
    sim.register_system(npc_relationship_system)
    sim.register_system(eavesdrop_system)
    sim.register_system(business_pulse_aftermath_system)
    sim.register_system(world_events_system)
    suppression_system = SuppressionSystem(sim, player)
    _live_timeskip_stride(suppression_system, 5)
    sim.register_system(door_wait_system)
    sim.register_system(criminal_drive_system)
    sim.register_system(justice_vehicle_misuse_system)
    sim.register_system(social_knowledge_influence_system)
    sim.register_system(npc_will_system)
    sim.register_system(business_pulse_scene_system)
    sim.register_system(npc_weapon_system)
    sim.register_system(suppression_system)
    sim.register_system(criminal_justice_system)
    sim.register_system(npc_system)

    sim.register_system(opportunity_system)
    sim.register_system(rival_operator_system)
    sim.register_system(objective_progress_system)
    sim.register_system(run_pressure_system)
    sim.register_system(organization_practice_evolution_system)
    sim.register_system(organization_reputation_system)
    sim.register_system(organization_response_system)
    sim.register_system(final_operation_system)
    sim.register_system(run_epilogue_system)
    if tutorial_system is not None:
        sim.register_system(tutorial_system)
    sim.register_system(visibility_system)
    sim.register_system(stealth_system)
    sim.register_system(log_system)
    sim.register_system(render_system)


def _consume_view_close_requested(view):
    consume = getattr(view, "consume_close_requested", None)
    if callable(consume):
        return bool(consume())
    close_requested = getattr(view, "close_requested", None)
    if callable(close_requested):
        return bool(close_requested())
    return False


def _request_session_quit(sim, *, source="input"):
    was_running = bool(getattr(sim, "running", True))
    sim.running = False
    if not was_running:
        return
    try:
        sim.emit(Event("quit_requested", eid=getattr(sim, "player_eid", None), source=str(source or "input")))
    except Exception:
        pass


def _run_loop(sim, view, character_name):
    set_active_debug_sim(sim)
    frame_seconds = 1.0 / 20.0
    # Advance the world tick every WORLD_TICK_DIVISOR UI frames.
    # InputSystem (runs_while_paused=True) still fires every frame so player
    # input and event-driven movement remain fully responsive.
    # Turn-based mode (e.g. combat) bypasses the throttle so it stays snappy.
    WORLD_TICK_DIVISOR = int(
        (sim.world_traits.get("tick_divisor") if isinstance(getattr(sim, "world_traits", None), dict) else None)
        or 4
    )
    LIVE_TIMESKIP_MAX_BATCH = 900
    LIVE_TIMESKIP_TARGET_SLICES = 6
    LIVE_TIMESKIP_SLICE_BUDGET_SECONDS = 0.02
    LIVE_TIMESKIP_MIN_YIELD_SECONDS = 0.001
    _frame = 0
    while True:
        if _consume_view_close_requested(view):
            _request_session_quit(sim, source="window_close")
            break
        if not sim.running:
            break

        site_service_system = getattr(sim, "site_service_system", None)
        if site_service_system is not None:
            try:
                site_service_system.finalize_live_timeskip_result_if_ready()
            except AttributeError:
                pass

        frame_start = time.perf_counter()

        live_timeskip = getattr(sim, "live_timeskip", {})
        if isinstance(live_timeskip, dict) and bool(live_timeskip.get("active")):
            pump_window = getattr(view, "pump_window", None)
            if callable(pump_window):
                pump_window()
            drain_keys = getattr(view, "drain_keys", None)
            if callable(drain_keys):
                drain_keys()
                if _consume_view_close_requested(view):
                    _request_session_quit(sim, source="window_close")
                    break
            remaining = max(0, int(live_timeskip.get("target_end_tick", sim.tick)) - int(getattr(sim, "tick", 0)))
            target_slices = max(1, int(LIVE_TIMESKIP_TARGET_SLICES))
            batch = max(
                1,
                min(
                    int(LIVE_TIMESKIP_MAX_BATCH),
                    ((remaining + target_slices - 1) // target_slices) if remaining > 0 else target_slices,
                ),
            )
            slice_deadline = time.perf_counter() + float(LIVE_TIMESKIP_SLICE_BUDGET_SECONDS)
            steps = 0
            while steps < batch:
                if not sim.running:
                    break
                live_timeskip = getattr(sim, "live_timeskip", {})
                if not isinstance(live_timeskip, dict) or not bool(live_timeskip.get("active")):
                    break
                sim.run_headless_tick()
                steps += 1
                if site_service_system is not None and hasattr(site_service_system, "after_live_timeskip_tick"):
                    site_service_system.after_live_timeskip_tick()
                if time.perf_counter() >= slice_deadline:
                    break
            if site_service_system is not None:
                try:
                    site_service_system.finalize_live_timeskip_result_if_ready()
                except AttributeError:
                    pass
            sim.render_frame()
            if callable(pump_window):
                pump_window()
            view.refresh()
            if _consume_view_close_requested(view):
                _request_session_quit(sim, source="window_close")
                break
            elapsed = time.perf_counter() - frame_start
            if elapsed < float(LIVE_TIMESKIP_MIN_YIELD_SECONDS):
                time.sleep(float(LIVE_TIMESKIP_MIN_YIELD_SECONDS) - elapsed)
            continue

        _frame += 1
        throttled = (_frame % WORLD_TICK_DIVISOR != 0) and not sim.turn_based
        if throttled:
            sim.set_time_paused(True, reason="tick_throttle")
        sim.update()
        if throttled:
            sim.set_time_paused(False, reason="tick_throttle")

        view.refresh()
        if _consume_view_close_requested(view):
            _request_session_quit(sim, source="window_close")
            break

        elapsed = time.perf_counter() - frame_start
        sleep_for = frame_seconds - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)

    run_end = None
    if isinstance(getattr(sim, "world_traits", None), dict):
        maybe_run_end = sim.world_traits.get("run_end")
        if isinstance(maybe_run_end, dict):
            run_end = dict(maybe_run_end)

    if run_end:
        return run_end

    if tutorial_no_persistence(sim):
        summary_lines = [
            "Tutorial ended before completion.",
            "This practice run did not write a save or alter future runs.",
        ]
        hint = current_tutorial_hint(sim)
        if hint:
            summary_lines.insert(1, hint)
        return {
            "show_post_curses": True,
            "outcome": "ended",
            "reason": "tutorial_quit",
            "objective_title": "Tutorial",
            "tick": int(getattr(sim, "tick", 0)),
            "summary_lines": summary_lines,
            "tutorial": True,
            "saved": False,
        }

    save_path = save_character_run(sim, character_name)
    return {
        "show_post_curses": True,
        "outcome": "saved",
        "reason": "quit",
        "objective_title": character_name,
        "tick": int(getattr(sim, "tick", 0)),
        "summary_lines": [
            f"Character saved: {character_name}",
            f"Save file: {save_path.relative_to(save_path.parent.parent)}",
        ],
    }


def _build_demo_map(sim, chunk):
    rng = random.Random(f"{sim.seed}:{chunk['cx']}:{chunk['cy']}:map")

    width = sim.tilemap.width
    height = sim.tilemap.height

    for z in range(sim.tilemap.max_floors):
        for y in range(height):
            for x in range(width):
                sim.tilemap.set_tile(x, y, Tile(walkable=True, transparent=True, glyph="."), z=z)

        for x in range(width):
            sim.tilemap.set_tile(x, 0, Tile(walkable=False, transparent=False, glyph="#"), z=z)
            sim.tilemap.set_tile(x, height - 1, Tile(walkable=False, transparent=False, glyph="#"), z=z)

        for y in range(height):
            sim.tilemap.set_tile(0, y, Tile(walkable=False, transparent=False, glyph="#"), z=z)
            sim.tilemap.set_tile(width - 1, y, Tile(walkable=False, transparent=False, glyph="#"), z=z)

        for _ in range(12):
            x = rng.randint(2, width - 3)
            y = rng.randint(2, height - 3)
            sim.tilemap.set_tile(x, y, Tile(walkable=False, transparent=False, glyph="#"), z=z)

    stairs_x = 3
    stairs_y = 3
    elevator_x = width - 4
    elevator_y = 3
    rear_stairs_x = 3
    rear_stairs_y = height - 4

    sim.tilemap.add_floor_link(stairs_x, stairs_y, from_z=0, to_z=1, kind="stairs")
    sim.tilemap.add_floor_link(rear_stairs_x, rear_stairs_y, from_z=1, to_z=2, kind="stairs")
    sim.tilemap.add_floor_link(elevator_x, elevator_y, from_z=0, to_z=1, kind="elevator")
    sim.tilemap.add_floor_link(elevator_x, elevator_y, from_z=1, to_z=2, kind="elevator")

    sim.tilemap.set_tile(stairs_x, stairs_y, Tile(walkable=True, transparent=True, glyph=">"), z=0)
    sim.tilemap.set_tile(stairs_x, stairs_y, Tile(walkable=True, transparent=True, glyph="<"), z=1)
    sim.tilemap.set_tile(rear_stairs_x, rear_stairs_y, Tile(walkable=True, transparent=True, glyph=">"), z=1)
    sim.tilemap.set_tile(rear_stairs_x, rear_stairs_y, Tile(walkable=True, transparent=True, glyph="<"), z=2)

    for z in range(3):
        sim.tilemap.set_tile(elevator_x, elevator_y, Tile(walkable=True, transparent=True, glyph="E"), z=z)


def _ensure_walkable(sim, x, y, z, glyph="."):
    if hasattr(sim, "door_state_at") and hasattr(sim, "apply_door_state"):
        state = sim.door_state_at(x, y, z)
        if isinstance(state, dict):
            sim.apply_door_state(x, y, z)
            return
    existing = sim.tilemap.tile_at(x, y, z)
    if existing and existing.walkable:
        return
    sim.tilemap.set_tile(x, y, Tile(walkable=True, transparent=True, glyph=glyph), z=z)


def _pick_playtest_start_chunk(sim, rng, radius=14, attempts=48, preferred_area_type="city"):
    fallback = (0, 0)
    wanted = str(preferred_area_type or "").strip().lower()

    for _ in range(max(1, int(attempts))):
        cx = rng.randint(-int(radius), int(radius))
        cy = rng.randint(-int(radius), int(radius))
        fallback = (cx, cy)
        if not wanted:
            return fallback
        area_type = str(sim.world.pick_area_type(cx, cy)).strip().lower()
        if area_type == wanted:
            return fallback

    return fallback


def _pick_chunk_street_spawn(sim, chunk, rng, reserved=None, z=0):
    reserved_positions = {tuple(pos) for pos in (reserved or ())}
    chunk_size = int(max(8, sim.chunk_size))
    origin_x, origin_y = sim.chunk_origin(chunk["cx"], chunk["cy"])

    street_candidates = []
    fallback_candidates = []
    for y in range(origin_y + 1, origin_y + chunk_size - 1):
        for x in range(origin_x + 1, origin_x + chunk_size - 1):
            pos = (x, y, z)
            if pos in reserved_positions:
                continue

            tile = sim.tilemap.tile_at(x, y, z)
            if not tile or not tile.walkable:
                continue

            if sim.structure_at(x, y, z) is None and sim.property_at(x, y, z) is None:
                street_candidates.append(pos)
                continue

            fallback_candidates.append(pos)

    if street_candidates:
        return rng.choice(street_candidates)
    if fallback_candidates:
        return rng.choice(fallback_candidates)

    center_x = origin_x + max(2, chunk_size // 2)
    center_y = origin_y + max(2, chunk_size // 2)
    return (center_x, center_y, z)


def _merge_site_services(metadata, extra_services):
    base = []
    if isinstance(metadata, dict):
        raw = metadata.get("site_services", ())
        if isinstance(raw, (list, tuple, set)):
            base = [str(service).strip().lower() for service in raw if str(service).strip()]
    merged = list(dict.fromkeys(base + [str(service).strip().lower() for service in extra_services if str(service).strip()]))
    if isinstance(metadata, dict):
        metadata["site_services"] = merged
    return merged


def _pick_nearest_vehicle_property(sim, x, y, z=0, radius=5, owner_tags=None):
    allowed_tags = None
    if owner_tags:
        allowed_tags = {str(tag).strip().lower() for tag in owner_tags if str(tag).strip()}
    best = None
    best_dist = 999999
    for prop in sim.properties.values():
        if int(prop.get("z", -1)) != int(z):
            continue
        if str(prop.get("kind", "")).strip().lower() != "vehicle":
            continue
        if allowed_tags is not None:
            owner_tag = str(prop.get("owner_tag", "")).strip().lower()
            if owner_tag not in allowed_tags:
                continue
        dist = abs(int(prop.get("x", 0)) - int(x)) + abs(int(prop.get("y", 0)) - int(y))
        if dist > int(radius):
            continue
        if dist < best_dist:
            best = prop
            best_dist = dist
    return best


def _ensure_starter_vehicle(sim, player_eid, player_pos, rng):
    if player_eid is None or not player_pos:
        return None

    vehicle_state = sim.ecs.get(VehicleState).get(player_eid)
    if not vehicle_state:
        return None

    nearby = _pick_nearest_vehicle_property(
        sim,
        x=player_pos[0],
        y=player_pos[1],
        z=player_pos[2],
        radius=5,
        owner_tags={"public", "unowned", "none", "neutral"},
    )
    if nearby:
        sim.assign_property_owner(nearby["id"], owner_eid=player_eid, owner_tag="player")
        metadata = nearby.get("metadata", {})
        if isinstance(metadata, dict):
            metadata["display_color"] = "vehicle_player"
            metadata["vehicle_owner_tag"] = "player"
            try:
                fuel_capacity = int(metadata.get("fuel_capacity", metadata.get("fuel", 60)))
            except (TypeError, ValueError):
                fuel_capacity = 60
            metadata["fuel"] = max(10, fuel_capacity)
        ensure_property_lock(
            nearby,
            locked=True,
            key_label=str(nearby.get("name", "Vehicle")).strip() or "Vehicle",
            lock_tier=int(metadata.get("property_lock_tier", 2)) if isinstance(metadata, dict) else 2,
        )
        key_ok, _instance_id, _created = ensure_actor_has_property_key(sim, player_eid, nearby, owner_tag="player")
        if not key_ok and isinstance(metadata, dict):
            metadata["property_locked"] = False
        vehicle_state.set_active_vehicle(nearby["id"], tick=sim.tick)
        return nearby

    cx, cy = sim.chunk_coords(player_pos[0], player_pos[1])
    chunk = sim.world.get_chunk(cx, cy)
    profile = roll_vehicle_profile(rng, quality="used")
    try:
        profile["fuel"] = int(profile.get("fuel_capacity", profile.get("fuel", 60)))
    except (TypeError, ValueError):
        profile["fuel"] = 60
    vehicle_name = f"{profile['make']} {profile['model']}"
    vehicle_token = f"veh:starter:{cx}:{cy}:{sim.tick}"
    metadata = vehicle_metadata(
        profile,
        chunk=(cx, cy),
        owner_tag="player",
        display_color="vehicle_player",
        locked=True,
        key_id=vehicle_token,
        key_label=vehicle_name,
        lock_tier=2,
    )
    metadata["vehicle_id"] = vehicle_token

    vehicle_id = sim.register_property(
        name=vehicle_name,
        kind="vehicle",
        x=int(player_pos[0]),
        y=int(player_pos[1]),
        z=int(player_pos[2]),
        owner_eid=player_eid,
        owner_tag="player",
        metadata=metadata,
    )
    record = {
        "id": vehicle_id,
        "kind": "vehicle",
        "x": int(player_pos[0]),
        "y": int(player_pos[1]),
        "z": int(player_pos[2]),
        "archetype": "vehicle",
        "building_id": None,
    }
    chunk_key = (int(chunk.get("cx", cx)), int(chunk.get("cy", cy)))
    sim.chunk_property_records.setdefault(chunk_key, []).append(record)
    vehicle = sim.properties.get(vehicle_id)
    key_ok, _instance_id, _created = ensure_actor_has_property_key(sim, player_eid, vehicle, owner_tag="player")
    if not key_ok and vehicle:
        vehicle_meta = vehicle.get("metadata", {})
        if isinstance(vehicle_meta, dict):
            vehicle_meta["property_locked"] = False
    vehicle_state.set_active_vehicle(vehicle_id, tick=sim.tick)
    return vehicle


def _bond_pair(sim, left_eid, right_eid, relation, closeness=0.75, trust=0.75):
    socials = sim.ecs.get(NPCSocial)
    left = socials.get(left_eid)
    right = socials.get(right_eid)
    if not left or not right:
        return

    left.add_bond(right_eid, kind=relation, closeness=closeness, trust=trust)
    right.add_bond(left_eid, kind=relation, closeness=closeness, trust=trust)


def _register_chunk_properties(sim, chunk):
    seed_chunk_organizations(sim, chunk)
    rng = random.Random(f"{sim.seed}:{chunk['cx']}:{chunk['cy']}:properties")
    records = []

    chunk_size = int(max(8, sim.chunk_size))
    origin_x = chunk["cx"] * chunk_size
    origin_y = chunk["cy"] * chunk_size
    area_type = str(chunk.get("district", {}).get("area_type", "city")).strip().lower() or "city"
    finance_by_archetype = {
        "bank": ("banking", "insurance"),
        "brokerage": ("banking", "insurance"),
        "office": ("insurance",),
        "tower": ("insurance",),
        "pawn_shop": ("insurance",),
        "backroom_clinic": ("insurance",),
    }

    for block in chunk.get("blocks", []):
        bx = block.get("grid_x", 0)
        by = block.get("grid_y", 0)
        building_count = len(block.get("buildings", []))

        for i, building in enumerate(block.get("buildings", [])):
            layout = layout_chunk_building(
                origin_x=origin_x,
                origin_y=origin_y,
                chunk_size=chunk_size,
                block_grid_x=bx,
                block_grid_y=by,
                building_index=i,
                building=building,
                building_count=building_count,
            )
            if not layout:
                continue

            x = int(layout["anchor_x"])
            y = int(layout["anchor_y"])
            z = 0

            _ensure_walkable(sim, x, y, z, glyph=".")

            archetype = building["archetype"]
            local_building_id = str(building.get("building_id", "") or "").strip()
            chunk_building_id = world_building_id(chunk["cx"], chunk["cy"], local_building_id)
            records.extend(register_large_span_child_properties(
                sim,
                parent_source=building,
                parent_layout=layout,
                parent_building_id=chunk_building_id,
                chunk_key=(chunk["cx"], chunk["cy"]),
                area_type=area_type,
                rng=rng,
                ensure_walkable=_ensure_walkable,
                district=chunk.get("district"),
            ))
            finance_services = list(finance_by_archetype.get(archetype, ()))
            site_services = list(dict.fromkeys(
                list(default_site_services_for_archetype(archetype))
                + list(vehicle_services_for_archetype(archetype))
            ))
            business_name = str(building.get("business_name") or "").strip()
            span_name = str(building.get("span_name") or "").strip()
            business_founder_name = str(building.get("business_founder_name") or "").strip()
            business_founder_first_name = str(building.get("business_founder_first_name") or "").strip()
            business_founder_last_name = str(building.get("business_founder_last_name") or "").strip()
            display_name = span_name or business_name or f"{archetype}:{building['building_id']}"
            property_id = sim.register_property(
                name=display_name,
                kind="building",
                x=x,
                y=y,
                z=z,
                owner_eid=None,
                owner_tag="city",
                metadata={
                    "archetype": archetype,
                    "building_id": chunk_building_id,
                    "local_building_id": local_building_id or None,
                    "large_parcel": bool(building.get("large_parcel")),
                    "parcel_span_x": int(building.get("parcel_span_x", 1) or 1),
                    "parcel_span_y": int(building.get("parcel_span_y", 1) or 1),
                    "floors": int(building.get("floors", 1)),
                    "basement_levels": int(building.get("basement_levels", 0)),
                    "rooms": list(building.get("rooms", ())),
                    "common_area_room_kinds": sorted(COMMON_AREA_ROOM_KINDS),
                    "common_area_kinds": sorted(COMMON_AREA_ROOM_KINDS),
                    "span_kind": str(building.get("span_kind", "") or "").strip().lower() or None,
                    "span_id": str(building.get("span_id", "") or "").strip() or None,
                    "span_name": span_name or None,
                    "span_founder_name": str(building.get("span_founder_name", "") or "").strip() or None,
                    "span_founder_first_name": str(building.get("span_founder_first_name", "") or "").strip() or None,
                    "span_founder_last_name": str(building.get("span_founder_last_name", "") or "").strip() or None,
                    "span_parent": bool(building.get("span_kind")),
                    "tenant_specs": [dict(spec) for spec in building.get("tenant_specs", ()) if isinstance(spec, dict)],
                    "housing_specs": [dict(spec) for spec in building.get("housing_specs", ()) if isinstance(spec, dict)],
                    "footprint": dict(layout.get("footprint", {})),
                    "placement": dict(layout.get("placement", {})),
                    "placement_profile": dict(building.get("placement_profile", {})) if isinstance(building.get("placement_profile"), dict) else None,
                    "entry": dict(layout.get("entry", {})),
                    "apertures": [dict(aperture) for aperture in layout.get("apertures", ()) if isinstance(aperture, dict)],
                    "signage": dict(layout["signage"]) if isinstance(layout.get("signage"), dict) else None,
                    "security_features": list(building.get("security_features", ())),
                    "purchase_cost": rng.randint(180, 460),
                    "finance_services": finance_services,
                    "site_services": site_services,
                    "is_storefront": bool(building.get("is_storefront")),
                    "public": bool(building.get("public")),
                    "business_name": business_name or None,
                    "business_founder_name": business_founder_name or None,
                    "business_founder_first_name": business_founder_first_name or None,
                    "business_founder_last_name": business_founder_last_name or None,
                    "chunk": (chunk["cx"], chunk["cy"]),
                },
            )
            prop = sim.properties.get(property_id)
            seed_property_organization_defaults(prop, district=chunk.get("district"))
            ensure_property_organization(sim, prop)

            records.append({
                "id": property_id,
                "kind": "building",
                "x": x,
                "y": y,
                "z": z,
                "archetype": archetype,
                "building_id": chunk_building_id,
                "basement_levels": int(building.get("basement_levels", 0)),
            })

    reserved_site_footprints = []
    for idx, site in enumerate(chunk.get("sites", ())):
        if not isinstance(site, dict):
            continue

        layout = layout_chunk_site(
            origin_x=origin_x,
            origin_y=origin_y,
            chunk_size=chunk_size,
            site_index=idx,
            site=site,
            reserved_footprints=reserved_site_footprints,
        )
        if not layout:
            continue
        reserved_site_footprints.extend(site_layout_reserved_footprints(layout))

        x = int(layout["anchor_x"])
        y = int(layout["anchor_y"])
        z = 0

        _ensure_walkable(sim, x, y, z, glyph=".")

        site_kind = str(site.get("kind", "site")).strip().lower() or "site"
        site_building_id = f"{chunk['cx']}:{chunk['cy']}:{site.get('site_id', idx)}"
        records.extend(register_large_span_child_properties(
            sim,
            parent_source=site,
            parent_layout=layout,
            parent_building_id=site_building_id,
            chunk_key=(chunk["cx"], chunk["cy"]),
            area_type=area_type,
            rng=rng,
            ensure_walkable=_ensure_walkable,
            district=chunk.get("district"),
        ))
        span_name = str(site.get("span_name") or "").strip()
        site_name = span_name or str(site.get("name", site_kind.replace("_", " ").title())).strip() or "Site"
        gameplay = site_gameplay_profile(site)
        public = bool(gameplay.get("public"))
        site_services = list(gameplay.get("site_services", ()))
        site_services = _merge_site_services(
            {"site_services": site_services},
            vehicle_services_for_archetype(site_kind),
        )
        property_id = sim.register_property(
            name=site_name,
            kind="building",
            x=x,
            y=y,
            z=z,
            owner_eid=None,
            owner_tag="public" if public else area_type,
            metadata={
                "archetype": site_kind,
                "site_kind": site_kind,
                "floors": 1,
                "rooms": list(site.get("rooms", ("entry", "room")) or ("entry", "room")),
                "building_id": site_building_id,
                "common_area_room_kinds": sorted(COMMON_AREA_ROOM_KINDS),
                "common_area_kinds": sorted(COMMON_AREA_ROOM_KINDS),
                "span_kind": str(site.get("span_kind", "") or "").strip().lower() or None,
                "span_id": str(site.get("span_id", "") or "").strip() or None,
                "span_name": span_name or None,
                "span_founder_name": str(site.get("span_founder_name", "") or "").strip() or None,
                "span_founder_first_name": str(site.get("span_founder_first_name", "") or "").strip() or None,
                "span_founder_last_name": str(site.get("span_founder_last_name", "") or "").strip() or None,
                "span_parent": bool(site.get("span_kind")),
                "tenant_specs": [dict(spec) for spec in site.get("tenant_specs", ()) if isinstance(spec, dict)],
                "housing_specs": [dict(spec) for spec in site.get("housing_specs", ()) if isinstance(spec, dict)],
                "footprint": dict(layout.get("footprint", {})),
                "entry": dict(layout.get("entry", {})),
                "apertures": [dict(aperture) for aperture in layout.get("apertures", ()) if isinstance(aperture, dict)],
                "signage": dict(layout["signage"]) if isinstance(layout.get("signage"), dict) else None,
                "purchase_cost": rng.randint(110, 260),
                "finance_services": list(gameplay.get("finance_services", ())),
                "is_storefront": bool(gameplay.get("is_storefront")),
                "site_services": list(site_services),
                "public": public,
                "chunk": (chunk["cx"], chunk["cy"]),
            },
        )
        prop = sim.properties.get(property_id)
        seed_property_organization_defaults(prop, district=chunk.get("district"))
        ensure_property_organization(sim, prop)

        records.append({
            "id": property_id,
            "kind": "building",
            "x": x,
            "y": y,
            "z": z,
            "archetype": site_kind,
            "building_id": site_building_id,
        })

    fixture_count = max(1, chunk_size // 8) if area_type != "city" else max(4, chunk_size // 4)
    fixtures = generate_chunk_fixture_records(
        sim,
        chunk,
        rng,
        origin_x=origin_x,
        origin_y=origin_y,
        chunk_size=chunk_size,
        target_count=fixture_count,
    )
    for fixture in fixtures:
        x = int(fixture["x"])
        y = int(fixture["y"])
        kind = str(fixture.get("kind", "fixture")).strip().lower() or "fixture"
        metadata = dict(fixture.get("metadata", {}))
        metadata["chunk"] = (chunk["cx"], chunk["cy"])
        property_id = sim.register_property(
            name=str(fixture.get("name", "Fixture")).strip() or "Fixture",
            kind=kind,
            x=x,
            y=y,
            z=0,
            owner_eid=None,
            owner_tag=str(fixture.get("owner_tag", "city")).strip() or "city",
            metadata=metadata,
        )

        records.append({
            "id": property_id,
            "kind": kind,
            "x": x,
            "y": y,
            "z": 0,
            "archetype": metadata.get("archetype"),
            "building_id": None,
        })

    _register_justice_station_vehicles(
        sim,
        chunk,
        records,
        origin_x=origin_x,
        origin_y=origin_y,
        chunk_size=chunk_size,
    )

    vehicle_target_count = max(2, chunk_size // 12) if area_type == "city" else (1 if rng.random() < 0.55 else 0)
    vehicles = generate_chunk_vehicle_records(
        sim,
        chunk,
        rng,
        origin_x=origin_x,
        origin_y=origin_y,
        chunk_size=chunk_size,
        target_count=vehicle_target_count,
    )
    for vehicle in vehicles:
        x = int(vehicle["x"])
        y = int(vehicle["y"])
        if sim.property_at(x, y, 0):
            continue
        property_id = sim.register_property(
            name=str(vehicle.get("name", "Vehicle")).strip() or "Vehicle",
            kind="vehicle",
            x=x,
            y=y,
            z=0,
            owner_eid=None,
            owner_tag=str(vehicle.get("owner_tag", "public")).strip() or "public",
            metadata={**dict(vehicle.get("metadata", {})), "chunk": (chunk["cx"], chunk["cy"])},
        )
        records.append({
            "id": property_id,
            "kind": "vehicle",
            "x": x,
            "y": y,
            "z": 0,
            "archetype": "vehicle",
            "building_id": None,
        })

    return records


def _pick_property(records, preferred_archetypes=None, used=None, building_only=True):
    used = used or set()
    candidates = []

    for record in records:
        if record["id"] in used:
            continue
        if building_only and record["kind"] != "building":
            continue
        if preferred_archetypes and record.get("archetype") not in preferred_archetypes:
            continue
        candidates.append(record)

    if not candidates and preferred_archetypes:
        for record in records:
            if record["id"] in used:
                continue
            if building_only and record["kind"] != "building":
                continue
            candidates.append(record)

    if not candidates:
        return None

    return candidates[0]


def _pick_job(sim, rng, property_records, preferred_archetypes=None):
    candidates = [p for p in property_records if p["kind"] == "building"]
    economy_profile = chunk_economy_profile(sim, sim.active_chunk)

    if preferred_archetypes:
        filtered = [p for p in candidates if p.get("archetype") in preferred_archetypes]
        if filtered:
            candidates = filtered

    if not candidates:
        return sim.world.draw_career(rng), {"property_id": None, "building_id": None, "archetype": None}

    weighted = []
    for property_ref in candidates:
        archetype = property_ref.get("archetype")
        weight = workplace_archetype_weight(economy_profile, archetype)
        weighted.append((property_ref, weight))

    total = sum(weight for _property_ref, weight in weighted)
    pick = rng.uniform(0.0, total) if total > 0.0 else 0.0
    running = 0.0
    property_ref = candidates[-1]
    for candidate, weight in weighted:
        running += weight
        if pick <= running:
            property_ref = candidate
            break

    career = pick_career_for_workplace(
        sim.world,
        rng,
        archetype=property_ref.get("archetype"),
        economy_profile=economy_profile,
    )
    prop = sim.properties.get(property_ref["id"])
    organization_eid = ensure_property_organization(sim, prop) if prop else None
    workplace = {
        "property_id": property_ref["id"],
        "building_id": property_ref.get("building_id"),
        "archetype": property_ref.get("archetype"),
        "organization_eid": organization_eid,
    }
    return career, workplace


def _coords_or(property_ref, fallback):
    if property_ref:
        return property_ref["x"], property_ref["y"], property_ref["z"]
    return fallback


def _claim_property(sim, property_id, owner_eid=None, owner_tag=None):
    prop = sim.properties.get(property_id)
    if not prop:
        return

    old_owner = prop.get("owner_eid")
    sim.assign_property_owner(property_id, owner_eid=owner_eid, owner_tag=owner_tag)
    sim.emit(Event(
        "property_owner_changed",
        property_id=property_id,
        old_owner_eid=old_owner,
        new_owner_eid=owner_eid,
    ))


def _seed_world_items(sim, property_records):
    chunk = getattr(sim, "active_chunk", None)
    if not isinstance(chunk, dict):
        return 0
    return int(seed_chunk_items(sim, chunk, property_records))


def _give_item(sim, eid, item_id, quantity=1, owner_tag="npc"):
    inventory = sim.ecs.get(Inventory).get(eid)
    if not inventory:
        return False

    item_def = ITEM_CATALOG.get(item_id)
    if not item_def:
        return False

    return inventory.add_item(
        item_id=item_id,
        quantity=quantity,
        stack_max=item_def.get("stack_max", 1),
        instance_factory=sim.new_item_instance_id,
        owner_eid=eid,
        owner_tag=owner_tag,
        metadata={"starter_item": True},
    )[0]


def _give_weapon(sim, eid, weapon_id, named_chance=0.2, owner_tag="npc", inventory_backed=False):
    loadout = sim.ecs.get(WeaponLoadout).get(eid)
    if not loadout:
        return False

    rng = random.Random(f"{sim.seed}:weapon:{eid}:{weapon_id}")
    instance = roll_weapon_instance(rng, weapon_id, named_chance=named_chance)
    if inventory_backed:
        inventory = sim.ecs.get(Inventory).get(eid)
        item_def = ITEM_CATALOG.get(weapon_id)
        if inventory and item_def:
            metadata = {
                "starter_item": True,
                "weapon_instance": dict(instance),
            }
            custom_name = str(instance.get("custom_name", "")).strip()
            if custom_name:
                metadata["display_name"] = custom_name
            added, instance_id = inventory.add_item(
                item_id=weapon_id,
                quantity=1,
                stack_max=item_def.get("stack_max", 1),
                instance_factory=sim.new_item_instance_id,
                owner_eid=eid,
                owner_tag=owner_tag,
                metadata=metadata,
            )
            if not added:
                return False
            instance["inventory_instance_id"] = instance_id
    loadout.add_weapon(weapon_id, instance=instance)
    return True


def _run_new_game_legacy(view, character_name):
    screen_w, screen_h = view.size()

    map_width = max(24, min(96, screen_w))
    map_height = max(14, min(40, screen_h - 10))

    sim = Simulation(
        seed=_resolve_run_seed(),
        map_width=map_width,
        map_height=map_height,
        max_floors=3,
        chunk_size=24,
    )
    sim.character_name = character_name
    sim.world_traits["character_name"] = character_name
    sim.world_traits["clock"] = {
        "start_hour": 9,
        "ticks_per_hour": 600,
    }
    final_op_downed_fails_run = _env_flag(
        "BAKERRRR_FINAL_OP_DOWNED_FAILS_RUN",
        True,
    )
    sim.world_traits["rules"] = {
        "final_op_downed_fails_run": bool(final_op_downed_fails_run),
    }
    prime_bones_runtime(sim)
    prime_run_echoes_runtime(sim)
    run_nonce = random.SystemRandom().randrange(1, 1_000_000_000)
    run_rng = random.Random(run_nonce)
    start_chunk_cx, start_chunk_cy = _pick_playtest_start_chunk(sim, run_rng)
    start_focus_x, start_focus_y = sim.chunk_origin(start_chunk_cx, start_chunk_cy)
    start_focus_x += max(2, sim.chunk_size // 2)
    start_focus_y += max(2, sim.chunk_size // 2)

    sim.stream_world(start_focus_x, start_focus_y)
    sim.ensure_loaded_chunk_terrain()
    property_records = _register_chunk_properties(sim, sim.active_chunk)
    sim.chunk_property_records[(sim.active_chunk["cx"], sim.active_chunk["cy"])] = list(property_records)
    world_item_count = _seed_world_items(sim, property_records)
    maybe_seed_bones_for_chunk(sim, sim.active_chunk)
    maybe_seed_run_echo_for_chunk(sim, sim.active_chunk)
    sim.world_traits["local_economy"] = chunk_economy_profile(sim, sim.active_chunk)
    sim.world_traits["playtest_start"] = {
        "nonce": run_nonce,
        "chunk": {"cx": sim.active_chunk["cx"], "cy": sim.active_chunk["cy"]},
    }

    used_properties = set()
    guard_home = _pick_property(property_records, {"apartment", "house", "tenement"}, used=used_properties)
    if guard_home:
        used_properties.add(guard_home["id"])

    guard_work = _pick_property(property_records, {"checkpoint", "armory", "barracks", "tower", "office"}, used=used_properties)
    if guard_work:
        used_properties.add(guard_work["id"])

    scout_home = _pick_property(property_records, {"apartment", "house", "corner_store"}, used=used_properties)
    if scout_home:
        used_properties.add(scout_home["id"])

    sibling_a_home = _pick_property(property_records, {"apartment", "house", "tenement"}, used=used_properties)
    if sibling_a_home:
        used_properties.add(sibling_a_home["id"])

    sibling_b_home = _pick_property(property_records, {"apartment", "house", "tenement"}, used=used_properties)
    if sibling_b_home:
        used_properties.add(sibling_b_home["id"])

    job_rng = random.Random(f"{sim.seed}:npc_jobs")
    guard_career, guard_workplace = _pick_job(
        sim,
        job_rng,
        property_records,
        preferred_archetypes={"checkpoint", "armory", "barracks", "tower"},
    )
    scout_career, scout_workplace = _pick_job(
        sim,
        job_rng,
        property_records,
        preferred_archetypes={"warehouse", "factory", "office", "server_hub"},
    )
    sibling_a_career, sibling_a_workplace = _pick_job(
        sim,
        job_rng,
        property_records,
        preferred_archetypes={"apartment", "house", "corner_store", "restaurant"},
    )
    sibling_b_career, sibling_b_workplace = _pick_job(
        sim,
        job_rng,
        property_records,
        preferred_archetypes={"apartment", "house", "corner_store", "bar"},
    )

    chunk_origin_x, chunk_origin_y = sim.chunk_origin(sim.active_chunk["cx"], sim.active_chunk["cy"])
    chunk_min_x = chunk_origin_x + 1
    chunk_max_x = chunk_origin_x + sim.chunk_size - 2
    chunk_min_y = chunk_origin_y + 1
    chunk_max_y = chunk_origin_y + sim.chunk_size - 2

    def _clamp_chunk_tile(x, y, z=0):
        return (
            max(chunk_min_x, min(chunk_max_x, int(x))),
            max(chunk_min_y, min(chunk_max_y, int(y))),
            int(z),
        )

    chunk_mid = max(4, sim.chunk_size // 2)
    chunk_mid_x = chunk_origin_x + chunk_mid
    chunk_mid_y = chunk_origin_y + chunk_mid
    guard_pos = _coords_or(guard_work, fallback=_clamp_chunk_tile(chunk_mid_x, chunk_mid_y, 0))
    scout_pos = _coords_or(scout_home, fallback=_clamp_chunk_tile(guard_pos[0] + 3, guard_pos[1], 0))
    sibling_a_pos = _coords_or(sibling_a_home, fallback=_clamp_chunk_tile(guard_pos[0] - 5, guard_pos[1] + 2, 0))
    sibling_b_pos = _coords_or(sibling_b_home, fallback=_clamp_chunk_tile(sibling_a_pos[0] - 2, sibling_a_pos[1], 0))
    orange_cat_pos = _clamp_chunk_tile(sibling_b_pos[0] + 2, sibling_b_pos[1] + 1, 0)
    black_cat_pos = _clamp_chunk_tile(sibling_b_pos[0] + 3, sibling_b_pos[1] - 1, 0)
    calico_cat_pos = _clamp_chunk_tile(sibling_b_pos[0] + 4, sibling_b_pos[1] + 2, 0)
    player_pos = _pick_chunk_street_spawn(
        sim,
        sim.active_chunk,
        run_rng,
        reserved=(
            guard_pos,
            scout_pos,
            sibling_a_pos,
            sibling_b_pos,
            orange_cat_pos,
            black_cat_pos,
            calico_cat_pos,
        ),
    )

    cat_trait_rng = random.Random(f"{sim.seed}:cat_trait_profile")
    cat_coat_pool = (
        "orange_tabby",
        "black",
        "calico",
        "tabby",
        "gray",
        "white",
        "tuxedo",
        "purple",
    )
    animal_taxonomy_pool = (
        "feline",
        "canine",
        "avian",
        "rodent",
        "reptile",
        "insect",
        "arachnid",
    )
    active_animal_taxonomies = ("feline",)
    active_human_roles = ("guard", "scout", "civilian")
    human_role_pool = (
        "guard",
        "scout",
        "civilian",
        "courier",
        "medic",
        "merchant",
        "mechanic",
        "technician",
        "bartender",
        "fixer",
    )

    def _pick_false_claim(pool, true_value, rng):
        options = [value for value in pool if value != true_value]
        if not options:
            return true_value
        return rng.choice(options)

    def _rumor_text(topic, claim_value):
        claim = str(claim_value or "").replace("_", " ").strip() or "unknown"
        topic = str(topic or "").strip().lower()
        if topic == "cat_toxin_coat":
            return f"{claim} cats are poisonous."
        if topic == "contamination_taxonomy":
            return f"{claim} animals are contaminated this cycle."
        if topic == "illness_human_role":
            return f"{claim} groups are carrying an illness."
        if topic == "war_human_role":
            return f"{claim} groups are gearing for conflict."
        if topic == "blessing_taxonomy":
            return f"{claim} animals are said to be lucky this run."
        return f"{topic.replace('_', ' ')} -> {claim}."

    spawned_cat_coats = list(cat_trait_rng.sample(cat_coat_pool, 3))
    toxic_cat_coat = cat_trait_rng.choice(spawned_cat_coats)
    false_cat_toxin_coat = _pick_false_claim(cat_coat_pool, toxic_cat_coat, cat_trait_rng)
    contamination_taxonomy = cat_trait_rng.choice(active_animal_taxonomies)
    false_contamination_taxonomy = _pick_false_claim(animal_taxonomy_pool, contamination_taxonomy, cat_trait_rng)
    illness_role = cat_trait_rng.choice(active_human_roles)
    false_illness_role = _pick_false_claim(human_role_pool, illness_role, cat_trait_rng)
    war_candidates = [role for role in active_human_roles if role != illness_role]
    war_role = cat_trait_rng.choice(war_candidates or list(active_human_roles))
    false_war_role = _pick_false_claim(human_role_pool, war_role, cat_trait_rng)
    blessing_roll = cat_trait_rng.random()
    if blessing_roll < 0.7:
        blessing_taxonomy = cat_trait_rng.choice(active_animal_taxonomies)
    else:
        blessing_taxonomy = cat_trait_rng.choice(animal_taxonomy_pool)
    false_blessing_taxonomy = _pick_false_claim(animal_taxonomy_pool, blessing_taxonomy, cat_trait_rng)

    misguided_rumor_chance = round(cat_trait_rng.uniform(0.18, 0.42), 2)
    contact_chance = round(cat_trait_rng.uniform(0.22, 0.44), 2)
    contact_cooldown = cat_trait_rng.randint(12, 24)
    condition_scale = cat_trait_rng.uniform(0.85, 1.22)

    world_conditions = [
        {
            "id": "contamination_taxonomy",
            "topic": "contamination_taxonomy",
            "target_kind": "taxonomy",
            "target_value": contamination_taxonomy,
            "is_positive": False,
            "status": "ambient_contamination",
            "duration": cat_trait_rng.randint(14, 24),
            "chance": round(0.022 * condition_scale, 3),
            "cooldown": cat_trait_rng.randint(42, 88),
            "modifiers": {
                "safety_tick_delta": -0.13,
                "energy_tick_delta": -0.05,
                "move_speed_mult": -0.08,
            },
            "chip_damage": 1,
            "safety_hit": -2.6,
            "energy_hit": -1.2,
            "source_tag": "contamination_bloom",
        },
        {
            "id": "illness_human_role",
            "topic": "illness_human_role",
            "target_kind": "human_role",
            "target_value": illness_role,
            "is_positive": False,
            "status": "illness_wave",
            "duration": cat_trait_rng.randint(12, 22),
            "chance": round(0.018 * condition_scale, 3),
            "cooldown": cat_trait_rng.randint(38, 80),
            "modifiers": {
                "energy_tick_delta": -0.11,
                "move_speed_mult": -0.1,
            },
            "chip_damage": 1,
            "energy_hit": -2.5,
            "social_hit": -0.8,
            "source_tag": "illness_wave",
        },
        {
            "id": "war_human_role",
            "topic": "war_human_role",
            "target_kind": "human_role",
            "target_value": war_role,
            "is_positive": False,
            "status": "war_tension",
            "duration": cat_trait_rng.randint(11, 20),
            "chance": round(0.015 * condition_scale, 3),
            "cooldown": cat_trait_rng.randint(52, 108),
            "modifiers": {
                "safety_tick_delta": -0.16,
                "social_tick_delta": -0.04,
                "move_speed_mult": -0.04,
            },
            "chip_damage": 0,
            "safety_hit": -3.0,
            "social_hit": -1.4,
            "source_tag": "war_tension",
        },
        {
            "id": "blessing_taxonomy",
            "topic": "blessing_taxonomy",
            "target_kind": "taxonomy",
            "target_value": blessing_taxonomy,
            "is_positive": True,
            "status": "lucky_currents",
            "duration": cat_trait_rng.randint(10, 18),
            "chance": round(0.012 * condition_scale, 3),
            "cooldown": cat_trait_rng.randint(54, 115),
            "modifiers": {
                "safety_tick_delta": 0.09,
                "energy_tick_delta": 0.06,
                "move_speed_mult": 0.08,
            },
            "chip_damage": 0,
            "safety_hit": 1.6,
            "energy_hit": 1.1,
            "social_hit": 0.6,
            "source_tag": "lucky_currents",
        },
    ]
    rumor_claim_pools = {
        "cat_toxin_coat": list(cat_coat_pool),
        "contamination_taxonomy": list(animal_taxonomy_pool),
        "illness_human_role": list(human_role_pool),
        "war_human_role": list(human_role_pool),
        "blessing_taxonomy": list(animal_taxonomy_pool),
    }
    sim.world_rumors = [
        {
            "topic": "cat_toxin_coat",
            "true_value": toxic_cat_coat,
            "false_value": false_cat_toxin_coat,
            "tone": "danger",
            "seed_share_chance": 0.95,
            "misguided_chance": min(0.72, round(misguided_rumor_chance + 0.06, 2)),
        },
        {
            "topic": "contamination_taxonomy",
            "true_value": contamination_taxonomy,
            "false_value": false_contamination_taxonomy,
            "tone": "danger",
            "seed_share_chance": 0.74,
            "misguided_chance": misguided_rumor_chance,
        },
        {
            "topic": "illness_human_role",
            "true_value": illness_role,
            "false_value": false_illness_role,
            "tone": "danger",
            "seed_share_chance": 0.66,
            "misguided_chance": min(0.75, round(misguided_rumor_chance + 0.08, 2)),
        },
        {
            "topic": "war_human_role",
            "true_value": war_role,
            "false_value": false_war_role,
            "tone": "danger",
            "seed_share_chance": 0.6,
            "misguided_chance": min(0.75, round(misguided_rumor_chance + 0.09, 2)),
        },
        {
            "topic": "blessing_taxonomy",
            "true_value": blessing_taxonomy,
            "false_value": false_blessing_taxonomy,
            "tone": "boon",
            "seed_share_chance": 0.54,
            "misguided_chance": max(0.05, round(misguided_rumor_chance - 0.08, 2)),
        },
    ]
    sim.world_traits.update({
        "cat_coat_pool": list(cat_coat_pool),
        "toxic_cat_coat": toxic_cat_coat,
        "false_cat_toxin_coat": false_cat_toxin_coat,
        "active_human_roles": list(active_human_roles),
        "active_animal_taxonomies": list(active_animal_taxonomies),
        "misguided_rumor_chance": misguided_rumor_chance,
        "toxic_cat_contact_chance": contact_chance,
        "toxic_cat_contact_cooldown": contact_cooldown,
        "rumor_claim_pools": rumor_claim_pools,
        "world_conditions": world_conditions,
    })

    pressure_rng = random.Random(f"{sim.seed}:market_pressures")
    pressure_templates = {
        "war_tension": {
            "summary": "checkpoint searches slow freight",
            "tag_weights": {"restricted": 0.6, "medical": 0.4, "tool": 0.4, "food": -0.2},
            "stock_mult": 0.9,
            "price_mult": 1.12,
        },
        "illness_wave": {
            "summary": "clinics and pharmacies are under strain",
            "tag_weights": {"medical": 0.9, "food": 0.2},
            "stock_mult": 0.94,
            "price_mult": 1.08,
        },
        "ambient_contamination": {
            "summary": "clean food and meds are tighter than usual",
            "tag_weights": {"medical": 0.8, "food": -0.4, "drink": -0.2},
            "stock_mult": 0.92,
            "price_mult": 1.1,
        },
        "lucky_currents": {
            "summary": "a lucky run has loosened supply lines",
            "tag_weights": {"food": 0.4, "drink": 0.4, "token": 0.2},
            "stock_mult": 1.1,
            "price_mult": 0.94,
        },
    }
    active_pressure_count = 1 + (1 if pressure_rng.random() < 0.6 else 0)
    active_pressure_keys = pressure_rng.sample(
        list(pressure_templates.keys()),
        k=min(active_pressure_count, len(pressure_templates)),
    )
    sim.world_traits["market_pressures"] = [
        {
            "status": key,
            "summary": pressure_templates[key]["summary"],
            "tag_weights": dict(pressure_templates[key]["tag_weights"]),
            "stock_mult": pressure_templates[key]["stock_mult"],
            "price_mult": pressure_templates[key]["price_mult"],
            "intensity": round(pressure_rng.uniform(0.4, 0.9), 2),
        }
        for key in active_pressure_keys
    ]
    sim.world_traits["local_economy"] = chunk_economy_profile(sim, sim.active_chunk)
    seed_run_objective(sim, run_rng)

    _ensure_walkable(sim, player_pos[0], player_pos[1], player_pos[2], glyph=".")
    _ensure_walkable(sim, guard_pos[0], guard_pos[1], guard_pos[2], glyph=".")
    _ensure_walkable(sim, scout_pos[0], scout_pos[1], scout_pos[2], glyph=".")
    _ensure_walkable(sim, sibling_a_pos[0], sibling_a_pos[1], sibling_a_pos[2], glyph=".")
    _ensure_walkable(sim, sibling_b_pos[0], sibling_b_pos[1], sibling_b_pos[2], glyph=".")
    _ensure_walkable(sim, orange_cat_pos[0], orange_cat_pos[1], orange_cat_pos[2], glyph=".")
    _ensure_walkable(sim, black_cat_pos[0], black_cat_pos[1], black_cat_pos[2], glyph=".")
    _ensure_walkable(sim, calico_cat_pos[0], calico_cat_pos[1], calico_cat_pos[2], glyph=".")

    npc_speed_rng = random.Random(f"{sim.seed}:npc_speed_mods")
    guard_speed = round(npc_speed_rng.uniform(0.92, 1.18), 2)
    scout_speed = round(npc_speed_rng.uniform(1.05, 1.34), 2)
    sibling_a_speed = round(npc_speed_rng.uniform(0.78, 1.0), 2)
    sibling_b_speed = round(npc_speed_rng.uniform(0.82, 1.06), 2)
    cat_a_speed = round(npc_speed_rng.uniform(1.08, 1.32), 2)
    cat_b_speed = round(npc_speed_rng.uniform(1.0, 1.26), 2)
    cat_c_speed = round(npc_speed_rng.uniform(0.96, 1.2), 2)
    starter_name_seed = (sim.world_traits.get("playtest_start", {}) or {}).get("nonce", "static")
    starter_name_rng = random.Random(f"{sim.seed}:starter_human_names:{starter_name_seed}")
    guard_name = generate_human_personal_name(sim, starter_name_rng)
    scout_name = generate_human_personal_name(sim, starter_name_rng)
    sibling_a_name, sibling_b_name = generate_human_household_names(sim, starter_name_rng, count=2)
    core_stats_rng = random.Random(f"{sim.seed}:player_core_stats")
    player_core_stats = CoreStats(
        brawn=core_stats_rng.randint(3, 8),
        athleticism=core_stats_rng.randint(4, 9),
        dexterity=core_stats_rng.randint(4, 9),
        access=core_stats_rng.randint(4, 9),
        charm=core_stats_rng.randint(3, 8),
        common_sense=core_stats_rng.randint(4, 9),
    )
    player_insight = InsightStats(
        charm=player_core_stats.charm,
        common_sense=player_core_stats.common_sense,
    )
    player_skill_profile = seed_skill_profile(
        random.Random(f"{sim.seed}:player_skill_profile"),
        role="player",
        core=player_core_stats,
        insight=player_insight,
        jitter=0.18,
        birth_key=f"{sim.seed}:player_birth",
    )

    player = _spawn(
        sim,
        Position(*player_pos),
        Render("@"),
        PlayerControlled(),
        PlayerModeState(),
        Collider(blocks=True),
        NoiseProfile(move_radius=6),
        PlayerAssets(credits=140),
        VehicleState(),
        FinancialProfile(bank_balance=45),
        player_core_stats,
        player_insight,
        player_skill_profile,
        NPCNeeds(energy=80, safety=76, social=70),
        Inventory(capacity=14),
        StatusEffects(),
        Vitality(max_hp=120, recover_to_hp=42),
        ArmorLoadout(),
        WeaponLoadout(),
        CoverState(),
        ContactLedger(),
        PropertyKnowledge(),
        PropertyPortfolio(),
    )
    sim.player_eid = player

    guard = _spawn(
        sim,
        Position(*guard_pos),
        Render("G"),
        CreatureIdentity(
            taxonomy_class="hominid",
            species="homo sapiens",
            creature_type="human",
            common_name=human_descriptor("guard", guard_career),
            personal_name=guard_name,
        ),
        AI("guard"),
        MovementThrottle(
            default_cooldown=1,
            state_cooldowns={"patrolling": 2, "resting": 3},
            speed_multiplier=guard_speed,
        ),
        Collider(blocks=True),
        Occupation(career=guard_career, workplace=guard_workplace),
        NPCNeeds(energy=78, safety=82, social=58),
        NPCTraits(bravery=0.75, empathy=0.45, loyalty=0.72, discipline=0.88),
        NPCWill(),
        NPCMemory(),
        NPCSocial(),
        Inventory(capacity=8),
        StatusEffects(),
        Vitality(max_hp=max(72, human_max_hp_for_role(random.Random(f"{sim.seed}:starter_guard_hp"), "guard"))),
        ArmorLoadout(),
        WeaponLoadout(),
        WeaponUseProfile(
            aggression=0.82,
            aim_bias=0.7,
            min_range=1,
            max_range=11,
            cooldown_jitter=0,
            allow_explosives=False,
        ),
        CoverState(),
        ItemUseProfile(
            willingness=0.72,
            risk_tolerance=0.2,
            auto_use=True,
            cooldown_ticks=11,
            preferred_tags={"medical", "safety"},
            avoid_tags={"illegal"},
        ),
        NPCRoutine(
            home=_coords_or(guard_home, fallback=_clamp_chunk_tile(guard_pos[0] - 2, guard_pos[1] + 1, 0)),
            work=_coords_or(guard_work, fallback=_clamp_chunk_tile(*guard_pos)),
        ),
        PropertyKnowledge(),
        PropertyPortfolio(),
        JusticeProfile(enforce_all=True, justice=0.92, corruption=0.06, crime_sensitivity=0.97),
        seed_skill_profile(
            random.Random(f"{sim.seed}:starter_guard_skill_profile"),
            role="guard",
            career=guard_career,
            jitter=0.22,
        ),
    )

    scout = _spawn(
        sim,
        Position(*scout_pos),
        Render("S"),
        CreatureIdentity(
            taxonomy_class="hominid",
            species="homo sapiens",
            creature_type="human",
            common_name=human_descriptor("scout", scout_career),
            personal_name=scout_name,
        ),
        AI("scout"),
        MovementThrottle(
            default_cooldown=2,
            state_cooldowns={"protecting": 1, "patrolling": 2, "resting": 4},
            speed_multiplier=scout_speed,
        ),
        Collider(blocks=True),
        Occupation(career=scout_career, workplace=scout_workplace),
        NPCNeeds(energy=84, safety=70, social=64),
        NPCTraits(bravery=0.63, empathy=0.56, loyalty=0.66, discipline=0.67),
        NPCWill(),
        NPCMemory(),
        NPCSocial(),
        Inventory(capacity=8),
        StatusEffects(),
        Vitality(max_hp=max(64, human_max_hp_for_role(random.Random(f"{sim.seed}:starter_scout_hp"), "scout"))),
        ArmorLoadout(),
        WeaponLoadout(),
        WeaponUseProfile(
            aggression=0.65,
            aim_bias=0.64,
            min_range=1,
            max_range=10,
            cooldown_jitter=1,
            allow_explosives=False,
        ),
        CoverState(),
        ItemUseProfile(
            willingness=0.64,
            risk_tolerance=0.42,
            auto_use=True,
            cooldown_ticks=10,
            preferred_tags={"energy", "stimulant"},
            avoid_tags={"illegal"},
        ),
        NPCRoutine(
            home=_coords_or(scout_home, fallback=_clamp_chunk_tile(scout_pos[0] + 1, scout_pos[1] + 1, 0)),
            work=_coords_or(guard_work, fallback=_clamp_chunk_tile(guard_pos[0] + 1, guard_pos[1], 0)),
        ),
        PropertyKnowledge(),
        PropertyPortfolio(),
        JusticeProfile(enforce_all=False, justice=0.58, corruption=0.12, crime_sensitivity=0.71),
        seed_skill_profile(
            random.Random(f"{sim.seed}:starter_scout_skill_profile"),
            role="scout",
            career=scout_career,
            jitter=0.22,
        ),
    )

    sibling_a = _spawn(
        sim,
        Position(*sibling_a_pos),
        Render("C"),
        CreatureIdentity(
            taxonomy_class="hominid",
            species="homo sapiens",
            creature_type="human",
            common_name=human_descriptor("civilian", sibling_a_career),
            personal_name=sibling_a_name,
        ),
        AI("civilian"),
        MovementThrottle(
            default_cooldown=3,
            state_cooldowns={"seeking_safety": 2, "patrolling": 3},
            speed_multiplier=sibling_a_speed,
        ),
        Collider(blocks=True),
        Occupation(career=sibling_a_career, workplace=sibling_a_workplace),
        NPCNeeds(energy=72, safety=74, social=82),
        NPCTraits(bravery=0.28, empathy=0.82, loyalty=0.94, discipline=0.35),
        NPCWill(),
        NPCMemory(),
        NPCSocial(),
        Inventory(capacity=7),
        StatusEffects(),
        Vitality(max_hp=max(56, human_max_hp_for_role(random.Random(f"{sim.seed}:starter_sibling_a_hp"), "civilian"))),
        ArmorLoadout(),
        WeaponLoadout(),
        WeaponUseProfile(
            aggression=0.26,
            aim_bias=0.52,
            min_range=1,
            max_range=8,
            cooldown_jitter=2,
            allow_explosives=False,
        ),
        CoverState(),
        ItemUseProfile(
            willingness=0.52,
            risk_tolerance=0.16,
            auto_use=True,
            cooldown_ticks=13,
            preferred_tags={"social", "food"},
            avoid_tags={"illegal", "stimulant"},
        ),
        NPCRoutine(
            home=_coords_or(sibling_a_home, fallback=_clamp_chunk_tile(*sibling_a_pos)),
            work=_coords_or(guard_work, fallback=_clamp_chunk_tile(sibling_a_pos[0] + 2, sibling_a_pos[1] - 1, 0)),
        ),
        PropertyKnowledge(),
        PropertyPortfolio(),
        JusticeProfile(enforce_all=False, justice=0.25, corruption=0.05, crime_sensitivity=0.43),
        seed_skill_profile(
            random.Random(f"{sim.seed}:starter_sibling_a_skill_profile"),
            role="civilian",
            career=sibling_a_career,
            jitter=0.22,
        ),
    )

    sibling_b = _spawn(
        sim,
        Position(*sibling_b_pos),
        Render("D"),
        CreatureIdentity(
            taxonomy_class="hominid",
            species="homo sapiens",
            creature_type="human",
            common_name=human_descriptor("civilian", sibling_b_career),
            personal_name=sibling_b_name,
        ),
        AI("civilian"),
        MovementThrottle(
            default_cooldown=3,
            state_cooldowns={"seeking_safety": 2, "patrolling": 3},
            speed_multiplier=sibling_b_speed,
        ),
        Collider(blocks=True),
        Occupation(career=sibling_b_career, workplace=sibling_b_workplace),
        NPCNeeds(energy=76, safety=71, social=88),
        NPCTraits(bravery=0.34, empathy=0.8, loyalty=0.91, discipline=0.33),
        NPCWill(),
        NPCMemory(),
        NPCSocial(),
        Inventory(capacity=7),
        StatusEffects(),
        Vitality(max_hp=max(58, human_max_hp_for_role(random.Random(f"{sim.seed}:starter_sibling_b_hp"), "civilian"))),
        ArmorLoadout(),
        WeaponLoadout(),
        WeaponUseProfile(
            aggression=0.34,
            aim_bias=0.56,
            min_range=1,
            max_range=9,
            cooldown_jitter=2,
            allow_explosives=False,
        ),
        CoverState(),
        ItemUseProfile(
            willingness=0.56,
            risk_tolerance=0.3,
            auto_use=True,
            cooldown_ticks=12,
            preferred_tags={"social", "energy"},
            avoid_tags={"illegal"},
        ),
        NPCRoutine(
            home=_coords_or(sibling_b_home, fallback=_clamp_chunk_tile(*sibling_b_pos)),
            work=_coords_or(scout_home, fallback=_clamp_chunk_tile(sibling_b_pos[0] + 1, sibling_b_pos[1] - 1, 0)),
        ),
        PropertyKnowledge(),
        PropertyPortfolio(),
        JusticeProfile(enforce_all=False, justice=0.2, corruption=0.03, crime_sensitivity=0.31),
        seed_skill_profile(
            random.Random(f"{sim.seed}:starter_sibling_b_skill_profile"),
            role="civilian",
            career=sibling_b_career,
            jitter=0.22,
        ),
    )

    def _starter_workplace_prop(workplace):
        if not isinstance(workplace, dict):
            return None
        property_id = str(workplace.get("property_id", "") or "").strip()
        if not property_id:
            return None
        return sim.properties.get(property_id)

    starter_economy_profile = chunk_economy_profile(sim, sim.active_chunk)
    seed_npc_finance(
        sim,
        guard,
        random.Random(f"{sim.seed}:starter_guard_finance"),
        role="guard",
        career=guard_career,
        workplace_prop=_starter_workplace_prop(guard_workplace),
        economy_profile=starter_economy_profile,
    )
    seed_npc_finance(
        sim,
        scout,
        random.Random(f"{sim.seed}:starter_scout_finance"),
        role="worker",
        career=scout_career,
        workplace_prop=_starter_workplace_prop(scout_workplace),
        economy_profile=starter_economy_profile,
    )
    seed_npc_finance(
        sim,
        sibling_a,
        random.Random(f"{sim.seed}:starter_sibling_a_finance"),
        role="civilian",
        career=sibling_a_career,
        workplace_prop=_starter_workplace_prop(sibling_a_workplace),
        economy_profile=starter_economy_profile,
    )
    seed_npc_finance(
        sim,
        sibling_b,
        random.Random(f"{sim.seed}:starter_sibling_b_finance"),
        role="civilian",
        career=sibling_b_career,
        workplace_prop=_starter_workplace_prop(sibling_b_workplace),
        economy_profile=starter_economy_profile,
    )

    def _spawn_cat(name, coat_variant, pos, speed, target=None):
        cat = _spawn(
            sim,
            Position(*pos),
            Render("F"),
            CreatureIdentity(
                taxonomy_class="feline",
                species="felis catus",
                creature_type="animal",
                common_name=name,
                coat_variant=coat_variant,
            ),
            AI("wildlife"),
            MovementThrottle(
                default_cooldown=2,
                state_cooldowns={"patrolling": 2, "seeking_safety": 1, "resting": 3},
                speed_multiplier=speed,
            ),
            Collider(blocks=True),
            NPCNeeds(energy=86, safety=67, social=44),
            NPCTraits(bravery=0.18, empathy=0.55, loyalty=0.35, discipline=0.22),
            NPCWill(),
            NPCMemory(),
            NPCSocial(),
            Inventory(capacity=2),
            StatusEffects(),
            Vitality(max_hp=42),
            CoverState(),
            ItemUseProfile(
                willingness=0.28,
                risk_tolerance=0.08,
                auto_use=False,
                cooldown_ticks=20,
            ),
            NPCRoutine(
                home=pos,
                work=None,
            ),
            WildlifeBehavior(
                home_radius=5,
                flee_radius=6,
                flock_radius=3,
                flocking=False,
                activity_period="day",
                rest_bias=0.48,
            ),
            PropertyKnowledge(),
            PropertyPortfolio(),
        )
        sim.ecs.get(AI)[cat].state = "patrolling"
        patrol_target = target or (pos[0] - 1, pos[1], pos[2])
        sim.ecs.get(AI)[cat].target = patrol_target
        return cat

    cat_positions = (orange_cat_pos, black_cat_pos, calico_cat_pos)
    cat_speeds = (cat_a_speed, cat_b_speed, cat_c_speed)
    cat_entities = []
    for idx, coat_variant in enumerate(spawned_cat_coats):
        coat_name = str(coat_variant).replace("_", " ")
        pos = cat_positions[idx]
        speed = cat_speeds[idx]
        cat_entities.append(_spawn_cat(
            name=f"{coat_name} cat",
            coat_variant=coat_variant,
            pos=pos,
            speed=speed,
            target=(pos[0] - 1, pos[1], pos[2]),
        ))

    rumor_seed_rng = random.Random(f"{sim.seed}:seed_cat_toxin_rumors")
    memories = sim.ecs.get(NPCMemory)
    witness_eids = [guard, scout, sibling_a, sibling_b]
    for eid in witness_eids:
        memory = memories.get(eid)
        if not memory:
            continue
        for rumor in sim.world_rumors:
            if rumor_seed_rng.random() > float(rumor.get("seed_share_chance", 0.72)):
                continue
            topic = str(rumor.get("topic", "")).strip().lower()
            true_claim = str(rumor.get("true_value", "")).strip().lower()
            false_claim = str(rumor.get("false_value", "")).strip().lower()
            if not topic or not true_claim:
                continue

            try:
                local_misguided = float(rumor.get("misguided_chance", misguided_rumor_chance))
            except (TypeError, ValueError):
                local_misguided = misguided_rumor_chance
            local_misguided = max(0.0, min(0.95, local_misguided))
            heard_claim = true_claim
            if false_claim and rumor_seed_rng.random() < local_misguided:
                heard_claim = false_claim

            memory.remember(
                tick=sim.tick,
                kind="world_trait",
                strength=round(rumor_seed_rng.uniform(0.48, 0.9), 3),
                topic=topic,
                claimed_value=heard_claim,
                is_true=heard_claim == true_claim,
                via="street_rumor_seed",
                tone=rumor.get("tone", "rumor"),
            )

    _give_item(sim, player, "street_ration", quantity=2, owner_tag="player")
    _give_item(sim, player, "calm_patch", quantity=1, owner_tag="player")
    _give_item(sim, player, "city_pass_token", quantity=2, owner_tag="player")

    _give_item(sim, guard, "med_gel", quantity=1, owner_tag="npc")
    _give_item(sim, guard, "focus_inhaler", quantity=1, owner_tag="npc")

    _give_item(sim, scout, "caff_shot", quantity=1, owner_tag="npc")
    _give_item(sim, scout, "street_ration", quantity=1, owner_tag="npc")

    _give_item(sim, sibling_a, "spark_brew", quantity=1, owner_tag="npc")
    _give_item(sim, sibling_a, "street_ration", quantity=1, owner_tag="npc")

    _give_item(sim, sibling_b, "caff_shot", quantity=1, owner_tag="npc")
    _give_item(sim, sibling_b, "street_ration", quantity=1, owner_tag="npc")

    _give_weapon(sim, player, "rust_revolver", named_chance=0.45, owner_tag="player", inventory_backed=True)
    _give_weapon(sim, player, "alley_shotgun", named_chance=0.35, owner_tag="player", inventory_backed=True)

    _give_weapon(sim, guard, "compact_smg", named_chance=0.4)
    _give_weapon(sim, guard, "rust_revolver", named_chance=0.3)

    _give_weapon(sim, scout, "rust_revolver", named_chance=0.25)
    _give_weapon(sim, sibling_a, "rust_revolver", named_chance=0.18)
    _give_weapon(sim, sibling_b, "improvised_launcher", named_chance=0.22)

    _bond_pair(sim, guard, scout, relation="coworker", closeness=0.68, trust=0.72)
    _bond_pair(sim, sibling_a, sibling_b, relation="family", closeness=0.93, trust=0.9)
    _bond_pair(sim, guard, sibling_a, relation="neighbor", closeness=0.38, trust=0.52)
    _bond_pair(sim, scout, sibling_b, relation="neighbor", closeness=0.32, trust=0.45)

    for owned_ref, owner_eid in (
        (guard_home, guard),
        (guard_work, guard),
        (scout_home, scout),
        (sibling_a_home, sibling_a),
        (sibling_b_home, sibling_b),
    ):
        if owned_ref:
            _claim_property(sim, owned_ref["id"], owner_eid=owner_eid, owner_tag="npc")

    for actor_eid in (guard, scout, sibling_a, sibling_b):
        sync_actor_organization_affiliations(sim, actor_eid)

    reserved_properties = set(used_properties)
    for workplace in (guard_workplace, scout_workplace, sibling_a_workplace, sibling_b_workplace):
        if isinstance(workplace, dict):
            property_id = workplace.get("property_id")
            if property_id:
                reserved_properties.add(property_id)
    ambient_npc_count = len(
        spawn_chunk_npcs(
            sim,
            sim.active_chunk,
            property_records,
            reserved_property_ids=reserved_properties,
        )
    )
    ensure_chunk_flora(sim, sim.active_chunk, property_records=property_records)

    sim.stream_world(player_pos[0], player_pos[1])
    sim.ensure_loaded_chunk_terrain()
    seed_run_opportunities(sim, player_eid=player, rng=run_rng)
    if hasattr(sim, "reapply_door_states"):
        sim.reapply_door_states()
    _register_runtime_systems(sim, view, player)

    sim.log.add("Booted city sandbox. The district reacts to what you do.")
    sim.log.add(f"Character: {character_name}.")
    sim.log.add(f"World seed: {sim.seed}.")
    sim.log.add(
        f"Career pool ready: {len(sim.world.career_pool)} careers for "
        f"{len(sim.world.building_archetypes)} building archetypes."
    )
    sim.log.add(
        f"Properties loaded: {len(sim.properties)}. "
        f"Items seeded: {world_item_count}. "
        f"Ambient NPCs seeded: {ambient_npc_count}. "
        "NPCs track ownership, social links, justice, and consumables."
    )
    start_district = sim.active_chunk.get("district", {}) if isinstance(sim.active_chunk, dict) else {}
    start_name = (
        str(start_district.get("settlement_name") or "").strip()
        or str(start_district.get("region_name") or "").strip()
        or "unknown district"
    )
    start_district_type = str(start_district.get("district_type", "district")).replace("_", " ")
    sim.log.add(
        f"Start area: {start_name} ({start_district_type}, chunk "
        f"{sim.active_chunk['cx']},{sim.active_chunk['cy']})."
    )
    local_economy = sim.world_traits.get("local_economy", {}) if isinstance(sim.world_traits, dict) else {}
    local_note = str(local_economy.get("chunk_note", "")).strip()
    pressure_note = str(local_economy.get("pressure_note", "")).strip()
    if local_note:
        if pressure_note:
            sim.log.add(f"Local economy: {local_note}; {pressure_note}.")
        else:
            sim.log.add(f"Local economy: {local_note}.")
    objective_eval = evaluate_run_objective(sim, player)
    if objective_eval:
        objective_title = objective_eval.get("title", "Run Objective")
        objective_summary = objective_eval.get("summary", "")
        objective_status = objective_eval.get("summary_line", "")
        objective_next = objective_eval.get("next_step", "")
        if objective_summary:
            sim.log.add(f"Run objective: {objective_title}. {objective_summary}", channel="mission", priority="high")
        else:
            sim.log.add(f"Run objective: {objective_title}.", channel="mission", priority="high")
        if objective_status:
            sim.log.add(f"{objective_status}.", channel="mission", priority="high")
        if objective_next:
            sim.log.add(f"Next step: {objective_next}", channel="mission", priority="high")
    opportunity_eval = evaluate_opportunity_board(sim, player, limit=2)
    opportunity_summary = str(opportunity_eval.get("summary_line", "")).strip()
    if opportunity_summary:
        sim.log.add(opportunity_summary + ".", channel="opportunity", priority="high")
    for raw in list(opportunity_eval.get("lines", ()))[:2]:
        line = str(raw).strip()
        if line:
            sim.log.add(f"  {line}", channel="opportunity", priority="high")
    sim.log.add("Press O for the operations report and Y for known locations on foot or in-vehicle.")
    sim.log.add("The ops report explains why the current objective matters, what counts, and which opportunities fit it.")
    sim.log.add("Known locations lists places you have a real read on, with coords and confident facts.")
    sim.log.add("Press L to open the scrollable event log if messages roll past; inside it, T cycles filters and H sets the HUD log focus.")
    sim.log.add("Press E next to people to talk, at properties to use services, and at nearby vehicles to drive.")
    sim.log.add("HUD modes show active states like SNEAK, COVER, AIM, LOOK, and TURN.")
    sim.log.add(
        "NPC speed mods: "
        f"guard {guard_speed:.2f}x, scout {scout_speed:.2f}x, "
        f"sibling-a {sibling_a_speed:.2f}x, sibling-b {sibling_b_speed:.2f}x, "
        f"cat-a {cat_a_speed:.2f}x, cat-b {cat_b_speed:.2f}x, cat-c {cat_c_speed:.2f}x."
    )
    if sim.world_rumors:
        opening_rng = random.Random(f"{sim.seed}:opening_rumor_claim")
        opening_rumor = opening_rng.choice(sim.world_rumors)
        opening_topic = str(opening_rumor.get("topic", "world_trait")).strip().lower()
        opening_true = str(opening_rumor.get("true_value", "")).strip().lower()
        opening_false = str(opening_rumor.get("false_value", "")).strip().lower()
        try:
            opening_misguided = float(opening_rumor.get("misguided_chance", misguided_rumor_chance))
        except (TypeError, ValueError):
            opening_misguided = misguided_rumor_chance
        opening_misguided = max(0.0, min(0.95, opening_misguided))
        opening_claim = opening_true
        if opening_false and opening_rng.random() < opening_misguided:
            opening_claim = opening_false
        sim.log.add(f"Street rumor: {_rumor_text(opening_topic, opening_claim)}")
        rumor_topics = ", ".join(
            str(rumor.get("topic", "world_trait")).replace("_", " ")
            for rumor in sim.world_rumors
        )
        sim.log.add(f"World rumor topics active: {rumor_topics}.")
    sim.log.add(
        "Controls: move with arrows/WASD/HJKL or numpad 1-9, and press ? for the full help panel."
    )
    sim.log.add('City legend: + closed door, \' open door, " window, / breach opening, > higher stairs, < lower stairs, : stair landing, E elevator.')
    sim.log.add("Local terrain: = road, : trail, , brush, ^ rock, ~ water, _ shore flats.")
    sim.log.add("City legend: uppercase property markers are protected, lowercase are public, and S/s mark service access.")
    sim.log.add("Infrastructure markers now use typed street symbols (for example l lamp, p pole, h hydrant, u stop, j/t utility hardware).")
    sim.log.add("City legend: world features use symbols, items are bright symbols, and NPCs are colored letters.")
    sim.log.add("Remote sites: relay/lookout/survey sites can provide intel; camps and huts can offer shelter.")
    sim.log.add(
        "Overworld legend: in-vehicle macro-grid with district or terrain center icons, route bands for travel lines, and marker badges for your notes. Bright chunks are currently loaded, dim chunks are distant."
    )
    sim.log.add("Overworld POIs: stronger frontier/wilderness/coastal chunks can replace the center glyph with a site initial.")
    sim.log.add("Finance: stand on a bank, ATM, or insurer tile and press . to use the service surface. Bank balances do not accrue passive interest.")
    sim.log.add("Combat overlay is exposure-aware: nearby danger can trigger action-driven turn mode.")
    final_rules = sim.world_traits.get("rules", {}) if isinstance(sim.world_traits, dict) else {}
    sim.log.add(
        "Rule: final-op downed fail is "
        f"{'ON' if bool(final_rules.get('final_op_downed_fails_run', True)) else 'OFF'} "
        "(set BAKERRRR_FINAL_OP_DOWNED_FAILS_RUN=0/1)."
    )
    if bool(final_rules.get("final_op_downed_fails_run", True)):
        sim.log.add("Combat is mostly forgiving: being downed costs credits and resets HP, except during final operation where a down can fail the run.")
    else:
        sim.log.add("Combat is forgiving: being downed costs credits and resets HP instead of ending the run.")

    return _run_loop(sim, view, character_name)


def _show_custom_content_notices(view, content_result):
    for notice in list(getattr(content_result, "notices", ()) or ()):
        if isinstance(notice, dict):
            show_final_notice(view, wait=True, **notice)


def _run_new_game(view, character_name, gender_identity, *, debug_mode=False, custom_content_result=None):
    screen_w, screen_h = view.size()

    map_width = max(24, min(96, screen_w))
    map_height = max(14, min(40, screen_h - 10))

    if custom_content_result is not None:
        apply_custom_content(custom_content_result)

    sim = Simulation(
        seed=_resolve_run_seed(),
        map_width=map_width,
        map_height=map_height,
        max_floors=3,
        chunk_size=24,
    )
    if custom_content_result is not None:
        apply_custom_content(custom_content_result, sim=sim)
    sim.character_name = character_name
    sim.world_traits["character_name"] = character_name
    sim.world_traits["clock"] = {
        "start_hour": 9,
        "ticks_per_hour": 600,
    }
    final_op_downed_fails_run = _env_flag(
        "BAKERRRR_FINAL_OP_DOWNED_FAILS_RUN",
        True,
    )
    sim.world_traits["rules"] = {
        "final_op_downed_fails_run": bool(final_op_downed_fails_run),
    }
    prime_bones_runtime(sim)
    prime_run_echoes_runtime(sim)
    run_nonce = random.SystemRandom().randrange(1, 1_000_000_000)
    run_rng = random.Random(run_nonce)
    sim.world_traits["playtest_start"] = {"nonce": run_nonce}

    bootstrap = bootstrap_normal_run(
        sim,
        character_name,
        run_rng,
        gender_identity=gender_identity,
    )
    set_debug_mode(sim, debug_mode, source="startup" if debug_mode else "public")
    if hasattr(sim, "reapply_door_states"):
        sim.reapply_door_states()
    _register_runtime_systems(sim, view, bootstrap.player_eid)

    sim.log.add("You arrive with a bag, a pulse, and no curated landing.")
    sim.log.add(f"Character: {character_name}.")
    sim.log.add(f"World seed: {sim.seed}.")
    sim.log.add(
        f"Properties loaded: {len(sim.properties)}. "
        f"Items seeded: {bootstrap.world_item_count}. "
        f"Ambient NPCs seeded: {bootstrap.ambient_npc_count}."
    )
    sim.log.add(
        f"Start area: {bootstrap.start_name} ({bootstrap.start_district_type}, chunk "
        f"{bootstrap.start_chunk[0]},{bootstrap.start_chunk[1]})."
    )
    if bootstrap.local_note:
        if bootstrap.pressure_note:
            sim.log.add(f"Local economy: {bootstrap.local_note}; {bootstrap.pressure_note}.")
        else:
            sim.log.add(f"Local economy: {bootstrap.local_note}.")
    if bootstrap.street_kit_items:
        kit_text = ", ".join(
            f"{item_id.replace('_', ' ')} x{quantity}"
            for item_id, quantity in bootstrap.street_kit_items
        )
        sim.log.add(f"Street kit: {kit_text}.")
    if bootstrap.starter_vehicle_seeded:
        sim.log.add("Luck held: there is a starter vehicle in your orbit, and the keys are yours.")
    else:
        sim.log.add("No guaranteed ride this time. If you want wheels, earn them or find them.")
    sim.log.add("No one hands you the run shape for free. Press O when you want to force a sitrep, or learn it from the block first.")
    sim.log.add("Press O for the operations report and Y for known locations on foot or in-vehicle.")
    sim.log.add("Known locations lists places you have a real read on, with coords and confident facts.")
    sim.log.add("Press L to open the scrollable event log if messages roll past; inside it, T cycles filters and H sets the HUD log focus.")
    sim.log.add("Controls: Tab actions, / talk, . service, ' interact, ; lock, , pickup, x look, X map, and ? help.")
    sim.log.add("Use ' for physical fixtures and doors, / for people, and . for same-space service surfaces like ATMs or counters.")
    sim.log.add("HUD modes show active states like SNEAK, COVER, AIM, LOOK, and TURN.")
    if bootstrap.opening_rumor_text:
        sim.log.add(f"Street rumor: {bootstrap.opening_rumor_text}")
    if bootstrap.opening_rumor_topics_text:
        sim.log.add(f"World rumor topics active: {bootstrap.opening_rumor_topics_text}.")
    sim.log.add("Movement: arrows/WASD/HJKL or numpad 1-9.")
    sim.log.add('City legend: + closed door, \' open door, " window, / breach opening, > higher stairs, < lower stairs, : stair landing, E elevator.')
    sim.log.add("Local terrain: = road, : trail, , brush, ^ rock, ~ water, _ shore flats.")
    sim.log.add("City legend: uppercase property markers are protected, lowercase are public, and S/s mark service access.")
    sim.log.add("Infrastructure markers now use typed street symbols (for example l lamp, p pole, h hydrant, u stop, j/t utility hardware).")
    sim.log.add("City legend: world features use symbols, items are bright symbols, and NPCs are colored letters.")
    sim.log.add("Remote sites: relay/lookout/survey sites can provide intel; camps and huts can offer shelter.")
    sim.log.add(
        "Overworld legend: in-vehicle macro-grid with district or terrain center icons, route bands for travel lines, and marker badges for your notes. Bright chunks are currently loaded, dim chunks are distant."
    )
    sim.log.add("Overworld POIs: stronger frontier/wilderness/coastal chunks can replace the center glyph with a site initial.")
    sim.log.add("Finance: stand on a bank, ATM, or insurer tile and press . to use the service surface. Bank balances do not accrue passive interest.")
    sim.log.add("Combat overlay is exposure-aware: nearby danger can trigger action-driven turn mode.")
    final_rules = sim.world_traits.get("rules", {}) if isinstance(sim.world_traits, dict) else {}
    sim.log.add(
        "Rule: final-op downed fail is "
        f"{'ON' if bool(final_rules.get('final_op_downed_fails_run', True)) else 'OFF'} "
        "(set BAKERRRR_FINAL_OP_DOWNED_FAILS_RUN=0/1)."
    )
    if bool(final_rules.get("final_op_downed_fails_run", True)):
        sim.log.add("Combat is mostly forgiving: being downed costs credits and resets HP, except during final operation where a down can fail the run.")
    else:
        sim.log.add("Combat is forgiving: being downed costs credits and resets HP instead of ending the run.")

    return _run_loop(sim, view, character_name)


def _run_tutorial_game(view, character_name, gender_identity, *, debug_mode=False):
    screen_w, screen_h = view.size()

    map_width = max(24, min(96, screen_w))
    map_height = max(14, min(40, screen_h - 10))

    sim = Simulation(
        seed=_resolve_run_seed(default=424242),
        map_width=map_width,
        map_height=map_height,
        max_floors=3,
        chunk_size=24,
    )
    sim.character_name = character_name
    sim.world_traits["character_name"] = character_name
    sim.world_traits["clock"] = {
        "start_hour": 9,
        "ticks_per_hour": 600,
    }
    sim.world_traits["rules"] = {
        "tutorial_no_persistence": True,
        "final_op_downed_fails_run": False,
    }
    run_nonce = random.SystemRandom().randrange(1, 1_000_000_000)
    run_rng = random.Random(f"tutorial:{run_nonce}")
    sim.world_traits["playtest_start"] = {"nonce": run_nonce, "tutorial": True}

    bootstrap = bootstrap_tutorial_run(
        sim,
        character_name,
        run_rng,
        gender_identity=gender_identity,
    )
    set_debug_mode(sim, debug_mode, source="startup" if debug_mode else "public")
    if hasattr(sim, "reapply_door_states"):
        sim.reapply_door_states()
    _register_runtime_systems(sim, view, bootstrap.player_eid)

    normal = bootstrap.normal_bootstrap
    sim.log.add("You arrive in a disposable tutorial block. Nothing here will be saved.")
    sim.log.add(f"Character: {character_name}.")
    sim.log.add(f"World seed: {sim.seed}.")
    sim.log.add(
        f"Training fixtures loaded: service {bootstrap.service_property_id}, "
        f"shop {bootstrap.shop_property_id}, retrieval {bootstrap.final_property_id}."
    )
    sim.log.add(
        f"Start area: {normal.start_name} ({normal.start_district_type}, chunk "
        f"{normal.start_chunk[0]},{normal.start_chunk[1]})."
    )
    if normal.street_kit_items:
        kit_text = ", ".join(
            f"{item_id.replace('_', ' ')} x{quantity}"
            for item_id, quantity in normal.street_kit_items
        )
        sim.log.add(f"Street kit: {kit_text}.")
    sim.log.add("Tutorial route: follow the HUD line, ask Mara what now, and recover the Training Retrieval Case.")
    sim.log.add("Controls start simple: move, Tab actions, x look, ' interact, / talk, . service, , pickup, i inventory, O report, Y notebooks, X map, L log, + sheet, ? help.")
    sim.log.add(current_tutorial_hint(sim))

    return _run_loop(sim, view, character_name)


def _run_loaded_game(view, character_name, *, debug_mode=False):
    sim = load_character_run(character_name, delete_on_load=False)
    content_result = validate_custom_content_for_resume(getattr(sim, "custom_content_manifest", None))
    _show_custom_content_notices(view, content_result)
    if bool(getattr(content_result, "blocking", False)):
        return {
            "show_post_curses": False,
            "outcome": "blocked",
            "reason": "custom_content_mismatch",
            "objective_title": character_name,
            "tick": int(getattr(sim, "tick", 0) or 0),
            "summary_lines": [
                "Saved run could not resume because required custom content did not match.",
                "The save file was not deleted.",
            ],
            "saved": True,
            "final_notice_printed": True,
        }
    apply_custom_content(content_result, sim=sim)
    sim.character_name = normalize_character_name(character_name) or getattr(sim, "character_name", None)
    prime_bones_runtime(sim)
    prime_run_echoes_runtime(sim)
    if not isinstance(getattr(sim, "world_traits", None), dict):
        sim.world_traits = {}
    if sim.character_name:
        sim.world_traits["character_name"] = sim.character_name

    if isinstance(getattr(sim, "look_ui", None), dict):
        sim.look_ui["active"] = False
    if isinstance(getattr(sim, "trade_ui", None), dict):
        sim.trade_ui["open"] = False
    if isinstance(getattr(sim, "report_ui", None), dict):
        sim.report_ui["open"] = False
        sim.report_ui["scroll"] = 0
    if isinstance(getattr(sim, "log_ui", None), dict):
        sim.log_ui["open"] = False
        sim.log_ui["scroll"] = 0
    sim.turn_advance_requested = False

    player = getattr(sim, "player_eid", None)
    if player is None:
        raise ValueError("save file is missing player entity")
    if not _ensure_loaded_player_identity(view, sim, sim.character_name or character_name):
        return None
    set_debug_mode(sim, debug_mode, source="startup" if debug_mode else "public")

    player_pos = sim.ecs.get(Position).get(player)
    if player_pos:
        sim.stream_world(player_pos.x, player_pos.y)
        sim.ensure_loaded_chunk_terrain()

    _register_runtime_systems(sim, view, player)
    delete_character_save(character_name)
    sim.log.add(f"Resumed character: {sim.character_name or character_name}.")
    sim.log.add("Save file consumed after resume setup. Quit again to write a fresh save.")
    return _run_loop(sim, view, sim.character_name or character_name)


def _run_character_session(view, character_name, gender_identity=None, *, tutorial=False, debug_mode=False):
    """Launch either a resumed run or a fresh run for a given view backend."""
    if tutorial:
        resolved_identity = (
            normalize_gender_identity(gender_identity, default="nonbinary")
            if str(gender_identity or "").strip()
            else ""
        )
        if not resolved_identity:
            resolved_identity = _prompt_player_gender_identity_view(
                view,
                character_name=character_name,
                resume=False,
            )
            if not resolved_identity:
                return None
        return _run_tutorial_game(view, character_name, resolved_identity, debug_mode=debug_mode)
    if character_save_exists(character_name):
        return _run_loaded_game(view, character_name, debug_mode=debug_mode)
    custom_content_result = load_custom_content_for_new_run()
    _show_custom_content_notices(view, custom_content_result)
    resolved_identity = (
        normalize_gender_identity(gender_identity, default="nonbinary")
        if str(gender_identity or "").strip()
        else ""
    )
    if not resolved_identity:
        resolved_identity = _prompt_player_gender_identity_view(
            view,
            character_name=character_name,
            resume=False,
        )
        if not resolved_identity:
            return None
    return _run_new_game(
        view,
        character_name,
        resolved_identity,
        debug_mode=debug_mode,
        custom_content_result=custom_content_result,
    )


def _run_curses(stdscr, tutorial=False, *, debug_mode=False):
    # Prompt before CursesView sets non-blocking input mode.
    character_name = _prompt_character_name(stdscr)
    selected_identity = None
    if tutorial or not character_save_exists(character_name):
        selected_identity = _prompt_player_gender_identity(
            stdscr,
            character_name=character_name,
            resume=False,
        )
        if not selected_identity:
            return None
    view = CursesView(stdscr)
    run_end = _run_character_session(view, character_name, selected_identity, tutorial=tutorial, debug_mode=debug_mode)
    show_run_end_notice(view, run_end, wait=True, print_notice=True)
    return run_end


def _run_pygame(tutorial=False, *, debug_mode=False):
    # Pygame uses a fixed procedural default cell size unless overridden by env.
    # Override with BAKERRRR_TILE_SIZE_PX / _GRID_W / _GRID_H if you want a different view.
    grid_w = _env_int("BAKERRRR_TILE_GRID_W", 64, minimum=24)
    grid_h = _env_int("BAKERRRR_TILE_GRID_H", 40, minimum=14)
    tile_px = _resolve_pygame_tile_px()
    view = PygameView(
        width_cells=grid_w,
        height_cells=grid_h,
        cell_px=tile_px,
        title="bakerrrr",
    )
    try:
        character_name = view.prompt_text_input(
            "Character name:",
            detail=(
                "Tutorial runs are disposable and ignore existing saves."
                if tutorial
                else "Existing save with this name resumes once, then is deleted on load."
            ),
            max_length=40,
            title="bakerrrr - character",
            banner="BAKERRRR",
            subtitle="Street-level run setup",
            invalid_message="Please enter a valid character name.",
            normalizer=normalize_character_name,
            status_lines_callback=lambda raw: (
                [{
                    "text": f"Disposable tutorial will start for {normalize_character_name(raw)}.",
                    "color": "objective",
                }]
                if tutorial and normalize_character_name(raw)
                else
                [{
                    "text": f"Resume available for {normalize_character_name(raw)}.",
                    "color": "objective",
                }]
                if normalize_character_name(raw) and character_save_exists(normalize_character_name(raw))
                else ([{
                    "text": f"Fresh run will start for {normalize_character_name(raw)}.",
                    "color": "scout",
                }] if normalize_character_name(raw) else [{
                    "text": "Enter a name to start or resume a run.",
                    "color": "default",
                }])
            ),
        )
        if not character_name:
            return None
        selected_identity = None
        if tutorial or not character_save_exists(character_name):
            selected_identity = _prompt_player_gender_identity_view(
                view,
                character_name=character_name,
                resume=False,
            )
            if not selected_identity:
                return None
        view.pygame.display.set_caption(f"bakerrrr - {character_name}")
        run_end = _run_character_session(view, character_name, selected_identity, tutorial=tutorial, debug_mode=debug_mode)
        show_run_end_notice(view, run_end, wait=True, print_notice=True)
        return run_end
    finally:
        view.close()


def _record_tutorial_run_if_needed(run_end):
    if not isinstance(run_end, dict) or not bool(run_end.get("tutorial")):
        return None
    outcome = str(run_end.get("outcome", "") or "").strip().lower()
    try:
        return mark_tutorial_run_seen(
            completed=outcome == "success",
            run_end=run_end,
        )
    except OSError:
        return None


def _print_post_run_summary(run_end):
    if not isinstance(run_end, dict) or not bool(run_end.get("show_post_curses")):
        return
    if bool(run_end.get("final_notice_printed")):
        return
    outcome = str(run_end.get("outcome", "unknown")).strip().upper()
    reason = str(run_end.get("reason", "")).strip().replace("_", " ")
    objective_title = str(run_end.get("objective_title", "Run")).strip() or "Run"
    tick = int(run_end.get("tick", 0))
    header = f"=== RUN {outcome} @ tick {tick}: {objective_title} ==="
    if reason:
        header += f" [{reason}]"
    print(header)
    for raw in run_end.get("summary_lines", ()):
        line = str(raw).strip()
        if line:
            print(f"- {line}")


def _show_crash_notice_modal(backend, title, lines):
    backend = str(backend or "").strip().lower()
    try:
        if backend == "pygame":
            view = PygameView(
                width_cells=72,
                height_cells=20,
                cell_px=_resolve_pygame_tile_px(),
                title="bakerrrr - notice",
            )
            try:
                show_final_notice(
                    view,
                    title=title,
                    lines=lines,
                    severity="error",
                    stream="stderr",
                    print_notice=False,
                    wait=True,
                )
            finally:
                view.close()
            return True
        if backend == "curses":
            return curses.wrapper(
                lambda stdscr: show_final_notice(
                    CursesView(stdscr),
                    title=title,
                    lines=lines,
                    severity="error",
                    stream="stderr",
                    print_notice=False,
                    wait=True,
                )
            )
    except Exception:
        return False
    return False


def _run_entrypoint(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    _install_usr1_stack_dump_handler()
    install_sigusr2_debug_unlock_handler()

    if _argv_has_flag(args, "--version"):
        print(game_build_label())
        return 0
    if _argv_has_flag(args, "--doctor"):
        ok, lines = _doctor_report(args)
        for line in lines:
            print(line)
        return 0 if ok else 1

    backend = _resolve_ui_backend(args)
    tutorial = _resolve_tutorial_flag(args)
    debug_mode = _resolve_debug_flag(args)
    if backend == "pygame":
        run_end = _run_pygame(tutorial=tutorial, debug_mode=debug_mode)
    else:
        run_end = curses.wrapper(lambda stdscr: _run_curses(stdscr, tutorial=tutorial, debug_mode=debug_mode))
    _record_tutorial_run_if_needed(run_end)
    _print_post_run_summary(run_end)
    return 0


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    backend = _resolve_ui_backend(args)
    tutorial = None
    try:
        tutorial = _resolve_tutorial_flag(args)
    except Exception:
        tutorial = None
    try:
        return _run_entrypoint(args)
    except Exception as exc:  # noqa: BLE001 - top-level report should catch unexpected game crashes
        try:
            crash_path = write_crash_report(
                exc,
                argv=args,
                backend=backend,
                tutorial=tutorial,
            )
            crash_lines = (f"Crash report written: {crash_path}",)
            show_final_notice(
                None,
                title="bakerrrr crashed",
                lines=crash_lines,
                severity="error",
                stream="stderr",
            )
            _show_crash_notice_modal(backend, "bakerrrr crashed", crash_lines)
        except Exception:
            crash_lines = ("A crash report could not be written.",)
            show_final_notice(
                None,
                title="bakerrrr crashed",
                lines=crash_lines,
                severity="error",
                stream="stderr",
            )
            _show_crash_notice_modal(backend, "bakerrrr crashed", crash_lines)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
