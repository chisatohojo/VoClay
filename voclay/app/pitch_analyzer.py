from __future__ import annotations

import math

import numpy as np

from voclay.app.audio_document import AudioDocument
from voclay.app.models import PitchFrame


class PitchAnalyzer:
    def __init__(self, hop_length: int = 256) -> None:
        self.hop_length = hop_length

    def analyze(self, document: AudioDocument) -> list[PitchFrame]:
        import librosa

        if document.analysis_frame_count == 0:
            return []

        sample_rate = document.analysis_sample_rate or document.sample_rate
        y = np.asarray(document.analysis_mono_samples, dtype=np.float32)
        fmin = librosa.note_to_hz("C2")
        fmax = librosa.note_to_hz("C7")

        f0, voiced_flag, voiced_prob = librosa.pyin(
            y,
            fmin=fmin,
            fmax=fmax,
            sr=sample_rate,
            hop_length=self.hop_length,
        )
        times = librosa.times_like(f0, sr=sample_rate, hop_length=self.hop_length)

        frames: list[PitchFrame] = []
        for time_value, f0_value, voiced, confidence in zip(times, f0, voiced_flag, voiced_prob):
            has_pitch = voiced and f0_value is not None and math.isfinite(float(f0_value))
            f0_out = float(f0_value) if has_pitch else None
            confidence_out = None
            if confidence is not None and math.isfinite(float(confidence)):
                confidence_out = float(confidence)

            frames.append(
                PitchFrame(
                    time=float(time_value),
                    f0=f0_out,
                    voiced=bool(has_pitch),
                    confidence=confidence_out,
                )
            )

        return frames
