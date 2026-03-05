from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .logging import ExecutionLogger
from .models import RunArtifact, StatusMessage


ProgressCallback = Callable[[str, int, int], None]
CancelCallback = Callable[[], bool]


@dataclass(slots=True)
class RunContext:
    logger: ExecutionLogger
    progress_callback: ProgressCallback | None = None
    cancel_callback: CancelCallback | None = None
    messages: list[StatusMessage] = field(default_factory=list)
    artifacts: list[RunArtifact] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    last_stage: str = ""
    last_field: str = ""

    def log(self, message: str) -> None:
        self.logger.info(message)

    def warn(self, message: str) -> None:
        self.logger.warn(message)
        self.messages.append(StatusMessage(level="warning", text=message))

    def error(self, message: str) -> None:
        self.logger.error(message)
        self.errors.append(message)

    def progress(self, stage: str, current: int, total: int) -> None:
        self.last_stage = stage
        if self.progress_callback:
            self.progress_callback(stage, current, total)

    def is_cancelled(self) -> bool:
        return bool(self.cancel_callback and self.cancel_callback())

    def track_field(self, stage: str, field_name: str) -> None:
        self.last_stage = stage
        self.last_field = field_name

    def add_artifact(self, artifact: RunArtifact) -> None:
        self.artifacts.append(artifact)

    def add_message(self, level: str, text: str, code: str = "", details: dict | None = None) -> None:
        self.messages.append(StatusMessage(level=level, text=text, code=code, details=details or {}))

