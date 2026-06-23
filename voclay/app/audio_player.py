from __future__ import annotations

import time

import numpy as np
import sounddevice as sd

from voclay.app.audio_document import AudioDocument


class AudioPlayer:
    def __init__(self) -> None:
        self._started_at: float | None = None
        self._duration = 0.0
        self._offset_seconds = 0.0
        self._is_playing = False

    def play(self, document: AudioDocument, start_time: float = 0.0) -> None:
        self.play_samples(document.current_samples, document.sample_rate, start_time)

    def play_samples(self, samples: np.ndarray, sample_rate: int, start_time: float = 0.0) -> None:
        self.stop()

        data = samples
        if data.ndim == 2 and data.shape[1] == 1:
            data = data[:, 0]
        data = np.asarray(data, dtype=np.float32)

        if sample_rate <= 0:
            raise ValueError("Audio sample rate must be positive.")

        self._duration = data.shape[0] / float(sample_rate)
        self._offset_seconds = max(0.0, min(start_time, self._duration))
        start_frame = max(0, min(int(round(self._offset_seconds * sample_rate)), data.shape[0]))
        playback_data = data[start_frame:]
        if playback_data.shape[0] == 0:
            raise ValueError("Playback start is beyond the end of the audio.")

        self._started_at = time.perf_counter()
        self._is_playing = True
        sd.play(playback_data, samplerate=sample_rate, blocking=False)

    def stop(self) -> float:
        position = self.get_position_seconds()
        if self._is_playing:
            sd.stop()
        self._is_playing = False
        self._started_at = None
        return position

    def get_position_seconds(self) -> float:
        if self._started_at is None:
            return self._offset_seconds
        elapsed = time.perf_counter() - self._started_at
        return max(0.0, min(self._offset_seconds + elapsed, self._duration))

    def is_playing(self) -> bool:
        if self._is_playing and self.get_position_seconds() >= self._duration:
            self._is_playing = False
        return self._is_playing
