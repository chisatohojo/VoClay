from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from voclay.app.audio_document import AudioDocument
from voclay.app.models import NoteSegment, PitchFrame
from voclay.app.theme import asset_path


class InspectorPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("InspectorPanel")
        self.setMinimumWidth(260)
        self.setMaximumWidth(340)

        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        logo = QPixmap(str(asset_path("voclay_icon_full_background_transparent.png")))
        if not logo.isNull():
            self.logo_label.setPixmap(
                logo.scaled(112, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

        self.file_name = QLabel("No file")
        self.sample_rate = QLabel("-")
        self.channels = QLabel("-")
        self.duration = QLabel("-")
        self.input_mode = QLabel("-")
        self.analysis_audio = QLabel("-")
        self.vocal_separation = QLabel("-")
        self.chord_changes = QLabel("-")
        self.pitch_range = QLabel("-")
        self.pitch_frames = QLabel("-")
        self.notes = QLabel("-")
        self.selected_note = QLabel("-")
        self.edits = QLabel("0")
        self.note_start = QLabel("-")
        self.note_end = QLabel("-")
        self.note_length = QLabel("-")
        self.note_midi = QLabel("-")
        self.note_name = QLabel("-")
        self.note_cents = QLabel("-")
        self.note_split_reason = QLabel("-")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)
        layout.addWidget(self.logo_label)
        layout.addWidget(self._section("File", self._file_form()))
        layout.addWidget(self._section("Analysis", self._analysis_form()))
        layout.addWidget(self._section("Selected note", self._selected_note_form()))
        layout.addStretch(1)

    def clear(self) -> None:
        self.file_name.setText("No file")
        self.sample_rate.setText("-")
        self.channels.setText("-")
        self.duration.setText("-")
        self.input_mode.setText("-")
        self.analysis_audio.setText("-")
        self.vocal_separation.setText("-")
        self.chord_changes.setText("-")
        self.pitch_range.setText("-")
        self.pitch_frames.setText("-")
        self.notes.setText("-")
        self.selected_note.setText("-")
        self.edits.setText("0")
        self._clear_selected_note_detail()

    def set_document(self, document: AudioDocument) -> None:
        self.file_name.setText(document.file_name)
        self.sample_rate.setText(f"{document.sample_rate:,} Hz")
        self.channels.setText(str(document.channels))
        self.duration.setText(f"{document.duration:.2f} s")
        self.input_mode.setText(document.input_mode)
        self.analysis_audio.setText(document.analysis_audio_path.name if document.analysis_audio_path else "-")
        self.vocal_separation.setText(document.vocal_separation_message)
        self.chord_changes.setText(str(len(document.chord_changes)))
        self.pitch_range.setText("-")
        self.pitch_frames.setText("-")
        self.notes.setText(str(len(document.vocal_notes)) if document.vocal_notes else "-")
        self.selected_note.setText("-")
        self.edits.setText(str(len(document.edit_history)))
        self._clear_selected_note_detail()

    def set_pitch_frames(self, frames: list[PitchFrame]) -> None:
        voiced = [frame for frame in frames if frame.voiced and frame.f0 is not None]
        self.pitch_frames.setText(f"{len(voiced):,} voiced / {len(frames):,} total")

        if not voiced:
            self.pitch_range.setText("-")
            return

        f0_values = [float(frame.f0) for frame in voiced if frame.f0 is not None]
        self.pitch_range.setText(f"{min(f0_values):.1f} - {max(f0_values):.1f} Hz")

    def set_analysis_status(self, document: AudioDocument) -> None:
        self.input_mode.setText(document.input_mode)
        self.analysis_audio.setText(document.analysis_audio_path.name if document.analysis_audio_path else "-")
        self.vocal_separation.setText(document.vocal_separation_message)
        self.chord_changes.setText(str(len(document.chord_changes)))

    def set_selection_range(self, start: float, end: float) -> None:
        pass

    def set_edit_count(self, count: int) -> None:
        self.edits.setText(str(count))

    def set_notes(self, notes: list[NoteSegment], selected_index: int | None = None) -> None:
        self.notes.setText(str(len(notes)) if notes else "-")
        if selected_index is None or not 0 <= selected_index < len(notes):
            self.selected_note.setText("-")
            self._clear_selected_note_detail()
            return

        note = notes[selected_index]
        self.selected_note.setText(f"{note.note_name}  {note.start:.2f}-{note.end:.2f} s")
        self.note_start.setText(f"{note.start:.2f} s")
        self.note_end.setText(f"{note.end:.2f} s")
        self.note_length.setText(f"{note.duration:.2f} s")
        self.note_midi.setText(str(int(round(note.midi_note))))
        self.note_name.setText(note.note_name)
        self.note_cents.setText(f"{note.cents_offset:+.1f} cents")
        self.note_split_reason.setText(note.split_reason)

    def _file_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.addRow("Name", self.file_name)
        form.addRow("Sample rate", self.sample_rate)
        form.addRow("Channels", self.channels)
        form.addRow("Length", self.duration)
        return form

    def _analysis_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.addRow("Input mode", self.input_mode)
        form.addRow("Analysis audio", self.analysis_audio)
        form.addRow("Vocal separation", self.vocal_separation)
        form.addRow("Chord changes", self.chord_changes)
        form.addRow("Pitch range", self.pitch_range)
        form.addRow("Frames", self.pitch_frames)
        form.addRow("Notes", self.notes)
        form.addRow("Selected note", self.selected_note)
        form.addRow("Edits", self.edits)
        return form

    def _selected_note_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.addRow("Start", self.note_start)
        form.addRow("End", self.note_end)
        form.addRow("Length", self.note_length)
        form.addRow("MIDI note", self.note_midi)
        form.addRow("Note name", self.note_name)
        form.addRow("Cents offset", self.note_cents)
        form.addRow("Split reason", self.note_split_reason)
        return form

    def _clear_selected_note_detail(self) -> None:
        self.note_start.setText("-")
        self.note_end.setText("-")
        self.note_length.setText("-")
        self.note_midi.setText("-")
        self.note_name.setText("-")
        self.note_cents.setText("-")
        self.note_split_reason.setText("-")

    def _section(self, title: str, content: QWidget | QFormLayout) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("AppTitle" if title == "File" else "MutedLabel")
        layout.addWidget(title_label)

        if isinstance(content, QFormLayout):
            content_widget = QWidget()
            content_widget.setLayout(content)
            layout.addWidget(content_widget)
        else:
            layout.addWidget(content)

        return wrapper
