from __future__ import annotations

from pathlib import Path

import win32gui
from PIL import ImageGrab


def _find_window_rect(title_fragment: str) -> tuple[int, int, int, int] | None:
    result: tuple[int, int, int, int] | None = None
    target = (title_fragment or "").strip().lower()

    def _callback(hwnd, _extra):
        nonlocal result
        if result is not None:
            return
        title = win32gui.GetWindowText(hwnd).strip().lower()
        if not title:
            return
        if target and target not in title:
            return
        if not win32gui.IsWindowVisible(hwnd):
            return
        result = win32gui.GetWindowRect(hwnd)

    win32gui.EnumWindows(_callback, None)
    return result


def capture_sap_window(session, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    title = ""
    try:
        title = str(session.findById("wnd[0]").Text or "")
    except Exception:
        title = ""
    bbox = _find_window_rect(title) if title else None
    image = ImageGrab.grab(bbox=bbox, all_screens=True) if bbox else ImageGrab.grab(all_screens=True)
    image.save(output_path)
    return output_path

