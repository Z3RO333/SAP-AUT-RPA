from __future__ import annotations

import json
import time
import unicodedata
from pathlib import Path

import pythoncom

from core.common.layout_maps import load_layout_map, resolve_profile
from core.common.logging import ExecutionLogger
from core.common.models import RobotResult, RunArtifact
from core.common.run_context import RunContext
from core.common.runtime import ensure_dir, run_output_dir, timestamp_id
from core.common.sap_actions import first_existing, press, send_vkey, set_text, tcode
from core.common.sap_popups import close_popup_ok, dump_popup, popup_exists
from core.common.sap_session import resolve_session
from core.common.sap_status import read_statusbar
from core.common.sap_tables import read_grid_cell
from core.common.sap_wait import wait, wait_not_busy
from core.common.screenshots import capture_sap_window


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------

def load_zme62_profile(profile_name: str | None = None) -> tuple[str, dict]:
    layout_map = load_layout_map("ZME62")
    return resolve_profile(layout_map, profile_name)


def allowed_responses(profile_name: str | None = None) -> list[str]:
    _name, profile = load_zme62_profile(profile_name)
    return list(profile.get("allowedResponses", []))


def _question_response_options_from_profile(profile: dict) -> list[list[str]]:
    question_values = profile.get("questionResponses", [])
    if question_values:
        return [[str(item) for item in group] for group in question_values]

    allowed = list(profile.get("allowedResponses", []))
    if not allowed:
        return []
    return [allowed[:] for _ in range(4)]


def question_response_options(profile_name: str | None = None) -> list[list[str]]:
    _name, profile = load_zme62_profile(profile_name)
    return _question_response_options_from_profile(profile)


# ---------------------------------------------------------------------------
# Normalization and validation
# ---------------------------------------------------------------------------

def normalize_response(value: str) -> str:
    """Normalize a response value for comparison only (not for SAP submission)."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.upper().split())


def validate_responses(respostas: list[str], allowed: list[str]) -> list[str]:
    """Return list of invalid response values (using normalized comparison)."""
    normalized_allowed = {normalize_response(r) for r in allowed}
    return [r for r in respostas if normalize_response(r) not in normalized_allowed]


def validate_responses_by_question(respostas: list[str], question_options: list[list[str]]) -> list[str]:
    invalid: list[str] = []
    for index, resposta in enumerate(respostas):
        if index >= len(question_options):
            invalid.append(f"Pergunta {index + 1}: '{resposta}'")
            continue
        allowed = {normalize_response(item) for item in question_options[index]}
        if index == 0:
            allowed.add("SIM")
        elif index >= 1:
            allowed.add("TALVEZ")
        if normalize_response(resposta) not in allowed:
            invalid.append(f"Pergunta {index + 1}: '{resposta}'")
    return invalid


def _safe_getattr(obj, name: str, default: str = "") -> str:
    try:
        value = getattr(obj, name)
    except Exception:
        return default
    if value is None:
        return default
    return str(value)


def _press_candidates(
    session,
    element_ids: str | list[str],
    context: RunContext | None = None,
    *,
    timeout: float = 4.0,
) -> str:
    ids = [str(element_ids)] if isinstance(element_ids, str) else [str(item) for item in element_ids]
    element, resolved_id = first_existing(session, ids, timeout=timeout)
    if context:
        context.track_field(context.last_stage or "sap", resolved_id)
    element.press()
    wait_not_busy(session)
    return resolved_id


def _toolbar_buttons_summary(session, toolbar_ids: list[str]) -> list[str]:
    summaries: list[str] = []
    for toolbar_id in toolbar_ids:
        try:
            toolbar = session.findById(toolbar_id)
            count = int(_safe_getattr(toolbar.Children, "Count", "0") or "0")
        except Exception:
            continue
        for index in range(count):
            try:
                button = toolbar.Children(index)
            except Exception:
                continue
            if _safe_getattr(button, "Type") != "GuiButton":
                continue
            button_id = _safe_getattr(button, "Id")
            label = _safe_getattr(button, "Text") or _safe_getattr(button, "Tooltip") or _safe_getattr(button, "IconName")
            summaries.append(f"{button_id} [{label}]")
    return summaries


def _find_toolbar_button_by_hints(
    session,
    toolbar_ids: list[str],
    *,
    hints: list[str],
    icon_names: list[str] | None = None,
    timeout: float = 6.0,
    interval: float = 0.25,
):
    normalized_hints = [normalize_response(hint) for hint in hints if str(hint).strip()]
    normalized_icons = {normalize_response(icon) for icon in (icon_names or []) if str(icon).strip()}
    deadline = time.monotonic() + max(timeout, 0.0)

    while True:
        try:
            wait_not_busy(session, timeout=interval, interval=min(interval, 0.1))
        except Exception:
            pass

        for toolbar_id in toolbar_ids:
            try:
                toolbar = session.findById(toolbar_id)
                count = int(_safe_getattr(toolbar.Children, "Count", "0") or "0")
            except Exception:
                continue

            for index in range(count):
                try:
                    button = toolbar.Children(index)
                except Exception:
                    continue
                if _safe_getattr(button, "Type") != "GuiButton":
                    continue

                text = _safe_getattr(button, "Text")
                tooltip = _safe_getattr(button, "Tooltip")
                icon_name = _safe_getattr(button, "IconName")
                haystacks = [
                    normalize_response(text),
                    normalize_response(tooltip),
                    normalize_response(_safe_getattr(button, "Id")),
                ]
                if any(hint and hint in haystack for hint in normalized_hints for haystack in haystacks):
                    return button
                if normalized_icons and normalize_response(icon_name) in normalized_icons:
                    return button

        if time.monotonic() >= deadline:
            break
        wait(interval)

    available_buttons = ", ".join(_toolbar_buttons_summary(session, toolbar_ids)) or "(nenhum botao visivel)"
    raise RuntimeError(
        "Nenhum botao compativel encontrado no toolbar. "
        f"Procurei por {hints} / icones {icon_names or []}. Disponiveis: {available_buttons}"
    )


def _press_email_button(
    session,
    profile: dict,
    context: RunContext,
    *,
    selector_timeout: float = 10.0,
    toolbar_timeout: float = 6.0,
    allow_vkey_fallback: bool = True,
) -> str:
    configured_ids = profile["buttons"].get("enviarEmail", [])

    try:
        return _press_candidates(session, configured_ids, context=context, timeout=selector_timeout)
    except Exception as selector_exc:
        context.warn(
            "Botao de email nao apareceu pelo seletor configurado. "
            f"Tentando localizar no toolbar. Motivo: {selector_exc}"
        )

    try:
        button = _find_toolbar_button_by_hints(
            session,
            ["wnd[0]/tbar[1]"],
            hints=["Gerar avaliação final", "Enviar por email", "email"],
            icon_names=["T_MAIL"],
            timeout=toolbar_timeout,
        )
        button_id = _safe_getattr(button, "Id")
        if context and button_id:
            context.track_field(context.last_stage or "sap", button_id)
        button.press()
        wait_not_busy(session)
        return button_id or "toolbar:email"
    except Exception as toolbar_exc:
        context.warn(
            "Botao de email nao foi localizado dinamicamente no toolbar. "
            f"Tentando atalho F7. Motivo: {toolbar_exc}"
        )

    if not allow_vkey_fallback:
        raise RuntimeError("Nenhuma avaliacao final disponivel para enviar email.")

    send_vkey(session, 7)
    return "vkey:7"


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------

def _find_editable_rows(grid, column: str, context: RunContext) -> list[int]:
    """
    Detect editable rows in the SAP GridView using a layered fallback strategy:
      1. GetCellType - non-zero means the cell is interactive/editable
      2. GetCellChangeable - available on SAP 7.4+
      3. If both fail, log a clear warning and return empty list
         (intentionally avoids ModifyCell no-op to prevent marking the document dirty)
    """
    try:
        total = int(grid.RowCount)
    except Exception as exc:
        raise RuntimeError(f"Nao foi possivel ler RowCount da grade ZME62: {exc}") from exc

    if total == 0:
        return []

    editable: list[int] = []

    # Strategy 1: GetCellType
    try:
        _ = grid.GetCellType(0, column)
        for row in range(total):
            try:
                cell_type = grid.GetCellType(row, column)
                if isinstance(cell_type, int):
                    is_editable = cell_type != 0
                else:
                    is_editable = str(cell_type).strip().lower() not in ("0", "normal", "")
                if is_editable:
                    editable.append(row)
            except Exception:
                pass
        if editable:
            context.log(f"Grade: {len(editable)} linha(s) editavel(is) detectada(s) via GetCellType: {editable}")
            return editable
    except Exception:
        pass

    # Strategy 2: GetCellChangeable (SAP 7.4+)
    try:
        _ = grid.GetCellChangeable(0, column)
        for row in range(total):
            try:
                if grid.GetCellChangeable(row, column):
                    editable.append(row)
            except Exception:
                pass
        if editable:
            context.log(f"Grade: {len(editable)} linha(s) editavel(is) detectada(s) via GetCellChangeable: {editable}")
            return editable
    except Exception:
        pass

    context.warn(
        f"Nao foi possivel detectar linhas editaveis na coluna '{column}' automaticamente. "
        "GetCellType e GetCellChangeable nao suportados nesta grade. "
        "Verifique se a grade ZME62 carregou corretamente ou ajuste o perfil de layout."
    )
    return []


def _read_grid_int_attr(grid, attr_names: tuple[str, ...], default: int) -> int:
    for attr_name in attr_names:
        try:
            value = getattr(grid, attr_name)
        except Exception:
            continue
        try:
            return int(value)
        except Exception:
            try:
                return int(str(value).strip())
            except Exception:
                continue
    return default


def _set_grid_first_visible_row(grid, row_index: int) -> bool:
    for attr_name in ("firstVisibleRow", "FirstVisibleRow"):
        try:
            setattr(grid, attr_name, int(row_index))
            return True
        except Exception:
            continue
    return False


def _commit_grid_batch(session, grid, row: int, response_col: str, context: RunContext, *, press_count: int) -> None:
    grid.setCurrentCell(row, response_col)
    wait(0.2)

    for press_index in range(press_count):
        context.log(f"  Confirmando grade na linha {row} ({press_index + 1}/{press_count})...")
        grid.pressEnter()
        try:
            wait_not_busy(session, timeout=5.0, interval=0.1)
        except Exception:
            pass
        wait(0.3)
        if popup_exists(session):
            context.log("  Popup de informacao detectado apos confirmacao; fechando para continuar.")
            close_popup_ok(session)
            wait(0.3)


def _verify_responses_written(grid, editable_rows: list[int], respostas: list[str], response_col: str) -> list[tuple[int, str, str]]:
    mismatches: list[tuple[int, str, str]] = []
    for row, expected in zip(editable_rows, respostas):
        actual = read_grid_cell(grid, row, response_col)
        if normalize_response(actual) != normalize_response(expected):
            mismatches.append((row, expected, actual))
    return mismatches


def _wait_for_status_message(session, *, timeout: float = 6.0, interval: float = 0.2) -> tuple[str, str]:
    attempts = max(1, int(timeout / interval))
    last_text = ""
    last_type = ""

    for _ in range(attempts):
        try:
            wait_not_busy(session, timeout=interval, interval=min(interval, 0.1))
        except Exception:
            pass

        if popup_exists(session):
            close_popup_ok(session)
            wait(0.2)

        last_text, last_type = read_statusbar(session)
        if last_text or last_type:
            return last_text, last_type
        wait(interval)

    return last_text, last_type


def _save_and_confirm(session, profile: dict, fornecedor: str, context: RunContext) -> tuple[str, str]:
    last_text = ""
    last_type = ""

    for attempt in range(1, 3):
        context.log(f"Salvando avaliacao (tentativa {attempt}/2)...")
        press(session, profile["buttons"]["salvar"], context=context)
        close_popup_ok(session)

        status_text, status_type = _wait_for_status_message(session)
        last_text, last_type = status_text, status_type

        if status_type == "E":
            raise RuntimeError(status_text or f"Falha ao salvar avaliacao do fornecedor {fornecedor}.")

        if status_text or status_type:
            return status_text, status_type

        if attempt == 1:
            context.warn("SAP nao confirmou o salvamento na status bar na primeira tentativa. Repetindo o salvar.")

    raise RuntimeError(
        f"SAP nao confirmou o salvamento da avaliacao do fornecedor {fornecedor}. "
        "A status bar permaneceu vazia apos duas tentativas."
    )


def _open_evaluation_grid(session, fornecedor: str, ano: str, profile: dict, context: RunContext):
    # 1. Open ZME62
    _open_transaction(session, context)

    # 2. Fill header fields
    context.log(f"Fornecedor: {fornecedor} | Ano: {ano}")
    set_text(session, profile["fields"]["fornecedor"], fornecedor, context=context)
    set_text(session, profile["fields"]["ano"], ano, context=context)

    # 3. Execute (load evaluation grid)
    context.log("Carregando grade de avaliacao...")
    press(session, profile["buttons"]["executar"], context=context)
    close_popup_ok(session)

    # 4. Locate grid
    try:
        _grid_elem, grid_id = first_existing(session, profile["grid"]["container"])
    except RuntimeError:
        raise RuntimeError(
            f"Grade de avaliacao nao encontrada para o fornecedor {fornecedor}. "
            "Verifique se a tela ZME62 carregou corretamente."
        )
    grid = session.findById(grid_id)
    context.log(f"Grade localizada: {grid_id}")
    return grid, grid_id


def _open_email_screen(session, fornecedor: str, ano: str, profile: dict, context: RunContext) -> None:
    context.log("Abrindo tela inicial para gerar avaliacao final...")
    _open_transaction(session, context)
    context.log(f"Fornecedor: {fornecedor} | Ano: {ano}")
    set_text(session, profile["fields"]["fornecedor"], fornecedor, context=context)
    set_text(session, profile["fields"]["ano"], ano, context=context)


def _status_indicates_existing_evaluation(status_text: str) -> bool:
    normalized = normalize_response(status_text)
    return "JA EXISTE AVALIACAO" in normalized


def _status_indicates_email_sent(status_text: str) -> bool:
    normalized = normalize_response(status_text)
    return "EMAIL ENVIADO" in normalized or "EMAILS ENVIADOS" in normalized


def _is_missing_email_evaluation_error(message: str) -> bool:
    normalized = normalize_response(message)
    return (
        "NENHUMA AVALIACAO FINAL DISPONIVEL" in normalized
        or "BTN[1]/USR/BTNBUTTON_1" in normalized
        or "BTNBUTTON_1" in normalized
        or "BOTAO DE EMAIL" in normalized and "NAO FOI LOCALIZADO" in normalized
    )


def _wait_for_status_without_touching_popups(
    session,
    *,
    timeout: float = 1.5,
    interval: float = 0.2,
) -> tuple[str, str]:
    attempts = max(1, int(timeout / interval))
    last_text = ""
    last_type = ""

    for _ in range(attempts):
        try:
            wait_not_busy(session, timeout=interval, interval=min(interval, 0.1))
        except Exception:
            pass
        if popup_exists(session):
            return "", ""
        last_text, last_type = read_statusbar(session)
        if last_text or last_type:
            return last_text, last_type
        wait(interval)

    return last_text, last_type


def _send_confirmation_candidates(profile: dict) -> list[str]:
    candidates: list[str] = []
    for key in ("confirmarEnvioInicial", "confirmarEnvioFinal"):
        for candidate in profile.get("buttons", {}).get(key, []):
            candidate = str(candidate)
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _button_candidates(profile: dict, key: str) -> list[str]:
    return [str(candidate) for candidate in profile.get("buttons", {}).get(key, [])]


def _email_grid_candidates(profile: dict) -> list[str]:
    return [str(candidate) for candidate in profile.get("emailGrid", ["wnd[1]/usr/cntlCC_EMAIL/shellcont/shell"])]


def _email_recipients_grid_exists(session, profile: dict, *, timeout: float = 0.2) -> bool:
    try:
        first_existing(session, _email_grid_candidates(profile), timeout=timeout)
        return True
    except Exception:
        return False


def _select_all_email_recipients(session, profile: dict, context: RunContext) -> bool:
    grid_candidates = _email_grid_candidates(profile)

    try:
        grid, grid_id = first_existing(session, grid_candidates, timeout=1.5)
    except Exception:
        return False

    try:
        row_count = int(getattr(grid, "RowCount"))
    except Exception:
        row_count = 0
    if row_count <= 0:
        return False

    context.log(f"Marcando todos os destinatarios do popup de email ({row_count} linha(s))...")

    try:
        grid.SelectAll()
        wait(0.2)
        if context:
            context.track_field(context.last_stage or "sap", grid_id)
        return True
    except Exception as exc:
        context.warn(f"Falha ao selecionar todos os destinatarios automaticamente: {exc}")
        return False


def _wait_for_email_recipient_grid(session, profile: dict, *, timeout: float = 8.0, interval: float = 0.2) -> bool:
    deadline = time.monotonic() + max(timeout, 0.0)
    while True:
        if _email_recipients_grid_exists(session, profile, timeout=0.1):
            return True
        status_text, status_type = read_statusbar(session)
        if status_type == "E":
            raise RuntimeError(status_text or "SAP retornou erro antes de abrir os destinatarios do email.")
        if time.monotonic() >= deadline:
            return False
        try:
            wait_not_busy(session, timeout=interval, interval=min(interval, 0.1))
        except Exception:
            pass
        wait(interval)


def _confirm_send_popup(session, profile: dict, context: RunContext, *, timeout: float = 8.0) -> str:
    initial_candidates = _button_candidates(profile, "confirmarEnvioInicial")
    final_candidates = _button_candidates(profile, "confirmarEnvioFinal")
    if not initial_candidates and not final_candidates:
        raise RuntimeError("Perfil ZME62 sem botoes de confirmacao do envio.")

    deadline = time.monotonic() + max(timeout, 0.0)

    if _email_recipients_grid_exists(session, profile, timeout=0.2):
        context.log("Popup de destinatarios localizado; confirmando envio do email...")
        _select_all_email_recipients(session, profile, context)
        return _press_candidates(session, final_candidates or initial_candidates, context=context, timeout=timeout)

    if initial_candidates:
        context.log("Confirmando popup inicial do envio de email...")
        initial_id = _press_candidates(session, initial_candidates, context=context, timeout=timeout)
        wait(0.4)

        remaining = max(0.5, deadline - time.monotonic())
        if _wait_for_email_recipient_grid(session, profile, timeout=remaining):
            context.log("Popup de destinatarios localizado; confirmando envio do email...")
            _select_all_email_recipients(session, profile, context)
            remaining = max(0.5, deadline - time.monotonic())
            return _press_candidates(session, final_candidates or initial_candidates, context=context, timeout=remaining)

        status_text, status_type = read_statusbar(session)
        if status_type == "E":
            raise RuntimeError(status_text or "SAP retornou erro ao confirmar envio de email.")
        if status_type == "S" and status_text:
            return initial_id

    if final_candidates:
        context.log("Confirmando envio do email...")
        if _email_recipients_grid_exists(session, profile, timeout=0.2):
            _select_all_email_recipients(session, profile, context)
        remaining = max(0.5, deadline - time.monotonic())
        return _press_candidates(session, final_candidates, context=context, timeout=remaining)

    raise RuntimeError("Popup de destinatarios do email nao abriu e o SAP nao confirmou o envio.")


def _wait_for_email_send_status(session, fornecedor: str, *, timeout: float = 12.0, interval: float = 0.25) -> tuple[str, str]:
    status_text, status_type = _wait_for_status_message(session, timeout=timeout, interval=interval)
    if status_type == "E":
        raise RuntimeError(status_text or f"Falha ao enviar avaliacao ao fornecedor {fornecedor}.")
    if not status_text and not status_type:
        raise RuntimeError(
            f"SAP nao confirmou o envio do email do fornecedor {fornecedor}. "
            "A status bar permaneceu vazia apos a confirmacao."
        )
    if status_type == "S" and not _status_indicates_email_sent(status_text):
        raise RuntimeError(
            f"SAP confirmou outra etapa, mas nao o envio do email do fornecedor {fornecedor}: {status_text}"
        )
    return status_text, status_type


def _select_first_existing_evaluation(session, profile: dict, fornecedor: str, context: RunContext) -> None:
    buttons = profile.get("buttons", {})
    view_candidates = buttons.get("verAvaliacoes", ["wnd[0]/tbar[1]/btn[5]"])
    detail_candidates = buttons.get("verDetalhes", ["wnd[0]/tbar[1]/btn[5]"])
    list_candidates = profile.get("listGrid", ["wnd[0]/usr/cntlGC_CONTAINER_LISTA/shellcont/shell"])

    context.log("Avaliacao final ja existente; abrindo lista de avaliacoes...")
    _press_candidates(session, view_candidates, context=context, timeout=8.0)

    try:
        list_grid, list_grid_id = first_existing(session, list_candidates, timeout=8.0)
    except Exception as exc:
        raise RuntimeError(
            f"Lista de avaliacoes nao encontrada para o fornecedor {fornecedor}: {exc}"
        ) from exc

    context.log(f"Lista de avaliacoes localizada: {list_grid_id}")

    try:
        row_count = int(getattr(list_grid, "RowCount"))
    except Exception as exc:
        raise RuntimeError(f"Nao foi possivel ler a lista de avaliacoes do fornecedor {fornecedor}: {exc}") from exc
    if row_count <= 0:
        raise RuntimeError(f"Nenhuma avaliacao existente foi encontrada para o fornecedor {fornecedor}.")

    selection_applied = False
    for attr_name, attr_value in (("selectedRows", "0"), ("SelectedRows", "0"), ("currentCellRow", 0), ("CurrentCellRow", 0)):
        try:
            setattr(list_grid, attr_name, attr_value)
            selection_applied = True
            break
        except Exception:
            continue
    if not selection_applied:
        raise RuntimeError(f"Nao foi possivel selecionar a primeira avaliacao do fornecedor {fornecedor}.")

    wait(0.3)
    _press_candidates(session, detail_candidates, context=context, timeout=8.0)

    if popup_exists(session):
        popup = dump_popup(session) or {}
        popup_text = json.dumps(popup, ensure_ascii=False)
        raise RuntimeError(
            f"Falha ao abrir detalhes da avaliacao existente do fornecedor {fornecedor}: {popup_text}"
        )


def _send_email_from_grid(session, grid, profile: dict, fornecedor: str, context: RunContext) -> tuple[str, str]:
    context.log("Iniciando envio da avaliacao ao fornecedor...")

    try:
        email_button_options = {}
        if grid is None:
            email_button_options = {
                "selector_timeout": 2.0,
                "toolbar_timeout": 1.0,
                "allow_vkey_fallback": False,
            }

        _press_email_button(session, profile, context, **email_button_options)

        initial_status_text, initial_status_type = _wait_for_status_without_touching_popups(session, timeout=1.5, interval=0.2)
        if _status_indicates_existing_evaluation(initial_status_text):
            _select_first_existing_evaluation(session, profile, fornecedor, context)
            _press_email_button(session, profile, context, **email_button_options)
            _confirm_send_popup(session, profile, context, timeout=4.0 if grid is None else 8.0)
        else:
            confirm_timeout = 4.0 if grid is None else 8.0
            _confirm_send_popup(session, profile, context, timeout=confirm_timeout)
            first_status_text, first_status_type = _wait_for_status_without_touching_popups(session, timeout=3.0, interval=0.25)
            if first_status_type == "S" and _status_indicates_email_sent(first_status_text):
                return first_status_text, first_status_type

            _press_email_button(session, profile, context, **email_button_options)
            _confirm_send_popup(session, profile, context, timeout=confirm_timeout)
    except Exception as exc:
        raise RuntimeError(f"Falha ao enviar avaliacao ao fornecedor {fornecedor}: {exc}") from exc

    if grid is not None:
        try:
            grid.setCurrentCell(10, profile["grid"]["responseColumn"])
            wait(0.2)
        except Exception:
            pass

    return _wait_for_email_send_status(session, fornecedor, timeout=12.0, interval=0.25)


def _translate_response_for_row(answer_index: int, resposta: str, question_options: list[list[str]]) -> str:
    """
    Translate the chosen value to the text the SAP grid actually persists.

    The panel now exposes the real per-question options, but we still accept a
    couple of legacy generic labels for backward compatibility:
      - question 1: 'SIM' -> 'SIM, MESMAS CONDICOES'
      - questions 2-4: 'TALVEZ' -> 'PARCIALMENTE'

    The negative option should be sent as the literal 'NAO' value for every
    question that exposes it in the dropdown.
    """
    normalized = normalize_response(resposta)
    option_map: dict[str, str] = {}
    if answer_index < len(question_options):
        option_map = {normalize_response(item): item for item in question_options[answer_index]}

    if answer_index == 0 and normalized == "SIM":
        normalized = "SIM, MESMAS CONDICOES"
    elif answer_index >= 1:
        if normalized == "TALVEZ":
            normalized = "PARCIALMENTE"

    return option_map.get(normalized, str(resposta))


def _fill_responses(
    session,
    grid,
    editable_rows: list[int],
    respostas: list[str],
    response_col: str,
    context: RunContext,
    *,
    question_options: list[list[str]],
) -> None:
    """
    Fill each editable row with its corresponding response value.

    The recorded ZME62 VBS uses two phases for the 4-question layout:
      - writes the first 3 rows
      - confirms the 3rd row with Enter twice
      - writes the final row
      - scrolls and confirms the final row once more before saving
    """
    try:
        grid.setColumnWidth(response_col, 20)
        wait(0.2)
    except Exception:
        pass

    if not editable_rows:
        return

    translated_respostas = [
        _translate_response_for_row(index, resposta, question_options)
        for index, resposta in enumerate(respostas)
    ]
    first_batch_rows = editable_rows[:-1] if len(editable_rows) > 1 else editable_rows
    first_batch_answers = translated_respostas[:-1] if len(translated_respostas) > 1 else translated_respostas

    for index, (row, resposta_original, resposta_sap) in enumerate(zip(first_batch_rows, respostas[:-1], first_batch_answers), start=1):
        context.log(
            f"  Resposta {index}/{len(respostas)}: linha {row} -> '{resposta_original}'"
            + (f" (SAP='{resposta_sap}')" if str(resposta_original) != str(resposta_sap) else "")
        )
        if resposta_sap != "":
            grid.modifyCell(row, response_col, str(resposta_sap))
            wait(0.3)

    if len(editable_rows) > 1:
        _commit_grid_batch(session, grid, first_batch_rows[-1], response_col, context, press_count=2)

        last_row = editable_rows[-1]
        last_answer_original = respostas[-1]
        last_answer_sap = translated_respostas[-1]
        context.log(
            f"  Resposta {len(respostas)}/{len(respostas)}: linha {last_row} -> '{last_answer_original}'"
            + (f" (SAP='{last_answer_sap}')" if str(last_answer_original) != str(last_answer_sap) else "")
        )
        if last_answer_sap != "":
            grid.modifyCell(last_row, response_col, str(last_answer_sap))
            wait(0.3)

        new_first_visible_row = max(0, last_row - 22)
        current_first_visible_row = _read_grid_int_attr(grid, ("firstVisibleRow", "FirstVisibleRow"), 0)
        if new_first_visible_row != current_first_visible_row:
            context.log(f"  Rolando grade antes da confirmacao final (firstVisibleRow={new_first_visible_row}).")
            if _set_grid_first_visible_row(grid, new_first_visible_row):
                wait(0.3)
            else:
                context.warn("Nao foi possivel ajustar firstVisibleRow da grade automaticamente.")

        _commit_grid_batch(session, grid, last_row, response_col, context, press_count=1)
    else:
        _commit_grid_batch(session, grid, editable_rows[0], response_col, context, press_count=1)

    mismatches = _verify_responses_written(grid, editable_rows, translated_respostas, response_col)
    if mismatches:
        details = "; ".join(
            f"linha {row}: esperado '{expected}', lido '{actual or '(vazio)'}'"
            for row, expected, actual in mismatches
        )
        raise RuntimeError(f"A grade ZME62 nao confirmou todas as respostas: {details}")


# ---------------------------------------------------------------------------
# Comment handler
# ---------------------------------------------------------------------------

def _handle_comment(session, profile: dict, comentario: str, context: RunContext) -> str:
    """
    Open the comment dialog, fill it if a comment was provided, save and close.
    Non-blocking: logs a warning and continues if the dialog does not open or
    saving fails. Never raises.
    """
    try:
        press(session, profile["buttons"]["comentario"], context=context)
    except Exception as exc:
        context.warn(f"Botao de comentario nao encontrado: {exc}")
        return ""

    if not popup_exists(session):
        context.warn("Dialogo de comentario nao abriu. Seguindo sem comentario.")
        return ""

    comment_used = ""
    try:
        if comentario:
            set_text(session, profile["commentField"], comentario, context=context)
            comment_used = comentario
        press(session, profile["buttons"]["salvarComentario"], context=context)
        close_popup_ok(session)
        context.log(f"Comentario processado: '{comment_used or '(vazio)'}'")
    except Exception as exc:
        context.warn(f"Falha ao processar comentario: {exc}. Tentando fechar o dialogo.")
        try:
            close_popup_ok(session)
        except Exception:
            pass
        try:
            send_vkey(session, 12)  # F12 = cancel
        except Exception:
            pass

    return comment_used


# ---------------------------------------------------------------------------
# Result factory
# ---------------------------------------------------------------------------

def _make_result(
    *,
    fornecedor: str,
    grupo_index: int,
    ano: str,
    success: bool,
    respostas_aplicadas: list[str] | None = None,
    editable_rows_found: int = 0,
    expected_answers: int = 0,
    status_bar: str = "",
    status_bar_type: str = "",
    error: str = "",
    comment_used: str = "",
) -> dict:
    return {
        "fornecedor": fornecedor,
        "grupo": grupo_index,
        "ano": ano,
        "success": success,
        "respostas_aplicadas": respostas_aplicadas or [],
        "editable_rows_found": editable_rows_found,
        "expected_answers": expected_answers,
        "status_bar": status_bar,
        "status_bar_type": status_bar_type,
        "error": error,
        "comment_used": comment_used,
    }


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def _open_transaction(session, context: RunContext) -> None:
    """Navigate to ZME62 cleanly, handling any popup from the previous state."""
    context.log("Navegando para ZME62...")
    tcode(session, "ZME62")
    close_popup_ok(session)


# ---------------------------------------------------------------------------
# Per-supplier processor
# ---------------------------------------------------------------------------

def _processar_fornecedor(
    session,
    *,
    fornecedor: str,
    ano: str,
    respostas: list[str],
    question_options: list[list[str]],
    comentario: str,
    grupo_index: int,
    profile: dict,
    output_dir: Path,
    context: RunContext,
) -> dict:
    response_col: str = profile["grid"]["responseColumn"]
    grid, _grid_id = _open_evaluation_grid(session, fornecedor, ano, profile, context)

    # 5. Detect editable rows
    editable_rows = _find_editable_rows(grid, response_col, context)

    # 6. Validate count before touching anything
    if len(editable_rows) != len(respostas):
        raise RuntimeError(
            f"Fornecedor {fornecedor}: esperadas {len(respostas)} respostas, "
            f"mas {len(editable_rows)} linha(s) editavel(is) encontrada(s) na grade "
            f"(linhas: {editable_rows}). "
            "Verifique a configuracao do grupo ou a tela ZME62."
        )

    # 7. Fill responses
    context.log(f"Preenchendo {len(respostas)} resposta(s)...")
    _fill_responses(
        session,
        grid,
        editable_rows,
        respostas,
        response_col,
        context,
        question_options=question_options,
    )

    # 8. Save
    status_text, status_type = _save_and_confirm(session, profile, fornecedor, context)
    context.log(f"Avaliacao salva. Status SAP: [{status_type}] {status_text}")

    # 9. Comment (optional, non-blocking)
    comment_used = ""
    if comentario:
        context.log("Inserindo comentario...")
        comment_used = _handle_comment(session, profile, comentario, context)

    return _make_result(
        fornecedor=fornecedor,
        grupo_index=grupo_index,
        ano=ano,
        success=True,
        respostas_aplicadas=respostas,
        editable_rows_found=len(editable_rows),
        expected_answers=len(respostas),
        status_bar=status_text,
        status_bar_type=status_type,
        comment_used=comment_used,
    )


def _processar_envio_fornecedor(
    session,
    *,
    fornecedor: str,
    ano: str,
    grupo_index: int,
    profile: dict,
    context: RunContext,
) -> dict:
    _open_email_screen(session, fornecedor, ano, profile, context)
    status_text, status_type = _send_email_from_grid(session, None, profile, fornecedor, context)
    context.log(f"Envio da avaliacao concluido. Status SAP: [{status_type}] {status_text}")

    return _make_result(
        fornecedor=fornecedor,
        grupo_index=grupo_index,
        ano=ano,
        success=True,
        status_bar=status_text,
        status_bar_type=status_type,
    )


# ---------------------------------------------------------------------------
# run_job - public entrypoint
# ---------------------------------------------------------------------------

def run_job(input_data: dict, options: dict, callbacks: dict) -> RobotResult:
    """
    Process a batch of supplier evaluations via ZME62.

    input_data:
        groups: list of {
            "ano": str,
            "respostas": list[str],
            "comentario": str,       # optional
            "fornecedores": list[str]
        }

    options:
        session_ref, allow_manual_login, session_chooser, layout_profile, output_dir

    callbacks:
        log, progress, is_cancelled
    """
    pythoncom.CoInitialize()
    run_id = timestamp_id()
    output_dir = ensure_dir(Path(options.get("output_dir") or run_output_dir("ZME62-Avaliacao", run_id=run_id)))
    log_path = output_dir / "run.log"
    logger = ExecutionLogger(log_path, callback=callbacks.get("log"))
    context = RunContext(
        logger=logger,
        progress_callback=callbacks.get("progress"),
        cancel_callback=callbacks.get("is_cancelled"),
    )
    result = RobotResult.new(robot="ZME62-AVALIACAO", run_id=run_id)

    groups: list[dict] = input_data.get("groups", [])
    payload_path = output_dir / "payload.json"
    payload_path.write_text(json.dumps({"groups": groups}, indent=2, ensure_ascii=False), encoding="utf-8")
    context.add_artifact(RunArtifact.from_path("payload", payload_path, "payload"))

    # Flatten groups into (group_index, group, fornecedor) tuples for progress tracking
    total_items = sum(len(g.get("fornecedores", [])) for g in groups)

    try:
        _profile_name, profile = load_zme62_profile(options.get("layout_profile"))
        question_options = _question_response_options_from_profile(profile)

        session, session_meta = resolve_session(
            session_ref=options.get("session_ref"),
            allow_manual_login=bool(options.get("allow_manual_login", True)),
            chooser=options.get("session_chooser"),
        )
        result.session_meta = session_meta

        results: list[dict] = []
        item_index = 0

        for grupo_index, grupo in enumerate(groups, start=1):
            if context.is_cancelled():
                result.status = "cancelled"
                break

            ano = str(grupo.get("ano", "")).strip()
            respostas: list[str] = [str(r).strip() for r in grupo.get("respostas", [])]
            comentario: str = str(grupo.get("comentario", "") or "").strip()
            fornecedores: list[str] = [str(f).strip() for f in grupo.get("fornecedores", [])]

            context.log(f"--- Grupo {grupo_index}: {len(fornecedores)} fornecedor(es), ano {ano} ---")

            # Validate responses against the actual option list of each question
            invalidos = validate_responses_by_question(respostas, question_options)
            if invalidos:
                msg = f"Grupo {grupo_index}: resposta(s) invalida(s): {invalidos}. Grupo ignorado."
                context.error(msg)
                for fornecedor in fornecedores:
                    item_index += 1
                    results.append(_make_result(
                        fornecedor=fornecedor,
                        grupo_index=grupo_index,
                        ano=ano,
                        success=False,
                        expected_answers=len(respostas),
                        error=msg,
                    ))
                continue

            for fornecedor in fornecedores:
                if context.is_cancelled():
                    result.status = "cancelled"
                    break

                item_index += 1
                context.progress("zme62-avaliacao", item_index, total_items)
                context.log(f"Processando fornecedor {fornecedor} ({item_index}/{total_items})...")

                try:
                    item_result = _processar_fornecedor(
                        session,
                        fornecedor=fornecedor,
                        ano=ano,
                        respostas=respostas,
                        question_options=question_options,
                        comentario=comentario,
                        grupo_index=grupo_index,
                        profile=profile,
                        output_dir=output_dir,
                        context=context,
                    )
                    results.append(item_result)
                    context.log(f"Fornecedor {fornecedor}: OK")
                except Exception as exc:
                    error_message = str(exc)
                    context.error(f"Fornecedor {fornecedor}: {error_message}")
                    results.append(_make_result(
                        fornecedor=fornecedor,
                        grupo_index=grupo_index,
                        ano=ano,
                        success=False,
                        expected_answers=len(respostas),
                        error=error_message,
                    ))
                    popup = dump_popup(session)
                    if popup:
                        popup_path = output_dir / f"popup-{fornecedor}.json"
                        popup_path.write_text(json.dumps(popup, indent=2, ensure_ascii=False), encoding="utf-8")
                        context.add_artifact(RunArtifact.from_path(f"popup-{fornecedor}", popup_path, "popup_dump"))
                    screenshot_path = output_dir / f"erro-{fornecedor}.png"
                    capture_sap_window(session, screenshot_path)
                    context.add_artifact(RunArtifact.from_path(f"screenshot-{fornecedor}", screenshot_path, "screenshot"))
                    # Attempt to reset to a clean state before the next supplier
                    try:
                        close_popup_ok(session)
                    except Exception:
                        pass

            if result.status == "cancelled":
                break

        ok_count = sum(1 for r in results if r.get("success"))
        fail_count = len(results) - ok_count
        if fail_count and result.status not in ("cancelled", "error"):
            result.status = "warning"

        result.business_result = {
            "results": results,
            "successCount": ok_count,
            "failCount": fail_count,
            "totalItems": len(results),
        }

    except Exception as exc:
        result.status = "error"
        context.error(str(exc))
    finally:
        result.errors = context.errors
        result.messages = [m.to_dict() for m in context.messages]
        result.artifacts = [a.to_dict() for a in context.artifacts]
        result.finalize()
        result_path = output_dir / "result.json"
        result_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        pythoncom.CoUninitialize()

    return result


def run_email_job(input_data: dict, options: dict, callbacks: dict) -> RobotResult:
    """
    Send saved ZME62 evaluations to suppliers.

    input_data:
        items: list of {
            "fornecedor": str,
            "ano": str,
            "grupo": int
        }
    """
    pythoncom.CoInitialize()
    run_id = timestamp_id()
    output_dir = ensure_dir(Path(options.get("output_dir") or run_output_dir("ZME62-Avaliacao-Envio", run_id=run_id)))
    log_path = output_dir / "run.log"
    logger = ExecutionLogger(log_path, callback=callbacks.get("log"))
    context = RunContext(
        logger=logger,
        progress_callback=callbacks.get("progress"),
        cancel_callback=callbacks.get("is_cancelled"),
    )
    result = RobotResult.new(robot="ZME62-AVALIACAO-ENVIO", run_id=run_id)

    items: list[dict] = input_data.get("items", [])
    payload_path = output_dir / "payload.json"
    payload_path.write_text(json.dumps({"items": items}, indent=2, ensure_ascii=False), encoding="utf-8")
    context.add_artifact(RunArtifact.from_path("payload", payload_path, "payload"))

    total_items = len(items)

    try:
        _profile_name, profile = load_zme62_profile(options.get("layout_profile"))

        session, session_meta = resolve_session(
            session_ref=options.get("session_ref"),
            allow_manual_login=bool(options.get("allow_manual_login", True)),
            chooser=options.get("session_chooser"),
        )
        result.session_meta = session_meta

        results: list[dict] = []

        for item_index, item in enumerate(items, start=1):
            if context.is_cancelled():
                result.status = "cancelled"
                break

            fornecedor = str(item.get("fornecedor", "")).strip()
            ano = str(item.get("ano", "")).strip()
            grupo_index = int(item.get("grupo", 0) or 0)

            context.progress("zme62-envio-email", item_index, total_items)
            context.log(f"Enviando avaliacao do fornecedor {fornecedor} ({item_index}/{total_items})...")

            try:
                item_result = _processar_envio_fornecedor(
                    session,
                    fornecedor=fornecedor,
                    ano=ano,
                    grupo_index=grupo_index,
                    profile=profile,
                    context=context,
                )
                results.append(item_result)
                context.log(f"Fornecedor {fornecedor}: envio OK")
            except Exception as exc:
                error_message = str(exc)
                missing_evaluation = _is_missing_email_evaluation_error(error_message)
                if missing_evaluation:
                    context.warn(f"Fornecedor {fornecedor}: sem avaliacao final para enviar; pulando.")
                    error_message = "Sem avaliacao final disponivel para enviar email."
                else:
                    context.error(f"Fornecedor {fornecedor}: {error_message}")
                results.append(_make_result(
                    fornecedor=fornecedor,
                    grupo_index=grupo_index,
                    ano=ano,
                    success=False,
                    error=error_message,
                ))
                if missing_evaluation:
                    continue
                popup = dump_popup(session)
                if popup:
                    popup_path = output_dir / f"popup-{fornecedor}.json"
                    popup_path.write_text(json.dumps(popup, indent=2, ensure_ascii=False), encoding="utf-8")
                    context.add_artifact(RunArtifact.from_path(f"popup-{fornecedor}", popup_path, "popup_dump"))
                screenshot_path = output_dir / f"erro-{fornecedor}.png"
                capture_sap_window(session, screenshot_path)
                context.add_artifact(RunArtifact.from_path(f"screenshot-{fornecedor}", screenshot_path, "screenshot"))
                try:
                    close_popup_ok(session)
                except Exception:
                    pass

        ok_count = sum(1 for r in results if r.get("success"))
        fail_count = len(results) - ok_count
        if fail_count and result.status not in ("cancelled", "error"):
            result.status = "warning"

        result.business_result = {
            "results": results,
            "successCount": ok_count,
            "failCount": fail_count,
            "totalItems": len(results),
        }

    except Exception as exc:
        result.status = "error"
        context.error(str(exc))
    finally:
        result.errors = context.errors
        result.messages = [m.to_dict() for m in context.messages]
        result.artifacts = [a.to_dict() for a in context.artifacts]
        result.finalize()
        result_path = output_dir / "result.json"
        result_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        pythoncom.CoUninitialize()

    return result
