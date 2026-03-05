from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable


LogCallback = Callable[[str], None]


class ExecutionLogger:
    def __init__(self, log_path: Path, callback: LogCallback | None = None) -> None:
        self.log_path = log_path
        self.callback = callback
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.write_text("", encoding="utf-8")

    def _write(self, level: str, message: str) -> None:
        line = f"{datetime.now().isoformat(timespec='seconds')} [{level}] {message}"
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
        if self.callback:
            self.callback(line)

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def warn(self, message: str) -> None:
        self._write("WARN", message)

    def error(self, message: str) -> None:
        self._write("ERROR", message)

