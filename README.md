#BAKERRRR
## The Game:
### BAKERRRR is a terminal-native systemic urban roguelike prototype about moving through a procedurally generated society.


* Instead of treating the world like a traditional dungeon full of monsters, BAKERRRR treats the city itself as the dungeon: streets, storefronts, homes, casinos, businesses, doors, witnesses, rumors, services, vehicles, lighting, ownership, jobs, routines, and social expectations all become part of the play space. The player is not just exploring rooms — they are infiltrating “@ land,” a little simulated civic world where people live, work, notice things, remember things, react to trespass, run businesses, gossip, investigate disturbances, and sometimes make deeply questionable decisions around cats.

* The project is built in Python and currently supports both a curses terminal frontend and a pygame graphical frontend, with the terminal version remaining the heart of the experience. It is designed around procedural generation, seeded worlds, systemic interaction, and emergent consequences. It is rough, experimental, and very much in active development, but it already has a lot of strange machinery under the hood.

* BAKERRRR’s main hook is that it is trying to make the social layer of a roguelike matter. A locked door is not just a binary obstacle. Opening a door does not mean you belong there. A property can be public, private, open, closed, staffed, watched, controlled by an organization, tied to business hours, connected to employment, or socially accessible through the right kind of cover. Access and legitimacy are separate concepts. Being inside a place is not the same as being allowed inside it. It is played real time until a combat situation is happening, then it snaps to turn based so u can enjoy tactical battles. 

* NPCs are not intended to be simple enemies. They have routines, roles, occupations, homes, workplaces, memories, needs, social context, affiliations, and the ability to react to what they observe. The world is not supposed to be omniscient: what happened, what was witnessed, what was inferred, what was remembered, and what can be proven are different things. That distinction drives systems like suspicion, criminal justice, rumor, investigation, property access, and escalation.

* The game includes a growing set of systemic features: procedural buildings and sites, multi-floor interiors, ownership and access rules, vehicles and fuel, services and trade, player business systems, finances, casino games, wildlife, lighting and visibility, noise, cover, weapons, combat, NPC investigation, social reactions, run objectives, opportunities, pressure, and a final-operation structure that gives the sandbox a larger arc.

* One of the design goals is that play should feel like entering an existing society and learning how to move through it. You might observe routines, exploit business hours, use social cover, find services, gamble, drive across known route-space, follow rumors, avoid witnesses, buy or steal items, interact with NPCs, manage heat, or pursue opportunities that eventually connect to a larger operation. Combat exists, but it is only one possible rupture in a much larger system of social and spatial consequences.

* The game is also full of small emergent weirdness — the kind that comes from systems colliding. Wildlife can appear near the player. NPCs may react to animals. Rumors can affect behavior. Properties can generate unexpected social situations. The world can produce little scenes that feel oddly alive precisely because they were not hand-authored as single-use scripted moments.

BAKERRRR is currently best approached as an experimental roguelike-sim prototype, not a polished finished game. If you like traditional roguelikes, terminal games, procedural systems, simulation-heavy design, emergent behavior, stealth-adjacent social play, or weird little worlds that expose their logic through surprising edge cases, it may be worth checking out.


## Instructions:
linux: clone the repo, run ./bakerrrr   (for the curses terminal frontend ) or ./bakerrrr-gui ( for the pygame "graphical" front end ) 

windows/apple: very untested, I will evaluate pull requests and/or will ensure compatibility myself at some future time. This is just due to hardware

android: the curses version works in termux using things available in termux's package manager (python is all you need for this, as it only imports outside of the standard python library when it is using the pygame graphical mode) 
# BAKERRRR
[assets/screens/bakerrrr.png]


## The Game:
### BAKERRRR is a terminal-native systemic urban roguelike prototype about moving through a procedurally generated society.

* Instead of treating the world like a traditional dungeon full of monsters, BAKERRRR treats the city itself as the dungeon: streets, storefronts, homes, casinos, businesses, doors, witnesses, rumors, services, vehicles, lighting, ownership, jobs, routines, and social expectations all become part of the play space. The player is not just exploring rooms — they are infiltrating “@ land,” a little simulated civic world where people live, work, notice things, remember things, react to trespass, run businesses, gossip, investigate disturbances, and sometimes make deeply questionable decisions around cats.

* The project is built in Python and currently supports both a curses terminal frontend and a pygame graphical frontend, with the terminal version remaining the heart of the experience. It is designed around procedural generation, seeded worlds, systemic interaction, and emergent consequences. It is rough, experimental, and very much in active development, but it already has a lot of strange machinery under the hood.

* BAKERRRR’s main hook is that it is trying to make the social layer of a roguelike matter. A locked door is not just a binary obstacle. Opening a door does not mean you belong there. A property can be public, private, open, closed, staffed, watched, controlled by an organization, tied to business hours, connected to employment, or socially accessible through the right kind of cover. Access and legitimacy are separate concepts. Being inside a place is not the same as being allowed inside it. It is played real time until a combat situation is happening, then it snaps to turn based so u can enjoy tactical battles. 

* NPCs are not intended to be simple enemies. They have routines, roles, occupations, homes, workplaces, memories, needs, social context, affiliations, and the ability to react to what they observe. The world is not supposed to be omniscient: what happened, what was witnessed, what was inferred, what was remembered, and what can be proven are different things. That distinction drives systems like suspicion, criminal justice, rumor, investigation, property access, and escalation.

* The game includes a growing set of systemic features: procedural buildings and sites, multi-floor interiors, ownership and access rules, vehicles and fuel, services and trade, player business systems, finances, casino games, wildlife, lighting and visibility, noise, cover, weapons, combat, NPC investigation, social reactions, run objectives, opportunities, pressure, and a final-operation structure that gives the sandbox a larger arc.

* One of the design goals is that play should feel like entering an existing society and learning how to move through it. You might observe routines, exploit business hours, use social cover, find services, gamble, drive across known route-space, follow rumors, avoid witnesses, buy or steal items, interact with NPCs, manage heat, or pursue opportunities that eventually connect to a larger operation. Combat exists, but it is only one possible rupture in a much larger system of social and spatial consequences.

* The game is also full of small emergent weirdness — the kind that comes from systems colliding. Wildlife can appear near the player. NPCs may react to animals. Rumors can affect behavior. Properties can generate unexpected social situations. The world can produce little scenes that feel oddly alive precisely because they were not hand-authored as single-use scripted moments.

BAKERRRR is currently best approached as an experimental roguelike-sim prototype, not a polished finished game. If you like traditional roguelikes, terminal games, procedural systems, simulation-heavy design, emergent behavior, stealth-adjacent social play, or weird little worlds that expose their logic through surprising edge cases, it may be worth checking out.


## Instructions:
linux: clone the repo, run ./bakerrrr   (for the curses terminal frontend ) or ./bakerrrr-gui ( for the pygame "graphical" front end ) 

windows/apple: very untested, I will evaluate pull requests and/or will ensure compatibility myself at some future time. This is just due to hardware

android: the curses version works in termux using things available in termux's package manager (python is all you need for this, as it only imports outside of the standard python library when it is using the pygame graphical mode) 



The command wrappers ```bakerrrr``` and ```bakerrrr-gui``` handle the underlying startup details, so they are the intended day-to-day way to run the game.

The shared Python entrypoint remains available through ```main.py``` for development and debugging.

## Requirements

### BAKERRRR is written in Python. 

Current frontends use:

pygame
curses / terminal support appropriate to your platform

Dependency licensing remains under the terms of their respective upstream projects.

Pull Requests

Pull requests may be examined, but review is discretionary and acceptance is not guaranteed.

Public discussion, bug reports, and clear reproduction notes are generally more useful than large unsolicited changes.

License

Code is licensed under the BAKERRRR Alpha Non-Commercial Source License.

See LICENSE.

Assets are licensed separately under LICENSE-ASSETS.

Commercial use by third parties is not permitted without written permission.

Documentation

Some internal methodology and state-tracking notes are maintained privately and are intentionally omitted from the public release.

Normal use of the public code and content does not require access to private methodology.

Internal materials may be shared separately at maintainer discretion.

thank u for checking out my game. it is in active ongoing development as of ```may 2026```. 
```if that date is far in the past, i may have lost my focus or my mind```.

here are some early screenshots of the gui mode (it is a lot further along but they still capture the feel of the game



The command wrappers ```bakerrrr``` and ```bakerrrr-gui``` handle the underlying startup details, so they are the intended day-to-day way to run the game.

The shared Python entrypoint remains available through ```main.py``` for development and debugging.

## Requirements

### BAKERRRR is written in Python. 

Current frontends use:

pygame
curses / terminal support appropriate to your platform

Dependency licensing remains under the terms of their respective upstream projects.

Pull Requests

Pull requests may be examined, but review is discretionary and acceptance is not guaranteed.

Public discussion, bug reports, and clear reproduction notes are generally more useful than large unsolicited changes.

License

Code is licensed under the BAKERRRR Alpha Non-Commercial Source License.

See LICENSE.

Assets are licensed separately under LICENSE-ASSETS.

Commercial use by third parties is not permitted without written permission.

Documentation

Some internal methodology and state-tracking notes are maintained privately and are intentionally omitted from the public release.

Normal use of the public code and content does not require access to private methodology.

Internal materials may be shared separately at maintainer discretion.

thank u for checking out my game. it is in active ongoing development as of ```may 2026```. 
```if that date is far in the past, i may have lost my focus or my mind```.

###here are some early screenshots of the gui mode (it is a lot further along but they still capture the feel of the game

<img width="1920" height="1080" alt="image" src="https://github.com/user-attachments/assets/2841c4f4-629f-481b-8f6f-507e62dd6a9e" />
<img width="1920" height="1080" alt="Screenshot_20260406_105855" src="https://github.com/user-attachments/assets/48041845-9915-466b-b56c-b51a10ace7ce" />
<img width="1920" height="1080" alt="Screenshot_20260406_181110" src="https://github.com/user-attachments/assets/3e206938-f894-482e-822a-27eb60bd0910" />

###running in termux, terminal mode
<img width="1440" height="2838" alt="Screenshot_20260505_000203_Termux" src="https://github.com/user-attachments/assets/3f0fc533-fb0a-407b-b0c2-b6a18d273745" />

