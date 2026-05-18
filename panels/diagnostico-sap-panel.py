from __future__ import annotations

import datetime
import os
import platform
import struct
import sys
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import scrolledtext, ttk

from _panel_utils import ensure_repo_root

ensure_repo_root()


LOG_FILE = Path.home() / "Desktop" / "diagnostico-sap.log"


class DiagnosticoSAPPanel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Diagnostico SAP - Robos SAP")
        self.root.geometry("900x650")
        self.root.configure(bg="#f4f7fb")

        self._build_layout()
        self._log(f"Log salvo em: {LOG_FILE}\n")
        self._log("Clique em 'Rodar diagnostico completo' para comecar.\n")

    def _build_layout(self) -> None:
        header = tk.Frame(self.root, bg="#0b2a5b", height=70)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="Diagnostico SAP",
            bg="#0b2a5b",
            fg="#ffffff",
            font=("Segoe UI Semibold", 16),
        ).place(x=20, y=10)
        tk.Label(
            header,
            text="Testa o COM do SAP GUI passo a passo. Tudo eh gravado em diagnostico-sap.log no Desktop.",
            bg="#0b2a5b",
            fg="#dbe7f6",
            font=("Segoe UI", 9),
        ).place(x=22, y=40)

        toolbar = tk.Frame(self.root, bg="#f4f7fb", padx=12, pady=10)
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="Rodar diagnostico completo", command=self._run_full).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="Limpar", command=self._clear).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="Abrir log", command=self._open_log).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="Abrir SAP Logon", command=self._open_logon).pack(side="left", padx=(0, 6))

        body = tk.Frame(self.root, bg="#f4f7fb", padx=12, pady=4)
        body.pack(fill="both", expand=True)

        self.output = scrolledtext.ScrolledText(
            body,
            wrap="word",
            font=("Consolas", 9),
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#e2e8f0",
        )
        self.output.pack(fill="both", expand=True)

    def _log(self, text: str) -> None:
        self.output.insert("end", text)
        self.output.see("end")
        self.root.update_idletasks()
        try:
            with LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(text)
        except Exception:
            pass

    def _section(self, title: str) -> None:
        self._log(f"\n{'=' * 70}\n{title}\n{'=' * 70}\n")

    def _clear(self) -> None:
        self.output.delete("1.0", "end")
        try:
            LOG_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    def _open_log(self) -> None:
        try:
            os.startfile(str(LOG_FILE))
        except Exception as exc:
            self._log(f"\nFalha ao abrir log: {exc}\n")

    def _open_logon(self) -> None:
        self._section("Abrir SAP Logon")
        try:
            from core.common.sap_session import find_saplogon_path, open_sap_logon

            path = find_saplogon_path()
            self._log(f"saplogon.exe encontrado em: {path}\n")
            open_sap_logon()
            self._log("Comando para abrir SAP Logon enviado.\n")
        except Exception as exc:
            self._log(f"FALHA: {exc}\n")
            self._log(traceback.format_exc())

    def _run_full(self) -> None:
        self._clear()
        self._log(f"Diagnostico iniciado em: {datetime.datetime.now().isoformat()}\n")

        self._section("1. Ambiente")
        self._log(f"Python executable.....: {sys.executable}\n")
        self._log(f"Python version........: {sys.version}\n")
        self._log(f"Python architecture...: {struct.calcsize('P') * 8} bits ({platform.architecture()[0]})\n")
        self._log(f"Plataforma............: {platform.platform()}\n")
        self._log(f"Frozen (PyInstaller)..: {getattr(sys, 'frozen', False)}\n")
        if getattr(sys, "frozen", False):
            self._log(f"sys._MEIPASS..........: {getattr(sys, '_MEIPASS', '')}\n")
        self._log(f"Diretorio do exe......: {Path(sys.executable).parent}\n")
        self._log(f"ROBOSSAP_INSTALL_DIR..: {os.environ.get('ROBOSSAP_INSTALL_DIR', '(nao definido)')}\n")
        self._log(f"SAP_SERVER (env)......: {os.environ.get('SAP_SERVER', '(nao definido)')}\n")

        self._section("2. Imports COM (pythoncom / win32com)")
        try:
            import pythoncom

            self._log(f"pythoncom importado OK. Versao: {getattr(pythoncom, '__version__', '?')}\n")
        except Exception as exc:
            self._log(f"FALHA ao importar pythoncom: {exc}\n")
            self._log(traceback.format_exc())
            return

        try:
            import win32com.client

            self._log("win32com.client importado OK.\n")
        except Exception as exc:
            self._log(f"FALHA ao importar win32com.client: {exc}\n")
            self._log(traceback.format_exc())
            return

        self._section("3. CoInitialize")
        try:
            pythoncom.CoInitialize()
            self._log("CoInitialize OK.\n")
        except Exception as exc:
            self._log(f"FALHA: {exc}\n")
            self._log(traceback.format_exc())

        self._section("4. saplogon.exe")
        try:
            from core.common.sap_session import find_saplogon_path

            path = find_saplogon_path()
            self._log(f"saplogon.exe encontrado: {path}\n")
        except Exception as exc:
            self._log(f"FALHA: {exc}\n")
            self._log("=> SAP GUI parece nao estar instalado, ou nao esta no caminho padrao.\n")

        self._section("5. GetObject('SAPGUI') - aqui falha o problema 32x64 bits")
        sap_gui_auto = None
        try:
            sap_gui_auto = win32com.client.GetObject("SAPGUI")
            self._log("GetObject('SAPGUI') OK.\n")
        except Exception as exc:
            self._log(f"FALHA: {exc}\n")
            self._log("=> Causas possiveis:\n")
            self._log("   - SAP GUI nao esta aberto (nenhuma janela do SAP Logon visivel)\n")
            self._log("   - Mismatch 32 vs 64 bits entre Python e SAP GUI\n")
            self._log("   - SAP GUI Scripting nao instalado/registrado\n")
            self._log(traceback.format_exc())

        self._section("6. GetScriptingEngine")
        engine = None
        if sap_gui_auto is not None:
            try:
                engine = sap_gui_auto.GetScriptingEngine
                self._log(f"GetScriptingEngine OK. Children.Count = {engine.Children.Count}\n")
            except Exception as exc:
                self._log(f"FALHA: {exc}\n")
                self._log("=> SAP GUI Scripting esta DESABILITADO. Habilite em:\n")
                self._log("   SAP Logon > Opcoes > Acessibilidade & Scripting > Scripting > marcar 'Habilitar scripting'\n")
                self._log("   (Tambem pode estar bloqueado pelo administrador do servidor SAP.)\n")
                self._log(traceback.format_exc())
        else:
            self._log("Pulado (passo 5 falhou).\n")

        self._section("7. Listar sessoes existentes")
        if engine is not None:
            try:
                count_conn = int(engine.Children.Count)
                self._log(f"Conexoes abertas: {count_conn}\n")
                for ci in range(count_conn):
                    conn = engine.Children(ci)
                    self._log(f"  Conexao {ci}: {getattr(conn, 'Description', '?')}\n")
                    for si in range(int(conn.Children.Count)):
                        sess = conn.Children(si)
                        info = getattr(sess, "Info", None)
                        self._log(
                            f"    Sessao {ci}:{si} - "
                            f"sistema={getattr(info, 'SystemName', '?')} "
                            f"client={getattr(info, 'Client', '?')} "
                            f"user={getattr(info, 'User', '?')} "
                            f"tcode={getattr(info, 'Transaction', '?')}\n"
                        )
            except Exception as exc:
                self._log(f"FALHA ao listar sessoes: {exc}\n")
                self._log(traceback.format_exc())
        else:
            self._log("Pulado (passo 6 falhou).\n")

        self._section("8. resolve_session() (codigo real do robo)")
        try:
            from core.common.sap_session import list_sessions

            sessions = list_sessions()
            self._log(f"list_sessions() retornou {len(sessions)} sessao(s):\n")
            for s in sessions:
                self._log(f"  {s}\n")
            if not sessions:
                self._log("=> Nenhuma sessao SAP esta logada agora. Faca login e rode novamente.\n")
        except Exception as exc:
            self._log(f"FALHA: {exc}\n")
            self._log(traceback.format_exc())

        self._section("9. Verificacao final")
        self._log("Diagnostico concluido.\n")
        self._log(f"Envie este arquivo para o suporte: {LOG_FILE}\n")


def main() -> int:
    root = tk.Tk()
    DiagnosticoSAPPanel(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
