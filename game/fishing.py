"""Run-specific fish, count-only waters, and shared player/NPC fishing sessions.

Water components are local fishing stretches: a river crossing a chunk boundary
has one stock per stretch. Indexing happens at terrain realization, never per
cast. No individual fish is simulated between casts.
"""
from __future__ import annotations

import random
from collections import deque

from engine.events import Event
from engine.systems import System
from game.components import AI, Inventory, NPCNeeds, NPCTraits, NPCWill, Occupation, Position, SkillProfile, Vitality
from game.items import ITEM_CATALOG
from game.system_support.player_feedback import _log_player_feedback

SPECIES_COUNT = 36
MAX_NPC_FISHERS = 12
STOCK_RECOVERY_TICKS = 2400
DIRS = ((0, -1), (1, 0), (0, 1), (-1, 0), (-1, -1), (1, -1), (1, 1), (-1, 1))
PREP_ARCHETYPES = {"restaurant", "butcher", "butcher_shop", "field_camp", "herbalist_camp", "camp_site", "campsite"}
FISH_ITEMS = {"fresh_fish", "prepared_fish"}
EFFECTS = ("nourishment",) * 15 + ("hp_up",) * 4 + ("hp_down",) * 2 + ("skill_up",) * 5 + ("skill_down",) * 2 + ("food_up", "water_up") * 3 + ("food_down", "water_down")
STEMS = ("amber", "silver", "copper", "glass", "pearl", "velvet", "ribbon", "moon", "sun", "dusk", "mist", "rain", "reed", "willow", "moss", "mud", "sand", "stone", "slate", "coral", "shell", "tide", "foam", "brine", "ripple", "lantern", "ink", "opal", "blue", "red", "gold", "ivory", "silt", "drift", "rill", "brook")
PARTS = ("fin", "tail", "gill", "scale", "belly", "back", "nose", "barbel", "stripe", "spot", "jaw", "crest")
NOUNS = ("darter", "loach", "goby", "bream", "perch", "eel", "skipper", "smelt", "shiner", "runner", "chub", "roach", "char", "minnow", "gudgeon", "mullet", "sucker", "pike")


def ensure_fishing(sim):
    state = getattr(sim, "fishing", None)
    if isinstance(state, dict):
        return state
    rng = random.Random(f"{sim.seed}:fish-roster:v1")
    names = set()
    species = {}
    effect_pool = list(EFFECTS)
    rng.shuffle(effect_pool)
    for i in range(SPECIES_COUNT):
        name = ""
        while not name or name in names:
            name = f"{rng.choice(STEMS)}{rng.choice(PARTS)} {rng.choice(NOUNS)}"
        names.add(name)
        effect = effect_pool[i]
        sid = f"fish:{i}"
        rarity = rng.choices((1, 2, 3, 4), weights=(50, 30, 15, 5))[0]
        species[sid] = dict(id=sid, name=name, rarity=rarity,
                            edible=rng.random() > .08, toxic=rng.random() < .2,
                            effect=effect, magnitude=rng.choice((1, 2, 3)),
                            skill=rng.choice(("athletics", "perception", "conversation", "streetwise", "tactics", "intrusion", "mechanics")),
                            nourishment=100 if effect != "nourishment" else rng.randint(24, 65),
                            value=6 + rarity * rarity * 4)
    state = dict(version=1, species=species, waters={}, chunks={}, sessions={},
                 knowledge={}, serial=0, npc_cooldowns={})
    sim.fishing = state
    sim.fishing_ui = {"open": False}
    return state


def index_fishing_chunk(sim, cx, cy):
    state = ensure_fishing(sim)
    key = (int(cx), int(cy))
    size = int(sim.chunk_size)
    ox, oy = sim.chunk_origin(*key)
    cells = {(x, y) for y in range(oy, oy + size) for x in range(ox, ox + size)
             if (tile := sim.tilemap.tile_at(x, y, 0)) is not None and tile.glyph == "~"}
    lookup, banks = {}, []
    while cells:
        anchor = min(cells)
        component, pending = set(), [anchor]
        cells.remove(anchor)
        while pending:
            cell = pending.pop()
            component.add(cell)
            for dx, dy in DIRS[:4]:
                other = (cell[0] + dx, cell[1] + dy)
                if other in cells:
                    cells.remove(other)
                    pending.append(other)
        wid = f"{cx}:{cy}:{anchor[0]}:{anchor[1]}"
        if wid not in state["waters"]:
            rng = random.Random(f"{sim.seed}:fishing-water:{wid}")
            ids = rng.sample(list(state["species"]), rng.randint(1, min(5, max(1, len(component) // 3))))
            capacity = max(len(ids), len(component) * 2)
            weights = [1 / state["species"][sid]["rarity"] for sid in ids]
            counts = {sid: 1 for sid in ids}
            for sid in rng.choices(ids, weights=weights, k=capacity - len(ids)):
                counts[sid] += 1
            state["waters"][wid] = dict(id=wid, size=len(component), capacity=dict(counts),
                                         stock=dict(counts), recovered_tick=int(sim.tick))
        for x, y in sorted(component):
            lookup[(x, y)] = wid
            for dx, dy in DIRS:
                bank = (x + dx, y + dy)
                tile = sim.tilemap.tile_at(*bank, 0)
                if tile and tile.walkable and tile.glyph != "~":
                    banks.append((bank[0], bank[1], x, y))
    state["chunks"][key] = {"cells": lookup, "banks": list(dict.fromkeys(banks))}


def water_at(sim, x, y, z=0):
    if z != 0:
        return None
    tile = sim.tilemap.tile_at(x, y, z)
    if tile is None or tile.glyph != "~":
        return None
    state = ensure_fishing(sim)
    wid = state["chunks"].get(sim.chunk_coords(x, y), {}).get("cells", {}).get((x, y))
    return state["waters"].get(wid)


def recover_stock(sim, water):
    elapsed = max(0, int(sim.tick) - water["recovered_tick"])
    periods = elapsed // STOCK_RECOVERY_TICKS
    if periods:
        for sid, cap in water["capacity"].items():
            water["stock"][sid] = min(cap, water["stock"][sid] + periods)
        water["recovered_tick"] += periods * STOCK_RECOVERY_TICKS


def fish_metadata(sim, sid, *, water_id=None):
    fish = ensure_fishing(sim)["species"][sid]
    return {"fish_species": sid, "fish_run_seed": sim.seed, "fish_water": water_id,
            "caught_tick": int(sim.tick), "display_name": fish["name"].title(),
            "fish_value": fish["value"]}


def species_for_entry(sim, entry):
    metadata = entry.get("metadata") or {}
    if metadata.get("fish_run_seed") != sim.seed:
        return None
    return ensure_fishing(sim)["species"].get(metadata.get("fish_species"))


def learn_fish(sim, eid, sid, source):
    knowledge = ensure_fishing(sim)["knowledge"].setdefault(eid, {})
    old = knowledge.get(sid)
    if old is None or source == "eaten":
        knowledge[sid] = {"source": source, "tick": int(sim.tick)}


def fish_fact(fish):
    name = fish["name"].title()
    if fish["toxic"]:
        return f"{name} is poisonous. Cooking won't make it safe."
    if not fish["edible"]:
        return f"{name} isn't good eating; save it for bait."
    effects = {
        "nourishment": "makes a decent meal",
        "hp_up": "can leave you hardier", "hp_down": "can leave you frailer",
        "skill_up": f"helps you hold on to your {fish['skill']}",
        "skill_down": f"can take the edge off your {fish['skill']}",
        "food_up": "helps you go longer between meals", "food_down": "leaves you needing food more often",
        "water_up": "helps you go longer without a drink", "water_down": "leaves you needing water more often",
    }
    return f"{name}, prepared and eaten whole, {effects[fish['effect']]}."


def fishing_rumor(sim, speaker_eid, listener_eid=None):
    state = ensure_fishing(sim)
    known = state["knowledge"].get(speaker_eid, {})
    if not known:
        return ""
    ids = sorted(known)
    sid = ids[(int(sim.tick) // 120 + int(speaker_eid)) % len(ids)]
    if listener_eid is not None:
        learn_fish(sim, listener_eid, sid, "rumor")
    prefix = "I've eaten it myself. " if known[sid]["source"] == "eaten" else "Word along the bank is: "
    return prefix + fish_fact(state["species"][sid])


def bait_shop_rumor(sim, eid, prop):
    state = ensure_fishing(sim)
    rng = random.Random(f"{sim.seed}:fish-advice:{prop.get('id')}")
    ids = rng.sample(list(state["species"]), 6)
    sid = ids[(int(sim.tick) // 120) % len(ids)]
    learn_fish(sim, eid, sid, "rumor")
    return "Here's what the regulars tell me. " + fish_fact(state["species"][sid])


def seed_fisher(sim, eid, role, *, workplace_prop=None, home_prop=None):
    """Personal fishing equipment and remembered food lore at actor genesis."""
    inv = sim.ecs.get(Inventory).get(eid)
    ai = sim.ecs.get(AI).get(eid)
    if inv is None or ai is None or role not in {"worker", "civilian", "drunk"}:
        return
    archetype = str((workplace_prop or {}).get("archetype", ""))
    rng = random.Random(f"{sim.seed}:angler:{eid}")
    professional = archetype in {"net_house", "dock_shack", "bait_shop"} and rng.random() < .6
    if not professional and rng.random() >= .12:
        return
    inv.capacity += 3  # Rod, bait, and space for the catch in a fisher's kit.
    for item, qty in (("fishing_pole", 1), ("fishing_bait", 4)):
        inv.add_item(item, quantity=qty, stack_max=ITEM_CATALOG[item]["stack_max"],
                     instance_factory=sim.new_item_instance_id, owner_eid=eid, owner_tag="npc")
    ai.fishing_livelihood = professional
    for sid in rng.sample(list(ensure_fishing(sim)["species"]), 5 if professional else 2):
        learn_fish(sim, eid, sid, "bank_lore")


def identify_fish(sim, eid, prop):
    inv = sim.ecs.get(Inventory).get(eid)
    if inv is None:
        return "Bring a fish along and I'll have a look."
    rng = random.Random(f"{sim.seed}:fishmonger:{prop.get('id')}")
    familiar = set(rng.sample(list(ensure_fishing(sim)["species"]), 24))
    for entry in inv.items:
        if entry.get("item_id") not in FISH_ITEMS:
            continue
        fish = species_for_entry(sim, entry)
        if fish and fish["id"] in familiar:
            learn_fish(sim, eid, fish["id"], "bait_shop")
            return fish_fact(fish)
    return "I don't know these well enough to tell you they're safe."


def prepare_fish(sim, eid, prop):
    """Prepare one whole specimen in place; identity and inventory slot survive."""
    inv = sim.ecs.get(Inventory).get(eid)
    entry = next((e for e in inv.items if e.get("item_id") == "fresh_fish"), None) if inv else None
    if entry is None:
        return "Bring a fresh fish and we can prepare it here."
    fish = species_for_entry(sim, entry)
    if fish is None:
        return "We can't make out what kind of fish this is."
    entry["item_id"] = "prepared_fish"
    entry["metadata"]["display_name"] = f"Prepared {fish['name']}"
    entry["metadata"]["fish_value"] = fish["value"] + 5
    entry["metadata"]["prepared_at"] = prop.get("id")
    sim.emit(Event("fish_prepared", eid=eid, species_id=fish["id"], property_id=prop.get("id")))
    return f"The {fish['name']} is cleaned and cooked, ready to eat."


def eat_fish(sim, eid, entry):
    inv = sim.ecs.get(Inventory).get(eid)
    fish = species_for_entry(sim, entry)
    needs = sim.ecs.get(NPCNeeds).get(eid)
    if not fish or inv is None or needs is None:
        return False
    if entry["item_id"] != "prepared_fish":
        feedback(sim, eid, "Prepare your catch at a campfire, restaurant, or butcher first.")
        return False
    before = float(needs.hunger)
    nourishment = fish["nourishment"] if fish["edible"] else 8
    whole = before < 75 or before + nourishment <= 100
    if not inv.remove_item(instance_id=entry["instance_id"], quantity=1):
        return False
    learn_fish(sim, eid, fish["id"], "eaten")
    needs.hunger = min(100.0, before + nourishment)
    vitality = sim.ecs.get(Vitality).get(eid)
    if fish["toxic"] and vitality is not None:
        from game.system_support.actor_runtime import _apply_downed_actor_state
        damage = 4 + fish["magnitude"] * 2
        vitality.hp = max(0, vitality.hp - damage)
        sim.emit(Event("entity_damaged", eid=eid, target_eid=eid, damage=damage, source="toxic_fish"))
        if vitality.hp <= 0:
            _apply_downed_actor_state(sim, eid)
    applied = "nourishment"
    if whole and fish["edible"]:
        applied = fish["effect"]
        amount = fish["magnitude"]
        if applied in {"hp_up", "hp_down"} and vitality is not None:
            delta = amount if applied == "hp_up" else -amount
            vitality.max_hp = max(1, vitality.max_hp + delta)
            vitality.hp = min(vitality.hp, vitality.max_hp)
            vitality.recover_to_hp = min(vitality.recover_to_hp, vitality.max_hp)
        elif applied in {"skill_up", "skill_down"}:
            profile = sim.ecs.get(SkillProfile).get(eid)
            if profile is not None:
                skill = fish["skill"]
                delta = amount * .1 * (1 if applied == "skill_up" else -1)
                profile.floors[skill] = max(1.0, min(10.0, profile.floor(skill) + delta))
                profile.ratings[skill] = max(profile.get(skill), profile.floors[skill])
        elif applied in {"food_up", "food_down", "water_up", "water_down"}:
            attr = "fish_food_resilience" if applied.startswith("food") else "fish_water_resilience"
            setattr(needs, attr, int(getattr(needs, attr, 0)) + amount * (1 if applied.endswith("up") else -1))
    text = f"You finish the {fish['name']}." if whole else f"You're full. You leave part of the {fish['name']} uneaten and discard it."
    if whole and applied != "nourishment":
        text += " " + fish_fact({**fish, "toxic": False})
    if fish["toxic"]:
        text += " Your stomach cramps. That fish was poisonous."
    elif not fish["edible"]:
        text += " Tough and bitter. This is better kept for bait."
    feedback(sim, eid, text)
    sim.emit(Event("fish_eaten", eid=eid, species_id=fish["id"], whole=whole, effect=applied, toxic=fish["toxic"]))
    return True


def depletion_multiplier(resilience):
    """Repeated fish retain benefits; positive resilience asymptotically saves food."""
    value = float(resilience) * .025
    return 1.0 / (1.0 + value) if value >= 0 else 1.0 - value


def feedback(sim, eid, text):
    if eid == getattr(sim, "player_eid", None):
        _log_player_feedback(sim, text, kind="game")


def begin_fishing(sim, eid, pole_id, direction=None, *, water=None, motive="relaxation"):
    state = ensure_fishing(sim)
    pos = sim.ecs.get(Position).get(eid)
    inv = sim.ecs.get(Inventory).get(eid)
    pole = inv.find(instance_id=pole_id) if inv else None
    if pos is None or pole is None or pole["item_id"] != "fishing_pole":
        return False
    if eid != getattr(sim, "player_eid", None) and len(state["sessions"]) >= MAX_NPC_FISHERS:
        return False
    if eid in state["sessions"]:
        return False
    if water is None:
        direction = direction or (0, 1)
        water = (pos.x + direction[0], pos.y + direction[1], pos.z)
    if max(abs(water[0] - pos.x), abs(water[1] - pos.y)) != 1 or water[2] != pos.z or water_at(sim, *water) is None:
        feedback(sim, eid, "Face the water from the bank, then use your fishing pole.")
        return False
    session = dict(eid=eid, pole=pole_id, origin=(pos.x, pos.y, pos.z), water=tuple(water),
                   phase="bait", motive=motive, created=int(sim.tick), bait=None)
    state["sessions"][eid] = session
    if eid == getattr(sim, "player_eid", None):
        sim.fishing_ui = {"open": True, "selected": 0, "message": "Choose bait, or cast with a bare hook."}
        for name in ("inventory_ui", "dialog_ui"):
            panel = getattr(sim, name, None)
            if isinstance(panel, dict):
                panel["open"] = False
        sim.set_time_paused(False, reason="dialog")
        sim.set_time_paused(True, reason="fishing")
        session["was_turn_based"] = sim.turn_based
        sim.turn_based = False
    else:
        ai = sim.ecs.get(AI).get(eid)
        if ai:
            ai.state, ai.target, ai.target_eid = "fishing", None, None
        bait = next((e for e in inv.items if e["item_id"] == "fishing_bait"), None)
        cast_line(sim, eid, bait["instance_id"] if bait else None)
    sim.emit(Event("fishing_started", eid=eid, x=pos.x, y=pos.y, z=pos.z))
    return True


def bait_choices(sim, eid):
    inv = sim.ecs.get(Inventory).get(eid)
    return [(None, "Bare hook")] + [(e["instance_id"], (e.get("metadata") or {}).get("display_name", ITEM_CATALOG[e["item_id"]]["name"]))
                                  for e in (inv.items if inv else ()) if e["item_id"] in {"fishing_bait", "fresh_fish"}]


def cast_line(sim, eid, bait_id=None):
    state = ensure_fishing(sim)
    session = state["sessions"].get(eid)
    if session is None or session["phase"] not in {"bait", "result"}:
        return False
    water = water_at(sim, *session["water"])
    inv = sim.ecs.get(Inventory).get(eid)
    pole = inv.find(instance_id=session["pole"]) if inv else None
    if not water or not pole or pole["item_id"] != "fishing_pole":
        end_fishing(sim, eid)
        return False
    if bait_id is not None:
        entry = inv.find(instance_id=bait_id)
        if entry is None or entry["item_id"] not in {"fishing_bait", "fresh_fish"}:
            return False
        if not inv.remove_item(instance_id=bait_id, quantity=1):
            return False
    # Bait is committed to this cast and cannot be duplicated by cancellation.
    state["serial"] += 1
    rng = random.Random(f"{sim.seed}:cast:{state['serial']}:{eid}")
    recover_stock(sim, water)
    available = [sid for sid, count in water["stock"].items() if count > 0]
    sid = rng.choices(available, weights=[water["stock"][sid] / state["species"][sid]["rarity"] for sid in available])[0] if available else None
    wait = rng.randint(50, 160) if bait_id else rng.randint(120, 280)
    session.update(phase="waiting", bait=bait_id, species=sid, cast_tick=int(sim.tick),
                   approach_tick=int(sim.tick) + max(20, wait - 25), bite_tick=int(sim.tick) + wait,
                   deadline=int(sim.tick) + wait + (max(12, 32 - state["species"][sid]["rarity"] * 4) if sid else 24),
                   rng_seed=state["serial"])
    if eid == getattr(sim, "player_eid", None):
        sim.fishing_ui["message"] = "Your float settles. Wait for it to dip."
        sim.set_time_paused(False, reason="fishing")
    return True


def finish_cast(sim, eid, message):
    session = ensure_fishing(sim)["sessions"].get(eid)
    if session:
        session.update(phase="result", result_tick=int(sim.tick), message=message)
    if eid == getattr(sim, "player_eid", None):
        sim.fishing_ui["message"] = message
        sim.set_time_paused(True, reason="fishing")
        feedback(sim, eid, message)


def strike(sim, eid):
    state = ensure_fishing(sim)
    session = state["sessions"].get(eid)
    if session is None or session["phase"] not in {"waiting", "approach", "bite"}:
        return False
    tick = int(sim.tick)
    sid = session.get("species")
    # Do not require a fresh key edge: a held Enter can strike too early.
    if not sid or tick < session["bite_tick"] or tick > session["deadline"]:
        rng = random.Random(f"{sim.seed}:fish-fumble:{session['rng_seed']}")
        very_early = tick - session["cast_tick"] < 8
        broken = very_early and rng.random() < .12
        if broken:
            inv = sim.ecs.get(Inventory).get(eid)
            pole = inv.find(instance_id=session["pole"]) if inv else None
            if pole:
                pole["item_id"] = "broken_fishing_pole"
        message = "You yank too soon. The hook comes back empty." if tick < session["bite_tick"] else "Too late. The fish gets away."
        if session.get("bait"):
            message += " Your bait is gone."
        if broken:
            message += " The pole cracks under the jerk."
        finish_cast(sim, eid, message)
        return False
    water = water_at(sim, *session["water"])
    if water is None or water["stock"].get(sid, 0) <= 0:
        finish_cast(sim, eid, "The fish slips away into the reeds.")
        return False
    inv = sim.ecs.get(Inventory).get(eid)
    added, _ = inv.add_item("fresh_fish", quantity=1, stack_max=1, instance_factory=sim.new_item_instance_id,
                            owner_eid=eid, owner_tag="player" if eid == getattr(sim, "player_eid", None) else "npc",
                            metadata=fish_metadata(sim, sid, water_id=water["id"])) if inv else (False, None)
    if not added:
        finish_cast(sim, eid, "You have nowhere to put the catch. You release it.")
        return False
    water["stock"][sid] -= 1
    finish_cast(sim, eid, f"Caught a {state['species'][sid]['name']}!")
    sim.emit(Event("fish_caught", eid=eid, species_id=sid, water_id=water["id"], x=session["origin"][0], y=session["origin"][1], z=0))
    return True


def end_fishing(sim, eid, message=""):
    state = ensure_fishing(sim)
    session = state["sessions"].pop(eid, None)
    if session is None:
        return
    if eid == getattr(sim, "player_eid", None):
        sim.fishing_ui = {"open": False}
        sim.turn_based = session.get("was_turn_based", sim.turn_based)
        sim.set_time_paused(False, reason="fishing")
        if message:
            feedback(sim, eid, message)
    else:
        ai = sim.ecs.get(AI).get(eid)
        if ai and ai.state == "fishing":
            ai.state, ai.target = "idle", None
        state["npc_cooldowns"][eid] = int(sim.tick) + 300


def fishing_input(sim, eid, key):
    state = getattr(sim, "fishing_ui", {})
    if not state.get("open"):
        return False
    session = ensure_fishing(sim)["sessions"].get(eid)
    if session is None:
        end_fishing(sim, eid)
        state["open"] = False
        sim.set_time_paused(False, reason="fishing")
        return True
    if key in (27, ord("q"), ord("Q")):
        end_fishing(sim, eid, "You reel in your line.")
    elif session["phase"] == "bait":
        from ui.input_keys import KEY_UP, KEY_DOWN
        choices = bait_choices(sim, eid)
        if key in (KEY_UP, ord("k")):
            state["selected"] = (state.get("selected", 0) - 1) % len(choices)
        elif key in (KEY_DOWN, ord("j")):
            state["selected"] = (state.get("selected", 0) + 1) % len(choices)
        elif key in (10, 13):
            cast_line(sim, eid, choices[state.get("selected", 0) % len(choices)][0])
    elif key in (10, 13):
        if session["phase"] == "result":
            session["phase"] = "bait"
            state.update(selected=0, message="Choose bait for another cast.")
        else:
            strike(sim, eid)
    return True


class FishingSystem(System):
    def __init__(self, sim):
        super().__init__(sim)
        state = ensure_fishing(sim)
        # Older saves acquire the index one materialized chunk at a time.
        self._unindexed = deque(k for k in sim.realized_chunks if k not in state["chunks"])
        self._next_invite = 0
        self._chunk_cursor = 0
        self._actor_cursor = {}
        sim.events.subscribe("entity_damaged", self.on_damage)
        sim.events.subscribe("npc_fishing_arrived", self.on_arrived)
        sim.events.subscribe("npc_fish_buyer_arrived", self.on_buyer_arrived)

    def on_damage(self, event):
        eid = event.data.get("target_eid", event.data.get("eid"))
        end_fishing(self.sim, eid, "You abandon your line to deal with the danger.")

    def on_arrived(self, event):
        eid = event.data.get("npc_eid")
        ai = self.sim.ecs.get(AI).get(eid)
        inv = self.sim.ecs.get(Inventory).get(eid)
        pole = inv.find(item_id="fishing_pole") if inv else None
        if ai and pole:
            begin_fishing(self.sim, eid, pole["instance_id"], water=getattr(ai, "fishing_water", None), motive=getattr(ai, "fishing_motive", "relaxation"))

    def on_buyer_arrived(self, event):
        from game.property_access import evaluate_property_access, site_services_for_property
        from game.property_runtime import property_distance
        eid = event.data.get("npc_eid")
        ai = self.sim.ecs.get(AI).get(eid)
        pos = self.sim.ecs.get(Position).get(eid)
        prop = self.sim.properties.get(getattr(ai, "fishing_buyer", None))
        if not ai or not pos or not prop or pos.z != int(prop.get("z", 0)) or property_distance(pos.x, pos.y, prop) > 2:
            return
        access = evaluate_property_access(self.sim, eid, prop, x=pos.x, y=pos.y, z=pos.z)
        if not access.can_use_services:
            return
        inv = self.sim.ecs.get(Inventory).get(eid)
        trade = next((s for s in self.sim.systems if callable(getattr(s, "npc_sell_fish", None))), None)
        catches = [e for e in (inv.items if inv else ()) if e["item_id"] == "fresh_fish"][:2]
        services = set(site_services_for_property(prop))
        can_cook = str(prop.get("archetype", "")) in PREP_ARCHETYPES or "campfire_cook" in services
        if not getattr(ai, "fishing_livelihood", False) and can_cook:
            prepare_fish(self.sim, eid, prop)
        elif trade:
            for entry in catches:
                trade.npc_sell_fish(eid, prop, entry["instance_id"])
        ai.fishing_catch_pending = bool(inv and inv.find(item_id="fresh_fish"))
        ai.state, ai.target, ai.target_eid = "idle", None, None
        ensure_fishing(self.sim)["npc_cooldowns"][eid] = int(self.sim.tick) + 300

    def update(self):
        if self._unindexed:
            index_fishing_chunk(self.sim, *self._unindexed.popleft())
        state = ensure_fishing(self.sim)
        for eid, session in tuple(state["sessions"].items()):
            pos = self.sim.ecs.get(Position).get(eid)
            ai = self.sim.ecs.get(AI).get(eid)
            player = eid == getattr(self.sim, "player_eid", None)
            if (pos is None or (pos.x, pos.y, pos.z) != session["origin"]
                    or water_at(self.sim, *session["water"]) is None
                    or (not player and (ai is None or ai.state != "fishing"))):
                end_fishing(self.sim, eid, "You reel in as you leave the bank.")
                continue
            tick = int(self.sim.tick)
            phase = session["phase"]
            if phase in {"waiting", "approach", "bite"}:
                if tick > session["deadline"]:
                    finish_cast(self.sim, eid, "The float jerks, then goes still. The fish escapes" + (" with your bait." if session.get("bait") else "."))
                elif tick >= session["bite_tick"] and session.get("species"):
                    if phase != "bite":
                        session["phase"] = "bite"
                        if player:
                            self.sim.fishing_ui["message"] = "BITE! The float plunges. Press Enter!"
                        self.sim.emit(Event("fishing_bite", eid=eid, x=pos.x, y=pos.y, z=pos.z))
                    if not player:
                        from game.skills import actor_skill
                        traits = self.sim.ecs.get(NPCTraits).get(eid)
                        skill = actor_skill(self.sim, eid, "perception")
                        delay = max(2, int(17 - skill - 5 * getattr(traits, "discipline", .5)))
                        if tick >= session["bite_tick"] + delay:
                            strike(self.sim, eid)
                elif tick >= session["approach_tick"] and phase == "waiting":
                    session["phase"] = "approach"
                    if player:
                        self.sim.fishing_ui["message"] = "A ripple beside the float. Wait for the bite..."
            elif phase == "result" and not player and tick >= session.get("result_tick", tick) + 12:
                inv = self.sim.ecs.get(Inventory).get(eid)
                catches = [e for e in inv.items if e["item_id"] == "fresh_fish"] if inv else []
                if tick - session["created"] >= 450 or len(catches) >= 2:
                    end_fishing(self.sim, eid)
                    self._finish_npc_outing(eid, session, catches)
                else:
                    cast_line(self.sim, eid)
            if not player:
                needs = self.sim.ecs.get(NPCNeeds).get(eid)
                if needs:
                    needs.energy = min(100, needs.energy + .1)
                    if session["motive"] == "social":
                        others = state["sessions"].values()
                        if any(s["eid"] != eid and max(abs(s["origin"][0]-pos.x), abs(s["origin"][1]-pos.y)) <= 4 for s in others):
                            needs.social = min(100, needs.social + .3)
        if int(self.sim.tick) >= self._next_invite:
            self._next_invite = int(self.sim.tick) + 20
            self._invite_npcs()

    def _invite_npcs(self):
        # One active chunk and sixteen actors per invitation pass, no registry scan.
        from game.population import work_shift_active
        state = ensure_fishing(self.sim)
        if len(state["sessions"]) >= MAX_NPC_FISHERS:
            return
        keys = [k for k, v in self.sim.world.loaded_chunks.items() if (v or {}).get("detail") == "active"]
        if not keys:
            return
        key = keys[self._chunk_cursor % len(keys)]
        self._chunk_cursor += 1
        banks = state["chunks"].get(key, {}).get("banks", ())
        if not banks:
            return
        ids = sorted(self.sim.entity_ids_in_chunk(key))
        start = self._actor_cursor.get(key, 0)
        candidates = (ids + ids)[start:start + min(16, len(ids))]
        self._actor_cursor[key] = (start + 16) % max(1, len(ids))
        for eid in candidates:
            if eid == getattr(self.sim, "player_eid", None) or state["npc_cooldowns"].get(eid, 0) > self.sim.tick:
                continue
            ai = self.sim.ecs.get(AI).get(eid)
            inv = self.sim.ecs.get(Inventory).get(eid)
            pos = self.sim.ecs.get(Position).get(eid)
            if not ai or not inv or not pos or pos.z != 0 or ai.state not in {"idle", "lounging", "resting", "socializing", "seeking_social", "working"}:
                continue
            if not inv.find(item_id="fishing_pole"):
                continue
            if inv.find(item_id="fresh_fish"):
                self._finish_npc_outing(eid, {}, [inv.find(item_id="fresh_fish")])
                state["npc_cooldowns"][eid] = int(self.sim.tick) + 300
                continue
            occupation = self.sim.ecs.get(Occupation).get(eid)
            professional = bool(getattr(ai, "fishing_livelihood", False))
            if not professional and occupation and work_shift_active(self.sim, occupation=occupation):
                continue
            needs = self.sim.ecs.get(NPCNeeds).get(eid)
            if needs and min(needs.hunger, needs.thirst, needs.safety) < 30:
                continue
            possible = (b for b in banks if max(abs(b[0]-pos.x), abs(b[1]-pos.y)) <= 10
                        and not self.sim.tilemap.entities_at(b[0], b[1], 0)
                        and not any(s["origin"] == (b[0], b[1], 0) for s in state["sessions"].values()))
            bank = min(possible, key=lambda b: abs(b[0]-pos.x)+abs(b[1]-pos.y), default=None)
            if bank is None:
                continue
            ai.state, ai.target, ai.target_eid = "seeking_fishing", (bank[0], bank[1], 0), None
            ai.fishing_water = (bank[2], bank[3], 0)
            ai.fishing_motive = "livelihood" if professional else ("social" if needs and needs.social < 60 else "relaxation")
            will = self.sim.ecs.get(NPCWill).get(eid)
            if will:
                will.intent, will.target, will.target_eid = ai.state, ai.target, None
            state["npc_cooldowns"][eid] = int(self.sim.tick) + 600
            self.sim.emit(Event("npc_intent_changed", npc_eid=eid, intent=ai.state, target=ai.target))
            break

    def _finish_npc_outing(self, eid, session, catches):
        from game.property_access import evaluate_property_access, site_services_for_property
        if not catches:
            return
        ai = self.sim.ecs.get(AI).get(eid)
        pos = self.sim.ecs.get(Position).get(eid)
        if ai is None or pos is None:
            return
        ai.fishing_catch_pending = True
        for prop in self.sim.properties_in_radius(pos.x, pos.y, pos.z, r=16)[:12]:
            archetype = str(prop.get("archetype", ""))
            services = set(site_services_for_property(prop))
            if archetype not in {"bait_shop", "butcher_shop", "restaurant", "corner_store"} and "campfire_cook" not in services:
                continue
            professional = getattr(ai, "fishing_livelihood", False)
            if professional and "campfire_cook" in services and archetype not in {"bait_shop", "butcher_shop", "restaurant", "corner_store"}:
                continue
            px, py, pz = int(prop.get("x", 0)), int(prop.get("y", 0)), int(prop.get("z", 0))
            if not evaluate_property_access(self.sim, eid, prop, x=pos.x, y=pos.y, z=pos.z).can_use_services:
                continue
            slots = [(px+dx, py+dy, pz) for dx, dy in ((0, 0),) + DIRS
                     if (t := self.sim.tilemap.tile_at(px+dx, py+dy, pz)) and t.walkable
                     and not self.sim.tilemap.entities_at(px+dx, py+dy, pz)]
            if not slots:
                continue
            ai.state, ai.target, ai.target_eid = "seeking_fish_buyer", min(slots, key=lambda p: abs(p[0]-pos.x)+abs(p[1]-pos.y)), None
            ai.fishing_buyer = prop["id"]
            will = self.sim.ecs.get(NPCWill).get(eid)
            if will:
                will.intent, will.target, will.target_eid = ai.state, ai.target, None
            self.sim.emit(Event("npc_intent_changed", npc_eid=eid, intent=ai.state, target=ai.target))
            return


__all__ = ["FishingSystem", "ensure_fishing", "index_fishing_chunk", "begin_fishing"]
