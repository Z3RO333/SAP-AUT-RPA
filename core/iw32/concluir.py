from __future__ import annotations

import json
from pathlib import Path

import pythoncom

from core.common.logging import ExecutionLogger
from core.common.models import RobotResult, RunArtifact
from core.common.run_context import RunContext
from core.common.runtime import ensure_dir, run_output_dir, timestamp_id
from core.common.sap_actions import press, set_text
from core.common.sap_popups import close_popup_ok, dump_popup
from core.common.sap_session import resolve_session
from core.common.sap_status import read_statusbar
from core.common.screenshots import capture_sap_window

from .common import load_iw32_profile, open_order_iw32, select_cuk_tab


def concluir_ordem(session, order: str, matricula: str, nota_key: str, profile: dict, context: RunContext) -> dict:
    open_order_iw32(session, order, profile, context=context)
    select_cuk_tab(session, profile, context=context)
    press(session, profile.get("buttons", {}).get("exec", []), context=context)
    press(session, profile.get("buttons", {}).get("avex", []), context=context)
    set_text(session, profile.get("fields", {}).get("matricula", []), matricula, context=context)
    nota_field = profile.get("fields", {}).get("nota", [])
    if nota_field:
        set_text(session, nota_field, nota_key, context=context)
    press(session, profile.get("buttons", {}).get("conc", []), context=context)
    close_popup_ok(session)
    if profile.get("buttons", {}).get("save"):
        press(session, profile["buttons"]["save"], context=context)
    status_text, status_type = read_statusbar(session)
    if status_type == "E":
        raise RuntimeError(status_text or f"Falha ao concluir a ordem {order}.")
    return {"aufnr": order, "success": status_type != "E", "statusBar": status_text, "error": ""}


def run_job(input_data, options, callbacks) -> RobotResult:
    pythoncom.CoInitialize()
    run_id = timestamp_id()
    output_dir = ensure_dir(Path(options.get("output_dir") or run_output_dir("IW32-Concluir", run_id=run_id)))
    log_path = output_dir / "run.log"
    logger = ExecutionLogger(log_path, callback=callbacks.get("log"))
    context = RunContext(logger=logger, progress_callback=callbacks.get("progress"), cancel_callback=callbacks.get("is_cancelled"))
    result = RobotResult.new(robot="IW32-CONCLUIR", run_id=run_id)
    orders = [str(item).strip() for item in input_data.get("orders", []) if str(item).strip()]
    matricula = str(input_data.get("matricula", "")).strip()
    nota_key = str(input_data.get("nota_key", "3")).strip() or "3"
    payload_path = output_dir / "payload.json"
    payload_path.write_text(
        json.dumps({"orders": orders, "matricula": matricula, "nota_key": nota_key}, indent=2),
        encoding="utf-8",
    )
    context.add_artifact(RunArtifact.from_path("payload", payload_path, "payload"))

    try:
        _profile_name, profile = load_iw32_profile(options.get("layout_profile"))
        session, session_meta = resolve_session(
            session_ref=options.get("session_ref"),
            allow_manual_login=bool(options.get("allow_manual_login", True)),
            chooser=options.get("session_chooser"),
        )
        result.session_meta = session_meta
        results = []
        for index, order in enumerate(orders, start=1):
            if context.is_cancelled():
                result.status = "cancelled"
                break
            context.progress("iw32-concluir", index, len(orders))
            try:
                results.append(concluir_ordem(session, order, matricula, nota_key, profile, context))
            except Exception as exc:
                error_message = str(exc)
                results.append({"aufnr": order, "success": False, "statusBar": "", "error": error_message})
                popup = dump_popup(session)
                if popup:
                    popup_path = output_dir / f"popup-{order}.json"
                    popup_path.write_text(json.dumps(popup, indent=2, ensure_ascii=False), encoding="utf-8")
                    context.add_artifact(RunArtifact.from_path(f"popup-{order}", popup_path, "popup_dump"))
                screenshot_path = output_dir / f"erro-{order}.png"
                capture_sap_window(session, screenshot_path)
                context.add_artifact(RunArtifact.from_path(f"screenshot-{order}", screenshot_path, "screenshot"))
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
