from __future__ import annotations

from statistics import mean, median
from typing import Protocol

from voclay.app.models import ChordChange, PitchFrame, PitchPoint, VocalNote


class PitchLike(Protocol):
    time: float
    f0: float | None
    voiced: bool
    confidence: float | None


class NoteSegmenter:
    def __init__(
        self,
        min_duration: float = 0.08,
        max_gap: float = 0.08,
        pitch_split_semitones: float = 0.7,
        abrupt_split_semitones: float = 1.2,
        chord_split_min_side: float = 0.12,
    ) -> None:
        self.min_duration = min_duration
        self.max_gap = max_gap
        self.pitch_split_semitones = pitch_split_semitones
        self.abrupt_split_semitones = abrupt_split_semitones
        self.chord_split_min_side = chord_split_min_side

    def segment(
        self,
        frames: list[PitchFrame] | list[PitchPoint],
        duration: float,
        chord_changes: list[ChordChange] | None = None,
    ) -> list[VocalNote]:
        voiced_frames = [
            frame
            for frame in sorted(frames, key=lambda item: item.time)
            if frame.voiced and frame.f0 is not None and self._midi(frame) is not None
        ]
        if not voiced_frames:
            return []

        frame_step = self._estimate_frame_step(frames)
        groups: list[tuple[list[PitchLike], str]] = []
        current: list[PitchLike] = []
        current_reason = "initial"

        for frame in voiced_frames:
            if not current:
                current.append(frame)
                continue

            previous = current[-1]
            previous_midi = self._midi(previous)
            current_median = median(
                self._midi(item) for item in current if self._midi(item) is not None
            )
            midi_note = self._midi(frame)
            split_reason: str | None = None

            if frame.time - previous.time >= self.max_gap:
                split_reason = "silence"
            elif (
                midi_note is not None
                and previous_midi is not None
                and abs(midi_note - previous_midi) >= self.abrupt_split_semitones
            ):
                split_reason = "pitch_jump"
            elif midi_note is None or abs(midi_note - current_median) >= self.pitch_split_semitones:
                split_reason = "pitch_change"

            if split_reason is not None:
                groups.append((current, current_reason))
                current = [frame]
                current_reason = split_reason
            else:
                current.append(frame)

        if current:
            groups.append((current, current_reason))

        notes: list[VocalNote] = []
        for group, split_reason in groups:
            note = self._group_to_note(len(notes), group, frame_step, duration, split_reason)
            if note is not None:
                notes.append(note)

        notes = self._apply_chord_splits(notes, chord_changes or [])
        return [note.with_id(index) for index, note in enumerate(notes)]

    def _group_to_note(
        self,
        note_id: int,
        group: list[PitchLike],
        frame_step: float,
        duration: float,
        split_reason: str,
    ) -> VocalNote | None:
        start = max(0.0, group[0].time - frame_step * 0.5)
        end = min(duration, group[-1].time + frame_step * 0.5)
        if end - start < self.min_duration:
            return None

        return self._points_to_note(
            note_id=note_id,
            start=start,
            end=end,
            points=[
                self._to_pitch_point(frame)
                for frame in group
                if self._midi(frame) is not None and frame.f0 is not None
            ],
            split_reason=split_reason,
        )

    def _points_to_note(
        self,
        note_id: int,
        start: float,
        end: float,
        points: list[PitchPoint],
        split_reason: str,
    ) -> VocalNote | None:
        if end - start < self.min_duration:
            return None
        midi_values = [point.midi for point in points if point.midi is not None]
        f0_values = [point.f0 for point in points if point.f0 is not None]
        if not midi_values or not f0_values:
            return None

        confidence_values = [
            point.confidence
            for point in points
            if point.confidence is not None
        ]
        confidence = mean(confidence_values) if confidence_values else None
        original_midi_median = median(midi_values)
        rounded_midi = int(round(original_midi_median))

        return VocalNote(
            id=note_id,
            start_time=start,
            end_time=end,
            midi_note=rounded_midi,
            cents_offset=(original_midi_median - rounded_midi) * 100.0,
            original_midi_median=original_midi_median,
            pitch_points=tuple(points),
            split_reason=split_reason,
            confidence=confidence,
            voiced=True,
            average_f0=median(f0_values),
        )

    def _apply_chord_splits(
        self,
        notes: list[VocalNote],
        chord_changes: list[ChordChange],
    ) -> list[VocalNote]:
        if not notes or not chord_changes:
            return notes

        output: list[VocalNote] = []
        for note in notes:
            pending = [note]
            for change in chord_changes:
                next_pending: list[VocalNote] = []
                for item in pending:
                    if not item.start + self.chord_split_min_side <= change.time <= item.end - self.chord_split_min_side:
                        next_pending.append(item)
                        continue
                    before_points = [point for point in item.pitch_points if point.time <= change.time]
                    after_points = [point for point in item.pitch_points if point.time >= change.time]
                    before = self._points_to_note(
                        note_id=0,
                        start=item.start,
                        end=change.time,
                        points=before_points,
                        split_reason=item.split_reason,
                    )
                    after = self._points_to_note(
                        note_id=0,
                        start=change.time,
                        end=item.end,
                        points=after_points,
                        split_reason="chord_change",
                    )
                    if before is None or after is None:
                        next_pending.append(item)
                    else:
                        next_pending.extend([before, after])
                pending = next_pending
            output.extend(pending)
        return output

    def _to_pitch_point(self, frame: PitchLike) -> PitchPoint:
        return PitchPoint(
            time=frame.time,
            f0=frame.f0,
            midi=self._midi(frame),
            voiced=frame.voiced,
            confidence=frame.confidence,
        )

    def _midi(self, frame: PitchLike) -> float | None:
        if hasattr(frame, "midi"):
            return getattr(frame, "midi")
        return getattr(frame, "midi_note", None)

    def _estimate_frame_step(self, frames: list[PitchFrame] | list[PitchPoint]) -> float:
        times = [frame.time for frame in frames]
        if len(times) < 2:
            return 0.02

        diffs = [
            later - earlier
            for earlier, later in zip(times, times[1:])
            if later > earlier
        ]
        if not diffs:
            return 0.02
        return max(0.001, median(diffs))
