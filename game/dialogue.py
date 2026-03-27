"""Shared dialogue topic definitions and deterministic line variation."""

from __future__ import annotations

import random


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
    "services",
    "hours",
    "owner",
    "security",
    "access",
    "entry",
    "keyholder",
    "purpose",
    "apologize",
    "leave",
    "local",
    "concern",
    "detail",
    "opportunities",
    "contract",
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
    "services": {
        "label": "What goes on there?",
        "root": False,
        "unlocks": ("trade",),
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
        "unlocks": ("access", "entry", "keyholder"),
    },
    "access": {
        "label": "How is it secured?",
        "root": False,
        "unlocks": ("entry", "keyholder"),
    },
    "entry": {
        "label": "Is there another way in?",
        "root": False,
        "unlocks": (),
    },
    "keyholder": {
        "label": "Who carries access?",
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
        "unlocks": ("concern", "detail", "history"),
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
        "unlocks": ("objective", "angle", "risk", "contract"),
    },
    "contract": {
        "label": "Any contracts going?",
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
    "opportunities",
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
    "opportunities",
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
    "introduction_offer_caution",
    "vouch_offer",
    "vouch_repeat",
    "vouch_offer_caution",
    "trade_yes_caution",
    "farewell",
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
    "contacts_offer_caution": (
        "Keep it quiet, but try {contact_place}.",
        "I can point you at {contact_place}, just do not make noise about it.",
        "Start with {contact_place}, and keep my name out of your mouth unless you need it.",
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
    "vouch_offer_caution": (
        "You can use my name, but keep the ask small.",
        "I will vouch once, quietly. Do not make me regret it.",
        "Use my name if you need to, just do not turn it into a scene.",
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
    "farewell": (
        "Take care.",
        "Alright. Stay sharp.",
        "See you around.",
        "Keep your head down.",
        "Watch yourself.",
        "Good luck out there.",
        "Careful out there.",
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

    if topic_id == "workplace" and context.get("workplace_here"):
        return "Do you work here?"
    if topic_id == "organization" and context.get("workplace_name"):
        return f"Who do you work for at {context['workplace_name']}?"
    if topic_id == "supervisor" and context.get("workplace_here"):
        return "Who runs things here?"
    if topic_id == "supervisor" and context.get("workplace_name"):
        return f"Who runs things at {context['workplace_name']}?"
    if topic_id == "coworkers" and context.get("workplace_here"):
        return "Who else works here?"
    if topic_id == "coworkers" and context.get("workplace_name"):
        return f"Who else works at {context['workplace_name']}?"
    if topic_id == "people" and context.get("workplace_here"):
        return "Who should I know here?"
    if topic_id == "people" and context.get("workplace_name"):
        return f"Who should I know around {context['workplace_name']}?"
    if topic_id == "people" and context.get("social_lead_name"):
        return "Who should I know around here?"
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
    if topic_id == "purpose" and context.get("guarded"):
        return "I'm not here for trouble."
    if topic_id == "apologize" and context.get("guarded"):
        return "Sorry. My mistake."
    if topic_id == "leave" and context.get("guarded"):
        return "I'll go."
    if topic_id == "services" and context.get("owner_place_name"):
        return f"What goes on at {context['owner_place_name']}?"
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
