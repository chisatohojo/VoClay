from __future__ import annotations

import math

import numpy as np

from voclay.app.audio_document import AudioDocument
from voclay.app.models import PitchEdit, PitchFrame, TimeRange


class AudioEditor:
    @staticmethod
    def pitch_shift_range(
        document: AudioDocument,
        selection: TimeRange,
        semitones: float,
    ) -> tuple[np.ndarray, list[PitchFrame], PitchEdit]:
        import librosa

        normalized = selection.normalized(document.duration)
        start_frame = int(round(normalized.start * document.sample_rate))
        end_frame = int(round(normalized.end * document.sample_rate))
        start_frame = max(0, min(start_frame, document.frame_count))
        end_frame = max(0, min(end_frame, document.frame_count))

        if end_frame <= start_frame:
            raise ValueError("Select a non-empty range before shifting pitch.")

        source = np.asarray(document.current_samples, dtype=np.float32)
        edited = source.copy()
        segment = source[start_frame:end_frame]
        if segment.shape[0] < 32:
            raise ValueError("The selected range is too short to pitch shift.")

        shifted = AudioEditor._shift_segment(segment, document.sample_rate, semitones, librosa)
        edited[start_frame:end_frame] = AudioEditor._edge_blend(segment, shifted, document.sample_rate)

        edit = PitchEdit(selection=normalized, semitones=semitones)
        frames = AudioEditor._shift_pitch_frames(document.pitch_frames, normalized, semitones)
        return edited, frames, edit

    @staticmethod
    def _shift_segment(segment: np.ndarray, sample_rate: int, semitones: float, librosa) -> np.ndarray:
        if segment.ndim == 1:
            shifted = librosa.effects.pitch_shift(
                y=segment.astype(np.float32, copy=False),
                sr=sample_rate,
                n_steps=semitones,
            )
            return AudioEditor._fit_length(shifted, segment.shape[0]).astype(np.float32, copy=False)

        channels: list[np.ndarray] = []
        for channel_index in range(segment.shape[1]):
            shifted_channel = librosa.effects.pitch_shift(
                y=segment[:, channel_index].astype(np.float32, copy=False),
                sr=sample_rate,
                n_steps=semitones,
            )
            channels.append(AudioEditor._fit_length(shifted_channel, segment.shape[0]))
        return np.stack(channels, axis=1).astype(np.float32, copy=False)

    @staticmethod
    def _fit_length(values: np.ndarray, length: int) -> np.ndarray:
        if values.shape[0] == length:
            return values
        if values.shape[0] > length:
            return values[:length]

        pad_width = length - values.shape[0]
        return np.pad(values, (0, pad_width), mode="constant")

    @staticmethod
    def _edge_blend(original: np.ndarray, shifted: np.ndarray, sample_rate: int) -> np.ndarray:
        output = shifted.copy()
        fade_length = min(int(sample_rate * 0.005), output.shape[0] // 2)
        if fade_length <= 1:
            return output

        fade_in = np.linspace(0.0, 1.0, fade_length, dtype=np.float32)
        fade_out = fade_in[::-1]
        if output.ndim == 2:
            fade_in = fade_in[:, None]
            fade_out = fade_out[:, None]

        output[:fade_length] = original[:fade_length] * (1.0 - fade_in) + output[:fade_length] * fade_in
        output[-fade_length:] = original[-fade_length:] * (1.0 - fade_out) + output[-fade_length:] * fade_out
        return output

    @staticmethod
    def _shift_pitch_frames(
        frames: list[PitchFrame],
        selection: TimeRange,
        semitones: float,
    ) -> list[PitchFrame]:
        if not frames:
            return []

        factor = math.pow(2.0, semitones / 12.0)
        shifted_frames: list[PitchFrame] = []
        for frame in frames:
            if (
                selection.start <= frame.time <= selection.end
                and frame.voiced
                and frame.f0 is not None
            ):
                shifted_frames.append(
                    PitchFrame(
                        time=frame.time,
                        f0=frame.f0 * factor,
                        voiced=frame.voiced,
                        confidence=frame.confidence,
                    )
                )
            else:
                shifted_frames.append(frame)
        return shifted_frames
