from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent


def ensure_repo_root() -> Path:
    repo_root = str(REPO_ROOT)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    return REPO_ROOT


def open_path(path: str) -> None:
    os.startfile(path)


def result_failure_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    result_status = str(payload.get("status", "") or "")
    if result_status not in ("error", "cancelled"):
        return ""

    errors = [str(item) for item in payload.get("errors", []) if str(item).strip()]
    if errors:
        return "\n".join(errors[:5])
    if result_status == "cancelled":
        return "Execucao cancelada antes de concluir o processamento."
    return "O robo terminou com erro antes de processar os itens."


def pick_session_thread_safe(root, sessions: list[dict]) -> str | None:
    from core.common.session_picker import pick_session

    if threading.current_thread() is threading.main_thread():
        return pick_session(sessions, root)

    result_holder: list[str | None] = [None]
    done = threading.Event()

    def _show() -> None:
        try:
            result_holder[0] = pick_session(sessions, root)
        finally:
            done.set()

    root.after(0, _show)
    done.wait()
    return result_holder[0]
