"""Registration hook for separately maintained Workbench modes."""

from __future__ import annotations


def register_packaged_modes() -> None:
    # Importing a mode module performs its explicit @register_mode registration.
    from editor.modes import building_stamps  # noqa: F401
    from editor.modes import drawables  # noqa: F401
    from editor.modes import items  # noqa: F401
