from __future__ import annotations

from dataclasses import dataclass
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
class NoteSegment:
    id: int
    start: float
    end: float
    midi_note: float
    average_f0: float
    confidence: float | None = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def note_name(self) -> str:
        names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        rounded = int(round(self.midi_note))
        octave = rounded // 12 - 1
        return f"{names[rounded % 12]}{octave}"

    def shifted(self, semitones: float) -> "NoteSegment":
        midi_note = self.midi_note + semitones
        average_f0 = self.average_f0 * pow(2.0, semitones / 12.0)
        return NoteSegment(
            id=self.id,
            start=self.start,
            end=self.end,
            midi_note=midi_note,
            average_f0=average_f0,
            confidence=self.confidence,
        )

    def with_range(self, start: float, end: float) -> "NoteSegment":
        return NoteSegment(
            id=self.id,
            start=start,
            end=end,
            midi_note=self.midi_note,
            average_f0=self.average_f0,
            confidence=self.confidence,
        )
