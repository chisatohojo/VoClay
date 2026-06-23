from __future__ import annotations

from statistics import mean, median
from typing import Protocol

from voclay.app.models import PitchFrame, PitchPoint, VocalNote


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
    ) -> None:
        self.min_duration = min_duration
        self.max_gap = max_gap
        self.pitch_split_semitones = pitch_split_semitones
        self.abrupt_split_semitones = abrupt_split_semitones

    def segment(
        self,
        frames: list[PitchFrame] | list[PitchPoint],
        duration: float,
        track_type: str = "source",
        locked: bool = False,
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
            note = self._group_to_note(
                len(notes),
                group,
                frame_step,
                duration,
                split_reason,
                track_type,
                locked,
            )
            if note is not None:
                notes.append(note)

        return [note.with_id(index) for index, note in enumerate(notes)]

    def _group_to_note(
        self,
        note_id: int,
        group: list[PitchLike],
        frame_step: float,
        duration: float,
        split_reason: str,
        track_type: str,
        locked: bool,
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
            track_type=track_type,
            locked=locked,
        )

    def _points_to_note(
        self,
        note_id: int,
        start: float,
        end: float,
        points: list[PitchPoint],
        split_reason: str,
        track_type: str = "source",
        locked: bool = False,
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
            track_type=track_type,
            original_start_time=start,
            original_end_time=end,
            cents_offset=(original_midi_median - rounded_midi) * 100.0,
            original_midi_median=original_midi_median,
            pitch_points=tuple(points),
            split_reason=split_reason,
            locked=locked,
            confidence=confidence,
            voiced=True,
            average_f0=median(f0_values),
        )

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
