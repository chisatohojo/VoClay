# VoClay

VoClay is an offline desktop MVP for vocal audio editing. It can open WAV files,
estimate the vocal pitch curve, convert voiced regions into note events, edit
those events in a piano-roll style note block view, export WAV files, and play
the file with a moving playhead.

The current build is focused on the note-block editing workflow:

- WAV loading
- input modes for `Vocal Only` and `Mixed Audio`
- optional Mixed Audio vocal separation through a replaceable `VocalSeparator`
- Melodyne-style main note editor with a left piano keyboard and time grid
- vocal F0 analysis with `librosa.pyin`
- simple chord-change analysis for Mixed Audio helper boundaries
- automatic `VocalNote` generation from F0 frames and optional chord-change hints
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
- right-side analysis status for input mode, analysis audio, vocal separation,
  chord changes, note count, and selected-note split reason
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

1. Choose `Vocal Only` for a vocal stem, or `Mixed Audio` for a full mix.
2. Click `Open` and choose a `.wav` file.
3. Click `Analyze` to estimate the vocal F0 curve and build note blocks.
   `Vocal Only` analyzes the input WAV directly. `Mixed Audio` tries to run
   demucs first, then analyzes the extracted vocal stem; if demucs is not
   available, VoClay keeps running and reports the fallback status.
4. Edit in the main note view: drag a block up/down for pitch, left/right for
   timing, or drag its left/right edge to change length.
5. Use Delete to remove the selected note block, or arrow keys to nudge pitch
   and timing.
6. Click `-1 semitone` or `+1 semitone` to move the selected note block.
7. Use `Play` / `Stop` to hear the loaded audio and watch the playhead.
8. `Export WAV` is present but intentionally shows a placeholder message until
   note-based rendering is implemented.

Stereo files are converted to mono for analysis. Playback uses the loaded audio
data directly when possible. Note block generation is driven by vocal F0, not
by chord labels. Chord changes are only helper split boundaries when available,
and are ignored when they would create unnaturally short notes. Direct note
block editing updates the internal `VocalNote` model (`start_time`, `end_time`,
`midi_note`, `cents_offset`, `original_midi_median`, `pitch_points`, and
`split_reason`) so the project is structured for a later resynthesis/WAV
rendering pass. Full audio resynthesis from dragged note timing and pitch is
still future work.

## Mixed Audio Notes

Mixed Audio mode uses demucs only when it is installed in the Python
environment or available on `PATH`. Heavy AI model files are not bundled with
VoClay. If demucs is unavailable or vocal separation fails, the app reports the
reason in the status/right panel and falls back to analyzing the source audio
instead of crashing.

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
    chord_analyzer.py
    note_segmenter.py
    pitch_analyzer.py
    scale_tools.py
    theme.py
    vocal_separator.py
    widgets/
      inspector_panel.py
      waveform_view.py
  assets/
    voclay_icon_full_background_transparent.png
    voclay_icon_outer_background_transparent.png
```
