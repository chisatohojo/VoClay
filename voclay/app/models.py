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
