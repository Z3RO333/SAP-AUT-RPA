from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pythoncom

from core.common.excel_utils import as_text, normalize_column_name
from core.common.layout_maps import field_candidates, load_layout_map, resolve_profile
from core.common.logging import ExecutionLogger
from core.common.models import RobotResult, RunArtifact
from core.common.run_context import RunContext
from core.common.runtime import ensure_dir, run_output_dir, timestamp_id
from core.common.sap_actions import element_exists, press, select, set_text, tcode
from core.common.sap_popups import close_popup_ok, dump_popup
from core.common.sap_session import resolve_session
from core.common.sap_status import read_statusbar
from core.common.screenshots import capture_sap_window
from core.common.sap_wait import wait_not_busy


def load_me23n_profile(profile_name: str | None = None) -> tuple[str, dict]:
    layout_map = load_layout_map("ME23N")
    return resolve_profile(layout_map, profile_name)


def _first_existing(session, ids: list[str]) -> str:
    for candidate in ids:
        if element_exists(session, candidate):
            return candidate
    raise RuntimeError(f"Nenhum elemento encontrado entre os caminhos esperados: {ids}")


def _close_validation_popups(session) -> None:
    while close_popup_ok(session):
        wait_not_busy(session)


def _open_order(session, pedido: str, profile: dict, context: RunContext) -> None:
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


def _fill_service_lines(session, ordens_aufnr: list[str], profile: dict, context: RunContext) -> None:
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
    _open_order(session, pedido, profile, context)
    _copy_first_item(session, profile, context)
    _set_delivery_date(session, data_entrega, profile, context)
    _fill_service_lines(session, linhas_aufnr, profile, context)
    save_button = profile.get("toolbar", {}).get("save", [])
    if save_button:
        press(session, save_button, context=context)
    text, msg_type = read_statusbar(session)
    if msg_type == "E":
        raise RuntimeError(f"SAP retornou erro ao salvar: {text}")
    return text or "Pedido salvo com sucesso."


def load_lots_from_excel(path: str) -> list[dict]:
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

