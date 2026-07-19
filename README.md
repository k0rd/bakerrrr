# BAKERRRR
(older screenshots at the end)
<img width="1550" height="973" alt="image" src="https://github.com/user-attachments/assets/4a3aa869-75cc-4203-9b3e-409e8fbf780a" />
<img width="1532" height="981" alt="image" src="https://github.com/user-attachments/assets/372067bc-53c8-499e-af6f-5f68022b1cd0" />
<img width="1540" height="994" alt="image" src="https://github.com/user-attachments/assets/c8445d84-55b5-4950-a071-59c043523ac1" />
<img width="1920" height="1080" alt="image" src="https://github.com/user-attachments/assets/109c5f99-cd15-485f-9bff-1b97b323c643" />


 
 
** video of game : ** https://www.youtube.com/embed/_-nwalnoCQw   (a little old)
### BAKERRRR is a python systemic urban roguelike prototype about moving through a procedurally generated society.
The only dependancy is python and pygame-ce. Stand-alone compiled executables are provided by github releases

## The Game:

* Instead of treating the world like a traditional dungeon full of monsters, BAKERRRR treats the city itself as the dungeon: streets, storefronts, homes, casinos, businesses, doors, witnesses, rumors, services, vehicles, lighting, ownership, jobs, routines, and social expectations all become part of the play space. The player is not just exploring rooms — they are infiltrating “@ land,” a little simulated civic world where people live, work, notice things, remember things, react to trespass, run businesses, gossip, investigate disturbances, and sometimes make deeply questionable decisions around cats.

* The project is built in Python and currently supports a pygame-ce rendered graphical frontend, with an earlier prototype in the ```terminal-native``` branch of the repo that runs on curses. It is designed around procedural generation, seeded worlds, systemic interaction, and emergent consequences. It is rough, experimental, and very much in active development, but it already has a lot of strange machinery under the hood. Aside from pygame-ce, the entire game is fully realized using the python standard library.

* This game was written by someone who was inspired by games she played as a kid: Legacy of the Ancients, Questron I and II, Ultima 4 and 5, as well as games like nethack and xevil. That doesn't mean it doesn't have modern complexity and depth. There are so many modules and systems that they would be hard to list here, but the source code is well-organized and has docstrings, so can be easily consulted if something seems off. 

* BAKERRRR’s main hook is that it is trying to make the social layer of a roguelike matter in a roguelike way- etching and carving into the world life after life. A locked door is not just a binary obstacle. Opening a door does not mean you belong there. A property can be public, private, open, closed, staffed, watched, controlled by an organization, tied to business hours, connected to employment, or socially accessible through the right kind of cover. Access and legitimacy are separate concepts. Being inside a place is not the same as being allowed inside it. It is played real time until a combat situation is happening, then it snaps to turn based so u can enjoy tactical battles.

* There is a fully realized genetic flora and fauna system that is persistent across your adventures. Flowers you bred into the world (or that naturally bred from cross pollination) can appear as embroidery on a character's t-shirt after a few games. I plan to allow for these to be exported from the game for individual swapping and trading as a reward for completing runs, this might already exist by the time you read this.

* NPCs are not intended to be simple enemies. They have routines, roles, occupations, homes, workplaces, memories, needs, social context, affiliations, and the ability to react to what they observe. The world is not supposed to be omniscient: what happened, what was witnessed, what was inferred, what was remembered, and what can be proven are different things. That distinction drives systems like suspicion, criminal justice, rumor, investigation, property access, and escalation.

* The game includes a growing set of systemic features: procedural buildings and sites, multi-floor interiors, ownership and access rules, vehicles and fuel, services and trade, player business systems, finances, casino games, wildlife, lighting and visibility, noise, cover, weapons, combat, NPC investigation, social reactions, run objectives, opportunities, pressure, and a final-operation structure that gives the sandbox a larger arc.

* One of the design goals is that play should feel like entering an existing society and learning how to move through it. Survive npc's version  You might observe routines, exploit business hours, use social cover, find services, go to the casino; hit big; then get too drunk and lose it all , drive across known routes, follow rumors, avoid witnesses, buy or steal items, interact with NPCs, manage heat, or pursue opportunities that eventually connect to a larger operation. Combat exists, but it is only one possible rupture in a much larger system of social and spatial consequences.

* The game is also full of what I can only call emergent weirdness — the kind that comes from systems colliding. Wildlife can appear near the player - brand new wildlife that the world has never seen can permanently be bred into existence while you were helping to make another species rare -for the profit in selling their hides. NPCs may react to animals. or hunters. or a sneaky thief taking cover from an out of control fire. Rumors can affect behavior. Properties can generate unexpected social situations. The world can produce little scenes that feel oddly alive precisely because they were not hand-authored as single-use scripted moments. Nothing at all is on rails. It's up to you to progress and take what you wish from the world. There is structure. There is guidance. You do not have to 

BAKERRRR is currently best approached as an experimental roguelike-sim prototype, not a polished finished game. If you like traditional roguelikes, terminal games, procedural systems, simulation-heavy design, emergent behavior, stealth-adjacent social play, worlds that expose their logic through (hopefully surprising) edge cases, it may be worth checking out.



## Instructions:
linux: clone the repo, run ./bakerrrr   

windows/apple: very untested, I will evaluate pull requests and/or will ensure compatibility myself at some future time. This is just due to hardware

android: the curses branch works in termux using things available in termux's package manager (python is all you need for this, as it only imports outside of the standard python library when it is using the pygame graphical mode) 
you can also use a compatible X server on android to play the pygame compatible version



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

<img width="1920" height="1068" alt="Screenshot_20260518_233736" src="https://github.com/user-attachments/assets/b30fb754-fac2-451d-a4ea-c10d37ef7554" />
<img width="1541" height="876" alt="Screenshot_20260610_002447" src="https://github.com/user-attachments/assets/472fc0fa-7090-4711-91bc-ebfe41016d0a" />
<img width="1541" height="969" alt="Screenshot_20260610_002814" src="https://github.com/user-attachments/assets/2701dc90-9414-4638-ab90-4b8b65f7af49" />
<img width="1538" height="996" alt="Screenshot_20260610_202800-1" src="https://github.com/user-attachments/assets/10830b05-90fb-4e57-9608-1d9628ac1add" />
<img width="1547" height="956" alt="Screenshot_20260610_225301-1" src="https://github.com/user-attachments/assets/6902360f-c63d-41e2-bcf9-adc8115f2c09" />
<img width="1537" height="835" alt="Screenshot_20260610_230624-1" src="https://github.com/user-attachments/assets/8d2c4840-2b41-4b15-8f9e-71e555ce4677" />
<img width="1535" height="984" alt="Screenshot_20260610_230624" src="https://github.com/user-attachments/assets/fd14d6c1-f6e1-4ebc-b5ce-27f4cc449391" />
<img width="1535" height="984" alt="Screenshot_20260610_202530" src="https://github.com/user-attachments/assets/699b8868-2b5e-4d9e-b1ec-7dd88de36a6f" />
<img width="1535" height="984" alt="Screenshot_20260612_184556" src="https://github.com/user-attachments/assets/4632eed4-c3cb-43cc-814b-a17cfb327b8f" />
<img width="1920" height="1080" alt="image" src="https://github.com/user-attachments/assets/2841c4f4-629f-481b-8f6f-507e62dd6a9e" />
<img width="1920" height="1080" alt="Screenshot_20260406_105855" src="https://github.com/user-attachments/assets/48041845-9915-466b-b56c-b51a10ace7ce" />
<img width="1920" height="1080" alt="Screenshot_20260406_181110" src="https://github.com/user-attachments/assets/3e206938-f894-482e-822a-27eb60bd0910" />
