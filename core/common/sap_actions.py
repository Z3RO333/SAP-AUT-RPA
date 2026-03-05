from __future__ import annotations

from collections.abc import Iterable

from .run_context import RunContext
from .sap_wait import retry_call, wait, wait_not_busy, wait_for_element


def _normalize_ids(element_id: str | Iterable[str]) -> list[str]:
    if isinstance(element_id, str):
        return [element_id]
    return [str(item) for item in element_id]


def element_exists(session, element_id: str) -> bool:
    try:
        session.findById(element_id)
        return True
    except Exception:
        return False


def find(session, element_id: str, timeout: float = 10.0):
    return wait_for_element(session, element_id, timeout=timeout)


def first_existing(session, ids: Iterable[str]):
    for candidate in ids:
        if element_exists(session, candidate):
            return session.findById(candidate), candidate
    raise RuntimeError(f"Nenhum elemento encontrado entre os caminhos esperados: {list(ids)}")


def safe_first_existing(session, ids: Iterable[str]):
    for candidate in ids:
        if element_exists(session, candidate):
            return session.findById(candidate), candidate
    return None, None


def set_text(session, element_id: str | Iterable[str], value: str, context: RunContext | None = None) -> str:
    ids = _normalize_ids(element_id)
    _element, resolved_id = first_existing(session, ids)
    if context:
        context.track_field(context.last_stage or "sap", resolved_id)

    def _apply():
        target = session.findById(resolved_id)
        try:
            target.SetFocus()
        except Exception:
            pass
        target.Text = str(value)
        return target

    retry_call(_apply)
    wait(0.15)
    return resolved_id


def press(session, element_id: str | Iterable[str], context: RunContext | None = None) -> str:
    ids = _normalize_ids(element_id)
    element, resolved_id = first_existing(session, ids)
    if context:
        context.track_field(context.last_stage or "sap", resolved_id)
    element.press()
    wait_not_busy(session)
    return resolved_id


def select(session, element_id: str | Iterable[str], context: RunContext | None = None) -> str:
    ids = _normalize_ids(element_id)
    element, resolved_id = first_existing(session, ids)
    if context:
        context.track_field(context.last_stage or "sap", resolved_id)
    element.select()
    wait_not_busy(session)
    return resolved_id


def send_vkey(session, key: int) -> None:
    session.findById("wnd[0]").sendVKey(key)
    wait_not_busy(session)


def tcode(session, code: str) -> None:
    session.findById("wnd[0]/tbar[0]/okcd").Text = f"/n{code}"
    send_vkey(session, 0)
