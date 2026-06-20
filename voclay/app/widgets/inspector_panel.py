from __future__ import annotations

from statistics import mean

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from voclay.app.audio_document import AudioDocument
from voclay.app.models import PitchFrame
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
        self.pitch_range = QLabel("-")
        self.pitch_frames = QLabel("-")
        self.confidence = QLabel("-")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)
        layout.addWidget(self.logo_label)
        layout.addWidget(self._section("File", self._file_form()))
        layout.addWidget(self._section("Analysis", self._analysis_form()))
        layout.addWidget(self._section("Future Controls", self._future_controls()))
        layout.addStretch(1)

    def clear(self) -> None:
        self.file_name.setText("No file")
        self.sample_rate.setText("-")
        self.channels.setText("-")
        self.duration.setText("-")
        self.pitch_range.setText("-")
        self.pitch_frames.setText("-")
        self.confidence.setText("-")

    def set_document(self, document: AudioDocument) -> None:
        self.file_name.setText(document.file_name)
        self.sample_rate.setText(f"{document.sample_rate:,} Hz")
        self.channels.setText(str(document.channels))
        self.duration.setText(f"{document.duration:.2f} s")
        self.pitch_range.setText("-")
        self.pitch_frames.setText("-")
        self.confidence.setText("-")

    def set_pitch_frames(self, frames: list[PitchFrame]) -> None:
        voiced = [frame for frame in frames if frame.voiced and frame.f0 is not None]
        self.pitch_frames.setText(f"{len(voiced):,} voiced / {len(frames):,} total")

        if not voiced:
            self.pitch_range.setText("-")
            self.confidence.setText("-")
            return

        f0_values = [float(frame.f0) for frame in voiced if frame.f0 is not None]
        self.pitch_range.setText(f"{min(f0_values):.1f} - {max(f0_values):.1f} Hz")

        confidence_values = [
            frame.confidence
            for frame in voiced
            if frame.confidence is not None
        ]
        if confidence_values:
            self.confidence.setText(f"{mean(confidence_values):.2f} avg")
        else:
            self.confidence.setText("-")

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
        form.addRow("Pitch range", self.pitch_range)
        form.addRow("Frames", self.pitch_frames)
        form.addRow("Confidence", self.confidence)
        return form

    def _future_controls(self) -> QWidget:
        holder = QWidget()
        layout = QFormLayout(holder)
        layout.setLabelAlignment(Qt.AlignLeft)

        for label in ("Pitch", "Timing", "Smooth", "Vibrato"):
            slider = QSlider(Qt.Horizontal)
            slider.setRange(-100, 100)
            slider.setValue(0)
            slider.setEnabled(False)
            slider.setToolTip("Reserved for later editing features")
            layout.addRow(label, slider)

        return holder

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
