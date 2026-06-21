from __future__ import annotations


KEYS = {
    "C": 0,
    "C#": 1,
    "D": 2,
    "D#": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "G": 7,
    "G#": 8,
    "A": 9,
    "A#": 10,
    "B": 11,
}

SCALES = {
    "Chromatic": tuple(range(12)),
    "Major": (0, 2, 4, 5, 7, 9, 11),
    "Natural Minor": (0, 2, 3, 5, 7, 8, 10),
    "Major Pentatonic": (0, 2, 4, 7, 9),
    "Minor Pentatonic": (0, 3, 5, 7, 10),
}


def nearest_scale_delta(midi_note: float, key_name: str, scale_name: str) -> float:
    root = KEYS.get(key_name, 0)
    intervals = SCALES.get(scale_name, SCALES["Chromatic"])
    target_pitch_classes = [((root + interval) % 12) for interval in intervals]

    base_octave = int(round(midi_note)) // 12
    candidates: list[int] = []
    for octave in range(base_octave - 1, base_octave + 2):
        for pitch_class in target_pitch_classes:
            candidates.append(octave * 12 + pitch_class)

    target = min(candidates, key=lambda candidate: abs(candidate - midi_note))
    return float(target - midi_note)
