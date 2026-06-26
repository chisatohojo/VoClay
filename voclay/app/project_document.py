from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from voclay.app.audio_document import AudioDocument
from voclay.app.models import PitchFrame, PitchPoint, VocalNote


PROJECT_FORMAT_VERSION = 2
EDIT_SCOPE_SELECTED = "selected"
EDIT_SCOPE_RANGE = "range"
EDIT_SCOPE_ALL_SOURCE = "all_source"
VALID_EDIT_SCOPES = {EDIT_SCOPE_SELECTED, EDIT_SCOPE_RANGE, EDIT_SCOPE_ALL_SOURCE}


@dataclass
class ProjectDocument:
    reference_audio: AudioDocument | None = None
    source_audio: AudioDocument | None = None
    reference_notes: list[VocalNote] = field(default_factory=list)
    source_notes: list[VocalNote] = field(default_factory=list)
    rendered_preview: object | None = None
    preview_status: str = "Not rendered"
    edit_count: int = 0
    selection_range_start: float | None = None
    selection_range_end: float | None = None
    edit_scope: str = EDIT_SCOPE_SELECTED

    def __post_init__(self) -> None:
        self.edit_scope = _valid_edit_scope(self.edit_scope)
        if self.selection_range is None:
            self.clear_selection_range()

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

    @property
    def selection_range(self) -> tuple[float, float] | None:
        if self.selection_range_start is None or self.selection_range_end is None:
            return None
        start, end = sorted((float(self.selection_range_start), float(self.selection_range_end)))
        if end <= start:
            return None
        return start, end

    def bump_edit_count(self) -> None:
        self.edit_count += 1

    def clear_preview(self, reason: str = "Preview needs render") -> None:
        self.rendered_preview = None
        self.preview_status = reason

    def set_selection_range(self, start: float, end: float) -> None:
        start, end = sorted((max(0.0, float(start)), max(0.0, float(end))))
        if end <= start:
            self.clear_selection_range()
            return
        self.selection_range_start = start
        self.selection_range_end = end

    def move_selection_range(self, delta_time: float) -> float:
        selection = self.selection_range
        if selection is None:
            return 0.0
        start, end = selection
        delta_time = max(float(delta_time), -start)
        self.set_selection_range(start + delta_time, end + delta_time)
        return delta_time

    def clear_selection_range(self) -> None:
        self.selection_range_start = None
        self.selection_range_end = None

    def get_range_source_notes(self) -> list[VocalNote]:
        selection = self.selection_range
        if selection is None:
            return []
        start, end = selection
        return [
            note
            for note in self.source_notes
            if _is_editable_source_note(note) and note.end > start and note.start < end
        ]

    def get_edit_target_notes(self, selected_source_indices: set[int] | None = None) -> list[VocalNote]:
        if self.edit_scope == EDIT_SCOPE_RANGE:
            return self.get_range_source_notes()
        if self.edit_scope == EDIT_SCOPE_ALL_SOURCE:
            return [note for note in self.source_notes if _is_editable_source_note(note)]

        selected_source_indices = selected_source_indices or set()
        return [
            self.source_notes[index]
            for index in sorted(selected_source_indices)
            if 0 <= index < len(self.source_notes)
            and _is_editable_source_note(self.source_notes[index])
        ]

    def save(self, file_path: str | Path) -> None:
        path = Path(file_path)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, file_path: str | Path) -> "ProjectDocument":
        path = Path(file_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def to_dict(self) -> dict:
        return {
            "format": "VoClay Project",
            "format_version": PROJECT_FORMAT_VERSION,
            "reference_audio_path": _path_to_text(self.reference_audio.file_path if self.reference_audio else None),
            "source_audio_path": _path_to_text(self.source_audio.file_path if self.source_audio else None),
            "reference_pitch_frames": _pitch_frames_to_dict(
                self.reference_audio.pitch_frames if self.reference_audio else []
            ),
            "source_pitch_frames": _pitch_frames_to_dict(
                self.source_audio.pitch_frames if self.source_audio else []
            ),
            "reference_notes": [_note_to_dict(note) for note in self.reference_notes],
            "source_notes": [_note_to_dict(note) for note in self.source_notes],
            "edit_count": self.edit_count,
            "preview_status": self.preview_status,
            "selection_range_start": _optional_float(self.selection_range_start),
            "selection_range_end": _optional_float(self.selection_range_end),
            "edit_scope": self.edit_scope,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectDocument":
        reference_audio = _load_audio_document(
            data.get("reference_audio_path"),
            "Reference",
            data.get("reference_pitch_frames", []),
        )
        source_audio = _load_audio_document(
            data.get("source_audio_path"),
            "Source",
            data.get("source_pitch_frames", []),
        )
        reference_notes = [
            _note_from_dict(note_data, "reference", locked=True)
            for note_data in data.get("reference_notes", [])
        ]
        source_notes = [
            _note_from_dict(note_data, "source", locked=False)
            for note_data in data.get("source_notes", [])
        ]
        if reference_audio is not None:
            reference_audio.note_segments = reference_notes
        if source_audio is not None:
            source_audio.note_segments = source_notes

        project = cls(
            reference_audio=reference_audio,
            source_audio=source_audio,
            reference_notes=reference_notes,
            source_notes=source_notes,
            rendered_preview=None,
            preview_status="Preview needs render" if source_notes else "Not rendered",
            edit_count=int(data.get("edit_count", 0) or 0),
            selection_range_start=_optional_float(data.get("selection_range_start")),
            selection_range_end=_optional_float(data.get("selection_range_end")),
            edit_scope=_valid_edit_scope(data.get("edit_scope")),
        )
        return project


def _path_to_text(path: Path | None) -> str | None:
    return str(path) if path is not None else None


def _load_audio_document(
    file_path: str | None,
    input_mode: str,
    pitch_frame_data: list[dict],
) -> AudioDocument | None:
    if not file_path:
        return None
    path = Path(file_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"{input_mode} WAV was not found: {path}")

    document = AudioDocument.load(path)
    document.set_input_mode(input_mode)
    document.use_source_for_analysis()
    document.pitch_frames = [_pitch_frame_from_dict(frame) for frame in pitch_frame_data]
    return document


def _pitch_frames_to_dict(frames: list[PitchFrame]) -> list[dict]:
    return [
        {
            "time": float(frame.time),
            "f0": _optional_float(frame.f0),
            "voiced": bool(frame.voiced),
            "confidence": _optional_float(frame.confidence),
        }
        for frame in frames
    ]


def _pitch_frame_from_dict(data: dict) -> PitchFrame:
    return PitchFrame(
        time=float(data.get("time", 0.0) or 0.0),
        f0=_optional_float(data.get("f0")),
        voiced=bool(data.get("voiced", False)),
        confidence=_optional_float(data.get("confidence")),
    )


def _pitch_point_to_dict(point: PitchPoint) -> dict:
    return {
        "time": float(point.time),
        "f0": _optional_float(point.f0),
        "midi": _optional_float(point.midi),
        "voiced": bool(point.voiced),
        "confidence": _optional_float(point.confidence),
    }


def _pitch_point_from_dict(data: dict) -> PitchPoint:
    return PitchPoint(
        time=float(data.get("time", 0.0) or 0.0),
        f0=_optional_float(data.get("f0")),
        midi=_optional_float(data.get("midi")),
        voiced=bool(data.get("voiced", False)),
        confidence=_optional_float(data.get("confidence")),
    )


def _note_to_dict(note: VocalNote) -> dict:
    return {
        "id": int(note.id),
        "start_time": float(note.start_time),
        "end_time": float(note.end_time),
        "midi_note": int(note.midi_note),
        "track_type": note.track_type,
        "original_start_time": _optional_float(note.original_start_time),
        "original_end_time": _optional_float(note.original_end_time),
        "cents_offset": float(note.cents_offset),
        "original_midi_median": float(note.original_midi_median),
        "pitch_points": [_pitch_point_to_dict(point) for point in note.pitch_points],
        "split_reason": note.split_reason,
        "locked": bool(note.locked),
        "confidence": _optional_float(note.confidence),
        "voiced": bool(note.voiced),
        "average_f0": float(note.average_f0),
    }


def _note_from_dict(data: dict, track_type: str, locked: bool) -> VocalNote:
    return VocalNote(
        id=int(data.get("id", 0) or 0),
        start_time=float(data.get("start_time", 0.0) or 0.0),
        end_time=float(data.get("end_time", 0.0) or 0.0),
        midi_note=int(data.get("midi_note", 60) or 60),
        track_type=track_type,
        original_start_time=_optional_float(data.get("original_start_time")),
        original_end_time=_optional_float(data.get("original_end_time")),
        cents_offset=float(data.get("cents_offset", 0.0) or 0.0),
        original_midi_median=float(data.get("original_midi_median", data.get("midi_note", 60)) or 60.0),
        pitch_points=tuple(_pitch_point_from_dict(point) for point in data.get("pitch_points", [])),
        split_reason=str(data.get("split_reason", "loaded_project")),
        selected=False,
        locked=locked,
        confidence=_optional_float(data.get("confidence")),
        voiced=bool(data.get("voiced", True)),
        average_f0=float(data.get("average_f0", 0.0) or 0.0),
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _valid_edit_scope(value: object) -> str:
    if isinstance(value, str) and value in VALID_EDIT_SCOPES:
        return value
    return EDIT_SCOPE_SELECTED


def _is_editable_source_note(note: VocalNote) -> bool:
    return note.track_type == "source" and not note.locked
