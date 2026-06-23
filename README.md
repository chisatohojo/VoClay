# VoClay

VoClay is an offline Windows/Python desktop MVP for aligning one vocal or audio
take to a reference melody. The app reads a reference WAV, extracts rough
Reference Notes from its F0 contour, reads a separate source WAV, extracts
editable Source Notes, and lets the user move, split, merge, match, render,
play, and export the adjusted result.

The current direction is reference melody alignment, not chord estimation.
Reference Notes are treated as a locked guide. Source Notes are the editable
material.

## Current Features

- Load Reference WAV and Source WAV separately
- Analyze Reference and Analyze Source separately with `librosa.pyin`
- Convert F0 frames into note blocks with `NoteSegmenter`
- Show Reference Notes and Source Notes in one piano-roll view
- Display locked Reference Notes in translucent teal
- Display editable Source Notes in purple, with orange selection
- Drag Source Notes left/right for timing and up/down for pitch
- Resize Source Notes from left/right edges
- Shift-click or range-drag to select multiple Source Notes
- Split selected Source Note at the playhead with `S`
- Merge selected Source Notes with `M`
- Delete selected Source Notes with Delete/Backspace
- Nudge selected Source Notes with arrow keys
- Match Selected Source Notes to the nearest Reference Notes
- Render Preview audio from edited Source Notes
- Play from selected note, selected range, or playhead position
- Export the rendered preview WAV

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

## Workflow

1. Click `Load Reference WAV` and choose the original song or guide melody.
2. Click `Analyze Reference` to create locked Reference Notes.
3. Click `Load Source WAV` and choose the audio you want to adjust.
4. Click `Analyze Source` to create editable Source Notes.
5. Edit Source Notes in the piano roll.
6. Use `Match Selected` to move selected Source Notes to nearby Reference Notes.
7. Use `Render Preview` to generate adjusted preview audio.
8. Use `Play from Selection` to listen from the selected note, selected range,
   or current playhead.
9. Use `Export WAV` to write the rendered preview to disk.

## Shortcuts

- `Space`: Play from Selection / Stop
- `S`: Split selected Source Note at playhead
- `M`: Merge selected Source Notes
- `Delete` or `Backspace`: Delete selected Source Notes
- `Up` / `Down`: Move selected Source Notes by semitone
- `Left` / `Right`: Nudge selected Source Notes in time

Reference Notes are locked and are not moved, deleted, split, or merged by
these editing commands.

## Rendering Notes

`AudioRenderer` currently uses `librosa` for a simple first-pass preview render:

- source note original range is cut from Source Audio
- `midi_note - original_midi_median` determines pitch shift
- edited note duration determines time stretch
- processed note segments are placed at edited Source Note positions
- the rendered result is kept in memory and also written to a temporary WAV

This is not intended to be final studio-quality rendering. It is a working
structure that can later be swapped to Rubber Band or another higher quality
time-stretch/pitch-shift backend.

## Project Layout

```text
voclay/
  main.py
  app/
    audio_document.py
    audio_player.py
    audio_renderer.py
    main_window.py
    models.py
    note_segmenter.py
    pitch_analyzer.py
    project_document.py
    theme.py
    widgets/
      inspector_panel.py
      waveform_view.py
  assets/
    voclay_icon_full_background_transparent.png
    voclay_icon_outer_background_transparent.png
```
