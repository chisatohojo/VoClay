from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFormLayout, QFrame, QLabel, QVBoxLayout, QWidget

from voclay.app.audio_document import AudioDocument
from voclay.app.models import VocalNote
from voclay.app.project_document import ProjectDocument
from voclay.app.theme import asset_path


class InspectorPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("InspectorPanel")
        self.setMinimumWidth(280)
        self.setMaximumWidth(360)

        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        logo = QPixmap(str(asset_path("voclay_icon_full_background_transparent.png")))
        if not logo.isNull():
            self.logo_label.setPixmap(
                logo.scaled(112, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

        self.reference_file = QLabel("-")
        self.source_file = QLabel("-")
        self.preview_status = QLabel("Not rendered")

        self.reference_length = QLabel("-")
        self.reference_frames = QLabel("-")
        self.reference_notes = QLabel("-")

        self.source_length = QLabel("-")
        self.source_frames = QLabel("-")
        self.source_notes = QLabel("-")
        self.source_edits = QLabel("0")

        self.selected_count = QLabel("-")
        self.selected_track = QLabel("-")
        self.selected_start = QLabel("-")
        self.selected_end = QLabel("-")
        self.selected_length = QLabel("-")
        self.selected_midi = QLabel("-")
        self.selected_name = QLabel("-")
        self.selected_original_midi = QLabel("-")
        self.selected_pitch_shift = QLabel("-")
        self.selected_split_reason = QLabel("-")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)
        layout.addWidget(self.logo_label)
        layout.addWidget(self._section("Project", self._project_form()))
        layout.addWidget(self._section("Reference", self._reference_form()))
        layout.addWidget(self._section("Source", self._source_form()))
        layout.addWidget(self._section("Selected", self._selected_form()))
        layout.addStretch(1)

    def clear(self) -> None:
        self.set_project(ProjectDocument())

    def set_project(self, project: ProjectDocument) -> None:
        self.reference_file.setText(self._file_name(project.reference_audio))
        self.source_file.setText(self._file_name(project.source_audio))
        self.preview_status.setText(project.preview_status)

        self.reference_length.setText(self._duration(project.reference_audio))
        self.reference_frames.setText(self._frame_count(project.reference_audio))
        self.reference_notes.setText(str(len(project.reference_notes)) if project.reference_notes else "-")

        self.source_length.setText(self._duration(project.source_audio))
        self.source_frames.setText(self._frame_count(project.source_audio))
        self.source_notes.setText(str(len(project.source_notes)) if project.source_notes else "-")
        self.source_edits.setText(str(project.edit_count))

    def set_selected_notes(self, notes: list[VocalNote]) -> None:
        if not notes:
            self.selected_count.setText("-")
            self._clear_selected()
            return

        first = min(notes, key=lambda note: note.start)
        last = max(notes, key=lambda note: note.end)
        length = max(0.0, last.end - first.start)
        self.selected_count.setText(str(len(notes)))
        self.selected_track.setText(first.track_type)
        self.selected_start.setText(f"{first.start:.2f} s")
        self.selected_end.setText(f"{last.end:.2f} s")
        self.selected_length.setText(f"{length:.2f} s")
        if len(notes) == 1:
            self.selected_midi.setText(str(int(round(first.midi_note))))
            self.selected_name.setText(first.note_name)
            self.selected_original_midi.setText(f"{first.original_midi_median:.2f}")
            self.selected_pitch_shift.setText(f"{first.pitch_shift_semitones:+.2f} st")
            self.selected_split_reason.setText(first.split_reason)
        else:
            self.selected_midi.setText("multiple")
            self.selected_name.setText("multiple")
            original = sum(note.original_midi_median for note in notes) / len(notes)
            shift = sum(note.pitch_shift_semitones for note in notes) / len(notes)
            self.selected_original_midi.setText(f"{original:.2f}")
            self.selected_pitch_shift.setText(f"{shift:+.2f} st avg")
            self.selected_split_reason.setText("multiple")

    def _clear_selected(self) -> None:
        self.selected_track.setText("-")
        self.selected_start.setText("-")
        self.selected_end.setText("-")
        self.selected_length.setText("-")
        self.selected_midi.setText("-")
        self.selected_name.setText("-")
        self.selected_original_midi.setText("-")
        self.selected_pitch_shift.setText("-")
        self.selected_split_reason.setText("-")

    def _project_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.addRow("Reference file", self.reference_file)
        form.addRow("Source file", self.source_file)
        form.addRow("Preview status", self.preview_status)
        return form

    def _reference_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.addRow("Length", self.reference_length)
        form.addRow("Pitch frames", self.reference_frames)
        form.addRow("Notes", self.reference_notes)
        return form

    def _source_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.addRow("Length", self.source_length)
        form.addRow("Pitch frames", self.source_frames)
        form.addRow("Notes", self.source_notes)
        form.addRow("Edits", self.source_edits)
        return form

    def _selected_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.addRow("Count", self.selected_count)
        form.addRow("Track type", self.selected_track)
        form.addRow("Start", self.selected_start)
        form.addRow("End", self.selected_end)
        form.addRow("Length", self.selected_length)
        form.addRow("MIDI note", self.selected_midi)
        form.addRow("Note name", self.selected_name)
        form.addRow("Original MIDI", self.selected_original_midi)
        form.addRow("Pitch shift", self.selected_pitch_shift)
        form.addRow("Split reason", self.selected_split_reason)
        return form

    def _section(self, title: str, content: QWidget | QFormLayout) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("AppTitle" if title == "Project" else "MutedLabel")
        layout.addWidget(title_label)

        if isinstance(content, QFormLayout):
            content_widget = QWidget()
            content_widget.setLayout(content)
            layout.addWidget(content_widget)
        else:
            layout.addWidget(content)

        return wrapper

    def _file_name(self, document: AudioDocument | None) -> str:
        return document.file_name if document is not None else "-"

    def _duration(self, document: AudioDocument | None) -> str:
        return f"{document.duration:.2f} s" if document is not None else "-"

    def _frame_count(self, document: AudioDocument | None) -> str:
        if document is None:
            return "-"
        voiced = sum(1 for frame in document.pitch_frames if frame.voiced)
        return f"{voiced:,} voiced / {len(document.pitch_frames):,} total" if document.pitch_frames else "-"
