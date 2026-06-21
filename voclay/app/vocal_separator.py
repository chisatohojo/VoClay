from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys


@dataclass(frozen=True)
class VocalSeparationResult:
    vocal_path: str
    accompaniment_path: str | None
    success: bool
    message: str


class VocalSeparator:
    def separate(self, input_path: str, output_dir: str) -> VocalSeparationResult:
        source = Path(input_path)
        target_dir = Path(output_dir)
        if not source.exists():
            return VocalSeparationResult("", None, False, f"Input file not found: {source}")

        demucs_command = self._demucs_command()
        if demucs_command is None:
            return VocalSeparationResult(
                "",
                None,
                False,
                "demucs is not installed. Install demucs to use Mixed Audio mode.",
            )

        target_dir.mkdir(parents=True, exist_ok=True)
        command = [
            *demucs_command,
            "--two-stems",
            "vocals",
            "-o",
            str(target_dir),
            str(source),
        ]

        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except Exception as exc:  # noqa: BLE001
            return VocalSeparationResult("", None, False, f"Vocal separation failed: {exc}")

        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            return VocalSeparationResult(
                "",
                None,
                False,
                f"Vocal separation failed: {detail or 'demucs exited with an error.'}",
            )

        candidates = list(target_dir.glob(f"**/{source.stem}/vocals.wav"))
        if not candidates:
            candidates = list(target_dir.glob("**/vocals.wav"))
        if not candidates:
            return VocalSeparationResult("", None, False, "demucs finished but vocals.wav was not found.")

        vocal_path = candidates[0]
        accompaniment = vocal_path.with_name("no_vocals.wav")
        return VocalSeparationResult(
            vocal_path=str(vocal_path),
            accompaniment_path=str(accompaniment) if accompaniment.exists() else None,
            success=True,
            message="Vocal separation complete.",
        )

    def _demucs_command(self) -> list[str] | None:
        if shutil.which("demucs") is not None:
            return ["demucs"]

        try:
            import demucs  # noqa: F401
        except Exception:  # noqa: BLE001
            return None
        return [sys.executable, "-m", "demucs"]
