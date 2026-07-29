# Sound And Music

Bakerrrr's soundscape is meant to be discovered during play. It responds to what
happens and where you are, while the music leaves room for the world around you.
The pygame version generates its audio when the game starts, so no external
sound pack is required.

Music arrives in short passages separated by long quiet stretches. A run keeps
a musical sense of where and how it began, while travel can occasionally bring
the character of a new place forward. Sound effects and the surrounding world
continue normally while the music rests.

## Volume And Muting

There is not an in-game volume menu yet. Set an option before launching:

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

## If Playback Crackles Or Skips

Try a larger audio buffer:

```bash
BAKERRRR_AUDIO_BUFFER=1024 python3 main.py
```

This gives a busy machine more protection against interrupted playback, at the
cost of a little extra response delay. A short pause while launching is normal:
the audio is generated once at startup and then reused during play.
