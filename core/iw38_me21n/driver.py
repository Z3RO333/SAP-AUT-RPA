from __future__ import annotations

import win32clipboard

from core.common.run_context import RunContext
from core.common.sap_actions import tcode
from core.common.sap_wait import wait_not_busy


def _window_exists(session, window_id: str) -> bool:
    try:
        session.findById(window_id)
        return True
    except Exception:
        return False


def _set_clipboard(text: str) -> None:
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_TEXT)
    finally:
        win32clipboard.CloseClipboard()


def execute_iw38_me21n(
    session,
    ordens: list[str],
    context: RunContext,
    tcode_name: str = "IW38",
) -> None:
    """Abre a transacao, cola as ordens no campo AUFNR, executa e abre a criacao de pedido ME21N.

    Traduz o fluxo do VBScript:
      1. Abre AUFNR selecao multipla, limpa, cola da area de transferencia e confirma.
      2. Executa o relatorio (F8).
      3. Seleciona todas as linhas do grid ALV.
      4. Aciona btn[31] para criacao de pedido.
      5. Confirma popup ME21N (btnBTN_ME21N_MN).
    """
    context.log(f"Abrindo {tcode_name}.")
    tcode(session, tcode_name)
    session.findById("wnd[0]").maximize()
    wait_not_busy(session)

    context.log("Abrindo selecao multipla para AUFNR.")
    session.findById("wnd[0]/usr/btn%AUFNR%APP%-VALU_PUSH").press()
    wait_not_busy(session)

    context.log("Limpando selecao anterior.")
    session.findById("wnd[1]/tbar[0]/btn[16]").press()
    wait_not_busy(session)

    context.log(f"Copiando {len(ordens)} ordem(ns) para a area de transferencia.")
    _set_clipboard("\r\n".join(str(o).strip() for o in ordens if str(o).strip()))

    context.log("Carregando ordens da area de transferencia.")
    session.findById("wnd[1]/tbar[0]/btn[24]").press()
    wait_not_busy(session)

    context.log("Confirmando selecao.")
    session.findById("wnd[1]/tbar[0]/btn[8]").press()
    wait_not_busy(session)

    context.log("Executando relatorio.")
    session.findById("wnd[0]/tbar[1]/btn[8]").press()
    wait_not_busy(session, timeout=60)

    context.log("Selecionando todas as linhas.")
    grid = session.findById("wnd[0]/usr/cntlGRID1/shellcont/shell")
    grid.setCurrentCell(-1, "")
    grid.selectAll()
    wait_not_busy(session)

    context.log("Acionando criacao de pedido.")
    session.findById("wnd[0]/tbar[1]/btn[31]").press()
    wait_not_busy(session)

    if _window_exists(session, "wnd[1]"):
        context.log("Confirmando popup ME21N.")
        session.findById("wnd[1]/usr/btnBTN_ME21N_MN").press()
        wait_not_busy(session)

    context.log("Concluido. ME21N aberta com as ordens selecionadas.")
