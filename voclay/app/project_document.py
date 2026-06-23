from __future__ import annotations

from dataclasses import dataclass, field

from voclay.app.audio_document import AudioDocument
from voclay.app.models import VocalNote


@dataclass
class ProjectDocument:
    reference_audio: AudioDocument | None = None
    source_audio: AudioDocument | None = None
    reference_notes: list[VocalNote] = field(default_factory=list)
    source_notes: list[VocalNote] = field(default_factory=list)
    rendered_preview: object | None = None
    preview_status: str = "Not rendered"
    edit_count: int = 0

    @property
    def duration(self) -> float:
        durations = [
            document.duration
            for document in (self.reference_audio, self.source_audio)
            if document is not None
        ]
        durations.extend(note.end for note in self.reference_notes)
        durations.extend(note.end for note in self.source_notes)
        preview_duration = getattr(self.rendered_preview, "duration", None)
        if preview_duration is not None:
            durations.append(float(preview_duration))
        return max(durations, default=0.0)

    @property
    def has_preview(self) -> bool:
        return bool(getattr(self.rendered_preview, "success", False))

    def bump_edit_count(self) -> None:
        self.edit_count += 1

    def clear_preview(self, reason: str = "Preview needs render") -> None:
        self.rendered_preview = None
        self.preview_status = reason
