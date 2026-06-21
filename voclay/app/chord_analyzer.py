from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import mean

import numpy as np

from voclay.app.models import ChordChange, ChordFrame


@dataclass(frozen=True)
class ChordAnalysisResult:
    frames: list[ChordFrame]
    changes: list[ChordChange]
    success: bool
    message: str


class ChordAnalyzer:
    def __init__(
        self,
        hop_length: int = 2048,
        min_segment_duration: float = 0.30,
    ) -> None:
        self.hop_length = hop_length
        self.min_segment_duration = min_segment_duration

    def analyze(self, file_path: str | Path) -> ChordAnalysisResult:
        import librosa

        path = Path(file_path)
        if not path.exists():
            return ChordAnalysisResult([], [], False, f"Chord source not found: {path}")

        try:
            y, sample_rate = librosa.load(str(path), sr=None, mono=True)
            if y.size < sample_rate * 0.2:
                return ChordAnalysisResult([], [], False, "Chord source is too short.")

            chroma = librosa.feature.chroma_stft(
                y=y,
                sr=sample_rate,
                hop_length=self.hop_length,
            )
            times = librosa.times_like(chroma[0], sr=sample_rate, hop_length=self.hop_length)
        except Exception as exc:  # noqa: BLE001
            return ChordAnalysisResult([], [], False, f"Chord analysis failed: {exc}")

        if chroma.size == 0:
            return ChordAnalysisResult([], [], False, "Chord analysis produced no chroma frames.")

        frames = [
            self._estimate_frame(float(time), chroma[:, index])
            for index, time in enumerate(times)
        ]
        changes = self._changes_from_frames(frames)
        return ChordAnalysisResult(
            frames=frames,
            changes=changes,
            success=True,
            message=f"{len(changes)} chord change(s)",
        )

    def _estimate_frame(self, time_value: float, chroma: np.ndarray) -> ChordFrame:
        chroma = np.asarray(chroma, dtype=float)
        norm = np.linalg.norm(chroma)
        if norm <= 1.0e-9:
            return ChordFrame(time=time_value, chord_label="N", confidence=0.0)

        chroma = chroma / norm
        labels, templates = self._templates()
        scores = templates @ chroma
        best_index = int(np.argmax(scores))
        best_score = float(scores[best_index])
        return ChordFrame(
            time=time_value,
            chord_label=labels[best_index],
            confidence=max(0.0, min(1.0, best_score / 2.0)),
        )

    def _changes_from_frames(self, frames: list[ChordFrame]) -> list[ChordChange]:
        if not frames:
            return []

        segments: list[tuple[str, float, float, list[float]]] = []
        current_label = frames[0].chord_label
        start = frames[0].time
        confidences = [
            frames[0].confidence
            if frames[0].confidence is not None
            else 0.0
        ]

        for previous, frame in zip(frames, frames[1:]):
            if frame.chord_label == current_label:
                if frame.confidence is not None:
                    confidences.append(frame.confidence)
                continue
            segments.append((current_label, start, previous.time, confidences))
            current_label = frame.chord_label
            start = frame.time
            confidences = [frame.confidence if frame.confidence is not None else 0.0]

        segments.append((current_label, start, frames[-1].time, confidences))
        stable_segments = [
            segment
            for segment in segments
            if segment[2] - segment[1] >= self.min_segment_duration
        ]
        if len(stable_segments) < 2:
            return []

        changes: list[ChordChange] = []
        for previous, current in zip(stable_segments, stable_segments[1:]):
            changes.append(
                ChordChange(
                    time=current[1],
                    prev_chord=previous[0],
                    next_chord=current[0],
                    confidence=mean(current[3]) if current[3] else None,
                )
            )
        return changes

    def _templates(self) -> tuple[list[str], np.ndarray]:
        names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        labels: list[str] = []
        templates: list[np.ndarray] = []
        for root, name in enumerate(names):
            major = np.zeros(12, dtype=float)
            major[[root, (root + 4) % 12, (root + 7) % 12]] = 1.0
            minor = np.zeros(12, dtype=float)
            minor[[root, (root + 3) % 12, (root + 7) % 12]] = 1.0
            labels.extend([name, f"{name}m"])
            templates.extend([major / np.linalg.norm(major), minor / np.linalg.norm(minor)])
        return labels, np.vstack(templates)
