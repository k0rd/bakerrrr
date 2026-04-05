BAKERRRR




Terminal-native systemic sandbox roguelike prototype.

BAKERRRR is a Python game built around emergent play, layered simulation, and readable chaos. It combines terminal-first design with systemic world logic, NPC behavior, economy, property access, and multiple UI backends. Public alpha prep is in progress.

Project Status

BAKERRRR is under active development and is currently being shaped toward a public alpha.

Current priorities include:

stabilizing the core loop
improving onboarding and moment-to-moment readability
refining controls across supported frontends
continuing systemic expansion without losing clarity

BAKERRRR currently ships with simple launcher scripts for both supported frontends.

Launch the terminal version:

./bakerrrr

Launch the graphical frontend:

./bakerrrr-gui

These wrappers handle the underlying startup details, so the launcher scripts are the intended day-to-day way to run the game.

The shared Python entrypoint remains available through main.py for development and debugging.

Requirements

BAKERRRR is written in Python.

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
