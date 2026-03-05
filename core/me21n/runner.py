from __future__ import annotations

import json
from pathlib import Path

import pythoncom

from core.common.layout_maps import load_layout_map, resolve_profile
from core.common.logging import ExecutionLogger
from core.common.models import RobotResult, RunArtifact
from core.common.run_context import RunContext
from core.common.runtime import ensure_dir, run_output_dir, timestamp_id
from core.common.sap_inspect import write_inspection_artifacts
from core.common.sap_popups import dump_popup
from core.common.sap_session import resolve_session
from core.common.screenshots import capture_sap_window

from .excel_reader import read_me21n_workbook
from .payload_builder import payload_to_json, write_payload
from .sap_driver import Me21nLayoutError, execute_purchase_order
from .validator import validate_payload


def validate_input_rows(
    header_rows: list[dict],
    item_rows: list[dict],
    service_rows: list[dict],
    profile: dict,
) -> tuple[dict | None, list[dict], list[dict]]:
    payload, errors, warnings = validate_payload(header_rows, item_rows, service_rows, profile=profile)
    return (
        payload_to_json(payload) if payload else None,
        [item.to_dict() for item in errors],
        [item.to_dict() for item in warnings],
    )


def validate_excel_file(path: str, profile: dict) -> tuple[dict | None, list[dict], list[dict]]:
    header_rows, item_rows, service_rows = read_me21n_workbook(path)
    return validate_input_rows(header_rows, item_rows, service_rows, profile)


def inspect_me21n_session(options, chooser) -> dict:
    session, session_meta = resolve_session(
        session_ref=options.get("session_ref"),
        allow_manual_login=bool(options.get("allow_manual_login", True)),
        chooser=chooser,
    )
    output_dir = ensure_dir(Path(options.get("output_dir") or run_output_dir("ME21N-Inspect", run_id=timestamp_id())))
    json_path, txt_path = write_inspection_artifacts(session, output_dir)
    return {
        "sessionMeta": session_meta,
        "outputDir": str(output_dir),
        "artifacts": [str(json_path), str(txt_path)],
    }


def _read_input_rows(input_data: dict) -> tuple[list[dict], list[dict], list[dict]]:
    if input_data.get("excel_path"):
        return read_me21n_workbook(str(input_data["excel_path"]))
    return (
        list(input_data.get("header_rows") or []),
        list(input_data.get("item_rows") or []),
        list(input_data.get("service_rows") or []),
    )


def run_job(input_data, options, callbacks) -> RobotResult:
    pythoncom.CoInitialize()
    run_id = timestamp_id()
    source_mode = str(input_data.get("source_mode") or ("excel" if input_data.get("excel_path") else "manual"))
    business_key = "VALIDACAO"
    try:
        preview_header_rows, _preview_item_rows, _preview_service_rows = _read_input_rows(input_data)
        if preview_header_rows:
            business_key = str(preview_header_rows[0].get("doc_ref") or "").strip() or business_key
    except Exception:
        pass
    output_dir = ensure_dir(Path(options.get("output_dir") or run_output_dir("ME21N", business_key=business_key, run_id=run_id)))
    log_path = output_dir / "run.log"
    logger = ExecutionLogger(log_path, callback=callbacks.get("log"))
    context = RunContext(logger=logger, progress_callback=callbacks.get("progress"), cancel_callback=callbacks.get("is_cancelled"))
    context.add_artifact(RunArtifact.from_path("run_log", log_path, "log"))
    result = RobotResult.new(robot="ME21N", run_id=run_id)
    session = None
    try:
        layout_map = load_layout_map("ME21N")
        profile_name, profile = resolve_profile(layout_map, options.get("layout_profile"))
        header_rows, item_rows, service_rows = _read_input_rows(input_data)
        payload, errors, warnings = validate_payload(header_rows, item_rows, service_rows, profile=profile)
        if errors:
            result.status = "error"
            result.business_result = {
                "docRef": str(header_rows[0].get("doc_ref") or "").strip() if header_rows else "",
                "validationErrors": [item.to_dict() for item in errors],
                "validationWarnings": [item.to_dict() for item in warnings],
                "itemCount": len(item_rows),
                "serviceLineCount": len(service_rows),
                "layoutProfile": profile_name,
                "profileKind": profile_name,
                "sourceMode": source_mode,
            }
            return result.finalize()

        payload_path = output_dir / "payload.json"
        write_payload(payload, payload_path)
        context.add_artifact(RunArtifact.from_path("payload", payload_path, "payload"))
        session, session_meta = resolve_session(
            session_ref=options.get("session_ref"),
            allow_manual_login=bool(options.get("allow_manual_login", True)),
            chooser=options.get("session_chooser"),
        )
        result.session_meta = session_meta
        business_result = execute_purchase_order(
            session,
            payload=payload,
            profile=profile,
            dry_run=bool(options.get("dry_run")),
            context=context,
        )
        result.status = "dry_run" if options.get("dry_run") else ("success" if business_result.get("poNumber") else "warning")
        result.status_bar_text = business_result.get("statusText", "")
        result.status_bar_type = business_result.get("statusType", "")
        result.business_result = {
            "docRef": payload.header.doc_ref,
            "poNumber": business_result.get("poNumber"),
            "created": business_result.get("created"),
            "itemCount": len(payload.items),
            "serviceLineCount": sum(len(item.service_lines) for item in payload.items),
            "warnings": [item.to_dict() for item in warnings],
            "validationWarnings": [item.to_dict() for item in warnings],
            "validationErrors": [],
            "layoutProfile": profile_name,
            "profileKind": profile_name,
            "sourceMode": source_mode,
        }
    except Me21nLayoutError as exc:
        result.status = "error"
        context.error(str(exc))
    except Exception as exc:
        result.status = "error"
        context.error(str(exc))
        if session is not None:
            popup = dump_popup(session)
            if popup:
                popup_path = output_dir / "popup_dump.json"
                popup_path.write_text(json.dumps(popup, indent=2, ensure_ascii=False), encoding="utf-8")
                context.add_artifact(RunArtifact.from_path("popup_dump", popup_path, "popup_dump"))
            screenshot_path = output_dir / "erro-me21n.png"
            capture_sap_window(session, screenshot_path)
            context.add_artifact(RunArtifact.from_path("screenshot", screenshot_path, "screenshot"))
    finally:
        result.errors = context.errors
        result.messages = [item.to_dict() for item in context.messages]
        result.artifacts = [item.to_dict() for item in context.artifacts]
        result.finalize()
        result_path = output_dir / "result.json"
        result_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        pythoncom.CoUninitialize()
    return result
