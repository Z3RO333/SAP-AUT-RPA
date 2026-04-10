from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pythoncom

from core.common.excel_utils import as_decimal, as_text, normalize_column_name
from core.common.layout_maps import load_layout_map, resolve_profile
from core.common.logging import ExecutionLogger
from core.common.models import RobotResult, RunArtifact
from core.common.run_context import RunContext
from core.common.runtime import ensure_dir, run_output_dir, timestamp_id
from core.common.sap_actions import element_exists, press, select, send_vkey, set_text, tcode
from core.common.sap_popups import close_popup_ok, dump_popup
from core.common.sap_session import resolve_session
from core.common.sap_status import read_statusbar
from core.common.screenshots import capture_sap_window
from core.common.sap_wait import wait, wait_not_busy


# ---------------------------------------------------------------------------
# Layout loaders
# ---------------------------------------------------------------------------

def load_me23n_profile(profile_name: str | None = None) -> tuple[str, dict]:
    layout_map = load_layout_map("ME23N")
    return resolve_profile(layout_map, profile_name)


def load_me22n_profile(profile_name: str | None = None) -> tuple[str, dict]:
    layout_map = load_layout_map("ME22N")
    return resolve_profile(layout_map, profile_name)


def _format_sap_decimal(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized.replace(".", ",")


def _normalize_service_external_text(value: str | None, max_length: int = 18) -> str:
    """
    O campo EXTSRVNO do grid de servicos do ME22N aceita texto curto.
    Pelos scripts manuais, o SAP trabalha com 18 caracteres nesse campo.
    """
    normalized = " ".join(str(value or "").strip().split())
    return normalized[:max_length]


# ---------------------------------------------------------------------------
# Internal helpers — ME23N (original)
# ---------------------------------------------------------------------------

def _first_existing(session, ids: list[str]) -> str:
    for candidate in ids:
        if element_exists(session, candidate):
            return candidate
    raise RuntimeError(f"Nenhum elemento encontrado entre os caminhos esperados: {ids}")


def _close_validation_popups(session) -> None:
    while close_popup_ok(session):
        wait_not_busy(session)


def _open_order_me23n(session, pedido: str, profile: dict, context: RunContext) -> None:
    tcode(session, "ME23N")
    toolbar = profile.get("toolbar", {})
    press(session, toolbar.get("selectOrder", []), context=context)
    set_text(session, toolbar.get("orderPopupField", []), pedido, context=context)
    press(session, toolbar.get("orderPopupOk", []), context=context)
    edit_button = toolbar.get("editMode", [])
    if edit_button:
        button_id = _first_existing(session, edit_button)
        try:
            session.findById(button_id).press()
            wait_not_busy(session)
        except Exception:
            pass


def _copy_first_item(session, profile: dict, context: RunContext) -> None:
    press(session, profile.get("toolbar", {}).get("copyItem", []), context=context)


def _set_delivery_date(session, data_entrega: str | None, profile: dict, context: RunContext) -> None:
    if not data_entrega:
        return
    tabs = profile.get("tabs", {})
    select(session, tabs.get("datesTab", []), context=context)
    set_text(session, profile.get("fields", {}).get("deliveryDate", []), data_entrega, context=context)


def _fill_service_lines_me23n(session, ordens_aufnr: list[str], profile: dict, context: RunContext) -> None:
    tabs = profile.get("tabs", {})
    select(session, tabs.get("servicesTab", []), context=context)
    table_id = _first_existing(session, profile.get("tables", {}).get("servicesTable", []))
    template = str(profile.get("tables", {}).get("serviceAufnrTemplate", ""))
    if not template:
        raise RuntimeError("Layout ME23N sem serviceAufnrTemplate configurado.")
    for index, aufnr in enumerate(ordens_aufnr):
        field_id = table_id + template.format(row=index)
        set_text(session, field_id, aufnr, context=context)
        _close_validation_popups(session)


# ---------------------------------------------------------------------------
# Internal helpers — ME22N (new)
# ---------------------------------------------------------------------------

def _open_order_me22n(session, pedido: str, profile: dict, context: RunContext) -> None:
    tcode(session, "ME22N")
    toolbar = profile.get("toolbar", {})
    press(session, toolbar.get("selectOrder", []), context=context)
    set_text(session, toolbar.get("orderPopupField", []), pedido, context=context)
    press(session, toolbar.get("orderPopupOk", []), context=context)
    # Tenta habilitar modo edicao (opcional — ignora se botao nao existir)
    _close_me22n_transient_popups(session)


def _is_items_overview_editable_me22n(session, profile: dict, page_size: int = 6) -> bool | None:
    tables = profile.get("tables", {})
    table_candidates = tables.get("itemsTable", [])
    probe_templates = [
        tables.get("itemKnttpTemplate", ""),
        tables.get("itemTxz01Template", ""),
        tables.get("itemEbelpTemplate", ""),
    ]

    table_id = None
    for candidate in table_candidates:
        if element_exists(session, candidate):
            table_id = candidate
            break
    if not table_id:
        return None

    for visual_row in range(page_size):
        for template in probe_templates:
            if not template:
                continue
            try:
                element = session.findById(table_id + template.format(row=visual_row))
            except Exception:
                continue
            try:
                return bool(getattr(element, "Changeable"))
            except Exception:
                continue

    return None


def _ensure_edit_mode_me22n(session, profile: dict) -> None:
    toolbar = profile.get("toolbar", {})
    edit_buttons = toolbar.get("editMode", [])
    if not edit_buttons:
        return

    for _ in range(8):
        editable = _is_items_overview_editable_me22n(session, profile)
        if editable is True:
            return
        if editable is False:
            for candidate in edit_buttons:
                if not element_exists(session, candidate):
                    continue
                try:
                    session.findById(candidate).press()
                    wait_not_busy(session)
                    wait(0.3)
                except Exception:
                    continue
                return
        wait(0.3)


def _select_item_me22n(session, item_ebelp: str, profile: dict) -> None:
    """
    Localiza o item pelo numero EBELP na tabela de itens e o seleciona.
    Suporta scroll (tabela mostra 6 linhas por vez).
    Se o EBELP nao for encontrado, clica na primeira linha vazia (novo item).
    """
    tables = profile.get("tables", {})
    items_table_candidates = tables.get("itemsTable", [])
    ebelp_tmpl = tables.get("itemEbelpTemplate", "")
    select_tmpl = tables.get("itemSelectTemplate", "")
    if not items_table_candidates or not ebelp_tmpl:
        return  # sem layout, assume item ja selecionado

    table_id = None
    for candidate in items_table_candidates:
        if element_exists(session, candidate):
            table_id = candidate
            break
    if not table_id:
        return

    target = str(item_ebelp).strip().lstrip("0") or "0"  # "00010" -> "10"
    page_size = 6  # tabela de itens mostra 6 linhas por vez

    def _scroll_items(pos: int) -> None:
        try:
            session.findById(table_id).verticalScrollbar.position = pos
            wait_not_busy(session)
        except Exception:
            pass

    def _focus_row(visual_row: int) -> None:
        if select_tmpl:
            try:
                session.findById(table_id + select_tmpl.format(row=visual_row)).setFocus()
                wait_not_busy(session)
                return
            except Exception:
                pass
        try:
            session.findById(table_id + ebelp_tmpl.format(row=visual_row)).setFocus()
            wait_not_busy(session)
        except Exception:
            pass

    # Fase 1: busca por EBELP com scroll
    for page_start in range(0, 300, page_size):
        if page_start > 0:
            _scroll_items(page_start)
        page_has_rows = False
        for visual_row in range(page_size):
            try:
                field_id = table_id + ebelp_tmpl.format(row=visual_row)
                el = session.findById(field_id)
                page_has_rows = True
                value = str(getattr(el, "Text", "") or "").strip().lstrip("0") or "0"
                if value == target:
                    _focus_row(visual_row)
                    return
                if not value or value == "0":
                    break  # linha vazia = fim da tabela nesta pagina
            except Exception:
                break
        if not page_has_rows:
            break

    # Fase 2: fallback — clica na primeira linha vazia (cria novo item)
    _scroll_items(0)
    wait(0.3)
    for page_start in range(0, 300, page_size):
        if page_start > 0:
            _scroll_items(page_start)
        for visual_row in range(page_size):
            try:
                field_id = table_id + ebelp_tmpl.format(row=visual_row)
                el = session.findById(field_id)
                value = str(getattr(el, "Text", "") or "").strip()
                if not value:
                    _focus_row(visual_row)
                    return
            except Exception:
                return  # sem mais linhas

def _get_items_table_id(session, profile: dict) -> str:
    candidates = profile.get("tables", {}).get("itemsTable", [])
    return _first_existing(session, candidates)


def _scroll_items_table(session, table_id: str, position: int) -> None:
    try:
        table = session.findById(table_id)
        table.verticalScrollbar.position = position
        wait_not_busy(session)
        wait(0.2)
    except Exception:
        pass


def _get_items_scroll_position(session, table_id: str) -> int:
    try:
        return int(getattr(session.findById(table_id).verticalScrollbar, "position", 0) or 0)
    except Exception:
        return 0


def _position_item_row(session, profile: dict, absolute_row: int, page_size: int = 6) -> tuple[str, int]:
    for desired_scroll in (
        max(absolute_row - (page_size - 1), 0),
        max(absolute_row - 1, 0),
        max(absolute_row, 0),
    ):
        table_id = _get_items_table_id(session, profile)
        _scroll_items_table(session, table_id, desired_scroll)
        table_id = _get_items_table_id(session, profile)
        actual_scroll = _get_items_scroll_position(session, table_id)
        visual_row = absolute_row - actual_scroll
        if 0 <= visual_row < page_size:
            return table_id, visual_row

    raise RuntimeError(
        f"Nao foi possivel posicionar a linha {absolute_row} no quadro de itens. "
        f"Scroll atual: {actual_scroll}."
    )


def _focus_item_overview_row(session, profile: dict, absolute_row: int, page_size: int = 6) -> None:
    tables = profile.get("tables", {})
    select_tmpl = tables.get("itemSelectTemplate", "")
    ebelp_tmpl = tables.get("itemEbelpTemplate", "")
    table_id, visual_row = _position_item_row(session, profile, absolute_row, page_size=page_size)
    target_id = ""
    if select_tmpl:
        target_id = table_id + select_tmpl.format(row=visual_row)
    elif ebelp_tmpl:
        target_id = table_id + ebelp_tmpl.format(row=visual_row)
    if not target_id:
        return
    try:
        session.findById(target_id).setFocus()
        wait_not_busy(session)
        wait(0.15)
    except Exception:
        pass


def _read_item_cell(session, table_id: str, template: str, visual_row: int) -> str:
    if not template:
        return ""
    field_id = table_id + template.format(row=visual_row)
    element = session.findById(field_id)
    return str(getattr(element, "Text", "") or "").strip()


def _read_item_probe_values(session, table_id: str, tables: dict, visual_row: int) -> dict[str, str]:
    probe_names = [
        "itemEbelpTemplate",
        "itemKnttpTemplate",
        "itemTxz01Template",
        "itemWgbezTemplate",
        "itemName1Template",
    ]
    values: dict[str, str] = {}
    for template_name in probe_names:
        template = tables.get(template_name, "")
        if not template:
            continue
        try:
            values[template_name] = _read_item_cell(session, table_id, template, visual_row)
        except Exception:
            values[template_name] = ""
    return values


def _item_row_has_data(values: dict[str, str]) -> bool:
    return any((value or "").strip() for value in values.values())


def _inspect_visible_append_slot(
    session,
    table_id: str,
    tables: dict,
    actual_scroll: int,
    page_size: int,
) -> dict[str, int | str] | None:
    last_visible_filled_row: int | None = None
    last_visible_filled_visual_row: int | None = None

    for visual_row in range(page_size):
        absolute_row = actual_scroll + visual_row
        values = _read_item_probe_values(session, table_id, tables, visual_row)

        if _item_row_has_data(values):
            last_visible_filled_row = absolute_row
            last_visible_filled_visual_row = visual_row
            continue
        if last_visible_filled_row is None:
            continue
        return {
            "table_id": table_id,
            "scroll": actual_scroll,
            "source_row": last_visible_filled_row,
            "target_row": absolute_row,
            "source_visual_row": last_visible_filled_row - actual_scroll,
            "target_visual_row": visual_row,
        }

    if last_visible_filled_row is not None and last_visible_filled_visual_row is not None:
        next_visual_row = last_visible_filled_visual_row + 1
        if next_visual_row < page_size:
            return {
                "table_id": table_id,
                "scroll": actual_scroll,
                "source_row": last_visible_filled_row,
                "target_row": last_visible_filled_row + 1,
                "source_visual_row": last_visible_filled_visual_row,
                "target_visual_row": next_visual_row,
            }

    return None


def _find_append_slot_me22n(session, profile: dict, page_size: int = 6) -> dict[str, int | str]:
    tables = profile.get("tables", {})
    if not (
        tables.get("itemEbelpTemplate")
        or tables.get("itemKnttpTemplate")
        or tables.get("itemTxz01Template")
    ):
        raise RuntimeError("Layout ME22N sem campos do quadro de itens configurados.")

    repeated_scrolls = 0
    last_actual_scroll: int | None = None
    for desired_scroll in range(0, 500):
        table_id = _get_items_table_id(session, profile)
        _scroll_items_table(session, table_id, desired_scroll)
        table_id = _get_items_table_id(session, profile)
        actual_scroll = _get_items_scroll_position(session, table_id)

        if last_actual_scroll is not None and actual_scroll == last_actual_scroll:
            repeated_scrolls += 1
        else:
            repeated_scrolls = 0
        last_actual_scroll = actual_scroll

        slot = _inspect_visible_append_slot(
            session,
            table_id,
            tables,
            actual_scroll,
            page_size,
        )
        if slot:
            return slot

        if repeated_scrolls >= 4 and desired_scroll > actual_scroll:
            break

    raise RuntimeError("Nao foi possivel localizar a ultima linha preenchida e a primeira linha vazia no quadro de itens.")


def _normalize_item_header_value(template_name: str, value: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return ""
    if template_name == "itemName1Template":
        return normalized.split(" - ", 1)[0].strip()
    return normalized


def _write_item_header_field(
    session,
    field_id: str,
    value: str,
    context: RunContext,
    confirm: bool = False,
) -> None:
    if not value:
        return
    set_text(session, field_id, value, context=context)
    if not confirm:
        return
    try:
        element = session.findById(field_id)
        element.setFocus()
        try:
            element.caretPosition = len(str(value))
        except Exception:
            pass
        wait_not_busy(session)
        wait(0.1)
    except Exception:
        pass
    send_vkey(session, 0)


def _focus_item_current_page(session, profile: dict, absolute_row: int, page_size: int = 6) -> bool:
    tables = profile.get("tables", {})
    focus_template = (
        tables.get("itemKnttpTemplate")
        or tables.get("itemSelectTemplate")
        or tables.get("itemEbelpTemplate")
    )
    if not focus_template:
        return False

    try:
        table_id = _get_items_table_id(session, profile)
        actual_scroll = _get_items_scroll_position(session, table_id)
        visual_row = absolute_row - actual_scroll
        if not (0 <= visual_row < page_size):
            return False
        focus_id = table_id + focus_template.format(row=visual_row)
        session.findById(focus_id).setFocus()
        wait_not_busy(session)
        wait(0.15)
        return True
    except Exception:
        return False


def _sum_group_total_me22n(linhas: list[dict]) -> str | None:
    if not linhas:
        return None
    total = Decimal("0")
    for linha in linhas:
        valor = as_text(linha.get("valor"))
        if not valor:
            return None
        decimal_value = as_decimal(valor)
        if decimal_value is None:
            return None
        total += decimal_value
    return _format_sap_decimal(total)


def _popup_text_blob(entry: dict | None) -> str:
    if not entry:
        return ""
    parts: list[str] = []
    for key in ("text", "name", "tooltip"):
        value = str(entry.get(key, "") or "").strip()
        if value:
            parts.append(value)
    for child in entry.get("children", []) or []:
        parts.append(_popup_text_blob(child))
    return " ".join(part for part in parts if part).strip()


def _close_me22n_transient_popups(session, max_attempts: int = 6) -> None:
    for _ in range(max_attempts):
        if element_exists(session, "wnd[2]"):
            try:
                session.findById("wnd[2]/tbar[0]/btn[0]").press()
                wait_not_busy(session)
                wait(0.15)
                continue
            except Exception:
                pass

        popup = dump_popup(session)
        if not popup:
            break

        popup_title = ""
        try:
            popup_title = str(getattr(session.findById("wnd[1]"), "Text", "") or "").strip().lower()
        except Exception:
            popup_title = ""

        popup_text = f"{popup_title} {_popup_text_blob(popup).lower()}".strip()
        if (
            "encerrar doc" in popup_text
            or "documento registrado" in popup_text
            or "gravar antes" in popup_text
        ):
            closed = False
            for candidate in (
                "wnd[1]/usr/btnSPOP-OPTION3",
                "wnd[1]/usr/btnSPOP-VAROPTION3",
                "wnd[1]/tbar[0]/btn[12]",
            ):
                try:
                    session.findById(candidate).press()
                    wait_not_busy(session)
                    wait(0.15)
                    closed = True
                    break
                except Exception:
                    continue
            if closed:
                continue
            break

        if close_popup_ok(session):
            wait_not_busy(session)
            wait(0.15)
            continue

        break


def _handle_item_creation_popups(session) -> None:
    for _ in range(10):
        if element_exists(session, "wnd[2]"):
            try:
                session.findById("wnd[2]").sendVKey(0)
                wait_not_busy(session)
                wait(0.15)
            except Exception:
                pass
            continue

        if not element_exists(session, "wnd[1]"):
            break

        if element_exists(session, "wnd[1]/usr/ctxtESKN-SAKTO"):
            break

        if close_popup_ok(session):
            wait_not_busy(session)
            wait(0.15)
            continue

        handled = False
        for key in (2, 0):
            try:
                session.findById("wnd[1]").sendVKey(key)
                wait_not_busy(session)
                wait(0.15)
                handled = True
                break
            except Exception:
                continue
        if not handled:
            break


def _prepare_new_item_me22n(
    session,
    linhas: list[dict],
    profile: dict,
    context: RunContext,
    page_size: int = 6,
) -> int:
    """
    Cria um novo item no quadro superior (ME22N) copiando os campos do item acima.
    Segue exatamente a sequencia gravada no VBS pelo usuario:
      KNTTP(Enter) → EPSTP(Enter) → TXZ01(sem Enter) → WGBEZ(sem Enter) → NAME1(Enter)
      → fecha wnd[1] → SAP auto-navega para aba Servicos.
    """
    _close_me22n_transient_popups(session)

    tables = profile.get("tables", {})
    # Campos que o SAP exige para criar o item, na ordem exata do VBS.
    header_fields = [
        "itemKnttpTemplate",
        "itemEpstpTemplate",
        "itemTxz01Template",
        "itemWgbezTemplate",
        "itemName1Template",
    ]
    # Campos que recebem Enter apos preenchimento (os demais nao recebem).
    fields_with_enter = {"itemKnttpTemplate", "itemEpstpTemplate", "itemName1Template"}

    slot = _find_append_slot_me22n(session, profile, page_size=page_size)
    source_row = int(slot["source_row"])
    target_row = int(slot["target_row"])
    scroll_position = int(slot["scroll"])

    table_id = _get_items_table_id(session, profile)
    _scroll_items_table(session, table_id, scroll_position)
    table_id = _get_items_table_id(session, profile)
    actual_scroll = _get_items_scroll_position(session, table_id)
    source_visual_row = source_row - actual_scroll
    target_visual_row = target_row - actual_scroll

    # Le valores do item acima para copiar.
    source_values: dict[str, str] = {}
    for template_name in header_fields:
        template = tables.get(template_name, "")
        if not template:
            continue
        source_values[template_name] = _read_item_cell(session, table_id, template, source_visual_row)

    # Preenche campos na ordem exata do VBS.
    for template_name in header_fields:
        template = tables.get(template_name, "")
        value = _normalize_item_header_value(template_name, source_values.get(template_name, ""))
        if not template or not value:
            continue
        field_id = table_id + template.format(row=target_visual_row)
        confirm = template_name in fields_with_enter
        try:
            _write_item_header_field(session, field_id, value, context=context, confirm=confirm)
        except Exception as exc:
            raise RuntimeError(
                f"Falha ao preparar novo item no quadro superior "
                f"(linha alvo {target_row}, campo {template_name}, valor '{value}'): {exc}"
            ) from exc
        wait_not_busy(session)
        wait(0.2)

    # Fecha popup wnd[1] que o SAP abre apos NAME1+Enter (exatamente como o VBS: wnd[1].sendVKey 0).
    wait_not_busy(session)
    wait(0.5)
    if element_exists(session, "wnd[1]"):
        try:
            session.findById("wnd[1]").sendVKey(0)
            wait_not_busy(session)
            wait(0.5)
        except Exception:
            pass

    # O SAP auto-navega para a aba Servicos — nao e necessario selecionar a aba.
    wait_not_busy(session)
    wait(0.8)
    tabs = profile.get("tabs", {})
    services_tab = tabs.get("servicesTab", [])
    if services_tab:
        try:
            select(session, services_tab, context=context)
        except Exception:
            pass

    return target_row


def _get_table_id_me22n(session, profile: dict) -> str:
    candidates = profile.get("tables", {}).get("servicesTable", [])
    return _first_existing(session, candidates)


def _service_field_id(table_id: str, template: str, row: int, template_name: str) -> str:
    if not template:
        raise RuntimeError(f"Layout ME22N sem {template_name} configurado.")
    return table_id + template.format(row=row)


def _set_service_field(
    session,
    table_id: str,
    template: str,
    template_name: str,
    row: int,
    value: str,
    context: RunContext,
) -> None:
    if not value:
        return
    field_id = _service_field_id(table_id, template, row, template_name)
    # Tenta ate 3 vezes com wait entre tentativas — sem mandar Enter (que abriria popups).
    last_exc = None
    for attempt in range(3):
        try:
            set_text(session, field_id, value, context=context)
            return
        except Exception as exc:
            last_exc = exc
            wait_not_busy(session)
            wait(0.3)
    display_value = str(value)
    if len(display_value) > 40:
        display_value = f"{display_value[:37]}..."
    raise RuntimeError(
        f"Falha ao preencher {template_name} na linha visual {row} "
        f"com valor '{display_value}' (len={len(str(value))}) "
        f"({field_id}): {last_exc}"
    ) from last_exc


def _scroll_service_table(session, table_id: str, position: int) -> None:
    try:
        table = session.findById(table_id)
        table.verticalScrollbar.position = position
        wait_not_busy(session)
    except Exception:
        pass


def _focus_service_field(
    session,
    table_id: str,
    template: str,
    row: int,
    template_name: str,
) -> None:
    field_id = _service_field_id(table_id, template, row, template_name)
    try:
        element = session.findById(field_id)
        element.setFocus()
        try:
            element.caretPosition = len(str(getattr(element, "Text", "") or ""))
        except Exception:
            pass
        wait_not_busy(session)
        wait(0.1)
    except Exception:
        pass


def _fill_service_page_me22n(
    session,
    table_id: str,
    page_rows: list[tuple[int, dict]],
    srvpos_default: str,
    sakto_default: str,
    profile: dict,
    context: RunContext,
) -> None:
    if not page_rows:
        return

    tables = profile.get("tables", {})
    srvpos_tmpl = tables.get("serviceSrvposTemplate", "")
    menge_tmpl = tables.get("serviceMengeTemplate", "")
    extsrvno_tmpl = tables.get("serviceExtsrvnoTemplate", "")
    tbtwr_tmpl = tables.get("serviceTbtvrTemplate", "")
    aufnr_tmpl = tables.get("serviceAufnrTemplate", "")

    # Replica a ordem do script manual do SAP:
    # SRVPOS -> MENGE -> TBTWR -> AUFNR -> EXTSRVNO -> Enter.
    for visual_row, linha in page_rows:
        _set_service_field(
            session,
            table_id,
            srvpos_tmpl,
            "serviceSrvposTemplate",
            visual_row,
            linha.get("srvpos") or srvpos_default,
            context,
        )

    for visual_row, linha in page_rows:
        _set_service_field(
            session,
            table_id,
            menge_tmpl,
            "serviceMengeTemplate",
            visual_row,
            linha.get("menge") or "1",
            context,
        )

    for visual_row, linha in page_rows:
        _set_service_field(
            session,
            table_id,
            tbtwr_tmpl,
            "serviceTbtvrTemplate",
            visual_row,
            linha.get("valor") or "",
            context,
        )

    for visual_row, linha in page_rows:
        _set_service_field(
            session,
            table_id,
            aufnr_tmpl,
            "serviceAufnrTemplate",
            visual_row,
            linha.get("aufnr") or "",
            context,
        )

    for visual_row, linha in page_rows:
        _set_service_field(
            session,
            table_id,
            extsrvno_tmpl,
            "serviceExtsrvnoTemplate",
            visual_row,
            linha.get("descricao") or "",
            context,
        )

    focus_row = next(
        (visual_row for visual_row, linha in page_rows if linha.get("aufnr")),
        page_rows[0][0],
    )
    focus_template = aufnr_tmpl or srvpos_tmpl
    focus_template_name = "serviceAufnrTemplate" if aufnr_tmpl else "serviceSrvposTemplate"
    if focus_template:
        _focus_service_field(session, table_id, focus_template, focus_row, focus_template_name)

    send_vkey(session, 0)
    _handle_account_popups(session, [linha for _, linha in page_rows], sakto_default, profile)


def _handle_account_popups(session, linhas: list[dict], sakto_default: str, profile: dict) -> None:
    """
    Apos preencher todas as linhas de servico e pressionar Enter,
    o SAP exibe popup de imputacao contabil para cada linha com AUFNR.
    Este metodo percorre os popups sequencialmente ate nao restar nenhum.
    """
    popup_sakto = profile.get("popups", {}).get("accountSakto", [])
    popup_ok = profile.get("popups", {}).get("accountOk", [])
    sakto_id = popup_sakto[0] if popup_sakto else "wnd[1]/usr/ctxtESKN-SAKTO"
    ok_candidates = popup_ok if popup_ok else ["wnd[1]/tbar[0]/btn[0]"]

    max_iterations = len(linhas) * 3 + 5
    iteration = 0
    processed = 0

    while iteration < max_iterations:
        iteration += 1
        wait(0.3)

        # Fecha wnd[2] se aparecer (popup de aviso/info) — usa btn[0].press() como o VBS
        if element_exists(session, "wnd[2]"):
            try:
                session.findById("wnd[2]/tbar[0]/btn[0]").press()
                wait_not_busy(session)
            except Exception:
                try:
                    session.findById("wnd[2]").sendVKey(0)
                    wait_not_busy(session)
                except Exception:
                    pass
            continue

        # Verifica se popup de imputacao (wnd[1] com SAKTO) esta aberto.
        # Algumas validacoes do SAP exibem um wnd[1] intermediario sem o campo SAKTO.
        if not element_exists(session, sakto_id):
            if element_exists(session, "wnd[1]"):
                _close_me22n_transient_popups(session)
                if not element_exists(session, "wnd[1]"):
                    continue
                if close_popup_ok(session):
                    wait_not_busy(session)
                    wait(0.15)
                    continue
                try:
                    session.findById("wnd[1]").sendVKey(0)
                    wait_not_busy(session)
                    wait(0.15)
                    continue
                except Exception:
                    pass
            break

        linha = linhas[processed] if processed < len(linhas) else {}
        sakto = linha.get("sakto") or sakto_default or ""

        try:
            session.findById(sakto_id).Text = sakto
            wait(0.15)
        except Exception:
            pass

        # Confirma popup
        ok_id = None
        for candidate in ok_candidates:
            if element_exists(session, candidate):
                ok_id = candidate
                break
        if ok_id:
            try:
                session.findById(ok_id).press()
                wait_not_busy(session)
            except Exception:
                pass
        else:
            try:
                session.findById("wnd[1]").sendVKey(0)
                wait_not_busy(session)
            except Exception:
                pass

        if processed < len(linhas):
            processed += 1


def _confirm_service_field(
    session,
    table_id: str,
    template: str,
    row: int,
    template_name: str,
) -> None:
    if not template:
        return
    _focus_service_field(session, table_id, template, row, template_name)
    send_vkey(session, 0)


def _service_chunk_position(start_abs_row: int, page_size: int = 10) -> tuple[int, int]:
    if start_abs_row <= 0:
        return 0, 0
    scroll_position = max(start_abs_row - 1, 0)
    start_visual_row = start_abs_row - scroll_position
    if start_visual_row >= page_size:
        return start_abs_row, 0
    return scroll_position, start_visual_row


def _build_service_chunk_rows(
    start_abs_row: int,
    remaining_linhas: list[dict],
    page_size: int = 10,
) -> tuple[int, list[tuple[int, dict]], int]:
    scroll_position, start_visual_row = _service_chunk_position(start_abs_row, page_size=page_size)
    capacity = max(page_size - start_visual_row, 1)
    chunk_linhas = remaining_linhas[:capacity]
    page_rows = [(start_visual_row + idx, linha) for idx, linha in enumerate(chunk_linhas)]
    return scroll_position, page_rows, len(chunk_linhas)


def _find_first_empty_service_row(session, table_id: str, srvpos_tmpl: str, page_size: int = 10) -> int:
    """
    Percorre a tabela de servicos e retorna o indice absoluto da primeira linha vazia (SRVPOS vazio).
    Garante modo append — nao sobrescreve linhas ja preenchidas.
    """
    if not srvpos_tmpl:
        return 0
    # Garante inicio do scroll
    _scroll_service_table(session, table_id, 0)
    wait(0.3)
    for page_start in range(0, 500, page_size):
        if page_start > 0:
            _scroll_service_table(session, table_id, page_start)
            wait(0.3)
        for visual_row in range(page_size):
            try:
                field_id = table_id + srvpos_tmpl.format(row=visual_row)
                el = session.findById(field_id)
                value = str(getattr(el, "Text", "") or "").strip()
                if not value:
                    return page_start + visual_row
            except Exception:
                return page_start + visual_row  # linha nao existe — fim da tabela
    return 0


def _activate_service_grid(session, table_id: str, srvpos_tmpl: str) -> None:
    """
    Posiciona o cursor na primeira celula do grid de servicos para que o SAP
    libere a edicao. Sem isso o SAP retorna SE029 ao tentar escrever nas celulas.
    Usa currentCellRow/currentCellColumn (equivalente a clicar na linha 10 da coluna
    'Linha' que o usuario faz manualmente antes de digitar).
    """
    try:
        table = session.findById(table_id)
        table.currentCellRow = 0
        table.currentCellColumn = 2  # coluna SRVPOS (Nº serviço)
        wait_not_busy(session)
        wait(0.8)
    except Exception:
        pass
    # Também tenta setFocus direto no campo SRVPOS[2,0] como fallback.
    if srvpos_tmpl:
        try:
            field_id = table_id + srvpos_tmpl.format(row=0)
            el = session.findById(field_id)
            el.setFocus()
            wait_not_busy(session)
            wait(0.5)
        except Exception:
            pass


def _fill_service_lines_me22n(
    session,
    linhas: list[dict],
    srvpos_default: str,
    sakto_default: str,
    profile: dict,
    context: RunContext,
) -> None:
    """
    Preenche linhas de servico na grade inferior (ME22N).
    NAO navega para a aba — o SAP ja esta na aba Servicos apos criar o item.

    Abordagem em lote (batch por pagina):
    - Preenche todos os campos de todas as linhas da pagina SEM pressionar Enter.
    - Pressiona Enter UMA vez no ultimo AUFNR da pagina.
    - Trata todos os popups de conta razao em sequencia.
    - Repete para a proxima pagina se houver mais linhas.
    """
    table_id = _get_table_id_me22n(session, profile)
    tables = profile.get("tables", {})
    srvpos_tmpl = tables.get("serviceSrvposTemplate", "")
    menge_tmpl = tables.get("serviceMengeTemplate", "")
    extsrvno_tmpl = tables.get("serviceExtsrvnoTemplate", "")
    tbtwr_tmpl = tables.get("serviceTbtvrTemplate", "")
    aufnr_tmpl = tables.get("serviceAufnrTemplate", "")
    page_size = 10

    first_empty = _find_first_empty_service_row(session, table_id, srvpos_tmpl, page_size)

    remaining = list(linhas)
    current_abs_row = first_empty

    while remaining:
        scroll_pos, start_visual_row = _service_chunk_position(current_abs_row, page_size=page_size)
        _scroll_service_table(session, table_id, scroll_pos)
        wait(0.3)
        table_id = _get_table_id_me22n(session, profile)
        _activate_service_grid(session, table_id, srvpos_tmpl)

        capacity = page_size - start_visual_row
        chunk = remaining[:capacity]
        last_visual_row = start_visual_row + len(chunk) - 1
        visual_rows = [start_visual_row + i for i in range(len(chunk))]

        # Preenche coluna por coluna para o chunk inteiro.
        # Isso garante que todos os lookups de SRVPOS sejam processados pelo SAP
        # antes de preencher os demais campos, evitando falhas por estado transitorio.

        # Col 2: todos os SRVPOS — aguarda SAP processar o lookup de cada um individualmente.
        for i, linha in enumerate(chunk):
            _set_service_field(session, table_id, srvpos_tmpl, "serviceSrvposTemplate",
                               visual_rows[i], linha.get("srvpos") or srvpos_default, context)
            wait_not_busy(session)
            wait(0.2)

        if srvpos_tmpl and visual_rows:
            _focus_service_field(
                session,
                table_id,
                srvpos_tmpl,
                visual_rows[-1],
                "serviceSrvposTemplate",
            )
            wait(0.2)

        # Col 4: todos os EXTSRVNO
        for i, linha in enumerate(chunk):
            _set_service_field(session, table_id, extsrvno_tmpl, "serviceExtsrvnoTemplate",
                               visual_rows[i], _normalize_service_external_text(linha.get("descricao")), context)

        # Col 5: todos os MENGE
        for i, linha in enumerate(chunk):
            _set_service_field(session, table_id, menge_tmpl, "serviceMengeTemplate",
                               visual_rows[i], linha.get("menge") or "1", context)

        # Col 7: todos os TBTWR
        for i, linha in enumerate(chunk):
            _set_service_field(session, table_id, tbtwr_tmpl, "serviceTbtvrTemplate",
                               visual_rows[i], linha.get("valor") or "", context)

        # Col 8: todos os AUFNR (ultimo campo — Enter sera dado aqui)
        for i, linha in enumerate(chunk):
            _set_service_field(session, table_id, aufnr_tmpl, "serviceAufnrTemplate",
                               visual_rows[i], linha.get("aufnr") or "", context)

        # Um unico Enter no AUFNR da ultima linha preenchida.
        if aufnr_tmpl:
            aufnr_id = _service_field_id(table_id, aufnr_tmpl, last_visual_row, "serviceAufnrTemplate")
            try:
                el = session.findById(aufnr_id)
                el.setFocus()
                try:
                    el.caretPosition = len(str(getattr(el, "Text", "") or ""))
                except Exception:
                    pass
                wait_not_busy(session)
                wait(0.1)
            except Exception:
                pass
        send_vkey(session, 0)
        wait_not_busy(session)
        wait(0.3)

        # wnd[2]: usa btn[0].press() — NAO sendVKey (diferenca critica do VBS)
        if element_exists(session, "wnd[2]"):
            try:
                session.findById("wnd[2]/tbar[0]/btn[0]").press()
                wait_not_busy(session)
                wait(0.3)
            except Exception:
                try:
                    session.findById("wnd[2]").sendVKey(0)
                    wait_not_busy(session)
                except Exception:
                    pass

        # Trata todos os popups de conta razao do chunk em sequencia.
        _handle_account_popups(session, chunk, sakto_default, profile)

        current_abs_row += len(chunk)
        remaining = remaining[len(chunk):]


def _set_tax_code(session, cod_imposto: str | None, profile: dict, context: RunContext) -> None:
    if not cod_imposto:
        return
    tabs = profile.get("tabs", {})
    tax_tab = tabs.get("taxTab", [])
    if not tax_tab:
        return
    select(session, tax_tab, context=context)
    tax_field = profile.get("fields", {}).get("taxCode", [])
    if tax_field:
        set_text(session, tax_field, cod_imposto, context=context)
        send_vkey(session, 0)


# ---------------------------------------------------------------------------
# Public API — ME23N
# ---------------------------------------------------------------------------

def alimentar_pedido_servicos(
    session,
    pedido: str,
    data_entrega: str | None,
    descricao_servico: str | None,
    ordens_aufnr: list[str],
    qtd_linhas: int | None,
    profile: dict,
    context: RunContext,
) -> str:
    ordens_validas = [value for value in ordens_aufnr if value]
    if not pedido:
        raise RuntimeError("Pedido vazio.")
    if not ordens_validas:
        raise RuntimeError(f"Pedido {pedido} sem ordens AUFNR validas.")
    qtd_alvo = qtd_linhas if qtd_linhas is not None else len(ordens_validas)
    if qtd_alvo < 1:
        raise RuntimeError("Qtd linhas deve ser inteiro >= 1.")
    if qtd_alvo > len(ordens_validas):
        raise RuntimeError(
            f"Pedido {pedido}: Qtd linhas ({qtd_alvo}) maior que ordens AUFNR informadas ({len(ordens_validas)})."
        )
    linhas_aufnr = ordens_validas[:qtd_alvo]
    _open_order_me23n(session, pedido, profile, context)
    _copy_first_item(session, profile, context)
    _set_delivery_date(session, data_entrega, profile, context)
    _fill_service_lines_me23n(session, linhas_aufnr, profile, context)
    save_button = profile.get("toolbar", {}).get("save", [])
    if save_button:
        wait_not_busy(session)
        _close_validation_popups(session)
        press(session, save_button, context=context)
    text, msg_type = read_statusbar(session)
    if msg_type == "E":
        raise RuntimeError(f"SAP retornou erro ao salvar: {text}")
    return text or "Pedido salvo com sucesso."


# ---------------------------------------------------------------------------
# Public API — ME22N
# ---------------------------------------------------------------------------

def alimentar_pedido_me22n(
    session,
    pedido: str,
    linhas: list[dict],
    srvpos_default: str,
    sakto_default: str,
    cod_imposto: str | None,
    profile: dict,
    context: RunContext,
    itens: list[dict] | None = None,
) -> str:
    """
    Preenche linhas de servico em um pedido existente via ME22N.

    Uso com item unico (backward compat):
      linhas = [{aufnr, valor, descricao, srvpos, menge, sakto}, ...]

    Uso com multiplos grupos (novo):
      itens = [{"item": "10", "linhas": [...]}, {"item": "20", "linhas": [...]}]

    Cada linha pode ter:
      - aufnr      : numero da ordem (AUFNR)
      - valor      : valor bruto da linha (TBTWR), ex: "5.761,71"
      - descricao  : descricao externa (EXTSRVNO), ex: "Loja Shopping"
      - srvpos     : numero do servico (override do default)
      - menge      : quantidade (default "1")
      - sakto      : conta GL para imputacao (override do default)
    """
    if not pedido:
        raise RuntimeError("Pedido vazio.")

    # Normaliza: se itens nao fornecido, usa linhas em um unico grupo.
    if itens:
        grupos = [g for g in itens if g.get("linhas")]
    else:
        linhas_validas = [l for l in linhas if l.get("aufnr") or l.get("valor")]
        if not linhas_validas:
            raise RuntimeError(f"Pedido {pedido} sem linhas validas.")
        grupos = [{"item": "10", "linhas": linhas_validas}]

    if not grupos:
        raise RuntimeError(f"Pedido {pedido} sem itens/linhas validos.")

    _open_order_me22n(session, pedido, profile, context)

    for grupo in grupos:
        linhas_grupo = grupo.get("linhas", [])
        if not linhas_grupo:
            continue
        # Cada grupo vira um novo item anexado ao pedido; nao usamos EBELP literal.
        _prepare_new_item_me22n(session, linhas_grupo, profile, context)
        wait_not_busy(session)
        wait(0.5)

        # SAP ja esta na aba Servicos apos criar o item — preenche diretamente.
        _fill_service_lines_me22n(session, linhas_grupo, srvpos_default, sakto_default, profile, context)
        _set_tax_code(session, cod_imposto, profile, context)
        wait_not_busy(session)
        wait(0.3)
        _close_me22n_transient_popups(session)

    save_button = profile.get("toolbar", {}).get("save", [])
    if save_button:
        wait_not_busy(session)
        _close_me22n_transient_popups(session)
        press(session, save_button, context=context)
    text, msg_type = read_statusbar(session)
    if msg_type == "E":
        raise RuntimeError(f"SAP retornou erro ao salvar pedido {pedido}: {text}")
    return text or "Pedido salvo com sucesso."


# ---------------------------------------------------------------------------
# Excel loaders
# ---------------------------------------------------------------------------

def load_lots_from_excel(path: str) -> list[dict]:
    """Formato antigo ME23N: PEDIDO, AUFNR, DATAENTREGA, DESCRICAO."""
    df = pd.read_excel(path)
    column_map = {normalize_column_name(column): column for column in df.columns}
    pedido_col = column_map.get("PEDIDO") or column_map.get("EBELN")
    aufnr_col = column_map.get("AUFNR") or column_map.get("ORDEM")
    if not pedido_col or not aufnr_col:
        raise ValueError("Colunas obrigatorias nao encontradas. Use PEDIDO e AUFNR.")
    data_col = column_map.get("DATAENTREGA") or column_map.get("DATA")
    desc_col = column_map.get("DESCRICAO") or column_map.get("DESCRICAOSERVICO")
    grouped: dict[str, dict] = {}
    for _, row in df.iterrows():
        pedido = as_text(row[pedido_col])
        aufnr = as_text(row[aufnr_col]).removesuffix(".0")
        if not pedido or not aufnr:
            continue
        lote = grouped.setdefault(
            pedido,
            {
                "pedido": pedido,
                "data_entrega": as_text(row[data_col]) if data_col else "",
                "descricao_servico": as_text(row[desc_col]) if desc_col else "",
                "ordens_aufnr": [],
            },
        )
        lote["ordens_aufnr"].append(aufnr)
    return list(grouped.values())


def load_me22n_from_excel(path: str) -> list[dict]:
    """
    Formato ME22N. Colunas esperadas:
      PEDIDO, AUFNR, VALOR, DESCRICAO, SRVPOS (opt), SAKTO (opt), MENGE (opt), IMPOSTO (opt)

    Retorna lista de lotes agrupados por PEDIDO:
      {pedido, srvpos_default, sakto_default, cod_imposto, linhas: [{aufnr, valor, descricao, srvpos, sakto, menge}]}
    """
    df = pd.read_excel(path)
    column_map = {normalize_column_name(col): col for col in df.columns}

    pedido_col = column_map.get("PEDIDO") or column_map.get("EBELN")
    aufnr_col = column_map.get("AUFNR") or column_map.get("ORDEM")
    if not pedido_col or not aufnr_col:
        raise ValueError("Colunas obrigatorias: PEDIDO e AUFNR.")

    valor_col = column_map.get("VALOR") or column_map.get("TBTWR")
    desc_col = column_map.get("DESCRICAO") or column_map.get("EXTSRVNO") or column_map.get("DESCRICAOSERVICO")
    srvpos_col = column_map.get("SRVPOS") or column_map.get("SERVICO")
    sakto_col = column_map.get("SAKTO") or column_map.get("CONTA")
    menge_col = column_map.get("MENGE") or column_map.get("QUANTIDADE")
    imposto_col = column_map.get("IMPOSTO") or column_map.get("CODIMPOSTO") or column_map.get("MWSKZ")

    grouped: dict[str, dict] = {}
    for _, row in df.iterrows():
        pedido = as_text(row[pedido_col])
        aufnr = as_text(row[aufnr_col]).removesuffix(".0")
        if not pedido or not aufnr:
            continue
        lote = grouped.setdefault(
            pedido,
            {
                "pedido": pedido,
                "srvpos_default": as_text(row[srvpos_col]) if srvpos_col else "",
                "sakto_default": as_text(row[sakto_col]) if sakto_col else "",
                "cod_imposto": as_text(row[imposto_col]) if imposto_col else "",
                "linhas": [],
            },
        )
        linha: dict = {"aufnr": aufnr}
        if valor_col:
            linha["valor"] = as_text(row[valor_col])
        if desc_col:
            linha["descricao"] = as_text(row[desc_col])
        if srvpos_col:
            linha["srvpos"] = as_text(row[srvpos_col])
        if sakto_col:
            linha["sakto"] = as_text(row[sakto_col])
        if menge_col:
            linha["menge"] = as_text(row[menge_col])
        lote["linhas"].append(linha)
    return list(grouped.values())


# ---------------------------------------------------------------------------
# run_job — ME23N (original, retrocompativel)
# ---------------------------------------------------------------------------

def run_job(input_data, options, callbacks) -> RobotResult:
    pythoncom.CoInitialize()
    run_id = timestamp_id()
    output_dir = ensure_dir(Path(options.get("output_dir") or run_output_dir("ME23N-Alimentacao", run_id=run_id)))
    log_path = output_dir / "run.log"
    logger = ExecutionLogger(log_path, callback=callbacks.get("log"))
    context = RunContext(logger=logger, progress_callback=callbacks.get("progress"), cancel_callback=callbacks.get("is_cancelled"))
    result = RobotResult.new(robot="ME23N-ALIMENTACAO", run_id=run_id)
    lots = input_data.get("lotes", [])
    payload_path = output_dir / "payload.json"
    payload_path.write_text(json.dumps({"lotes": lots}, indent=2, ensure_ascii=False), encoding="utf-8")
    context.add_artifact(RunArtifact.from_path("payload", payload_path, "payload"))

    try:
        _profile_name, profile = load_me23n_profile(options.get("layout_profile"))
        session, session_meta = resolve_session(
            session_ref=options.get("session_ref"),
            allow_manual_login=bool(options.get("allow_manual_login", True)),
            chooser=options.get("session_chooser"),
        )
        result.session_meta = session_meta
        results = []
        for index, lote in enumerate(lots, start=1):
            if context.is_cancelled():
                result.status = "cancelled"
                break
            context.progress("me23n-alimentacao", index, len(lots))
            try:
                message = alimentar_pedido_servicos(
                    session,
                    pedido=lote.get("pedido", ""),
                    data_entrega=lote.get("data_entrega"),
                    descricao_servico=lote.get("descricao_servico"),
                    ordens_aufnr=lote.get("ordens_aufnr", []),
                    qtd_linhas=lote.get("qtd_linhas"),
                    profile=profile,
                    context=context,
                )
                results.append({"pedido": lote.get("pedido", ""), "success": True, "message": message})
            except Exception as exc:
                error_message = str(exc)
                results.append({"pedido": lote.get("pedido", ""), "success": False, "message": error_message})
                popup = dump_popup(session)
                if popup:
                    popup_path = output_dir / f"popup-{lote.get('pedido', index)}.json"
                    popup_path.write_text(json.dumps(popup, indent=2, ensure_ascii=False), encoding="utf-8")
                    context.add_artifact(RunArtifact.from_path(f"popup-{index}", popup_path, "popup_dump"))
                screenshot_path = output_dir / f"erro-{lote.get('pedido', index)}.png"
                capture_sap_window(session, screenshot_path)
                context.add_artifact(RunArtifact.from_path(f"screenshot-{index}", screenshot_path, "screenshot"))
                context.error(error_message)
        ok_count = sum(1 for item in results if item["success"])
        fail_count = len(results) - ok_count
        if fail_count and result.status != "cancelled":
            result.status = "warning"
        result.business_result = {"results": results, "successCount": ok_count, "failCount": fail_count}
        status_text, status_type = read_statusbar(session)
        result.status_bar_text = status_text
        result.status_bar_type = status_type
    except Exception as exc:
        result.status = "error"
        context.error(str(exc))
    finally:
        result.errors = context.errors
        result.messages = [item.to_dict() for item in context.messages]
        result.artifacts = [item.to_dict() for item in context.artifacts]
        result.finalize()
        result_path = output_dir / "result.json"
        result_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        pythoncom.CoUninitialize()
    return result


# ---------------------------------------------------------------------------
# run_job_me22n — ME22N
# ---------------------------------------------------------------------------

def run_job_me22n(input_data, options, callbacks) -> RobotResult:
    pythoncom.CoInitialize()
    run_id = timestamp_id()
    output_dir = ensure_dir(Path(options.get("output_dir") or run_output_dir("ME22N-Alimentacao", run_id=run_id)))
    log_path = output_dir / "run.log"
    logger = ExecutionLogger(log_path, callback=callbacks.get("log"))
    context = RunContext(logger=logger, progress_callback=callbacks.get("progress"), cancel_callback=callbacks.get("is_cancelled"))
    result = RobotResult.new(robot="ME22N-ALIMENTACAO", run_id=run_id)
    lotes = input_data.get("lotes", [])
    payload_path = output_dir / "payload.json"
    payload_path.write_text(json.dumps({"lotes": lotes}, indent=2, ensure_ascii=False), encoding="utf-8")
    context.add_artifact(RunArtifact.from_path("payload", payload_path, "payload"))

    try:
        _profile_name, profile = load_me22n_profile(options.get("layout_profile"))
        session, session_meta = resolve_session(
            session_ref=options.get("session_ref"),
            allow_manual_login=bool(options.get("allow_manual_login", True)),
            chooser=options.get("session_chooser"),
        )
        result.session_meta = session_meta
        results = []
        for index, lote in enumerate(lotes, start=1):
            if context.is_cancelled():
                result.status = "cancelled"
                break
            context.progress("me22n-alimentacao", index, len(lotes))
            try:
                message = alimentar_pedido_me22n(
                    session,
                    pedido=lote.get("pedido", ""),
                    linhas=lote.get("linhas", []),
                    itens=lote.get("itens"),
                    srvpos_default=lote.get("srvpos_default", ""),
                    sakto_default=lote.get("sakto_default", ""),
                    cod_imposto=lote.get("cod_imposto"),
                    profile=profile,
                    context=context,
                )
                results.append({"pedido": lote.get("pedido", ""), "success": True, "message": message})
            except Exception as exc:
                error_message = str(exc)
                results.append({"pedido": lote.get("pedido", ""), "success": False, "message": error_message})
                popup = dump_popup(session)
                if popup:
                    popup_path = output_dir / f"popup-{lote.get('pedido', index)}.json"
                    popup_path.write_text(json.dumps(popup, indent=2, ensure_ascii=False), encoding="utf-8")
                    context.add_artifact(RunArtifact.from_path(f"popup-{index}", popup_path, "popup_dump"))
                screenshot_path = output_dir / f"erro-{lote.get('pedido', index)}.png"
                capture_sap_window(session, screenshot_path)
                context.add_artifact(RunArtifact.from_path(f"screenshot-{index}", screenshot_path, "screenshot"))
                context.error(error_message)
        ok_count = sum(1 for item in results if item["success"])
        fail_count = len(results) - ok_count
        if fail_count and result.status != "cancelled":
            result.status = "warning"
        result.business_result = {"results": results, "successCount": ok_count, "failCount": fail_count}
        status_text, status_type = read_statusbar(session)
        result.status_bar_text = status_text
        result.status_bar_type = status_type
    except Exception as exc:
        result.status = "error"
        context.error(str(exc))
    finally:
        result.errors = context.errors
        result.messages = [item.to_dict() for item in context.messages]
        result.artifacts = [item.to_dict() for item in context.artifacts]
        result.finalize()
        result_path = output_dir / "result.json"
        result_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        pythoncom.CoUninitialize()
    return result
