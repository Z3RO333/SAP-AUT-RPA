from __future__ import annotations

from typing import Any


def _safe_getattr(obj, name: str, default: Any = "") -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return default


def popup_exists(session) -> bool:
    try:
        session.findById("wnd[1]")
        return True
    except Exception:
        return False


def _walk_element(element, depth: int = 0, max_depth: int = 4) -> dict[str, Any]:
    entry = {
        "id": _safe_getattr(element, "Id", ""),
        "type": _safe_getattr(element, "Type", ""),
        "name": _safe_getattr(element, "Name", ""),
        "text": _safe_getattr(element, "Text", ""),
        "tooltip": _safe_getattr(element, "Tooltip", ""),
        "children": [],
    }
    if depth >= max_depth:
        return entry
    try:
        count = int(_safe_getattr(element.Children, "Count", 0) or 0)
    except Exception:
        count = 0
    for index in range(count):
        try:
            child = element.Children(index)
            entry["children"].append(_walk_element(child, depth + 1, max_depth=max_depth))
        except Exception:
            continue
    return entry


def dump_popup(session) -> dict[str, Any] | None:
    try:
        popup = session.findById("wnd[1]")
    except Exception:
        return None
    return _walk_element(popup, depth=0, max_depth=4)


def close_popup_ok(session) -> bool:
    for candidate in ("wnd[1]/tbar[0]/btn[0]", "wnd[1]/usr/btnSPOP-OPTION1", "wnd[1]/usr/btnSPOP-VAROPTION1"):
        try:
            session.findById(candidate).press()
            return True
        except Exception:
            continue
    return False
