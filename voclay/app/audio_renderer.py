from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

import numpy as np
import soundfile as sf

from voclay.app.audio_document import AudioDocument
from voclay.app.models import VocalNote


@dataclass(frozen=True)
class RenderResult:
    samples: np.ndarray
    sample_rate: int
    duration: float
    temp_path: str | None
    success: bool
    message: str


class AudioRenderer:
    def render_preview(
        self,
        source_document: AudioDocument,
        source_notes: list[VocalNote],
        sample_rate: int | None = None,
    ) -> RenderResult:
        if not source_notes:
            return RenderResult(
                samples=np.zeros((0, source_document.channels), dtype=np.float32),
                sample_rate=source_document.sample_rate,
                duration=0.0,
                temp_path=None,
                success=False,
                message="No Source Notes to render.",
            )

        import librosa

        target_rate = sample_rate or source_document.sample_rate
        source_samples = np.asarray(source_document.samples, dtype=np.float32)
        if target_rate != source_document.sample_rate:
            source_samples = self._resample(source_samples, source_document.sample_rate, target_rate, librosa)

        channels = 1 if source_samples.ndim == 1 else source_samples.shape[1]
        output_frames = max(
            int(round(max(note.end for note in source_notes) * target_rate)),
            int(round(source_document.duration * target_rate)),
            1,
        )
        output = np.zeros((output_frames, channels), dtype=np.float32)
        weight = np.zeros((output_frames, channels), dtype=np.float32)

        rendered_count = 0
        for note in sorted(source_notes, key=lambda item: item.start):
            segment = self._source_segment(source_samples, target_rate, note)
            if segment.shape[0] < 16 or note.duration <= 0.0:
                continue

            processed = self._process_note_segment(segment, target_rate, note, librosa)
            start_frame = max(0, int(round(note.start * target_rate)))
            target_length = max(1, int(round(note.duration * target_rate)))
            processed = self._fit_length(processed, target_length)
            if processed.ndim == 1:
                processed = processed[:, None]

            end_frame = min(output.shape[0], start_frame + processed.shape[0])
            if end_frame <= start_frame:
                continue

            chunk = processed[: end_frame - start_frame]
            fade = self._fade_envelope(chunk.shape[0], target_rate)
            if chunk.ndim == 2:
                fade = fade[:, None]
            output[start_frame:end_frame] += chunk * fade
            weight[start_frame:end_frame] += fade
            rendered_count += 1

        active = weight > 1.0e-6
        output[active] = output[active] / weight[active]
        output = np.clip(output, -1.0, 1.0).astype(np.float32, copy=False)

        if source_document.channels == 1 and output.ndim == 2:
            write_samples: np.ndarray = output[:, 0]
        else:
            write_samples = output

        temp_path = str(Path(tempfile.gettempdir()) / "voclay_rendered_preview.wav")
        sf.write(temp_path, write_samples, target_rate)
        duration = output.shape[0] / float(target_rate)
        return RenderResult(
            samples=write_samples,
            sample_rate=target_rate,
            duration=duration,
            temp_path=temp_path,
            success=rendered_count > 0,
            message=f"Rendered {rendered_count} Source Note(s).",
        )

    def _source_segment(self, samples: np.ndarray, sample_rate: int, note: VocalNote) -> np.ndarray:
        start = max(0, int(round(note.original_start * sample_rate)))
        end = max(start + 1, int(round(note.original_end * sample_rate)))
        end = min(end, samples.shape[0])
        return samples[start:end].astype(np.float32, copy=False)

    def _process_note_segment(self, segment: np.ndarray, sample_rate: int, note: VocalNote, librosa) -> np.ndarray:
        semitones = note.pitch_shift_semitones
        shifted = self._pitch_shift(segment, sample_rate, semitones, librosa)

        original_duration = max(1.0e-4, note.original_end - note.original_start)
        target_duration = max(1.0e-4, note.duration)
        rate = original_duration / target_duration
        if abs(rate - 1.0) < 0.01:
            return shifted
        return self._time_stretch(shifted, rate, librosa)

    def _pitch_shift(self, segment: np.ndarray, sample_rate: int, semitones: float, librosa) -> np.ndarray:
        if abs(semitones) < 0.01:
            return segment.copy()
        if segment.ndim == 1:
            return librosa.effects.pitch_shift(
                y=segment.astype(np.float32, copy=False),
                sr=sample_rate,
                n_steps=semitones,
            ).astype(np.float32, copy=False)
        return np.column_stack(
            [
                librosa.effects.pitch_shift(
                    y=segment[:, channel].astype(np.float32, copy=False),
                    sr=sample_rate,
                    n_steps=semitones,
                )
                for channel in range(segment.shape[1])
            ]
        ).astype(np.float32, copy=False)

    def _time_stretch(self, segment: np.ndarray, rate: float, librosa) -> np.ndarray:
        if segment.ndim == 1:
            return librosa.effects.time_stretch(
                y=segment.astype(np.float32, copy=False),
                rate=rate,
            ).astype(np.float32, copy=False)
        return np.column_stack(
            [
                librosa.effects.time_stretch(
                    y=segment[:, channel].astype(np.float32, copy=False),
                    rate=rate,
                )
                for channel in range(segment.shape[1])
            ]
        ).astype(np.float32, copy=False)

    def _resample(self, samples: np.ndarray, original_rate: int, target_rate: int, librosa) -> np.ndarray:
        if samples.ndim == 1:
            return librosa.resample(samples, orig_sr=original_rate, target_sr=target_rate).astype(np.float32)
        return np.column_stack(
            [
                librosa.resample(samples[:, channel], orig_sr=original_rate, target_sr=target_rate)
                for channel in range(samples.shape[1])
            ]
        ).astype(np.float32)

    def _fit_length(self, samples: np.ndarray, length: int) -> np.ndarray:
        if samples.shape[0] == length:
            return samples.astype(np.float32, copy=False)
        if samples.shape[0] > length:
            return samples[:length].astype(np.float32, copy=False)

        pad_shape = [(0, length - samples.shape[0])]
        if samples.ndim == 2:
            pad_shape.append((0, 0))
        return np.pad(samples, pad_shape, mode="constant").astype(np.float32, copy=False)

    def _fade_envelope(self, length: int, sample_rate: int) -> np.ndarray:
        envelope = np.ones(length, dtype=np.float32)
        fade_length = min(int(sample_rate * 0.006), length // 2)
        if fade_length <= 1:
            return envelope
        fade = np.linspace(0.0, 1.0, fade_length, dtype=np.float32)
        envelope[:fade_length] = fade
        envelope[-fade_length:] = fade[::-1]
        return envelope
