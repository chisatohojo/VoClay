from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QBrush, QPainter, QPainterPath, QPen
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
from voclay.app.models import VocalNote
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
        self._range_dragged = False

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        self.editor.draw_piano_roll_background(painter, rect)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.button() == Qt.LeftButton and not self._event_hits_source_note(event.pos()):
            scene_pos = self.mapToScene(event.pos())
            if scene_pos.x() >= self.editor.keyboard_width:
                self._range_drag_anchor = self.editor.x_to_time(scene_pos.x())
                self._range_dragged = False
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._range_drag_anchor is not None:
            current = self.editor.x_to_time(self.mapToScene(event.pos()).x())
            self._range_dragged = self._range_dragged or abs(current - self._range_drag_anchor) >= 0.015
            self.editor.set_selection_range(self._range_drag_anchor, current)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._range_drag_anchor is not None:
            current = self.editor.x_to_time(self.mapToScene(event.pos()).x())
            anchor = self._range_drag_anchor
            additive = bool(event.modifiers() & Qt.ShiftModifier)
            self._range_drag_anchor = None
            if self._range_dragged:
                self.editor.set_selection_range(anchor, current)
                start, end = sorted((anchor, current))
                self.editor.range_selected.emit(start, end, additive)
            else:
                inside_range = self.editor.time_in_selection_range(current)
                self.editor.set_playhead_time(current, emit=True)
                if not inside_range:
                    self.editor.clear_selection_range(emit=False)
                    self.editor.range_cleared.emit()
                self.editor.clear_selection_requested.emit()
            self._range_dragged = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: ANN001, N802
        delta = event.angleDelta().y()
        if delta == 0:
            event.accept()
            return

        if event.modifiers() & Qt.ControlModifier:
            cursor_x = self.mapToScene(event.position().toPoint()).x()
            cursor_time = self.editor.x_to_time(cursor_x)
            factor = 1.12 if delta > 0 else 1.0 / 1.12
            zoom = self.editor.set_time_zoom(self.editor.pixels_per_second * factor)
            new_x = self.editor.time_to_x(cursor_time)
            self.horizontalScrollBar().setValue(int(new_x - event.position().x()))
            self.editor.zoom_changed.emit(zoom)
            event.accept()
            return

        step = 86
        notches = delta / 120.0
        bar = self.horizontalScrollBar()
        bar.setValue(int(bar.value() - notches * step))
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: ANN001, N802
        if self.editor.handle_key_press(event.key()):
            event.accept()
            return
        super().keyPressEvent(event)

    def _event_hits_source_note(self, pos) -> bool:  # noqa: ANN001
        item = self.itemAt(pos)
        while item is not None:
            if isinstance(item, NoteBlockItem) and item.is_source:
                return True
            item = item.parentItem()
        return False


class NoteBlockItem(QGraphicsRectItem):
    HANDLE_WIDTH = 8.0

    def __init__(
        self,
        note: VocalNote,
        index: int,
        selected: bool,
        editor: "WaveformView",
    ) -> None:
        super().__init__(editor.note_rect(note))
        self.note = note
        self.index = index
        self.editor = editor
        self.selected = selected
        self.range_target = False
        self.mode = "move"
        self.drag_start_scene = QPointF()
        self.drag_start_note = note
        self.drag_start_notes: list[VocalNote] = []
        self.is_source = note.track_type == "source" and not note.locked
        self.setAcceptedMouseButtons(Qt.LeftButton if self.is_source else Qt.NoButton)
        self.setAcceptHoverEvents(self.is_source)
        self.setZValue(14 if self.is_source else 8)

        self.label = QGraphicsSimpleTextItem(note.note_name, self)
        self.label.setAcceptedMouseButtons(Qt.NoButton)
        self.pitch_path = QGraphicsPathItem(self)
        self.pitch_path.setAcceptedMouseButtons(Qt.NoButton)
        self.pitch_path.setPen(QPen(QColor(232, 236, 242, 115), 1.0))
        self._layout_label()
        self._layout_pitch_path()
        self._apply_style(hovered=False)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802
        if not self.is_source or event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        additive = bool(event.modifiers() & Qt.ShiftModifier)
        if additive or not self.editor.is_source_index_selected(self.index):
            self.editor.note_selected.emit(self.index, additive)
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
        self.drag_start_notes = list(self.editor.source_notes())
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001, N802
        if not self.is_source:
            return

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

        start, end, midi = self.editor.clamp_source_note_edit(self.index, start, end, midi, self.mode)
        self.note = self.drag_start_note.with_range(start, end).with_pitch(midi)
        delta_time = self.note.start - self.drag_start_note.start
        delta_midi = int(round(self.note.midi_note - self.drag_start_note.midi_note))
        self.editor.preview_source_note_drag(
            self.index,
            self.drag_start_notes,
            delta_time,
            delta_midi,
            self.mode,
            self.note,
        )
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001, N802
        if not self.is_source:
            return
        delta_time = self.note.start - self.drag_start_note.start
        delta_midi = int(round(self.note.midi_note - self.drag_start_note.midi_note))
        self.editor.note_edited.emit(
            self.index,
            self.note.start,
            self.note.end,
            self.note.midi_note,
            self.mode,
            delta_time,
            delta_midi,
        )
        self.unsetCursor()
        event.accept()

    def hoverMoveEvent(self, event) -> None:  # noqa: ANN001, N802
        if not self.is_source:
            return
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

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self._apply_style(hovered=False)

    def set_range_target(self, range_target: bool) -> None:
        self.range_target = range_target
        self._apply_style(hovered=False)

    def set_note(self, note: VocalNote) -> None:
        self.note = note
        self.setRect(self.editor.note_rect(note))
        self.label.setText(note.note_name)
        self._layout_label()
        self._layout_pitch_path()

    def _layout_label(self) -> None:
        rect = self.rect()
        self.label.setPos(rect.x() + 6, rect.y() + max(1.0, rect.height() * 0.10))

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
        source_span = max(0.001, self.note.original_end - self.note.original_start)

        path = QPainterPath()
        for index, point in enumerate(points):
            midi = float(point.midi) if point.midi is not None else float(self.note.midi_note)
            progress = (point.time - self.note.original_start) / source_span
            x = rect.left() + progress * rect.width()
            y = rect.center().y() - ((midi - self.note.original_midi_median) / span) * rect.height() * 0.42
            y = max(rect.top(), min(rect.bottom(), y))
            if index == 0:
                path.moveTo(QPointF(x, y))
            else:
                path.lineTo(QPointF(x, y))
        self.pitch_path.setPath(path)

    def _note_local_x(self, event) -> float:  # noqa: ANN001
        return event.pos().x() - self.rect().x()

    def _apply_style(self, hovered: bool) -> None:
        if self.note.track_type == "reference" or self.note.locked:
            fill = QColor(121, 216, 208, 78)
            border = QColor(121, 216, 208, 150)
        elif self.selected:
            fill = QColor("#FFB86B")
            fill.setAlpha(190)
            border = QColor("#FFB86B")
        elif self.range_target:
            fill = QColor("#FFB86B")
            fill.setAlpha(112)
            border = QColor("#FFB86B")
            border.setAlpha(190)
        elif hovered:
            fill = QColor(121, 216, 208, 135)
            border = QColor(121, 216, 208, 220)
        else:
            fill = QColor("#B89CFF")
            fill.setAlpha(155)
            border = QColor("#B89CFF")

        pen = QPen(border)
        pen.setWidthF(1.7 if self.selected else 1.1)
        self.setPen(pen)
        self.setBrush(QBrush(fill))
        self.label.setBrush(QBrush(QColor(COLORS["text"])))


class WaveformView(QWidget):
    selection_changed = Signal(float, float)
    range_selected = Signal(float, float, bool)
    range_cleared = Signal()
    playhead_changed = Signal(float)
    note_selected = Signal(int, bool)
    note_edited = Signal(int, float, float, float, str, float, int)
    clear_selection_requested = Signal()
    zoom_changed = Signal(float)
    delete_selected_requested = Signal()
    keyboard_edit_requested = Signal(float, int)
    split_requested = Signal()
    merge_requested = Signal()
    play_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.keyboard_width = 76.0
        self.pixels_per_second = 120.0
        self.min_pixels_per_second = 45.0
        self.max_pixels_per_second = 520.0
        self.note_height = 22.0
        self.min_note_duration = 0.05
        self.edit_scope = "selected"

        self._duration = 0.0
        self._midi_low = 60
        self._midi_high = 84
        self._selection_start = 0.0
        self._selection_end = 0.0
        self._playhead_time = 0.0
        self._reference_notes: list[VocalNote] = []
        self._source_notes: list[VocalNote] = []
        self._selected_source_indices: set[int] = set()
        self._reference_items: list[NoteBlockItem] = []
        self._source_items: list[NoteBlockItem] = []
        self._selection_item: QGraphicsRectItem | None = None
        self._selection_start_item: QGraphicsLineItem | None = None
        self._selection_end_item: QGraphicsLineItem | None = None
        self._playhead_item: QGraphicsLineItem | None = None

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
        self._playhead_time = 0.0
        self._reference_notes = []
        self._source_notes = []
        self._selected_source_indices = set()
        self._reference_items = []
        self._source_items = []
        self._selection_item = None
        self._selection_start_item = None
        self._selection_end_item = None
        self._playhead_item = None
        self._update_scene_rect()
        self._ensure_overlay_items()

    def set_documents(
        self,
        reference_document: AudioDocument | None,
        source_document: AudioDocument | None,
    ) -> None:
        self._duration = max(
            reference_document.duration if reference_document is not None else 0.0,
            source_document.duration if source_document is not None else 0.0,
            max((note.end for note in self._reference_notes), default=0.0),
            max((note.end for note in self._source_notes), default=0.0),
        )
        self._update_scene_rect()
        self._update_overlay_geometry()
        self.scene.update()

    def set_tracks(
        self,
        reference_notes: list[VocalNote],
        source_notes: list[VocalNote],
        selected_source_indices: set[int] | None = None,
    ) -> None:
        self._reference_notes = reference_notes
        self._source_notes = source_notes
        self._selected_source_indices = set(selected_source_indices or set())
        self._duration = max(
            self._duration,
            max((note.end for note in reference_notes), default=0.0),
            max((note.end for note in source_notes), default=0.0),
        )
        self._update_midi_range()
        self._update_scene_rect()
        self._draw_note_segments()
        self._update_overlay_geometry()
        self.scene.update()

    def source_notes(self) -> list[VocalNote]:
        return list(self._source_notes)

    def is_source_index_selected(self, index: int) -> bool:
        return index in self._selected_source_indices

    def set_edit_scope(self, edit_scope: str) -> None:
        self.edit_scope = edit_scope
        self._update_range_target_highlights()

    def set_selected_source_indices(self, indices: set[int]) -> None:
        self._selected_source_indices = set(indices)
        for index, item in enumerate(self._source_items):
            item.set_selected(index in self._selected_source_indices)
        self.scene.update()

    def set_playhead_time(self, seconds: float, emit: bool = False) -> None:
        self._playhead_time = max(0.0, min(float(seconds), max(self._duration, 0.0)))
        self._ensure_overlay_items()
        x = self.time_to_x(self._playhead_time)
        if self._playhead_item is not None:
            self._playhead_item.setLine(x, 0.0, x, self.scene_height)
        if emit:
            self.playhead_changed.emit(self._playhead_time)

    def playhead_time(self) -> float:
        return self._playhead_time

    def selection_range(self) -> tuple[float, float] | None:
        if self._selection_end <= self._selection_start:
            return None
        return self._selection_start, self._selection_end

    def time_in_selection_range(self, seconds: float) -> bool:
        selection = self.selection_range()
        if selection is None:
            return False
        start, end = selection
        return start <= seconds <= end

    def set_selection_range(self, start: float, end: float, emit: bool = True) -> None:
        start = max(0.0, min(float(start), max(self._duration, 0.0)))
        end = max(0.0, min(float(end), max(self._duration, 0.0)))
        if end < start:
            start, end = end, start
        self._selection_start = start
        self._selection_end = end
        self._update_selection_item()
        self._update_range_target_highlights()
        if emit:
            self.selection_changed.emit(start, end)

    def clear_selection_range(self, emit: bool = True) -> None:
        self._selection_start = 0.0
        self._selection_end = 0.0
        self._update_selection_item()
        self._update_range_target_highlights()
        if emit:
            self.selection_changed.emit(0.0, 0.0)

    def handle_key_press(self, key: int) -> bool:
        if key == Qt.Key_Space:
            self.play_requested.emit()
            return True
        if key == Qt.Key_S:
            self.split_requested.emit()
            return True
        if key == Qt.Key_M:
            self.merge_requested.emit()
            return True
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected_requested.emit()
            return True
        if key == Qt.Key_Up:
            self.keyboard_edit_requested.emit(0.0, 1)
            return True
        if key == Qt.Key_Down:
            self.keyboard_edit_requested.emit(0.0, -1)
            return True
        if key == Qt.Key_Left:
            self.keyboard_edit_requested.emit(-0.02, 0)
            return True
        if key == Qt.Key_Right:
            self.keyboard_edit_requested.emit(0.02, 0)
            return True
        return False

    def set_time_zoom(self, pixels_per_second: float) -> float:
        previous_playhead = self._playhead_time
        self.pixels_per_second = max(
            self.min_pixels_per_second,
            min(float(pixels_per_second), self.max_pixels_per_second),
        )
        self._update_scene_rect()
        self._draw_note_segments()
        self._update_overlay_geometry()
        self.set_playhead_time(previous_playhead)
        self.scene.update()
        return self.pixels_per_second / 120.0

    @property
    def scene_width(self) -> float:
        return self.keyboard_width + max(8.0, self._duration * self.pixels_per_second) + 48.0

    @property
    def scene_height(self) -> float:
        return max(1, self._midi_high - self._midi_low + 1) * self.note_height

    def time_to_x(self, seconds: float) -> float:
        return self.keyboard_width + max(0.0, min(seconds, max(self._duration, 0.0))) * self.pixels_per_second

    def x_to_time(self, x_value: float) -> float:
        seconds = (x_value - self.keyboard_width) / self.pixels_per_second
        return max(0.0, min(seconds, max(self._duration, 0.0)))

    def midi_to_y(self, midi_note: float) -> float:
        return (self._midi_high - midi_note + 0.5) * self.note_height

    def note_rect(self, note: VocalNote) -> QRectF:
        x = self.time_to_x(note.start)
        width = max(8.0, (note.end - note.start) * self.pixels_per_second)
        center = self.midi_to_y(note.midi_note)
        if note.track_type == "reference" or note.locked:
            height = self.note_height * 0.48
            y = center - self.note_height * 0.47
        else:
            height = self.note_height * 0.66
            y = center - self.note_height * 0.18
        return QRectF(x, y, width, height)

    def clamp_source_note_edit(
        self,
        index: int,
        start: float,
        end: float,
        midi_note: float,
        mode: str = "move",
    ) -> tuple[float, float, float]:
        midi_note = round(max(self._midi_low, min(midi_note, self._midi_high)))
        lower_bound = self._source_notes[index - 1].end if index > 0 else 0.0
        upper_bound = (
            self._source_notes[index + 1].start
            if index < len(self._source_notes) - 1
            else max(self._duration, end)
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
            targets = self.drag_target_indices(index)
            delta_time = start - self._source_notes[index].start
            if targets:
                earliest = min(self._source_notes[target].start for target in targets)
                lower_limit = -earliest
                selection = self.selection_range()
                if self.edit_scope == "range" and selection is not None:
                    lower_limit = max(lower_limit, -selection[0])
                delta_time = max(delta_time, lower_limit)
            duration = max(self.min_note_duration, self._source_notes[index].duration)
            start = self._source_notes[index].start + delta_time
            end = start + duration

        return round(start, 2), round(end, 2), midi_note

    def drag_target_indices(self, anchor_index: int) -> set[int]:
        if self.edit_scope == "all_source":
            return set(range(len(self._source_notes)))
        if self.edit_scope == "range":
            selection = self.selection_range()
            if selection is None or not 0 <= anchor_index < len(self._source_notes):
                return set()
            if not self._note_overlaps_range(self._source_notes[anchor_index], selection):
                return set()
            return self.range_source_indices()
        if anchor_index in self._selected_source_indices:
            return set(self._selected_source_indices)
        return {anchor_index}

    def range_source_indices(self) -> set[int]:
        selection = self.selection_range()
        if selection is None:
            return set()
        return {
            index
            for index, note in enumerate(self._source_notes)
            if self._note_overlaps_range(note, selection)
        }

    def preview_source_note_drag(
        self,
        anchor_index: int,
        start_notes: list[VocalNote],
        delta_time: float,
        delta_midi: int,
        mode: str,
        edited_anchor: VocalNote,
    ) -> None:
        if not start_notes or len(start_notes) != len(self._source_items):
            return

        if mode != "move":
            for index, item in enumerate(self._source_items):
                item.set_note(edited_anchor if index == anchor_index else start_notes[index])
            self.scene.update()
            return

        targets = self.drag_target_indices(anchor_index)
        if targets:
            earliest = min(start_notes[index].start for index in targets)
            lower_limit = -earliest
            selection = self.selection_range()
            if self.edit_scope == "range" and selection is not None:
                lower_limit = max(lower_limit, -selection[0])
            delta_time = max(delta_time, lower_limit)

        for index, item in enumerate(self._source_items):
            note = start_notes[index]
            if index in targets:
                note = (
                    note.with_range(note.start + delta_time, note.end + delta_time)
                    .with_pitch(note.midi_note + delta_midi)
                )
            item.set_note(note)
            item.set_selected(index in self._selected_source_indices or index in targets)
        self.scene.update()

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
        count = int(math.ceil(max(self._duration, 0.0) / step)) + 1
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
        values = [note.midi_note for note in self._reference_notes + self._source_notes]
        for note in self._reference_notes + self._source_notes:
            values.extend(point.midi for point in note.pitch_points if point.midi is not None)
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
            range_fill = QColor("#FFB86B")
            range_fill.setAlpha(46)
            range_border = QColor("#FFB86B")
            range_border.setAlpha(115)
            self._selection_item.setBrush(QBrush(range_fill))
            self._selection_item.setPen(QPen(range_border))
            self._selection_item.setZValue(2)
            self.scene.addItem(self._selection_item)

        if self._selection_start_item is None:
            self._selection_start_item = QGraphicsLineItem()
            self._selection_start_item.setAcceptedMouseButtons(Qt.NoButton)
            pen = QPen(QColor("#FFB86B"))
            pen.setWidthF(2.0)
            self._selection_start_item.setPen(pen)
            self._selection_start_item.setZValue(3)
            self.scene.addItem(self._selection_start_item)

        if self._selection_end_item is None:
            self._selection_end_item = QGraphicsLineItem()
            self._selection_end_item.setAcceptedMouseButtons(Qt.NoButton)
            pen = QPen(QColor("#FFB86B"))
            pen.setWidthF(2.0)
            self._selection_end_item.setPen(pen)
            self._selection_end_item.setZValue(3)
            self.scene.addItem(self._selection_end_item)

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
        self.set_playhead_time(self._playhead_time)

    def _update_selection_item(self) -> None:
        self._ensure_overlay_items()
        if (
            self._selection_item is None
            or self._selection_start_item is None
            or self._selection_end_item is None
        ):
            return
        has_range = self._selection_end > self._selection_start
        self._selection_item.setVisible(has_range)
        self._selection_start_item.setVisible(has_range)
        self._selection_end_item.setVisible(has_range)
        if not has_range:
            return
        x1 = self.time_to_x(self._selection_start)
        x2 = self.time_to_x(self._selection_end)
        self._selection_item.setRect(QRectF(x1, 0.0, max(1.0, x2 - x1), self.scene_height))
        self._selection_start_item.setLine(x1, 0.0, x1, self.scene_height)
        self._selection_end_item.setLine(x2, 0.0, x2, self.scene_height)

    def _draw_note_segments(self) -> None:
        for item in self._reference_items + self._source_items:
            self.scene.removeItem(item)
        self._reference_items = []
        self._source_items = []

        for index, note in enumerate(self._reference_notes):
            item = NoteBlockItem(note=note, index=index, selected=False, editor=self)
            self.scene.addItem(item)
            self._reference_items.append(item)

        for index, note in enumerate(self._source_notes):
            item = NoteBlockItem(
                note=note,
                index=index,
                selected=index in self._selected_source_indices,
                editor=self,
            )
            self.scene.addItem(item)
            self._source_items.append(item)
        self._update_range_target_highlights()

    def _update_range_target_highlights(self) -> None:
        targets = self.range_source_indices() if self.edit_scope == "range" else set()
        for index, item in enumerate(self._source_items):
            item.set_range_target(index in targets)

    def _note_overlaps_range(self, note: VocalNote, selection: tuple[float, float]) -> bool:
        start, end = selection
        return note.track_type == "source" and not note.locked and note.end > start and note.start < end
