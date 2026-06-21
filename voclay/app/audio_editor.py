from __future__ import annotations

import math

import numpy as np

from voclay.app.audio_document import AudioDocument
from voclay.app.models import AudioEffectEdit, NoteSegment, PitchEdit, PitchFrame, TimeRange


class AudioEditor:
    @staticmethod
    def pitch_shift_range(
        document: AudioDocument,
        selection: TimeRange,
        semitones: float,
    ) -> tuple[np.ndarray, list[PitchFrame], PitchEdit]:
        import librosa

        normalized = selection.normalized(document.duration)

        source = np.asarray(document.current_samples, dtype=np.float32)
        edited = AudioEditor._pitch_shift_samples(
            source,
            document.sample_rate,
            normalized,
            semitones,
            librosa,
        )
        edit = PitchEdit(selection=normalized, semitones=semitones)
        frames = AudioEditor._shift_pitch_frames(document.pitch_frames, normalized, semitones)
        return edited, frames, edit

    @staticmethod
    def pitch_shift_edits(
        document: AudioDocument,
        edits: list[PitchEdit],
    ) -> tuple[np.ndarray, list[PitchFrame], list[PitchEdit]]:
        import librosa

        source = np.asarray(document.current_samples, dtype=np.float32)
        edited = source.copy()
        frames = list(document.pitch_frames)
        applied: list[PitchEdit] = []

        for edit in edits:
            normalized = edit.selection.normalized(document.duration)
            if normalized.duration <= 0:
                continue
            edited = AudioEditor._pitch_shift_samples(
                edited,
                document.sample_rate,
                normalized,
                edit.semitones,
                librosa,
            )
            frames = AudioEditor._shift_pitch_frames(frames, normalized, edit.semitones)
            applied.append(PitchEdit(selection=normalized, semitones=edit.semitones))

        if not applied:
            raise ValueError("No pitch edits were applied.")

        return edited, frames, applied

    @staticmethod
    def apply_vibrato_range(
        document: AudioDocument,
        selection: TimeRange,
        amount: float,
    ) -> tuple[np.ndarray, list[PitchFrame], AudioEffectEdit]:
        normalized = selection.normalized(document.duration)
        source = np.asarray(document.current_samples, dtype=np.float32)
        edited = source.copy()
        start_frame, end_frame = AudioEditor._frame_bounds(
            normalized,
            document.sample_rate,
            document.frame_count,
        )
        segment = source[start_frame:end_frame]
        if segment.shape[0] < 32:
            raise ValueError("The selected range is too short for vibrato editing.")

        if amount > 0:
            processed = AudioEditor._add_vibrato(segment, document.sample_rate, amount)
        else:
            processed = AudioEditor._soften_segment(segment, abs(amount))
        edited[start_frame:end_frame] = AudioEditor._edge_blend(
            segment,
            processed,
            document.sample_rate,
        )

        frames = AudioEditor._adjust_vibrato_frames(document.pitch_frames, normalized, amount)
        edit = AudioEffectEdit(
            kind="vibrato",
            selection=normalized,
            amount=amount,
            label=f"Vibrato {amount:+.1f}",
        )
        return edited, frames, edit

    @staticmethod
    def correct_transition(
        document: AudioDocument,
        note: NoteSegment,
        mode: str,
    ) -> tuple[np.ndarray, list[PitchFrame], list[PitchEdit]]:
        frames_in_note = [
            frame
            for frame in document.pitch_frames
            if note.start <= frame.time <= note.end and frame.midi_note is not None
        ]
        if not frames_in_note:
            raise ValueError("The selected note has no pitch data to correct.")

        target_midi = float(np.median([frame.midi_note for frame in frames_in_note if frame.midi_note is not None]))
        edge_duration = max(0.04, min(0.18, note.duration * 0.28))
        if mode == "scoop":
            selection = TimeRange(note.start, min(note.end, note.start + edge_duration))
        elif mode == "fall":
            selection = TimeRange(max(note.start, note.end - edge_duration), note.end)
        else:
            raise ValueError("Unknown transition correction mode.")

        edge_frames = [
            frame
            for frame in frames_in_note
            if selection.start <= frame.time <= selection.end and frame.midi_note is not None
        ]
        if not edge_frames:
            raise ValueError("The selected note edge has no pitch data to correct.")

        edge_midi = float(np.median([frame.midi_note for frame in edge_frames if frame.midi_note is not None]))
        semitones = target_midi - edge_midi
        if abs(semitones) < 0.05:
            raise ValueError("The selected note edge is already close to the note center.")

        edited, frames, edit = AudioEditor.pitch_shift_range(document, selection, semitones)
        return edited, frames, [edit]

    @staticmethod
    def formant_color_range(
        document: AudioDocument,
        selection: TimeRange,
        amount: float,
    ) -> tuple[np.ndarray, list[PitchFrame], AudioEffectEdit]:
        normalized = selection.normalized(document.duration)
        source = np.asarray(document.current_samples, dtype=np.float32)
        edited = source.copy()
        start_frame, end_frame = AudioEditor._frame_bounds(
            normalized,
            document.sample_rate,
            document.frame_count,
        )
        segment = source[start_frame:end_frame]
        if segment.shape[0] < 32:
            raise ValueError("The selected range is too short for formant color editing.")

        processed = AudioEditor._spectral_tilt(segment, amount)
        edited[start_frame:end_frame] = AudioEditor._edge_blend(
            segment,
            processed,
            document.sample_rate,
        )
        edit = AudioEffectEdit(
            kind="formant",
            selection=normalized,
            amount=amount,
            label=f"Formant color {amount:+.1f}",
        )
        return edited, list(document.pitch_frames), edit

    @staticmethod
    def _pitch_shift_samples(
        source: np.ndarray,
        sample_rate: int,
        selection: TimeRange,
        semitones: float,
        librosa,
    ) -> np.ndarray:
        edited = source.copy()
        start_frame, end_frame = AudioEditor._frame_bounds(selection, sample_rate, source.shape[0])
        segment = source[start_frame:end_frame]
        if segment.shape[0] < 32:
            raise ValueError("The selected range is too short to pitch shift.")

        shifted = AudioEditor._shift_segment(segment, sample_rate, semitones, librosa)
        edited[start_frame:end_frame] = AudioEditor._edge_blend(segment, shifted, sample_rate)
        return edited

    @staticmethod
    def _frame_bounds(selection: TimeRange, sample_rate: int, frame_count: int) -> tuple[int, int]:
        start_frame = int(round(selection.start * sample_rate))
        end_frame = int(round(selection.end * sample_rate))
        start_frame = max(0, min(start_frame, frame_count))
        end_frame = max(0, min(end_frame, frame_count))
        if end_frame <= start_frame:
            raise ValueError("Select a non-empty range before editing audio.")
        return start_frame, end_frame

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
    def _add_vibrato(segment: np.ndarray, sample_rate: int, amount: float) -> np.ndarray:
        depth_samples = max(1.0, sample_rate * 0.0025 * min(2.0, abs(amount)))
        rate = 5.5
        source = segment.astype(np.float32, copy=False)
        positions = np.arange(source.shape[0], dtype=np.float32)
        offsets = depth_samples * np.sin(2.0 * np.pi * rate * positions / sample_rate)
        warped = np.clip(positions + offsets, 0, source.shape[0] - 1)

        if source.ndim == 1:
            return np.interp(warped, positions, source).astype(np.float32)

        channels = [
            np.interp(warped, positions, source[:, channel_index])
            for channel_index in range(source.shape[1])
        ]
        return np.stack(channels, axis=1).astype(np.float32)

    @staticmethod
    def _soften_segment(segment: np.ndarray, amount: float) -> np.ndarray:
        source = segment.astype(np.float32, copy=False)
        strength = min(0.75, 0.35 * amount)
        kernel_size = 9
        kernel = np.ones(kernel_size, dtype=np.float32) / kernel_size

        if source.ndim == 1:
            smoothed = np.convolve(source, kernel, mode="same")
        else:
            smoothed = np.column_stack(
                [
                    np.convolve(source[:, channel_index], kernel, mode="same")
                    for channel_index in range(source.shape[1])
                ]
            )
        return (source * (1.0 - strength) + smoothed * strength).astype(np.float32)

    @staticmethod
    def _spectral_tilt(segment: np.ndarray, amount: float) -> np.ndarray:
        source = segment.astype(np.float32, copy=False)
        strength = float(np.clip(amount, -2.0, 2.0)) * 0.22

        def process_channel(values: np.ndarray) -> np.ndarray:
            spectrum = np.fft.rfft(values)
            if spectrum.shape[0] <= 1:
                return values
            freqs = np.linspace(0.0, 1.0, spectrum.shape[0], dtype=np.float32)
            curve = np.clip(1.0 + strength * (freqs - 0.35), 0.25, 2.0)
            output = np.fft.irfft(spectrum * curve, n=values.shape[0])
            peak = max(1.0e-6, float(np.max(np.abs(output))))
            source_peak = max(1.0e-6, float(np.max(np.abs(values))))
            if peak > source_peak:
                output *= source_peak / peak
            return output.astype(np.float32)

        if source.ndim == 1:
            return process_channel(source)
        return np.column_stack(
            [process_channel(source[:, channel_index]) for channel_index in range(source.shape[1])]
        ).astype(np.float32)

    @staticmethod
    def _adjust_vibrato_frames(
        frames: list[PitchFrame],
        selection: TimeRange,
        amount: float,
    ) -> list[PitchFrame]:
        frames_in_range = [
            frame
            for frame in frames
            if selection.start <= frame.time <= selection.end and frame.f0 is not None
        ]
        if not frames_in_range:
            return list(frames)

        median_f0 = float(np.median([frame.f0 for frame in frames_in_range if frame.f0 is not None]))
        adjusted: list[PitchFrame] = []
        for frame in frames:
            if (
                selection.start <= frame.time <= selection.end
                and frame.voiced
                and frame.f0 is not None
            ):
                if amount > 0:
                    cents = 28.0 * min(2.0, amount) * math.sin(2.0 * math.pi * 5.5 * (frame.time - selection.start))
                    factor = math.pow(2.0, cents / 1200.0)
                    f0 = frame.f0 * factor
                else:
                    strength = min(0.8, abs(amount) * 0.45)
                    f0 = frame.f0 * (1.0 - strength) + median_f0 * strength
                adjusted.append(
                    PitchFrame(
                        time=frame.time,
                        f0=f0,
                        voiced=frame.voiced,
                        confidence=frame.confidence,
                    )
                )
            else:
                adjusted.append(frame)
        return adjusted

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
