from __future__ import annotations

from core.common.layout_maps import field_candidates, load_layout_map, resolve_profile
from core.common.run_context import RunContext
from core.common.sap_actions import element_exists, press, safe_first_existing, send_vkey, set_text, tcode
from core.common.sap_popups import close_popup_ok
from core.common.sap_status import read_statusbar
from core.common.sap_wait import wait_not_busy


def load_iw32_profile(profile_name: str | None = None) -> tuple[str, dict]:
    layout_map = load_layout_map("IW32")
    return resolve_profile(layout_map, profile_name)


def open_order_iw32(session, order: str, profile: dict, context: RunContext | None = None) -> None:
    tcode(session, "IW32")
    wait_not_busy(session, timeout=60)
    close_popup_ok(session)

    order_fields = field_candidates(profile, "order", "orderFields")
    popup_order_fields = field_candidates(profile, "order", "popupOrderFields")
    other_order_buttons = field_candidates(profile, "order", "otherOrderButtons")

    for field_id in order_fields:
        if element_exists(session, field_id):
            set_text(session, field_id, order, context=context)
            send_vkey(session, 0)
            text, msg_type = read_statusbar(session)
            if msg_type == "E":
                raise RuntimeError(f"Erro ao abrir ordem {order}: {text}")
            return

    button, _resolved = safe_first_existing(session, other_order_buttons)
    if button is None:
        raise RuntimeError("Nao achei campo da ordem nem botao 'Outra ordem' na IW32.")

    button.press()
    wait_not_busy(session)
    if not popup_order_fields:
        raise RuntimeError("Layout IW32 sem popupOrderFields configurado.")
    set_text(session, popup_order_fields, order, context=context)
    send_vkey(session, 0)
    text, msg_type = read_statusbar(session)
    if msg_type == "E":
        raise RuntimeError(f"Erro ao abrir ordem {order}: {text}")


def select_cuk_tab(session, profile: dict, context: RunContext | None = None) -> None:
    press_id = field_candidates(profile, "tabs", "cukTab")
    if not press_id:
        raise RuntimeError("Layout IW32 sem cukTab configurado.")
    from core.common.sap_actions import select

    select(session, press_id, context=context)

