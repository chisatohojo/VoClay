# VoClay

VoClay is an offline desktop MVP for vocal audio editing. It can open WAV files,
estimate the vocal pitch curve, convert voiced regions into note events, edit
those events in a piano-roll style note block view, export WAV files, and play
the file with a moving playhead.

The current build is focused on the note-block editing workflow:

- WAV loading
- Melodyne-style main note editor with a left piano keyboard and time grid
- pitch analysis with `librosa.pyin`
- automatic `VocalNote` generation from F0 frames when `Analyze` completes
- auxiliary MIDI pitch curve display behind the note blocks
- play and stop controls
- playhead display
- draggable time range selection
- automatic note segmentation from the detected pitch curve
- note block display from detected vocal note events
- block drag editing for note pitch and timing
- left/right edge drag editing for note length
- Delete and arrow-key editing for the selected note block
- selected note semitone changes from the top toolbar
- export placeholder for the future rendering pass
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
2. Click `Analyze` to estimate the vocal F0 curve and build note blocks.
3. Edit in the main note view: drag a block up/down for pitch, left/right for
   timing, or drag its left/right edge to change length.
4. Use Delete to remove the selected note block, or arrow keys to nudge pitch
   and timing.
5. Click `-1 semitone` or `+1 semitone` to move the selected note block.
6. Use `Play` / `Stop` to hear the loaded audio and watch the playhead.
7. `Export WAV` is present but intentionally shows a placeholder message until
   note-based rendering is implemented.

Stereo files are converted to mono for analysis. Playback uses the loaded audio
data directly when possible. Direct note block editing updates the internal
`VocalNote` model (`start_time`, `end_time`, `midi_note`, `cents_offset`,
`original_midi_median`, and `pitch_points`) so the project is structured for a
later resynthesis/WAV rendering pass. Full audio resynthesis from dragged note
timing and pitch is still future work.

## Project Layout

```text
voclay/
  main.py
  app/
    audio_document.py
    audio_editor.py
    audio_player.py
    main_window.py
    models.py
    note_segmenter.py
    pitch_analyzer.py
    scale_tools.py
    theme.py
    widgets/
      inspector_panel.py
      waveform_view.py
  assets/
    voclay_icon_full_background_transparent.png
    voclay_icon_outer_background_transparent.png
```
