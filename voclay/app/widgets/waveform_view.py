from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QBrush,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QWidget,
)

from voclay.app.audio_document import AudioDocument
from voclay.app.models import NoteSegment, PitchFrame
from voclay.app.theme import COLORS


class PianoRollGraphicsView(QGraphicsView):
    def __init__(self, editor: "WaveformView") -> None:
        super().__init__(editor)
        self.editor = editor
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor(COLORS["panel"])))
        self._range_drag_anchor: float | None = None

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        self.editor.draw_piano_roll_background(painter, rect)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.button() == Qt.LeftButton and not self._event_hits_note(event.pos()):
            scene_pos = self.mapToScene(event.pos())
            if scene_pos.x() >= self.editor.keyboard_width:
                self._range_drag_anchor = self.editor.x_to_time(scene_pos.x())
                self.editor.set_selection_range(self._range_drag_anchor, self._range_drag_anchor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._range_drag_anchor is not None:
            current = self.editor.x_to_time(self.mapToScene(event.pos()).x())
            self.editor.set_selection_range(self._range_drag_anchor, current)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._range_drag_anchor is not None:
            current = self.editor.x_to_time(self.mapToScene(event.pos()).x())
            self.editor.set_selection_range(self._range_drag_anchor, current)
            self._range_drag_anchor = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: ANN001, N802
        if self.editor.handle_key_press(event.key()):
            event.accept()
            return
        super().keyPressEvent(event)

    def _event_hits_note(self, pos) -> bool:  # noqa: ANN001
        item = self.itemAt(pos)
        while item is not None:
            if isinstance(item, NoteBlockItem):
                return True
            item = item.parentItem()
        return False


class NoteBlockItem(QGraphicsRectItem):
    HANDLE_WIDTH = 8.0

    def __init__(self, note: NoteSegment, index: int, selected: bool, editor: "WaveformView") -> None:
        super().__init__(editor.note_rect(note))
        self.note = note
        self.index = index
        self.editor = editor
        self.selected = selected
        self.mode = "move"
        self.drag_start_scene = QPointF()
        self.drag_start_note = note
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)
        self.label = QGraphicsSimpleTextItem(note.note_name, self)
        self.label.setAcceptedMouseButtons(Qt.NoButton)
        self.pitch_path = QGraphicsPathItem(self)
        self.pitch_path.setAcceptedMouseButtons(Qt.NoButton)
        self.pitch_path.setPen(QPen(QColor(232, 236, 242, 135), 1.1))
        self._layout_label()
        self._layout_pitch_path()
        self._apply_style(hovered=False)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        self.editor.note_selected.emit(self.index)
        self.editor.view.setFocus(Qt.MouseFocusReason)
        local_x = self._note_local_x(event)
        width = self.rect().width()
        if local_x <= self.HANDLE_WIDTH:
            self.mode = "resize_left"
            self.setCursor(Qt.SizeHorCursor)
        elif local_x >= width - self.HANDLE_WIDTH:
            self.mode = "resize_right"
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.mode = "move"
            self.setCursor(Qt.SizeAllCursor)

        self.drag_start_scene = event.scenePos()
        self.drag_start_note = self.note
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001, N802
        delta = event.scenePos() - self.drag_start_scene
        start = self.drag_start_note.start
        end = self.drag_start_note.end
        midi = self.drag_start_note.midi_note

        if self.mode == "resize_left":
            start += delta.x() / self.editor.pixels_per_second
        elif self.mode == "resize_right":
            end += delta.x() / self.editor.pixels_per_second
        else:
            shift = delta.x() / self.editor.pixels_per_second
            start += shift
            end += shift
            midi = round(self.drag_start_note.midi_note - delta.y() / self.editor.note_height)

        start, end, midi = self.editor.clamp_note_edit(self.index, start, end, midi, self.mode)
        self.note = self.drag_start_note.with_range(start, end).with_pitch(midi)
        self.set_note(self.note)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001, N802
        self.editor.note_edited.emit(self.index, self.note.start, self.note.end, self.note.midi_note)
        self.unsetCursor()
        event.accept()

    def hoverMoveEvent(self, event) -> None:  # noqa: ANN001, N802
        local_x = self._note_local_x(event)
        width = self.rect().width()
        if local_x <= self.HANDLE_WIDTH or local_x >= width - self.HANDLE_WIDTH:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)
        event.accept()

    def hoverEnterEvent(self, event) -> None:  # noqa: ANN001, N802
        self._apply_style(hovered=True)
        event.accept()

    def hoverLeaveEvent(self, event) -> None:  # noqa: ANN001, N802
        self._apply_style(hovered=False)
        self.unsetCursor()
        event.accept()

    def _layout_label(self) -> None:
        rect = self.rect()
        self.label.setPos(rect.x() + 6, rect.y() + max(1.0, rect.height() * 0.14))

    def _note_local_x(self, event) -> float:  # noqa: ANN001
        return event.pos().x() - self.rect().x()

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self._apply_style(hovered=False)

    def set_note(self, note: NoteSegment) -> None:
        self.note = note
        self.setRect(self.editor.note_rect(note))
        self.label.setText(note.note_name)
        self._layout_label()
        self._layout_pitch_path()

    def _layout_pitch_path(self) -> None:
        rect = self.rect().adjusted(4.0, 3.0, -4.0, -3.0)
        points = [point for point in self.note.pitch_points if point.midi is not None]
        if len(points) < 2 or rect.width() <= 2:
            self.pitch_path.setPath(QPainterPath())
            return

        midi_values = [float(point.midi) for point in points if point.midi is not None]
        low = min(midi_values)
        high = max(midi_values)
        span = max(0.25, high - low)
        time_span = max(0.001, self.note.end - self.note.start)

        path = QPainterPath()
        for index, point in enumerate(points):
            midi = float(point.midi) if point.midi is not None else float(self.note.midi_note)
            x = rect.left() + ((point.time - self.note.start) / time_span) * rect.width()
            y = rect.center().y() - ((midi - self.note.original_midi_median) / span) * rect.height() * 0.45
            y = max(rect.top(), min(rect.bottom(), y))
            if index == 0:
                path.moveTo(QPointF(x, y))
            else:
                path.lineTo(QPointF(x, y))
        self.pitch_path.setPath(path)

    def _apply_style(self, hovered: bool) -> None:
        if self.selected:
            fill = QColor(COLORS["accent"])
            fill.setAlpha(176)
            border = QColor(COLORS["accent"])
        elif hovered:
            fill = QColor(121, 216, 208, 128)
            border = QColor(COLORS["accent"])
        else:
            fill = QColor(COLORS["accent_alt"])
            fill.setAlpha(142)
            border = QColor(COLORS["accent_alt"])

        pen = QPen(border)
        pen.setWidthF(1.6 if self.selected else 1.1)
        self.setPen(pen)
        self.setBrush(QBrush(fill))
        self.label.setBrush(QBrush(QColor(COLORS["text"])))


class WaveformView(QWidget):
    selection_changed = Signal(float, float)
    note_selected = Signal(int)
    note_edited = Signal(int, float, float, float)
    note_deleted = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.keyboard_width = 76.0
        self.pixels_per_second = 120.0
        self.note_height = 22.0
        self.min_note_duration = 0.05

        self._duration = 0.0
        self._midi_low = 60
        self._midi_high = 84
        self._selection_start = 0.0
        self._selection_end = 0.0
        self._pitch_frames: list[PitchFrame] = []
        self._note_segments: list[NoteSegment] = []
        self._selected_note_index: int | None = None
        self._note_items: list[NoteBlockItem] = []
        self._selection_item: QGraphicsRectItem | None = None
        self._playhead_item: QGraphicsLineItem | None = None
        self._pitch_curve_item: QGraphicsPathItem | None = None

        self.scene = QGraphicsScene(self)
        self.view = PianoRollGraphicsView(self)
        self.view.setScene(self.scene)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.clear()

    def clear(self) -> None:
        self.scene.clear()
        self._duration = 0.0
        self._midi_low = 60
        self._midi_high = 84
        self._selection_start = 0.0
        self._selection_end = 0.0
        self._pitch_frames = []
        self._note_segments = []
        self._selected_note_index = None
        self._note_items = []
        self._selection_item = None
        self._playhead_item = None
        self._pitch_curve_item = None
        self._update_scene_rect()
        self._ensure_overlay_items()

    def set_audio(self, document: AudioDocument) -> None:
        self.clear()
        self._duration = max(0.0, document.duration)
        self._update_scene_rect()
        if document.duration > 0:
            default_end = min(document.duration, max(0.25, document.duration * 0.25))
            self.set_selection_range(0.0, default_end, emit=False)

    def set_pitch_frames(self, frames: list[PitchFrame]) -> None:
        self._pitch_frames = frames
        self._update_midi_range()
        self._update_scene_rect()
        self._draw_pitch_curve()
        self._update_overlay_geometry()
        self.scene.update()

    def set_note_segments(
        self,
        notes: list[NoteSegment],
        selected_index: int | None = None,
    ) -> None:
        same_notes = notes == self._note_segments and len(notes) == len(self._note_items)
        self._note_segments = notes
        if selected_index is not None and not 0 <= selected_index < len(notes):
            selected_index = None
        self._selected_note_index = selected_index

        if same_notes:
            self._update_note_item_selection()
            self.scene.update()
            return

        self._update_midi_range()
        self._update_scene_rect()
        self._draw_pitch_curve()
        self._draw_note_segments()
        self._update_overlay_geometry()
        self.scene.update()

    def set_selected_note_index(self, index: int | None) -> None:
        if index is not None and not 0 <= index < len(self._note_segments):
            index = None
        self._selected_note_index = index
        self._update_note_item_selection()
        self.scene.update()

    def set_playhead_time(self, seconds: float) -> None:
        self._ensure_overlay_items()
        x = self.time_to_x(seconds)
        if self._playhead_item is not None:
            self._playhead_item.setLine(x, 0.0, x, self.scene_height)

    def selection_range(self) -> tuple[float, float] | None:
        if self._selection_end <= self._selection_start:
            return None
        return self._selection_start, self._selection_end

    def set_selection_range(self, start: float, end: float, emit: bool = True) -> None:
        start = max(0.0, min(float(start), self._duration))
        end = max(0.0, min(float(end), self._duration))
        if end < start:
            start, end = end, start
        self._selection_start = start
        self._selection_end = end
        self._update_selection_item()
        if emit:
            self.selection_changed.emit(start, end)

    def handle_key_press(self, key: int) -> bool:
        if self._selected_note_index is None:
            return False

        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.note_deleted.emit(self._selected_note_index)
            return True
        if key == Qt.Key_Up:
            self._apply_keyboard_edit(midi_delta=1)
            return True
        if key == Qt.Key_Down:
            self._apply_keyboard_edit(midi_delta=-1)
            return True
        if key == Qt.Key_Left:
            self._apply_keyboard_edit(time_delta=-0.02)
            return True
        if key == Qt.Key_Right:
            self._apply_keyboard_edit(time_delta=0.02)
            return True
        return False

    def _apply_keyboard_edit(self, time_delta: float = 0.0, midi_delta: int = 0) -> None:
        index = self._selected_note_index
        if index is None or not 0 <= index < len(self._note_segments):
            return

        note = self._note_segments[index]
        start, end, midi = self.clamp_note_edit(
            index,
            note.start + time_delta,
            note.end + time_delta,
            note.midi_note + midi_delta,
            "move",
        )
        edited = note.with_range(start, end).with_pitch(midi)
        self._note_segments = list(self._note_segments)
        self._note_segments[index] = edited
        if 0 <= index < len(self._note_items):
            self._note_items[index].set_note(edited)
            self._note_items[index].set_selected(True)
        self.set_selection_range(edited.start, edited.end, emit=False)
        self.note_edited.emit(index, edited.start, edited.end, edited.midi_note)
        self.scene.update()

    @property
    def scene_width(self) -> float:
        return self.keyboard_width + max(8.0, self._duration * self.pixels_per_second) + 48.0

    @property
    def scene_height(self) -> float:
        return max(1, self._midi_high - self._midi_low + 1) * self.note_height

    def time_to_x(self, seconds: float) -> float:
        return self.keyboard_width + max(0.0, min(seconds, self._duration)) * self.pixels_per_second

    def x_to_time(self, x_value: float) -> float:
        seconds = (x_value - self.keyboard_width) / self.pixels_per_second
        return max(0.0, min(seconds, self._duration))

    def midi_to_y(self, midi_note: float) -> float:
        return (self._midi_high - midi_note + 0.5) * self.note_height

    def note_rect(self, note: NoteSegment) -> QRectF:
        x = self.time_to_x(note.start)
        width = max(8.0, (note.end - note.start) * self.pixels_per_second)
        y = self.midi_to_y(note.midi_note) - self.note_height * 0.36
        return QRectF(x, y, width, self.note_height * 0.72)

    def clamp_note_edit(
        self,
        index: int,
        start: float,
        end: float,
        midi_note: float,
        mode: str = "move",
    ) -> tuple[float, float, float]:
        midi_note = round(max(self._midi_low, min(midi_note, self._midi_high)))
        lower_bound = self._note_segments[index - 1].end if index > 0 else 0.0
        upper_bound = (
            self._note_segments[index + 1].start
            if index < len(self._note_segments) - 1
            else self._duration
        )
        available = max(0.0, upper_bound - lower_bound)
        if available <= self.min_note_duration:
            return round(lower_bound, 2), round(upper_bound, 2), midi_note

        start = round(start, 2)
        end = round(end, 2)

        if mode == "resize_left":
            end = max(lower_bound + self.min_note_duration, min(end, upper_bound))
            start = max(lower_bound, min(start, end - self.min_note_duration))
        elif mode == "resize_right":
            start = max(lower_bound, min(start, upper_bound - self.min_note_duration))
            end = min(upper_bound, max(end, start + self.min_note_duration))
        else:
            duration = min(max(self.min_note_duration, self._note_segments[index].duration), available)
            start = max(lower_bound, min(start, upper_bound - duration))
            end = start + duration

        return round(start, 2), round(end, 2), midi_note

    def draw_piano_roll_background(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(COLORS["panel"]))
        self._draw_time_grid(painter)
        self._draw_pitch_rows(painter)
        self._draw_keyboard(painter)

    def _draw_time_grid(self, painter: QPainter) -> None:
        height = self.scene_height
        minor_pen = QPen(QColor(232, 236, 242, 30))
        major_pen = QPen(QColor(121, 216, 208, 70))
        text_pen = QPen(QColor(COLORS["text_muted"]))

        step = 0.25
        count = int(math.ceil(self._duration / step)) + 1
        for tick in range(count):
            seconds = tick * step
            x = self.time_to_x(seconds)
            is_major = tick % 4 == 0
            painter.setPen(major_pen if is_major else minor_pen)
            painter.drawLine(QPointF(x, 0), QPointF(x, height))
            if is_major:
                painter.setPen(text_pen)
                painter.drawText(QRectF(x + 4, 2, 64, 18), Qt.AlignLeft, f"{seconds:.0f}s")

    def _draw_pitch_rows(self, painter: QPainter) -> None:
        for midi in range(self._midi_low, self._midi_high + 1):
            y = (self._midi_high - midi) * self.note_height
            pitch_class = midi % 12
            if pitch_class in (1, 3, 6, 8, 10):
                painter.fillRect(
                    QRectF(self.keyboard_width, y, self.scene_width - self.keyboard_width, self.note_height),
                    QColor(16, 19, 26, 68),
                )
            pen_color = QColor(232, 236, 242, 48 if pitch_class == 0 else 24)
            painter.setPen(QPen(pen_color))
            painter.drawLine(QPointF(self.keyboard_width, y), QPointF(self.scene_width, y))

    def _draw_keyboard(self, painter: QPainter) -> None:
        painter.fillRect(QRectF(0, 0, self.keyboard_width, self.scene_height), QColor(COLORS["background_alt"]))
        names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        for midi in range(self._midi_low, self._midi_high + 1):
            y = (self._midi_high - midi) * self.note_height
            pitch_class = midi % 12
            is_black = pitch_class in (1, 3, 6, 8, 10)
            fill = QColor(32, 37, 50) if is_black else QColor(232, 236, 242)
            text = QColor(COLORS["text"]) if is_black else QColor(COLORS["background"])
            painter.fillRect(QRectF(0, y, self.keyboard_width, self.note_height), fill)
            painter.setPen(QPen(QColor(16, 19, 26, 120)))
            painter.drawRect(QRectF(0, y, self.keyboard_width, self.note_height))
            if pitch_class == 0 or not is_black:
                octave = midi // 12 - 1
                label = f"{names[pitch_class]}{octave}" if pitch_class == 0 else names[pitch_class]
                painter.setPen(QPen(text))
                painter.drawText(QRectF(6, y, self.keyboard_width - 10, self.note_height), Qt.AlignVCenter, label)

        painter.fillRect(QRectF(self.keyboard_width - 2, 0, 2, self.scene_height), QColor(COLORS["border"]))

    def _update_midi_range(self) -> None:
        values: list[float] = [note.midi_note for note in self._note_segments]
        values.extend(frame.midi_note for frame in self._pitch_frames if frame.midi_note is not None)
        if not values:
            self._midi_low = 60
            self._midi_high = 84
            return

        low = max(12, int(math.floor(min(values))) - 3)
        high = min(108, int(math.ceil(max(values))) + 3)
        if high - low < 12:
            center = (high + low) // 2
            low = max(12, center - 6)
            high = min(108, center + 6)
        self._midi_low = low
        self._midi_high = high

    def _update_scene_rect(self) -> None:
        self.scene.setSceneRect(QRectF(0, 0, self.scene_width, self.scene_height))

    def _ensure_overlay_items(self) -> None:
        if self._selection_item is None:
            self._selection_item = QGraphicsRectItem()
            self._selection_item.setAcceptedMouseButtons(Qt.NoButton)
            self._selection_item.setBrush(QBrush(QColor(121, 216, 208, 38)))
            self._selection_item.setPen(QPen(QColor(121, 216, 208, 95)))
            self._selection_item.setZValue(2)
            self.scene.addItem(self._selection_item)

        if self._playhead_item is None:
            self._playhead_item = QGraphicsLineItem()
            self._playhead_item.setAcceptedMouseButtons(Qt.NoButton)
            pen = QPen(QColor(COLORS["warning"]))
            pen.setWidthF(2.0)
            self._playhead_item.setPen(pen)
            self._playhead_item.setZValue(30)
            self.scene.addItem(self._playhead_item)

    def _update_overlay_geometry(self) -> None:
        self._ensure_overlay_items()
        self._update_selection_item()
        if self._playhead_item is not None:
            x = self._playhead_item.line().x1() or self.keyboard_width
            self._playhead_item.setLine(x, 0.0, x, self.scene_height)

    def _update_selection_item(self) -> None:
        self._ensure_overlay_items()
        if self._selection_item is None:
            return
        x1 = self.time_to_x(self._selection_start)
        x2 = self.time_to_x(self._selection_end)
        self._selection_item.setRect(QRectF(x1, 0.0, max(1.0, x2 - x1), self.scene_height))

    def _draw_pitch_curve(self) -> None:
        if self._pitch_curve_item is not None:
            self.scene.removeItem(self._pitch_curve_item)
            self._pitch_curve_item = None

        path = QPainterPath()
        active = False
        for frame in self._pitch_frames:
            midi = frame.midi_note
            if midi is None:
                active = False
                continue
            point = QPointF(self.time_to_x(frame.time), self.midi_to_y(midi))
            if not active:
                path.moveTo(point)
                active = True
            else:
                path.lineTo(point)

        if path.isEmpty():
            return

        item = QGraphicsPathItem(path)
        pen = QPen(QColor(121, 216, 208, 105))
        pen.setWidthF(1.4)
        item.setPen(pen)
        item.setAcceptedMouseButtons(Qt.NoButton)
        item.setZValue(4)
        self.scene.addItem(item)
        self._pitch_curve_item = item

    def _draw_note_segments(self) -> None:
        for item in self._note_items:
            self.scene.removeItem(item)
        self._note_items = []

        for index, note in enumerate(self._note_segments):
            item = NoteBlockItem(
                note=note,
                index=index,
                selected=index == self._selected_note_index,
                editor=self,
            )
            self.scene.addItem(item)
            self._note_items.append(item)

    def _update_note_item_selection(self) -> None:
        for index, item in enumerate(self._note_items):
            item.set_selected(index == self._selected_note_index)
