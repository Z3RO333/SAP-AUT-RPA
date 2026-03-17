from __future__ import annotations

from decimal import Decimal

from core.common.layout_maps import field_candidates
from core.common.run_context import RunContext
from core.common.sap_actions import element_exists, press, select, send_vkey, set_text, tcode
from core.common.sap_popups import close_popup_ok
from core.common.sap_status import read_statusbar
from core.common.sap_wait import wait_not_busy

from .models import PurchaseOrderItem, PurchaseOrderPayload, PurchaseOrderServiceLine
from .status_parser import parse_purchase_order_number


class Me21nLayoutError(RuntimeError):
    """Raised when the ME21N layout map is incomplete for the requested action."""


def _format_sap_decimal(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized.replace(".", ",")


def _capture_status(context: RunContext, session, stage: str, details: dict | None = None) -> tuple[str, str]:
    text, msg_type = read_statusbar(session)
    if text or msg_type:
        level_map = {
            "S": "success",
            "W": "warning",
            "E": "error",
            "A": "abort",
            "I": "info",
        }
        context.add_message(level_map.get(msg_type, "info"), text=text, code=msg_type, details={"stage": stage, **(details or {})})
    return text, msg_type


def _window_exists(session, window_id: str) -> bool:
    try:
        session.findById(window_id)
        return True
    except Exception:
        return False


def _send_vkey_to_window(session, window_id: str, key: int) -> None:
    session.findById(window_id).sendVKey(key)
    wait_not_busy(session)


def _close_value_help_popup(
    session,
    context: RunContext,
    stage: str,
    details: dict | None = None,
    max_attempts: int = 3,
) -> None:
    attempts = max(1, int(max_attempts or 1))
    for attempt in range(1, attempts + 1):
        if not _window_exists(session, "wnd[1]"):
            return
        attempt_details = {**(details or {}), "attempt": attempt}
        context.last_stage = stage
        if close_popup_ok(session):
            wait_not_busy(session)
            _capture_status(context, session, stage, {**attempt_details, "action": "close_popup_ok"})
            continue
        _send_vkey_to_window(session, "wnd[1]", 0)
        _capture_status(context, session, stage, {**attempt_details, "action": "wnd1-enter"})
    if _window_exists(session, "wnd[1]"):
        raise RuntimeError(
            f"Popup nao resolvido no estagio {stage}. "
            "Revise o valor de grupo_mercadoria; a ajuda de pesquisa retornou multiplas opcoes."
        )


def _required_candidates(profile: dict, section: str, field_name: str, required: bool = True) -> list[str]:
    candidates = field_candidates(profile, section, field_name)
    if required and not candidates:
        raise Me21nLayoutError(f"Layout ME21N sem mapeamento para {section}.{field_name}")
    return candidates


def _formatted_candidates(profile: dict, section: str, field_name: str, **formats) -> list[str]:
    candidates = field_candidates(profile, section, field_name)
    formatted: list[str] = []
    for candidate in candidates:
        try:
            formatted.append(candidate.format(**formats))
        except Exception:
            formatted.append(candidate)
    return formatted


def _first_existing_candidate(session, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if element_exists(session, candidate):
            return candidate
    return None


def _set_text_and_confirm(
    session,
    candidates: list[str],
    value: str,
    context: RunContext,
    stage: str,
    details: dict | None = None,
    confirm: bool = True,
) -> None:
    if value in (None, ""):
        return
    context.last_stage = stage
    set_text(session, candidates, value, context=context)
    if confirm:
        send_vkey(session, 0)
        _capture_status(context, session, stage, details)


def _press_existing_buttons(session, candidates: list[str], context: RunContext, stage: str) -> None:
    for candidate in candidates:
        if element_exists(session, candidate):
            context.last_stage = stage
            press(session, candidate, context=context)


def _get_service_table_path(profile: dict) -> str | None:
    candidates = field_candidates(profile, "serviceLines", "serviceNumber")
    if not candidates:
        return None
    template = candidates[0]
    idx = template.rfind("/tbl")
    if idx == -1:
        return None
    rest = template[idx + 1:]
    end_idx = rest.find("/")
    if end_idx == -1:
        return None
    return template[: idx + 1] + rest[:end_idx]


def _scroll_service_table_to(session, table_path: str, line_index: int) -> int:
    """Rola o table control para que line_index fique visível. Retorna o índice visual."""
    try:
        table = session.findById(table_path)
        visible_count = int(table.visibleRowCount or 0) or 10
        first_visible = (line_index // visible_count) * visible_count
        if int(table.firstVisibleRow) != first_visible:
            table.firstVisibleRow = first_visible
            wait_not_busy(session)
        return line_index - first_visible
    except Exception:
        return line_index


def _focus_item_row(session, profile: dict, row_index: int) -> None:
    probe_fields = ("shortText", "itemCategory", "accountAssignmentCategory", "materialGroup", "plantOrCenter")
    for logical_name in probe_fields:
        for candidate in _formatted_candidates(profile, "itemOverview", logical_name, row=row_index):
            if not element_exists(session, candidate):
                continue
            try:
                session.findById(candidate).setFocus()
                return
            except Exception:
                continue


def _tax_code_input_sequence(tax_code: str | None, profile: dict) -> list[str]:
    target = (tax_code or "").strip().upper()
    if not target:
        return []
    capabilities = profile.get("capabilities", {}) if isinstance(profile, dict) else {}
    constraints = profile.get("constraints", {}) if isinstance(profile, dict) else {}
    requires_toggle = bool(capabilities.get("requiresTaxCodeToggle"))
    toggle_values = constraints.get("taxCodeToggleValues", [])
    allowed_toggle_values = [str(value).strip().upper() for value in toggle_values if str(value).strip()] if isinstance(toggle_values, list) else []
    if not requires_toggle or target not in allowed_toggle_values:
        return [target]
    prime_code = next((code for code in allowed_toggle_values if code != target), None)
    if not prime_code:
        return [target]
    return [prime_code, target]


def _has_any_gross_price(payload: PurchaseOrderPayload) -> bool:
    return any(line.preco_bruto is not None for item in payload.items for line in item.service_lines)


def _status_requires_header_org_data(status_text: str, status_type: str) -> bool:
    if status_type != "E":
        return False
    normalized = (status_text or "").strip().lower()
    if not normalized:
        return False
    return any(
        token in normalized
        for token in (
            "org.compras",
            "org compras",
            "grupo compras",
            "grupo de compras",
            "empresa",
            "company code",
            "purchasing organization",
            "purchasing group",
        )
    )


def validate_layout_for_payload(payload: PurchaseOrderPayload, profile: dict, dry_run: bool) -> None:
    _required_candidates(profile, "header", "supplierTop")
    _required_candidates(profile, "header", "paymentTerms")
    _required_candidates(profile, "header", "purchOrg")
    _required_candidates(profile, "header", "purchGroup")
    _required_candidates(profile, "header", "companyCode")
    _required_candidates(profile, "headerTabs", "commercial")
    _required_candidates(profile, "headerTabs", "orgData")
    _required_candidates(profile, "itemOverview", "accountAssignmentCategory")
    _required_candidates(profile, "itemOverview", "itemCategory")
    _required_candidates(profile, "itemOverview", "shortText")
    _required_candidates(profile, "itemOverview", "materialGroup")
    _required_candidates(profile, "itemDetail", "serviceTab")
    _required_candidates(profile, "serviceLines", "serviceNumber")
    _required_candidates(profile, "serviceLines", "quantity")
    if _has_any_gross_price(payload):
        _required_candidates(profile, "serviceLines", "grossPrice")

    if any(item.plant_or_center for item in payload.items):
        _required_candidates(profile, "itemOverview", "plantOrCenter")
    if any((item.conta_razao_default or any(line.conta_razao for line in item.service_lines)) for item in payload.items):
        _required_candidates(profile, "accountPopup", "glAccountField")
    if any(item.categoria_classif == "F" for item in payload.items):
        direct_order = field_candidates(profile, "serviceLines", "order")
        popup_order = field_candidates(profile, "accountPopup", "orderField")
        if not direct_order and not popup_order:
            raise Me21nLayoutError("Layout ME21N sem mapeamento para serviceLines.order ou accountPopup.orderField")
    if any(item.categoria_classif == "K" for item in payload.items):
        _required_candidates(profile, "accountPopup", "costCenterField")
    if any(item.tax_code for item in payload.items):
        _required_candidates(profile, "itemDetail", "taxTab")
        _required_candidates(profile, "itemFields", "taxCode")
    if any(item.observacao_item for item in payload.items):
        _required_candidates(profile, "itemDetail", "textTab")
        _required_candidates(profile, "itemFields", "observation")
    if not dry_run:
        _required_candidates(profile, "toolbar", "save")


def _prepare_me21n_screen(session, profile: dict, context: RunContext) -> None:
    tcode(session, "ME21N")
    session.findById("wnd[0]").maximize()
    wait_not_busy(session, timeout=60)
    _press_existing_buttons(session, field_candidates(profile, "preNavigation", "expandHeaderButtons"), context, "me21n-prepare-header")
    _press_existing_buttons(session, field_candidates(profile, "preNavigation", "expandItemButtons"), context, "me21n-prepare-item")


def _fill_header(session, payload: PurchaseOrderPayload, profile: dict, context: RunContext) -> None:
    header = payload.header
    _set_text_and_confirm(session, _required_candidates(profile, "header", "supplierTop"), header.fornecedor, context, "me21n-header-fornecedor")

    select(session, _required_candidates(profile, "headerTabs", "commercial"), context=context)
    _set_text_and_confirm(session, _required_candidates(profile, "header", "paymentTerms"), header.condicao_pagamento, context, "me21n-header-payment")
    payment_status_text, payment_status_type = _capture_status(context, session, "me21n-header-payment-postcheck")
    if _status_requires_header_org_data(payment_status_text, payment_status_type):
        select(session, _required_candidates(profile, "headerTabs", "orgData"), context=context)
        _set_text_and_confirm(session, _required_candidates(profile, "header", "purchOrg"), header.org_compras, context, "me21n-header-org")
        _set_text_and_confirm(session, _required_candidates(profile, "header", "purchGroup"), header.grupo_compras, context, "me21n-header-group")
        _set_text_and_confirm(session, _required_candidates(profile, "header", "companyCode"), header.empresa, context, "me21n-header-company")
        # Algumas variantes voltam a exigir confirmacao da condicao de pagamento apos org data.
        select(session, _required_candidates(profile, "headerTabs", "commercial"), context=context)
        _set_text_and_confirm(session, _required_candidates(profile, "header", "paymentTerms"), header.condicao_pagamento, context, "me21n-header-payment-retry")

    if header.moeda and field_candidates(profile, "header", "currency"):
        _set_text_and_confirm(session, field_candidates(profile, "header", "currency"), header.moeda, context, "me21n-header-currency")
    if header.incoterms and field_candidates(profile, "header", "incoterms"):
        _set_text_and_confirm(session, field_candidates(profile, "header", "incoterms"), header.incoterms, context, "me21n-header-incoterms")
    if header.texto_cabecalho and field_candidates(profile, "header", "headerText"):
        _set_text_and_confirm(session, field_candidates(profile, "header", "headerText"), header.texto_cabecalho, context, "me21n-header-text")


def _fill_item_overview_row(session, item: PurchaseOrderItem, profile: dict, row_index: int, context: RunContext) -> None:
    details = {"itemRef": item.item_ref, "row": row_index}
    _set_text_and_confirm(
        session,
        _formatted_candidates(profile, "itemOverview", "accountAssignmentCategory", row=row_index),
        item.categoria_classif,
        context,
        "me21n-item-knttp",
        details,
    )
    _set_text_and_confirm(
        session,
        _formatted_candidates(profile, "itemOverview", "itemCategory", row=row_index),
        item.categoria_item,
        context,
        "me21n-item-epstp",
        details,
    )
    _set_text_and_confirm(
        session,
        _formatted_candidates(profile, "itemOverview", "shortText", row=row_index),
        item.texto_livre,
        context,
        "me21n-item-text",
        details,
    )
    if item.plant_or_center and field_candidates(profile, "itemOverview", "plantOrCenter"):
        _set_text_and_confirm(
            session,
            _formatted_candidates(profile, "itemOverview", "plantOrCenter", row=row_index),
            item.plant_or_center,
            context,
            "me21n-item-plant",
            details,
        )
    _set_text_and_confirm(
        session,
        _formatted_candidates(profile, "itemOverview", "materialGroup", row=row_index),
        item.grupo_mercadoria,
        context,
        "me21n-item-material-group",
        details,
    )
    if item.grupo_mercadoria:
        _close_value_help_popup(
            session,
            context,
            "me21n-item-material-group-popup",
            details=details,
            max_attempts=3,
        )


def _open_item_detail(session, item: PurchaseOrderItem, profile: dict, row_index: int, tab_name: str, context: RunContext) -> None:
    _focus_item_row(session, profile, row_index)
    select(session, _required_candidates(profile, "itemDetail", tab_name), context=context)
    _capture_status(context, session, f"me21n-open-{tab_name}", {"itemRef": item.item_ref, "row": row_index})


def _fill_service_line_reference(
    session,
    item: PurchaseOrderItem,
    service_line: PurchaseOrderServiceLine,
    profile: dict,
    line_index: int,
    context: RunContext,
    visual_row: int | None = None,
) -> bool:
    row = visual_row if visual_row is not None else line_index
    details = {"itemRef": item.item_ref, "lineRef": service_line.line_ref, "row": line_index}
    if item.categoria_classif != "F" or not service_line.ordem:
        send_vkey(session, 0)
        _capture_status(context, session, "me21n-line-reference-trigger", details)
        return False

    direct_candidates = _formatted_candidates(profile, "serviceLines", "order", row=row)
    direct_existing = _first_existing_candidate(session, direct_candidates)
    if direct_existing:
        _set_text_and_confirm(
            session,
            [direct_existing],
            service_line.ordem,
            context,
            "me21n-line-order-grid",
            details,
        )
        return True

    send_vkey(session, 0)
    _capture_status(context, session, "me21n-line-reference-trigger", details)
    return False


def _handle_account_assignment_popup(
    session,
    item: PurchaseOrderItem,
    service_line: PurchaseOrderServiceLine,
    profile: dict,
    context: RunContext,
    reference_already_filled: bool,
) -> None:
    popup_ok_candidates = field_candidates(profile, "accountPopup", "prePopupOk")
    confirm_candidates = field_candidates(profile, "accountPopup", "confirm")
    details = {"itemRef": item.item_ref, "lineRef": service_line.line_ref}

    if _window_exists(session, "wnd[2]"):
        if popup_ok_candidates:
            press(session, popup_ok_candidates, context=context)
        else:
            _send_vkey_to_window(session, "wnd[2]", 0)

    if not _window_exists(session, "wnd[1]"):
        raise RuntimeError("Popup de classificacao contabil nao apareceu para a linha de servico.")

    if service_line.conta_razao:
        _set_text_and_confirm(
            session,
            _required_candidates(profile, "accountPopup", "glAccountField"),
            service_line.conta_razao,
            context,
            "me21n-line-gl-account",
            details,
            confirm=False,
        )

    if item.categoria_classif == "F" and service_line.ordem and not reference_already_filled:
        order_popup_candidates = field_candidates(profile, "accountPopup", "orderField")
        if not order_popup_candidates:
            raise Me21nLayoutError("Layout ME21N sem mapeamento para accountPopup.orderField")
        _set_text_and_confirm(
            session,
            order_popup_candidates,
            service_line.ordem,
            context,
            "me21n-line-order-popup",
            details,
            confirm=False,
        )

    if item.categoria_classif == "K" and service_line.centro_custo:
        _set_text_and_confirm(
            session,
            _required_candidates(profile, "accountPopup", "costCenterField"),
            service_line.centro_custo,
            context,
            "me21n-line-cost-center-popup",
            details,
            confirm=False,
        )

    if confirm_candidates:
        press(session, confirm_candidates, context=context)
    else:
        _send_vkey_to_window(session, "wnd[1]", 0)
    _capture_status(context, session, "me21n-line-account-popup-complete", details)


def _fill_service_lines(session, item: PurchaseOrderItem, profile: dict, context: RunContext) -> None:
    table_path = _get_service_table_path(profile)
    total_lines = len(item.service_lines)
    for line_index, service_line in enumerate(item.service_lines):
        context.progress("me21n-service-lines", line_index + 1, total_lines)
        visual_row = _scroll_service_table_to(session, table_path, line_index) if table_path else line_index
        details = {"itemRef": item.item_ref, "lineRef": service_line.line_ref, "row": line_index, "visualRow": visual_row}
        _set_text_and_confirm(
            session,
            _formatted_candidates(profile, "serviceLines", "serviceNumber", row=visual_row),
            service_line.numero_servico,
            context,
            "me21n-line-service-number",
            details,
        )
        # Se o numero de servico abrir popup de selecao (lista de resultados), confirmar o primeiro com Enter
        if _window_exists(session, "wnd[1]"):
            _send_vkey_to_window(session, "wnd[1]", 0)
        _set_text_and_confirm(
            session,
            _formatted_candidates(profile, "serviceLines", "quantity", row=visual_row),
            _format_sap_decimal(service_line.quantidade),
            context,
            "me21n-line-quantity",
            details,
        )
        if service_line.preco_bruto is not None:
            _set_text_and_confirm(
                session,
                _formatted_candidates(profile, "serviceLines", "grossPrice", row=visual_row),
                _format_sap_decimal(service_line.preco_bruto),
                context,
                "me21n-line-gross-price",
                details,
                confirm=False,
            )
        if service_line.descricao_externa and field_candidates(profile, "serviceLines", "externalText"):
            _set_text_and_confirm(
                session,
                _formatted_candidates(profile, "serviceLines", "externalText", row=visual_row),
                service_line.descricao_externa,
                context,
                "me21n-line-text",
                details,
                confirm=False,
            )

        reference_already_filled = _fill_service_line_reference(session, item, service_line, profile, line_index, context, visual_row=visual_row)
        _handle_account_assignment_popup(session, item, service_line, profile, context, reference_already_filled)
        _capture_status(context, session, "me21n-line-complete", details)


def _fill_item_tax(session, item: PurchaseOrderItem, profile: dict, row_index: int, context: RunContext) -> None:
    if not item.tax_code or not field_candidates(profile, "itemFields", "taxCode"):
        return
    _open_item_detail(session, item, profile, row_index, "taxTab", context)
    tax_candidates = _required_candidates(profile, "itemFields", "taxCode")
    tax_steps = _tax_code_input_sequence(item.tax_code, profile)
    for step_index, tax_value in enumerate(tax_steps):
        stage = "me21n-item-tax-final" if step_index == len(tax_steps) - 1 else "me21n-item-tax-prime"
        _set_text_and_confirm(
            session,
            tax_candidates,
            tax_value,
            context,
            stage,
            {"itemRef": item.item_ref, "row": row_index, "taxCodeStep": step_index + 1, "taxCodeValue": tax_value},
        )


def _fill_item_observation(session, item: PurchaseOrderItem, profile: dict, row_index: int, context: RunContext) -> None:
    if not item.observacao_item or not field_candidates(profile, "itemFields", "observation"):
        return
    if not field_candidates(profile, "itemDetail", "textTab"):
        raise Me21nLayoutError("Layout ME21N sem mapeamento para itemDetail.textTab")
    _open_item_detail(session, item, profile, row_index, "textTab", context)
    _set_text_and_confirm(
        session,
        _required_candidates(profile, "itemFields", "observation"),
        item.observacao_item,
        context,
        "me21n-item-observation",
        {"itemRef": item.item_ref, "row": row_index},
        confirm=False,
    )


def _save_or_validate(session, profile: dict, dry_run: bool, context: RunContext) -> dict:
    if dry_run:
        validation_button = field_candidates(profile, "validationActions", "check")
        if validation_button:
            press(session, validation_button, context=context)
        status_text, status_type = _capture_status(context, session, "me21n-dry-run")
        return {"created": False, "poNumber": None, "statusText": status_text, "statusType": status_type}

    press(session, _required_candidates(profile, "toolbar", "save"), context=context)
    if _window_exists(session, "wnd[1]"):
        confirm_candidates = field_candidates(profile, "popupPolicies", "saveConfirmationOption2")
        if confirm_candidates:
            press(session, confirm_candidates, context=context)
        else:
            raise Me21nLayoutError("Popup de salvamento apareceu sem mapeamento popupPolicies.saveConfirmationOption2")
    status_text, status_type = _capture_status(context, session, "me21n-save")
    po_number = parse_purchase_order_number(status_text, status_type)
    if status_type == "E":
        raise RuntimeError(status_text or "SAP retornou erro ao salvar o pedido.")
    return {"created": bool(po_number), "poNumber": po_number, "statusText": status_text, "statusType": status_type}


def execute_purchase_order(session, payload: PurchaseOrderPayload, profile: dict, dry_run: bool, context: RunContext) -> dict:
    validate_layout_for_payload(payload, profile, dry_run=dry_run)
    _prepare_me21n_screen(session, profile, context)
    context.log("ME21N aberta e preparada.")
    _fill_header(session, payload, profile, context)

    for row_index, item in enumerate(payload.items):
        if context.is_cancelled():
            raise RuntimeError("Execucao cancelada pelo usuario.")
        context.progress("me21n-items", row_index + 1, len(payload.items))
        _fill_item_overview_row(session, item, profile, row_index, context)
        _open_item_detail(session, item, profile, row_index, "serviceTab", context)
        _fill_service_lines(session, item, profile, context)
        _fill_item_tax(session, item, profile, row_index, context)
        _fill_item_observation(session, item, profile, row_index, context)

    return _save_or_validate(session, profile, dry_run, context)
