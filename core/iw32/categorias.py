from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pythoncom

from core.common.layout_maps import load_layout_map, resolve_profile
from core.common.logging import ExecutionLogger
from core.common.models import RobotResult, RunArtifact
from core.common.run_context import RunContext
from core.common.runtime import ensure_dir, run_output_dir, timestamp_id
from core.common.sap_actions import first_existing, press, select, send_vkey, set_text
from core.common.sap_wait import wait
from core.common.sap_popups import close_popup_ok, dump_popup
from core.common.sap_session import resolve_session
from core.common.sap_status import read_statusbar
from core.common.screenshots import capture_sap_window

from .common import load_iw32_profile, open_order_iw32, select_cuk_tab


def load_categories_profile(profile_name: str | None = None) -> tuple[str, dict]:
    layout_map = load_layout_map("IW32-CATEGORIAS")
    return resolve_profile(layout_map, profile_name)


def normalize_category_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.upper().split())


def category_names(profile_name: str | None = None) -> list[str]:
    _name, profile = load_categories_profile(profile_name)
    categories = profile.get("categories", {})
    if not isinstance(categories, dict):
        return []
    return sorted(categories.keys())


def configured_category_names(profile_name: str | None = None) -> list[str]:
    _name, profile = load_categories_profile(profile_name)
    categories = profile.get("categories", {})
    if not isinstance(categories, dict):
        return []
    configured = []
    for name, entry in categories.items():
        if isinstance(entry, dict) and entry.get("fieldCandidates"):
            configured.append(normalize_category_name(name))
    return sorted(configured)


def _normalize_rows(rows: list[dict]) -> list[dict]:
    normalized = []
    for row in rows:
        ordem = str(row.get("ordem", "")).strip()
        categoria = normalize_category_name(row.get("categoria", ""))
        valor = str(row.get("valor", "")).strip()
        numero_servico = str(row.get("numero_servico", "")).strip()
        if not ordem and not categoria and not valor:
            continue
        normalized.append(
            {
                "ordem": ordem,
                "categoria": categoria,
                "valor": valor,
                "numero_servico": numero_servico,
            }
        )
    return normalized


def _resolve_category(profile: dict, categoria: str) -> dict:
    categories = profile.get("categories", {})
    if not isinstance(categories, dict):
        raise RuntimeError("Layout IW32-CATEGORIAS sem secao 'categories'.")
    entry = categories.get(normalize_category_name(categoria))
    if not isinstance(entry, dict):
        raise RuntimeError(f"Categoria sem mapeamento no layout: {categoria}")
    return entry


def _fill_optional_service_number(
    session,
    *,
    ordem: str,
    service_number: str,
    service_field: list[str],
    context: RunContext,
) -> None:
    if not service_number or not service_field:
        return

    try:
        set_text(session, service_field, service_number, context=context)
    except Exception as exc:
        message = str(exc)
        recoverable = (
            "Nenhum elemento encontrado" in message
            or "Elemento nao apareceu" in message
            or "Layout IW32 sem" in message
            or "The control could not be found by id." in message
        )
        if not recoverable:
            raise
        context.warn(
            f"Campo 'Nr. Servico' nao localizado para a ordem {ordem}; seguindo sem preencher. Detalhe: {message}"
        )


def _focus_field(session, field_candidates: list[str], context: RunContext | None = None) -> None:
    if not field_candidates:
        return
    try:
        element, resolved_id = first_existing(session, field_candidates)
        if context:
            context.track_field(context.last_stage or "sap", resolved_id)
        try:
            element.SetFocus()
        except Exception:
            pass
    except Exception:
        return


def _ensure_service_line(
    session,
    *,
    ordem: str,
    service_number: str,
    service_field: list[str],
    context: RunContext,
) -> None:
    if not service_field:
        return

    try:
        element, resolved_id = first_existing(session, service_field)
        if context:
            context.track_field(context.last_stage or "sap", resolved_id)
        try:
            element.SetFocus()
        except Exception:
            pass
        current_value = str(getattr(element, "Text", "") or "").strip()
        if current_value or not service_number:
            return
    except Exception as exc:
        message = str(exc)
        recoverable = (
            "Nenhum elemento encontrado" in message
            or "Elemento nao apareceu" in message
            or "Layout IW32 sem" in message
            or "The control could not be found by id." in message
        )
        if not recoverable:
            raise
        context.warn(
            f"Campo 'Nr. Servico' nao localizado para a ordem {ordem}; seguindo sem preencher. Detalhe: {message}"
        )
        return

    _fill_optional_service_number(
        session,
        ordem=ordem,
        service_number=service_number,
        service_field=service_field,
        context=context,
    )


def preencher_categoria_ordem(
    session,
    ordem: str,
    categoria: str,
    valor: str,
    numero_servico: str,
    iw32_profile: dict,
    categorias_profile: dict,
    context: RunContext,
) -> dict:
    category_entry = _resolve_category(categorias_profile, categoria)
    tab_sequence = category_entry.get("tabSequence", [])
    tab_candidates = category_entry.get("tabCandidates", []) or categorias_profile.get("tabs", {}).get("costTab", [])
    field_candidates = category_entry.get("fieldCandidates", [])
    confirm_field_candidates = category_entry.get("confirmFieldCandidates", [])
    save_button = iw32_profile.get("buttons", {}).get("save", [])
    service_field = iw32_profile.get("fields", {}).get("serviceNumber", [])
    default_service = str(category_entry.get("serviceNumber", "")).strip()

    if not field_candidates:
        raise RuntimeError(f"Categoria '{categoria}' sem fieldCandidates configurado no layout IW32-CATEGORIAS.")

    open_order_iw32(session, ordem, iw32_profile, context=context)
    select_cuk_tab(session, iw32_profile, context=context)
    service_number = numero_servico or default_service
    _ensure_service_line(
        session,
        ordem=ordem,
        service_number=service_number,
        service_field=service_field,
        context=context,
    )
    if tab_sequence:
        for step_candidates in tab_sequence:
            select(session, step_candidates, context=context)
    elif tab_candidates:
        press(session, tab_candidates, context=context)

    wait(0.5)  # aguarda tabela SAP renderizar apos navegacao de abas
    set_text(session, field_candidates, valor, context=context)
    send_vkey(session, 0)
    _focus_field(session, confirm_field_candidates, context=context)
    if save_button:
        press(session, save_button, context=context)
    close_popup_ok(session)
    status_text, status_type = read_statusbar(session)
    if status_type == "E":
        raise RuntimeError(status_text or f"Falha ao preencher a categoria {categoria} na ordem {ordem}.")
    return {
        "aufnr": ordem,
        "categoria": categoria,
        "valor": valor,
        "success": status_type != "E",
        "statusBar": status_text,
        "error": "",
    }


def run_job(input_data, options, callbacks) -> RobotResult:
    pythoncom.CoInitialize()
    run_id = timestamp_id()
    output_dir = ensure_dir(Path(options.get("output_dir") or run_output_dir("IW32-Categorias", run_id=run_id)))
    log_path = output_dir / "run.log"
    logger = ExecutionLogger(log_path, callback=callbacks.get("log"))
    context = RunContext(logger=logger, progress_callback=callbacks.get("progress"), cancel_callback=callbacks.get("is_cancelled"))
    result = RobotResult.new(robot="IW32-CATEGORIAS", run_id=run_id)
    rows = _normalize_rows(input_data.get("rows", []))
    payload_path = output_dir / "payload.json"
    payload_path.write_text(json.dumps({"rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    context.add_artifact(RunArtifact.from_path("payload", payload_path, "payload"))

    try:
        _iw32_profile_name, iw32_profile = load_iw32_profile(options.get("layout_profile"))
        _categories_profile_name, categories_profile = load_categories_profile(options.get("categories_profile"))
        session, session_meta = resolve_session(
            session_ref=options.get("session_ref"),
            allow_manual_login=bool(options.get("allow_manual_login", True)),
            chooser=options.get("session_chooser"),
        )
        result.session_meta = session_meta
        results = []
        for index, row in enumerate(rows, start=1):
            if context.is_cancelled():
                result.status = "cancelled"
                break
            context.progress("iw32-categorias", index, len(rows))
            try:
                results.append(
                    preencher_categoria_ordem(
                        session,
                        ordem=row["ordem"],
                        categoria=row["categoria"],
                        valor=row["valor"],
                        numero_servico=row["numero_servico"],
                        iw32_profile=iw32_profile,
                        categorias_profile=categories_profile,
                        context=context,
                    )
                )
            except Exception as exc:
                error_message = str(exc)
                results.append(
                    {
                        "aufnr": row["ordem"],
                        "categoria": row["categoria"],
                        "valor": row["valor"],
                        "success": False,
                        "statusBar": "",
                        "error": error_message,
                    }
                )
                popup = dump_popup(session)
                if popup:
                    popup_path = output_dir / f"popup-{row['ordem']}.json"
                    popup_path.write_text(json.dumps(popup, indent=2, ensure_ascii=False), encoding="utf-8")
                    context.add_artifact(RunArtifact.from_path(f"popup-{row['ordem']}", popup_path, "popup_dump"))
                screenshot_path = output_dir / f"erro-{row['ordem']}.png"
                capture_sap_window(session, screenshot_path)
                context.add_artifact(RunArtifact.from_path(f"screenshot-{row['ordem']}", screenshot_path, "screenshot"))
                context.error(error_message)

        ok_count = sum(1 for item in results if item.get("success"))
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
