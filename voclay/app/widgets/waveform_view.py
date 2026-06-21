from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QBrush, QPen
from PySide6.QtWidgets import QGraphicsRectItem, QVBoxLayout, QWidget

from voclay.app.audio_document import AudioDocument
from voclay.app.models import NoteSegment, PitchFrame
from voclay.app.theme import COLORS


class NoteBlockItem(QGraphicsRectItem):
    def __init__(self, note: NoteSegment, index: int, selected: bool, view: "WaveformView") -> None:
        super().__init__(QRectF(note.start, note.midi_note - 0.38, note.duration, 0.76))
        self.index = index
        self.view = view
        self.selected = selected
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setZValue(5)
        self._apply_style(selected, hovered=False)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802
        self.view.note_selected.emit(self.index)
        event.accept()

    def hoverEnterEvent(self, event) -> None:  # noqa: ANN001, N802
        self._apply_style(self.selected, hovered=True)
        event.accept()

    def hoverLeaveEvent(self, event) -> None:  # noqa: ANN001, N802
        self._apply_style(self.selected, hovered=False)
        event.accept()

    def _apply_style(self, selected: bool, hovered: bool) -> None:
        if selected:
            brush = QBrush(QColor(255, 184, 107, 120))
            pen = QPen(QColor(COLORS["warning"]))
            pen.setWidthF(1.8)
        elif hovered:
            brush = QBrush(QColor(184, 156, 255, 105))
            pen = QPen(QColor(COLORS["accent_alt"]))
            pen.setWidthF(1.4)
        else:
            brush = QBrush(QColor(184, 156, 255, 70))
            pen = QPen(QColor(COLORS["accent_alt"]))
            pen.setWidthF(1.0)
        self.setBrush(brush)
        self.setPen(pen)


class WaveformView(QWidget):
    selection_changed = Signal(float, float)
    note_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)

        self.waveform_plot = pg.PlotWidget()
        self.pitch_plot = pg.PlotWidget()
        self.waveform_playhead: pg.InfiniteLine | None = None
        self.pitch_playhead: pg.InfiniteLine | None = None
        self.waveform_selection: pg.LinearRegionItem | None = None
        self.pitch_selection: pg.LinearRegionItem | None = None
        self._duration = 0.0
        self._selection_start = 0.0
        self._selection_end = 0.0
        self._syncing_selection = False
        self._note_segments: list[NoteSegment] = []
        self._note_items: list[NoteBlockItem] = []
        self._selected_note_index: int | None = None

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
        self.waveform_selection = None
        self.pitch_selection = None
        self._note_segments = []
        self._note_items = []
        self._selected_note_index = None
        self._duration = 0.0
        self._selection_start = 0.0
        self._selection_end = 0.0
        self._add_playheads()
        self.waveform_plot.setYRange(-1.05, 1.05)
        self.pitch_plot.setYRange(36, 96)

    def set_audio(self, document: AudioDocument) -> None:
        self.clear()

        sample_count = document.mono_samples.shape[0]
        if sample_count == 0:
            return

        self._duration = document.duration
        max_points = 48000
        if sample_count > max_points:
            indices = np.linspace(0, sample_count - 1, max_points).astype(np.int64)
            y_values = document.current_mono_samples[indices]
            x_values = indices / float(document.sample_rate)
        else:
            y_values = document.current_mono_samples
            x_values = np.arange(sample_count, dtype=np.float32) / float(document.sample_rate)

        self.waveform_plot.plot(
            x_values,
            y_values,
            pen=pg.mkPen(COLORS["accent_alt"], width=1.2),
            connect="finite",
        )
        self.waveform_plot.setXRange(0.0, max(0.1, document.duration), padding=0.01)
        self.waveform_plot.setYRange(-1.05, 1.05)
        if document.duration > 0:
            default_end = min(document.duration, max(0.25, document.duration * 0.25))
            self.set_selection_range(0.0, default_end, emit=False)

    def set_pitch_frames(self, frames: list[PitchFrame]) -> None:
        self.pitch_plot.clear()
        self.pitch_selection = None
        self._note_items = []

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

        self._add_pitch_selection_region()
        self._add_pitch_playhead()

    def set_note_segments(
        self,
        notes: list[NoteSegment],
        selected_index: int | None = None,
    ) -> None:
        self._note_segments = notes
        if selected_index is not None and not 0 <= selected_index < len(notes):
            selected_index = None
        self._selected_note_index = selected_index
        self._draw_note_segments()

    def set_selected_note_index(self, index: int | None) -> None:
        if index is not None and not 0 <= index < len(self._note_segments):
            index = None
        self._selected_note_index = index
        self._draw_note_segments()

    def set_playhead_time(self, seconds: float) -> None:
        if self.waveform_playhead is not None:
            self.waveform_playhead.setValue(seconds)
        if self.pitch_playhead is not None:
            self.pitch_playhead.setValue(seconds)

    def selection_range(self) -> tuple[float, float] | None:
        if self._selection_end <= self._selection_start:
            return None
        return self._selection_start, self._selection_end

    def set_selection_range(self, start: float, end: float, emit: bool = True) -> None:
        start, end = self._clamp_selection(start, end)
        self._selection_start = start
        self._selection_end = end
        self._sync_selection_items()
        if emit:
            self.selection_changed.emit(start, end)

    def _add_playheads(self) -> None:
        self.waveform_playhead = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=False,
            pen=pg.mkPen(COLORS["warning"], width=2),
        )
        self.waveform_playhead.setZValue(20)
        self.waveform_plot.addItem(self.waveform_playhead)
        self._add_pitch_playhead()

    def _add_pitch_playhead(self) -> None:
        self.pitch_playhead = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=False,
            pen=pg.mkPen(COLORS["warning"], width=2),
        )
        self.pitch_playhead.setZValue(20)
        self.pitch_plot.addItem(self.pitch_playhead)

    def _draw_note_segments(self) -> None:
        for item in self._note_items:
            try:
                self.pitch_plot.removeItem(item)
            except Exception:  # noqa: BLE001
                pass
        self._note_items = []

        if not self._note_segments:
            return

        for index, note in enumerate(self._note_segments):
            item = NoteBlockItem(
                note=note,
                index=index,
                selected=index == self._selected_note_index,
                view=self,
            )
            self.pitch_plot.addItem(item)
            self._note_items.append(item)

    def _add_selection_region(self, plot: pg.PlotWidget) -> pg.LinearRegionItem:
        brush = pg.mkBrush(121, 216, 208, 40)
        hover_brush = pg.mkBrush(184, 156, 255, 55)
        pen = pg.mkPen(COLORS["accent"], width=1.2)
        hover_pen = pg.mkPen(COLORS["accent_alt"], width=1.4)
        region = pg.LinearRegionItem(
            values=(self._selection_start, self._selection_end),
            orientation="vertical",
            brush=brush,
            pen=pen,
            hoverBrush=hover_brush,
            hoverPen=hover_pen,
            movable=True,
            bounds=(0.0, max(0.0, self._duration)),
        )
        region.setZValue(8)
        plot.addItem(region)
        return region

    def _add_waveform_selection_region(self) -> None:
        if self.waveform_selection is not None or self._duration <= 0:
            return
        self.waveform_selection = self._add_selection_region(self.waveform_plot)
        self.waveform_selection.sigRegionChanged.connect(self._waveform_region_changed)

    def _add_pitch_selection_region(self) -> None:
        if self.pitch_selection is not None or self._duration <= 0:
            return
        self.pitch_selection = self._add_selection_region(self.pitch_plot)
        self.pitch_selection.sigRegionChanged.connect(self._pitch_region_changed)

    def _sync_selection_items(self) -> None:
        self._syncing_selection = True
        try:
            self._add_waveform_selection_region()
            self._add_pitch_selection_region()
            for item in (self.waveform_selection, self.pitch_selection):
                if item is not None:
                    item.blockSignals(True)
                    item.setRegion((self._selection_start, self._selection_end))
                    item.blockSignals(False)
        finally:
            self._syncing_selection = False

    def _waveform_region_changed(self) -> None:
        self._region_changed(self.waveform_selection)

    def _pitch_region_changed(self) -> None:
        self._region_changed(self.pitch_selection)

    def _region_changed(self, item: pg.LinearRegionItem | None) -> None:
        if self._syncing_selection or item is None:
            return
        start, end = item.getRegion()
        self.set_selection_range(float(start), float(end), emit=True)

    def _clamp_selection(self, start: float, end: float) -> tuple[float, float]:
        start = max(0.0, min(float(start), self._duration))
        end = max(0.0, min(float(end), self._duration))
        if end < start:
            start, end = end, start
        return start, end

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
