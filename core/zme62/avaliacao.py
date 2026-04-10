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
from core.common.sap_actions import first_existing, press, send_vkey, set_text, tcode
from core.common.sap_popups import close_popup_ok, dump_popup, popup_exists
from core.common.sap_session import resolve_session
from core.common.sap_status import read_statusbar
from core.common.sap_wait import wait
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


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------

def _find_editable_rows(grid, column: str, context: RunContext) -> list[int]:
    """
    Detect editable rows in the SAP GridView using a layered fallback strategy:
      1. GetCellType — non-zero means the cell is interactive/editable
      2. GetCellChangeable — available on SAP 7.4+
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


def _fill_responses(grid, editable_rows: list[int], respostas: list[str], response_col: str, context: RunContext) -> None:
    """Fill each editable row with its corresponding response value."""
    for i, (row, resposta) in enumerate(zip(editable_rows, respostas), start=1):
        context.log(f"  Resposta {i}/{len(respostas)}: linha {row} -> '{resposta}'")
        grid.modifyCell(row, response_col, str(resposta))
        grid.setCurrentCell(row, response_col)
        grid.pressEnter()
        wait(0.1)


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
    comentario: str,
    grupo_index: int,
    profile: dict,
    output_dir: Path,
    context: RunContext,
) -> dict:
    response_col: str = profile["grid"]["responseColumn"]

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
    _fill_responses(grid, editable_rows, respostas, response_col, context)

    # 8. Save
    context.log("Salvando avaliacao...")
    press(session, profile["buttons"]["salvar"], context=context)
    close_popup_ok(session)

    status_text, status_type = read_statusbar(session)
    if status_type == "E":
        raise RuntimeError(status_text or f"Falha ao salvar avaliacao do fornecedor {fornecedor}.")

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


# ---------------------------------------------------------------------------
# run_job — public entrypoint
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
        allowed = profile.get("allowedResponses", [])

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

            # Validate responses against allowed list
            invalidos = validate_responses(respostas, allowed)
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
