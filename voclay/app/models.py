from __future__ import annotations

from dataclasses import dataclass
from math import log2


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
