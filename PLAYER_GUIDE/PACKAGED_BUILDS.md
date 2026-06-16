# Packaged Builds

Packaged builds are the least fussy way to try BAKERRRR when an artifact exists for your system.

Unpack the artifact, then run the `bakerrrr` executable inside. These builds open the pygame frontend by default and keep their saves/config in a local `saves` folder beside the executable.

If the executable does not open, try the built-in doctor from a terminal:

```bash
bakerrrr --doctor
```

On Windows, you may need to run it from PowerShell or Command Prompt so you can see the output.

Source launch still works too:

```bash
python3 main.py --ui pygame
```

For current playtests, start with a regular run and use `?` for the in-game help surface:

```bash
python3 main.py --ui pygame
```

The disposable tutorial is available only when explicitly requested:

```bash
python3 main.py --tutorial --ui pygame
```

## Files You May See

- `saves/` keeps local saves and the small player config.
- `saves/bakerrrr_last_crash.txt` appears after some crashes.

Deleting the folder resets local saves/config for that copy of the game.
