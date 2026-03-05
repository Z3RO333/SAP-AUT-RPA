from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _safe_getattr(obj, name: str, default: Any = "") -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _walk(element, depth: int = 0, max_depth: int = 10) -> dict[str, Any]:
    entry = {
        "id": _safe_getattr(element, "Id", ""),
        "type": _safe_getattr(element, "Type", ""),
        "name": _safe_getattr(element, "Name", ""),
        "text": _safe_getattr(element, "Text", ""),
        "tooltip": _safe_getattr(element, "Tooltip", ""),
        "childrenCount": 0,
        "children": [],
    }
    if depth >= max_depth:
        return entry
    try:
        count = int(_safe_getattr(element.Children, "Count", 0) or 0)
    except Exception:
        count = 0
    entry["childrenCount"] = count
    for index in range(count):
        try:
            child = element.Children(index)
            entry["children"].append(_walk(child, depth + 1, max_depth=max_depth))
        except Exception:
            continue
    return entry


def inspect_session(session, max_depth: int = 10) -> dict[str, Any]:
    root = session.findById("wnd[0]")
    return {
        "transaction": str(getattr(getattr(session, "Info", None), "Transaction", "") or ""),
        "windowTitle": str(getattr(root, "Text", "") or ""),
        "tree": _walk(root, max_depth=max_depth),
    }


def write_inspection_artifacts(session, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = inspect_session(session)
    json_path = output_dir / "inspect-tree.json"
    txt_path = output_dir / "inspect-summary.txt"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines: list[str] = []

    def _flatten(entry: dict[str, Any], depth: int = 0) -> None:
        prefix = "  " * depth
        lines.append(
            f"{prefix}- {entry.get('id', '')} | {entry.get('type', '')} | {entry.get('name', '')} | {entry.get('text', '')}"
        )
        for child in entry.get("children", []):
            _flatten(child, depth + 1)

    _flatten(payload["tree"])
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, txt_path
