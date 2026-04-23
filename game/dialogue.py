"""Shared dialogue topic definitions and deterministic line variation."""

from __future__ import annotations

import random
import string


TOPIC_ORDER = (
    "name",
    "history",
    "job",
    "routine",
    "workplace",
    "organization",
    "supervisor",
    "coworkers",
    "people",
    "hire",
    "hire_manager",
    "hire_staff",
    "fire",
    "services",
    "service_fuel",
    "service_repair",
    "service_banking",
    "service_insurance",
    "service_rest",
    "service_transit",
    "service_rail",
    "service_bus",
    "service_shuttle",
    "service_ferry",
    "service_intel",
    "service_trade",
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
    "concern",
    "detail",
    "opportunities",
    "fallout",
    "contract",
    "side_job",
    "hire_runner",
    "backup_orders",
    "backup_follow",
    "backup_hold",
    "backup_distract",
    "backup_goto_wait",
    "backup_wait_return",
    "backup_kill",
    "objective",
    "angle",
    "risk",
    "attention",
    "weird",
    "pry",
    "insult",
    "contacts",
    "introduction",
    "vouch",
    "trade",
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
        "unlocks": (),
    },
    "job": {
        "label": "What do you do?",
        "root": True,
        "unlocks": ("routine", "workplace", "organization"),
    },
    "routine": {
        "label": "What does your day look like?",
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
        "unlocks": ("supervisor", "coworkers", "people"),
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
    "hire": {
        "label": "Want a job?",
        "root": True,
        "unlocks": ("hire_manager", "hire_staff"),
    },
    "hire_manager": {
        "label": "Run the place.",
        "root": False,
        "unlocks": (),
    },
    "hire_staff": {
        "label": "Take a staff shift.",
        "root": False,
        "unlocks": (),
    },
    "fire": {
        "label": "We need to talk about your job.",
        "root": True,
        "unlocks": (),
    },
    "services": {
        "label": "What goes on there?",
        "root": False,
        "unlocks": (
            "service_fuel",
            "service_repair",
            "service_banking",
            "service_insurance",
            "service_rest",
            "service_transit",
            "service_rail",
            "service_bus",
            "service_shuttle",
            "service_ferry",
            "service_intel",
            "service_trade",
            "service_used_cars",
            "service_vehicle_fetch",
            "service_gaming",
            "trade",
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
    "service_banking": {
        "label": "Any bank or broker nearby?",
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
    "service_intel": {
        "label": "Anywhere selling intel nearby?",
        "root": False,
        "unlocks": (),
    },
    "service_trade": {
        "label": "Any shopping around here?",
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
            "concern",
            "detail",
            "fallout",
            "history",
            "service_fuel",
            "service_repair",
            "service_banking",
            "service_insurance",
            "service_rest",
            "service_transit",
            "service_rail",
            "service_bus",
            "service_shuttle",
            "service_ferry",
            "service_intel",
            "service_trade",
            "service_used_cars",
            "service_vehicle_fetch",
            "service_gaming",
        ),
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
        "label": "Your sister... [creepy] ",
        "root": False,
        "unlocks": (),
    },
    "pry": {
        "label": "Whats your interest here, anyway? [hostile]",
        "root": False,
        "unlocks": (),
    },
    "insult": {
        "label": "Your momma... [hostile]",
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
        "unlocks": (),
    },
    "bye": {
        "label": "Goodbye.",
        "root": True,
        "unlocks": (),
    },
    "payoff": {
        "label": "I can make it worth your while to forget you saw me.",
        "root": False,
        "unlocks": (),
    },
    "fence": {
        "label": "I have some things I need to move quietly.",
        "root": False,
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
    "job": (
        "So what do you do around here?",
        "What kind of work do you do?",
        "What do you do for a living?",
    ),
    "workplace": (
        "Where do you usually work?",
        "What place do you work out of?",
        "Is {workplace_name} where you spend most of your time?",
    ),
    "organization": (
        "Who are you tied in with there?",
        "Whose outfit is {workplace_name}?",
        "Are you working for somebody there, or is it your show?",
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
    "services": (
        "What does the place actually do?",
        "So what are people coming there for?",
        "What does {owner_place_name} mostly handle?",
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
    ),
    "objective": (
        "What would actually help me here?",
        "If you were me, what would you focus on?",
        "What's the move on {objective_title}?",
    ),
    "angle": (
        "Where would you start?",
        "What's the first move?",
        "So what's the cleanest angle?",
    ),
    "risk": (
        "What's the catch?",
        "What could go wrong fastest?",
        "What's the catch with {primary_opportunity_title}?",
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
    ),
    "introduction": (
        "Would you introduce me to {social_lead_name}?",
        "Think you could put me in touch with {social_lead_name}?",
        "Can you connect me with {social_lead_name}?",
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
    ),
    "bye": (
        "Alright. Take care.",
        "That is enough for now. Later.",
        "Appreciate it. I'll let you get back to it.",
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
    "insult",
    "trade",
    "bye",
    "payoff",
    "fence",
    "hire",
    "hire_manager",
    "hire_staff",
    "fire",
    "hire_runner",
    "backup_orders",
    "backup_follow",
    "backup_hold",
    "backup_distract",
    "backup_goto_wait",
    "backup_wait_return",
    "backup_kill",
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
            "The streets talk louder than people think.",
        ),
    },
    "frontier": {
        "farewell_tags": (
            "The road runs long out here.",
            "The weather turns quick out here.",
            "Always keep one eye on the horizon.",
        ),
        "catch_phrases": (
            "Even road dust remembers...",
            "Nothing stays easy for long out here.",
            "The frontier holds on to things.",
            "The distance out here is honest.",
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
            "The port knows what moves and what stays.",
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
            "The trees remember faces.",
            "Out here, you can't help but listen.",
        ),
    },
}


DISTRICT_STYLE_HINTS = {
    "industrial": {
        "catch_phrases": (
            "The shift whistle never lies.",
            "Keep your gears straight.",
            "The floor never forgets.",
            "A person's sweat tells the honest story.",
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
        "address_terms": (
            "citizen",
            "friend",
            "civillian",
        ),
    },
    "entertainment": {
        "catch_phrases": (
            "The crowd hears everything.",
            "The show's still running.",
            "The applause covers a lot.",
            "The applause is the loudest voice in the room.",
            "The applause is the toughest critic.",
        ),
        "address_terms": (
            "friend",
            "dear",
            "patron",
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
    },
    "thief": {
        "register": "rough",
        "lead_ins": (
            "Straight up,",
            "Look,",
            "Real talk,",
            "Ay, peep this :",
        ),
        "catch_phrases": (
            "Loose talk costs.",
            "Keep it quiet.",
            "You better not be the one time",
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
            "Bartenders are the universe's secret keepers.",
        ),
        "address_terms": (
            "friend",
            "there",
            "pal",
            "buddy",
        ),
    },
    "courier": {
        "catch_phrases": (
            "The road keeps no secrets.",
            "Every movement tells a story.",
        ),
    },
    "medic": {
        "catch_phrases": (
            "People talk when they hurt.",
            "Care comes around.",
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
        ),
        "address_terms": (
            "associate",
            "friend",
        ),
    },
}


REGISTER_STYLE_HINTS = {
    "plain": {
        "lead_ins": (),
        "address_terms": (),
        "farewell_tags": (),
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
    },
    "clipped": {
        "lead_ins": (
            "Right,",
            "Fine,",
            "Alright,",
            "Simply put,",
        ),
        "address_terms": (),
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
    },
}


STYLE_LEAD_IN_BANKS = {
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
    "concern",
    "detail_rumor",
    "detail_opportunity",
}


STYLE_CATCH_BANKS = {
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
    "local_none",
    "concern",
    "detail_rumor",
    "detail_opportunity",
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
        "You have a question, ask it.",
        "I haven't shot you yet, so go on.",
    ),
    "greet_wary": (
        "Yeah?",
        "Need something?",
        "You stopping me for a reason?",
        "Alright. What is it?",
    ),
    "greet_neutral": (
        "Sure. What do you need?",
        "Yeah, go on.",
        "What can I do for you?",
        "You wanted something?",
        "Fair enough. What is on your mind?",
        "Yeah? Go ahead.",
    ),
    "greet_friendly": (
        "Hey. What is up?",
        "Sure thing. What do you want to know?",
        "Good to see you. Need anything?",
        "Yeah, talk to me.",
    ),
    "greet_introduced": (
        "If {intro_source_name} pointed you my way, I can spare a minute.",
        "{intro_source_name} mentioned you. Go on.",
        "Alright. If {intro_source_name} sent you, talk.",
    ),
    "name_first": (
        "I am {npc_name}.",
        "Name's {npc_name}.",
        "People call me {npc_name}.",
        "{npc_name}. That is me.",
    ),
    "name_repeat": (
        "Still {npc_name}.",
        "Same answer: {npc_name}.",
        "{npc_name}, unless I missed something.",
        "You already asked. It is {npc_name}.",
    ),
    "name_guarded": (
        "{npc_name}. That is enough for now.",
        "It is {npc_name}. Keep moving.",
        "{npc_name}. Do not make this strange.",
    ),
    "history": (
        "{history_summary}",
        "Long story short, {history_summary}",
        "Around here? {history_summary}",
        "If you want the short version, {history_summary}",
    ),
    "history_none": (
        "Long enough to recognize the regulars.",
        "A while. Enough to know the rhythm.",
        "Long enough that new faces stand out.",
    ),
    "job_first": (
        "I work as {career_text}.",
        "Mostly {career_text} work.",
        "I am on {career_text} duty most days.",
        "{career_text} work pays the bills.",
    ),
    "job_repeat": (
        "Still {career_text}.",
        "No career change since a minute ago. {career_text}.",
        "Same job: {career_text}.",
    ),
    "job_none": (
        "Nothing tidy enough to put on a sign.",
        "Odd jobs, mostly.",
        "A little of whatever keeps me moving.",
        "Nothing official worth bragging about.",
    ),
    "routine": (
        "{routine_summary}",
        "Most days, {routine_summary}",
        "Usually, {routine_summary}",
        "That depends on the day, but {routine_summary}",
    ),
    "routine_none": (
        "Nothing steady enough to map out.",
        "No clean routine worth naming.",
        "It changes too much to call it a routine.",
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
    ),
    "workplace_none": (
        "No fixed place right now.",
        "Nowhere steady enough to point to.",
        "I drift more than I clock in.",
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
    ),
    "people": (
        "{people_summary}",
        "If you are looking for names, {people_summary}",
        "Start here: {people_summary}",
    ),
    "people_none": (
        "No one I would point you at just yet.",
        "Nobody I feel like handing over cold.",
        "It wouldn't make sense for me to stick my neck out when your name keeps popping up on the wrong side of reports.",
        "Not a clean name worth passing along from me right now.",
    ),
    "chatter_offense": (
        "You hear about {trouble_summary}?",
        "Word is there was trouble at {topic_place}.",
        "People keep talking about {trouble_summary}.",
        "Something went down at {topic_place}. People are still edgy about it.",
        "There was a thing with {trouble_summary}. Nerved a few people up.",
    ),
    "chatter_world_trait": (
        "People keep saying {trait_claim}.",
        "I keep hearing that {trait_claim_lc}",
        "Whole block is repeating that {trait_claim_lc}",
        "{trait_claim} is the word going around.",
        "Everyone has an opinion about {trait_claim_lc}",
    ),
    "chatter_security": (
        "{topic_place} runs {security_summary}.",
        "If you are wondering, {topic_place} runs {security_summary}.",
        "Everyone around there knows {security_summary_lc}",
        "Security around {topic_place}: {security_summary}.",
        "Place like {topic_place} does not take chances. {security_summary}.",
    ),
    "chatter_supervisor": (
        "{supervisor_name} is the one really running {topic_place}.",
        "Far as I can tell, {supervisor_name} runs {topic_place}.",
        "{supervisor_name} keeps the floor at {topic_place} moving.",
        "If you want the real authority at {topic_place}, look at {supervisor_name}.",
        "Ask around {topic_place} and {supervisor_name} is the name that comes up.",
    ),
    "chatter_schedule": (
        "{topic_place} usually runs {schedule_text}.",
        "Most days, {topic_place} keeps {schedule_text}.",
        "If the doors move on time, {topic_place} runs {schedule_text}.",
        "Schedule around {topic_place} tends to be {schedule_text}.",
        "{topic_place} keeps regular hours: {schedule_text}.",
    ),
    "chatter_shift": (
        "Staff shift at {topic_place} usually runs {schedule_text}.",
        "Most days, the shift at {topic_place} is {schedule_text}.",
        "If payroll lands on time, staff at {topic_place} work {schedule_text}.",
        "The shift around {topic_place} tends to be {schedule_text}.",
        "People on that floor at {topic_place} are usually on {schedule_text}.",
    ),
    "chatter_opportunity": (
        "{opportunity_title} sounds live {distance_phrase}. {opportunity_summary}",
        "Word is {opportunity_title} is {distance_phrase}. {opportunity_summary}",
        "People keep pointing toward {opportunity_title} {distance_phrase}. {opportunity_summary}",
        "Best street lead I heard is {opportunity_title} {distance_phrase}. {opportunity_summary}",
        "{opportunity_title} is the one people still mention {distance_phrase}. {opportunity_summary}",
    ),
    "chatter_illegal_goods": (
        "If you want hot goods, {topic_place} is where people look.",
        "Word is {topic_place} moves the kind of stock nobody lists openly.",
        "People say {topic_place} can find things that never make the front counter.",
        "If someone needs quiet merchandise, they drift toward {topic_place}.",
        "{topic_place} has a reputation for back-counter goods.",
    ),
    "chatter_check_in": (
        "How are things at {topic_place} these days?",
        "Everything holding together around {topic_place}?",
        "How is {topic_place} treating you lately?",
        "What is the mood like over at {topic_place}?",
        "Any word on what is happening at {topic_place}?",
    ),
    "chatter_actor_reputation": (
        "Word on {actor_name}: {reputation_read_lc}",
        "Around here, {actor_name} keeps coming up. {reputation_read}",
        "I keep hearing the same thing about {actor_name}: {reputation_read_lc}",
        "People keep bringing up {actor_name}. {reputation_read}",
        "{actor_name} is the name in half the talk lately. {reputation_read}",
    ),
    "chatter_conflict_side": (
        "Word is {conflict_summary_lc}",
        "People keep saying {conflict_summary_lc}",
        "Every version of that story ends the same way: {conflict_summary_lc}",
        "If it goes loud again, {conflict_summary_lc}",
        "The room keeps leaning one way on that: {conflict_summary_lc}",
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
    ),
    "security": (
        "{security_summary}",
        "From what I see, {security_summary}",
        "If you are asking me, {security_summary}",
        "That place? {security_summary}",
    ),
    "security_none": (
        "Nothing sharper than an ordinary lock.",
        "No special security worth mentioning.",
        "About what you would expect from an ordinary place.",
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
    ),
    "purpose_defuse": (
        "Fine. Keep it quick and keep it clean.",
        "Alright. Then do not give me another reason to stop you.",
        "Maybe. Stay straight and we are done here.",
    ),
    "purpose_wary": (
        "Maybe. I am still watching you.",
        "Could be. I still do not like it.",
        "I hear you. I am not convinced.",
    ),
    "purpose_fail": (
        "I am not buying that.",
        "That is not good enough.",
        "No. Try a better story somewhere else.",
    ),
    "apologize_defuse": (
        "Fine. Do not make it a pattern.",
        "Alright. Then clean it up and move on.",
        "I will let that sit, once. Do not press it.",
    ),
    "apologize_wary": (
        "Words are cheap. I am still watching you.",
        "Maybe you mean it. I am still keeping an eye on you.",
        "Fine. I am not relaxed about it.",
    ),
    "apologize_fail": (
        "Save it. You already crossed the line.",
        "Too late for a soft apology.",
        "No. You do not get to smooth it over that easily.",
    ),
    "leave_defuse": (
        "Good. Clear out and we are done.",
        "Then go. We can leave it there.",
        "Fine. Move along and let that be the end of it.",
    ),
    "leave_wary": (
        "Do that. Quickly.",
        "Good. Start moving.",
        "Then move, and do not make me ask twice.",
    ),
    "leave_fail": (
        "You should have done that before I had to say it.",
        "Now you are just behind the count.",
        "Move, before this gets worse.",
    ),
    "local_rumor": (
        "{rumor_line}",
        "{rumor_line}",
        "If you ask me, {rumor_line_lc}",
    ),
    "local_opportunity": (
        "{opportunity_summary}",
        "Word around here is: {opportunity_summary}",
        "There is something worth knowing. {opportunity_summary}",
        "Something circulating locally. {opportunity_summary}",
    ),
    "local_other_bond": (
        "You should probably talk to {other_name} too.",
        "{other_name} hears more than I do.",
        "If anyone knows more, it is {other_name}.",
    ),
    "local_none": (
        "Quiet enough, for the moment.",
        "Nothing clean enough to pass along right now.",
        "Usual street noise. Nothing sharp.",
        "Nothing worth your time from me today.",
        "Slow stretch right now. I would not count on that lasting.",
    ),
    "initiative_name": (
        "And you?",
        "So what should I call you?",
        "You got a name too, or are we skipping that part?",
    ),
    "initiative_history": (
        "You new here, or just taking inventory?",
        "You asking because you plan to stick around?",
        "That curiosity, or are you trying to place me?",
    ),
    "initiative_job": (
        "You asking out of curiosity, or is there a reason?",
        "Why the interest?",
        "That just curiosity, or are you headed somewhere with it?",
    ),
    "initiative_workplace": (
        "You looking for me there, or just drawing a map?",
        "That place matter to you for a reason?",
        "You need the location, or just the shape of my day?",
    ),
    "initiative_organization": (
        "You keeping score on who answers to who?",
        "That kind of hierarchy matter to you for a reason?",
        "You asking about the outfit, or about me?",
    ),
    "initiative_people": (
        "You looking for friends, or leverage?",
        "You collecting names, or actually looking to meet someone?",
        "That you trying to build a circle, or just pull a thread?",
    ),
    "initiative_local": (
        "You looking for work, trouble, or directions?",
        "You after a lead, or just getting your bearings?",
        "You trying to get the lay of the block, or is there something specific you need?",
    ),
    "initiative_concern": (
        "You trying to stay ahead of trouble, or step into it?",
        "That you being careful, or curious?",
        "Good question. You planning around it?",
    ),
    "initiative_detail": (
        "You like the useful part, I can respect that.",
        "So you are listening for the part that matters.",
        "Alright. You want the sharp version.",
    ),
    "initiative_opportunities": (
        "You looking for money, leverage, or just a way in?",
        "You after a score, or do you just like hearing the map out loud?",
        "That you planning something, or just taking the temperature?",
    ),
    "initiative_risk": (
        "You planning something that needs the caution?",
        "Good. Most people ask for the angle and forget the cost.",
        "So you are thinking about how this goes bad first.",
    ),
    "initiative_attention": (
        "Then keep your head down if you can.",
        "Good instinct. Too many people ignore that part.",
        "That is the right question, honestly.",
    ),
    "initiative_contacts": (
        "If I point you at someone, are you going to handle it cleanly?",
        "You looking for a real connection, or just another name to lean on?",
        "Depends what you think you are going to do with the introduction.",
    ),
    "initiative_introduction": (
        "Depends what you plan to say when you meet them.",
        "Maybe. That kind of introduction matters.",
        "That depends how clean you mean to keep it.",
    ),
    "initiative_services": (
        "You looking for the place, or the kind of people around it?",
        "That you scouting the room, or shopping?",
        "Useful to know the sign before you walk under it.",
    ),
    "initiative_security": (
        "That question alone tells me you are thinking past the front door.",
        "Most people do not ask that unless they need the real picture.",
        "You are planning carefully, at least.",
    ),
    "initiative_access": (
        "Access is usually the part people underestimate.",
        "That is where places really tell you what they are.",
        "Good. Doors matter more than signs.",
    ),
    "initiative_entry": (
        "There is always the obvious way and the honest way.",
        "People learn a lot from how a place is entered.",
        "That is a better question than most.",
    ),
    "initiative_weak_point": (
        "Every place pretends not to have one.",
        "Soft spots are easier to talk about than fix.",
        "That is the question owners hate most.",
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
    ),
    "opportunities": (
        "{opportunity_summary}",
        "Here is what sounds live from where I stand: {opportunity_summary}",
        "One worth noting: {opportunity_summary}",
        "If you are looking around, here is one: {opportunity_summary}",
    ),
    "opportunities_none": (
        "Nothing is lining up cleanly right this second.",
        "No clear opening jumps out at me right now.",
        "Not a clean angle worth betting on from here.",
        "Things are too quiet to call anything solid.",
        "Nothing sharp enough to point at from where I stand.",
        "I would not chase anything right now.",
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
    ),
    "objective": (
        "{objective_summary}",
        "If you want my read, {objective_summary_lc}",
        "For the shape of this run, {objective_summary_lc}",
    ),
    "objective_none": (
        "Depends what you are chasing.",
        "That is hard to answer without a real direction.",
        "No clean answer there from me.",
    ),
    "angle": (
        "{angle_summary}",
        "Where I would push: {angle_summary}",
        "Best first move: {angle_summary}",
        "Starting point: {angle_summary}",
    ),
    "angle_none": (
        "Nothing clean enough to point at first.",
        "No clear lead I would start with.",
        "I do not have a clean first move for you there.",
        "Hard to say where to push without more to go on.",
        "Nothing I would commit to from here.",
    ),
    "risk": (
        "{risk_summary}",
        "Here is the catch. {risk_summary}",
        "Worth knowing. {risk_summary}",
        "Keep this in mind. {risk_summary}",
    ),
    "risk_none": (
        "Same risk as anything else around here: people, distance, and bad timing.",
        "Nothing sharper than the usual trouble.",
        "No cleaner warning than the obvious one.",
        "Standard risks. Nothing unusual from where I stand.",
        "Watch for the things you always watch for.",
    ),
    "attention": (
        "{attention_summary}",
        "If you want the plain read, {attention_summary_lc}",
        "From where I am standing, {attention_summary_lc}",
    ),
    "attention_none": (
        "Nothing sharp enough to call real heat yet.",
        "You are not setting the whole block off right now.",
        "No more attention than the usual street noise.",
        "You are reading clean from out here.",
        "Nobody is pointing at you specifically.",
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
    ),
    "repeat_wary": (
        "You keep circling the same question.",
        "You are starting to wear this thin.",
        "Ask it again and I am going to stop being polite.",
    ),
    "repeat_fail": (
        "That is enough. I already answered you.",
        "You keep grinding the same question. We are done.",
        "No. I am not doing this loop with you.",
    ),
    "repeat_bonus": (
        "Alright, the useful part is this: {extra_detail_lc}",
        "If you are going to keep at it, fine: {extra_detail_lc}",
        "Since you keep worrying at it, here is the part that matters: {extra_detail_lc}",
    ),
    "contacts_offer": (
        "Depends what you need, but I can point you at {contact_place}.",
        "If you are trying to get somewhere, start with {contact_place}.",
        "For a local way in, try {contact_place}.",
    ),
    "contacts_repeat": (
        "Same answer as before: {contact_place}.",
        "Still telling you to start with {contact_place}.",
        "{contact_place} is still my best answer.",
    ),
    "contacts_soft_no": (
        "Not yet. I like to know who I am steering people toward.",
        "Maybe later. I do not hand names out cold.",
        "Give it time. I do not spend favors that fast.",
        "I am still figuring out what I think of you.",
        "Ask me again after we have had more time.",
    ),
    "contacts_caution_no": (
        "Not while attention is up. Keep your head down first.",
        "People are noticing enough already. I am not opening another line for you right now.",
        "Cool the heat off first. I am not pointing you at anyone while eyes are up.",
    ),
    "contacts_caution_no_guard": (
        "No. Patrol memory is long, and I am not putting another name in your path while the city is keyed up.",
        "Not with this much heat. The next person you touch turns into a report.",
        "No. You are too hot for me to point at someone else cleanly.",
    ),
    "contacts_caution_no_worker": (
        "No. I am not dragging a coworker into this while the floor is already twitchy.",
        "Not on a hot day. I like keeping my job.",
        "No. I am not putting another worker in your orbit while eyes are up.",
    ),
    "contacts_caution_no_merchant": (
        "Not with this kind of attention on you. People remember who was seen talking at the counter.",
        "No. Bad heat turns every introduction into shop gossip.",
        "Cool it down first. I am not sending trouble through my front room.",
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
        "If you are after a real name, try {contact_name}. They are {contact_context}.",
        "You might want {contact_name}. They are {contact_context}.",
        "For a person, start with {contact_name}. They are {contact_context}.",
    ),
    "contacts_person_repeat": (
        "Same name as before: {contact_name}. They are still {contact_context}.",
        "I already gave you the best person I have: {contact_name}.",
        "Still saying {contact_name}. That is where I would start.",
    ),
    "contacts_hard_no": (
        "No.",
        "Not for you.",
        "I am not putting you on anyone right now.",
    ),
    "introduction_offer": (
        "Tell {contact_name} I pointed you their way. They are {contact_context}.",
        "Use my name with {contact_name}. They are {contact_context}.",
        "If you are going to start somewhere, start with {contact_name}. They are {contact_context}.",
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
    ),
    "introduction_caution_no": (
        "Not with this much attention on you. That kind of introduction sticks.",
        "No. Not until things cool off around you.",
        "I am not connecting you to someone else while the city is still watching.",
    ),
    "introduction_offer_caution": (
        "You can use my name with {contact_name}, but do it quietly. They are {contact_context}.",
        "Talk to {contact_name} if you have to, just keep it subtle. They are {contact_context}.",
        "I will point you at {contact_name}, but do not burn the line. They are {contact_context}.",
    ),
    "vouch_offer": (
        "Tell them {npc_name} said you were alright.",
        "Use my name. It should smooth things a little.",
        "I can put a little weight behind your name there.",
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
        "Listen, once I trust you more, i'll reconsider.... but no.",
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
    ),
    "trade_yes_caution": (
        "Fine, but keep it quick.",
        "Alright. Quiet business only.",
        "Yeah, but let us not make this look like a meeting.",
    ),
    "trade_yes_caution_merchant": (
        "Fine. Keep it quick and make it look like shopping.",
        "Alright. Quick business, no crowd, no scene.",
        "Yeah, but I am not turning my counter into gossip.",
    ),
    "trade_yes_caution_chaotic": (
        "Yeah. Fast hands, short words.",
        "Alright, but move it. I do not hold hot business for long.",
        "Sure. Quick deal, then disappear.",
    ),
    "trade_no": (
        "Not here.",
        "I am not set up to sell anything.",
        "No trade from me right now.",
    ),
    "contract_offer": (
        "Word came down about a problem that needs handling. {target_description} Keep it quiet and you walk with {reward_hint}.",
        "Between you and me, someone has credits on a name. {target_description} Clean and quiet, that is {reward_hint}.",
        "I have a standing job. {target_description} Nobody asks questions, you collect {reward_hint}.",
        "There is work if you can handle things. {target_description} Score is {reward_hint}.",
        "Someone is paying to have a complication removed. {target_description} Do it right, you earn {reward_hint}.",
    ),
    "contract_repeat": (
        "Same job, still open. {target_description} Confirm the work for {reward_hint}.",
        "Contract stands. {target_description} You know the rate: {reward_hint}.",
        "Still on offer. {target_description} Get it done, collect {reward_hint}.",
    ),
    "contract_accepted": (
        "Good. No details, no noise. Come back when it is finished.",
        "Smart. Payment is ready when the work is done.",
        "Deal. I do not need a story, just results.",
        "You have my attention. Do not waste it.",
    ),
    "contract_no_contract": (
        "Nothing right now.",
        "No work on offer at the moment.",
        "Check back later. Nothing on the table right now.",
    ),
    "side_job_offer": (
        "Maybe. {side_job_summary} Keep it clean and you walk with {reward_hint}, plus a better name with {favor_target}.",
        "Yeah, one small thing. {side_job_summary} Do it right and it pays {reward_hint}, and {favor_target} remembers it.",
        "There is a quiet errand going. {side_job_summary} Handle it softly and you collect {reward_hint} with a little goodwill attached.",
        "I could use a discreet hand. {side_job_summary} Bring it through without noise and that is {reward_hint}, plus a favor with {favor_target}.",
    ),
    "side_job_repeat": (
        "Same side job. {side_job_summary} Finish it clean and the rate stays {reward_hint}.",
        "Same errand, still open. {side_job_summary} Reward is still {reward_hint}.",
        "Nothing changed. {side_job_summary} Bring it through quietly and collect {reward_hint}.",
    ),
    "side_job_accepted": (
        "Good. Keep it moving and do not make me regret the ask.",
        "Fine. Quiet hands, short trail, then we are square.",
        "That works. Make the drop and come back clean.",
        "Good. Do it right and I will remember it.",
    ),
    "side_job_none": (
        "Nothing small and quiet right now.",
        "No side work on the table at the moment.",
        "Not the kind of errand I hand out lightly. Nothing open right now.",
    ),
    "farewell": (
        "Take care.",
        "Alright. Stay sharp.",
        "See you around.",
        "Keep your head down.",
        "Watch yourself.",
        "Good luck out there.",
        "Careful out there.",
    ),
    "payoff_accept": (
        "Fine. {payoff_cost} and I did not see anything.",
        "That works. {payoff_cost} and we are done here.",
        "Hand it over. {payoff_cost} and I forget your face.",
        "Alright. {payoff_cost} and this conversation did not happen.",
        "Fair enough. {payoff_cost} and you were never here.",
        "{payoff_cost}. And stay out of my sight for a while.",
    ),
    "payoff_refuse_broke": (
        "That is not enough. Come back when you are serious.",
        "You call that a payoff? Walk away.",
        "Not with that. Try again when you have something real.",
        "That does not cover it. Walk.",
        "I am worth more than that. Come back with more.",
    ),
    "payoff_refuse_clean": (
        "I am not that kind of person.",
        "Keep your money.",
        "That is not how I do things.",
        "No. Take your credits and go.",
        "I don't work that way.",
    ),
    "payoff_cooldown": (
        "We already handled this. Do not push it.",
        "You already paid. That window is closed.",
        "That deal was made. Don't come looking for another one.",
        "I said we were done. Stay out of trouble.",
    ),
    "fence_accept": (
        "{fence_payout} and that stock does not exist. Leave the bag.",
        "I can do {fence_payout}. No names, no receipts.",
        "Alright. {fence_payout} and I forget I ever saw what you were carrying.",
        "Done. {fence_payout}. You were never here with those.",
        "{fence_payout} is what I can move. Take it or walk.",
    ),
    "fence_decline_corrupt": (
        "Not today. I am already running too much heat right now.",
        "Wrong time. Come back when things have cooled down.",
        "I can't take anything right now. The block is too hot.",
        "Not this week. You're going to have to sit on it.",
    ),
    "fence_decline_clean": (
        "That's not a conversation I have. Move on.",
        "Wrong person. I don't move product.",
        "I don't know what you're implying, but no.",
        "Keep that away from me.",
    ),
    "fence_cooldown": (
        "We just did this. Give it time.",
        "I haven't moved the last batch yet. Not yet.",
        "Come back in a few days.",
        "Too soon. You're making me nervous.",
    ),
    "hire_runner_accept": (
        "{hire_runner_cost} and I stay with you for {hire_runner_hours}. Keep moving.",
        "Alright. {hire_runner_cost}. I watch your flank for {hire_runner_hours}.",
        "{hire_runner_cost} and I am on your side for {hire_runner_hours}.",
        "Fine. {hire_runner_cost}. Stay where I can see you.",
        "You bought another pair of hands. {hire_runner_cost}. Lead.",
    ),
    "hire_runner_decline_clean": (
        "I don't do that kind of arrangement. Move along.",
        "That's not something I get involved in.",
        "Wrong person for that conversation.",
        "I keep my head down. You should too.",
    ),
    "hire_runner_decline_broke": (
        "I've got a memory like a trap, but not that cheap.",
        "That's not enough for me to forget anything.",
        "Come back when you've got real money.",
        "Not worth the risk for that amount.",
    ),
    "hire_runner_already_hired": (
        "We already have an arrangement. I am with you.",
        "You're covered. Keep moving.",
        "I haven't wandered off. Lead.",
        "Still on your side. Just do not lose me.",
    ),
    "backup_orders": (
        "Yeah. You want me close, posted up, making noise, or putting someone down?",
        "Say it plain. I can stay on you, hold a spot, draw eyes, or handle a marked problem.",
        "Alright. Give the word. Passive cover, a position to hold, a distraction, or a harder push?",
    ),
    "backup_follow": (
        "Alright. Back to passive cover. I stay near you and keep my eyes open.",
        "Copy. I am back on your shoulder unless something live shows up.",
        "Fine. I stick close and watch your flank again.",
    ),
    "backup_hold": (
        "Got it. I will hold here and keep watch.",
        "I can post here. Come find me when you are ready to move.",
        "Here works. I stay put and keep my head up.",
    ),
    "backup_distract": (
        "Sure. I will pull some eyes away from you.",
        "Got it. I will make enough noise to bend attention.",
        "I can stir things up a little. Move when you are ready.",
    ),
    "backup_goto_wait": (
        "Alright. I will head to {backup_marked_spot} and sit tight.",
        "Copy. I will move to {backup_marked_spot} and wait there.",
        "Marked spot, then quiet. I have it.",
    ),
    "backup_wait_return": (
        "Got it. I will post at {backup_marked_spot}, wait a bit, then circle back.",
        "I can do that. {backup_marked_spot}, hold for a minute, then back to you.",
        "Alright. I will stage at {backup_marked_spot} and return after a short beat.",
    ),
    "backup_kill_trusted": (
        "If that is the move, I will handle {backup_kill_target}.",
        "You are sure? Fine. I will put {backup_kill_target} down.",
        "Alright. {backup_kill_target} is mine.",
    ),
    "backup_kill_paid": (
        "{backup_kill_cost} and I will make {backup_kill_target} stop being your problem.",
        "That is hazard-pay territory. {backup_kill_cost}, and I will handle {backup_kill_target}.",
        "For {backup_kill_cost}, I can put {backup_kill_target} in the ground.",
    ),
    "backup_kill_refuse": (
        "No clean shot from me on that.",
        "Mark somebody real if you want that kind of work.",
        "Not like that. Give me a real target or another order.",
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
):
    del seed
    del npc_eid
    area_type = str(area_type or "city").strip().lower() or "city"
    district_type = str(district_type or "unknown").strip().lower() or "unknown"
    role_id = str(role_id or "").strip().lower()
    tone = str(tone or "neutral").strip().lower() or "neutral"
    try:
        empathy = float(empathy)
    except (TypeError, ValueError):
        empathy = 0.5
    try:
        discipline = float(discipline)
    except (TypeError, ValueError):
        discipline = 0.5

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
    merged = {
        "register": register,
        "area_type": area_type,
        "district_type": district_type,
        "role_id": role_id,
        "tone": tone,
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
        "farewell_tags": _tuple_merge(
            area_profile.get("farewell_tags"),
            district_profile.get("farewell_tags"),
            register_profile.get("farewell_tags"),
        ),
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
    rng = random.Random(
        f"{seed}:dialogue-style:{npc_eid}:{bank_key}:{topic_id}:{count}:{district_type}:{area_type}:{role_id}"
    )
    result = text

    lead_ins = tuple(style_profile.get("lead_ins", ()) or ())
    address_terms = tuple(style_profile.get("address_terms", ()) or ())
    catch_phrases = tuple(style_profile.get("catch_phrases", ()) or ())
    farewell_tags = tuple(style_profile.get("farewell_tags", ()) or ()) or catch_phrases
    register = str(style_profile.get("register", "plain")).strip().lower() or "plain"

    if bank_key in STYLE_LEAD_IN_BANKS and lead_ins and register in {"official", "rough", "theatrical"}:
        result = _prepend_phrase(result, lead_ins[rng.randrange(len(lead_ins))])

    if bank_key in STYLE_ADDRESS_BANKS and address_terms:
        result = _with_address(result, address_terms[rng.randrange(len(address_terms))])

    if bank_key == "farewell" and farewell_tags:
        result = _append_phrase(result, farewell_tags[rng.randrange(len(farewell_tags))])
    elif bank_key in STYLE_CATCH_BANKS and catch_phrases:
        result = _append_phrase(result, catch_phrases[rng.randrange(len(catch_phrases))])

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

    if topic_id == "workplace" and context.get("workplace_here"):
        return "Do you work here?"
    if topic_id == "organization" and context.get("workplace_name"):
        if str(context.get("organization_role", "")).strip().lower() == "owner":
            return f"Is {context['workplace_name']} yours?"
        if context.get("workplace_here"):
            return "Who's the outfit behind this place?"
        return f"Who's the outfit behind {context['workplace_name']}?"
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
    if topic_id == "hire" and context.get("player_business_hire_name"):
        open_roles = tuple(
            str(role).strip().lower()
            for role in tuple(context.get("player_business_hire_roles", ()) or ())
            if str(role).strip()
        )
        if len(open_roles) > 1:
            return _with_hint(f"Want work at {context['player_business_hire_name']}?", "player_business_hire_fit_hint")
        if str(context.get("player_business_hire_role", "")).strip().lower() == "manager":
            return _with_hint(f"Want to run {context['player_business_hire_name']}?", "player_business_hire_fit_hint")
        return _with_hint(f"Want work at {context['player_business_hire_name']}?", "player_business_hire_fit_hint")
    if topic_id == "hire_manager" and context.get("player_business_hire_name"):
        return _with_hint(f"Would you run {context['player_business_hire_name']}?", "player_business_hire_manager_fit_hint")
    if topic_id == "hire_staff" and context.get("player_business_hire_name"):
        return _with_hint(f"Would you take a shift at {context['player_business_hire_name']}?", "player_business_hire_staff_fit_hint")
    if topic_id == "fire" and context.get("player_business_fire_name"):
        return f"I'm letting you go from {context['player_business_fire_name']}."
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
    if topic_id == "service_banking":
        return "Any bank or broker nearby?"
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
    if topic_id == "service_intel":
        return "Anywhere selling intel nearby?"
    if topic_id == "service_trade":
        return "Any shopping around here?"
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
    for key in ("npc_soft", "npc_wary", "npc_fail"):
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
    }
    for key in ("npc_soft", "npc_wary", "npc_fail"):
        rendered[key] = tuple(
            rendered_text
            for raw in tuple(normalized.get(key, ()) or ())
            if (rendered_text := _render_topic_text(raw, context, fallback=""))
        )
    return rendered


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


def topic_player_reaction_line(topic_id, *, seed, npc_eid, count=0, outcome="soft", context=None):
    prompt = topic_player_prompt(
        topic_id,
        seed=seed,
        npc_eid=npc_eid,
        count=count,
        context=context,
    )
    outcome_key = f"npc_{str(outcome or 'soft').strip().lower() or 'soft'}"
    options = tuple(prompt.get(outcome_key, ()))
    if not options:
        return ""
    chooser = random.Random(
        f"{seed}:dialogue-player-reaction:{npc_eid}:{topic_id}:{count}:{outcome_key}"
    )
    return str(options[chooser.randrange(len(options))]).strip()


def topic_player_line(topic_id, *, seed, npc_eid, count=0, context=None, previous_topic_id="", total_asked=0):
    topic_id = str(topic_id or "").strip().lower()
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


def choose_dialogue_line(bank_id, *, seed, npc_eid, topic_id="", count=0, salt="", style_profile=None, **slots):
    options = tuple(DIALOGUE_BANKS.get(str(bank_id or "").strip().lower(), ()))
    if not options:
        return ""

    chooser = random.Random(
        f"{seed}:dialogue:{npc_eid}:{bank_id}:{topic_id}:{count}:{salt}"
    )
    template = options[chooser.randrange(len(options))]
    safe_slots = {key: str(value) for key, value in slots.items()}
    line = str(template).format(**safe_slots).strip()
    return style_dialogue_line(
        line,
        seed=seed,
        npc_eid=npc_eid,
        bank_id=bank_id,
        topic_id=topic_id,
        count=count,
        style_profile=style_profile,
    )
