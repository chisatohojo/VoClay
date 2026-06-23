from __future__ import annotations

from dataclasses import dataclass, field
from math import log2, pow


@dataclass(frozen=True)
class PitchFrame:
    time: float
    f0: float | None
    voiced: bool
    confidence: float | None = None

    @property
    def midi_note(self) -> float | None:
        if self.f0 is None or self.f0 <= 0:
            return None
        return 69.0 + 12.0 * log2(self.f0 / 440.0)


def hz_to_midi(f0: float | None) -> float | None:
    if f0 is None or f0 <= 0:
        return None
    return 69.0 + 12.0 * log2(f0 / 440.0)


@dataclass(frozen=True)
class TimeRange:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def start_time(self) -> float:
        return self.start

    @property
    def end_time(self) -> float:
        return self.end

    def normalized(self, maximum: float | None = None) -> "TimeRange":
        start = min(self.start, self.end)
        end = max(self.start, self.end)
        if maximum is not None:
            start = max(0.0, min(start, maximum))
            end = max(0.0, min(end, maximum))
        return TimeRange(start=start, end=end)


@dataclass(frozen=True)
class PitchEdit:
    selection: TimeRange
    semitones: float


@dataclass(frozen=True)
class AudioEffectEdit:
    kind: str
    selection: TimeRange
    amount: float
    label: str


@dataclass(frozen=True)
class PitchPoint:
    time: float
    f0: float | None
    midi: float | None
    voiced: bool
    confidence: float | None = None

    def shifted(self, semitones: float, factor: float | None = None) -> "PitchPoint":
        if factor is None:
            factor = pow(2.0, semitones / 12.0)
        return PitchPoint(
            time=self.time,
            f0=self.f0 * factor if self.f0 is not None else None,
            midi=self.midi + semitones if self.midi is not None else None,
            voiced=self.voiced,
            confidence=self.confidence,
        )

    def with_time(self, time: float) -> "PitchPoint":
        return PitchPoint(
            time=time,
            f0=self.f0,
            midi=self.midi,
            voiced=self.voiced,
            confidence=self.confidence,
        )


@dataclass(frozen=True)
class VocalNote:
    id: int
    start_time: float
    end_time: float
    midi_note: int
    track_type: str = "source"
    original_start_time: float | None = None
    original_end_time: float | None = None
    cents_offset: float = 0.0
    original_midi_median: float = 0.0
    pitch_points: tuple[PitchPoint, ...] = field(default_factory=tuple)
    split_reason: str = "pitch_change"
    selected: bool = False
    locked: bool = False
    confidence: float | None = None
    voiced: bool = True
    average_f0: float = 0.0

    def __post_init__(self) -> None:
        if self.original_start_time is None:
            object.__setattr__(self, "original_start_time", self.start_time)
        if self.original_end_time is None:
            object.__setattr__(self, "original_end_time", self.end_time)

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    @property
    def start(self) -> float:
        return self.start_time

    @property
    def end(self) -> float:
        return self.end_time

    @property
    def original_start(self) -> float:
        return float(self.original_start_time if self.original_start_time is not None else self.start_time)

    @property
    def original_end(self) -> float:
        return float(self.original_end_time if self.original_end_time is not None else self.end_time)

    @property
    def pitch_shift_semitones(self) -> float:
        return float(self.midi_note - self.original_midi_median)

    @property
    def note_name(self) -> str:
        names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        rounded = int(round(self.midi_note))
        octave = rounded // 12 - 1
        return f"{names[rounded % 12]}{octave}"

    def shifted(self, semitones: float) -> "VocalNote":
        return self.with_pitch(self.midi_note + semitones)

    def with_id(self, note_id: int) -> "VocalNote":
        return VocalNote(
            id=note_id,
            start_time=self.start_time,
            end_time=self.end_time,
            midi_note=self.midi_note,
            track_type=self.track_type,
            original_start_time=self.original_start,
            original_end_time=self.original_end,
            cents_offset=self.cents_offset,
            original_midi_median=self.original_midi_median,
            pitch_points=self.pitch_points,
            split_reason=self.split_reason,
            selected=self.selected,
            locked=self.locked,
            confidence=self.confidence,
            voiced=self.voiced,
            average_f0=self.average_f0,
        )

    def with_pitch(self, midi_note: float) -> "VocalNote":
        midi_note = int(round(midi_note))
        average_f0 = 440.0 * pow(2.0, (midi_note - 69.0) / 12.0)
        return VocalNote(
            id=self.id,
            start_time=self.start_time,
            end_time=self.end_time,
            midi_note=midi_note,
            track_type=self.track_type,
            original_start_time=self.original_start,
            original_end_time=self.original_end,
            cents_offset=(self.original_midi_median - midi_note) * 100.0,
            original_midi_median=self.original_midi_median,
            pitch_points=self.pitch_points,
            split_reason=self.split_reason,
            selected=self.selected,
            locked=self.locked,
            confidence=self.confidence,
            voiced=self.voiced,
            average_f0=average_f0,
        )

    def with_range(self, start: float, end: float) -> "VocalNote":
        return VocalNote(
            id=self.id,
            start_time=start,
            end_time=end,
            midi_note=self.midi_note,
            track_type=self.track_type,
            original_start_time=self.original_start,
            original_end_time=self.original_end,
            cents_offset=self.cents_offset,
            original_midi_median=self.original_midi_median,
            pitch_points=self.pitch_points,
            split_reason=self.split_reason,
            selected=self.selected,
            locked=self.locked,
            confidence=self.confidence,
            voiced=self.voiced,
            average_f0=self.average_f0,
        )

    def with_original_range(
        self,
        original_start: float,
        original_end: float,
        pitch_points: tuple[PitchPoint, ...] | None = None,
        split_reason: str | None = None,
    ) -> "VocalNote":
        return VocalNote(
            id=self.id,
            start_time=self.start_time,
            end_time=self.end_time,
            midi_note=self.midi_note,
            track_type=self.track_type,
            original_start_time=original_start,
            original_end_time=original_end,
            cents_offset=self.cents_offset,
            original_midi_median=self.original_midi_median,
            pitch_points=self.pitch_points if pitch_points is None else pitch_points,
            split_reason=self.split_reason if split_reason is None else split_reason,
            selected=self.selected,
            locked=self.locked,
            confidence=self.confidence,
            voiced=self.voiced,
            average_f0=self.average_f0,
        )

    def with_track(self, track_type: str, locked: bool) -> "VocalNote":
        return VocalNote(
            id=self.id,
            start_time=self.start_time,
            end_time=self.end_time,
            midi_note=self.midi_note,
            track_type=track_type,
            original_start_time=self.original_start,
            original_end_time=self.original_end,
            cents_offset=self.cents_offset,
            original_midi_median=self.original_midi_median,
            pitch_points=self.pitch_points,
            split_reason=self.split_reason,
            selected=self.selected,
            locked=locked,
            confidence=self.confidence,
            voiced=self.voiced,
            average_f0=self.average_f0,
        )

    def with_split_reason(self, split_reason: str) -> "VocalNote":
        return VocalNote(
            id=self.id,
            start_time=self.start_time,
            end_time=self.end_time,
            midi_note=self.midi_note,
            track_type=self.track_type,
            original_start_time=self.original_start,
            original_end_time=self.original_end,
            cents_offset=self.cents_offset,
            original_midi_median=self.original_midi_median,
            pitch_points=self.pitch_points,
            split_reason=split_reason,
            selected=self.selected,
            locked=self.locked,
            confidence=self.confidence,
            voiced=self.voiced,
            average_f0=self.average_f0,
        )

    def with_selected(self, selected: bool) -> "VocalNote":
        return VocalNote(
            id=self.id,
            start_time=self.start_time,
            end_time=self.end_time,
            midi_note=self.midi_note,
            track_type=self.track_type,
            original_start_time=self.original_start,
            original_end_time=self.original_end,
            cents_offset=self.cents_offset,
            original_midi_median=self.original_midi_median,
            pitch_points=self.pitch_points,
            split_reason=self.split_reason,
            selected=selected,
            locked=self.locked,
            confidence=self.confidence,
            voiced=self.voiced,
            average_f0=self.average_f0,
        )

NoteSegment = VocalNote
