from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QComboBox,
    QSizePolicy,
    QSplitter,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from voclay.app.audio_editor import AudioEditor
from voclay.app.audio_document import AudioDocument
from voclay.app.audio_player import AudioPlayer
from voclay.app.chord_analyzer import ChordAnalyzer
from voclay.app.models import ChordChange, ChordFrame, NoteSegment, PitchEdit, PitchFrame, TimeRange, VocalNote
from voclay.app.note_segmenter import NoteSegmenter
from voclay.app.pitch_analyzer import PitchAnalyzer
from voclay.app.scale_tools import KEYS, SCALES, nearest_scale_delta
from voclay.app.theme import asset_path
from voclay.app.vocal_separator import VocalSeparator
from voclay.app.widgets.inspector_panel import InspectorPanel
from voclay.app.widgets.waveform_view import WaveformView


@dataclass
class AnalysisResult:
    frames: list[PitchFrame]
    notes: list[VocalNote]
    chord_frames: list[ChordFrame]
    chord_changes: list[ChordChange]
    input_mode: str
    analysis_audio_path: Path | None
    vocal_stem_path: Path | None
    accompaniment_stem_path: Path | None
    vocal_separation_message: str
    chord_analysis_message: str
    status_message: str


class PitchAnalysisWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, document: AudioDocument, input_mode: str) -> None:
        super().__init__()
        self.document = document
        self.input_mode = input_mode

    @Slot()
    def run(self) -> None:
        try:
            result = self._run_analysis()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)

    def _run_analysis(self) -> AnalysisResult:
        self.document.set_input_mode(self.input_mode)
        self.document.chord_frames = []
        self.document.chord_changes = []
        self.document.vocal_separation_message = "Skipped"
        self.document.chord_analysis_message = "Skipped"

        vocal_stem_path: Path | None = None
        accompaniment_stem_path: Path | None = None
        vocal_message = "Skipped in Vocal Only Mode"
        chord_message = "Chord analysis skipped in Vocal Only Mode"

        if self.input_mode == "Mixed Audio":
            output_dir = Path(tempfile.mkdtemp(prefix="voclay_stems_"))
            separation = VocalSeparator().separate(str(self.document.source_file_path or self.document.file_path), str(output_dir))
            vocal_message = separation.message
            if separation.success and separation.vocal_path:
                vocal_stem_path = Path(separation.vocal_path)
                accompaniment_stem_path = Path(separation.accompaniment_path) if separation.accompaniment_path else None
                self.document.set_vocal_stems(vocal_stem_path, accompaniment_stem_path)
                self.document.set_analysis_audio(vocal_stem_path)
            else:
                self.document.set_vocal_stems(None, None)
                self.document.use_source_for_analysis()
                vocal_message = f"{vocal_message} Using source audio for analysis."

            chord_source = accompaniment_stem_path or self.document.source_file_path or self.document.file_path
            chord_result = ChordAnalyzer().analyze(chord_source)
            chord_frames = chord_result.frames
            chord_changes = chord_result.changes
            chord_message = chord_result.message
        else:
            self.document.set_vocal_stems(None, None)
            self.document.use_source_for_analysis()
            chord_frames = []
            chord_changes = []

        frames = PitchAnalyzer().analyze(self.document)
        voiced_count = sum(1 for frame in frames if frame.voiced and frame.f0 is not None)
        if voiced_count < 3:
            notes: list[VocalNote] = []
            status = "F0 detection failed or too few voiced frames"
        else:
            notes = NoteSegmenter().segment(
                frames,
                self.document.analysis_duration,
                chord_changes,
            )
            status = (
                f"{self.input_mode}: {len(frames):,} F0 frames, "
                f"{voiced_count:,} voiced, {len(chord_changes):,} chord changes, "
                f"{len(notes):,} notes"
            )

        return AnalysisResult(
            frames=frames,
            notes=notes,
            chord_frames=chord_frames,
            chord_changes=chord_changes,
            input_mode=self.input_mode,
            analysis_audio_path=self.document.analysis_audio_path,
            vocal_stem_path=vocal_stem_path,
            accompaniment_stem_path=accompaniment_stem_path,
            vocal_separation_message=vocal_message,
            chord_analysis_message=chord_message,
            status_message=status,
        )


class PitchShiftWorker(QObject):
    finished = Signal(object, object, object)
    failed = Signal(str)

    def __init__(self, document: AudioDocument, selection: TimeRange, semitones: float) -> None:
        super().__init__()
        self.document = document
        self.selection = selection
        self.semitones = semitones

    @Slot()
    def run(self) -> None:
        try:
            edited_samples, frames, edit = AudioEditor.pitch_shift_range(
                self.document,
                self.selection,
                self.semitones,
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.finished.emit(edited_samples, frames, edit)


class AudioOperationWorker(QObject):
    finished = Signal(object, object, object, object)
    failed = Signal(str)

    def __init__(self, operation) -> None:  # noqa: ANN001
        super().__init__()
        self.operation = operation

    @Slot()
    def run(self) -> None:
        try:
            edited_samples, frames, edits, select_time = self.operation()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.finished.emit(edited_samples, frames, edits, select_time)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VoClay")
        self.resize(1280, 760)

        icon_file = asset_path("voclay_icon_outer_background_transparent.png")
        if icon_file.exists():
            self.setWindowIcon(QIcon(str(icon_file)))

        self.document: AudioDocument | None = None
        self.audio_player = AudioPlayer()
        self.playhead_timer = QTimer(self)
        self.playhead_timer.setInterval(30)
        self.playhead_timer.timeout.connect(self._update_playhead)

        self.analysis_thread: QThread | None = None
        self.analysis_worker: PitchAnalysisWorker | None = None
        self.edit_thread: QThread | None = None
        self.edit_worker: QObject | None = None
        self.selected_note_index: int | None = None

        self.waveform_view = WaveformView()
        self.inspector_panel = InspectorPanel()
        self.open_button = self._make_button("Open", QStyle.SP_DialogOpenButton)
        self.analyze_button = self._make_button("Analyze", QStyle.SP_FileDialogDetailedView)
        self.play_button = self._make_button("Play", QStyle.SP_MediaPlay)
        self.pitch_down_button = self._make_button("-1 semitone", QStyle.SP_ArrowDown)
        self.pitch_up_button = self._make_button("+1 semitone", QStyle.SP_ArrowUp)
        self.export_button = self._make_button("Export WAV", QStyle.SP_DialogSaveButton)
        self.input_mode_combo = QComboBox()
        self.input_mode_combo.addItems(["Vocal Only", "Mixed Audio"])
        self.input_mode_combo.setCurrentText("Vocal Only")
        self.detect_notes_button = self._make_button("Detect Notes", QStyle.SP_FileDialogListView)
        self.previous_note_button = self._make_button("Prev Note", QStyle.SP_MediaSeekBackward)
        self.next_note_button = self._make_button("Next Note", QStyle.SP_MediaSeekForward)
        self.note_down_button = self._make_button("Note -1", QStyle.SP_ArrowDown)
        self.note_up_button = self._make_button("Note +1", QStyle.SP_ArrowUp)
        self.note_start_earlier_button = self._make_button("Start -", QStyle.SP_ArrowLeft)
        self.note_start_later_button = self._make_button("Start +", QStyle.SP_ArrowRight)
        self.note_shorter_button = self._make_button("Shorter", QStyle.SP_TitleBarShadeButton)
        self.note_longer_button = self._make_button("Longer", QStyle.SP_TitleBarUnshadeButton)
        self.scale_key_combo = QComboBox()
        self.scale_key_combo.addItems(KEYS.keys())
        self.scale_key_combo.setCurrentText("C")
        self.scale_mode_combo = QComboBox()
        self.scale_mode_combo.addItems(SCALES.keys())
        self.scale_mode_combo.setCurrentText("Major")
        self.snap_note_button = self._make_button("Snap Note", QStyle.SP_DialogApplyButton)
        self.snap_all_button = self._make_button("Snap All", QStyle.SP_DialogApplyButton)
        self.vibrato_down_button = self._make_button("Vib -", QStyle.SP_ArrowDown)
        self.vibrato_up_button = self._make_button("Vib +", QStyle.SP_ArrowUp)
        self.scoop_button = self._make_button("Scoop Fix", QStyle.SP_ArrowUp)
        self.fall_button = self._make_button("Fall Fix", QStyle.SP_ArrowUp)
        self.formant_down_button = self._make_button("Formant -", QStyle.SP_ArrowDown)
        self.formant_up_button = self._make_button("Formant +", QStyle.SP_ArrowUp)
        self.file_label = QLabel("No file loaded")
        self.file_label.setObjectName("MutedLabel")
        self.file_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.open_button.clicked.connect(self.open_file)
        self.analyze_button.clicked.connect(self.analyze_pitch)
        self.play_button.clicked.connect(self.toggle_playback)
        self.pitch_down_button.clicked.connect(lambda: self.apply_selected_note_pitch_shift(-1.0))
        self.pitch_up_button.clicked.connect(lambda: self.apply_selected_note_pitch_shift(1.0))
        self.export_button.clicked.connect(self.export_wav)
        self.waveform_view.selection_changed.connect(self._selection_changed)
        self.waveform_view.note_selected.connect(self._note_selected)
        self.waveform_view.note_edited.connect(self._note_edited)
        self.waveform_view.note_deleted.connect(self._note_deleted)
        self.detect_notes_button.clicked.connect(self.detect_notes)
        self.previous_note_button.clicked.connect(lambda: self.select_relative_note(-1))
        self.next_note_button.clicked.connect(lambda: self.select_relative_note(1))
        self.note_down_button.clicked.connect(lambda: self.apply_selected_note_pitch_shift(-1.0))
        self.note_up_button.clicked.connect(lambda: self.apply_selected_note_pitch_shift(1.0))
        self.note_start_earlier_button.clicked.connect(lambda: self.adjust_selected_note(start_delta=-0.02))
        self.note_start_later_button.clicked.connect(lambda: self.adjust_selected_note(start_delta=0.02))
        self.note_shorter_button.clicked.connect(lambda: self.adjust_selected_note(end_delta=-0.04))
        self.note_longer_button.clicked.connect(lambda: self.adjust_selected_note(end_delta=0.04))
        self.snap_note_button.clicked.connect(self.snap_selected_note_to_scale)
        self.snap_all_button.clicked.connect(self.snap_all_notes_to_scale)
        self.vibrato_down_button.clicked.connect(lambda: self.apply_vibrato(-1.0))
        self.vibrato_up_button.clicked.connect(lambda: self.apply_vibrato(1.0))
        self.scoop_button.clicked.connect(lambda: self.correct_selected_transition("scoop"))
        self.fall_button.clicked.connect(lambda: self.correct_selected_transition("fall"))
        self.formant_down_button.clicked.connect(lambda: self.apply_formant_color(-1.0))
        self.formant_up_button.clicked.connect(lambda: self.apply_formant_color(1.0))
        self.analyze_button.setEnabled(False)
        self.play_button.setEnabled(False)
        self.pitch_down_button.setEnabled(False)
        self.pitch_up_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.detect_notes_button.setEnabled(False)
        self._set_note_controls_enabled(False)
        self._set_phase4_controls_enabled(False)

        self._build_layout()
        self._set_state("Ready")

    def _build_layout(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 8)
        root_layout.setSpacing(10)
        root_layout.addWidget(self._top_bar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.waveform_view)
        splitter.addWidget(self.inspector_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([980, 300])
        root_layout.addWidget(splitter, stretch=1)

        self.setCentralWidget(root)

    def _top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        logo_label = QLabel()
        logo = QPixmap(str(asset_path("voclay_icon_outer_background_transparent.png")))
        if not logo.isNull():
            logo_label.setPixmap(logo.scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        title = QLabel("VoClay")
        title.setObjectName("AppTitle")

        layout.addWidget(logo_label)
        layout.addWidget(title)
        layout.addSpacing(12)
        layout.addWidget(self.open_button)
        layout.addWidget(self.analyze_button)
        layout.addWidget(self.play_button)
        layout.addWidget(self.pitch_down_button)
        layout.addWidget(self.pitch_up_button)
        layout.addWidget(self.export_button)
        layout.addSpacing(8)
        mode_label = QLabel("Input Mode")
        mode_label.setObjectName("MutedLabel")
        layout.addWidget(mode_label)
        layout.addWidget(self.input_mode_combo)
        layout.addSpacing(12)
        layout.addWidget(self.file_label, stretch=1)
        return bar

    def _note_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        label = QLabel("Notes")
        label.setObjectName("MutedLabel")
        layout.addWidget(label)
        layout.addSpacing(8)
        layout.addWidget(self.detect_notes_button)
        layout.addWidget(self.previous_note_button)
        layout.addWidget(self.next_note_button)
        layout.addSpacing(8)
        layout.addWidget(self.note_down_button)
        layout.addWidget(self.note_up_button)
        layout.addSpacing(8)
        layout.addWidget(self.note_start_earlier_button)
        layout.addWidget(self.note_start_later_button)
        layout.addWidget(self.note_shorter_button)
        layout.addWidget(self.note_longer_button)
        layout.addStretch(1)
        return bar

    def _tone_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        label = QLabel("Tone")
        label.setObjectName("MutedLabel")
        layout.addWidget(label)
        layout.addSpacing(8)
        layout.addWidget(self.scale_key_combo)
        layout.addWidget(self.scale_mode_combo)
        layout.addWidget(self.snap_note_button)
        layout.addWidget(self.snap_all_button)
        layout.addSpacing(8)
        layout.addWidget(self.vibrato_down_button)
        layout.addWidget(self.vibrato_up_button)
        layout.addSpacing(8)
        layout.addWidget(self.scoop_button)
        layout.addWidget(self.fall_button)
        layout.addSpacing(8)
        layout.addWidget(self.formant_down_button)
        layout.addWidget(self.formant_up_button)
        layout.addStretch(1)
        return bar

    def _make_button(self, label: str, standard_icon: QStyle.StandardPixmap) -> QToolButton:
        button = QToolButton()
        button.setText(label)
        button.setIcon(self.style().standardIcon(standard_icon))
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setCursor(Qt.PointingHandCursor)
        return button

    @Slot()
    def open_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open WAV",
            str(Path.home()),
            "WAV files (*.wav)",
        )
        if not file_path:
            return

        self._stop_playback()
        self._set_state("Loading", Path(file_path).name)

        try:
            document = AudioDocument.load(file_path)
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"Could not load WAV file:\n{exc}")
            self._set_state("Ready")
            return

        self.document = document
        self.document.set_input_mode(self.input_mode_combo.currentText())
        self.document.use_source_for_analysis()
        self.selected_note_index = None
        self.waveform_view.set_audio(document)
        self.waveform_view.set_note_segments([])
        self.inspector_panel.set_document(document)
        self.inspector_panel.set_notes([])
        selection = self.waveform_view.selection_range()
        if selection is not None:
            self._selection_changed(*selection)
        self.file_label.setText(document.file_name)
        self.analyze_button.setEnabled(True)
        self.play_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self._update_edit_buttons()
        self._update_note_buttons()
        self._set_state("Ready", f"{document.duration:.2f} s")

    @Slot()
    def analyze_pitch(self) -> None:
        if self.document is None or self.analysis_thread is not None:
            return

        self._set_state("Analyzing", self.document.file_name)
        self.analyze_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.input_mode_combo.setEnabled(False)

        thread = QThread(self)
        worker = PitchAnalysisWorker(self.document, self.input_mode_combo.currentText())
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._analysis_finished)
        worker.failed.connect(self._analysis_failed)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._analysis_cleanup)

        self.analysis_thread = thread
        self.analysis_worker = worker
        thread.start()

    @Slot(object)
    def _analysis_finished(self, result: AnalysisResult) -> None:
        if self.document is None:
            return

        self.document.set_input_mode(result.input_mode)
        self.document.analysis_audio_path = result.analysis_audio_path
        self.document.set_vocal_stems(result.vocal_stem_path, result.accompaniment_stem_path)
        self.document.vocal_separation_message = result.vocal_separation_message
        self.document.chord_analysis_message = result.chord_analysis_message
        self.document.pitch_frames = result.frames
        self.document.chord_frames = result.chord_frames
        self.document.chord_changes = result.chord_changes
        self.document.note_segments = result.notes
        self.selected_note_index = None
        self.waveform_view.set_pitch_frames(result.frames)
        self.inspector_panel.set_document(self.document)
        self.inspector_panel.set_pitch_frames(result.frames)
        self.inspector_panel.set_analysis_status(self.document)

        if result.notes:
            self._select_note_index(0)
        else:
            self.waveform_view.set_note_segments([])
            self.inspector_panel.set_notes([])
            self._update_note_buttons()

        self._set_state("Ready", result.status_message)

    @Slot(str)
    def _analysis_failed(self, message: str) -> None:
        self._show_error(f"Pitch analysis failed:\n{message}")
        self._set_state("Ready")

    @Slot()
    def _analysis_cleanup(self) -> None:
        self.analysis_thread = None
        self.analysis_worker = None
        self.open_button.setEnabled(True)
        self.input_mode_combo.setEnabled(True)
        self.analyze_button.setEnabled(self.document is not None)
        self._update_edit_buttons()
        self._update_note_buttons()

    @Slot()
    def apply_pitch_shift(self, semitones: float) -> None:
        if self.document is None or self.edit_thread is not None:
            return

        selection = self.waveform_view.selection_range()
        if selection is None:
            self._show_error("Select a time range before shifting pitch.")
            return

        self._stop_playback()
        selection_range = TimeRange(selection[0], selection[1]).normalized(self.document.duration)
        self._start_pitch_shift(selection_range, semitones)

    def _start_pitch_shift(self, selection_range: TimeRange, semitones: float) -> None:
        if self.document is None or self.edit_thread is not None:
            return

        self._set_state("Processing", f"{semitones:+.0f} semitone")
        self._set_controls_enabled(False)

        thread = QThread(self)
        worker = PitchShiftWorker(self.document, selection_range, semitones)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._pitch_shift_finished)
        worker.failed.connect(self._audio_operation_failed)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._pitch_shift_cleanup)

        self.edit_thread = thread
        self.edit_worker = worker
        thread.start()

    @Slot(object, object, object)
    def _pitch_shift_finished(
        self,
        edited_samples,
        frames: list[PitchFrame],
        edit: PitchEdit,
    ) -> None:
        if self.document is None:
            return

        had_notes = bool(self.document.note_segments)
        select_time = edit.selection.start + edit.selection.duration * 0.5
        self.document.apply_pitch_edit(edited_samples, frames, edit)
        self.waveform_view.set_audio(self.document)
        self.waveform_view.set_pitch_frames(self.document.pitch_frames)
        self.inspector_panel.set_document(self.document)
        self.inspector_panel.set_pitch_frames(self.document.pitch_frames)

        if had_notes:
            self._refresh_notes_from_pitch(select_time=select_time)
        else:
            self.document.note_segments = []
            self.selected_note_index = None
            self.waveform_view.set_note_segments([])
            self.waveform_view.set_selection_range(edit.selection.start, edit.selection.end)
            self.inspector_panel.set_selection_range(edit.selection.start, edit.selection.end)
            self.inspector_panel.set_notes([])

        self.inspector_panel.set_edit_count(len(self.document.edit_history))
        self._set_state("Ready", f"shifted {edit.selection.duration:.2f} s by {edit.semitones:+.0f} semitone")

    @Slot(str)
    def _audio_operation_failed(self, message: str) -> None:
        self._show_error(f"Audio edit failed:\n{message}")
        self._set_state("Ready")

    @Slot()
    def _pitch_shift_cleanup(self) -> None:
        self.edit_thread = None
        self.edit_worker = None
        self._set_controls_enabled(True)

    @Slot()
    def detect_notes(self) -> None:
        if self.document is None:
            return
        if not self.document.pitch_frames:
            self._show_error("Analyze pitch before detecting notes.")
            return

        note_count = self._refresh_notes_from_pitch()
        self._set_state("Ready", f"detected {note_count:,} notes")

    @Slot(int)
    def _note_selected(self, index: int) -> None:
        self._select_note_index(index)

    @Slot(int, float, float, float)
    def _note_edited(self, index: int, start: float, end: float, midi_note: float) -> None:
        if self.document is None or not 0 <= index < len(self.document.note_segments):
            return

        notes = list(self.document.note_segments)
        notes[index] = notes[index].with_range(start, end).with_pitch(midi_note)
        self.document.note_segments = notes
        self.selected_note_index = index

        note = notes[index]
        self.waveform_view.set_note_segments(notes, index)
        self.waveform_view.set_selection_range(note.start, note.end)
        self.inspector_panel.set_notes(notes, index)
        self.inspector_panel.set_selection_range(note.start, note.end)
        self._update_edit_buttons()
        self._update_note_buttons()
        self._set_state("Ready", f"edited {note.note_name}")

    @Slot(int)
    def _note_deleted(self, index: int) -> None:
        if self.document is None or not 0 <= index < len(self.document.note_segments):
            return

        deleted = self.document.note_segments[index]
        notes = [
            note.with_id(new_id)
            for new_id, note in enumerate(
                [
                    note
                    for item_index, note in enumerate(self.document.note_segments)
                    if item_index != index
                ]
            )
        ]
        self.document.note_segments = notes
        if not notes:
            self.selected_note_index = None
            self.waveform_view.set_note_segments([])
            self.inspector_panel.set_notes([])
            self._update_edit_buttons()
            self._set_state("Ready", f"deleted {deleted.note_name}")
            return

        self._select_note_index(min(index, len(notes) - 1))
        self._set_state("Ready", f"deleted {deleted.note_name}")

    def select_relative_note(self, offset: int) -> None:
        if self.document is None or not self.document.note_segments:
            return
        if self.selected_note_index is None:
            self._select_note_index(0)
            return

        next_index = max(
            0,
            min(len(self.document.note_segments) - 1, self.selected_note_index + offset),
        )
        self._select_note_index(next_index)

    def apply_selected_note_pitch_shift(self, semitones: float) -> None:
        if self.document is None or self.selected_note_index is None:
            self._set_state("Ready", "No note selected")
            return
        if not 0 <= self.selected_note_index < len(self.document.note_segments):
            self._set_state("Ready", "No note selected")
            return

        notes = list(self.document.note_segments)
        note = notes[self.selected_note_index]
        notes[self.selected_note_index] = note.with_pitch(note.midi_note + semitones)
        self.document.note_segments = notes

        self._select_note_index(self.selected_note_index)
        self._set_state("Ready", f"{notes[self.selected_note_index].note_name} {semitones:+.0f} semitone")

    def adjust_selected_note(self, start_delta: float = 0.0, end_delta: float = 0.0) -> None:
        if self.document is None or self.selected_note_index is None:
            return
        if not 0 <= self.selected_note_index < len(self.document.note_segments):
            return

        notes = list(self.document.note_segments)
        note = notes[self.selected_note_index]
        min_duration = 0.05
        previous_end = notes[self.selected_note_index - 1].end if self.selected_note_index > 0 else 0.0
        next_start = (
            notes[self.selected_note_index + 1].start
            if self.selected_note_index < len(notes) - 1
            else self.document.duration
        )

        new_start = note.start + start_delta
        new_end = note.end + end_delta
        new_start = max(previous_end, min(new_start, note.end - min_duration))
        new_end = min(next_start, max(new_end, new_start + min_duration))

        notes[self.selected_note_index] = note.with_range(new_start, new_end)
        self.document.note_segments = notes
        self._select_note_index(self.selected_note_index)
        self._set_state("Ready", f"adjusted {notes[self.selected_note_index].note_name}")

    def snap_selected_note_to_scale(self) -> None:
        note = self._selected_note()
        if note is None:
            return

        delta = nearest_scale_delta(
            note.midi_note,
            self.scale_key_combo.currentText(),
            self.scale_mode_combo.currentText(),
        )
        if abs(delta) < 0.03:
            self._set_state("Ready", f"{note.note_name} is already on scale")
            return

        self._stop_playback()
        selection = TimeRange(note.start, note.end)
        self.waveform_view.set_selection_range(note.start, note.end)
        self._start_pitch_shift(selection, delta)

    def snap_all_notes_to_scale(self) -> None:
        if self.document is None or not self.document.note_segments:
            return

        edits: list[PitchEdit] = []
        for note in self.document.note_segments:
            delta = nearest_scale_delta(
                note.midi_note,
                self.scale_key_combo.currentText(),
                self.scale_mode_combo.currentText(),
            )
            if abs(delta) >= 0.03:
                edits.append(PitchEdit(selection=TimeRange(note.start, note.end), semitones=delta))

        if not edits:
            self._set_state("Ready", "all notes already on scale")
            return

        self._stop_playback()
        select_time = self._selected_note_center()

        def operation():
            edited, frames, applied = AudioEditor.pitch_shift_edits(self.document, edits)
            return edited, frames, applied, select_time

        self._start_audio_operation("Snapping", operation)

    def apply_vibrato(self, amount: float) -> None:
        selection = self._active_edit_range()
        if self.document is None or selection is None:
            return

        self._stop_playback()
        select_time = selection.start + selection.duration * 0.5

        def operation():
            edited, frames, edit = AudioEditor.apply_vibrato_range(
                self.document,
                selection,
                amount,
            )
            return edited, frames, [edit], select_time

        self._start_audio_operation("Vibrato", operation)

    def correct_selected_transition(self, mode: str) -> None:
        note = self._selected_note()
        if self.document is None or note is None:
            return

        self._stop_playback()
        select_time = note.start + note.duration * 0.5

        def operation():
            edited, frames, edits = AudioEditor.correct_transition(self.document, note, mode)
            return edited, frames, edits, select_time

        label = "Scoop" if mode == "scoop" else "Fall"
        self._start_audio_operation(label, operation)

    def apply_formant_color(self, amount: float) -> None:
        selection = self._active_edit_range()
        if self.document is None or selection is None:
            return

        self._stop_playback()
        select_time = selection.start + selection.duration * 0.5

        def operation():
            edited, frames, edit = AudioEditor.formant_color_range(
                self.document,
                selection,
                amount,
            )
            return edited, frames, [edit], select_time

        self._start_audio_operation("Formant", operation)

    def _start_audio_operation(self, label: str, operation) -> None:  # noqa: ANN001
        if self.document is None or self.edit_thread is not None:
            return

        self._set_state(label, "processing")
        self._set_controls_enabled(False)

        thread = QThread(self)
        worker = AudioOperationWorker(operation)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._audio_operation_finished)
        worker.failed.connect(self._audio_operation_failed)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._pitch_shift_cleanup)

        self.edit_thread = thread
        self.edit_worker = worker
        thread.start()

    @Slot(object, object, object, object)
    def _audio_operation_finished(
        self,
        edited_samples,
        frames: list[PitchFrame],
        edits,
        select_time,
    ) -> None:
        if self.document is None:
            return

        had_notes = bool(self.document.note_segments)
        self.document.apply_audio_edits(edited_samples, frames, edits)
        self.waveform_view.set_audio(self.document)
        self.waveform_view.set_pitch_frames(self.document.pitch_frames)
        self.inspector_panel.set_document(self.document)
        self.inspector_panel.set_pitch_frames(self.document.pitch_frames)

        if had_notes:
            self._refresh_notes_from_pitch(select_time=select_time)
        else:
            self.document.note_segments = []
            self.selected_note_index = None
            self.waveform_view.set_note_segments([])
            self.inspector_panel.set_notes([])
            if edits:
                selection = edits[0].selection
                self.waveform_view.set_selection_range(selection.start, selection.end)
                self.inspector_panel.set_selection_range(selection.start, selection.end)

        self.inspector_panel.set_edit_count(len(self.document.edit_history))
        self._set_state("Ready", f"applied {len(edits)} edit(s)")

    @Slot()
    def export_wav(self) -> None:
        if self.document is None:
            return
        QMessageBox.information(
            self,
            "VoClay",
            "Export is not implemented yet. Note edit data is ready for future rendering.",
        )
        self._set_state("Ready", "export not implemented")

    @Slot()
    def toggle_playback(self) -> None:
        if self.audio_player.is_playing():
            self._stop_playback()
            return

        if self.document is None:
            return

        try:
            self.audio_player.play(self.document)
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"Playback failed:\n{exc}")
            self._set_state("Stopped")
            return

        self.play_button.setText("Stop")
        self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.playhead_timer.start()
        self.waveform_view.set_playhead_time(0.0)
        self._set_state("Playing", self.document.file_name)

    def _stop_playback(self) -> None:
        position = self.audio_player.stop()
        self.playhead_timer.stop()
        self.waveform_view.set_playhead_time(position)
        self.play_button.setText("Play")
        self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        if self.document is not None:
            self._set_state("Stopped", f"{position:.2f} s")

    @Slot()
    def _update_playhead(self) -> None:
        position = self.audio_player.get_position_seconds()
        self.waveform_view.set_playhead_time(position)
        if not self.audio_player.is_playing():
            self._stop_playback()

    @Slot(float, float)
    def _selection_changed(self, start: float, end: float) -> None:
        self.inspector_panel.set_selection_range(start, end)
        self._update_edit_buttons()

    def _update_edit_buttons(self) -> None:
        has_selected_note = (
            self.document is not None
            and self.edit_thread is None
            and bool(self.document.note_segments)
            and self.selected_note_index is not None
        )
        self.pitch_down_button.setEnabled(has_selected_note)
        self.pitch_up_button.setEnabled(has_selected_note)
        self.detect_notes_button.setEnabled(
            self.document is not None
            and bool(self.document.pitch_frames)
            and self.edit_thread is None
        )
        self._update_note_buttons()
        self._update_phase4_buttons()

    def _update_note_buttons(self) -> None:
        has_notes = (
            self.document is not None
            and bool(self.document.note_segments)
            and self.selected_note_index is not None
            and self.edit_thread is None
        )
        self._set_note_controls_enabled(has_notes)
        self.pitch_down_button.setEnabled(has_notes)
        self.pitch_up_button.setEnabled(has_notes)
        self._update_phase4_buttons()

    def _set_note_controls_enabled(self, enabled: bool) -> None:
        for button in (
            self.previous_note_button,
            self.next_note_button,
            self.note_down_button,
            self.note_up_button,
            self.note_start_earlier_button,
            self.note_start_later_button,
            self.note_shorter_button,
            self.note_longer_button,
        ):
            button.setEnabled(enabled)

    def _update_phase4_buttons(self) -> None:
        can_process = self.document is not None and self.edit_thread is None
        has_pitch = can_process and bool(self.document.pitch_frames)
        has_notes = can_process and bool(self.document.note_segments)
        has_note = has_notes and self.selected_note_index is not None
        has_range = can_process and self.waveform_view.selection_range() is not None

        self.scale_key_combo.setEnabled(has_notes)
        self.scale_mode_combo.setEnabled(has_notes)
        self.snap_note_button.setEnabled(has_note)
        self.snap_all_button.setEnabled(has_notes)
        self.vibrato_down_button.setEnabled(has_pitch and has_range)
        self.vibrato_up_button.setEnabled(has_pitch and has_range)
        self.scoop_button.setEnabled(has_note)
        self.fall_button.setEnabled(has_note)
        self.formant_down_button.setEnabled(has_range)
        self.formant_up_button.setEnabled(has_range)

    def _set_phase4_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.scale_key_combo,
            self.scale_mode_combo,
            self.snap_note_button,
            self.snap_all_button,
            self.vibrato_down_button,
            self.vibrato_up_button,
            self.scoop_button,
            self.fall_button,
            self.formant_down_button,
            self.formant_up_button,
        ):
            widget.setEnabled(enabled)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.open_button.setEnabled(enabled)
        self.input_mode_combo.setEnabled(enabled)
        self.analyze_button.setEnabled(enabled and self.document is not None)
        self.play_button.setEnabled(enabled and self.document is not None)
        self.export_button.setEnabled(enabled and self.document is not None)
        self.detect_notes_button.setEnabled(
            enabled
            and self.document is not None
            and bool(self.document.pitch_frames)
        )
        if enabled:
            self._update_edit_buttons()
            self._update_note_buttons()
            self._update_phase4_buttons()
        else:
            self.pitch_down_button.setEnabled(False)
            self.pitch_up_button.setEnabled(False)
            self._set_note_controls_enabled(False)
            self._set_phase4_controls_enabled(False)

    def _refresh_notes_from_pitch(self, select_time: float | None = None) -> int:
        if self.document is None:
            return 0

        notes = NoteSegmenter().segment(
            self.document.pitch_frames,
            self.document.analysis_duration,
            self.document.chord_changes,
        )
        self.document.note_segments = notes
        if not notes:
            self.selected_note_index = None
            self.waveform_view.set_note_segments([])
            self.inspector_panel.set_notes([])
            self._update_note_buttons()
            return 0

        selected_index = self._note_index_for_time(notes, select_time)
        if selected_index is None:
            selected_index = 0
        self._select_note_index(selected_index)
        return len(notes)

    def _note_index_for_time(
        self,
        notes: list[NoteSegment],
        time_value: float | None,
    ) -> int | None:
        if time_value is None:
            return None
        for index, note in enumerate(notes):
            if note.start <= time_value <= note.end:
                return index

        if not notes:
            return None
        return min(
            range(len(notes)),
            key=lambda index: abs((notes[index].start + notes[index].end) * 0.5 - time_value),
        )

    def _select_note_index(self, index: int | None) -> None:
        if self.document is None or not self.document.note_segments:
            self.selected_note_index = None
            self.waveform_view.set_note_segments([])
            self.inspector_panel.set_notes([])
            self._update_note_buttons()
            return

        if index is None:
            index = 0
        index = max(0, min(index, len(self.document.note_segments) - 1))
        self.selected_note_index = index
        note = self.document.note_segments[index]
        self.waveform_view.set_note_segments(self.document.note_segments, index)
        self.waveform_view.set_selection_range(note.start, note.end)
        self.inspector_panel.set_notes(self.document.note_segments, index)
        self.inspector_panel.set_selection_range(note.start, note.end)
        self._update_note_buttons()
        self._update_phase4_buttons()

    def _selected_note(self) -> NoteSegment | None:
        if self.document is None or self.selected_note_index is None:
            return None
        if not 0 <= self.selected_note_index < len(self.document.note_segments):
            return None
        return self.document.note_segments[self.selected_note_index]

    def _selected_note_center(self) -> float | None:
        note = self._selected_note()
        if note is None:
            return None
        return note.start + note.duration * 0.5

    def _active_edit_range(self) -> TimeRange | None:
        note = self._selected_note()
        if note is not None:
            return TimeRange(note.start, note.end)

        selection = self.waveform_view.selection_range()
        if selection is None:
            return None
        if self.document is None:
            return None
        return TimeRange(selection[0], selection[1]).normalized(self.document.duration)

    def _set_state(self, state: str, detail: str | None = None) -> None:
        message = state if not detail else f"{state} - {detail}"
        self.statusBar().showMessage(message)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "VoClay", message)

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        self.audio_player.stop()
        if self.analysis_thread is not None and self.analysis_thread.isRunning():
            self.analysis_thread.quit()
            self.analysis_thread.wait(500)
        if self.edit_thread is not None and self.edit_thread.isRunning():
            self.edit_thread.quit()
            self.edit_thread.wait(500)
        super().closeEvent(event)
