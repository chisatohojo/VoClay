from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from voclay.app.models import AudioEffectEdit, PitchEdit, PitchFrame, PitchPoint, VocalNote


AudioEdit = PitchEdit | AudioEffectEdit


@dataclass
class AudioDocument:
    file_path: Path
    sample_rate: int
    samples: np.ndarray
    mono_samples: np.ndarray
    channels: int
    source_file_path: Path | None = None
    analysis_audio_path: Path | None = None
    input_mode: str = "Source"
    vocal_stem_path: Path | None = None
    accompaniment_stem_path: Path | None = None
    analysis_samples: np.ndarray | None = None
    analysis_mono_samples_data: np.ndarray | None = None
    analysis_sample_rate: int | None = None
    pitch_frames: list[PitchFrame] = field(default_factory=list)
    vocal_notes: list[VocalNote] = field(default_factory=list)
    edited_samples: np.ndarray | None = None
    edit_history: list[AudioEdit] = field(default_factory=list)

    @classmethod
    def load(cls, file_path: str | Path) -> "AudioDocument":
        path = Path(file_path)
        if path.suffix.lower() != ".wav":
            raise ValueError("VoClay currently supports WAV files only.")

        samples, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
        if samples.size == 0 or samples.shape[0] == 0:
            raise ValueError("The selected WAV file contains no audio samples.")

        channels = int(samples.shape[1])
        mono_samples = samples.mean(axis=1).astype(np.float32, copy=False)

        return cls(
            file_path=path,
            sample_rate=int(sample_rate),
            samples=samples.astype(np.float32, copy=False),
            mono_samples=mono_samples,
            channels=channels,
            source_file_path=path,
            analysis_audio_path=path,
            analysis_samples=samples.astype(np.float32, copy=False),
            analysis_mono_samples_data=mono_samples,
            analysis_sample_rate=int(sample_rate),
        )

    @property
    def file_name(self) -> str:
        return self.file_path.name

    @property
    def frame_count(self) -> int:
        return int(self.mono_samples.shape[0])

    @property
    def analysis_frame_count(self) -> int:
        return int(self.analysis_mono_samples.shape[0])

    @property
    def duration(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return self.frame_count / float(self.sample_rate)

    @property
    def analysis_duration(self) -> float:
        sample_rate = self.analysis_sample_rate or self.sample_rate
        if sample_rate <= 0:
            return 0.0
        return self.analysis_frame_count / float(sample_rate)

    @property
    def current_samples(self) -> np.ndarray:
        if self.edited_samples is not None:
            return self.edited_samples
        return self.samples

    @property
    def current_mono_samples(self) -> np.ndarray:
        samples = self.current_samples
        if samples.ndim == 1:
            return samples.astype(np.float32, copy=False)
        return samples.mean(axis=1).astype(np.float32, copy=False)

    @property
    def analysis_mono_samples(self) -> np.ndarray:
        if self.analysis_mono_samples_data is not None:
            return self.analysis_mono_samples_data.astype(np.float32, copy=False)
        return self.current_mono_samples

    @property
    def has_edits(self) -> bool:
        return bool(self.edit_history)

    @property
    def edit_count(self) -> int:
        return len(self.edit_history)

    @property
    def note_segments(self) -> list[VocalNote]:
        return self.vocal_notes

    @note_segments.setter
    def note_segments(self, notes: list[VocalNote]) -> None:
        self.vocal_notes = notes

    @property
    def pitch_points(self) -> list[PitchPoint]:
        return [
            PitchPoint(
                time=frame.time,
                f0=frame.f0,
                midi=frame.midi_note,
                voiced=frame.voiced,
                confidence=frame.confidence,
            )
            for frame in self.pitch_frames
        ]

    def set_input_mode(self, input_mode: str) -> None:
        self.input_mode = input_mode

    def set_analysis_audio(self, file_path: str | Path) -> None:
        path = Path(file_path)
        samples, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
        if samples.size == 0 or samples.shape[0] == 0:
            raise ValueError("The analysis audio contains no samples.")

        self.analysis_audio_path = path
        self.analysis_samples = samples.astype(np.float32, copy=False)
        self.analysis_mono_samples_data = self.analysis_samples.mean(axis=1).astype(np.float32, copy=False)
        self.analysis_sample_rate = int(sample_rate)

    def use_source_for_analysis(self) -> None:
        self.analysis_audio_path = self.source_file_path or self.file_path
        self.analysis_samples = self.samples
        self.analysis_mono_samples_data = self.mono_samples
        self.analysis_sample_rate = self.sample_rate

    def set_vocal_stems(
        self,
        vocal_path: str | Path | None,
        accompaniment_path: str | Path | None = None,
    ) -> None:
        self.vocal_stem_path = Path(vocal_path) if vocal_path else None
        self.accompaniment_stem_path = Path(accompaniment_path) if accompaniment_path else None

    def apply_pitch_edit(
        self,
        edited_samples: np.ndarray,
        pitch_frames: list[PitchFrame],
        edit: PitchEdit,
    ) -> None:
        self.apply_audio_edits(edited_samples, pitch_frames, [edit])

    def apply_audio_edits(
        self,
        edited_samples: np.ndarray,
        pitch_frames: list[PitchFrame],
        edits: list[AudioEdit],
    ) -> None:
        self.edited_samples = edited_samples.astype(np.float32, copy=False)
        self.mono_samples = self.current_mono_samples
        self.pitch_frames = pitch_frames
        self.edit_history.extend(edits)

    def export_wav(self, file_path: str | Path) -> None:
        sf.write(str(file_path), self.current_samples, self.sample_rate)
