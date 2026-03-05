from __future__ import annotations

import os
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

import pythoncom
import win32com.client

from .config import load_config
from .models import SessionMeta
from .runtime import REPO_ROOT


def _load_env_file() -> None:
    """Load .env into os.environ (does not override existing vars).
    Checks: repo root (dev mode), install dir via ROBOSSAP_INSTALL_DIR env var (compiled exe),
    and %LOCALAPPDATA%/Programs/Robos SAP (Inno Setup default install path).
    """
    from .runtime import local_app_dir
    candidates = [
        REPO_ROOT / ".env",
        Path(os.environ.get("ROBOSSAP_INSTALL_DIR", "")) / ".env",
        local_app_dir() / ".env",
    ]
    env_path = next((p for p in candidates if p.name == ".env" and p.exists()), None)
    if env_path is None:
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _get_sap_server_env() -> str | None:
    _load_env_file()
    return os.environ.get("SAP_SERVER") or None


class NoSapSessionError(RuntimeError):
    """Raised when no SAP session can be attached."""


class MultipleSapSessionsError(RuntimeError):
    def __init__(self, sessions: list[dict]) -> None:
        super().__init__("Mais de uma sessao SAP utilizavel foi encontrada.")
        self.sessions = sessions


def _session_info(connection_index: int, session_index: int, session) -> dict:
    info = getattr(session, "Info", None)
    return asdict(
        SessionMeta(
            session_ref=f"{connection_index}:{session_index}",
            connection_index=connection_index,
            session_index=session_index,
            connection_name=str(getattr(getattr(session, "Parent", None), "Description", "") or ""),
            system_name=str(getattr(info, "SystemName", "") or ""),
            client=str(getattr(info, "Client", "") or ""),
            user=str(getattr(info, "User", "") or ""),
            transaction=str(getattr(info, "Transaction", "") or ""),
            window_title=str(getattr(session.findById("wnd[0]"), "Text", "") or ""),
        )
    )


def sap_application():
    pythoncom.CoInitialize()
    try:
        sap_gui_auto = win32com.client.GetObject("SAPGUI")
    except Exception as exc:
        raise NoSapSessionError(f"Nao foi possivel anexar ao SAP GUI: {exc}") from exc
    return sap_gui_auto.GetScriptingEngine


def list_sessions() -> list[dict]:
    app = sap_application()
    sessions: list[dict] = []
    for connection_index in range(int(app.Children.Count)):
        connection = app.Children(connection_index)
        for session_index in range(int(connection.Children.Count)):
            session = connection.Children(session_index)
            if session is None:
                continue
            sessions.append(_session_info(connection_index, session_index, session))
    return sessions


def get_session_by_ref(session_ref: str):
    conn_index, sess_index = [int(part) for part in session_ref.split(":", 1)]
    app = sap_application()
    return app.Children(conn_index).Children(sess_index)


def find_saplogon_path() -> Path:
    config = load_config()
    candidates = []
    if config.sap_logon_path:
        candidates.append(config.sap_logon_path)
    candidates.extend(
        [
            Path(r"C:\Program Files (x86)\SAP\FrontEnd\SAPgui\saplogon.exe"),
            Path(r"C:\Program Files\SAP\FrontEnd\SAPgui\saplogon.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("saplogon.exe nao encontrado.")


def open_sap_logon() -> None:
    subprocess.Popen([str(find_saplogon_path())], close_fds=True)


def _wait_for_sap_engine(timeout: float = 30.0):
    """Poll until the SAP GUI COM engine is available. Returns the scripting engine."""
    start = time.time()
    last_error: Exception | None = None
    while time.time() - start < timeout:
        try:
            pythoncom.CoInitialize()
            return win32com.client.GetObject("SAPGUI").GetScriptingEngine
        except Exception as exc:
            last_error = exc
        time.sleep(1.0)
    raise NoSapSessionError(f"SAP GUI nao ficou disponivel a tempo. Ultimo erro: {last_error}")


def auto_connect_to_server(server: str) -> list[dict]:
    """Conecta ao SAP automaticamente via OpenConnection (usa SSO se configurado no SAP Logon)."""
    # Try to get an already-running SAP GUI engine; if not, launch SAP Logon first.
    try:
        engine = _wait_for_sap_engine(timeout=3.0)
    except NoSapSessionError:
        open_sap_logon()
        engine = _wait_for_sap_engine(timeout=30.0)

    try:
        engine.OpenConnection(server, True)  # True = synchronous
    except Exception as exc:
        raise NoSapSessionError(f"Falha ao conectar ao servidor '{server}': {exc}") from exc

    return list_sessions()


def wait_for_any_session(timeout: float = 60.0, interval: float = 1.0):
    start = time.time()
    last_error: Exception | None = None
    while time.time() - start < timeout:
        try:
            sessions = list_sessions()
            if sessions:
                return sessions
        except Exception as exc:
            last_error = exc
        time.sleep(interval)
    raise NoSapSessionError(f"Login no SAP nao concluiu a tempo. Ultimo erro: {last_error}")


def resolve_session(session_ref: str | None = None, allow_manual_login: bool = True, chooser=None):
    try:
        sessions = list_sessions()
    except NoSapSessionError:
        if not allow_manual_login:
            raise
        sap_server = _get_sap_server_env()
        if sap_server:
            sessions = auto_connect_to_server(sap_server)
        else:
            open_sap_logon()
            sessions = wait_for_any_session()

    if session_ref:
        return get_session_by_ref(session_ref), next(item for item in sessions if item["session_ref"] == session_ref)

    if not sessions:
        if allow_manual_login:
            sap_server = _get_sap_server_env()
            if sap_server:
                sessions = auto_connect_to_server(sap_server)
        if not sessions:
            raise NoSapSessionError("Nenhuma sessao SAP disponivel.")
    if len(sessions) == 1:
        info = sessions[0]
        return get_session_by_ref(info["session_ref"]), info
    if chooser is None:
        raise MultipleSapSessionsError(sessions)
    chosen_ref = chooser(sessions)
    if not chosen_ref:
        raise NoSapSessionError("Selecao de sessao cancelada.")
    return get_session_by_ref(chosen_ref), next(item for item in sessions if item["session_ref"] == chosen_ref)

