from __future__ import annotations

import time

import numpy as np
import sounddevice as sd

from voclay.app.audio_document import AudioDocument


class AudioPlayer:
    def __init__(self) -> None:
        self._started_at: float | None = None
        self._duration = 0.0
        self._is_playing = False

    def play(self, document: AudioDocument) -> None:
        self.stop()

        data = document.samples
        if data.ndim == 2 and data.shape[1] == 1:
            data = data[:, 0]
        data = np.asarray(data, dtype=np.float32)

        self._duration = document.duration
        self._started_at = time.perf_counter()
        self._is_playing = True
        sd.play(data, samplerate=document.sample_rate, blocking=False)

    def stop(self) -> float:
        position = self.get_position_seconds()
        if self._is_playing:
            sd.stop()
        self._is_playing = False
        self._started_at = None
        return position

    def get_position_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        elapsed = time.perf_counter() - self._started_at
        return max(0.0, min(elapsed, self._duration))

    def is_playing(self) -> bool:
        if self._is_playing and self.get_position_seconds() >= self._duration:
            self._is_playing = False
        return self._is_playing
