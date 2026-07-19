# Windows Instructions

BAKERRRR may have experimental Windows packaged builds attached to GitHub Actions runs. They are not a tested release path yet.

This is an early, manual Windows path for brave testers. It is currently untested by the maintainer, so please expect rough edges and report what happens if it fails.

## Experimental Packaged Build

If a Windows artifact is available from a GitHub Actions build, download it, unpack it, and run `bakerrrr.exe`.

The packaged build defaults to the pygame frontend. It writes saves and the small player config into a `saves` folder beside the executable.

## Recommended Path

Use the pygame frontend on Windows. The terminal/curses frontend is not the recommended Windows path right now.

1. Install Python 3.10 or newer from <https://www.python.org/downloads/windows/>.
2. Open PowerShell.
3. Change into the BAKERRRR project folder.
4. Create and activate a virtual environment.   (OPTIONAL -allegedly safer)
5. Install `pygame-ce` and `windows-curses`.
6. Launch the pygame frontend.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install pygame-ce windows-curses
py main.py --ui pygame
```

Press `?` during a run for the exhaustive control and system reference. See
`PLAYER_GUIDE/` for the spoiler-light external guide.

note: the two venv commands are optional, if you wish to run in a virtual python sandbox. if you are following my lead, 
    you would throw caution to the wind.

## If PowerShell Blocks Activation

If PowerShell refuses to run the activation script, use this for the current PowerShell window:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Notes

- the maintainer does not have any experience in the windows system in recent years. this document took more time to
  research than I am prepared to admit. 
- if any windows-only bugs are found, the project direction will opt to keep the behavior that is working in linux and       windows players may find themselves back in unsupported land. if this happens, please fork the code and offer it as a solution for others who wish to play on your operating system. 
- `pygame-ce` is the recommended pygame dependency for this manual Windows path.
- `windows-curses` is installed for source runs because some startup imports still touch curses, even when pygame is selected.
- If the game fails to launch, please include the full PowerShell output when reporting the issue.
