# VoClay

VoClay is an offline desktop MVP for vocal audio editing. It can open WAV files,
show a waveform, estimate the vocal pitch curve, and play the file with a moving
playhead.

The current build focuses on Phase 1:

- WAV loading
- waveform display
- pitch analysis with `librosa.pyin`
- MIDI-style pitch curve display
- play and stop controls
- playhead display
- internal data structures for later pitch and timing editing

## Requirements

- Python 3.10 or newer
- A working audio output device
- On some systems, `sounddevice` may require PortAudio support

## Setup

```powershell
python -m pip install -r requirements.txt
```

## Run

```powershell
python voclay/main.py
```

## Use

1. Click `Open` and choose a `.wav` file.
2. Confirm that the waveform appears.
3. Click `Analyze` to estimate the pitch.
4. Use `Play` / `Stop` to hear the file and watch the playhead.

Stereo files are converted to mono for analysis. Playback uses the loaded audio
data directly when possible.

## Project Layout

```text
voclay/
  main.py
  app/
    audio_document.py
    audio_player.py
    main_window.py
    models.py
    pitch_analyzer.py
    theme.py
    widgets/
      inspector_panel.py
      waveform_view.py
  assets/
    voclay_icon_full_background_transparent.png
    voclay_icon_outer_background_transparent.png
```
