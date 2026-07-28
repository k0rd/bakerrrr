# Sound And Music

The pygame version of Bakerrrr generates its current sound effects, ambient
layers, and music when the game starts. No external sound pack is required.

Action sounds confirm things that actually happened. Successful movement,
opening or closing a door, picking something up, completing a transaction,
finishing craft work, taking damage, and entering combat each have a small cue.
Blocked movement and failed actions stay quiet.

The background changes with the world around you:

- water becomes clearer as you approach it;
- nearby campfires add a restrained crackle;
- dawn and daytime sound different from dusk and night;
- city, frontier, wilderness, coast, and underground areas carry different low
  tones;
- outdoor ambience becomes quieter when you step inside.

The music is deliberately sparse so local sounds can come through between its
notes.
There is not an in-game volume menu yet. For a source checkout, set an option
before launching:

```bash
BAKERRRR_AUDIO_VOLUME=0.5 python3 main.py       # lower everything
BAKERRRR_BGM_VOLUME=1.4 python3 main.py         # raise music only
BAKERRRR_AMBIENCE_VOLUME=1.3 python3 main.py    # raise environment only
BAKERRRR_BGM=0 python3 main.py                  # effects and ambience, no music
BAKERRRR_AMBIENCE=0 python3 main.py             # music and action effects only
BAKERRRR_AUDIO=0 python3 main.py                # mute all game audio
```

Master volume accepts values from `0.0` to `1.0`. Music and ambience multipliers
accept values up to `2.0`, though final playback is still limited to the mixer's
safe maximum.
