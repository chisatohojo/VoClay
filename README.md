# VoClay

VoClay is an offline desktop MVP for vocal audio editing. It can open WAV files,
show a waveform, estimate the vocal pitch curve, shift the pitch of a selected
range, export WAV files, and play the file with a moving playhead.

The current build covers Phase 1 and a first Phase 2 editing pass:

- WAV loading
- waveform display
- pitch analysis with `librosa.pyin`
- MIDI-style pitch curve display
- play and stop controls
- playhead display
- draggable time range selection
- selected-range pitch shifting by semitone
- WAV export of the edited audio
- internal edit history for later pitch and timing editing

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
4. Drag the highlighted range on the waveform or pitch view.
5. Click `-1 semitone` or `+1 semitone` to shift the selected range.
6. Use `Play` / `Stop` to hear the current edited audio and watch the playhead.
7. Click `Export WAV` to write the edited audio to disk.

Stereo files are converted to mono for analysis. Playback uses the loaded audio
data directly when possible. Pitch shifting is intentionally simple in this MVP:
it processes the selected range and blends the edges lightly to reduce clicks.

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
