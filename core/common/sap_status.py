from __future__ import annotations

from .models import StatusMessage


def read_statusbar(session) -> tuple[str, str]:
    try:
        statusbar = session.findById("wnd[0]/sbar")
        return str(getattr(statusbar, "Text", "") or ""), str(getattr(statusbar, "MessageType", "") or "")
    except Exception:
        return "", ""


def status_message(session) -> StatusMessage:
    text, msg_type = read_statusbar(session)
    level_map = {
        "S": "success",
        "W": "warning",
        "E": "error",
        "A": "abort",
        "I": "info",
    }
    return StatusMessage(level=level_map.get(msg_type, "info"), text=text, code=msg_type)

