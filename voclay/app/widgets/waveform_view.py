from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout, QWidget

from voclay.app.audio_document import AudioDocument
from voclay.app.models import PitchFrame
from voclay.app.theme import COLORS


class WaveformView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)

        self.waveform_plot = pg.PlotWidget()
        self.pitch_plot = pg.PlotWidget()
        self.waveform_playhead: pg.InfiniteLine | None = None
        self.pitch_playhead: pg.InfiniteLine | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.waveform_plot, stretch=3)
        layout.addWidget(self.pitch_plot, stretch=2)

        self._style_plot(self.waveform_plot, "Waveform", "Amplitude")
        self._style_plot(self.pitch_plot, "Pitch", "MIDI")
        self.pitch_plot.setXLink(self.waveform_plot)
        self.clear()

    def _style_plot(self, plot: pg.PlotWidget, title: str, left_label: str) -> None:
        plot.setBackground(COLORS["panel"])
        plot.showGrid(x=True, y=True, alpha=0.18)
        plot.setTitle(title, color=COLORS["text"], size="11pt")
        plot.setLabel("bottom", "Time", units="s", color=COLORS["text_muted"])
        plot.setLabel("left", left_label, color=COLORS["text_muted"])

        item = plot.getPlotItem()
        item.getAxis("bottom").setPen(pg.mkPen(COLORS["border"]))
        item.getAxis("left").setPen(pg.mkPen(COLORS["border"]))
        item.getAxis("bottom").setTextPen(pg.mkPen(COLORS["text_muted"]))
        item.getAxis("left").setTextPen(pg.mkPen(COLORS["text_muted"]))

    def clear(self) -> None:
        self.waveform_plot.clear()
        self.pitch_plot.clear()
        self._add_playheads()
        self.waveform_plot.setYRange(-1.05, 1.05)
        self.pitch_plot.setYRange(36, 96)

    def set_audio(self, document: AudioDocument) -> None:
        self.clear()

        sample_count = document.mono_samples.shape[0]
        if sample_count == 0:
            return

        max_points = 48000
        if sample_count > max_points:
            indices = np.linspace(0, sample_count - 1, max_points).astype(np.int64)
            y_values = document.mono_samples[indices]
            x_values = indices / float(document.sample_rate)
        else:
            y_values = document.mono_samples
            x_values = np.arange(sample_count, dtype=np.float32) / float(document.sample_rate)

        self.waveform_plot.plot(
            x_values,
            y_values,
            pen=pg.mkPen(COLORS["accent_alt"], width=1.2),
            connect="finite",
        )
        self.waveform_plot.setXRange(0.0, max(0.1, document.duration), padding=0.01)
        self.waveform_plot.setYRange(-1.05, 1.05)

    def set_pitch_frames(self, frames: list[PitchFrame]) -> None:
        self.pitch_plot.clear()

        times: list[float] = []
        midi_values: list[float] = []
        for frame in frames:
            midi_note = frame.midi_note
            times.append(frame.time)
            midi_values.append(float("nan") if midi_note is None else midi_note)

        finite_values = np.asarray([value for value in midi_values if math.isfinite(value)], dtype=float)
        if finite_values.size:
            low = max(24, math.floor(float(finite_values.min())) - 2)
            high = min(108, math.ceil(float(finite_values.max())) + 2)
            self._add_pitch_grid(low, high)
            self.pitch_plot.setYRange(low, high)
        else:
            self._add_pitch_grid(36, 96)
            self.pitch_plot.setYRange(36, 96)

        if times:
            self.pitch_plot.plot(
                np.asarray(times, dtype=float),
                np.asarray(midi_values, dtype=float),
                pen=pg.mkPen(COLORS["accent"], width=2.0),
                connect="finite",
            )

        self._add_pitch_playhead()

    def set_playhead_time(self, seconds: float) -> None:
        if self.waveform_playhead is not None:
            self.waveform_playhead.setValue(seconds)
        if self.pitch_playhead is not None:
            self.pitch_playhead.setValue(seconds)

    def _add_playheads(self) -> None:
        self.waveform_playhead = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=False,
            pen=pg.mkPen(COLORS["warning"], width=2),
        )
        self.waveform_plot.addItem(self.waveform_playhead)
        self._add_pitch_playhead()

    def _add_pitch_playhead(self) -> None:
        self.pitch_playhead = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=False,
            pen=pg.mkPen(COLORS["warning"], width=2),
        )
        self.pitch_plot.addItem(self.pitch_playhead)

    def _add_pitch_grid(self, low: int, high: int) -> None:
        for note in range(low, high + 1):
            if note % 12 == 0:
                width = 1.0
                alpha = 75
            else:
                width = 0.6
                alpha = 32
            color = pg.mkColor(COLORS["text_muted"])
            color.setAlpha(alpha)
            line = pg.InfiniteLine(
                pos=float(note),
                angle=0,
                movable=False,
                pen=pg.mkPen(color, width=width),
            )
            self.pitch_plot.addItem(line)
