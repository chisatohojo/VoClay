from __future__ import annotations

from statistics import mean, median

from voclay.app.models import PitchFrame, PitchPoint, VocalNote


class NoteSegmenter:
    def __init__(
        self,
        min_duration: float = 0.08,
        max_gap: float = 0.08,
        pitch_split_semitones: float = 0.7,
    ) -> None:
        self.min_duration = min_duration
        self.max_gap = max_gap
        self.pitch_split_semitones = pitch_split_semitones

    def segment(self, frames: list[PitchFrame], duration: float) -> list[VocalNote]:
        voiced_frames = [
            frame
            for frame in frames
            if frame.voiced and frame.f0 is not None and frame.midi_note is not None
        ]
        if not voiced_frames:
            return []

        frame_step = self._estimate_frame_step(frames)
        groups: list[list[PitchFrame]] = []
        current: list[PitchFrame] = []

        for frame in voiced_frames:
            if not current:
                current.append(frame)
                continue

            previous = current[-1]
            current_median = median(
                item.midi_note for item in current if item.midi_note is not None
            )
            midi_note = frame.midi_note
            should_split = (
                frame.time - previous.time > self.max_gap
                or midi_note is None
                or abs(midi_note - current_median) > self.pitch_split_semitones
            )

            if should_split:
                groups.append(current)
                current = [frame]
            else:
                current.append(frame)

        if current:
            groups.append(current)

        notes: list[VocalNote] = []
        for group in groups:
            note = self._group_to_note(len(notes), group, frame_step, duration)
            if note is not None:
                notes.append(note)

        return notes

    def _group_to_note(
        self,
        note_id: int,
        group: list[PitchFrame],
        frame_step: float,
        duration: float,
    ) -> VocalNote | None:
        start = max(0.0, group[0].time - frame_step * 0.5)
        end = min(duration, group[-1].time + frame_step * 0.5)
        if end - start < self.min_duration:
            return None

        midi_values = [frame.midi_note for frame in group if frame.midi_note is not None]
        f0_values = [frame.f0 for frame in group if frame.f0 is not None]
        if not midi_values or not f0_values:
            return None

        confidence_values = [
            frame.confidence
            for frame in group
            if frame.confidence is not None
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
            pitch_points=tuple(
                PitchPoint(
                    time=frame.time,
                    f0=frame.f0,
                    midi=frame.midi_note,
                    voiced=frame.voiced,
                )
                for frame in group
                if frame.f0 is not None and frame.midi_note is not None
            ),
            confidence=confidence,
            voiced=True,
            average_f0=median(f0_values),
        )

    def _estimate_frame_step(self, frames: list[PitchFrame]) -> float:
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
