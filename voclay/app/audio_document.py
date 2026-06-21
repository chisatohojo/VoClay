from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from voclay.app.models import PitchEdit, PitchFrame


@dataclass
class AudioDocument:
    file_path: Path
    sample_rate: int
    samples: np.ndarray
    mono_samples: np.ndarray
    channels: int
    pitch_frames: list[PitchFrame] = field(default_factory=list)
    edited_samples: np.ndarray | None = None
    edit_history: list[PitchEdit] = field(default_factory=list)

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
        )

    @property
    def file_name(self) -> str:
        return self.file_path.name

    @property
    def frame_count(self) -> int:
        return int(self.mono_samples.shape[0])

    @property
    def duration(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return self.frame_count / float(self.sample_rate)

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
    def has_edits(self) -> bool:
        return bool(self.edit_history)

    def apply_pitch_edit(
        self,
        edited_samples: np.ndarray,
        pitch_frames: list[PitchFrame],
        edit: PitchEdit,
    ) -> None:
        self.edited_samples = edited_samples.astype(np.float32, copy=False)
        self.mono_samples = self.current_mono_samples
        self.pitch_frames = pitch_frames
        self.edit_history.append(edit)

    def export_wav(self, file_path: str | Path) -> None:
        sf.write(str(file_path), self.current_samples, self.sample_rate)
