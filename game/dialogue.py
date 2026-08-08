"""Shared dialogue topic definitions and deterministic line variation."""

from __future__ import annotations

import random
import string


TOPIC_ORDER = (
    "name",
    "history",
    "roots",
    "job",
    "job_feel",
    "routine",
    "rapport",
    "check_in",
    "day_feel",
    "off_shift",
    "care_about",
    "read_player",
    "object_meaning",
    "workplace",
    "organization",
    "corporate_presence",
    "corporate_pull",
    "corporate_cost",
    "cult",
    "supervisor",
    "coworkers",
    "people",
    "where_place",
    "hire",
    "hire_manager",
    "hire_staff",
    "hire_accept",
    "hire_decline",
    "fire",
    "services",
    "service_fuel",
    "service_repair",
    "service_contractor",
    "service_banking",
    "service_business_desk",
    "service_insurance",
    "service_rest",
    "service_transit",
    "service_rail",
    "service_bus",
    "service_shuttle",
    "service_ferry",
    "service_coach",
    "service_intel",
    "service_work",
    "service_courier",
    "service_agency",
    "service_bounty",
    "service_trade",
    "service_discreet_trade",
    "service_street_doctor",
    "service_herbal",
    "service_butcher",
    "service_appearance",
    "service_outfitter",
    "service_drone_parts",
    "service_wire_gear",
    "service_records",
    "service_justice",
    "service_vehicle_sales",
    "service_used_cars",
    "service_vehicle_fetch",
    "service_gaming",
    "hours",
    "owner",
    "security",
    "access",
    "entry",
    "keyholder",
    "weak_point",
    "purpose",
    "apologize",
    "leave",
    "local",
    "street_talk",
    "social_incident",
    "social_business",
    "local_economy",
    "social_opportunity",
    "social_relationship",
    "concern",
    "detail",
    "opportunities",
    "fallout",
    "contract",
    "side_job",
    "side_job_accept",
    "side_job_decline",
    "hire_runner",
    "backup_orders",
    "backup_follow",
    "backup_hold",
    "backup_distract",
    "backup_goto_wait",
    "backup_wait_return",
    "backup_kill",
    "bodyguard_stand_down",
    "objective",
    "angle",
    "risk",
    "attention",
    "weird",
    "pry",
    "provoke",
    "intimidate",
    "insult",
    "contacts",
    "introduction",
    "vouch",
    "trade",
    "store_buy_policy",
    "street_appraise",
    "street_buy",
    "street_buy_accept",
    "street_buy_next",
    "street_buy_decline",
    "leverage",
    "leverage_credits",
    "leverage_trade_terms",
    "leverage_look_away",
    "leverage_distraction",
    "leverage_access_window",
    "leverage_credentials",
    "leverage_disable_camera",
    "leverage_hand_over_item",
    "leverage_falsify_record",
    "leverage_arrange_meeting",
    "bye",
    "payoff",
    "fence",
)


TOPIC_DEFS = {
    "name": {
        "label": "Who are you?",
        "root": True,
        "unlocks": ("history", "job", "workplace"),
    },
    "history": {
        "label": "How long have you been around here?",
        "root": False,
        "unlocks": ("roots",),
    },
    "roots": {
        "label": "What keeps you here?",
        "root": False,
        "unlocks": (),
    },
    "job": {
        "label": "What do you do?",
        "root": True,
        "unlocks": ("routine", "job_feel", "workplace", "organization"),
    },
    "job_feel": {
        "label": "How do you feel about the work?",
        "root": False,
        "unlocks": (),
    },
    "routine": {
        "label": "What does your day look like?",
        "root": False,
        "unlocks": ("day_feel", "off_shift"),
    },
    "rapport": {
        "label": "How's your day going?",
        "root": True,
        "unlocks": ("day_feel", "off_shift", "care_about", "read_player"),
    },
    "check_in": {
        "label": "How've you been since last time?",
        "root": False,
        "unlocks": (),
    },
    "day_feel": {
        "label": "How's the day treating you?",
        "root": False,
        "unlocks": (),
    },
    "off_shift": {
        "label": "What do you do when you're off?",
        "root": False,
        "unlocks": (),
    },
    "care_about": {
        "label": "What matters to you, really?",
        "root": False,
        "unlocks": (),
    },
    "read_player": {
        "label": "How do you read me?",
        "root": False,
        "unlocks": (),
    },
    "object_meaning": {
        "label": "Can I ask about that object?",
        "root": False,
        "unlocks": (),
    },
    "workplace": {
        "label": "Where do you work?",
        "root": False,
        "unlocks": ("organization", "services", "hours", "owner", "security", "access"),
    },
    "organization": {
        "label": "Who do you work for?",
        "root": False,
        "unlocks": ("supervisor", "coworkers", "people", "corporate_pull", "corporate_cost"),
    },
    "corporate_presence": {
        "label": "What's the corporation doing around here?",
        "root": True,
        "unlocks": ("corporate_pull", "corporate_cost"),
    },
    "corporate_pull": {
        "label": "Why do people choose them?",
        "root": False,
        "unlocks": ("services", "service_work"),
    },
    "corporate_cost": {
        "label": "What does their presence cost people?",
        "root": False,
        "unlocks": (),
    },
    "cult": {
        "label": "What's that circle about?",
        "root": True,
        "unlocks": (),
    },
    "supervisor": {
        "label": "Who runs things there?",
        "root": False,
        "unlocks": (),
    },
    "coworkers": {
        "label": "Who else works there?",
        "root": False,
        "unlocks": ("people",),
    },
    "people": {
        "label": "Who should I know around here?",
        "root": False,
        "unlocks": (),
    },
    "where_place": {
        "label": "Where is that place?",
        "root": True,
        "unlocks": (),
    },
    "hire": {
        "label": "Want a job?",
        "root": True,
        "unlocks": ("hire_manager", "hire_staff", "hire_accept", "hire_decline"),
    },
    "hire_manager": {
        "label": "Run the place.",
        "root": False,
        "unlocks": ("hire_accept", "hire_decline"),
    },
    "hire_staff": {
        "label": "Take a staff shift.",
        "root": False,
        "unlocks": ("hire_accept", "hire_decline"),
    },
    "hire_accept": {
        "label": "Agree to the wage.",
        "root": False,
        "unlocks": (),
    },
    "hire_decline": {
        "label": "No deal.",
        "root": False,
        "unlocks": (),
    },
    "fire": {
        "label": "I need to talk about your job.",
        "root": True,
        "unlocks": (),
    },
    "services": {
        "label": "What goes on there?",
        "root": False,
        "unlocks": (
            "service_fuel",
            "service_repair",
            "service_contractor",
            "service_banking",
            "service_business_desk",
            "service_insurance",
            "service_rest",
            "service_transit",
            "service_rail",
            "service_bus",
            "service_shuttle",
            "service_ferry",
            "service_coach",
            "service_intel",
            "service_work",
            "service_courier",
            "service_agency",
            "service_bounty",
            "service_trade",
            "service_discreet_trade",
            "service_street_doctor",
            "service_herbal",
            "service_butcher",
            "service_appearance",
            "service_outfitter",
            "service_drone_parts",
            "service_wire_gear",
            "service_records",
            "service_justice",
            "service_vehicle_sales",
            "service_used_cars",
            "service_vehicle_fetch",
            "service_gaming",
            "trade",
            "store_buy_policy",
        ),
    },
    "service_fuel": {
        "label": "Any fuel nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_repair": {
        "label": "Any repair shop nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_contractor": {
        "label": "Any contractor nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_banking": {
        "label": "Any bank or broker nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_business_desk": {
        "label": "Any business desk nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_insurance": {
        "label": "Any insurer or claims desk nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_rest": {
        "label": "Anywhere to sleep nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_transit": {
        "label": "Any transit nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_rail": {
        "label": "Where's the nearest station?",
        "root": False,
        "unlocks": (),
    },
    "service_bus": {
        "label": "Where can I catch a bus?",
        "root": False,
        "unlocks": (),
    },
    "service_shuttle": {
        "label": "Any shuttle stop around here?",
        "root": False,
        "unlocks": (),
    },
    "service_ferry": {
        "label": "Any ferry landing around here?",
        "root": False,
        "unlocks": (),
    },
    "service_coach": {
        "label": "Where can I catch a coach?",
        "root": False,
        "unlocks": (),
    },
    "service_intel": {
        "label": "Anywhere selling intel nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_work": {
        "label": "Any posted work nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_courier": {
        "label": "Any courier board nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_agency": {
        "label": "Any agency work nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_bounty": {
        "label": "Any bounty board nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_trade": {
        "label": "Any shopping around here?",
        "root": False,
        "unlocks": (),
    },
    "service_discreet_trade": {
        "label": "Know any discreet sellers?",
        "root": False,
        "unlocks": (),
    },
    "service_street_doctor": {
        "label": "Know any quiet doctors?",
        "root": False,
        "unlocks": (),
    },
    "service_herbal": {
        "label": "Any herbal care nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_butcher": {
        "label": "Any butcher nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_appearance": {
        "label": "Anywhere for hair, makeup, or tattoos?",
        "root": False,
        "unlocks": (),
    },
    "service_outfitter": {
        "label": "Any outfitter nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_drone_parts": {
        "label": "Any drone parts nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_wire_gear": {
        "label": "Any Wire gear nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_records": {
        "label": "Where can I inspect civic records?",
        "root": False,
        "unlocks": (),
    },
    "service_justice": {
        "label": "Where's the nearest jail or courthouse?",
        "root": False,
        "unlocks": (),
    },
    "service_vehicle_sales": {
        "label": "Anyone selling vehicles nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_used_cars": {
        "label": "Any used cars nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_vehicle_fetch": {
        "label": "Anyone who can retrieve a vehicle?",
        "root": False,
        "unlocks": (),
    },
    "service_gaming": {
        "label": "Any gaming around here?",
        "root": False,
        "unlocks": (),
    },
    "hours": {
        "label": "When are they open?",
        "root": False,
        "unlocks": (),
    },
    "owner": {
        "label": "Who runs this place?",
        "root": False,
        "unlocks": ("security", "vouch"),
    },
    "security": {
        "label": "How tight is security there?",
        "root": False,
        "unlocks": ("access", "entry", "keyholder", "weak_point"),
    },
    "access": {
        "label": "How is it secured?",
        "root": False,
        "unlocks": ("entry", "keyholder", "weak_point"),
    },
    "entry": {
        "label": "Is there another way in?",
        "root": False,
        "unlocks": ("weak_point",),
    },
    "keyholder": {
        "label": "Who carries access?",
        "root": False,
        "unlocks": (),
    },
    "weak_point": {
        "label": "What's the weak point there?",
        "root": False,
        "unlocks": (),
    },
    "purpose": {
        "label": "I'm not here for trouble.",
        "root": True,
        "unlocks": (),
    },
    "apologize": {
        "label": "Sorry. My mistake.",
        "root": True,
        "unlocks": (),
    },
    "leave": {
        "label": "I'll go.",
        "root": True,
        "unlocks": (),
    },
    "local": {
        "label": "What's going on around here?",
        "root": True,
        "unlocks": (
            "street_talk",
            "concern",
            "detail",
            "fallout",
            "history",
            "service_fuel",
            "service_repair",
            "service_contractor",
            "service_banking",
            "service_business_desk",
            "service_insurance",
            "service_rest",
            "service_transit",
            "service_rail",
            "service_bus",
            "service_shuttle",
            "service_ferry",
            "service_coach",
            "service_intel",
            "service_work",
            "service_courier",
            "service_agency",
            "service_bounty",
            "service_trade",
            "service_discreet_trade",
            "service_street_doctor",
            "service_herbal",
            "service_butcher",
            "service_appearance",
            "service_outfitter",
            "service_drone_parts",
            "service_wire_gear",
            "service_records",
            "service_justice",
            "service_vehicle_sales",
            "service_used_cars",
            "service_vehicle_fetch",
            "service_gaming",
        ),
    },
    "street_talk": {
        "label": "What's the street saying?",
        "root": True,
        "unlocks": ("social_incident", "social_business", "local_economy", "social_opportunity", "social_relationship", "detail"),
    },
    "social_incident": {
        "label": "What trouble are people talking about?",
        "root": False,
        "unlocks": ("detail",),
    },
    "social_business": {
        "label": "Who's got a reputation right now?",
        "root": False,
        "unlocks": ("where_place",),
    },
    "local_economy": {
        "label": "How are local businesses doing?",
        "root": False,
        "unlocks": ("services", "social_business", "where_place"),
    },
    "social_opportunity": {
        "label": "Any rumor worth acting on?",
        "root": False,
        "unlocks": ("opportunities", "angle", "risk"),
    },
    "social_relationship": {
        "label": "Who's tied together around here?",
        "root": False,
        "unlocks": ("contacts",),
    },
    "concern": {
        "label": "Anyone causing trouble?",
        "root": False,
        "unlocks": ("detail",),
    },
    "detail": {
        "label": "Tell me more.",
        "root": False,
        "unlocks": (),
    },
    "opportunities": {
        "label": "Anything worth pursuing?",
        "root": True,
        "unlocks": ("fallout", "objective", "angle", "risk", "contract", "side_job", "hire_runner"),
    },
    "fallout": {
        "label": "Any fallout from rival moves?",
        "root": False,
        "unlocks": (),
    },
    "contract": {
        "label": "Any contracts going?",
        "root": False,
        "unlocks": (),
    },
    "side_job": {
        "label": "Need anything handled quietly?",
        "root": False,
        "unlocks": ("side_job_accept", "side_job_decline"),
    },
    "side_job_accept": {
        "label": "I'll take that job.",
        "root": False,
        "unlocks": (),
    },
    "side_job_decline": {
        "label": "Not this one.",
        "root": False,
        "unlocks": (),
    },
    "hire_runner": {
        "label": "I need backup for a few hours. Interested?",
        "root": False,
        "unlocks": ("backup_orders",),
    },
    "backup_orders": {
        "label": "Let's tighten the plan.",
        "root": False,
        "unlocks": (
            "backup_follow",
            "backup_hold",
            "backup_distract",
            "backup_goto_wait",
            "backup_wait_return",
            "backup_kill",
        ),
    },
    "backup_follow": {
        "label": "Back to passive cover.",
        "root": False,
        "unlocks": (),
    },
    "backup_hold": {
        "label": "Hang here.",
        "root": False,
        "unlocks": (),
    },
    "backup_distract": {
        "label": "Make a distraction.",
        "root": False,
        "unlocks": (),
    },
    "backup_goto_wait": {
        "label": "Head to the marked spot and wait.",
        "root": False,
        "unlocks": (),
    },
    "backup_wait_return": {
        "label": "Head to the marked spot, wait, then return.",
        "root": False,
        "unlocks": (),
    },
    "backup_kill": {
        "label": "Take out the marked target.",
        "root": False,
        "unlocks": (),
    },
    "objective": {
        "label": "What would help me right now?",
        "root": False,
        "unlocks": ("angle", "risk"),
    },
    "angle": {
        "label": "Where would you start?",
        "root": False,
        "unlocks": ("risk",),
    },
    "risk": {
        "label": "What's the catch?",
        "root": False,
        "unlocks": (),
    },
    "attention": {
        "label": "Am I drawing attention?",
        "root": True,
        "unlocks": (),
    },
    "weird": {
        "label": "Ask something strange. [odd]",
        "root": False,
        "unlocks": (),
    },
    "pry": {
        "label": "What's your interest here, anyway? [hostile]",
        "root": False,
        "unlocks": (),
    },
    "provoke": {
        "label": "Needle them for an honest reaction. [hostile]",
        "root": False,
        "unlocks": (),
    },
    "intimidate": {
        "label": "Pressure them for local information. [threat]",
        "root": False,
        "unlocks": (),
    },
    "insult": {
        "label": "Throw a cheap shot. [hostile]",
        "root": False,
        "unlocks": (),
    },
    "contacts": {
        "label": "Who should I know?",
        "root": True,
        "unlocks": ("people", "introduction", "vouch"),
    },
    "introduction": {
        "label": "Could you put me in touch?",
        "root": False,
        "unlocks": (),
    },
    "vouch": {
        "label": "Can you put in a good word?",
        "root": False,
        "unlocks": (),
    },
    "trade": {
        "label": "Let's trade.",
        "root": True,
        "unlocks": ("store_buy_policy",),
    },
    "store_buy_policy": {
        "label": "What does this place buy?",
        "root": True,
        "unlocks": (),
    },
    "street_appraise": {
        "label": "Can you look over this stock for me?",
        "root": True,
        "unlocks": (),
    },
    "street_buy": {
        "label": "Can we do some street trade?",
        "root": True,
        "unlocks": (),
    },
    "street_buy_accept": {
        "label": "Sell it.",
        "root": False,
        "unlocks": (),
    },
    "street_buy_next": {
        "label": "What about the next item?",
        "root": False,
        "unlocks": (),
    },
    "street_buy_decline": {
        "label": "Not this time.",
        "root": False,
        "unlocks": (),
    },
    "bye": {
        "label": "Goodbye.",
        "root": True,
        "unlocks": (),
    },
    "payoff": {
        "label": "I can make it worth your while to ease off the scrutiny.",
        "root": False,
        "unlocks": (),
    },
    "fence": {
        "label": "I have some things I need to move quietly.",
        "root": False,
        "unlocks": (),
    },
    "leverage": {
        "label": "I know what you've been hiding.",
        "root": True,
        "unlocks": (
            "leverage_credits",
            "leverage_trade_terms",
            "leverage_look_away",
            "leverage_distraction",
            "leverage_access_window",
            "leverage_credentials",
            "leverage_disable_camera",
            "leverage_hand_over_item",
            "leverage_falsify_record",
            "leverage_arrange_meeting",
        ),
    },
    "leverage_credits": {
        "label": "Pay me and I keep the records quiet.",
        "root": False,
        "unlocks": (),
    },
    "leverage_trade_terms": {
        "label": "Give me better terms at your counter.",
        "root": False,
        "unlocks": (),
    },
    "leverage_look_away": {
        "label": "Look the other way for me.",
        "root": False,
        "unlocks": (),
    },
    "leverage_distraction": {
        "label": "Make a distraction and keep people looking elsewhere.",
        "root": False,
        "unlocks": (),
    },
    "leverage_access_window": {
        "label": "Open a real access window for me.",
        "root": False,
        "unlocks": (),
    },
    "leverage_credentials": {
        "label": "Hand over your credential.",
        "root": False,
        "unlocks": (),
    },
    "leverage_disable_camera": {
        "label": "Take one of your cameras offline.",
        "root": False,
        "unlocks": (),
    },
    "leverage_hand_over_item": {
        "label": "Hand over something useful.",
        "root": False,
        "unlocks": (),
    },
    "leverage_falsify_record": {
        "label": "Put me in the access records.",
        "root": False,
        "unlocks": (),
    },
    "leverage_arrange_meeting": {
        "label": "Arrange a meeting with one of your contacts.",
        "root": False,
        "unlocks": (),
    },
    "bodyguard_stand_down": {
        "label": "Stand down from this detail.",
        "root": True,
        "unlocks": (),
    },
}


PLAYER_TOPIC_BANKS = {
    "name": (
        "So who are you?",
        "What should I call you?",
        "Mind telling me your name?",
    ),
    "history": (
        "Have you been around here long?",
        "So how long have you been on this block?",
        "You local, or did you land here more recently?",
    ),
    "roots": (
        {
            "text": "What keeps you tied to this place?",
            "npc_reserved": (
                "Enough ties that I am still here.",
                "Same reason as most people: one tie, then another.",
            ),
            "npc_open": (
                "{rapport_roots_note}",
                "Mostly? {rapport_roots_note_lc}",
            ),
            "npc_warm": (
                "{rapport_roots_note} It creeps up on you when a place starts feeling like yours.",
                "{rapport_roots_note} After a while you stop pretending that does not matter.",
            ),
            "npc_rebuff": (
                "That is personal ground, and we are not there yet.",
                "You are reaching for roots before we have even settled into a conversation.",
            ),
        },
        {
            "text": "So why stay here?",
            "npc_reserved": (
                "Because I am still here, for one.",
                "Because leaving is not always the easy half.",
            ),
            "npc_open": (
                "{rapport_roots_note}",
                "There is a reason I keep circling back. {rapport_roots_note}",
            ),
            "npc_warm": (
                "{rapport_roots_note} Some places get under your skin before you notice.",
                "{rapport_roots_note} That counts more than I like admitting.",
            ),
            "npc_rebuff": (
                "That is not a first-pass question for me.",
                "You do not get the whole why-stay story this early.",
            ),
        },
    ),
    "job": (
        "So what do you do around here?",
        "What kind of work do you do?",
        "What do you do for a living?",
        "What keeps you busy around here?",
        "What is your corner of this place?",
    ),
    "job_feel": (
        {
            "text": "How do you feel about the work itself?",
            "npc_reserved": (
                "It is work. That is enough of a feeling for some days.",
                "I show up and do it. Some days that is the whole answer.",
            ),
            "npc_open": (
                "{rapport_job_note}",
                "Honestly? {rapport_job_note_lc}",
            ),
            "npc_warm": (
                "{rapport_job_note} I care more about getting it right than I usually say out loud.",
                "{rapport_job_note} When it lands clean, that still means something to me.",
            ),
            "npc_rebuff": (
                "That is a more personal angle on the work than I feel like opening right now.",
                "You are asking for the inside of the job, not just the title. I am not there with you yet.",
            ),
        },
        {
            "text": "Do you actually like the {career_text} work?",
            "npc_reserved": (
                "Like is a generous word for work.",
                "Some days I respect it. Some days I just finish it.",
            ),
            "npc_open": (
                "{rapport_job_note}",
                "Depends on the day. {rapport_job_note}",
            ),
            "npc_warm": (
                "{rapport_job_note} It gets under my skin in the good way sometimes.",
                "{rapport_job_note} There is pride in it, even when I act like there is not.",
            ),
            "npc_rebuff": (
                "That is not a question I give a clean answer to on demand.",
                "You are asking for how the work sits in me. Not yet.",
            ),
        },
    ),
    "routine": (
        "What does a normal day look like for you?",
        "When are you usually moving through here?",
        "How does your day tend to run?",
        "What rhythm does the work keep you on?",
        "Where would someone usually find you during the day?",
    ),
    "rapport": (
        {
            "text": "How's your day going?",
            "npc_reserved": (
                "{rapport_day_note}",
                "Same day as anyone else's, mostly. {rapport_day_note}",
            ),
            "npc_open": (
                "{rapport_day_note} Could be worse.",
                "I have had rougher. {rapport_day_note}",
            ),
            "npc_warm": (
                "{rapport_day_note} Better for the asking, honestly.",
                "{rapport_day_note} Nice change, somebody asking like they mean it.",
            ),
            "npc_rebuff": (
                "We barely know each other and you are already asking after the day.",
                "That is a personal sort of question for minute one.",
            ),
        },
        {
            "text": "Day treating you alright?",
            "npc_reserved": (
                "It is moving. That counts.",
                "{rapport_day_note}",
            ),
            "npc_open": (
                "{rapport_day_note} I am still standing, anyway.",
                "{rapport_day_note} So I will call it survivable.",
            ),
            "npc_warm": (
                "{rapport_day_note} Feels better once somebody asks straight.",
                "{rapport_day_note} I can breathe a little easier saying it out loud.",
            ),
            "npc_rebuff": (
                "That is a quick jump into the personal lane.",
                "Maybe later. I am not handing you my whole day cold.",
            ),
        },
        {
            "text": "You holding up okay?",
            "npc_reserved": (
                "Holding up is about right.",
                "Enough to keep moving. That is where the bar sits today.",
            ),
            "npc_open": (
                "{rapport_day_note}",
                "I appreciate the ask. {rapport_day_note}",
            ),
            "npc_warm": (
                "{rapport_day_note} That lands better from someone who actually listens.",
                "{rapport_day_note} Easier answer when the question does not feel thrown away.",
            ),
            "npc_rebuff": (
                "That sounds warmer than where we are.",
                "You are asking like we have more ease than we do.",
            ),
        },
    ),
    "check_in": (
        {
            "text": "How've you been since last time?",
            "npc_reserved": (
                "Still moving.",
                "About the same, mostly.",
            ),
            "npc_open": (
                "{rapport_check_in_note}",
                "Since last time? {rapport_check_in_note_lc}",
            ),
            "npc_warm": (
                "{rapport_check_in_note} I remember where we left it, anyway.",
                "{rapport_check_in_note} Feels a little easier picking the thread back up with you.",
            ),
            "npc_rebuff": (
                "We are not close enough for that kind of continuity talk from you right now.",
                "That sort of check-in lands warmer than where we actually stand.",
            ),
        },
        {
            "text": "How've things been treating you since we last talked?",
            "npc_reserved": (
                "Could be worse.",
                "Still standing, which is enough of an answer some days.",
            ),
            "npc_open": (
                "{rapport_check_in_note}",
                "Honestly? {rapport_check_in_note_lc}",
            ),
            "npc_warm": (
                "{rapport_check_in_note} Nice having somebody remember there was a last time.",
                "{rapport_check_in_note} That kind of question lands differently once there is a little history behind it.",
            ),
            "npc_rebuff": (
                "You are reaching for familiarity faster than I am willing to give it.",
                "Maybe later. That question assumes more ease between us than I feel right now.",
            ),
        },
        {
            "text": "Want to pick up where we left off?",
            "npc_reserved": (
                "Carefully, maybe.",
                "Depends which part you mean.",
            ),
            "npc_open": (
                "{rapport_check_in_note}",
                "We can pick up a little of it. {rapport_check_in_note}",
            ),
            "npc_warm": (
                "{rapport_check_in_note} I was wondering whether that thread would come back around.",
                "{rapport_check_in_note} With you, picking it back up does not feel wasted.",
            ),
            "npc_rebuff": (
                "We did not leave enough there for you to pick up like that.",
                "That is more continuity than I am ready to grant.",
            ),
        },
    ),
    "day_feel": (
        {
            "text": "What kind of day has it been?",
            "npc_reserved": (
                "{rapport_day_note}",
                "The sort you get through one piece at a time.",
            ),
            "npc_open": (
                "{rapport_day_note} It has had a shape to it, anyway.",
                "{rapport_day_note} Enough going on to keep me from drifting.",
            ),
            "npc_warm": (
                "{rapport_day_note} Some days feel like they are trying to sand a person down.",
                "{rapport_day_note} You ask at the right time, I guess.",
            ),
            "npc_rebuff": (
                "That is more of my day than I feel like unpacking for you.",
                "You are asking after the inside of the day now. I am not opening that much.",
            ),
        },
        {
            "text": "You sound like the day's been doing something to you.",
            "npc_reserved": (
                "It has. I am still here.",
                "{rapport_day_note}",
            ),
            "npc_open": (
                "{rapport_day_note} Some days sit heavier than others.",
                "{rapport_day_note} That is about the honest size of it.",
            ),
            "npc_warm": (
                "{rapport_day_note} Hard not to feel it by the end of one like this.",
                "{rapport_day_note} Sometimes it helps hearing somebody notice.",
            ),
            "npc_rebuff": (
                "You do not know me well enough to pull at that thread yet.",
                "That is a close read for someone I do not know that well.",
            ),
        },
    ),
    "off_shift": (
        {
            "text": "What do you do when you're off the clock?",
            "npc_reserved": (
                "Nothing dramatic. I get clear and keep it moving.",
                "Usual things. Eat, breathe, let the noise burn off.",
            ),
            "npc_open": (
                "{rapport_off_shift_note}",
                "Mostly? {rapport_off_shift_note_lc}",
            ),
            "npc_warm": (
                "{rapport_off_shift_note} Everybody needs a little corner of the day back.",
                "{rapport_off_shift_note} That is how I keep the work from swallowing the rest of me.",
            ),
            "npc_rebuff": (
                "Off-shift life is the part I keep for myself.",
                "That is private ground, even if you asked it gently.",
            ),
        },
        {
            "text": "So what does your time actually look like when the work lets go?",
            "npc_reserved": (
                "Quiet if I can get it.",
                "Less interesting than you are hoping, probably.",
            ),
            "npc_open": (
                "{rapport_off_shift_note}",
                "When the day loosens up, {rapport_off_shift_note_lc}",
            ),
            "npc_warm": (
                "{rapport_off_shift_note} I try to remember I belong to myself for a bit too.",
                "{rapport_off_shift_note} That is how I come back the next day without grinding my teeth through it.",
            ),
            "npc_rebuff": (
                "That is more off-shift than I hand over lightly.",
                "You are asking for the life around the work. Not today.",
            ),
        },
    ),
    "care_about": (
        {
            "text": "What matters to you, really?",
            "npc_reserved": (
                "Enough to keep me showing up.",
                "A few things. I keep them close.",
            ),
            "npc_open": (
                "{rapport_care_note}",
                "Honestly? {rapport_care_note_lc}",
            ),
            "npc_warm": (
                "{rapport_care_note} Once you know that about a person, you can do real damage with it.",
                "{rapport_care_note} I do not say it out loud to just anyone.",
            ),
            "npc_rebuff": (
                "That is deeper than I want to go with you right now.",
                "No. That kind of question lands too close if we have not earned it.",
            ),
        },
        {
            "text": "What are you actually trying to protect in all this?",
            "npc_reserved": (
                "The same things anyone tries to protect.",
                "Enough that I am still here guarding it.",
            ),
            "npc_open": (
                "{rapport_care_note}",
                "That is the part I try not to lose sight of. {rapport_care_note}",
            ),
            "npc_warm": (
                "{rapport_care_note} Maybe that is the closest thing I have to a straight answer.",
                "{rapport_care_note} That is the kind of truth people usually earn slowly.",
            ),
            "npc_rebuff": (
                "That question asks for a lot.",
                "You are reaching right into the part I keep defended.",
            ),
        },
        {
            "text": "What would you hate to lose?",
            "npc_reserved": (
                "Enough that I do not list it for strangers.",
                "A few things. Naming them makes them easier to hurt.",
            ),
            "npc_open": (
                "{rapport_care_note}",
                "If I am being honest, {rapport_care_note_lc}",
            ),
            "npc_warm": (
                "{rapport_care_note} That is the sort of answer I only give when the room feels steady.",
                "{rapport_care_note} It matters that you asked without trying to pry it loose.",
            ),
            "npc_rebuff": (
                "No. That is too close to the lock.",
                "You are asking me to name what can hurt me. Not right now.",
            ),
        },
    ),
    "read_player": (
        {
            "text": "How do you read me?",
            "npc_reserved": (
                "I am still working that out.",
                "You are still mostly a live question mark to me.",
            ),
            "npc_open": (
                "{rapport_read_note}",
                "If you want the honest read, {rapport_read_note_lc}",
            ),
            "npc_warm": (
                "{rapport_read_warm_note}",
                "{rapport_read_warm_note} That is the truest version I have got.",
            ),
            "npc_rebuff": (
                "That is a deeper question than you are entitled to yet.",
                "I am not laying my whole read of you on the table right now.",
            ),
        },
        {
            "text": "What kind of person do I seem like to you?",
            "npc_reserved": (
                "Still too early for a neat answer.",
                "I have an impression, not a verdict.",
            ),
            "npc_open": (
                "{rapport_read_note}",
                "Near as I can tell, {rapport_read_note_lc}",
            ),
            "npc_warm": (
                "{rapport_read_warm_note}",
                "{rapport_read_warm_note} I would not say that if I did not mean it.",
            ),
            "npc_rebuff": (
                "No. That is more of my read than I feel like spending right now.",
                "You are asking for a level of honesty that takes longer than this.",
            ),
        },
        {
            "text": "Where do I stand with you?",
            "npc_reserved": (
                "Somewhere I am still measuring.",
                "Not in a place I can name cleanly yet.",
            ),
            "npc_open": (
                "{rapport_read_note}",
                "If you want it plain, {rapport_read_note_lc}",
            ),
            "npc_warm": (
                "{rapport_read_warm_note}",
                "{rapport_read_warm_note} That is not a line I give out for politeness.",
            ),
            "npc_rebuff": (
                "You are asking for my private read before I am ready to spend it.",
                "I am not putting a label on you just because you asked.",
            ),
        },
    ),
    "object_meaning": (
        {
            "text": "Can I ask about {object_label}?",
            "npc_reserved": (
                "You already know enough to know it matters. That is where I leave it.",
                "It is mine to keep close. That is the whole answer for now.",
            ),
            "npc_open": (
                "{object_meaning_phrase}",
                "It looks small from the outside. {object_meaning_phrase}",
            ),
            "npc_warm": (
                "{object_meaning_phrase} I do not talk about that part with many people.",
                "{object_meaning_phrase} It is easier to carry when somebody asks gently.",
            ),
            "npc_rebuff": (
                "No. You do not get the story just because you noticed the object.",
                "That is not a door I am opening for you right now.",
            ),
        },
        {
            "text": "That {object_label} seemed important. What is it?",
            "npc_reserved": (
                "Important is the right word. Private is the next one.",
                "It keeps its own counsel, and so do I.",
            ),
            "npc_open": (
                "{object_meaning_phrase}",
                "If you are asking cleanly, {object_meaning_phrase_lc}",
            ),
            "npc_warm": (
                "{object_meaning_phrase} I guess you have earned the gentle version.",
                "{object_meaning_phrase} Some things stay ordinary until they are the only ordinary thing left.",
            ),
            "npc_rebuff": (
                "Do not pry at it.",
                "You saw it matter. That does not mean you get to spend it.",
            ),
        },
    ),
    "workplace": (
        "Where do you usually work?",
        "What place do you work out of?",
        "Is {workplace_name} where you spend most of your time?",
        "Where do you clock most of your hours?",
        "What door do you usually answer to?",
    ),
    "organization": (
        "Who are you tied in with there?",
        "Whose outfit is {workplace_name}?",
        "Are you working for somebody there, or is it your show?",
    ),
    "corporate_presence": (
        "What's {corporate_brand} doing to this block?",
        "How much of this neighborhood belongs to {corporate_brand} now?",
        "What's changed since {corporate_brand} moved in?",
        "How does {corporate_brand} make itself felt around here?",
    ),
    "corporate_pull": (
        "What makes {corporate_brand} worth dealing with?",
        "Why do people choose {corporate_brand}?",
        "What's the part of the {corporate_brand} pitch that actually works?",
        "If I walked into their side of the block, what would I go there for?",
    ),
    "corporate_cost": (
        "What's the part {corporate_brand} leaves out of the pitch?",
        "Who pays for {corporate_brand} taking more ground?",
        "What goes wrong once {corporate_brand} has enough control?",
        "What's the real cost of dealing with {corporate_brand}?",
    ),
    "supervisor": (
        "So who calls the shots there?",
        "Is there anybody above you day to day?",
        "When something goes wrong at {workplace_name}, whose problem is it?",
    ),
    "coworkers": (
        "Who else is usually on with you?",
        "Is it mostly a crew, or mostly just you?",
        "Who do you usually end up working alongside at {workplace_name}?",
    ),
    "people": (
        "Anybody around here worth knowing?",
        "Who matters around here?",
        "Who matters around {workplace_name}?",
    ),
    "where_place": (
        "Where is {referenced_place_name}, exactly?",
        "How do I find {referenced_place_name}?",
        "Where is that place, then?",
    ),
    "hire": (
        "Would you be interested in work?",
        "I might have a position for you. Interested?",
        "How do you feel about working for me?",
        "Want to talk about a job?",
    ),
    "hire_manager": (
        "Could you run the place for me?",
        "Would you take manager work there?",
        "Think you could handle the operation?",
        "I need someone steady in charge. Is that you?",
    ),
    "hire_staff": (
        "Would you take a regular shift?",
        "Could I put you on staff?",
        "Are you looking for counter or floor work?",
        "Want a spot on the schedule?",
    ),
    "hire_accept": (
        "Deal. I'll pay that rate.",
        "Agreed. That hourly rate works.",
    ),
    "hire_decline": (
        "No deal.",
        "I can't agree to that rate.",
    ),
    "fire": (
        "I need to take you off staff at {player_business_fire_name}.",
        "I am ending your position at {player_business_fire_name}.",
        "Your work at {player_business_fire_name} ends today.",
        "I need you off the schedule at {player_business_fire_name}.",
    ),
    "services": (
        "What does the place actually do?",
        "So what are people coming there for?",
        "What does {owner_place_name} mostly handle?",
    ),
    "service_fuel": (
        "Where can I get fuel nearby?",
        "Any place close that sells fuel?",
        "Who handles fuel around here?",
        "If I need fuel, where am I going?",
    ),
    "service_repair": (
        "Who repairs vehicles around here?",
        "Any repair shop close enough to matter?",
        "Where would you take something that needs fixing?",
        "Is there a mechanic nearby?",
    ),
    "service_contractor": (
        "Any contractor office nearby?",
        "Where do people find hired hands around here?",
        "Who handles contractor work close by?",
        "If I need a contractor, who is local?",
    ),
    "service_banking": (
        "Where is the nearest bank or broker?",
        "Who handles money around here?",
        "Any banking close by?",
        "If I need a broker, where do I start?",
    ),
    "service_business_desk": (
        "Where can an owner manage a business around here?",
        "Any business desk close by?",
        "Who handles business policy around here?",
        "If I need to check on a shop, where do I go?",
    ),
    "service_insurance": (
        "Any insurer or claims desk nearby?",
        "Who handles claims around here?",
        "Where would someone file insurance nearby?",
        "If I need coverage talk, who is close?",
    ),
    "service_rest": (
        "Anywhere close where I can sleep?",
        "Who rents a bed around here?",
        "Where do people rest nearby?",
        "If I need to get off my feet, where do I go?",
    ),
    "service_transit": (
        "How do people get out of this area?",
        "Any transit close by?",
        "Where is the nearest ride out?",
        "What moves people through here?",
    ),
    "service_rail": (
        "Where is the nearest station?",
        "How do I find the rail line?",
        "Any station close enough to use?",
        "Where do people catch the train around here?",
    ),
    "service_bus": (
        "Where can I catch a bus?",
        "Any bus stop close by?",
        "Which way to the nearest bus route?",
        "Where does the bus pick up around here?",
    ),
    "service_shuttle": (
        "Any shuttle stop around here?",
        "Where would I catch a shuttle?",
        "Who runs shuttle service nearby?",
        "Is there a shuttle route close?",
    ),
    "service_ferry": (
        "Any ferry landing around here?",
        "Where do people catch the ferry?",
        "Is there a landing close by?",
        "Which way to the nearest ferry?",
    ),
    "service_coach": (
        "Where can I catch a coach?",
        "Any coach stop around here?",
        "Which way to the regional coach?",
        "How do people get farther out by road?",
    ),
    "service_intel": (
        "Where does someone buy useful information?",
        "Any intel sellers around here?",
        "Who trades in local information nearby?",
        "If I need a lead, who sells one?",
    ),
    "service_work": (
        "Any posted work nearby?",
        "Where do people pick up paid jobs around here?",
        "Who has work boards close by?",
        "If I need paying work, where do I start?",
    ),
    "service_courier": (
        "Any courier board nearby?",
        "Who posts delivery work close by?",
        "Where do couriers pick up runs around here?",
        "If I want a route job, who has one?",
    ),
    "service_agency": (
        "Any agency work nearby?",
        "Where do people get day work around here?",
        "Who posts local errands or labor jobs?",
        "If I need agency work, who is close?",
    ),
    "service_bounty": (
        "Any bounty board nearby?",
        "Who posts alive-capture work around here?",
        "Where do fighters pick up legal targets?",
        "If I want a bounty job, who handles that?",
    ),
    "service_trade": (
        "Any shopping around here?",
        "Where can I buy supplies nearby?",
        "Who has a counter open close by?",
        "If I need to shop, where do I go?",
    ),
    "service_discreet_trade": (
        "Know any discreet sellers?",
        "Who sells things off the ordinary counter?",
        "Where would quiet stock move around here?",
        "Any sellers who prefer low voices?",
    ),
    "service_street_doctor": (
        "Know any quiet doctors?",
        "Who handles medical trouble off the books?",
        "Where does someone go when a clinic is too loud?",
        "Any doctor around here who does not ask much?",
    ),
    "service_herbal": (
        "Any herbal care nearby?",
        "Who handles hunger or thirst without a full clinic?",
        "Where do people get herbal help around here?",
        "If I need restorative care, who is close?",
    ),
    "service_butcher": (
        "Any butcher nearby?",
        "Who prepares game meat around here?",
        "Where would someone sell or pack meat close by?",
        "If I need meat prepared, who handles it?",
    ),
    "service_appearance": (
        "Anywhere for hair, makeup, or tattoos?",
        "Who handles styling around here?",
        "Where do people change up their look nearby?",
        "Any salon, counter, or tattoo place close?",
    ),
    "service_outfitter": (
        "Any outfitter nearby?",
        "Where do people gear up around here?",
        "Who sells field-ready kit close by?",
        "If I need equipment, who is nearby?",
    ),
    "service_drone_parts": (
        "Any drone parts nearby?",
        "Who sells drone modules or sensors around here?",
        "Where would I find radios, batteries, or drone stock?",
        "If I need drone parts, who is close?",
    ),
    "service_wire_gear": (
        "Any Wire gear nearby?",
        "Who sells decks or Wire software around here?",
        "Where would I find an interface and programs?",
        "If I need Wire equipment, who is close?",
    ),
    "service_records": (
        "Where can I inspect civic records?",
        "Who keeps the public records around here?",
        "Where would I look up a person or license nearby?",
        "Is there a public records counter close by?",
    ),
    "service_justice": (
        "Where is the nearest jail or courthouse?",
        "Who handles legal trouble around here?",
        "Where does law business happen nearby?",
        "If someone gets booked, where do they go?",
    ),
    "service_vehicle_sales": (
        "Anyone selling vehicles nearby?",
        "Where do people buy vehicles around here?",
        "Any vehicle lot close?",
        "Who has cars for sale nearby?",
    ),
    "service_used_cars": (
        "Anyone selling used cars nearby?",
        "Where do people buy a cheap vehicle around here?",
        "Any used-car lot close?",
        "Who moves vehicles for cash nearby?",
    ),
    "service_vehicle_fetch": (
        "Anyone who can retrieve a vehicle?",
        "Who handles vehicle recovery around here?",
        "Where would I find someone to fetch a car?",
        "Any vehicle retrieval outfit nearby?",
    ),
    "service_gaming": (
        "Any gaming around here?",
        "Where do people gamble nearby?",
        "Who runs games close by?",
        "If I wanted a table or machine, where would I go?",
    ),
    "hours": (
        "When is the place actually open?",
        "What hours does it keep?",
        "When is {owner_place_name} usually open?",
    ),
    "owner": (
        "Whose place is it, really?",
        "Who really runs the place?",
        "Who does {owner_place_name} answer to?",
    ),
    "security": (
        "How tight is the place, really?",
        "How much security are we talking?",
        "How hard is {owner_place_name} to push?",
    ),
    "access": (
        "What gets people through the door?",
        "How do people usually get in?",
        "What passes for access at {owner_place_name}?",
    ),
    "entry": (
        "Any other way in besides the front?",
        "Is there a side way in?",
        "If you were looking for another way into {owner_place_name}, where would you start?",
    ),
    "keyholder": (
        "Who actually carries the access?",
        "Who keeps the key or badge?",
        "Whose hand is the door to {owner_place_name} really in?",
    ),
    "weak_point": (
        "Where does the place bend?",
        "What's the soft spot?",
        "If something gives first at {owner_place_name}, what is it?",
    ),
    "local": (
        "So what's the word around here lately?",
        "Anything local I should know?",
        "What's been going on around here?",
    ),
    "street_talk": (
        "What's the street saying lately?",
        "What are people talking about when they think it matters?",
        "Anything making the rounds that you would tell me?",
        "What is the useful gossip right now?",
    ),
    "social_incident": (
        "What trouble are people talking about?",
        "Anything messy making the rounds?",
        "What happened that people keep repeating?",
    ),
    "social_business": (
        "Who's got a reputation right now?",
        "What place are people talking about?",
        "Any business I should read differently?",
    ),
    "local_economy": (
        "How are local businesses doing?",
        "What is the business weather on this block?",
        "Are the shops around here steady or hurting?",
        "What is the local money mood like?",
    ),
    "social_opportunity": (
        "Any rumor worth acting on?",
        "Anything in that talk I can actually use?",
        "Is there a live angle in the gossip?",
    ),
    "social_relationship": (
        "Who's tied together around here?",
        "Any people I should understand as a pair?",
        "Who keeps showing up for each other?",
    ),
    "concern": (
        "What's got people on edge?",
        "What is bothering folks around here?",
        "Anything needling at this place lately?",
    ),
    "detail": (
        "Can you get specific?",
        "Give me the useful part.",
        "What is the part that actually matters?",
    ),
    "opportunities": (
        "Anything worth chasing right now?",
        "Any angle on the street I should know about?",
        "What sounds live around here right now?",
        "What is actually worth my time out here?",
        "Where is the useful trouble today?",
    ),
    "fallout": (
        "Any fallout from rival moves?",
        "What did the rival activity shake loose?",
        "Did someone else's move leave anything behind?",
        "Anything worth salvaging from the mess?",
    ),
    "contract": (
        "Any contracts going?",
        "You mentioned work with a sharper edge?",
        "Is there paid work that needs a quiet hand?",
        "Anyone paying to have a problem handled?",
    ),
    "side_job": (
        "Need anything handled quietly?",
        "Any small work you would trust me with?",
        "Is there an errand I can take off your hands?",
        "Anything quiet that pays and helps your people?",
    ),
    "side_job_accept": (
        "I'll take that job.",
        "Mark that one for me.",
        "That works. I'll handle it.",
        "Put that in my hands.",
    ),
    "side_job_decline": (
        "Not this one.",
        "I'll pass on that.",
        "That is not my work right now.",
        "Keep that one off my list.",
    ),
    "hire_runner": (
        "I need backup for a few hours. Interested?",
        "Would you watch my back for pay?",
        "Can I hire you to stay close for a while?",
        "How much to have you on my side for a bit?",
    ),
    "backup_orders": (
        "Let's tighten the plan.",
        "How do you want to handle this next move?",
        "I need to set your position.",
        "Let's change your orders.",
    ),
    "backup_follow": (
        "Stay close again.",
        "Back on my shoulder.",
        "Return to passive cover.",
        "Keep with me and watch the edges.",
    ),
    "backup_hold": (
        "Hold this spot.",
        "Post up here for me.",
        "Stay here and keep watch.",
        "Plant yourself here until I come back.",
    ),
    "backup_distract": (
        "Make a distraction.",
        "Pull some eyes off me.",
        "Give them something else to watch.",
        "Bend the room away from me.",
    ),
    "backup_goto_wait": (
        "Head to {backup_marked_spot} and wait.",
        "Move to {backup_marked_spot} and hold.",
        "Post at {backup_marked_spot}.",
        "Take {backup_marked_spot} and stay there.",
    ),
    "backup_wait_return": (
        "Head to {backup_marked_spot}, wait, then return.",
        "Touch {backup_marked_spot}, hold a beat, then come back.",
        "Stage at {backup_marked_spot}, then return.",
        "Move to {backup_marked_spot} and circle back after a short wait.",
    ),
    "backup_kill": (
        "Take out {backup_kill_target_name}.",
        "Handle {backup_kill_target_name}.",
        "I need {backup_kill_target_name} stopped.",
        "Can you remove {backup_kill_target_name}?",
    ),
    "objective": (
        "What would actually help me here?",
        "If you were me, what would you focus on?",
        "What's the move on {objective_title}?",
        "What gets me closer to {objective_title}?",
        "What part of {objective_title} would you push first?",
    ),
    "angle": (
        "Where would you start?",
        "What's the first move?",
        "So what's the cleanest angle?",
        "Where is the opening?",
        "What is the least stupid way in?",
    ),
    "risk": (
        "What's the catch?",
        "What could go wrong fastest?",
        "What's the catch with {primary_opportunity_title}?",
        "Where does this go bad?",
        "What am I probably underestimating?",
    ),
    "attention": (
        "How hot do I look right now?",
        "Am I drawing eyes?",
        "Should I be keeping my head down?",
    ),
    "contacts": (
        "Know anybody I should be talking to?",
        "Who would you point me toward?",
        "Anybody useful I should know?",
        "Who opens doors around here?",
        "Who would you talk to if you were me?",
    ),
    "introduction": (
        "Would you introduce me to {social_lead_name}?",
        "Think you could put me in touch with {social_lead_name}?",
        "Can you connect me with {social_lead_name}?",
        "Could you open the door with {social_lead_name}?",
        "Would your name help me get a minute with {social_lead_name}?",
    ),
    "vouch": (
        "Can you put in a good word?",
        "Would your name smooth this over?",
        "Can I use your name there?",
        "Would you vouch for me if I keep it quiet?",
    ),
    "purpose": (
        "I'm not looking for trouble.",
        "Easy. I'm just passing through.",
        "I'm not here to make this worse.",
    ),
    "apologize": (
        "Alright, that's on me.",
        "Sorry. My mistake.",
        "Okay. I pushed that wrong.",
    ),
    "leave": (
        "Fine. I'm going.",
        "Alright. I'll move.",
        "Okay. I'll get out of your way.",
    ),
    "trade": (
        "Let me see what you've got.",
        "Mind if we do business?",
        "Let's talk prices.",
        "What are you willing to move?",
        "Can we make a clean trade?",
    ),
    "store_buy_policy": (
        "What does this place usually buy?",
        "What should I put on this counter if I am selling?",
        "What kinds of goods do you take here?",
        "What is this shop actually looking to buy?",
    ),
    "street_appraise": (
        "Can you look over this stock for me?",
        "What do you make of what I am carrying?",
        "Can you price this out honestly?",
        "I need a read on this stock. Interested?",
    ),
    "street_buy": (
        "Can we do some street trade?",
        "Are you buying or selling today?",
        "Can we make a quiet trade?",
        "Do you have anything moving right now?",
    ),
    "street_buy_accept": (
        "Sell it.",
        "Take the deal.",
        "Fine, it is yours.",
        "Done. Pay me.",
    ),
    "street_buy_next": (
        "What about the next item?",
        "What else would you buy?",
        "What about the rest of my stock?",
        "What is the next thing you'd move?",
    ),
    "street_buy_decline": (
        "Not this time.",
        "No deal.",
        "I am holding onto it.",
        "Pass. Maybe later.",
    ),
    "bye": (
        "Alright. Take care.",
        "That is enough for now. Later.",
        "Appreciate it. I'll let you get back to it.",
        "That answers enough. Stay safe.",
        "I have what I need. See you around.",
    ),
    "payoff": (
        "I can make it worth your while to forget you saw me.",
        "What would it cost for this to stay quiet?",
        "There has to be a number that ends this.",
        "Take the money and let this blur.",
    ),
    "fence": (
        "I have some things I need to move quietly.",
        "Can you make this stock disappear?",
        "What would you pay for goods with no questions?",
        "I need a quiet buyer. Is that you?",
    ),
    "leverage": (
        "I have the records. We should talk about what happens if {leverage_audience} sees them.",
        "I know about this: {leverage_fact}",
        "You should recognize these records. I decide where they go next.",
    ),
    "leverage_credits": (
        "Pay me {leverage_credits_amount} credits and I keep this contained.",
        "I want {leverage_credits_amount} credits for my silence.",
        "Transfer {leverage_credits_amount} credits. Then the records stay with me.",
    ),
    "leverage_trade_terms": (
        "My prices improve at {leverage_trade_property_name}. You make that happen.",
        "I want favorable terms at {leverage_trade_property_name}.",
        "Ease the counter rates at {leverage_trade_property_name}, and I keep quiet.",
    ),
    "leverage_look_away": (
        "You are going to look away at {leverage_look_away_property_name}.",
        "Give me a quiet window at {leverage_look_away_property_name}.",
        "For a while, you do not see what I do at {leverage_look_away_property_name}.",
    ),
    "leverage_distraction": (
        "Make a distraction. Pull attention away from me.",
        "Go make yourself conspicuous somewhere else.",
        "Give everyone nearby something else to watch.",
    ),
    "leverage_access_window": (
        "Open the access window at {leverage_access_property_name}.",
        "Release the doors at {leverage_access_property_name}. I want a real window.",
        "Use the {leverage_access_fixture_label} at {leverage_access_property_name} and let me through.",
    ),
    "leverage_credentials": (
        "Hand over the {leverage_credential_item_name} for {leverage_credential_property_name}.",
        "Your {leverage_credential_item_name}. Give it to me.",
        "I want the actual {leverage_credential_item_name}, not a promise.",
    ),
    "leverage_disable_camera": (
        "Take the {leverage_camera_name} at {leverage_camera_property_name} offline.",
        "Blind the {leverage_camera_name}. I want the surveillance gap.",
        "The {leverage_camera_name} goes dark, or these records travel.",
    ),
    "leverage_hand_over_item": (
        "Hand over your {leverage_item_name}.",
        "Put the {leverage_item_name} in my hand.",
        "I am leaving with your {leverage_item_name}.",
    ),
    "leverage_falsify_record": (
        "Put my name in the access records at {leverage_record_property_name}.",
        "Make the {leverage_record_fixture_label} recognize me at {leverage_record_property_name}.",
        "For a while, the records at {leverage_record_property_name} say I belong there.",
    ),
    "leverage_arrange_meeting": (
        "Arrange a meeting with {leverage_meeting_lead_name}.",
        "Put me in touch with your {leverage_meeting_relation}, {leverage_meeting_lead_name}.",
        "Use your name. I want a meeting with {leverage_meeting_lead_name}.",
    ),
    "weird": (
        {
            "text": "Do you think pigeons have favorite people?",
            "npc_soft": (
                "Pigeons having favorite people is a strange place to start, but I have heard worse.",
                "I have never had to map the emotional lives of pigeons before, but fine.",
            ),
            "npc_wary": (
                "You stopped me for a serious pigeon question?",
                "Why are we talking about pigeons right now?",
            ),
            "npc_fail": (
                "I am not doing pigeon philosophy with you.",
                "Find someone else to workshop the pigeon thing on.",
            ),
        },
        {
            "text": "What soup best matches your mood today?",
            "npc_soft": (
                "The soup question is ridiculous, but at least it is original.",
                "That is absurdly specific. Fine. Keep going.",
            ),
            "npc_wary": (
                "Why would I tell you my mood in soup form?",
                "That is a very strange thing to ask somebody cold.",
            ),
            "npc_fail": (
                "No. I am not ranking my feelings as soup for you.",
                "That soup question is where I tap out.",
            ),
        },
        {
            "text": "If this block had a mascot, what would it be?",
            "npc_soft": (
                "A block mascot is weirdly harmless as questions go.",
                "That is odd, but at least I know what you mean.",
            ),
            "npc_wary": (
                "You are asking me to assign a mascot to the whole block?",
                "That is the sort of question that makes people edge away.",
            ),
            "npc_fail": (
                "I am not doing a neighborhood mascot draft with you.",
                "No. Take the mascot question somewhere else.",
            ),
        },
        {
            "text": "Do your shoes ever feel like they know too much?",
            "npc_soft": (
                "The shoe question is unsettling, but I can survive it.",
                "That is one of the stranger things anyone has opened with around me.",
            ),
            "npc_wary": (
                "What does that even mean about my shoes?",
                "You are making this odd on purpose now.",
            ),
            "npc_fail": (
                "I am not staying for haunted shoe talk.",
                "No. The shoe thing is where this ends.",
            ),
        },
        {
            "text": "Be honest. Could you win an argument with a goose?",
            "npc_soft": (
                "The goose question is ridiculous, but I almost respect it.",
                "That is bizarre, though I admit it paints a picture.",
            ),
            "npc_wary": (
                "Why exactly are you sizing me up against a goose?",
                "That is a strange little test to spring on somebody.",
            ),
            "npc_fail": (
                "I am not debating goose combat with you.",
                "Go ask somebody else about the goose.",
            ),
        },
    ),
    "pry": (
        {
            "text": "What do you worry about when it gets quiet?",
            "npc_soft": (
                "That gets personal fast, though I get what you are reaching for.",
                "Quiet worries are not casual talk, but I see the angle.",
            ),
            "npc_wary": (
                "That is a heavy question to drop on somebody cold.",
                "You do not just walk up and ask people what keeps them up.",
            ),
            "npc_fail": (
                "No. I am not opening that door for you.",
                "That kind of question is exactly why this is over.",
            ),
        },
        {
            "text": "Who do you trust when things go sideways?",
            "npc_soft": (
                "Trust is personal territory, though I know why you would ask.",
                "That is closer to the bone than most people start with.",
            ),
            "npc_wary": (
                "You do not know me well enough to ask about trust like that.",
                "That is not the kind of thing I hand over to a near stranger.",
            ),
            "npc_fail": (
                "I am not giving you my trust map.",
                "No. That question closes the door.",
            ),
        },
        {
            "text": "What do you wish people understood about you?",
            "npc_soft": (
                "That is personal, but at least it is honest.",
                "You are reaching for the inside of a person there.",
            ),
            "npc_wary": (
                "That is a lot to ask out of nowhere.",
                "You are trying to get under the skin too fast.",
            ),
            "npc_fail": (
                "No. I am not unpacking myself for you.",
                "That is not a question you earn for free.",
            ),
        },
        {
            "text": "What part of yourself do you keep off the record?",
            "npc_soft": (
                "Off-the-record parts usually stay that way for a reason.",
                "That is nosy, though I appreciate the honesty of it.",
            ),
            "npc_wary": (
                "If it is off the record, why would I tell you?",
                "You hear yourself, right? That is deeply personal.",
            ),
            "npc_fail": (
                "I am not handing you the off-the-record parts.",
                "No. That question is too far over the line.",
            ),
        },
        {
            "text": "When was the last time you changed your mind about someone?",
            "npc_soft": (
                "That is more intimate than it sounds, but fair enough.",
                "You are leaning personal, though not without a reason.",
            ),
            "npc_wary": (
                "That is not the kind of story I owe you.",
                "You are digging for a private memory there.",
            ),
            "npc_fail": (
                "No. I am not opening old history for you.",
                "That kind of question is where I stop talking.",
            ),
        },
    ),
    "provoke": (
        {
            "text": "Drop the polite act. What do you actually think of me?",
            "npc_soft": (
                "Fine. You asked for the part people usually soften.",
                "Alright. No manners around it, then.",
            ),
            "npc_wary": (
                "You do not get honesty by trying to start a fight.",
                "I have a read on you. That does not mean you get to drag it out of me.",
            ),
            "npc_fail": (
                "What I think is that this conversation is over.",
                "You wanted a reaction. You can have the door closing.",
            ),
        },
        {
            "text": "Come on. Say the part you're swallowing.",
            "npc_soft": (
                "You really want the unsanded version? Fine.",
                "Alright. You pulled at it, so here it is.",
            ),
            "npc_wary": (
                "Do not mistake restraint for fear of saying it.",
                "I am swallowing it because this was almost a civil conversation.",
            ),
            "npc_fail": (
                "The part I was swallowing was goodbye.",
                "Keep pushing for a reaction somewhere else.",
            ),
        },
        {
            "text": "You keep looking at me like you have something to say.",
            "npc_soft": (
                "I do. Since you insist, I will be plain.",
                "That look had a reason. Listen carefully.",
            ),
            "npc_wary": (
                "A look is not an invitation to pick a fight.",
                "Maybe I was deciding whether this conversation was worth the trouble.",
            ),
            "npc_fail": (
                "I have something to say: leave me alone.",
                "I was looking for the end of this conversation. Found it.",
            ),
        },
        {
            "text": "Let's hear what you say when you're not hiding behind manners.",
            "npc_soft": (
                "Manners were doing you a favor, but fine.",
                "You want it without the soft edges. Alright.",
            ),
            "npc_wary": (
                "Manners are the only reason you still have a conversation.",
                "You are confusing self-control with something you can peel away.",
            ),
            "npc_fail": (
                "Without manners? Get out of my face.",
                "There. No manners: we are done.",
            ),
        },
    ),
    "intimidate": (
        {
            "text": "Stop wasting my time. Tell me what is happening around here.",
            "npc_soft": (
                "Fine. Take the answer and get out of my face.",
                "Alright. You want something useful, listen once.",
            ),
            "npc_wary": (
                "You do not get to order information out of me.",
                "That tone is buying you nothing but attention.",
            ),
            "npc_fail": (
                "Threaten somebody else. We are done.",
                "You picked the wrong person to lean on.",
            ),
        },
        {
            "text": "You can answer now, or we can make this difficult.",
            "npc_soft": (
                "You have your answer. Do not make me see you twice.",
                "Fine. One answer, and then you leave me alone.",
            ),
            "npc_wary": (
                "It already got difficult when you said that.",
                "Careful. You are turning a question into an incident.",
            ),
            "npc_fail": (
                "Try to make it difficult. See who arrives first.",
                "No. Now everybody nearby gets to remember your face.",
            ),
        },
        {
            "text": "Give me something useful before I decide you're part of the problem.",
            "npc_soft": (
                "Take this and keep me out of whatever comes next.",
                "Fine. Here is the useful part. Then we are finished.",
            ),
            "npc_wary": (
                "Your decisions do not make me part of anything.",
                "You are making yourself the problem right now.",
            ),
            "npc_fail": (
                "Decide whatever you like from farther away.",
                "That was a threat. I am treating it like one.",
            ),
        },
        {
            "text": "I asked nicely enough. Start talking.",
            "npc_soft": (
                "Fine. Hear it once, because there will not be a second time.",
                "Alright. This is the answer you get for that tone.",
            ),
            "npc_wary": (
                "No, you started demanding. Those are different things.",
                "You can ask, or you can threaten. You do not get to call both polite.",
            ),
            "npc_fail": (
                "You are done asking me anything.",
                "Conversation over. Keep the threat to yourself.",
            ),
        },
    ),
    "insult": (
        {
            "text": "You have the dramatic presence of a damp sandwich.",
            "npc_soft": (
                "A damp sandwich is weak material, but I will let it slide once.",
                "Damp sandwich is awful. Almost impressive in its own way.",
            ),
            "npc_wary": (
                "Did you really just compare me to a damp sandwich?",
                "That is the cheap line you went with?",
            ),
            "npc_fail": (
                "You do not get to call me a damp sandwich and keep talking.",
                "No. We are not continuing after the sandwich line.",
            ),
        },
        {
            "text": "You sound like you lose arguments to vending machines.",
            "npc_soft": (
                "That vending-machine line is cheap, but I have heard rougher.",
                "Weak shot, though I can admit it had structure.",
            ),
            "npc_wary": (
                "You really stopped me to compare me to a vending machine loser?",
                "That is the kind of insult you rehearse on the walk over.",
            ),
            "npc_fail": (
                "Take the vending-machine routine somewhere else.",
                "No. You do not get to swing that line and stay here.",
            ),
        },
        {
            "text": "I've met friendlier traffic cones.",
            "npc_soft": (
                "Traffic cone is a corny insult, but not the worst I have heard.",
                "Friendlier traffic cones. Fine. You got your cheap shot in.",
            ),
            "npc_wary": (
                "You walked up to call me worse than a traffic cone?",
                "That is not as charming as you seem to think it is.",
            ),
            "npc_fail": (
                "Go compare someone else to a traffic cone.",
                "No. The traffic cone line ends this.",
            ),
        },
        {
            "text": "You have the energy of a waiting room magazine.",
            "npc_soft": (
                "Waiting-room magazine is specific enough that I almost respect it.",
                "That was cheap, but at least you committed to the bit.",
            ),
            "npc_wary": (
                "You really think that was worth saying out loud?",
                "That is a strange amount of effort for a bad insult.",
            ),
            "npc_fail": (
                "Keep the waiting-room material to yourself.",
                "No. That line buys you the end of this conversation.",
            ),
        },
        {
            "text": "You carry yourself like a warning label nobody reads.",
            "npc_soft": (
                "That warning-label line was cheap, but I can let one pass.",
                "Not your best work, though I understand the message.",
            ),
            "npc_wary": (
                "That is a pretty deliberate way to make this worse.",
                "You really wanted me annoyed, apparently.",
            ),
            "npc_fail": (
                "Take the warning-label line and leave.",
                "No. We are done after that one.",
            ),
        },
        {
            "text": "You mistake being difficult for being important.",
            "npc_soft": (
                "That one had a point buried under the cheapness.",
                "Maybe. You still said it like somebody looking for a bruise.",
            ),
            "npc_wary": (
                "You came over here just to make yourself feel taller?",
                "That was precise enough to be deliberate. Watch yourself.",
            ),
            "npc_fail": (
                "You are not important enough to keep listening to.",
                "Take your little diagnosis and leave.",
            ),
        },
        {
            "text": "I can see why people stop telling you the truth.",
            "npc_soft": (
                "That is a sharp line from somebody who barely knows me.",
                "Maybe there is a splinter of truth in it. Do not get comfortable.",
            ),
            "npc_wary": (
                "You do not know enough about me to swing that cleanly.",
                "That sounded rehearsed. It still landed badly.",
            ),
            "npc_fail": (
                "Here is the truth: I am done talking to you.",
                "Congratulations. You just stopped the conversation yourself.",
            ),
        },
    ),
    "bodyguard_stand_down": (
        "I'm standing you down from this detail.",
        "Clear your post. You're released from this assignment.",
        "You're off this protection detail. Stand down clean.",
        "Close your post and step off the contract.",
    ),
}


PLAYER_CONNECTIVE_FOLLOWUP_PREFIXES = (
    "And",
    "So",
    "Okay, then,",
    "Right,",
)

PLAYER_CONNECTIVE_SHIFT_PREFIXES = (
    "Alright,",
    "Okay,",
    "Different question,",
    "Then,",
)

PLAYER_CONNECTIVE_SKIP_TOPICS = {
    "weird",
    "pry",
    "provoke",
    "intimidate",
    "insult",
    "trade",
    "street_appraise",
    "street_buy",
    "bye",
    "payoff",
    "fence",
    "leverage",
    "leverage_credits",
    "leverage_trade_terms",
    "leverage_look_away",
    "leverage_distraction",
    "leverage_access_window",
    "leverage_credentials",
    "leverage_disable_camera",
    "leverage_hand_over_item",
    "leverage_falsify_record",
    "leverage_arrange_meeting",
    "hire",
    "hire_manager",
    "hire_staff",
    "hire_accept",
    "hire_decline",
    "fire",
    "hire_runner",
    "backup_orders",
    "backup_follow",
    "backup_hold",
    "backup_distract",
    "backup_goto_wait",
    "backup_wait_return",
    "backup_kill",
    "bodyguard_stand_down",
}


PLAYER_MENU_BASE_LABEL_TOPICS = {
    "hire",
    "hire_manager",
    "hire_staff",
    "hire_accept",
    "hire_decline",
    "fire",
    "street_buy_accept",
    "street_buy_next",
    "street_buy_decline",
}


PLAYER_CONTEXT_MENU_BANKS = {
    "organization_owner": (
        "Is {workplace_name} actually yours?",
        "How much of {workplace_name} is yours?",
        "Is this place yours, or are you fronting it?",
        "Is {workplace_name} yours on paper too?",
    ),
    "supervisor_owner": (
        "Is anyone above you here?",
        "Does anybody sit above you at {workplace_name}?",
        "Is there someone above you on this place?",
        "Who, if anyone, is above you here?",
    ),
    "coworkers_solo": (
        "Is it usually just you here?",
        "Is it just you holding the place down?",
        "At {workplace_name}, is it mostly just you?",
        "Is just you the usual staffing plan?",
    ),
    "street_buy_requested": (
        "I might have some {street_buy_hint}. Can we trade?",
        "Are you still buying {street_buy_hint}, or are you moving other stock too?",
        "Is {street_buy_hint} still what you are looking for?",
        "Want to open trade and look at my {street_buy_hint}?",
    ),
}


AREA_STYLE_HINTS = {
    "city": {
        "farewell_tags": (
            "The city keeps moving.",
            "Nothing stays quiet for long.",
            "Keep up.",
            "Later.",
        ),
        "catch_phrases": (
            "This place never really sleeps.",
            "Word moves fast here.",
            "The city keeps no secrets long.",
            "Half the city learns things by pretending not to look.",
        ),
        "idioms": (
            "Keep it under the streetline.",
            "A quiet face travels farther than a loud story.",
            "The block counts twice before it forgets.",
        ),
        "local_terms": (
            "Streetline is what everybody saw enough to deny.",
            "Backcount follows a person longer than heat.",
            "Corner talk gets legs before noon.",
        ),
    },
    "frontier": {
        "farewell_tags": (
            "The road runs long out here.",
            "The weather turns quick out here.",
            "Always keep one eye on the horizon.",
        ),
        "catch_phrases": (
            "Even road dust keeps receipts.",
            "Nothing stays easy for long out here.",
            "The frontier holds on to things.",
            "Distance makes every choice louder.",
        ),
        "idioms": (
            "Roadcount changes faster than maps.",
            "A long road makes short tempers.",
            "A quiet day out here still has a bill.",
        ),
        "local_terms": (
            "Dustmark sticks to sloppy choices.",
            "Fence talk travels straighter than gossip.",
            "Out here, close means before dark.",
        ),
    },
    "coastal": {
        "farewell_tags": (
            "Mind the tide.",
            "The storm shifts quick on the coast.",
            "The sea has long ears.",
        ),
        "catch_phrases": (
            "The docks hear everything.",
            "The salt air carries talk farther than people think.",
            "The tide brings more than water.",
            "The port knows what moves and who waits too long.",
        ),
        "idioms": (
            "Tidebook never balances clean.",
            "Dockwind carries names.",
            "Storm talk makes people generous with bad guesses.",
        ),
        "local_terms": (
            "Tidebook is the version the docks remember.",
            "Dockwind makes a whisper cross the whole landing.",
            "Salt hours turn small delays into stories.",
        ),
    },
    "wilderness": {
        "farewell_tags": (
            "The quiet carries out here.",
            "The tree line remembers.",
            "The wild does not forget.",
        ),
        "catch_phrases": (
            "The quiet tells on people.",
            "Nothing in the wild stays hidden forever.",
            "A quiet trail is still a trail.",
            "Out here, you can't help but listen.",
        ),
        "idioms": (
            "Treeline talk travels quietly.",
            "A cold trail still tells on somebody.",
            "The quiet has a way of counting footsteps.",
        ),
        "local_terms": (
            "Treeline talk means news with no witness attached.",
            "Trailcount is never as empty as it looks.",
            "Out here, near means before the light turns.",
        ),
    },
}


DISTRICT_STYLE_HINTS = {
    "industrial": {
        "catch_phrases": (
            "The shift whistle never lies.",
            "Keep your gears straight.",
            "The floor remembers who misses a beat.",
            "A person's hands tell the honest story.",
        ),
        "idioms": (
            "Shiftline catches every mistake.",
            "Gear-debt comes due when the room gets loud.",
            "If the floor goes quiet, listen harder.",
        ),
        "local_terms": (
            "Shiftline is the part of the day nobody gets to dodge.",
            "Gear-debt means a problem someone kept nursing.",
        ),
        "address_terms": (
            "friend",
            "mate",
        ),
    },
    "residential": {
        "catch_phrases": (
            "The block remembers faces.",
            "Our neighbors notice plenty.",
            "Nobody forgets a face on their block.",
            "Curtains move faster than doors around here.",
        ),
        "idioms": (
            "Porchlight talk moves faster than mail.",
            "A quiet block is still taking notes.",
            "Curtain-count is high today.",
        ),
        "local_terms": (
            "Porchcount means who noticed without stepping outside.",
            "Doorquiet never lasts after trouble.",
        ),
        "address_terms": (
            "neighbor",
            "friend",
        ),
    },
    "downtown": {
        "catch_phrases": (
            "The center never really sleeps.",
            "The money moves fast downtown.",
            "Speed is the price of being central.",
            "Downtown hears a rumor and invoices it by lunch.",
        ),
        "idioms": (
            "Fastwalk rules apply.",
            "Lunch rumor becomes policy by noon.",
            "If it matters downtown, somebody already priced it.",
        ),
        "local_terms": (
            "Fastwalk means answer while you are still moving.",
            "Glass minutes cost more than street hours.",
        ),
        "address_terms": (
            "friend",
            "chief",
            "homie",
            "boss",
        ),
    },
    "slums": {
        "catch_phrases": (
            "The street's got ears.",
            "It gets real out here.",
            "Keep your pockets close.",
            "Help has a price out here.",
            "Every favor here leaves a thumbprint.",
        ),
        "idioms": (
            "Favor-marks last longer than cash.",
            "Backstep before you owe.",
            "Thin pockets still remember who helped.",
        ),
        "local_terms": (
            "Favor-mark means a kindness with a shadow.",
            "Backstep is what you take before the day owns you.",
            "Street mercy is real, but it keeps a ledger.",
        ),
        "address_terms": (
            "friend",
            "pal",
            "my homie",
            "dude"
        ),
    },
    "corporate": {
        "catch_phrases": (
            "Paper walls are always talking.",
            "Gotta keep it professional.",
            "That is above somebody's pay grade.",
            "The numbers cover a lot of ground.",
            "Every room here has a budget.",
            "Someone always signs the silence.",
        ),
        "idioms": (
            "Glass talk always has a signer.",
            "Budget hush covers plenty.",
            "Policy is just a locked door with nicer shoes.",
        ),
        "local_terms": (
            "Glass talk is what people say when walls might invoice them.",
            "Budget hush means nobody admits the quiet was purchased.",
        ),
        "address_terms": (
            "friend",
            "associate",
        ),
    },
    "military": {
        "catch_phrases": (
            "The chain of command sees plenty.",
            "Keep it clean.",
            "My orders cut clean.",
            "How copy?",
        ),
        "idioms": (
            "Linecall stays clean.",
            "Clean copy or no copy.",
            "Loose procedure makes loud reports.",
        ),
        "local_terms": (
            "Linecall means everyone knows who answered.",
            "Clean copy means no story attached.",
        ),
        "address_terms": (
            "citizen",
            "friend",
            "civilian",
        ),
    },
    "entertainment": {
        "catch_phrases": (
            "The crowd hears everything.",
            "The show's still running.",
            "The applause covers a lot.",
            "The applause is the loudest voice in the room.",
            "The applause is the toughest critic.",
            "Every backstage whisper wants an audience.",
        ),
        "idioms": (
            "Backlight makes every whisper taller.",
            "Curtain heat sticks.",
            "The room loves a secret until it owns one.",
        ),
        "local_terms": (
            "Backlight is gossip dressed up pretty.",
            "Curtain heat means trouble waiting for applause to cover it.",
        ),
        "address_terms": (
            "friend",
            "dear",
            "patron",
        ),
    },
    "transit": {
        "catch_phrases": (
            "Routes remember delays.",
            "Every platform has a listener.",
            "The schedule tells one truth and people tell another.",
        ),
        "idioms": (
            "Platform talk moves in loops.",
            "Routewash makes clean stories muddy.",
            "A missed stop can still follow you.",
        ),
        "local_terms": (
            "Routewash is what happens when a story rides too many lines.",
            "Platform time makes strangers sound local.",
        ),
        "address_terms": (
            "friend",
            "traveler",
        ),
    },
    "tourist": {
        "catch_phrases": (
            "Guest faces get noticed fast.",
            "Maps hide the parts locals actually use.",
            "A bright sign is not always a clean door.",
        ),
        "idioms": (
            "Map-smile only lasts one question.",
            "Guestlight makes things look safer than they are.",
        ),
        "local_terms": (
            "Guestlight is the shine a place keeps for new eyes.",
            "Map-smile means helpful until the question gets real.",
        ),
        "address_terms": (
            "friend",
            "traveler",
        ),
    },
}


ROLE_STYLE_HINTS = {
    "guard": {
        "register": "official",
        "lead_ins": (
            "For the record,",
            "Listen,",
            "Heads up,",
            "Heed this,",
        ),
        "catch_phrases": (
            "Rules are rules.",
            "Stay where you belong.",
            "Keep it moving.",
            "Don't cause trouble here.",
            "I notice repeats.",
        ),
        "idioms": (
            "Procedure has a long memory.",
            "A clean line keeps everyone breathing.",
        ),
        "local_terms": (
            "Paper shadow follows every bad step.",
            "Linecall means I know who I am answering for.",
        ),
        "address_terms": (
            "citizen",
            "friend",
        ),
    },
    "patrol": {
        "register": "official",
        "lead_ins": (
            "For the record,",
            "Listen up,",
            "Heads up,",
        ),
        "catch_phrases": (
            "The zone stays clear.",
            "Keep it orderly.",
            "Eyes open.",
            "Head on a swivel!",
            "Patterns matter.",
        ),
        "idioms": (
            "Patterns get louder when people hurry.",
            "The quiet part of a patrol still counts.",
        ),
        "local_terms": (
            "Linecall means every stop has a name on it.",
        ),
        "address_terms": (
            "citizen",
            "friend",
        ),
    },
    "scout": {
        "register": "official",
        "lead_ins": (
            "Listen,",
            "Eyes open,",
            "Quick note,",
        ),
        "catch_phrases": (
            "The quiet carries.",
            "Eyes stay open out here.",
        ),
        "idioms": (
            "A good scout trusts the second look.",
            "Quiet ground still changes shape.",
        ),
    },
    "thief": {
        "register": "rough",
        "lead_ins": (
            "Straight up,",
            "Look,",
            "Real talk,",
            "Peep this,",
        ),
        "catch_phrases": (
            "Loose talk costs.",
            "Keep it quiet.",
            "Do not be the reason this gets loud.",
            "Clean exits beat pretty stories.",
        ),
        "idioms": (
            "A clean exit is worth more than a clever entrance.",
            "Heat loves a slow hand.",
        ),
        "local_terms": (
            "Soft-step means nobody has to explain you later.",
        ),
    },
    "drunk": {
        "register": "rough",
        "lead_ins": (
            "Easy,",
            "Look,",
            "Between us,",
            "*hic*",
        ),
        "catch_phrases": (
            "The night's got long legs.",
            "Easy now.",
            "*hic*",
        ),
    },
    "bartender": {
        "catch_phrases": (
            "I hear plenty at the bar.",
            "People talk when they drink.",
            "You'd be surprised what I hear at the job.",
            "A wet counter collects dry secrets.",
        ),
        "idioms": (
            "Barlight makes liars generous.",
            "A glass tells on the hand holding it.",
        ),
        "local_terms": (
            "Barlight is when people think nobody can see them clearly.",
        ),
        "address_terms": (
            "friend",
            "there",
            "pal",
            "buddy",
        ),
    },
    "courier": {
        "register": "plain",
        "catch_phrases": (
            "The road keeps no secrets.",
            "Every movement tells a story.",
            "Late packages make loud enemies.",
            "Routes teach you who waits and who wanders.",
        ),
        "idioms": (
            "Routecount is never just distance.",
            "A clean handoff beats a loud arrival.",
        ),
        "local_terms": (
            "Routecount means distance, eyes, and who is waiting.",
            "Handoff hush is what keeps a package boring.",
        ),
    },
    "runner": {
        "register": "plain",
        "catch_phrases": (
            "Fast feet hear a lot.",
            "Loose routes make loud trouble.",
            "A clean pass beats a pretty plan.",
        ),
        "idioms": (
            "A good route is mostly the parts nobody notices.",
            "Fast gets ugly when it forgets quiet.",
        ),
        "local_terms": (
            "Threading means moving like the room already expected you.",
        ),
    },
    "driver": {
        "register": "plain",
        "catch_phrases": (
            "Roads teach patience the hard way.",
            "Every route has a mood.",
            "A bad turn tells on you.",
        ),
        "idioms": (
            "The road charges extra for panic.",
            "A clean turn is half apology.",
        ),
        "local_terms": (
            "Roadmood is why the same block feels different twice.",
        ),
    },
    "mechanic": {
        "register": "plain",
        "catch_phrases": (
            "Everything breaks where it was already tired.",
            "Bad maintenance always finds daylight.",
            "You can hear a problem before it admits itself.",
        ),
        "idioms": (
            "A machine lies loud before it dies quiet.",
            "Rust keeps better notes than people.",
        ),
        "local_terms": (
            "Tooltruth is what the part says after the owner is done explaining.",
        ),
        "address_terms": (
            "friend",
            "chief",
        ),
    },
    "shopkeeper": {
        "register": "plain",
        "catch_phrases": (
            "Counters remember who leaned on them.",
            "Bad business echoes.",
            "Receipts are quieter than rumors, but not by much.",
        ),
        "idioms": (
            "Counterweather changes before the door opens.",
            "Shelf heat tells you what people are afraid to ask for.",
        ),
        "local_terms": (
            "Counterweather is the mood that walks in before the customer.",
            "Shelf heat means stock people stare at and do not name.",
        ),
        "address_terms": (
            "friend",
            "neighbor",
        ),
    },
    "merchant": {
        "register": "plain",
        "catch_phrases": (
            "Prices talk when people do not.",
            "A counter sees more than it sells.",
            "Bad heat sticks to shelves.",
        ),
        "idioms": (
            "Counterweather changes before the door opens.",
            "Prices lean when the neighborhood leans.",
        ),
        "local_terms": (
            "Counterweather is the mood that walks in before the customer.",
        ),
        "address_terms": (
            "friend",
            "neighbor",
        ),
    },
    "clerk": {
        "register": "plain",
        "catch_phrases": (
            "Counters remember repeat faces.",
            "The till hears more than it should.",
            "People tell on themselves while pretending to browse.",
        ),
        "idioms": (
            "Counterweather changes before the bell rings.",
            "A slow customer is sometimes just a fast problem.",
        ),
        "local_terms": (
            "Counterweather is the mood that walks in before the customer.",
            "Shelf heat means stock people stare at and do not name.",
        ),
        "address_terms": (
            "friend",
            "neighbor",
        ),
    },
    "vendor": {
        "register": "plain",
        "catch_phrases": (
            "Stalls hear more than walls.",
            "A busy aisle tells the truth sideways.",
            "Goods move when stories move.",
        ),
        "idioms": (
            "A stall has ears even when the seller smiles.",
            "Market noise sorts itself if you stand still.",
        ),
        "local_terms": (
            "Aisleweather is how a market tells you what it wants.",
        ),
        "address_terms": (
            "friend",
            "neighbor",
        ),
    },
    "cashier": {
        "register": "plain",
        "catch_phrases": (
            "The register hears plenty.",
            "Small talk gets expensive at the counter.",
            "A line of customers becomes a line of rumors.",
        ),
        "idioms": (
            "Counterweather changes before the receipt prints.",
            "Receipts are the polite version of memory.",
        ),
        "local_terms": (
            "Register hush is what people use when the line is listening.",
        ),
        "address_terms": (
            "friend",
            "neighbor",
        ),
    },
    "server": {
        "register": "warm",
        "catch_phrases": (
            "Tables talk when people settle in.",
            "A room gets honest after the second cup.",
            "Service hears the parts people mean to keep quiet.",
        ),
        "idioms": (
            "Tablelight makes people softer than they expect.",
            "A clean plate does not mean a clean mood.",
        ),
        "local_terms": (
            "Tablelight is when a person forgets the room can hear them.",
        ),
        "address_terms": (
            "friend",
            "hon",
        ),
    },
    "resident": {
        "register": "plain",
        "catch_phrases": (
            "The block remembers faces.",
            "People notice what repeats.",
            "Doors hear more than walls admit.",
        ),
        "idioms": (
            "Porchcount is high when the block goes quiet.",
            "A neighbor hears the apology before the excuse.",
        ),
        "local_terms": (
            "Porchcount means who noticed without stepping outside.",
        ),
        "address_terms": (
            "neighbor",
            "friend",
        ),
    },
    "medic": {
        "catch_phrases": (
            "People talk when they hurt.",
            "Care comes around.",
            "Pain makes honest witnesses.",
        ),
        "idioms": (
            "Pain makes poor secrets.",
            "A steady hand is not the same as a soft heart.",
        ),
        "local_terms": (
            "Pulse talk is what people say when they think they might not get another chance.",
        ),
        "address_terms": (
            "friend",
        ),
    },
    "doctor": {
        "register": "plain",
        "catch_phrases": (
            "People tell the truth differently when they hurt.",
            "Pain makes poor secrets.",
            "Care gets complicated fast.",
        ),
        "idioms": (
            "Pain makes poor secrets.",
            "A diagnosis is just a door with cleaner hinges.",
        ),
        "local_terms": (
            "Pulse talk is what people say when they think they might not get another chance.",
        ),
        "address_terms": (
            "friend",
        ),
    },
    "street_doctor": {
        "register": "rough",
        "lead_ins": (
            "Look,",
            "Quietly,",
            "Between us,",
        ),
        "catch_phrases": (
            "Pain makes poor secrets.",
            "Keep it clean or keep it moving.",
            "Quiet care is still care.",
        ),
        "idioms": (
            "Pain makes poor secrets.",
            "Quiet care still leaves a trail.",
        ),
        "local_terms": (
            "Backroom clean means nobody asks why the bandage is new.",
        ),
        "address_terms": (
            "friend",
        ),
    },
    "broker": {
        "register": "official",
        "lead_ins": (
            "For the record,",
            "Off the books,",
            "Between us,",
        ),
        "catch_phrases": (
            "The market keeps moving.",
            "Value finds its level... without guidance.",
            "Risk always wants a receipt.",
        ),
        "idioms": (
            "Risk always wants a receipt.",
            "Paper money keeps paper shadows.",
        ),
        "local_terms": (
            "Paper shadow is what follows a bad signature.",
        ),
        "address_terms": (
            "associate",
            "friend",
        ),
    },
    "banker": {
        "register": "official",
        "lead_ins": (
            "For the record,",
            "Practically speaking,",
            "On paper,",
        ),
        "catch_phrases": (
            "Risk always wants a receipt.",
            "Numbers remember what people forget.",
            "Clean books are rarely quiet books.",
        ),
        "idioms": (
            "Numbers remember what people forget.",
            "Risk always wants a receipt.",
        ),
        "local_terms": (
            "Paper shadow is what follows a bad signature.",
        ),
        "address_terms": (
            "associate",
            "friend",
        ),
    },
    "transit_worker": {
        "register": "plain",
        "catch_phrases": (
            "Routes remember delays.",
            "Schedules are promises with weather in them.",
            "Every platform has a mood.",
        ),
        "idioms": (
            "Platform talk moves in loops.",
            "Routewash makes clean stories muddy.",
        ),
        "local_terms": (
            "Routewash is what happens when a story rides too many lines.",
        ),
        "address_terms": (
            "friend",
            "traveler",
        ),
    },
    "rail_worker": {
        "register": "plain",
        "catch_phrases": (
            "Rail time is honest until people touch it.",
            "Platforms remember who waited too long.",
            "A late train makes every story bigger.",
        ),
        "idioms": (
            "Tracktalk runs ahead of the train.",
            "A clean platform is still listening.",
        ),
        "local_terms": (
            "Tracktalk means the version that arrives before the train does.",
        ),
        "address_terms": (
            "friend",
            "traveler",
        ),
    },
}


REGISTER_STYLE_HINTS = {
    "plain": {
        "lead_ins": (),
        "address_terms": (),
        "farewell_tags": (),
        "usage_weights": {
            "lead_in": 0.35,
            "address": 0.55,
        },
    },
    "warm": {
        "lead_ins": (
            "Honestly,",
            "Look,",
            "Truth is,",
            "Between us,",
            "Okay..",
        ),
        "address_terms": (
            "friend",
            "neighbor",
            "hun",
            "my dear",
            "youngster",
        ),
        "usage_weights": {
            "lead_in": 0.75,
            "address": 0.85,
            "idiom": 0.3,
        },
    },
    "clipped": {
        "lead_ins": (
            "Right,",
            "Fine,",
            "Alright,",
            "Simply put,",
        ),
        "address_terms": (),
        "usage_weights": {
            "lead_in": 0.9,
            "address": 0.15,
            "local_term": 0.05,
        },
    },
    "official": {
        "lead_ins": (
            "For the record,",
            "Listen,",
            "Heads up,",
            "Simply put,",
            "Not to be vague,",
        ),
        "address_terms": (
            "citizen",
            "friend",
        ),
        "usage_weights": {
            "lead_in": 1.1,
            "address": 0.65,
            "idiom": 0.2,
            "local_term": 0.08,
        },
    },
    "rough": {
        "lead_ins": (
            "Straight up,",
            "Look,",
            "Real talk,",
            "Honest answer,",
            "Between you and me,",
        ),
        "address_terms": (
            "friend",
            "pal",
            "bud",
        ),
        "usage_weights": {
            "lead_in": 1.0,
            "address": 0.8,
            "idiom": 0.45,
            "local_term": 0.2,
        },
    },
    "theatrical": {
        "lead_ins": (
            "Honestly,",
            "Look,",
            "Truth is,",
            "Between us,",
            "Let me be direct,",
        ),
        "address_terms": (
            "friend",
            "dear",
        ),
        "usage_weights": {
            "lead_in": 1.0,
            "address": 0.75,
            "idiom": 0.65,
            "local_term": 0.25,
        },
    },
}


VOICE_QUALITY_PROFILES = {
    "spare": {
        "descriptor": "spare",
        "usage_weights": {
            "lead_in": 0.25,
            "address": 0.35,
            "catch": 1.0,
            "idiom": 0.04,
            "local_term": 0.01,
            "farewell": 0.8,
            "quiet": 1.35,
        },
    },
    "ordinary": {
        "descriptor": "ordinary",
        "usage_weights": {
            "lead_in": 0.65,
            "address": 0.65,
            "catch": 1.0,
            "idiom": 0.18,
            "local_term": 0.06,
            "farewell": 1.0,
            "quiet": 0.75,
        },
    },
    "local": {
        "descriptor": "local",
        "usage_weights": {
            "lead_in": 0.85,
            "address": 0.75,
            "catch": 0.9,
            "idiom": 0.45,
            "local_term": 0.18,
            "farewell": 1.0,
            "quiet": 0.35,
        },
    },
    "colorful": {
        "descriptor": "colorful",
        "usage_weights": {
            "lead_in": 0.95,
            "address": 0.8,
            "catch": 0.75,
            "idiom": 0.85,
            "local_term": 0.32,
            "farewell": 1.0,
            "quiet": 0.18,
        },
    },
}


VOICE_QUALITY_ORDER = ("spare", "ordinary", "local", "colorful")


STYLE_LEAD_IN_BANKS = {
    "greet_guarded",
    "history",
    "organization",
    "supervisor",
    "coworkers",
    "people",
    "chatter_offense",
    "chatter_world_trait",
    "chatter_security",
    "chatter_supervisor",
    "chatter_schedule",
    "chatter_shift",
    "chatter_opportunity",
    "chatter_illegal_goods",
    "chatter_check_in",
    "chatter_actor_reputation",
    "chatter_conflict_side",
    "opportunities",
    "fallout",
    "objective",
    "angle",
    "risk",
    "attention",
    "weird_soft",
    "weird_wary",
    "weird_fail",
    "pry_soft",
    "pry_wary",
    "pry_fail",
    "insult_soft",
    "insult_wary",
    "insult_fail",
    "routine",
    "security",
    "access",
    "entry",
    "keyholder",
    "weak_point",
    "purpose_defuse",
    "purpose_wary",
    "purpose_fail",
    "apologize_defuse",
    "apologize_wary",
    "apologize_fail",
    "leave_defuse",
    "leave_wary",
    "leave_fail",
    "local_rumor",
    "local_opportunity",
    "local_other_bond",
    "social_knowledge",
    "social_knowledge_incident",
    "social_knowledge_business",
    "social_knowledge_opportunity",
    "social_knowledge_relationship",
    "social_knowledge_none",
    "concern",
    "detail_rumor",
    "detail_opportunity",
}


STYLE_CATCH_BANKS = {
    "greet_guarded",
    "greet_wary",
    "greet_neutral",
    "greet_friendly",
    "greet_introduced",
    "history",
    "organization",
    "supervisor",
    "coworkers",
    "people",
    "chatter_offense",
    "chatter_world_trait",
    "chatter_security",
    "chatter_supervisor",
    "chatter_schedule",
    "chatter_shift",
    "chatter_opportunity",
    "chatter_illegal_goods",
    "chatter_check_in",
    "chatter_actor_reputation",
    "chatter_conflict_side",
    "opportunities",
    "fallout",
    "objective",
    "angle",
    "risk",
    "attention",
    "weird_soft",
    "weird_wary",
    "weird_fail",
    "pry_soft",
    "pry_wary",
    "pry_fail",
    "insult_soft",
    "insult_wary",
    "insult_fail",
    "routine",
    "security",
    "access",
    "entry",
    "keyholder",
    "weak_point",
    "purpose_defuse",
    "purpose_wary",
    "purpose_fail",
    "apologize_defuse",
    "apologize_wary",
    "apologize_fail",
    "leave_defuse",
    "leave_wary",
    "leave_fail",
    "local_rumor",
    "local_opportunity",
    "local_other_bond",
    "social_knowledge",
    "social_knowledge_incident",
    "social_knowledge_business",
    "social_knowledge_opportunity",
    "social_knowledge_relationship",
    "social_knowledge_none",
    "concern",
    "detail_rumor",
    "detail_opportunity",
}


STYLE_SOFT_TEXTURE_BANKS = {
    "greet_guarded",
    "greet_wary",
    "greet_neutral",
    "greet_friendly",
    "greet_introduced",
}


STYLE_ADDRESS_BANKS = {
    "contacts_offer",
    "contacts_repeat",
    "contacts_person_hint",
    "contacts_person_repeat",
    "introduction_offer",
    "introduction_repeat",
    "contacts_offer_caution",
    "contacts_offer_caution_guard",
    "contacts_offer_caution_worker",
    "contacts_offer_caution_merchant",
    "contacts_offer_caution_neighbor",
    "contacts_offer_caution_chaotic",
    "introduction_offer_caution",
    "vouch_offer",
    "vouch_repeat",
    "vouch_offer_caution",
    "vouch_offer_caution_guard",
    "vouch_offer_caution_worker",
    "vouch_offer_caution_merchant",
    "vouch_offer_caution_neighbor",
    "vouch_offer_caution_chaotic",
    "trade_yes_caution",
    "trade_yes_caution_merchant",
    "trade_yes_caution_chaotic",
    "farewell",
    "payoff_accept",
    "payoff_refuse_broke",
    "payoff_refuse_clean",
    "payoff_cooldown",
    "fence_accept",
    "fence_decline_corrupt",
    "fence_decline_clean",
    "fence_cooldown",
    "hire_runner_accept",
    "hire_runner_decline_clean",
    "hire_runner_decline_broke",
    "hire_runner_already_hired",
}


DIALOGUE_BANKS = {
    "greet_guarded": (
        "Keep it short.",
        "Talk fast. You are pushing it.",
        "Make it quick.",
        "Say what you came to say.",
        "You have about a minute before this gets old.",
        "Do not dress it up. What do you want?",
        "You have a question, ask it.",
        "I haven't shot you yet, so go on.",
        "You are already on the wrong side of my patience.",
        "Start with the useful part.",
        "No wandering around the point. Speak.",
        "This is not friendly time. What do you need?",
        "Keep this clean and I will listen.",
    ),
    "greet_wary": (
        "Yeah?",
        "Need something?",
        "You looking for something?",
        "Alright. What is it?",
        "I am listening.",
        "Okay. What is going on?",
        "Go ahead. I am keeping this short.",
        "You have my attention for a minute.",
        "Tell me what you need.",
        "Careful start, but I am listening.",
        "Is this quick?",
        "Say it plain and we will see.",
        "Alright, talk to me.",
        "I can spare a second. What are you after?",
        "Let us hear the ask.",
        "Where should we start?",
        "I can listen for a minute.",
        "No rush, just say it straight.",
        "What do you need from me?",
    ),
    "greet_neutral": (
        "Sure. What do you need?",
        "Yeah, go on.",
        "What can I do for you?",
        "You wanted something?",
        "Fair enough. What is on your mind?",
        "Yeah? Go ahead.",
        "I have a minute. What are you after?",
        "Ask your question.",
        "Alright. What are we looking at?",
        "I can talk. Start where it matters.",
    ),
    "greet_friendly": (
        "Hey. What is up?",
        "Sure thing. What is on your mind?",
        "Good to see you. Need anything?",
        "Yeah, talk to me.",
        "You caught me in a decent mood. What are we talking about?",
        "Alright, I am here. Where do you want to start?",
        "Hey. I can spare a minute for you.",
        "Good timing. What are we looking at?",
        "Yeah, I have got you. What do you need?",
        "Alright. Let us pick this up properly.",
    ),
    "greet_introduced": (
        "If {intro_source_name} pointed you my way, I can spare a minute.",
        "{intro_source_name} mentioned you. Go on.",
        "Alright. If {intro_source_name} sent you, let us hear it.",
        "{intro_source_name} does not send people lightly. What is on your mind?",
        "You came through {intro_source_name}? Then I am listening.",
    ),
    "name_first": (
        "I am {npc_name}.",
        "Name's {npc_name}.",
        "People call me {npc_name}.",
        "{npc_name}. That is me.",
        "You can call me {npc_name}.",
        "{npc_name}, if you are keeping track.",
    ),
    "name_repeat": (
        "Still {npc_name}.",
        "Same answer: {npc_name}.",
        "{npc_name}, unless I missed something.",
        "You already asked. It is {npc_name}.",
        "The name has not changed on me yet: {npc_name}.",
    ),
    "name_guarded": (
        "{npc_name}. That is enough for now.",
        "It is {npc_name}. Keep moving.",
        "{npc_name}. Do not make this strange.",
        "{npc_name}. Do not spend it like we are friends yet.",
    ),
    "history": (
        "{history_summary}",
        "Long story short? {history_summary}",
        "Around here? Yeah, {history_summary}",
        "If you want the short version, {history_summary}",
        "The clean version is this: {history_summary}",
        "If you are asking how this place settled on me, {history_summary}",
    ),
    "history_none": (
        "Long enough to recognize the regulars.",
        "A while. Enough to know the rhythm.",
        "Long enough that new faces stand out.",
        "Long enough to know which stories get better when left alone.",
        "Not long enough to own the place, long enough to know when it shifts.",
    ),
    "job_first": (
        "I work as {career_text}.",
        "Mostly {career_text} work.",
        "Most days I am on {career_text} duty.",
        "{career_text} work keeps the lights on.",
    ),
    "job_repeat": (
        "Still {career_text}.",
        "No career change since a minute ago. {career_text}.",
        "Same job: {career_text}.",
        "Same work, same aches: {career_text}.",
    ),
    "job_none": (
        "Nothing tidy enough to put on a sign.",
        "Odd jobs, mostly.",
        "A little of whatever keeps me moving.",
        "Nothing official worth bragging about.",
        "Whatever pays before it turns into a problem.",
        "I keep my name off most schedules.",
    ),
    "routine": (
        "{routine_summary}",
        "Most days? {routine_summary}",
        "Usually, {routine_summary}",
        "Depends on the day, but {routine_summary}",
    ),
    "routine_none": (
        "Nothing steady enough to map out.",
        "No clean routine worth naming.",
        "It changes too much to call it a routine.",
        "My day is mostly errands wearing different hats.",
        "If I make a plan, the block usually laughs first.",
    ),
    "workplace_first": (
        "You can usually find me at {workplace_name}.",
        "I am tied to {workplace_name} most days.",
        "Mostly {workplace_name}. That is my place.",
        "I work out of {workplace_name}.",
    ),
    "workplace_here": (
        "Right here, at {workplace_name}.",
        "This place. {workplace_name}.",
        "Here. {workplace_name} keeps me busy.",
    ),
    "workplace_repeat": (
        "Still {workplace_name}.",
        "Same place as before: {workplace_name}.",
        "I already told you, {workplace_name}.",
        "Unless the building wandered off, {workplace_name}.",
    ),
    "workplace_none": (
        "No fixed place right now.",
        "Nowhere steady enough to point to.",
        "I drift more than I clock in.",
        "No counter, no locker, no chair with my name on it.",
        "I work where the day leaves me standing.",
    ),
    "organization": (
        "{organization_summary}",
        "Work-wise? {organization_summary}",
        "Officially, {organization_summary}",
        "As far as the job goes, {organization_summary}",
    ),
    "organization_none": (
        "Nothing formal enough to pin a name on.",
        "No banner over my head worth repeating.",
        "Nobody organized enough to call it a proper outfit.",
        "No letterhead. No patch. Just people asking for things.",
        "If there is an outfit, nobody gave me the shirt.",
    ),
    "corporate_presence_member": (
        "{corporate_presence_read} I work inside that reach, so I see the useful side of it too.",
        "{corporate_presence_read} From inside the outfit, it feels more ordinary than the street makes it sound.",
        "{corporate_presence_read} That is real, but so are the shifts and stocked counters behind the signs.",
        "{corporate_presence_read} They call it consistency. People outside the company use sharper words.",
    ),
    "corporate_presence_conflicted": (
        "{corporate_presence_read} Some people call that stability. Some call it a hand around the block's throat.",
        "{corporate_presence_read} It solves enough daily problems that people tolerate what comes attached.",
        "{corporate_presence_read} The useful part and the ugly part arrived in the same trucks.",
        "{corporate_presence_read} Nobody agrees whether that counts as improvement, but everybody adjusts to it.",
    ),
    "corporate_presence_critical": (
        "{corporate_presence_read} They make the block depend on them, then point at the dependence as proof they belong.",
        "{corporate_presence_read} The signs came first. The pressure behind them took longer to show.",
        "{corporate_presence_read} It looks tidy until you ask what happened to the choices that used to be here.",
        "{corporate_presence_read} They are buying convenience with everybody else's room to refuse.",
    ),
    "corporate_pull_loyal": (
        "{corporate_benefit} That kind of reliability is why people sign on.",
        "{corporate_benefit} You can sneer at the logo after your shift still pays.",
        "{corporate_benefit} For plenty of people, that is not a sales pitch. It is the practical answer.",
        "{corporate_benefit} It is easier to judge the bargain when you are not the one who needs it.",
    ),
    "corporate_pull_conflicted": (
        "{corporate_benefit} I understand why people take the offer, even knowing what comes with it.",
        "The honest pitch? {corporate_benefit_lc} That solves a real problem for people.",
        "{corporate_benefit} Useful is not the same as harmless, but it is still useful.",
        "{corporate_benefit} That is how they get more than fear out of a neighborhood.",
    ),
    "corporate_pull_critical": (
        "If you want the part that works, {corporate_benefit_lc} I cannot blame people for needing that.",
        "{corporate_benefit} A trap works better when the bait is something people genuinely need.",
        "{corporate_benefit} That is a real advantage, even if I hate who gets to ration it.",
        "People go because {corporate_benefit_lc} The logo does not make that need imaginary.",
    ),
    "corporate_cost_loyal": (
        "{corporate_cost} I will not pretend that never lands hard, but the rules are not hidden.",
        "The hard edge is this: {corporate_cost_lc} People decide whether the rest is worth it.",
        "{corporate_cost} That is the trade, not some secret rot I can expose for you.",
        "{corporate_cost} I think the order is worth the edge, but I know where the edge is.",
    ),
    "corporate_cost_conflicted": (
        "The part they leave out is simple: {corporate_cost_lc}",
        "{corporate_cost} You feel that part after the convenient pieces have already settled in.",
        "{corporate_cost} Most people notice it. Fewer can afford to do anything about it.",
        "The bargain turns when {corporate_cost_lc}",
    ),
    "corporate_cost_critical": (
        "{corporate_cost} That is not an accident. It is how the grip tightens.",
        "Start with this: {corporate_cost_lc} Then ask who still gets a real choice.",
        "{corporate_cost} They call the result efficiency once nobody can afford to refuse it.",
        "The clean signs hide the dirty part: {corporate_cost_lc}",
    ),
    "cult_member": (
        "{cult_name} asks for {cult_devotion}. Dress is {cult_uniform}. Meetings are not for every passerby.",
        "The circle keeps to {cult_devotion}. If you wear {cult_uniform}, they expect you to mean it.",
        "{cult_name} is not a shop sign. It is people, dress, meetings, and consequences.",
        "You can call it strange if you want. Around us it means {cult_devotion}, and the clothes say who is inside.",
        "If you are looking at the colors, you are seeing the easy part. The hard part is keeping the code.",
    ),
    "cult_official": (
        "{cult_name} keeps {cult_devotion}. I can explain membership, donations, clothing, and when the circle meets.",
        "We do not drag anyone in. We count people who choose the code and keep the dress.",
        "Membership has a shape: {cult_uniform}, {cult_devotion}, and no pretending betrayal is just weather.",
        "I speak for the circle here. The leader is not a counter service.",
        "If you want the door opened, start with the code and the clothing. The rest comes slower.",
    ),
    "cult_shunned": (
        "{cult_name} is not open to you.",
        "The circle already carried your name. No business.",
        "You are outside the door now. That is the whole answer.",
        "No sale, no meeting, no audience. Walk clear.",
    ),
    "cult_unknown": (
        "People gather. People dress alike. That is all I am saying.",
        "If there is a circle here, it has not opened itself to me.",
        "I see the colors too. I do not know what they mean.",
        "Ask someone wearing the mark if they want to be asked.",
    ),
    "supervisor": (
        "{supervisor_summary}",
        "If you mean chain of command, {supervisor_summary}",
        "Most days, {supervisor_summary}",
    ),
    "supervisor_none": (
        "Nobody steady enough to point to.",
        "Depends on the day more than the title.",
        "No single boss worth hanging the answer on.",
        "Whoever is loudest is not always the one in charge.",
        "The chain of command is more chain than command.",
    ),
    "coworkers": (
        "{coworker_summary}",
        "Most days? {coworker_summary}",
        "Around the shift, {coworker_summary}",
    ),
    "coworkers_none": (
        "Nobody steady enough to name.",
        "No real crew to speak of.",
        "Not a regular enough bunch to call them coworkers.",
        "Faces rotate too fast for me to hand you a roster.",
        "If there is a crew, it changes before you learn the jokes.",
    ),
    "people": (
        "{people_summary}",
        "If you are looking for names, {people_summary}",
        "If you want a place to start, {people_summary}",
        "Names worth keeping? {people_summary}",
        "If you are trying to get a read on people, {people_summary}",
    ),
    "where_place": (
        "{place_location_summary}",
        "If you need it plain, {place_location_summary_lc}",
        "For finding it? {place_location_summary_lc}",
    ),
    "where_place_none": (
        "Nothing concrete enough to point at yet.",
        "I do not have a clean place to put on the map for you.",
        "Not enough there for me to point you anywhere real.",
        "I would be guessing, and bad directions get expensive fast.",
    ),
    "people_none": (
        "No one I would point you at just yet.",
        "Nobody I feel like handing over cold.",
        "It wouldn't make sense for me to stick my neck out when your name keeps popping up on the wrong side of reports.",
        "Not a clean name worth passing along from me right now.",
        "Ask again when your face has less weather on it.",
        "There are names, sure. None I am spending on this conversation yet.",
    ),
    "chatter_offense": (
        "You hear about {trouble_summary}?",
        "Word is there was trouble at {topic_place}.",
        "People keep talking about {trouble_summary}.",
        "Something went down at {topic_place}. People are still edgy about it.",
        "There was a thing with {trouble_summary}. Nerved a few people up.",
        "Everybody keeps lowering their voice around {topic_place}. Sounds like {trouble_summary}.",
        "{trouble_summary} is the version people keep repeating. I do not know if it got cleaner with travel.",
        "The room gets smaller when {topic_place} comes up. People say {trouble_summary}.",
        "Nobody wants to be the first to say {trouble_summary}, but that is where the talk keeps landing.",
    ),
    "chatter_world_trait": (
        "People keep saying {trait_claim}.",
        "I keep hearing that {trait_claim_lc}",
        "Whole block is repeating that {trait_claim_lc}",
        "{trait_claim} is the word going around.",
        "Everyone has an opinion about {trait_claim_lc}",
        "The current story is {trait_claim_lc}",
        "People are acting like {trait_claim_lc} explains more than it probably does.",
    ),
    "chatter_security": (
        "{topic_place} runs {security_summary}.",
        "If you are wondering, {topic_place} runs {security_summary}.",
        "Everyone around there knows {security_summary_lc}",
        "Security around {topic_place}: {security_summary}.",
        "Place like {topic_place} does not take chances. {security_summary}.",
        "{topic_place} is not casual about the door. {security_summary}.",
        "The thing about {topic_place}: {security_summary_lc}",
    ),
    "chatter_supervisor": (
        "{supervisor_name} is the one really running {topic_place}.",
        "Far as I can tell, {supervisor_name} runs {topic_place}.",
        "{supervisor_name} keeps the floor at {topic_place} moving.",
        "If you want the real authority at {topic_place}, look at {supervisor_name}.",
        "Ask around {topic_place} and {supervisor_name} is the name that comes up.",
        "When {topic_place} gets tense, people look toward {supervisor_name}.",
        "{supervisor_name} is the name people use when they stop pretending it is everyone's decision.",
    ),
    "chatter_schedule": (
        "{topic_place} usually runs {schedule_text}.",
        "Most days, {topic_place} keeps {schedule_text}.",
        "If the doors move on time, {topic_place} runs {schedule_text}.",
        "Schedule around {topic_place} tends to be {schedule_text}.",
        "{topic_place} keeps regular hours: {schedule_text}.",
        "{topic_place} has a rhythm to it: {schedule_text}.",
        "If you are timing {topic_place}, start with {schedule_text}.",
    ),
    "chatter_shift": (
        "Staff shift at {topic_place} usually runs {schedule_text}.",
        "Most days, the shift at {topic_place} is {schedule_text}.",
        "If payroll lands on time, staff at {topic_place} work {schedule_text}.",
        "The shift around {topic_place} tends to be {schedule_text}.",
        "People on that floor at {topic_place} are usually on {schedule_text}.",
        "{topic_place} has bodies moving on {schedule_text}, give or take the usual excuses.",
        "The floor at {topic_place} wakes and clears around {schedule_text}.",
    ),
    "chatter_opportunity": (
        "{opportunity_title} sounds live {distance_phrase}. {opportunity_summary}",
        "Word is {opportunity_title} is {distance_phrase}. {opportunity_summary}",
        "People keep pointing toward {opportunity_title} {distance_phrase}. {opportunity_summary}",
        "Best street lead I heard is {opportunity_title} {distance_phrase}. {opportunity_summary}",
        "{opportunity_title} is the one people still mention {distance_phrase}. {opportunity_summary}",
        "If anything has a pulse, it is {opportunity_title} {distance_phrase}. {opportunity_summary}",
        "The talk keeps bending back to {opportunity_title} {distance_phrase}. {opportunity_summary}",
        "{opportunity_title} has not gone cold yet {distance_phrase}. {opportunity_summary}",
    ),
    "chatter_illegal_goods": (
        "If you want hot goods, {topic_place} is where people look.",
        "Word is {topic_place} moves the kind of stock nobody lists openly.",
        "People say {topic_place} can find things that never make the front counter.",
        "If someone needs quiet merchandise, they drift toward {topic_place}.",
        "{topic_place} has a reputation for back-counter goods.",
        "{topic_place} gets mentioned when people stop saying item names out loud.",
        "Quiet stock has a way of orbiting {topic_place}.",
    ),
    "chatter_check_in": (
        "How are things at {topic_place} these days?",
        "Everything holding together around {topic_place}?",
        "How is {topic_place} treating you lately?",
        "What is the mood like over at {topic_place}?",
        "Any word on what is happening at {topic_place}?",
        "{topic_place} still steady, or is it starting to tilt?",
        "People still smiling at {topic_place}, or just showing teeth?",
    ),
    "chatter_actor_reputation": (
        "Word on {actor_name}: {reputation_read_lc}",
        "Around here, {actor_name} keeps coming up. {reputation_read}",
        "I keep hearing the same thing about {actor_name}: {reputation_read_lc}",
        "People keep bringing up {actor_name}. {reputation_read}",
        "{actor_name} is the name in half the talk lately. {reputation_read}",
        "{actor_name} has become a shorthand around here. {reputation_read}",
        "The way people say {actor_name} tells you plenty. {reputation_read}",
    ),
    "chatter_conflict_side": (
        "Word is {conflict_summary_lc}",
        "People keep saying {conflict_summary_lc}",
        "Every version of that story ends the same way: {conflict_summary_lc}",
        "If it goes loud again, {conflict_summary_lc}",
        "The room keeps leaning one way on that: {conflict_summary_lc}",
        "Nobody says it first, but everybody lands there: {conflict_summary_lc}",
        "The quiet read is this: {conflict_summary_lc}",
    ),
    "services": (
        "Mostly {service_summary}.",
        "{service_summary_cap} is what people come here for.",
        "Around there? {service_summary_cap}.",
    ),
    "services_none": (
        "Nothing special. People come and go.",
        "No big secret. It is just a place to be.",
        "Depends on the day more than the sign.",
        "The sign promises more than the room delivers.",
        "Mostly it is a place where people wait for better options.",
    ),
    "service_locator": (
        "For {service_label}? {service_locator_summary}",
        "{service_locator_summary}",
        "If you are after {service_label}, {service_locator_summary_lc}",
    ),
    "service_locator_none": (
        "No clean {service_label} lead from me right now.",
        "Nothing nearby I trust pointing you toward for {service_label}.",
        "If there is {service_label} close, I do not have the name for it.",
        "No clean {service_label} lead I would put my name behind.",
        "Nothing nearby for {service_label} that I would send you to with a straight face.",
        "I do not have the name for it if {service_label} is closer than the map admits.",
        "I would be guessing on {service_label}, and guesses make bad directions.",
        "{service_label} is not a thread I can pull cleanly from here.",
        "No one close enough for {service_label} that I would call reliable.",
        "I hear scraps about {service_label}, not a door I would send you through.",
    ),
    "hours": (
        "Usually {hours_text}.",
        "Most days, {hours_text}.",
        "If the schedule holds, {hours_text}.",
    ),
    "hours_none": (
        "Depends on who is around to open up.",
        "No clean schedule I would trust.",
        "Hard to pin down. It shifts.",
        "They open like people who hate being predictable.",
        "If there is a schedule, it is losing the argument.",
    ),
    "owner_named": (
        "{owner_name} runs it.",
        "That place answers to {owner_name}.",
        "{owner_name} is the one in charge.",
    ),
    "owner_founder": (
        "Folks still tie it back to {owner_name}.",
        "It was built around {owner_name}, more or less.",
        "Around here it is still {owner_name}'s place in spirit.",
    ),
    "owner_tag": (
        "It is city-run, more or less.",
        "City people keep a hand in it.",
        "It belongs to the city side of things.",
    ),
    "owner_none": (
        "No single face to point at.",
        "Hard to say. It is more of a shared place.",
        "Nobody obvious owns the room from where I stand.",
        "Ownership is foggy enough that everyone points somewhere else.",
        "If someone owns it, they let other people take the blame.",
    ),
    "security": (
        "{security_summary}",
        "From what I see, {security_summary}",
        "If you are asking me, {security_summary}",
        "That place? {security_summary}",
        "The practical read is this: {security_summary_lc}",
        "If you are reading the door, start here: {security_summary_lc}",
    ),
    "security_none": (
        "Nothing sharper than an ordinary lock.",
        "No special security worth mentioning.",
        "About what you would expect from an ordinary place.",
        "Mostly habit and a door that complains when it closes.",
        "No system, just a little caution and whatever patience is on shift.",
    ),
    "access": (
        "{access_summary}",
        "As far as access goes, {access_summary}",
        "Door-wise? {access_summary}",
        "If you are asking about the threshold, {access_summary}",
    ),
    "access_none": (
        "Nothing stranger than an ordinary door.",
        "No trickier than the usual threshold.",
        "It is not complicated enough to make a speech about.",
        "Walk in when it is open, look suspicious when it is not.",
        "The door is the whole theory, far as I can tell.",
    ),
    "entry": (
        "{entry_summary}",
        "If you are mapping it out, {entry_summary}",
        "From the outside? {entry_summary}",
    ),
    "entry_none": (
        "Just the ordinary way in, from what I know.",
        "Nothing cleverer than the front way.",
        "No side route worth hanging your hopes on.",
        "If there is a smarter entrance, nobody smart told me.",
        "Front way, public face, no magic trick.",
    ),
    "keyholder": (
        "{keyholder_summary}",
        "For access? {keyholder_summary}",
        "If you mean who carries it, {keyholder_summary}",
    ),
    "keyholder_none": (
        "Nobody local enough to name.",
        "No clear hand on it that I would trust telling you about.",
        "Hard to pin that down cleanly.",
        "Keys pass around quietly; I am not guessing for you.",
        "The people with access are not advertising it.",
    ),
    "weak_point": (
        "{weak_point_summary}",
        "If there is a soft seam, {weak_point_summary_lc}",
        "The place bends here: {weak_point_summary_lc}",
        "What gives first? {weak_point_summary_lc}",
    ),
    "weak_point_none": (
        "No weak point I would bet on from here.",
        "Nothing soft enough to call it a real seam.",
        "If there is a gap, I do not know it cleanly enough to name.",
        "Nothing I would call a crack without standing closer.",
        "It may bend somewhere, but I am not selling you a guess.",
    ),
    "purpose_defuse": (
        "Fine. Keep it quick and keep it clean.",
        "Alright. Then do not give me another reason to stop you.",
        "Maybe. Stay straight and we are done here.",
        "Fine. You get a short leash and a shorter conversation.",
        "Alright. Act like you know where the line is.",
    ),
    "purpose_wary": (
        "Maybe. I am still watching you.",
        "Could be. I still do not like it.",
        "I hear you. I am not convinced.",
        "That story has room in it. I am watching the room.",
        "Maybe. Do not mistake that for comfort.",
    ),
    "purpose_fail": (
        "I am not buying that.",
        "That is not good enough.",
        "No. Try a better story somewhere else.",
        "That answer is too thin for where you are standing.",
        "No. You dressed that up and it still came out wrong.",
    ),
    "apologize_defuse": (
        "Fine. Do not make it a pattern.",
        "Alright. Then clean it up and move on.",
        "I will let that sit, once. Do not press it.",
        "Fine. Fix your feet and make this the last time.",
        "Alright. Mistakes happen. Repeats become choices.",
    ),
    "apologize_wary": (
        "Words are cheap. I am still watching you.",
        "Maybe you mean it. I am still keeping an eye on you.",
        "Fine. I am not relaxed about it.",
        "Apology noted. Trust not restored.",
        "I hear the sorry. I am still counting exits.",
    ),
    "apologize_fail": (
        "Save it. You already crossed the line.",
        "Too late for a soft apology.",
        "No. You do not get to smooth it over that easily.",
        "No. That apology arrived after the damage.",
        "Too neat. I do not trust neat after trouble.",
    ),
    "leave_defuse": (
        "Good. Clear out and we are done.",
        "Then go. We can leave it there.",
        "Fine. Move along and let that be the end of it.",
        "Good. Give the place some distance and we can all breathe.",
        "Fine. Walk away clean and this stays small.",
    ),
    "leave_wary": (
        "Do that. Quickly.",
        "Good. Start moving.",
        "Then move, and do not make me ask twice.",
        "Feet first, explanation never.",
        "Good. Keep going until this is boring again.",
    ),
    "leave_fail": (
        "You should have done that before I had to say it.",
        "Now you are just behind the count.",
        "Move, before this gets worse.",
        "Too slow. Now I have to treat it like a choice.",
        "You are past polite exits. Move.",
    ),
    "local_rumor": (
        "{rumor_line}",
        "{rumor_line}",
        "If you ask me, {rumor_line_lc}",
        "The version I heard goes like this: {rumor_line_lc}",
        "Do not carve it in stone, but {rumor_line_lc}",
    ),
    "local_opportunity": (
        "{opportunity_summary}",
        "Word around here is: {opportunity_summary}",
        "There is something worth knowing. {opportunity_summary}",
        "Something circulating locally. {opportunity_summary}",
        "The useful noise says this: {opportunity_summary}",
        "If you need a thread, take this one: {opportunity_summary}",
        "The part with a handle on it is this: {opportunity_summary}",
        "I would not call it safe, but it is live: {opportunity_summary}",
    ),
    "local_other_bond": (
        "You should probably talk to {other_name} too.",
        "{other_name} {other_hear} more than I do.",
        "If anyone knows more, it is {other_name}.",
        "{other_name} catches the parts that slip past me.",
        "I would put the next question to {other_name}.",
    ),
    "local_none": (
        "Quiet enough, for the moment.",
        "Nothing clean enough to pass along right now.",
        "Usual street noise. Nothing sharp.",
        "Nothing worth your time from me today.",
        "Slow stretch right now. I would not count on that lasting.",
        "The block is holding its breath, which usually means someone else is moving.",
        "No fresh word, just old grudges changing pockets.",
        "Nothing with a handle on it. Plenty of noise without a door.",
        "No clean signal. Just people watching the usual corners.",
        "Nothing has risen above background trouble yet.",
        "The day is quiet in the way that makes people check twice.",
        "No useful story has separated itself from the static.",
    ),
    "street_talk_local_economy_intro": (
        "I do not have a clean rumor to hand you, but the business weather is readable if that is what you need.",
        "Nothing I would call a street lead. If you mean the local shops, I can give you the broad read.",
        "The useful talk today is mostly business weather. Ask that straight and I can keep it clean.",
        "No sharp gossip from me. The block's money mood is the part I can speak to.",
    ),
    "local_economy_skilled": (
        "From the work side, {local_economy_summary}",
        "If you want the counter read, {local_economy_summary_lc}",
        "Business-wise, {local_economy_summary_lc}",
        "The practical read is this: {local_economy_summary_lc}",
    ),
    "local_economy_familiar": (
        "From being around here, {local_economy_summary_lc}",
        "The local read is this: {local_economy_summary_lc}",
        "I would call it like this: {local_economy_summary_lc}",
        "Broadly, {local_economy_summary_lc}",
    ),
    "local_economy_rumor": (
        "I only have the customer read, but {local_economy_summary_lc}",
        "I would not pretend to know the books, but {local_economy_summary_lc}",
        "Loose read? {local_economy_summary}",
        "From the outside, {local_economy_summary_lc}",
    ),
    "local_economy_none": (
        "I do not know this block well enough to read the businesses cleanly.",
        "That is not my lane. Ask somebody who works a counter here.",
        "I would be guessing, and bad business guesses waste everybody's time.",
        "Not from me. I do not have a clean read on this block's money.",
    ),
    "local_economy_self_interest": (
        "{local_economy_agenda_line}",
        "{local_economy_agenda_line}",
        "{local_economy_agenda_line}",
    ),
    "social_knowledge": (
        "Since it is you: {social_knowledge_summary}",
        "I would not hand this to everyone, but {social_knowledge_summary_lc}",
        "The useful version is this: {social_knowledge_summary_lc}",
        "Keep the source soft. {social_knowledge_summary}",
    ),
    "social_knowledge_incident": (
        "Trouble-wise, {social_knowledge_summary_lc}",
        "People are still turning this over: {social_knowledge_summary_lc}",
        "The messy thing I keep hearing is this: {social_knowledge_summary_lc}",
    ),
    "social_knowledge_business": (
        "Business-wise, {social_knowledge_summary_lc}",
        "If you are reading the room, remember this: {social_knowledge_summary_lc}",
        "The place people keep measuring is this: {social_knowledge_summary_lc}",
    ),
    "social_knowledge_opportunity": (
        "If you want something actionable, {social_knowledge_summary_lc}",
        "The live angle in the noise is this: {social_knowledge_summary_lc}",
        "This is the part you might actually use: {social_knowledge_summary_lc}",
    ),
    "social_knowledge_relationship": (
        "People-wise, {social_knowledge_summary_lc}",
        "The social map says this: {social_knowledge_summary_lc}",
        "If you are tracking who matters to whom, {social_knowledge_summary_lc}",
    ),
    "social_knowledge_none": (
        "Nothing I would hand you as more than loose noise.",
        "No clean street talk I trust enough to put in your ear.",
        "Plenty of chatter, nothing I would make you carry.",
    ),
    "initiative_name": (
        "And you?",
        "So what should I call you?",
        "You got a name too, or are we skipping that part?",
        "Names go both ways, usually.",
        "If I am giving you mine, I should hear yours.",
    ),
    "initiative_history": (
        "You new here, or just trying to get your bearings?",
        "You asking because you plan to stick around?",
        "That curiosity, or are you trying to place me?",
        "You counting years, or just trying to hear how people landed here?",
        "Trying to learn the block, or looking for where it cracked?",
    ),
    "initiative_job": (
        "You asking out of curiosity, or is there a reason?",
        "Why the interest?",
        "That just curiosity, or are you headed somewhere with it?",
        "Work talk usually means somebody needs something done.",
        "You asking what I do, or trying to get a feel for me?",
    ),
    "initiative_workplace": (
        "You looking for me there, or just drawing a map?",
        "That place matter to you for a reason?",
        "You need the location, or just the shape of my day?",
        "People ask about workplaces when they want a door, a face, or a schedule.",
        "You tracking me, or tracking the place?",
    ),
    "initiative_organization": (
        "You keeping score on who answers to who?",
        "That kind of hierarchy matter to you for a reason?",
        "You asking about the outfit, or about me?",
        "Careful with org charts. They bite through paper.",
        "You want the name on the wall or the hand on the lever?",
    ),
    "initiative_people": (
        "You looking for friends, or leverage?",
        "You collecting names, or actually hoping to meet someone?",
        "That you trying to build a circle, or just pull a thread?",
        "Names are not loose change. What are you spending them on?",
        "A person can be a door or a warning. Which are you after?",
    ),
    "initiative_local": (
        "You looking for work, trouble, or directions?",
        "You after a lead, or just getting your bearings?",
        "You trying to get the lay of the block, or is there something specific you need?",
        "Local talk is wide. Narrow it before it cuts you.",
        "This block has plenty of stories. Which kind are you buying?",
    ),
    "initiative_concern": (
        "You trying to stay ahead of trouble, or step into it?",
        "That you being careful, or curious?",
        "Good question. You planning around it?",
        "Trouble is easier to avoid before it has a name.",
        "You asking like someone who expects a problem to move.",
    ),
    "initiative_detail": (
        "You like the useful part, I can respect that.",
        "So you are listening for the part that matters.",
        "Alright. You want the sharp version.",
        "Good. Broad talk is cheap; detail is where it gets expensive.",
        "Fine. You want the piece with a handle on it.",
    ),
    "initiative_opportunities": (
        "You looking for money, leverage, or just a way in?",
        "You after a score, or do you just like hearing the map out loud?",
        "That you planning something, or just taking the temperature?",
        "Opportunities are just problems with better lighting.",
        "You want clean work, quick work, or something nobody admits is work?",
    ),
    "initiative_risk": (
        "You planning something that needs the caution?",
        "Good. Most people ask for the angle and forget the cost.",
        "So you are thinking about how this goes bad first.",
        "That is the question people ask after they have already chosen. Good sign you asked now.",
        "Risk is the part that remembers your name.",
    ),
    "initiative_attention": (
        "Then keep your head down if you can.",
        "Good instinct. Too many people ignore that part.",
        "That is the right question, honestly.",
        "Attention spends faster than money.",
        "If you feel watched, do not make them work to prove it.",
    ),
    "initiative_contacts": (
        "If I point you at someone, are you going to handle it cleanly?",
        "You looking for a real connection, or just another name to lean on?",
        "Depends what you think you are going to do with the introduction.",
        "Contacts are living things. Do not bruise mine.",
        "I need to know whether you build bridges or burn them for warmth.",
    ),
    "initiative_introduction": (
        "Depends what you plan to say when you meet them.",
        "Maybe. That kind of introduction matters.",
        "That depends how clean you mean to keep it.",
        "My name travels with you if I do this.",
        "Introductions are small debts with long legs.",
    ),
    "initiative_services": (
        "You looking for the place, or the kind of people around it?",
        "That you scouting the room, or shopping?",
        "Useful to know the sign before you walk under it.",
        "Services tell you what a block thinks it can survive selling.",
        "Sometimes the service is the front and the front is the service.",
    ),
    "initiative_security": (
        "That question alone tells me you are thinking past the front door.",
        "Most people do not ask that unless they need the real picture.",
        "You are planning carefully, at least.",
        "Security talk has fingerprints on it.",
        "That is not a tourist question.",
    ),
    "initiative_access": (
        "Access is usually the part people underestimate.",
        "That is where places really tell you what they are.",
        "Good. Doors matter more than signs.",
        "Access is where policy turns into metal.",
        "The lock is the honest version of the welcome mat.",
    ),
    "initiative_entry": (
        "There is always the obvious way and the honest way.",
        "People learn a lot from how a place is entered.",
        "That is a better question than most.",
        "Entrances tell you who a place expects and who it fears.",
        "Every extra way in exists because somebody needed it once.",
    ),
    "initiative_weak_point": (
        "Every place pretends not to have one.",
        "Soft spots are easier to talk about than fix.",
        "That is the question owners hate most.",
        "Weak points are usually old compromises with fresh paint.",
        "If a place has a secret, it often starts as maintenance.",
    ),
    "concern": (
        "{concern_summary}",
        "Lately? {concern_summary}",
        "What has my attention is this: {concern_summary}",
        "If something is needling at people, it is this: {concern_summary}",
    ),
    "concern_none": (
        "Nothing sharper than the usual nerves.",
        "Nothing clean enough to call real trouble yet.",
        "Same old low-grade friction, mostly.",
        "Quiet on that front, for now.",
        "Nobody is lighting fires at the moment.",
        "People are tense, but not pointed at one thing yet.",
        "No single problem has climbed above the rest of the static.",
    ),
    "detail_rumor": (
        "{detail_line}",
        "What I heard: {detail_line_lc}",
        "{detail_line}",
    ),
    "detail_opportunity": (
        "Best lead I heard was this: {detail_line}",
        "The useful part is {detail_line_lc}",
        "If you want specifics, {detail_line_lc}",
    ),
    "detail_none": (
        "That is all I have.",
        "No cleaner details than that.",
        "That is the shape of it.",
        "Past that I would just be decorating a guess.",
        "That is where my version runs out of road.",
    ),
    "opportunities": (
        "{opportunity_summary}",
        "Here is what sounds live from where I stand: {opportunity_summary}",
        "One worth noting: {opportunity_summary}",
        "If you are looking around, here is one: {opportunity_summary}",
        "The one with a pulse is this: {opportunity_summary}",
        "If you want something with shape, start here: {opportunity_summary}",
        "The useful opening I can see is this: {opportunity_summary}",
    ),
    "opportunities_none": (
        "Nothing is lining up cleanly right this second.",
        "No clear opening jumps out at me right now.",
        "Not a clean angle worth betting on from here.",
        "Things are too quiet to call anything solid.",
        "Nothing sharp enough to point at from where I stand.",
        "I would not chase anything right now.",
        "No door is open far enough to put your shoulder into it.",
        "Everything I hear is either stale or already spoken for.",
        "Plenty of motion, no handle. Bad time to grab at shadows.",
    ),
    "fallout": (
        "{fallout_summary}",
        "If you want the fallout lane, {fallout_summary_lc}",
        "There is still fallout worth chasing. {fallout_summary}",
        "On the rival side of things, {fallout_summary_lc}",
    ),
    "fallout_none": (
        "Nothing in that lane is still warm enough to trust.",
        "No rival fallout I would point you at right now.",
        "That wake has gone cold from where I stand.",
        "The smoke is there, but the trail has already split three ways.",
        "Whatever broke already got swept under somebody else's rug.",
    ),
    "objective": (
        "{objective_summary}",
        "If you want my read, {objective_summary_lc}",
        "For the shape of this run, {objective_summary_lc}",
        "If this were my problem, {objective_summary_lc}",
    ),
    "objective_none": (
        "Depends what you are chasing.",
        "That is hard to answer without a real direction.",
        "No clean answer there from me.",
        "Point me at the problem and I can maybe point back.",
        "Right now you are asking me to read smoke.",
    ),
    "angle": (
        "{angle_summary}",
        "Where I would push: {angle_summary}",
        "Best first move: {angle_summary}",
        "Starting point: {angle_summary}",
        "First thing I would test: {angle_summary}",
    ),
    "angle_none": (
        "Nothing clean enough to point at first.",
        "No clear lead I would start with.",
        "I do not have a clean first move for you there.",
        "Hard to say where to push without more to go on.",
        "Nothing I would commit to from here.",
        "Every start I can see has mud on it.",
        "I would rather say nothing than aim you at a dead wall.",
    ),
    "risk": (
        "{risk_summary}",
        "Here is the catch. {risk_summary}",
        "Worth knowing. {risk_summary}",
        "Keep this in mind. {risk_summary}",
        "The part that bites is this: {risk_summary}",
    ),
    "risk_none": (
        "Same risk as anything else around here: people, distance, and bad timing.",
        "Nothing sharper than the usual trouble.",
        "No cleaner warning than the obvious one.",
        "Standard risks. Nothing unusual from where I stand.",
        "Watch for the things you always watch for.",
        "If it goes wrong, it will probably be because someone saw more than they admit.",
        "The boring risks are still the ones that get people caught.",
    ),
    "attention": (
        "{attention_summary}",
        "If you want the plain read, {attention_summary_lc}",
        "From where I am standing, {attention_summary_lc}",
        "My honest read: {attention_summary_lc}",
    ),
    "attention_none": (
        "Nothing sharp enough to call real heat yet.",
        "You are not setting the whole block off right now.",
        "No more attention than the usual street noise.",
        "You are reading clean from out here.",
        "Nobody is pointing at you specifically.",
        "You are a face in the stream, not the reason people stop talking.",
        "Right now you are background motion. Keep it that way.",
    ),
    "weird_soft": (
        "That is a strange question, but I have heard worse.",
        "You do ask odd things. I can live with it.",
        "Weird angle, but fine. Keep going.",
    ),
    "weird_wary": (
        "What kind of question is that?",
        "You are making this conversation strange.",
        "That is an odd thing to ask someone cold.",
    ),
    "weird_fail": (
        "No. I am done entertaining that.",
        "That is weird enough that I want this over.",
        "Try that question on someone with more patience.",
    ),
    "pry_soft": (
        "That is personal, but I get what you are fishing for.",
        "You are leaning a bit hard, though I have heard rougher.",
        "Careful. That is close to too personal.",
    ),
    "pry_wary": (
        "That is none of your business.",
        "You are getting nosy now.",
        "You do not know me well enough for that question.",
    ),
    "pry_fail": (
        "Too personal. We are done here.",
        "Back off. That question closes the door.",
        "No. Ask somebody else if you want to pry.",
    ),
    "provoke_soft": (
        "Fine. You wanted the honest version.",
        "Alright. No manners around it, then.",
        "You pulled for a reaction. Listen carefully.",
    ),
    "provoke_wary": (
        "You do not get honesty by trying to start a fight.",
        "Do not mistake restraint for fear of saying it.",
        "You are pushing for something you may not enjoy hearing.",
    ),
    "provoke_fail": (
        "You wanted a reaction. You can have the conversation ending.",
        "Keep pushing for a fight somewhere else.",
        "What I think is that you should leave me alone.",
    ),
    "intimidate_soft": (
        "Fine. Take the answer and leave me out of what comes next.",
        "One answer. Then you get out of my face.",
        "Listen once, because there will not be a second time.",
    ),
    "intimidate_wary": (
        "You do not get to order information out of me.",
        "That tone is buying you nothing but attention.",
        "Careful. You are turning a question into an incident.",
    ),
    "intimidate_fail": (
        "You picked the wrong person to threaten.",
        "No. Now everybody nearby gets to remember your face.",
        "That was a threat. I am treating it like one.",
    ),
    "insult_soft": (
        "Cute. I will pretend you thought that sounded better.",
        "You should be careful with that mouth.",
        "That was cheap. I am letting it pass once.",
    ),
    "insult_wary": (
        "Watch your mouth.",
        "You are closer to a problem than a joke.",
        "You really want to make this uglier?",
    ),
    "insult_fail": (
        "That does it. Conversation over.",
        "Try that tone again and see what happens.",
        "No. You can leave now.",
    ),
    "repeat_soft": (
        "You already asked that.",
        "Same answer as before.",
        "I heard you the first time.",
        "You can turn it around, but it lands in the same place.",
        "That answer has not grown legs since you last asked.",
    ),
    "repeat_wary": (
        "You keep circling the same question.",
        "You are starting to wear this thin.",
        "Ask it again and I am going to stop being polite.",
        "That is the same door with fresh fingerprints on it.",
        "You keep worrying at this like there is a second answer hiding under it.",
    ),
    "repeat_fail": (
        "That is enough. I already answered you.",
        "You keep grinding the same question. We are done.",
        "No. I am not doing this loop with you.",
        "No more circles. Conversation ends there.",
        "You got your answer and then tried to squeeze it. We are finished.",
    ),
    "repeat_bonus": (
        "Alright, the useful part is this: {extra_detail_lc}",
        "If you are going to keep at it, fine: {extra_detail_lc}",
        "Since you keep worrying at it, here is the part that matters: {extra_detail_lc}",
        "There is one sharper piece, and then I am done with this: {extra_detail_lc}",
        "Fine. The part I did not lead with is this: {extra_detail_lc}",
    ),
    "contacts_offer": (
        "Depends what you need, but I can point you at {contact_place}.",
        "If you are trying to get somewhere, start with {contact_place}.",
        "For a local way in, try {contact_place}.",
        "{contact_place} is the place I would test first.",
        "Start with {contact_place}, and listen before you spend my name.",
        "If you can walk in without making it official, {contact_place} is the door.",
        "The cleanest first step I have is {contact_place}. Do not stomp on it.",
    ),
    "contacts_repeat": (
        "Same answer as before: {contact_place}.",
        "Still telling you to start with {contact_place}.",
        "{contact_place} is still my best answer.",
        "I am not improving on {contact_place} by saying it twice.",
    ),
    "contacts_soft_no": (
        "Not yet. I like to know who I am steering people toward.",
        "Maybe later. I do not hand names out cold.",
        "Give it time. I do not spend favors that fast.",
        "I am still figuring out what I think of you.",
        "Ask me again after we have had more time.",
        "Names are easier to give away than earn back. Not yet.",
        "I am not opening my people to a stranger with fresh questions.",
        "Contacts are not loose change. Let me know your shape first.",
        "Not cold. People live on the other end of those names.",
        "I need more than a few questions before I start pointing you at anyone.",
    ),
    "contacts_caution_no": (
        "Not while attention is up. Keep your head down first.",
        "People are noticing enough already. I am not opening another line for you right now.",
        "Cool the heat off first. I am not pointing you at anyone while eyes are up.",
        "Not now. Every new introduction gives the heat another handle.",
    ),
    "contacts_caution_no_guard": (
        "No. Patrol memory is long, and I am not putting another name in your path while the city is keyed up.",
        "Not with this much heat. The next person you touch turns into a report.",
        "No. You are too hot for me to point at someone else cleanly.",
        "No. I am not turning a contact into another patrol note.",
    ),
    "contacts_caution_no_worker": (
        "No. I am not dragging a coworker into this while the floor is already twitchy.",
        "Not on a hot day. I like keeping my job.",
        "No. I am not putting another worker in your orbit while eyes are up.",
        "No. One wrong name and the whole floor starts answering questions.",
    ),
    "contacts_caution_no_merchant": (
        "Not with this kind of attention on you. People remember who was seen talking at the counter.",
        "No. Bad heat turns every introduction into shop gossip.",
        "Cool it down first. I am not sending trouble through my front room.",
        "No. A shop can survive slow business; it cannot survive becoming your meeting place.",
    ),
    "contacts_caution_no_neighbor": (
        "Not on this block. Cool it down first.",
        "No. People around here notice enough already.",
        "Not while the street is talking about you.",
    ),
    "contacts_caution_no_chaotic": (
        "Not with that kind of heat trailing you back here.",
        "No. You are bringing too much watch with you.",
        "Cool off first. I am not feeding a hot line.",
    ),
    "contacts_offer_caution": (
        "Keep it quiet, but try {contact_place}.",
        "I can point you at {contact_place}, just do not make noise about it.",
        "Start with {contact_place}, and keep my name out of your mouth unless you need it.",
        "Keep it quiet and try {contact_place}; if anyone asks, you found it yourself.",
    ),
    "contacts_offer_caution_guard": (
        "If you need a start, try {contact_place}, but keep it clean and do not say I sent you unless you have to.",
        "Start with {contact_place}. Quiet feet, quiet mouth, no scene.",
        "You can try {contact_place}, but do it like you belong there and keep me out of the report.",
    ),
    "contacts_offer_caution_worker": (
        "Try {contact_place}, but keep me out of any supervisor talk.",
        "Start with {contact_place}, just do not make it look like staff chatter.",
        "You can try {contact_place}, but keep it quiet enough that it does not get back upstairs.",
    ),
    "contacts_offer_caution_merchant": (
        "Keep it quiet and make it look like regular business at {contact_place}.",
        "I can point you at {contact_place}; just do not make noise about it at the counter.",
        "Start with {contact_place}, and keep my name out of the shop talk.",
    ),
    "contacts_offer_caution_neighbor": (
        "Try {contact_place}, but keep it off this block.",
        "Start with {contact_place}; just do not let the whole street clock you doing it.",
        "You can try {contact_place}, but keep the noise away from the neighbors.",
    ),
    "contacts_offer_caution_chaotic": (
        "Try {contact_place}, just do not drag the watch back here.",
        "Start with {contact_place} and move quick.",
        "You can try {contact_place}, but keep the trail thin.",
    ),
    "contacts_person_hint": (
        "If you are after a real name, try {contact_name}. {contact_subject_cap} {contact_be} {contact_context}.",
        "You might want {contact_name}. {contact_subject_cap} {contact_be} {contact_context}.",
        "For a person, start with {contact_name}. {contact_subject_cap} {contact_be} {contact_context}.",
        "{contact_name} is the name I would not ignore. {contact_subject_cap} {contact_be} {contact_context}.",
        "You need a face, not just a door: {contact_name}. {contact_subject_cap} {contact_be} {contact_context}.",
    ),
    "contacts_person_repeat": (
        "Same name as before: {contact_name}. {contact_subject_cap} {contact_be} still {contact_context}.",
        "I already gave you the best person I have: {contact_name}.",
        "Still saying {contact_name}. That is where I would start.",
    ),
    "contacts_hard_no": (
        "No.",
        "Not for you.",
        "I am not putting you on anyone right now.",
        "That door stays closed.",
    ),
    "introduction_offer": (
        "Tell {contact_name} I pointed you {contact_possessive_adj} way. {contact_subject_cap} {contact_be} {contact_context}.",
        "Use my name with {contact_name}. {contact_subject_cap} {contact_be} {contact_context}.",
        "If you are going to start somewhere, start with {contact_name}. {contact_subject_cap} {contact_be} {contact_context}.",
        "Tell {contact_name} I said you were worth a minute. {contact_subject_cap} {contact_be} {contact_context}.",
        "I will open the door a crack with {contact_name}. {contact_subject_cap} {contact_be} {contact_context}.",
    ),
    "introduction_repeat": (
        "Same answer: use my name with {contact_name}.",
        "I already pointed you at {contact_name}. Start there.",
        "Still {contact_name}. I meant it the first time.",
    ),
    "introduction_soft_no": (
        "Not yet. I am not comfortable connecting that line.",
        "Maybe later. I am not opening that door this quickly.",
        "Give it time. I am not ready to hand that introduction over.",
        "Not yet. That bridge has my weight on it too.",
        "I need a better read on you before I spend that name.",
    ),
    "introduction_caution_no": (
        "Not with this much attention on you. That kind of introduction sticks.",
        "No. Not until things cool off around you.",
        "I am not connecting you to someone else while the city is still watching.",
    ),
    "introduction_offer_caution": (
        "You can use my name with {contact_name}, but do it quietly. {contact_subject_cap} {contact_be} {contact_context}.",
        "Talk to {contact_name} if you have to, just keep it subtle. {contact_subject_cap} {contact_be} {contact_context}.",
        "I will point you at {contact_name}, but do not burn the line. {contact_subject_cap} {contact_be} {contact_context}.",
        "Use my name with {contact_name}, quietly and once. {contact_subject_cap} {contact_be} {contact_context}.",
    ),
    "vouch_offer": (
        "Tell them {npc_name} said you were alright.",
        "Use my name. It should smooth things a little.",
        "I can put a little weight behind your name there.",
        "I will put my name beside yours, but do not make it wobble.",
        "Tell them I said you can be dealt with.",
    ),
    "vouch_repeat": (
        "My answer did not change. Use my name.",
        "Same deal: tell them I sent you.",
        "I am still willing to vouch there.",
    ),
    "vouch_soft_no": (
        "Not yet. We are not there.",
        "Maybe later, once I trust the shape of you better.",
        "I am not ready to lend my name out yet.",
        "Listen, once I trust you more, I will reconsider. But no.",
        "My name is not loose paper. Not yet.",
        "I am not ready to make your first impression mine.",
        "A vouch is not a wave from across the street. Not yet.",
        "My name travels farther than I do. I am keeping it here for now.",
        "Ask again when I know whether my name comes back clean.",
    ),
    "vouch_caution_no": (
        "Not with this kind of attention on you.",
        "No. My name is not covering heat I did not make.",
        "Cool things down first. I am not staking my name on you while people are watching.",
        "Naw, you *way* too hot.",
    ),
    "vouch_caution_no_guard": (
        "No. I am not staking my name on a hot face while patrols are already looking.",
        "Not now. That kind of favor turns into paperwork when the city is this keyed up.",
        "Cool it down first. I am not pinning my name to active heat.",
    ),
    "vouch_caution_no_worker": (
        "No. That kind of favor gets me called into someone's office.",
        "Not while things are this hot. I am not risking my shift on your name.",
        "Cool it first. I am not burning work trust on active heat.",
    ),
    "vouch_caution_no_merchant": (
        "No. My name is not smoothing over heat at the counter.",
        "Not with this much attention on you. Bad business sticks to a shop.",
        "Cool things down first. I am not tying my trade name to that.",
    ),
    "vouch_caution_no_neighbor": (
        "Not while people around here are already looking your way.",
        "No. I am not hanging my name on block heat.",
        "Cool it down first. I still have to live here.",
    ),
    "vouch_caution_no_chaotic": (
        "Not with that much heat on you. I am not wearing your splash.",
        "No. My name does not cover a trail that hot.",
        "Cool off first. I am not pinning myself to active watch.",
    ),
    "vouch_offer_caution": (
        "You can use my name, but keep the ask small.",
        "I will vouch once, quietly. Do not make me regret it.",
        "Use my name if you need to, just do not turn it into a scene.",
        "Use my name once, quietly, and keep the ask small.",
    ),
    "vouch_offer_caution_guard": (
        "You get one quiet use of my name. Keep it clean and keep it short.",
        "I will vouch once, quietly. Do not make me look twice at it.",
        "Use my name if you need to, but no scene and no extra trouble.",
    ),
    "vouch_offer_caution_worker": (
        "You get one quiet use of my name, and keep me out of trouble at work.",
        "I will vouch once. Keep it small and keep it off the clock.",
        "Use my name if you need to, just do not let it come back through the workplace.",
    ),
    "vouch_offer_caution_merchant": (
        "You can use my name, but keep it looking like ordinary business.",
        "I will vouch once, quietly. Do not turn the counter into a story.",
        "Use my name if you need to, just keep the transaction clean.",
    ),
    "vouch_offer_caution_neighbor": (
        "You get one quiet use of my name. Keep it off the block.",
        "I will vouch once, but neighbor-quiet, understood?",
        "Use my name if you need to, just do not let the whole street hear about it.",
    ),
    "vouch_offer_caution_chaotic": (
        "Use my name once if it buys you a step, but do not drag heat back here.",
        "I will vouch once, quietly. Then you move.",
        "Use my name if you need to, just keep the trail thin.",
    ),
    "trade_yes": (
        "Sure. Let us see what you have got.",
        "Alright, let us do business.",
        "Yeah. Show me the goods.",
        "Fine. Put it where I can see it.",
        "Alright. Prices first, stories never.",
        "Sure. Keep it square and we can both leave clean.",
        "Alright. Hands where I can see them, numbers where I can count them.",
    ),
    "trade_yes_caution": (
        "Fine, but keep it quick.",
        "Alright. Quiet business only.",
        "Yeah, but let us not make this look like a meeting.",
        "Fine. Short deal, low voices.",
        "Alright. No lingering over the merchandise.",
        "Open hands, low voices, fast count.",
        "Fine. Buy, sell, breathe, leave.",
    ),
    "trade_yes_caution_merchant": (
        "Fine. Keep it quick and make it look like shopping.",
        "Alright. Quick counter business, no crowd, no scene.",
        "Yeah, but I am not turning my counter into gossip.",
        "Fine. Keep it counter-clean and shopping-quiet.",
        "Alright. If anyone looks over, this is ordinary shopping.",
        "Keep it shopping-small and counter-quiet.",
        "No gossip, no lingering, no strange stacks on the counter.",
    ),
    "trade_yes_caution_chaotic": (
        "Yeah. Fast hands, short words.",
        "Alright, but move it. I do not hold hot business for long.",
        "Sure. Quick deal, then disappear.",
        "Yeah. Show it, price it, vanish.",
        "Fine. I like hot business cold by the time anyone asks.",
        "Hot deal, cold face. Move.",
        "You get a fast yes. Do not make it slower.",
    ),
    "trade_no": (
        "Not here.",
        "I am not set up to sell anything.",
        "No trade from me right now.",
        "I have nothing on me that wants a price tag.",
        "Wrong pocket, wrong moment.",
        "I am conversation, not inventory.",
        "Nothing I can move across to you today.",
        "No stock, no counter, no deal.",
        "If you are shopping, you found the wrong person.",
        "Nothing I am carrying belongs in a trade window.",
        "No shelf, no till, no sale.",
        "I am not the person with stock today.",
    ),
    "store_buy_policy": (
        "{store_purchase_summary}",
        "For this counter, {store_purchase_summary_lc}",
        "Here, the practical answer is: {store_purchase_summary_lc}",
        "If you are selling to this place, {store_purchase_summary_lc}",
    ),
    "store_buy_policy_no": (
        "I am not on that counter, so I would not trust my answer.",
        "Ask whoever is working the shop. I do not want to misprice their business.",
        "I am not the person who decides what that place takes.",
        "Wrong person for that. The worker at the counter would know.",
    ),
    "contract_offer": (
        "Word came down about a problem that needs handling. {target_description} Keep it quiet and you walk with {reward_hint}.",
        "Between you and me, someone has credits on a name. {target_description} Clean and quiet, that is {reward_hint}.",
        "I have a standing job. {target_description} Nobody asks questions, you collect {reward_hint}.",
        "There is work if you can handle things. {target_description} Score is {reward_hint}.",
        "Someone is paying to have a complication removed. {target_description} Do it right, you earn {reward_hint}.",
        "There is a job with no patience left. {target_description} Keep the trail short and it pays {reward_hint}.",
        "Someone wants a problem made smaller. {target_description} Quiet hands, {reward_hint}.",
        "A name came through with money attached. {target_description} Keep the shape simple and it is {reward_hint}.",
        "This is not public work. {target_description} Finish it without theater and the envelope is {reward_hint}.",
    ),
    "contract_repeat": (
        "Same job, still open. {target_description} Confirm the work for {reward_hint}.",
        "Contract stands. {target_description} You know the rate: {reward_hint}.",
        "Still on offer. {target_description} Get it done, collect {reward_hint}.",
        "Same shadow, same price. {target_description} Bring it back clean for {reward_hint}.",
        "The work has not walked away. {target_description} Rate stays {reward_hint}.",
        "No new poetry on it. {target_description} The number is still {reward_hint}.",
        "Still waiting for someone with steady hands. {target_description} Pay remains {reward_hint}.",
    ),
    "contract_accepted": (
        "Good. No details, no noise. Come back when it is finished.",
        "Smart. Payment is ready when the work is done.",
        "Deal. I do not need a story, just results.",
        "You have my attention. Do not waste it.",
        "Good. Make it look like the city did it to itself.",
        "Fine. Finish it before the story grows teeth.",
        "Accepted. Keep your name out of it, keep my name farther out.",
        "Good. The less anyone can explain later, the better.",
    ),
    "contract_no_contract": (
        "Nothing right now.",
        "No work on offer at the moment.",
        "Check back later. Nothing on the table right now.",
        "No name, no package, no envelope. Quiet board today.",
        "The table is empty. Enjoy that while it lasts.",
        "No quiet money looking for hands today.",
        "Nothing with a price attached that I am willing to say out loud.",
    ),
    "side_job_offer": (
        "Maybe. {side_job_summary} Keep it clean and you walk with {reward_hint}, plus a better name with {favor_target}.",
        "Yeah, one small thing. {side_job_summary} Do it right and it pays {reward_hint}, and {favor_target} remembers it.",
        "There is a quiet errand going. {side_job_summary} Handle it softly and you collect {reward_hint} with a little goodwill attached.",
        "I could use a discreet hand. {side_job_summary} Bring it through without noise and that is {reward_hint}, plus a favor with {favor_target}.",
        "I have something that should stay small. {side_job_summary} Keep it that way and it is {reward_hint}, with {favor_target} warmer to you.",
        "There is an errand with a clean edge if you do not drag it. {side_job_summary} Pay is {reward_hint}, plus favor with {favor_target}.",
        "One useful favor, if you can keep it from becoming a scene. {side_job_summary} That gets you {reward_hint} and standing with {favor_target}.",
        "I need a careful hand, not a loud one. {side_job_summary} Bring it home and you get {reward_hint}, plus {favor_target} owes you a better look.",
    ),
    "side_job_repeat": (
        "Same side job. {side_job_summary} Finish it clean and the rate stays {reward_hint}.",
        "Same errand, still open. {side_job_summary} Reward is still {reward_hint}.",
        "Nothing changed. {side_job_summary} Bring it through quietly and collect {reward_hint}.",
        "Same quiet work. {side_job_summary} Keep it quiet and {reward_hint} still waits.",
        "The errand is still breathing. {side_job_summary} Rate remains {reward_hint}.",
        "Still the same small ask. {side_job_summary} Do it clean and it stays worth {reward_hint}.",
        "You already know the shape. {side_job_summary} Finish it and {reward_hint} is still there.",
    ),
    "side_job_accepted": (
        "I am marking it for you now. Keep it moving and do not make me regret the ask.",
        "I am putting it in your hands. Quiet route, clean finish.",
        "That works. I am counting it as yours.",
        "I will mark you for it. Do it right and I will remember it.",
        "Alright. Small job, small shadow. It is yours now.",
        "I am marking it on your list. Bring back results, not explanations.",
        "Fine. I am putting your name on it. Make it look like nothing needed doing.",
        "It is yours. Bring me the ending, not the drama.",
    ),
    "side_job_declined": (
        "Fair enough. I will keep it off your list.",
        "No problem. I will hold that work back.",
        "That is fine. Better to pass than drag it messy.",
        "Understood. I will not count on you for that one.",
        "Alright. I will keep the ask small by keeping it mine.",
    ),
    "side_job_none": (
        "Nothing small and quiet right now.",
        "No side work on the table at the moment.",
        "Not the kind of errand I hand out lightly. Nothing open right now.",
        "No errand I trust to a loose hand today.",
        "Nothing that would stay small after I gave it away.",
        "No favor-shaped work today.",
        "Nothing I can hand you without making both of us more interesting.",
    ),
    "farewell": (
        "Take care.",
        "Alright. Stay sharp.",
        "See you around.",
        "Keep your head down.",
        "Watch yourself.",
        "Good luck out there.",
        "Careful out there.",
        "Leave some quiet behind you.",
        "Do not make me hear your name twice today.",
        "Walk like you meant to be here.",
        "Keep the next step clean.",
        "Try not to make the day louder.",
        "Later. Move smart.",
        "Go easy where you can.",
        "Leave the room quieter than you found it.",
        "Catch your breath where you can.",
    ),
    "payoff_accept": (
        "Fine. {payoff_cost} and I stop making you today's priority.",
        "That works. {payoff_cost} and I ease off for now.",
        "Hand it over. {payoff_cost} buys you less scrutiny, not amnesia.",
        "Alright. {payoff_cost} and I stop asking extra questions today.",
        "Fair enough. {payoff_cost} buys room to breathe, not a rewritten past.",
        "{payoff_cost}. And stay out of my sight for a while.",
        "{payoff_cost}. That buys less attention, not friendship.",
        "Fine. {payoff_cost}, and I find something else to watch for a while.",
        "{payoff_cost}. I look the other way once; I still know who asked.",
        "Alright. {payoff_cost} buys you a quieter hour.",
    ),
    "payoff_refuse_broke": (
        "That is not enough. Come back when you are serious.",
        "You call that a payoff? Walk away.",
        "Not with that. Try again when you have something real.",
        "That does not cover it. Walk.",
        "I am worth more than that. Come back with more.",
        "That is apology money, not silence money.",
        "You are short, and I am not sentimental.",
    ),
    "payoff_refuse_clean": (
        "I am not that kind of person.",
        "Keep your money.",
        "That is not how I do things.",
        "No. Take your credits and go.",
        "I don't work that way.",
        "I do not sell my attention that cheap.",
        "No. I would rather sleep clean.",
        "Put that away before it becomes evidence.",
    ),
    "payoff_cooldown": (
        "We already handled this. Do not push it.",
        "You already paid. That window is closed.",
        "That deal was made. Don't come looking for another one.",
        "I said we were done. Stay out of trouble.",
        "You bought one silence, not a subscription.",
        "No second pass. Move along.",
    ),
    "fence_accept": (
        "{fence_payout} and that stock does not exist. Leave the bag.",
        "I can do {fence_payout}. No names, no receipts.",
        "Alright. {fence_payout} and I forget I ever saw what you were carrying.",
        "Done. {fence_payout}. You were never here with those.",
        "{fence_payout} is what I can move. Take it or walk.",
        "{fence_payout}. I make it disappear from memory, not from consequence.",
        "I can move it for {fence_payout}. After that, we never admired it together.",
        "{fence_payout}. I can find it a quieter shelf.",
        "For {fence_payout}, it stops being yours before it starts being anyone else's.",
    ),
    "fence_decline_corrupt": (
        "Not today. I am already running too much heat right now.",
        "Wrong time. Come back when things have cooled down.",
        "I can't take anything right now. The block is too hot.",
        "Not this week. You're going to have to sit on it.",
        "No. My quiet channels are full of noise right now.",
        "I like money, but I like not being noticed more.",
    ),
    "fence_decline_clean": (
        "That's not a conversation I have. Move on.",
        "Wrong person. I don't move product.",
        "I don't know what you're implying, but no.",
        "Keep that away from me.",
        "Whatever you think I am, adjust it downward.",
        "No. I do honest shelves and boring receipts.",
        "You brought the wrong kind of question to the wrong kind of person.",
    ),
    "fence_cooldown": (
        "We just did this. Give it time.",
        "I haven't moved the last batch yet. Not yet.",
        "Come back in a few days.",
        "Too soon. You're making me nervous.",
        "Let the last thing vanish before you hand me another.",
        "No. Heat sticks when you stack it.",
    ),
    "hire_runner_accept": (
        "{hire_runner_cost} and I stay with you for {hire_runner_hours}. Keep moving.",
        "Alright. {hire_runner_cost}. I watch your flank for {hire_runner_hours}.",
        "{hire_runner_cost} and I am on your side for {hire_runner_hours}.",
        "Fine. {hire_runner_cost}. Stay where I can see you.",
        "You bought another pair of hands. {hire_runner_cost}. Lead.",
        "Deal. {hire_runner_cost} buys {hire_runner_hours} of me keeping trouble off your back.",
        "{hire_runner_cost}. For {hire_runner_hours}, your problems get one more set of eyes.",
        "{hire_runner_cost}. For {hire_runner_hours}, I am behind you and paying attention.",
        "Done. {hire_runner_cost}. You point, I keep the edges from closing in.",
    ),
    "hire_runner_decline_clean": (
        "I don't do that kind of arrangement. Move along.",
        "That's not something I get involved in.",
        "Wrong person for that conversation.",
        "I keep my head down. You should too.",
        "I am not renting my trouble to yours.",
        "No. My day stays mine.",
        "I do not sell my shadow. Find someone else.",
    ),
    "hire_runner_decline_broke": (
        "I've got a memory like a trap, but not that cheap.",
        "That's not enough for me to forget anything.",
        "Come back when you've got real money.",
        "Not worth the risk for that amount.",
        "You are asking for danger at errand prices.",
        "That money barely buys a yes, never mind backup.",
    ),
    "hire_runner_already_hired": (
        "We already have an arrangement. I am with you.",
        "You're covered. Keep moving.",
        "I haven't wandered off. Lead.",
        "Still on your side. Just do not lose me.",
        "Contract is still warm. Tell me where we are going.",
        "I am already on the clock. Use me or release me.",
    ),
    "backup_orders": (
        "Yeah. You want me close, posted up, making noise, or putting someone down?",
        "Say it plain. I can stay on you, hold a spot, draw eyes, or handle a marked problem.",
        "Alright. Give the word. Passive cover, a position to hold, a distraction, or a harder push?",
        "Give me the shape. Shoulder, station, noise, or teeth?",
        "Plan it out. I can trail you, plant myself, pull attention, or hit the marked problem.",
        "Pick the posture: close guard, fixed point, noisy misdirection, or direct force.",
    ),
    "backup_follow": (
        "Alright. Back to passive cover. I stay near you and keep my eyes open.",
        "Copy. I am back on your shoulder unless something live shows up.",
        "Fine. I stick close and watch your flank again.",
        "Understood. I shadow you and keep the noise small.",
        "Close cover it is. I move when you move.",
        "Back in your pocket. I will watch the edges.",
    ),
    "backup_hold": (
        "Got it. I will hold here and keep watch.",
        "I can post here. Come find me when you are ready to move.",
        "Here works. I stay put and keep my head up.",
        "I will make this spot look ordinary until it stops being useful.",
        "Holding. I will keep the floor from surprising us.",
        "I stay here. If the room changes, I will be the first to know.",
    ),
    "backup_distract": (
        "Sure. I will pull some eyes away from you.",
        "Got it. I will make enough noise to bend attention.",
        "I can stir things up a little. Move when you are ready.",
        "I will give them something easier to watch. Use it.",
        "I can make the room look the wrong way. Be gone by then.",
        "Fine. I will spend a little attention so you do not have to.",
    ),
    "backup_goto_wait": (
        "Alright. I will head to {backup_marked_spot} and sit tight.",
        "Copy. I will move to {backup_marked_spot} and wait there.",
        "Marked spot, then quiet. I have it.",
        "{backup_marked_spot}. I move, I wait, I do not improvise.",
        "I will post at {backup_marked_spot} and keep the mark warm.",
    ),
    "backup_wait_return": (
        "Got it. I will post at {backup_marked_spot}, wait a bit, then circle back.",
        "I can do that. {backup_marked_spot}, hold for a minute, then back to you.",
        "Alright. I will stage at {backup_marked_spot} and return after a short beat.",
        "{backup_marked_spot}, short hold, then I come back to your shoulder.",
        "I will touch the mark, count the pause, and return.",
    ),
    "backup_kill_trusted": (
        "If that is the move, I will handle {backup_kill_target}.",
        "You are sure? Fine. I will put {backup_kill_target} down.",
        "Alright. {backup_kill_target} is mine.",
        "If that line is crossed, {backup_kill_target} does not walk back over it.",
        "Trusted call. I will make {backup_kill_target} stop the problem.",
        "Say when, and {backup_kill_target} becomes my whole room.",
    ),
    "backup_kill_paid": (
        "{backup_kill_cost} and I will make {backup_kill_target} stop being your problem.",
        "That is hazard-pay territory. {backup_kill_cost}, and I will handle {backup_kill_target}.",
        "For {backup_kill_cost}, I can put {backup_kill_target} in the ground.",
        "{backup_kill_cost}. For that, {backup_kill_target} becomes a finished sentence.",
        "{backup_kill_cost}. That buys ugly work on {backup_kill_target}.",
        "For {backup_kill_cost}, I stop asking why and start watching {backup_kill_target}.",
    ),
    "backup_kill_refuse": (
        "No clean shot from me on that.",
        "Mark somebody real if you want that kind of work.",
        "Not like that. Give me a real target or another order.",
        "No target, no trigger. Give me something I can actually read.",
        "I am not swinging at fog. Mark the problem or change the order.",
    ),
}


def _tuple_merge(*groups):
    ordered = []
    seen = set()
    for group in groups:
        for entry in tuple(group or ()):
            text = str(entry or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(text)
    return tuple(ordered)


def _style_profile(group, key):
    profile = group.get(str(key or "").strip().lower(), {})
    return profile if isinstance(profile, dict) else {}


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _voice_quality_for(seed, npc_eid, *, area_type, district_type, role_id, tone, empathy, discipline):
    rng = random.Random(
        f"{seed}:dialogue-voice-quality:{npc_eid}:{area_type}:{district_type}:{role_id}:{tone}"
    )
    roll = rng.random()
    roll -= max(0.0, min(1.0, float(discipline))) * 0.07
    roll += max(0.0, min(1.0, float(empathy))) * 0.05
    if str(role_id or "").strip().lower() in {"guard", "patrol", "scout", "banker", "broker"}:
        roll -= 0.04
    if str(tone or "").strip().lower() in {"friendly", "warm"}:
        roll += 0.04
    elif str(tone or "").strip().lower() in {"guarded", "wary"}:
        roll -= 0.03
    roll = max(0.0, min(0.999, roll))
    if roll < 0.16:
        return "spare"
    if roll < 0.72:
        return "ordinary"
    if roll < 0.93:
        return "local"
    return "colorful"


def _merge_usage_weights(*profiles):
    merged = {}
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        weights = profile.get("usage_weights", {})
        if not isinstance(weights, dict):
            continue
        for key, value in weights.items():
            key = str(key or "").strip().lower()
            if not key:
                continue
            weight = max(0.0, _safe_float(value, 0.0))
            if key in merged:
                merged[key] = max(0.0, merged[key] * weight)
            else:
                merged[key] = weight
    return dict(merged)


def _style_weight(weights, key, default=1.0):
    if not isinstance(weights, dict):
        return max(0.0, float(default))
    return max(0.0, _safe_float(weights.get(key, default), default))


def _weighted_style_choice(rng, candidates):
    weighted = [
        (str(kind or "").strip().lower(), tuple(phrases or ()), max(0.0, _safe_float(weight, 0.0)))
        for kind, phrases, weight in candidates
        if max(0.0, _safe_float(weight, 0.0)) > 0.0
    ]
    if not weighted:
        return "", ()
    total = sum(weight for _kind, _phrases, weight in weighted)
    if total <= 0.0:
        return "", ()
    pick = rng.random() * total
    running = 0.0
    for kind, phrases, weight in weighted:
        running += weight
        if pick <= running:
            return kind, phrases
    kind, phrases, _weight = weighted[-1]
    return kind, phrases


def speaker_style(
    seed,
    npc_eid,
    *,
    area_type="city",
    district_type="unknown",
    role_id="",
    tone="neutral",
    empathy=0.5,
    discipline=0.5,
    culture_profile=None,
):
    area_type = str(area_type or "city").strip().lower() or "city"
    district_type = str(district_type or "unknown").strip().lower() or "unknown"
    role_id = str(role_id or "").strip().lower()
    tone = str(tone or "neutral").strip().lower() or "neutral"
    empathy = _safe_float(empathy, 0.5)
    discipline = _safe_float(discipline, 0.5)
    culture_profile = culture_profile if isinstance(culture_profile, dict) else {}
    culture_lexemes = culture_profile.get("lexemes", {})
    culture_lexemes = culture_lexemes if isinstance(culture_lexemes, dict) else {}
    culture_key = str(culture_profile.get("culture_key", "") or "").strip()
    culture_greeting = str(culture_lexemes.get("greeting", "") or "").strip().capitalize()
    culture_farewell = str(culture_lexemes.get("farewell", "") or "").strip().capitalize()

    role_profile = _style_profile(ROLE_STYLE_HINTS, role_id)
    district_profile = _style_profile(DISTRICT_STYLE_HINTS, district_type)
    area_profile = _style_profile(AREA_STYLE_HINTS, area_type)

    register = str(role_profile.get("register", "")).strip().lower()
    if not register:
        if district_type in {"military", "corporate"}:
            register = "official"
        elif district_type == "slums":
            register = "rough"
        elif district_type == "entertainment":
            register = "theatrical"
        elif empathy >= 0.72:
            register = "warm"
        elif discipline >= 0.72:
            register = "clipped"
        else:
            register = "plain"

    if tone == "friendly" and register in {"plain", "clipped"} and empathy >= 0.58:
        register = "warm"
    if tone == "guarded" and register == "warm":
        register = "plain"

    register_profile = _style_profile(REGISTER_STYLE_HINTS, register)
    voice_quality = _voice_quality_for(
        seed,
        npc_eid,
        area_type=area_type,
        district_type=district_type,
        role_id=role_id,
        tone=tone,
        empathy=empathy,
        discipline=discipline,
    )
    quality_profile = _style_profile(VOICE_QUALITY_PROFILES, voice_quality)
    usage_weights = _merge_usage_weights(
        quality_profile,
        register_profile,
        area_profile,
        district_profile,
        role_profile,
    )
    merged = {
        "register": register,
        "area_type": area_type,
        "district_type": district_type,
        "role_id": role_id,
        "tone": tone,
        "voice_quality": voice_quality,
        "culture_key": culture_key,
        "usage_weights": usage_weights,
        "lead_ins": _tuple_merge(
            register_profile.get("lead_ins"),
            role_profile.get("lead_ins"),
        ),
        "address_terms": _tuple_merge(
            district_profile.get("address_terms"),
            register_profile.get("address_terms"),
            role_profile.get("address_terms"),
        ),
        "catch_phrases": _tuple_merge(
            area_profile.get("catch_phrases"),
            district_profile.get("catch_phrases"),
            role_profile.get("catch_phrases"),
        ),
        "idioms": _tuple_merge(
            area_profile.get("idioms"),
            district_profile.get("idioms"),
            role_profile.get("idioms"),
        ),
        "local_terms": _tuple_merge(
            area_profile.get("local_terms"),
            district_profile.get("local_terms"),
            role_profile.get("local_terms"),
        ),
        "farewell_tags": _tuple_merge(
            area_profile.get("farewell_tags"),
            district_profile.get("farewell_tags"),
            register_profile.get("farewell_tags"),
        ),
        "culture_greetings": (f"{culture_greeting}.",) if culture_greeting else (),
        "culture_farewells": (culture_farewell,) if culture_farewell else (),
    }
    return merged


def _prepend_phrase(text, phrase):
    phrase = str(phrase or "").strip()
    text = str(text or "").strip()
    if not phrase or not text:
        return text
    return f"{phrase} {text}"


def _append_phrase(text, phrase):
    phrase = str(phrase or "").strip()
    text = str(text or "").strip()
    if not phrase or not text:
        return text
    if phrase[-1] not in ".!?":
        phrase = phrase + "."
    return f"{text} {phrase}"


def _with_address(text, address):
    address = str(address or "").strip()
    text = str(text or "").strip()
    if not address or not text:
        return text
    if text[-1] in ".!?":
        return f"{text[:-1]}, {address}{text[-1]}"
    return f"{text}, {address}"


def style_dialogue_line(text, *, seed, npc_eid, bank_id, topic_id="", count=0, style_profile=None):
    text = str(text or "").strip()
    if not text or not isinstance(style_profile, dict):
        return text

    bank_key = str(bank_id or "").strip().lower()
    # Include key style dimensions in the rng seed so that different districts/
    # roles produce different phrasing even with the same base seed.
    district_type = str(style_profile.get("district_type", "")).strip().lower()
    area_type = str(style_profile.get("area_type", "")).strip().lower()
    role_id = str(style_profile.get("role_id", "")).strip().lower()
    culture_key = str(style_profile.get("culture_key", "")).strip().lower()
    rng = random.Random(
        f"{seed}:dialogue-style:{npc_eid}:{bank_key}:{topic_id}:{count}:"
        f"{district_type}:{area_type}:{role_id}:{culture_key}"
    )
    result = text

    lead_ins = tuple(style_profile.get("lead_ins", ()) or ())
    address_terms = tuple(style_profile.get("address_terms", ()) or ())
    catch_phrases = tuple(style_profile.get("catch_phrases", ()) or ())
    idioms = tuple(style_profile.get("idioms", ()) or ())
    local_terms = tuple(style_profile.get("local_terms", ()) or ())
    farewell_tags = tuple(style_profile.get("farewell_tags", ()) or ()) or catch_phrases
    culture_greetings = tuple(style_profile.get("culture_greetings", ()) or ())
    culture_farewells = tuple(style_profile.get("culture_farewells", ()) or ())
    usage_weights = style_profile.get("usage_weights", {})
    if not isinstance(usage_weights, dict):
        usage_weights = {}

    candidates = []
    if bank_key.startswith("greet_") and culture_greetings:
        candidates.append(("culture_greeting", culture_greetings, 0.72))
    if bank_key in STYLE_LEAD_IN_BANKS and lead_ins:
        candidates.append(("lead_in", lead_ins, _style_weight(usage_weights, "lead_in", 0.65)))
    if bank_key in STYLE_ADDRESS_BANKS and address_terms:
        candidates.append(("address", address_terms, _style_weight(usage_weights, "address", 0.65)))
    if bank_key == "farewell" and farewell_tags:
        candidates.append(("farewell", farewell_tags, _style_weight(usage_weights, "farewell", 1.0)))
    elif bank_key in STYLE_CATCH_BANKS:
        if catch_phrases:
            candidates.append(("catch", catch_phrases, _style_weight(usage_weights, "catch", 1.0)))
        if idioms:
            candidates.append(("idiom", idioms, _style_weight(usage_weights, "idiom", 0.15)))
        if local_terms:
            candidates.append(("local_term", local_terms, _style_weight(usage_weights, "local_term", 0.05)))
    if bank_key in STYLE_SOFT_TEXTURE_BANKS:
        candidates.append(("none", (), _style_weight(usage_weights, "quiet", 0.75)))
    if bank_key == "farewell" and culture_farewells:
        candidates.append(("culture_farewell", culture_farewells, 0.55))

    style_kind, phrases = _weighted_style_choice(rng, candidates)
    if not style_kind or style_kind == "none":
        return result
    phrase = phrases[rng.randrange(len(phrases))] if phrases else ""
    if style_kind in {"lead_in", "culture_greeting"}:
        result = _prepend_phrase(result, phrase)
    elif style_kind == "address":
        result = _with_address(result, phrase)
    else:
        result = _append_phrase(result, phrase)

    return result


def topic_spec(topic_id):
    return TOPIC_DEFS.get(str(topic_id or "").strip().lower(), {})


def topic_unlocks(topic_id):
    return tuple(topic_spec(topic_id).get("unlocks", ()))


def topic_label(topic_id, context=None):
    topic_id = str(topic_id or "").strip().lower()
    context = context if isinstance(context, dict) else {}

    def _with_hint(base, hint_key):
        label = str(base or "").strip()
        hint = str(context.get(hint_key, "") or "").strip()
        if label and hint:
            return f"{label} [{hint}]"
        return label

    if topic_id == "leverage":
        return "I know what you've been hiding."
    if topic_id == "leverage_credits":
        amount = int(context.get("leverage_credits_amount", 0) or 0)
        return f"Pay me {amount} credits." if amount > 0 else "Pay me for my silence."
    if topic_id == "leverage_trade_terms":
        place = str(context.get("leverage_trade_property_name", "your counter") or "your counter").strip()
        return f"Give me better terms at {place}."
    if topic_id == "leverage_look_away":
        place = str(context.get("leverage_look_away_property_name", "this place") or "this place").strip()
        return f"Look the other way at {place}."
    if topic_id == "leverage_distraction":
        return "Make a distraction for me."
    if topic_id == "leverage_access_window":
        place = str(context.get("leverage_access_property_name", "this place") or "this place").strip()
        return f"Open an access window at {place}."
    if topic_id == "leverage_credentials":
        credential = str(context.get("leverage_credential_item_name", "credential") or "credential").strip()
        return f"Hand over your {credential}."
    if topic_id == "leverage_disable_camera":
        camera = str(context.get("leverage_camera_name", "camera") or "camera").strip()
        return f"Take the {camera} offline."
    if topic_id == "leverage_hand_over_item":
        item_name = str(context.get("leverage_item_name", "item") or "item").strip()
        return f"Hand over your {item_name}."
    if topic_id == "leverage_falsify_record":
        place = str(context.get("leverage_record_property_name", "this place") or "this place").strip()
        return f"Put me in the access records at {place}."
    if topic_id == "leverage_arrange_meeting":
        name = str(context.get("leverage_meeting_lead_name", "your contact") or "your contact").strip()
        return f"Arrange a meeting with {name}."

    if topic_id == "workplace" and context.get("workplace_here"):
        return "Do you work here?"
    if topic_id == "rapport":
        return "How's your day going?"
    if topic_id == "check_in":
        return "How've you been since last time?"
    if topic_id == "day_feel":
        return "How's the day treating you?"
    if topic_id == "job_feel" and context.get("career_text"):
        return f"How do you feel about the {context['career_text']} work?"
    if topic_id == "job_feel":
        return "How do you feel about the work?"
    if topic_id == "roots" and context.get("home_name"):
        return f"What keeps you tied to {context['home_name']}?"
    if topic_id == "roots":
        return "What keeps you here?"
    if topic_id == "off_shift":
        return "What do you do when you're off?"
    if topic_id == "care_about":
        return "What matters to you, really?"
    if topic_id == "read_player":
        return "How do you read me?"
    if topic_id == "street_buy" and context.get("street_buy_hint"):
        return f"I might have some {context['street_buy_hint']}. Can we trade?"
    if topic_id == "street_buy_accept" and context.get("street_buy_offer_accept_label"):
        return str(context["street_buy_offer_accept_label"]).strip()
    if topic_id == "street_buy_next" and context.get("street_buy_offer_next_label"):
        return str(context["street_buy_offer_next_label"]).strip()
    if topic_id == "street_buy_decline" and context.get("street_buy_offer_decline_label"):
        return str(context["street_buy_offer_decline_label"]).strip()
    if topic_id == "organization" and context.get("workplace_name"):
        if str(context.get("organization_role", "")).strip().lower() == "owner":
            return f"Is {context['workplace_name']} yours?"
        if context.get("workplace_here"):
            return "Who's the outfit behind this place?"
        return f"Who's the outfit behind {context['workplace_name']}?"
    if topic_id == "corporate_presence" and context.get("corporate_brand"):
        return f"What's {context['corporate_brand']} doing to this block?"
    if topic_id == "corporate_pull" and context.get("corporate_brand"):
        return f"Why do people choose {context['corporate_brand']}?"
    if topic_id == "corporate_cost" and context.get("corporate_brand"):
        if context.get("corporate_presence_here"):
            return f"What's the real cost of having {context['corporate_brand']} here?"
        return f"What's the real cost of dealing with {context['corporate_brand']}?"
    if topic_id == "cult" and context.get("cult_name"):
        return f"What's {context['cult_name']} asking from people?"
    if topic_id == "cult":
        return "What's that circle about?"
    if topic_id == "supervisor" and context.get("workplace_here"):
        if str(context.get("organization_role", "")).strip().lower() == "owner":
            return "Anybody above you here?"
        return "Who calls the shots here?"
    if topic_id == "supervisor" and context.get("workplace_name"):
        if str(context.get("organization_role", "")).strip().lower() == "owner":
            return f"Anybody above you at {context['workplace_name']}?"
        return f"Who calls the shots at {context['workplace_name']}?"
    if topic_id == "coworkers" and context.get("workplace_here"):
        if int(context.get("organization_member_count", 0) or 0) <= 1:
            return "Is it usually just you here?"
        return "Who else is usually on here?"
    if topic_id == "coworkers" and context.get("workplace_name"):
        if int(context.get("organization_member_count", 0) or 0) <= 1:
            return f"Is it usually just you at {context['workplace_name']}?"
        return f"Who else is usually on at {context['workplace_name']}?"
    if topic_id == "people" and context.get("workplace_here"):
        return "Who should I know here?"
    if topic_id == "people" and context.get("workplace_name"):
        return f"Who should I know around {context['workplace_name']}?"
    if topic_id == "people" and context.get("social_lead_name"):
        return "Who should I know around here?"
    if topic_id == "where_place" and context.get("referenced_place_name"):
        return f"Where is {context['referenced_place_name']}?"
    if topic_id == "hire" and context.get("player_business_hire_name"):
        open_roles = tuple(
            str(role).strip().lower()
            for role in tuple(context.get("player_business_hire_roles", ()) or ())
            if str(role).strip()
        )
        if context.get("player_business_hire_poaching") and context.get("player_business_hire_current_name"):
            if len(open_roles) > 1:
                return _with_hint(
                    f"Would you leave {context['player_business_hire_current_name']} for {context['player_business_hire_name']}?",
                    "player_business_hire_fit_hint",
                )
            if str(context.get("player_business_hire_role", "")).strip().lower() == "manager":
                return _with_hint(
                    f"Would you leave {context['player_business_hire_current_name']} to run {context['player_business_hire_name']}?",
                    "player_business_hire_fit_hint",
                )
            return _with_hint(
                f"Would you leave {context['player_business_hire_current_name']} for {context['player_business_hire_name']}?",
                "player_business_hire_fit_hint",
            )
        if len(open_roles) > 1:
            return _with_hint(f"Want work at {context['player_business_hire_name']}?", "player_business_hire_fit_hint")
        if str(context.get("player_business_hire_role", "")).strip().lower() == "manager":
            return _with_hint(f"Want to run {context['player_business_hire_name']}?", "player_business_hire_fit_hint")
        return _with_hint(f"Want work at {context['player_business_hire_name']}?", "player_business_hire_fit_hint")
    if topic_id == "hire_manager" and context.get("player_business_hire_name"):
        if context.get("player_business_hire_poaching") and context.get("player_business_hire_current_name"):
            return _with_hint(
                f"Would you leave {context['player_business_hire_current_name']} to run {context['player_business_hire_name']}?",
                "player_business_hire_manager_fit_hint",
            )
        return _with_hint(f"Would you run {context['player_business_hire_name']}?", "player_business_hire_manager_fit_hint")
    if topic_id == "hire_staff" and context.get("player_business_hire_name"):
        if context.get("player_business_hire_poaching") and context.get("player_business_hire_current_name"):
            return _with_hint(
                f"Would you leave {context['player_business_hire_current_name']} for shifts at {context['player_business_hire_name']}?",
                "player_business_hire_staff_fit_hint",
            )
        return _with_hint(f"Would you take a shift at {context['player_business_hire_name']}?", "player_business_hire_staff_fit_hint")
    if topic_id == "hire_accept" and context.get("player_business_hire_quote_text"):
        business_name = str(context.get("player_business_hire_quote_business", "the business") or "the business")
        return f"Agree to {context['player_business_hire_quote_text']}/hr at {business_name}."
    if topic_id == "hire_decline" and context.get("player_business_hire_pending_offer"):
        return "No deal."
    if topic_id == "fire" and context.get("player_business_fire_name"):
        return f"I need to take you off staff at {context['player_business_fire_name']}."
    if topic_id == "owner" and context.get("owner_place_name"):
        return f"Who runs {context['owner_place_name']}?"
    if topic_id == "security" and context.get("owner_place_name"):
        return f"How tight is {context['owner_place_name']}?"
    if topic_id == "access" and context.get("workplace_here"):
        return "What gets people through here?"
    if topic_id == "access" and context.get("owner_place_name"):
        return f"What gets people through {context['owner_place_name']}?"
    if topic_id == "entry" and context.get("workplace_here"):
        return "Is there another way in here?"
    if topic_id == "entry" and context.get("owner_place_name"):
        return f"Is there another way into {context['owner_place_name']}?"
    if topic_id == "keyholder" and context.get("owner_place_name"):
        return f"Who carries access to {context['owner_place_name']}?"
    if topic_id == "weak_point" and context.get("workplace_here"):
        return "What's the weak point here?"
    if topic_id == "weak_point" and context.get("owner_place_name"):
        return f"What's the weak point at {context['owner_place_name']}?"
    if topic_id == "purpose" and context.get("guarded"):
        return "I'm not here for trouble."
    if topic_id == "apologize" and context.get("guarded"):
        return "Sorry. My mistake."
    if topic_id == "leave" and context.get("guarded"):
        return "I'll go."
    if topic_id == "services" and context.get("owner_place_name"):
        return f"What goes on at {context['owner_place_name']}?"
    if topic_id == "service_fuel":
        return "Any fuel nearby?"
    if topic_id == "service_repair":
        return "Any repair shop nearby?"
    if topic_id == "service_contractor":
        return "Any contractor nearby?"
    if topic_id == "service_banking":
        return "Any bank or broker nearby?"
    if topic_id == "service_business_desk":
        return "Any business desk nearby?"
    if topic_id == "service_insurance":
        return "Any insurer or claims desk nearby?"
    if topic_id == "service_rest":
        return "Anywhere to sleep nearby?"
    if topic_id == "service_transit":
        return "Any transit nearby?"
    if topic_id == "service_rail":
        return "Where's the nearest station?"
    if topic_id == "service_bus":
        return "Where can I catch a bus?"
    if topic_id == "service_shuttle":
        return "Any shuttle stop around here?"
    if topic_id == "service_ferry":
        return "Any ferry landing around here?"
    if topic_id == "service_coach":
        return "Where can I catch a coach?"
    if topic_id == "service_intel":
        return "Anywhere selling intel nearby?"
    if topic_id == "service_work":
        return "Any posted work nearby?"
    if topic_id == "service_courier":
        return "Any courier board nearby?"
    if topic_id == "service_agency":
        return "Any agency work nearby?"
    if topic_id == "service_bounty":
        return "Any bounty board nearby?"
    if topic_id == "service_trade":
        return "Any shopping around here?"
    if topic_id == "service_discreet_trade":
        return "Know any discreet sellers?"
    if topic_id == "service_street_doctor":
        return "Know any quiet doctors?"
    if topic_id == "service_herbal":
        return "Any herbal care nearby?"
    if topic_id == "service_butcher":
        return "Any butcher nearby?"
    if topic_id == "service_appearance":
        return "Anywhere for hair, makeup, or tattoos?"
    if topic_id == "service_outfitter":
        return "Any outfitter nearby?"
    if topic_id == "service_drone_parts":
        return "Any drone parts nearby?"
    if topic_id == "service_wire_gear":
        return "Any Wire gear nearby?"
    if topic_id == "service_records":
        return "Where can I inspect civic records?"
    if topic_id == "service_justice":
        return "Where's the nearest jail or courthouse?"
    if topic_id == "service_vehicle_sales":
        return "Anyone selling vehicles nearby?"
    if topic_id == "service_used_cars":
        return "Any used cars nearby?"
    if topic_id == "service_vehicle_fetch":
        return "Anyone who can retrieve a vehicle?"
    if topic_id == "service_gaming":
        return "Any gaming around here?"
    if topic_id == "hours" and context.get("owner_place_name"):
        return f"When is {context['owner_place_name']} open?"
    if topic_id == "concern" and context.get("guarded"):
        return "What seems to be the problem?"
    if topic_id == "detail":
        detail_label = str(context.get("detail_label", "")).strip()
        if detail_label:
            return detail_label
    if topic_id == "opportunities" and context.get("objective_title"):
        return "Anything worth pursuing right now?"
    if topic_id == "objective" and context.get("objective_title"):
        return f"What helps with {context['objective_title']}?"
    if topic_id == "angle" and context.get("objective_title"):
        return f"Where would you push {context['objective_title']}?"
    if topic_id == "risk" and context.get("primary_opportunity_title"):
        return f"What's the catch with {context['primary_opportunity_title']}?"
    if topic_id == "attention":
        if context.get("guarded"):
            return "How bad does this look?"
        pressure_tier = str(context.get("pressure_tier", "low")).strip().lower()
        if pressure_tier == "high":
            return "How bad is the heat right now?"
        if pressure_tier == "medium":
            return "Am I drawing attention right now?"
        return "Should I keep my head down?"
    if topic_id == "backup_orders":
        return _with_hint("Let's tighten the plan.", "backup_status_hint")
    if topic_id == "backup_follow":
        return "Back to passive cover."
    if topic_id == "backup_hold":
        return "Hang here."
    if topic_id == "backup_distract":
        return "Make a distraction."
    if topic_id == "backup_goto_wait":
        return _with_hint("Head to the marked spot and wait.", "backup_cursor_hint")
    if topic_id == "backup_wait_return":
        return _with_hint("Head to the marked spot, wait, then return.", "backup_cursor_hint")
    if topic_id == "backup_kill":
        target_name = str(context.get("backup_kill_target_name", "")).strip()
        base = f"Take out {target_name}." if target_name else "Take out the marked target."
        return _with_hint(base, "backup_kill_cost_hint")
    if topic_id == "weird":
        return "Ask something weird."
    if topic_id == "pry":
        return "Get a little too personal."
    if topic_id == "provoke":
        return "Needle them for an honest reaction."
    if topic_id == "intimidate":
        return "Pressure them for local information."
    if topic_id == "insult":
        tone = str(context.get("tone", "neutral")).strip().lower()
        if tone in {"wary", "guarded"}:
            return "Push their buttons."
        return "Throw a cheap shot."
    if topic_id == "introduction" and context.get("social_lead_name"):
        return f"Could you introduce me to {context['social_lead_name']}?"
    if topic_id == "contract" and context.get("contract_target_role"):
        return "You mentioned you have work on offer?"
    return str(topic_spec(topic_id).get("label", topic_id.replace("_", " ").title()))


def _dialogue_lower_start(text):
    text = str(text or "")
    if not text:
        return ""
    first = text[:1]
    if first.isalpha():
        return first.lower() + text[1:]
    return text


def _normalize_player_topic_entry(entry, fallback_text):
    if isinstance(entry, dict):
        normalized = dict(entry)
    else:
        normalized = {"text": str(entry).strip()}
    normalized["text"] = str(normalized.get("text", "")).strip() or str(fallback_text or "").strip()
    for key in (
        "npc_soft",
        "npc_wary",
        "npc_fail",
        "npc_reserved",
        "npc_open",
        "npc_warm",
        "npc_rebuff",
    ):
        value = normalized.get(key, ())
        if isinstance(value, str):
            normalized[key] = (str(value).strip(),) if str(value).strip() else ()
            continue
        normalized[key] = tuple(
            str(item).strip()
            for item in tuple(value or ())
            if str(item).strip()
        )
    return normalized


def _render_topic_text(template, context, *, fallback=""):
    template = str(template or "").strip()
    fallback = str(fallback or "").strip()
    if not template:
        return fallback
    if "{" not in template or "}" not in template:
        return template
    context = context if isinstance(context, dict) else {}
    safe_slots = {}
    for key, value in context.items():
        if value is None or isinstance(value, (dict, list, tuple, set)):
            continue
        text = str(value).strip()
        if text:
            safe_slots[str(key)] = text
    for (_literal, field_name, _format_spec, _conversion) in string.Formatter().parse(template):
        if not field_name:
            continue
        field_key = str(field_name).split(".", 1)[0].split("[", 1)[0]
        if not safe_slots.get(field_key, ""):
            return fallback
    try:
        rendered = str(template).format(**safe_slots).strip()
    except Exception:
        return fallback
    return rendered or fallback


def _render_player_topic_entry(entry, context):
    normalized = _normalize_player_topic_entry(entry, "")
    text = _render_topic_text(normalized.get("text", ""), context, fallback="")
    if not text:
        return None
    rendered = {
        "text": text,
        "npc_soft": (),
        "npc_wary": (),
        "npc_fail": (),
        "npc_reserved": (),
        "npc_open": (),
        "npc_warm": (),
        "npc_rebuff": (),
    }
    for key in (
        "npc_soft",
        "npc_wary",
        "npc_fail",
        "npc_reserved",
        "npc_open",
        "npc_warm",
        "npc_rebuff",
    ):
        rendered[key] = tuple(
            rendered_text
            for raw in tuple(normalized.get(key, ()) or ())
            if (rendered_text := _render_topic_text(raw, context, fallback=""))
        )
    return rendered


def _render_player_topic_text_options(options, context):
    rendered = []
    seen = set()
    for raw in tuple(options or ()):
        entry = _render_player_topic_entry(raw, context)
        if not entry:
            continue
        text = str(entry.get("text", "")).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        rendered.append(text)
    return tuple(rendered)


def _menu_hint_suffix(base_label):
    base_label = str(base_label or "").strip()
    if not base_label.endswith("]"):
        return ""
    start = base_label.rfind(" [")
    if start < 0:
        return ""
    return base_label[start:]


def _context_menu_options(topic_id, base_label, context):
    topic_id = str(topic_id or "").strip().lower()
    base_lc = str(base_label or "").strip().lower()
    context = context if isinstance(context, dict) else {}
    if topic_id == "organization" and "yours" in base_lc:
        return PLAYER_CONTEXT_MENU_BANKS.get("organization_owner", ())
    if topic_id == "supervisor" and "above you" in base_lc:
        return PLAYER_CONTEXT_MENU_BANKS.get("supervisor_owner", ())
    if topic_id == "coworkers" and "just you" in base_lc:
        return PLAYER_CONTEXT_MENU_BANKS.get("coworkers_solo", ())
    if topic_id == "street_buy" and context.get("street_buy_hint"):
        return PLAYER_CONTEXT_MENU_BANKS.get("street_buy_requested", ())
    return ()


def _choose_menu_text(options, context, *, fallback, seed, npc_eid, topic_id, count=0, previous_topic_id="", total_asked=0, opened_count=0, salt=""):
    fallback = str(fallback or "").strip()
    rendered = _render_player_topic_text_options(options, context)
    if not rendered:
        return fallback
    try:
        count = max(1, int(count))
    except (TypeError, ValueError):
        count = 1
    try:
        total_asked = max(0, int(total_asked))
    except (TypeError, ValueError):
        total_asked = 0
    try:
        opened_count = max(0, int(opened_count))
    except (TypeError, ValueError):
        opened_count = 0
    chooser = random.Random(
        f"{seed}:dialogue-player-menu:{npc_eid}:{topic_id}:{count}:"
        f"{previous_topic_id}:{total_asked}:{opened_count}:{salt}"
    )
    text = str(rendered[chooser.randrange(len(rendered))]).strip()
    suffix = _menu_hint_suffix(fallback)
    if suffix and suffix not in text:
        text = f"{text}{suffix}"
    return text or fallback


def topic_player_prompt(topic_id, *, seed, npc_eid, count=0, context=None):
    topic_id = str(topic_id or "").strip().lower()
    label = topic_label(topic_id, context=context)
    options = tuple(PLAYER_TOPIC_BANKS.get(topic_id, ()))
    if not options:
        return {"text": label, "npc_soft": (), "npc_wary": (), "npc_fail": ()}
    rendered_entries = [
        rendered
        for raw in options
        if (rendered := _render_player_topic_entry(raw, context))
    ]
    if not rendered_entries:
        return {"text": label, "npc_soft": (), "npc_wary": (), "npc_fail": ()}
    try:
        count = max(1, int(count))
    except (TypeError, ValueError):
        count = 1
    offset = random.Random(f"{seed}:dialogue-player-topic:{npc_eid}:{topic_id}").randrange(len(rendered_entries))
    return rendered_entries[(offset + count - 1) % len(rendered_entries)]


def topic_player_prompt_matching_text(topic_id, *, seed, npc_eid, count=0, context=None, prompt_text=""):
    prompt_text = str(prompt_text or "").strip()
    if not prompt_text:
        return topic_player_prompt(
            topic_id,
            seed=seed,
            npc_eid=npc_eid,
            count=count,
            context=context,
        )
    prompt_key = prompt_text.casefold()
    if prompt_text.endswith("]"):
        hint_start = prompt_text.rfind(" [")
        if hint_start >= 0:
            prompt_key = prompt_text[:hint_start].strip().casefold()
    options = tuple(PLAYER_TOPIC_BANKS.get(str(topic_id or "").strip().lower(), ()))
    for raw in options:
        rendered = _render_player_topic_entry(raw, context)
        rendered_key = str(rendered.get("text", "")).strip().casefold() if isinstance(rendered, dict) else ""
        if rendered_key and (rendered_key == prompt_key or rendered_key in prompt_key):
            return rendered
    return topic_player_prompt(
        topic_id,
        seed=seed,
        npc_eid=npc_eid,
        count=count,
        context=context,
    )


def topic_player_reaction_line(topic_id, *, seed, npc_eid, count=0, outcome="soft", context=None, prompt_text=""):
    prompt = topic_player_prompt_matching_text(
        topic_id,
        seed=seed,
        npc_eid=npc_eid,
        count=count,
        context=context,
        prompt_text=prompt_text,
    )
    normalized_outcome = str(outcome or "soft").strip().lower() or "soft"
    outcome_key = {
        "reserved": "npc_reserved",
        "open": "npc_open",
        "warm": "npc_warm",
        "rebuff": "npc_rebuff",
    }.get(normalized_outcome, f"npc_{normalized_outcome}")
    options = tuple(prompt.get(outcome_key, ()))
    if not options:
        return ""
    chooser = random.Random(
        f"{seed}:dialogue-player-reaction:{npc_eid}:{topic_id}:{count}:{outcome_key}"
    )
    return str(options[chooser.randrange(len(options))]).strip()


def topic_menu_label(topic_id, *, seed, npc_eid, count=0, context=None, previous_topic_id="", total_asked=0, opened_count=0):
    topic_id = str(topic_id or "").strip().lower()
    base_label = topic_label(topic_id, context=context)
    if topic_id in PLAYER_MENU_BASE_LABEL_TOPICS:
        return base_label

    context = context if isinstance(context, dict) else {}
    context_options = _context_menu_options(topic_id, base_label, context)
    if context_options:
        return _choose_menu_text(
            context_options,
            context,
            fallback=base_label,
            seed=seed,
            npc_eid=npc_eid,
            topic_id=topic_id,
            count=count,
            previous_topic_id=previous_topic_id,
            total_asked=total_asked,
            opened_count=opened_count,
            salt="context",
        )

    options = tuple(PLAYER_TOPIC_BANKS.get(topic_id, ()))
    if not options:
        return base_label
    return _choose_menu_text(
        options,
        context,
        fallback=base_label,
        seed=seed,
        npc_eid=npc_eid,
        topic_id=topic_id,
        count=count,
        previous_topic_id=previous_topic_id,
        total_asked=total_asked,
        opened_count=opened_count,
    )


def topic_player_line(topic_id, *, seed, npc_eid, count=0, context=None, previous_topic_id="", total_asked=0, line_override=""):
    topic_id = str(topic_id or "").strip().lower()
    line = str(line_override or "").strip()
    if not line:
        prompt = topic_player_prompt(
            topic_id,
            seed=seed,
            npc_eid=npc_eid,
            count=count,
            context=context,
        )
        line = str(prompt.get("text", "")).strip() or topic_label(topic_id, context=context)
    previous_topic_id = str(previous_topic_id or "").strip().lower()
    try:
        count = max(1, int(count))
    except (TypeError, ValueError):
        count = 1
    try:
        total_asked = max(0, int(total_asked))
    except (TypeError, ValueError):
        total_asked = 0
    if (
        not previous_topic_id
        or total_asked <= 1
        or count > 1
        or topic_id in PLAYER_CONNECTIVE_SKIP_TOPICS
        or not line.endswith("?")
    ):
        return line

    followup = topic_id in topic_unlocks(previous_topic_id)
    if followup and total_asked <= 3:
        bridge_chance = 1.0
    elif followup:
        bridge_chance = 0.72
    else:
        bridge_chance = 0.26
    roll = random.Random(
        f"{seed}:dialogue-player-bridge:{npc_eid}:{previous_topic_id}:{topic_id}:{count}:{total_asked}"
    ).random()
    if roll > bridge_chance:
        return line
    prefixes = PLAYER_CONNECTIVE_FOLLOWUP_PREFIXES if followup else PLAYER_CONNECTIVE_SHIFT_PREFIXES
    chooser = random.Random(
        f"{seed}:dialogue-player-bridge-prefix:{npc_eid}:{previous_topic_id}:{topic_id}:{count}:{total_asked}"
    )
    prefix = str(prefixes[chooser.randrange(len(prefixes))]).strip()
    lowered = _dialogue_lower_start(line)
    return f"{prefix} {lowered}".strip()


def ordered_topic_ids():
    return tuple(TOPIC_ORDER)


class _SafeFormatSlots(dict):
    def __missing__(self, key):
        return ""


def _clean_dialogue_output(text):
    return " ".join(str(text or "").split()).strip()


def choose_dialogue_line(bank_id, *, seed, npc_eid, topic_id="", count=0, salt="", style_profile=None, **slots):
    options = tuple(DIALOGUE_BANKS.get(str(bank_id or "").strip().lower(), ()))
    if not options:
        return ""

    chooser = random.Random(
        f"{seed}:dialogue:{npc_eid}:{bank_id}:{topic_id}:{count}:{salt}"
    )
    template = str(options[chooser.randrange(len(options))])
    safe_slots = _SafeFormatSlots({key: str(value) for key, value in slots.items()})
    line = _clean_dialogue_output(template.format_map(safe_slots))
    styled = style_dialogue_line(
        line,
        seed=seed,
        npc_eid=npc_eid,
        bank_id=bank_id,
        topic_id=topic_id,
        count=count,
        style_profile=style_profile,
    )
    return _clean_dialogue_output(styled)


DIALOGUE_VOICE_SAMPLE_BANKS = (
    "greet_neutral",
    "history",
    "local_opportunity",
    "security",
    "opportunities",
    "attention",
    "farewell",
)


def dialogue_voice_samples(
    seed=12345,
    npc_eid=2,
    *,
    area_type="city",
    district_type="downtown",
    role_id="clerk",
    tone="neutral",
    empathy=0.5,
    discipline=0.5,
    sample_banks=None,
):
    style = speaker_style(
        seed,
        npc_eid,
        area_type=area_type,
        district_type=district_type,
        role_id=role_id,
        tone=tone,
        empathy=empathy,
        discipline=discipline,
    )
    slots = {
        "history_summary": "I have been here long enough to know the corners.",
        "history_summary_lc": "i have been here long enough to know the corners.",
        "opportunity_summary": "A courier lead is still live nearby.",
        "security_summary": "Badge checks and one camera cover the front.",
        "security_summary_lc": "badge checks and one camera cover the front.",
        "attention_summary": "You are background motion right now.",
        "attention_summary_lc": "you are background motion right now.",
    }
    rows = []
    banks = tuple(sample_banks or DIALOGUE_VOICE_SAMPLE_BANKS)
    for index, bank_id in enumerate(banks):
        bank_key = str(bank_id or "").strip().lower()
        line = choose_dialogue_line(
            bank_key,
            seed=seed,
            npc_eid=npc_eid,
            topic_id=bank_key,
            count=index,
            style_profile=style,
            **slots,
        )
        if not line:
            continue
        rows.append(
            {
                "bank_id": bank_key,
                "line": line,
                "voice_quality": style.get("voice_quality", ""),
                "register": style.get("register", ""),
                "area_type": style.get("area_type", ""),
                "district_type": style.get("district_type", ""),
                "role_id": style.get("role_id", ""),
            }
        )
    return tuple(rows)
