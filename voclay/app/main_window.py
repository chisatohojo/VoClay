from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median

import soundfile as sf
from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from voclay.app.audio_document import AudioDocument
from voclay.app.audio_player import AudioPlayer
from voclay.app.audio_renderer import AudioRenderer, RenderResult
from voclay.app.models import PitchFrame, VocalNote
from voclay.app.note_segmenter import NoteSegmenter
from voclay.app.pitch_analyzer import PitchAnalyzer
from voclay.app.project_document import ProjectDocument
from voclay.app.theme import asset_path
from voclay.app.widgets.inspector_panel import InspectorPanel
from voclay.app.widgets.waveform_view import WaveformView


@dataclass
class TrackAnalysisResult:
    track_type: str
    frames: list[PitchFrame]
    notes: list[VocalNote]
    status_message: str


class TrackAnalysisWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, document: AudioDocument, track_type: str) -> None:
        super().__init__()
        self.document = document
        self.track_type = track_type

    @Slot()
    def run(self) -> None:
        try:
            frames = PitchAnalyzer().analyze(self.document)
            voiced_count = sum(1 for frame in frames if frame.voiced and frame.f0 is not None)
            locked = self.track_type == "reference"
            notes = NoteSegmenter().segment(
                frames,
                self.document.analysis_duration,
                track_type=self.track_type,
                locked=locked,
            )
            status = (
                f"{self.track_type}: {len(frames):,} F0 frames, "
                f"{voiced_count:,} voiced, {len(notes):,} notes"
            )
            if voiced_count < 3:
                status = f"{self.track_type}: F0 detection failed or too few voiced frames"
                notes = []
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.finished.emit(TrackAnalysisResult(self.track_type, frames, notes, status))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VoClay")
        self.resize(1280, 760)

        icon_file = asset_path("voclay_icon_outer_background_transparent.png")
        if icon_file.exists():
            self.setWindowIcon(QIcon(str(icon_file)))

        self.project = ProjectDocument()
        self.audio_player = AudioPlayer()
        self.playhead_timer = QTimer(self)
        self.playhead_timer.setInterval(30)
        self.playhead_timer.timeout.connect(self._update_playhead)

        self.analysis_thread: QThread | None = None
        self.analysis_worker: TrackAnalysisWorker | None = None
        self.selected_source_indices: set[int] = set()

        self.piano_roll = WaveformView()
        self.inspector_panel = InspectorPanel()
        self.load_reference_button = self._make_button("Load Reference WAV", QStyle.SP_DialogOpenButton)
        self.analyze_reference_button = self._make_button("Analyze Reference", QStyle.SP_FileDialogDetailedView)
        self.load_source_button = self._make_button("Load Source WAV", QStyle.SP_DialogOpenButton)
        self.analyze_source_button = self._make_button("Analyze Source", QStyle.SP_FileDialogDetailedView)
        self.match_selected_button = self._make_button("Match Selected", QStyle.SP_DialogApplyButton)
        self.render_preview_button = self._make_button("Render Preview", QStyle.SP_MediaPlay)
        self.play_from_selection_button = self._make_button("Play from Selection", QStyle.SP_MediaPlay)
        self.stop_button = self._make_button("Stop", QStyle.SP_MediaStop)
        self.export_button = self._make_button("Export WAV", QStyle.SP_DialogSaveButton)
        self.edit_scope_combo = QComboBox()
        self.edit_scope_combo.addItems(["Selected Notes", "All Source Notes"])
        self.edit_scope_combo.setCurrentText("Selected Notes")
        self.file_label = QLabel("Load a reference and source WAV")
        self.file_label.setObjectName("MutedLabel")
        self.file_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.load_reference_button.clicked.connect(lambda: self.load_audio("reference"))
        self.analyze_reference_button.clicked.connect(lambda: self.analyze_track("reference"))
        self.load_source_button.clicked.connect(lambda: self.load_audio("source"))
        self.analyze_source_button.clicked.connect(lambda: self.analyze_track("source"))
        self.match_selected_button.clicked.connect(self.match_selected)
        self.render_preview_button.clicked.connect(self.render_preview)
        self.play_from_selection_button.clicked.connect(self.play_from_selection)
        self.stop_button.clicked.connect(self.stop_playback)
        self.export_button.clicked.connect(self.export_wav)
        self.edit_scope_combo.currentTextChanged.connect(self._edit_scope_changed)

        self.piano_roll.note_selected.connect(self._source_note_selected)
        self.piano_roll.note_edited.connect(self._source_note_edited)
        self.piano_roll.range_selected.connect(self._range_selected)
        self.piano_roll.playhead_changed.connect(self._playhead_changed)
        self.piano_roll.clear_selection_requested.connect(self.clear_source_selection)
        self.piano_roll.zoom_changed.connect(self._timeline_zoom_changed)
        self.piano_roll.delete_selected_requested.connect(self.delete_selected_source_notes)
        self.piano_roll.keyboard_edit_requested.connect(self.keyboard_edit_selected)
        self.piano_roll.split_requested.connect(self.split_selected_note)
        self.piano_roll.merge_requested.connect(self.merge_selected_notes)
        self.piano_roll.play_requested.connect(self.play_from_selection)
        self.piano_roll.selection_changed.connect(self._selection_changed)

        self._build_layout()
        self._refresh_all()
        self._set_state("Ready")

    def _build_layout(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 8)
        root_layout.setSpacing(10)
        root_layout.addWidget(self._top_bar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.piano_roll)
        splitter.addWidget(self.inspector_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([960, 320])
        root_layout.addWidget(splitter, stretch=1)
        self.setCentralWidget(root)

    def _top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        logo_label = QLabel()
        logo = QPixmap(str(asset_path("voclay_icon_outer_background_transparent.png")))
        if not logo.isNull():
            logo_label.setPixmap(logo.scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        title = QLabel("VoClay")
        title.setObjectName("AppTitle")

        layout.addWidget(logo_label)
        layout.addWidget(title)
        layout.addSpacing(10)
        layout.addWidget(self.load_reference_button)
        layout.addWidget(self.analyze_reference_button)
        layout.addWidget(self.load_source_button)
        layout.addWidget(self.analyze_source_button)
        layout.addWidget(self.match_selected_button)
        layout.addWidget(self.render_preview_button)
        layout.addWidget(self.play_from_selection_button)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.export_button)
        layout.addSpacing(8)
        mode_label = QLabel("Edit Scope")
        mode_label.setObjectName("MutedLabel")
        layout.addWidget(mode_label)
        layout.addWidget(self.edit_scope_combo)
        layout.addSpacing(10)
        layout.addWidget(self.file_label, stretch=1)
        return bar

    def _make_button(self, label: str, standard_icon: QStyle.StandardPixmap) -> QToolButton:
        button = QToolButton()
        button.setText(label)
        button.setIcon(self.style().standardIcon(standard_icon))
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setCursor(Qt.PointingHandCursor)
        return button

    @Slot()
    def load_audio(self, track_type: str) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Reference WAV" if track_type == "reference" else "Load Source WAV",
            str(Path.home()),
            "WAV files (*.wav)",
        )
        if not file_path:
            return

        try:
            document = AudioDocument.load(file_path)
            document.set_input_mode("Reference" if track_type == "reference" else "Source")
            document.use_source_for_analysis()
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"Could not load WAV file:\n{exc}")
            return

        self.stop_playback(update_state=False)
        if track_type == "reference":
            self.project.reference_audio = document
            self.project.reference_notes = []
        else:
            self.project.source_audio = document
            self.project.source_notes = []
            self.selected_source_indices = set()
            self.project.edit_count = 0
        self.project.clear_preview("Preview needs render")
        self._refresh_all()
        self._set_state("Ready", f"loaded {track_type} {document.file_name}")

    @Slot()
    def analyze_track(self, track_type: str) -> None:
        if self.analysis_thread is not None:
            return
        document = self.project.reference_audio if track_type == "reference" else self.project.source_audio
        if document is None:
            self._set_state("Ready", f"Load {track_type} audio first")
            return

        self._set_controls_enabled(False)
        self._set_state("Analyzing", track_type)
        thread = QThread(self)
        worker = TrackAnalysisWorker(document, track_type)
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
    def _analysis_finished(self, result: TrackAnalysisResult) -> None:
        document = self.project.reference_audio if result.track_type == "reference" else self.project.source_audio
        if document is None:
            return

        document.pitch_frames = result.frames
        document.note_segments = result.notes
        if result.track_type == "reference":
            self.project.reference_notes = result.notes
        else:
            self.project.source_notes = result.notes
            self.selected_source_indices = set()
            self.project.edit_count = 0
            self.project.clear_preview("Preview needs render")
        self._refresh_all()
        self._set_state("Ready", result.status_message)

    @Slot(str)
    def _analysis_failed(self, message: str) -> None:
        self._show_error(f"Analysis failed:\n{message}")
        self._set_state("Ready", "analysis failed")

    @Slot()
    def _analysis_cleanup(self) -> None:
        self.analysis_thread = None
        self.analysis_worker = None
        self._set_controls_enabled(True)
        self._update_buttons()

    @Slot(int, bool)
    def _source_note_selected(self, index: int, additive: bool) -> None:
        if not 0 <= index < len(self.project.source_notes):
            return
        if additive:
            if index in self.selected_source_indices:
                self.selected_source_indices.remove(index)
            else:
                self.selected_source_indices.add(index)
        else:
            self.selected_source_indices = {index}

        note = self.project.source_notes[index]
        self.piano_roll.set_selected_source_indices(self.selected_source_indices)
        self.piano_roll.set_selection_range(note.start, note.end, emit=False)
        self.inspector_panel.set_selected_notes(self._selected_source_notes())
        self._update_buttons()

    @Slot(float, float, bool)
    def _range_selected(self, start: float, end: float, additive: bool) -> None:
        matches = {
            index
            for index, note in enumerate(self.project.source_notes)
            if note.start < end and note.end > start
        }
        if additive:
            self.selected_source_indices |= matches
        else:
            self.selected_source_indices = matches
        self.piano_roll.set_selected_source_indices(self.selected_source_indices)
        self.inspector_panel.set_selected_notes(self._selected_source_notes())
        self._update_buttons()

    @Slot()
    def clear_source_selection(self) -> None:
        if not self.selected_source_indices:
            return
        self.selected_source_indices = set()
        self.piano_roll.set_selected_source_indices(set())
        self.inspector_panel.set_selected_notes([])
        self._update_buttons()
        self._set_state("Ready", "selection cleared")

    @Slot(int, float, float, float, str, float, int)
    def _source_note_edited(
        self,
        index: int,
        start: float,
        end: float,
        midi_note: float,
        mode: str,
        delta_time: float,
        delta_midi: int,
    ) -> None:
        if not 0 <= index < len(self.project.source_notes):
            return
        notes = list(self.project.source_notes)
        selected: list[VocalNote] = []

        if mode == "move":
            targets = self._edit_target_indices(index)
            delta_time = self._clamped_time_delta(notes, targets, delta_time)
            for target in targets:
                if not 0 <= target < len(notes):
                    continue
                note = notes[target]
                edited = (
                    note.with_range(note.start + delta_time, note.end + delta_time)
                    .with_pitch(note.midi_note + delta_midi)
                    .with_split_reason("edited_by_user")
                )
                notes[target] = edited
                selected.append(edited)
            self._commit_source_notes(notes, selected)
            if delta_midi and abs(delta_time) > 0.0001:
                self._set_state("Ready", f"Moved {len(selected)} note(s) by {delta_time:+.2f}s and {delta_midi:+d} semitone(s)")
            elif delta_midi:
                self._set_state("Ready", f"Shifted {len(selected)} note(s) by {delta_midi:+d} semitone(s)")
            else:
                self._set_state("Ready", f"Moved {len(selected)} note(s) by {delta_time:+.2f}s")
            return

        edited = notes[index].with_range(start, end).with_pitch(midi_note).with_split_reason("edited_by_user")
        notes[index] = edited
        self._commit_source_notes(notes, [edited])
        self._set_state("Ready", f"resized {edited.note_name}")

    @Slot(float, int)
    def keyboard_edit_selected(self, time_delta: float, midi_delta: int) -> None:
        targets = self._edit_target_indices(None)
        if not targets:
            self._set_state("Ready", "No source note selected")
            return
        notes = list(self.project.source_notes)
        selected: list[VocalNote] = []
        if abs(time_delta) > 0.0:
            time_delta = self._clamped_time_delta(notes, targets, time_delta)
        for index in sorted(targets):
            if not 0 <= index < len(notes):
                continue
            note = notes[index]
            edited = note
            if midi_delta:
                edited = edited.with_pitch(note.midi_note + midi_delta)
            if abs(time_delta) > 0.0:
                start = note.start + time_delta
                end = note.end + time_delta
                start = max(0.0, start)
                if end - start >= 0.05:
                    edited = edited.with_range(start, end)
            edited = edited.with_split_reason("edited_by_user")
            notes[index] = edited
            selected.append(edited)
        self._commit_source_notes(notes, selected)
        scope = self.edit_scope_combo.currentText()
        if midi_delta:
            self._set_state("Ready", f"Shifted {scope.lower()} by {midi_delta:+d} semitone(s)")
        elif abs(time_delta) > 0.0:
            self._set_state("Ready", f"Moved {scope.lower()} by {time_delta:+.2f}s")
        else:
            self._set_state("Ready", "No movement applied")

    @Slot()
    def delete_selected_source_notes(self) -> None:
        if not self.selected_source_indices:
            return
        notes = [
            note
            for index, note in enumerate(self.project.source_notes)
            if index not in self.selected_source_indices
        ]
        self.selected_source_indices = set()
        self._commit_source_notes(notes, [], bump_edit=True)
        self._set_state("Ready", "deleted selected Source Notes")

    @Slot()
    def split_selected_note(self) -> None:
        if len(self.selected_source_indices) != 1:
            self._set_state("Ready", "Select one Source Note to split")
            return
        index = next(iter(self.selected_source_indices))
        if not 0 <= index < len(self.project.source_notes):
            return
        note = self.project.source_notes[index]
        split_time = self.piano_roll.playhead_time()
        if not note.start + 0.05 <= split_time <= note.end - 0.05:
            self._set_state("Ready", "Move playhead inside the selected Source Note")
            return

        ratio = (split_time - note.start) / max(0.001, note.duration)
        original_split = note.original_start + ratio * max(0.001, note.original_end - note.original_start)
        left_points = tuple(point for point in note.pitch_points if point.time <= original_split)
        right_points = tuple(point for point in note.pitch_points if point.time >= original_split)
        if not left_points:
            left_points = note.pitch_points
        if not right_points:
            right_points = note.pitch_points

        left = (
            note.with_range(note.start, split_time)
            .with_original_range(note.original_start, original_split, left_points, "split_by_user")
        )
        right = (
            note.with_range(split_time, note.end)
            .with_original_range(original_split, note.original_end, right_points, "split_by_user")
        )
        notes = list(self.project.source_notes)
        notes[index : index + 1] = [left, right]
        self._commit_source_notes(notes, [left, right])
        self._set_state("Ready", "split Source Note")

    @Slot()
    def merge_selected_notes(self) -> None:
        if len(self.selected_source_indices) < 2:
            self._set_state("Ready", "Select at least two Source Notes to merge")
            return
        selected = [
            self.project.source_notes[index]
            for index in sorted(self.selected_source_indices)
            if 0 <= index < len(self.project.source_notes)
        ]
        if len(selected) < 2:
            return

        total_duration = sum(max(0.001, note.duration) for note in selected)
        midi_note = int(round(sum(note.midi_note * max(0.001, note.duration) for note in selected) / total_duration))
        original_midi = sum(note.original_midi_median * max(0.001, note.duration) for note in selected) / total_duration
        points = tuple(sorted((point for note in selected for point in note.pitch_points), key=lambda point: point.time))
        f0_values = [point.f0 for point in points if point.f0 is not None]
        merged = VocalNote(
            id=0,
            start_time=min(note.start for note in selected),
            end_time=max(note.end for note in selected),
            midi_note=midi_note,
            track_type="source",
            original_start_time=min(note.original_start for note in selected),
            original_end_time=max(note.original_end for note in selected),
            cents_offset=(original_midi - midi_note) * 100.0,
            original_midi_median=original_midi,
            pitch_points=points,
            split_reason="merged_by_user",
            locked=False,
            confidence=self._average_confidence(selected),
            average_f0=median(f0_values) if f0_values else 0.0,
        )
        notes = [
            note
            for index, note in enumerate(self.project.source_notes)
            if index not in self.selected_source_indices
        ]
        notes.append(merged)
        self._commit_source_notes(notes, [merged])
        self._set_state("Ready", "merged Source Notes")

    @Slot()
    def match_selected(self) -> None:
        if not self.selected_source_indices:
            self._set_state("Ready", "No Source Note selected")
            return
        if not self.project.reference_notes:
            self._set_state("Ready", "Analyze Reference first")
            return

        notes = list(self.project.source_notes)
        selected: list[VocalNote] = []
        for index in sorted(self.selected_source_indices):
            if not 0 <= index < len(notes):
                continue
            source = notes[index]
            target = min(
                self.project.reference_notes,
                key=lambda item: abs(self._note_center(item) - self._note_center(source)),
            )
            edited = (
                source.with_range(target.start, target.end)
                .with_pitch(target.midi_note)
                .with_split_reason("matched_reference")
            )
            notes[index] = edited
            selected.append(edited)
        self._commit_source_notes(notes, selected)
        self._set_state("Ready", f"matched {len(selected)} Source Note(s)")

    @Slot()
    def render_preview(self) -> None:
        if self.project.source_audio is None:
            self._set_state("Ready", "Load Source WAV first")
            return
        if not self.project.source_notes:
            self._set_state("Ready", "Analyze Source first")
            return

        self._set_controls_enabled(False)
        self._set_state("Rendering", "preview")
        try:
            result = AudioRenderer().render_preview(
                self.project.source_audio,
                self.project.source_notes,
                self.project.source_audio.sample_rate,
            )
        except Exception as exc:  # noqa: BLE001
            self.project.rendered_preview = None
            self.project.preview_status = f"Render failed: {exc}"
            self._show_error(f"Render Preview failed:\n{exc}")
            self._set_controls_enabled(True)
            self._refresh_all()
            return

        self.project.rendered_preview = result
        self.project.preview_status = result.message if result.success else f"Render failed: {result.message}"
        self._set_controls_enabled(True)
        self._refresh_all()
        self._set_state("Ready", self.project.preview_status)

    @Slot()
    def play_from_selection(self) -> None:
        if self.audio_player.is_playing():
            self.stop_playback()
            return

        start_time = self._play_start_time()
        try:
            if self.project.has_preview and isinstance(self.project.rendered_preview, RenderResult):
                result = self.project.rendered_preview
                self.audio_player.play_samples(result.samples, result.sample_rate, start_time)
                label = "preview"
            elif self.project.source_audio is not None:
                self.audio_player.play(self.project.source_audio, start_time)
                label = "source"
            elif self.project.reference_audio is not None:
                self.audio_player.play(self.project.reference_audio, start_time)
                label = "reference"
            else:
                self._set_state("Ready", "Load audio first")
                return
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"Playback failed:\n{exc}")
            return

        self.playhead_timer.start()
        self.piano_roll.set_playhead_time(start_time)
        self._set_state("Playing", f"{label} from {start_time:.2f} s")

    @Slot()
    def stop_playback(self, update_state: bool = True) -> None:
        position = self.audio_player.stop()
        self.playhead_timer.stop()
        self.piano_roll.set_playhead_time(position)
        if update_state:
            self._set_state("Stopped", f"{position:.2f} s")

    @Slot()
    def export_wav(self) -> None:
        if not self.project.has_preview or not isinstance(self.project.rendered_preview, RenderResult):
            QMessageBox.warning(
                self,
                "VoClay",
                "Render Preview before exporting WAV.",
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export WAV",
            str(Path.home() / "voclay_preview.wav"),
            "WAV files (*.wav)",
        )
        if not file_path:
            return
        try:
            sf.write(file_path, self.project.rendered_preview.samples, self.project.rendered_preview.sample_rate)
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"Export failed:\n{exc}")
            return
        self._set_state("Ready", f"exported {Path(file_path).name}")

    @Slot()
    def _update_playhead(self) -> None:
        position = self.audio_player.get_position_seconds()
        self.piano_roll.set_playhead_time(position)
        if not self.audio_player.is_playing():
            self.stop_playback()

    @Slot(float)
    def _playhead_changed(self, seconds: float) -> None:
        self._set_state("Ready", f"playhead {seconds:.2f} s")

    @Slot(float)
    def _timeline_zoom_changed(self, zoom: float) -> None:
        self._set_state("Ready", f"Timeline zoom: {zoom * 100:.0f}%")

    @Slot(str)
    def _edit_scope_changed(self, edit_scope: str) -> None:
        self.piano_roll.set_edit_scope(edit_scope)
        self.inspector_panel.set_edit_scope(edit_scope)
        self._set_state("Ready", f"Edit Scope: {edit_scope}")

    @Slot(float, float)
    def _selection_changed(self, start: float, end: float) -> None:
        if end > start:
            self._set_state("Ready", f"selection {start:.2f}-{end:.2f} s")

    def _commit_source_notes(
        self,
        notes: list[VocalNote],
        selected_notes: list[VocalNote],
        bump_edit: bool = True,
    ) -> None:
        sorted_notes = sorted(notes, key=lambda note: (note.start, note.end, note.midi_note))
        selected_indices: set[int] = set()
        renumbered: list[VocalNote] = []
        for index, note in enumerate(sorted_notes):
            updated = note.with_id(index).with_track("source", locked=False)
            renumbered.append(updated)
            if any(note == selected for selected in selected_notes):
                selected_indices.add(index)

        self.project.source_notes = renumbered
        if self.project.source_audio is not None:
            self.project.source_audio.note_segments = renumbered
        self.selected_source_indices = selected_indices
        if bump_edit:
            self.project.bump_edit_count()
            self.project.clear_preview("Preview needs render")
        self._refresh_all()
        if bump_edit:
            self._set_state("Ready", "Preview needs render")

    def _refresh_all(self) -> None:
        self.piano_roll.set_edit_scope(self.edit_scope_combo.currentText())
        self.piano_roll.set_documents(self.project.reference_audio, self.project.source_audio)
        self.piano_roll.set_tracks(
            self.project.reference_notes,
            self.project.source_notes,
            self.selected_source_indices,
        )
        self.inspector_panel.set_project(self.project)
        self.inspector_panel.set_edit_scope(self.edit_scope_combo.currentText())
        self.inspector_panel.set_selected_notes(self._selected_source_notes())
        self._update_file_label()
        self._update_buttons()

    def _set_controls_enabled(self, enabled: bool) -> None:
        for button in (
            self.load_reference_button,
            self.analyze_reference_button,
            self.load_source_button,
            self.analyze_source_button,
            self.match_selected_button,
            self.render_preview_button,
            self.play_from_selection_button,
            self.stop_button,
            self.export_button,
        ):
            button.setEnabled(enabled)
        self.edit_scope_combo.setEnabled(enabled)

    def _update_buttons(self) -> None:
        if self.analysis_thread is not None:
            return
        self.load_reference_button.setEnabled(True)
        self.load_source_button.setEnabled(True)
        self.analyze_reference_button.setEnabled(self.project.reference_audio is not None)
        self.analyze_source_button.setEnabled(self.project.source_audio is not None)
        self.match_selected_button.setEnabled(bool(self.selected_source_indices) and bool(self.project.reference_notes))
        self.render_preview_button.setEnabled(self.project.source_audio is not None and bool(self.project.source_notes))
        self.play_from_selection_button.setEnabled(
            self.project.source_audio is not None
            or self.project.reference_audio is not None
            or self.project.has_preview
        )
        self.stop_button.setEnabled(True)
        self.export_button.setEnabled(self.project.has_preview)
        self.edit_scope_combo.setEnabled(True)

    def _update_file_label(self) -> None:
        reference = self.project.reference_audio.file_name if self.project.reference_audio else "No reference"
        source = self.project.source_audio.file_name if self.project.source_audio else "No source"
        self.file_label.setText(f"Reference: {reference}   Source: {source}")

    def _selected_source_notes(self) -> list[VocalNote]:
        return [
            self.project.source_notes[index]
            for index in sorted(self.selected_source_indices)
            if 0 <= index < len(self.project.source_notes)
        ]

    def _edit_target_indices(self, anchor_index: int | None) -> set[int]:
        if self.edit_scope_combo.currentText() == "All Source Notes":
            return set(range(len(self.project.source_notes)))
        if anchor_index is not None and anchor_index in self.selected_source_indices:
            return set(self.selected_source_indices)
        if anchor_index is not None and 0 <= anchor_index < len(self.project.source_notes):
            return {anchor_index}
        return set(self.selected_source_indices)

    def _clamped_time_delta(
        self,
        notes: list[VocalNote],
        target_indices: set[int],
        delta_time: float,
    ) -> float:
        if not target_indices:
            return 0.0
        earliest = min(notes[index].start for index in target_indices if 0 <= index < len(notes))
        return max(delta_time, -earliest)

    def _play_start_time(self) -> float:
        selected = self._selected_source_notes()
        if selected:
            return min(note.start for note in selected)
        selection = self.piano_roll.selection_range()
        if selection is not None:
            return selection[0]
        return self.piano_roll.playhead_time()

    def _note_center(self, note: VocalNote) -> float:
        return note.start + note.duration * 0.5

    def _average_confidence(self, notes: list[VocalNote]) -> float | None:
        values = [note.confidence for note in notes if note.confidence is not None]
        if not values:
            return None
        return sum(values) / len(values)

    def _set_state(self, state: str, detail: str | None = None) -> None:
        message = state if not detail else f"{state} - {detail}"
        self.statusBar().showMessage(message)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "VoClay", message)

    def keyPressEvent(self, event) -> None:  # noqa: ANN001, N802
        key = event.key()
        if key == Qt.Key_Space:
            self.play_from_selection()
            event.accept()
            return
        if key == Qt.Key_S:
            self.split_selected_note()
            event.accept()
            return
        if key == Qt.Key_M:
            self.merge_selected_notes()
            event.accept()
            return
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected_source_notes()
            event.accept()
            return
        if key == Qt.Key_Up:
            self.keyboard_edit_selected(0.0, 1)
            event.accept()
            return
        if key == Qt.Key_Down:
            self.keyboard_edit_selected(0.0, -1)
            event.accept()
            return
        if key == Qt.Key_Left:
            self.keyboard_edit_selected(-0.02, 0)
            event.accept()
            return
        if key == Qt.Key_Right:
            self.keyboard_edit_selected(0.02, 0)
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        self.audio_player.stop()
        if self.analysis_thread is not None and self.analysis_thread.isRunning():
            self.analysis_thread.quit()
            self.analysis_thread.wait(500)
        super().closeEvent(event)
