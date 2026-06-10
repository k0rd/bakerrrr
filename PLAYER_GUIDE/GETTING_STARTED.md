# Getting Started

BAKERRRR runs from the shared `main.py` entry point.

You need Python, plus the pygame and curses libraries available in your Python environment.

## First Run

Start with the tutorial if you are new:

```bash
python3 main.py --tutorial --ui pygame
```

This opens the pygame frontend and starts a disposable tutorial run. It still asks for your character name and identity, because those are normal game surfaces. When you leave that tutorial, it does not resume or write a character save.

On a fresh player config, BAKERRRR may start the tutorial automatically once. If you want to skip that first pass:

```bash
python3 main.py --no-tutorial --ui pygame
```

## Regular Launch

For pygame:

```bash
python3 main.py --ui pygame
```

You can also select pygame through the environment:

```bash
BAKERRRR_UI=pygame python3 main.py
```

The default launch uses the curses frontend:

```bash
python3 main.py
```

Supported pygame aliases are `pygame`, `tile`, and `tiles`.

## Packaged Builds

If a GitHub build artifact is available for your system, unpack it and run the `bakerrrr` executable inside. Those builds open pygame by default and keep saves in a `saves` folder beside the executable.

More detail lives in [Packaged Builds](PACKAGED_BUILDS.md).

## Once You Are In

Press `?` for help. The footer at the bottom of the screen also changes with the current mode, so it is worth glancing down before you wrestle with a menu.

The game expects some poking around. Look at things, talk to people, open the operations report, and keep an eye on the log. If the city seems like it is doing a lot, that is because it is.

If something breaks in a way worth reporting, [Reporting Bugs](REPORTING_BUGS.md) has the short list of useful details.
