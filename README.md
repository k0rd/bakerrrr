# BAKERRRR

Terminal-native systemic sandbox roguelike prototype.

Public alpha prep is in progress.

The game is written in python and requires the pygame and curses libraries. the license does not cover the terms of these licenses

## Early Adopter Note

Planned direction (no date commitment):

- continue open alpha development with community feedback
- target a free or low-cost Steam release once the core loop and onboarding are stable
- validate controls and readability on Steam Deck during that process

Early testers can have direct influence on UX priorities, controls, and readability decisions.

## Community

If you love entropy-heavy roguelikes and systemic simulation, contributions are welcome.

Start here: [CONTRIBUTING.md](CONTRIBUTING.md)

Friendly ways to help:

- report surprising outcomes, unclear UI states, and readability pain points
- propose small, testable system interactions
- add or tune content data with matching regression coverage
- improve docs for onboarding and discoverability

## Fan Art

Project-origin  art can be added under `assets/art/`.

Current placeholder and naming guidance: `assets/art/README.txt`.

## Tile Assets

Tile source PNGs under `assets/tiles/src/` are tracked with the repo.

Tile tooling under `scripts/` and tile policy data such as `assets/tiles/tile_map.json` are also tracked.

Generated atlas outputs under `assets/tiles/atlas/` are rebuildable artifacts and are not part of the tracked source set.

Regenerate them with:

- `python3 scripts/tile_refresh.py`

## Planned Repo Split (Tiles)

Planned for a later milestone:

- keep runtime tile outputs and tile metadata public
- move or mirror source tile files to a private asset repo
- continue shipping rebuild scripts for public outputs that do not require
	private source files

## Running

The game uses a shared entrypoint: `main.py`.

Default launch uses the curses frontend:

- `python3 main.py`

To launch the pygame frontend, select the backend explicitly:

- `python3 main.py --ui pygame`
- `BAKERRRR_UI=pygame python3 main.py`

Supported pygame aliases are `pygame`, `tile`, and `tiles`.

## License

Code is licensed under the BAKERRRR Alpha Non-Commercial Source License.

See `LICENSE`.

Assets are licensed separately under `LICENSE-ASSETS`.

Commercial use by third parties is not permitted without written permission.

## Documentation

Internal methodology and state-tracking notes are maintained privately and are intentionally omitted from the public release.
Normal code and content contributions do not require an NDA.
Method-sharing may be considered for trusted contributors who enter into a good-faith NDA with the project maintainers.

## Checks

Run `python3 scripts/run_regressions.py --suite ci` for the default local/CI verification set.

Run `python3 scripts/run_regressions.py --suite full` for the broader regression sweep.
