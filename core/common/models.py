from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class StatusMessage:
    level: str
    text: str
    code: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunArtifact:
    name: str
    path: str
    kind: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_path(cls, name: str, path: Path, kind: str, metadata: dict[str, Any] | None = None) -> "RunArtifact":
        return cls(name=name, path=str(path), kind=kind, metadata=metadata or {})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SessionMeta:
    session_ref: str
    connection_index: int
    session_index: int
    connection_name: str = ""
    system_name: str = ""
    client: str = ""
    user: str = ""
    transaction: str = ""
    window_title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RobotResult:
    robot: str
    run_id: str
    status: str
    started_at: str
    finished_at: str
    session_meta: dict[str, Any] = field(default_factory=dict)
    status_bar_text: str = ""
    status_bar_type: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    business_result: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(cls, robot: str, run_id: str) -> "RobotResult":
        now = datetime.now().isoformat(timespec="seconds")
        return cls(robot=robot, run_id=run_id, status="success", started_at=now, finished_at=now)

    def finalize(self) -> "RobotResult":
        self.finished_at = datetime.now().isoformat(timespec="seconds")
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ValidationIssue:
    sheet: str
    row_number: int
    column_name: str
    level: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
