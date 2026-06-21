from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
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

from voclay.app.audio_editor import AudioEditor
from voclay.app.audio_document import AudioDocument
from voclay.app.audio_player import AudioPlayer
from voclay.app.models import PitchEdit, PitchFrame, TimeRange
from voclay.app.pitch_analyzer import PitchAnalyzer
from voclay.app.theme import asset_path
from voclay.app.widgets.inspector_panel import InspectorPanel
from voclay.app.widgets.waveform_view import WaveformView


class PitchAnalysisWorker(QObject):
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, document: AudioDocument) -> None:
        super().__init__()
        self.document = document

    @Slot()
    def run(self) -> None:
        try:
            frames = PitchAnalyzer().analyze(self.document)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.finished.emit(frames)


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
        self.edit_worker: PitchShiftWorker | None = None

        self.waveform_view = WaveformView()
        self.inspector_panel = InspectorPanel()
        self.open_button = self._make_button("Open", QStyle.SP_DialogOpenButton)
        self.analyze_button = self._make_button("Analyze", QStyle.SP_FileDialogDetailedView)
        self.play_button = self._make_button("Play", QStyle.SP_MediaPlay)
        self.pitch_down_button = self._make_button("-1 semitone", QStyle.SP_ArrowDown)
        self.pitch_up_button = self._make_button("+1 semitone", QStyle.SP_ArrowUp)
        self.export_button = self._make_button("Export WAV", QStyle.SP_DialogSaveButton)
        self.file_label = QLabel("No file loaded")
        self.file_label.setObjectName("MutedLabel")
        self.file_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.open_button.clicked.connect(self.open_file)
        self.analyze_button.clicked.connect(self.analyze_pitch)
        self.play_button.clicked.connect(self.toggle_playback)
        self.pitch_down_button.clicked.connect(lambda: self.apply_pitch_shift(-1.0))
        self.pitch_up_button.clicked.connect(lambda: self.apply_pitch_shift(1.0))
        self.export_button.clicked.connect(self.export_wav)
        self.waveform_view.selection_changed.connect(self._selection_changed)
        self.analyze_button.setEnabled(False)
        self.play_button.setEnabled(False)
        self.pitch_down_button.setEnabled(False)
        self.pitch_up_button.setEnabled(False)
        self.export_button.setEnabled(False)

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
        layout.addSpacing(12)
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
        self.waveform_view.set_audio(document)
        self.inspector_panel.set_document(document)
        selection = self.waveform_view.selection_range()
        if selection is not None:
            self._selection_changed(*selection)
        self.file_label.setText(document.file_name)
        self.analyze_button.setEnabled(True)
        self.play_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self._update_edit_buttons()
        self._set_state("Ready", f"{document.duration:.2f} s")

    @Slot()
    def analyze_pitch(self) -> None:
        if self.document is None or self.analysis_thread is not None:
            return

        self._set_state("Analyzing", self.document.file_name)
        self.analyze_button.setEnabled(False)
        self.open_button.setEnabled(False)

        thread = QThread(self)
        worker = PitchAnalysisWorker(self.document)
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

    @Slot(list)
    def _analysis_finished(self, frames: list[PitchFrame]) -> None:
        if self.document is None:
            return

        self.document.pitch_frames = frames
        self.waveform_view.set_pitch_frames(frames)
        self.inspector_panel.set_pitch_frames(frames)
        voiced_count = sum(1 for frame in frames if frame.voiced)
        self._set_state("Ready", f"{voiced_count:,} voiced pitch frames")

    @Slot(str)
    def _analysis_failed(self, message: str) -> None:
        self._show_error(f"Pitch analysis failed:\n{message}")
        self._set_state("Ready")

    @Slot()
    def _analysis_cleanup(self) -> None:
        self.analysis_thread = None
        self.analysis_worker = None
        self.open_button.setEnabled(True)
        self.analyze_button.setEnabled(self.document is not None)
        self._update_edit_buttons()

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
        self._set_state("Processing", f"{semitones:+.0f} semitone")
        self._set_controls_enabled(False)

        thread = QThread(self)
        worker = PitchShiftWorker(self.document, selection_range, semitones)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._pitch_shift_finished)
        worker.failed.connect(self._pitch_shift_failed)
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

        self.document.apply_pitch_edit(edited_samples, frames, edit)
        self.waveform_view.set_audio(self.document)
        self.waveform_view.set_pitch_frames(self.document.pitch_frames)
        self.waveform_view.set_selection_range(edit.selection.start, edit.selection.end)
        self.inspector_panel.set_document(self.document)
        self.inspector_panel.set_pitch_frames(self.document.pitch_frames)
        self.inspector_panel.set_edit_count(len(self.document.edit_history))
        self.inspector_panel.set_selection_range(edit.selection.start, edit.selection.end)
        self._set_state("Ready", f"shifted {edit.selection.duration:.2f} s by {edit.semitones:+.0f} semitone")

    @Slot(str)
    def _pitch_shift_failed(self, message: str) -> None:
        self._show_error(f"Pitch shift failed:\n{message}")
        self._set_state("Ready")

    @Slot()
    def _pitch_shift_cleanup(self) -> None:
        self.edit_thread = None
        self.edit_worker = None
        self._set_controls_enabled(True)

    @Slot()
    def export_wav(self) -> None:
        if self.document is None:
            return

        suggested = self.document.file_path.with_name(f"{self.document.file_path.stem}_voclay.wav")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export WAV",
            str(suggested),
            "WAV files (*.wav)",
        )
        if not file_path:
            return

        path = Path(file_path)
        if path.suffix.lower() != ".wav":
            path = path.with_suffix(".wav")

        try:
            self.document.export_wav(path)
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"Could not export WAV file:\n{exc}")
            return

        self._set_state("Ready", f"exported {path.name}")

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
        can_edit = (
            self.document is not None
            and self.edit_thread is None
            and self.waveform_view.selection_range() is not None
        )
        self.pitch_down_button.setEnabled(can_edit)
        self.pitch_up_button.setEnabled(can_edit)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.open_button.setEnabled(enabled)
        self.analyze_button.setEnabled(enabled and self.document is not None)
        self.play_button.setEnabled(enabled and self.document is not None)
        self.export_button.setEnabled(enabled and self.document is not None)
        if enabled:
            self._update_edit_buttons()
        else:
            self.pitch_down_button.setEnabled(False)
            self.pitch_up_button.setEnabled(False)

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
