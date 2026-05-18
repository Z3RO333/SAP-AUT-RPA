import os
import runpy
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


PANELS_DIR = Path(__file__).resolve().parent
PANEL_RUN_ARG = "--panel"

APPS = [
    {
        "title": "IW38",
        "subtitle": "Ordens por Centro de Trabalho",
        "description": "Consulta ordens na IW38, filtra por status e gera PDF.",
        "panel": "iw38-panel.py",
    },
    {
        "title": "IW32 - Liberar",
        "subtitle": "Liberar Ordens em Lote",
        "description": "Cola os numeros de ordem e libera todas de uma vez.",
        "panel": "iw32-liberar-panel.py",
    },
    {
        "title": "IW32 - Cancelar",
        "subtitle": "Cancelar Ordens em Lote",
        "description": "Interface para cancelamento em lote via IW32.",
        "panel": "iw32-cancelar-panel.py",
    },
    {
        "title": "IW32 - Concluir",
        "subtitle": "Concluir Ordens em Lote",
        "description": "Interface para conclusao em lote via IW32.",
        "panel": "iw32-concluir-panel.py",
    },
    {
        "title": "IW32 - Categorias",
        "subtitle": "Alimentar Valores por Categoria",
        "description": "Preenche categorias e valores em lote via IW32 com layout configuravel.",
        "panel": "iw32-categorias-panel.py",
    },
    {
        "title": "IW28",
        "subtitle": "Ordens em Aberto (IW28)",
        "description": "Consulta ordens em aberto via IW28.",
        "panel": "iw28-panel.py",
    },
    {
        "title": "MB51",
        "subtitle": "Documentos de Material",
        "description": "Lista documentos de material por centro e fornecedor.",
        "panel": "mb51-panel.py",
    },
    {
        "title": "ME2L",
        "subtitle": "Pedidos por Fornecedor",
        "description": "Extrai pedidos por fornecedor e gera relatorio.",
        "panel": "me2l-panel.py",
    },
    {
        "title": "Ordens em Aberto",
        "subtitle": "Lista Local de Ordens Abertas",
        "description": "Filtra uma base local e exporta o resultado consolidado.",
        "panel": "ordens-aberto-panel.py",
    },
    {
        "title": "ME23N - Alimentacao",
        "subtitle": "Modificar Pedido",
        "description": "Copia item e preenche servicos/AUFNR no pedido.",
        "panel": "alimentacao-pedidos-panel.py",
    },
    {
        "title": "ME21N - Criar Pedido",
        "subtitle": "Criacao de Pedido de Compra",
        "description": "Valida Excel, inspeciona a tela e executa a criacao de pedido na ME21N.",
        "panel": "me21n-panel.py",
    },
    {
        "title": "IW38 \u2192 ME21N",
        "subtitle": "Criar Pedido por Ordens IW38",
        "description": "Cola ordens, executa IW38, seleciona tudo e abre a criacao de pedido ME21N.",
        "panel": "iw38-me21n-panel.py",
    },
    {
        "title": "ZME62 - Avaliacao",
        "subtitle": "Avaliacao de Fornecedores em Lote",
        "description": "Preenche avaliacoes de fornecedores via ZME62 com grupos e combinacoes de respostas.",
        "panel": "zme62-avaliacao-panel.py",
    },
    {
        "title": "ZME62 - Envio",
        "subtitle": "Enviar Emails de Avaliacao",
        "description": "Envia por email avaliacoes finais ja salvas para fornecedores avaliados.",
        "panel": "zme62-envio-email-panel.py",
    },
    {
        "title": "Diagnostico SAP",
        "subtitle": "Testar conexao COM com SAP GUI",
        "description": "Testa cada etapa do COM SAP e gera log no Desktop. Use quando o robo nao reconhece a sessao.",
        "panel": "diagnostico-sap-panel.py",
    },
]

COLS = 3


class MenuPrincipal:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Robos SAP - Menu Principal")
        self.root.configure(bg="#f4f7fb")
        self.root.resizable(True, True)
        self._child_processes: dict[int, tuple] = {}

        self._build_styles()
        self._build_layout()

    def _build_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Header.TFrame", background="#0b2a5b")
        style.configure("HeaderTitle.TLabel", background="#0b2a5b", foreground="#ffffff", font=("Segoe UI Semibold", 20))
        style.configure("HeaderText.TLabel", background="#0b2a5b", foreground="#dbe7f6", font=("Segoe UI", 9))
        style.configure("Body.TFrame", background="#f4f7fb")
        style.configure("Open.TButton", font=("Segoe UI Semibold", 9))

    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", height=100)
        header.pack(fill="x")
        header.pack_propagate(False)
        ttk.Label(header, text="Robos SAP", style="HeaderTitle.TLabel").place(x=24, y=16)
        ttk.Label(header, text="Selecione um modulo para abrir o painel correspondente.", style="HeaderText.TLabel").place(x=26, y=58)

        wrapper = tk.Frame(self.root, bg="#f4f7fb")
        wrapper.pack(fill="both", expand=True)

        canvas = tk.Canvas(wrapper, bg="#f4f7fb", highlightthickness=0)
        scrollbar = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = ttk.Frame(canvas, style="Body.TFrame", padding=24)
        canvas_window = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_frame_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_resize(event):
            canvas.itemconfig(canvas_window, width=event.width)

        body.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_resize)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        for idx, app in enumerate(APPS):
            row = idx // COLS
            col = idx % COLS
            self._build_card(body, app, row, col)

        for col in range(COLS):
            body.columnconfigure(col, weight=1, minsize=260)

    def _build_card(self, parent: ttk.Frame, app: dict, row: int, col: int) -> None:
        card = tk.Frame(parent, bg="#ffffff", bd=0, highlightthickness=1, highlightbackground="#e5e7eb")
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

        inner = tk.Frame(card, bg="#ffffff", padx=16, pady=14)
        inner.pack(fill="both", expand=True)

        tk.Label(inner, text=app["title"], bg="#ffffff", fg="#0b2a5b", font=("Segoe UI Semibold", 11), anchor="w").pack(fill="x")
        tk.Label(inner, text=app["subtitle"], bg="#ffffff", fg="#374151", font=("Segoe UI Semibold", 9), anchor="w").pack(fill="x", pady=(2, 4))
        tk.Label(inner, text=app["description"], bg="#ffffff", fg="#6b7280", font=("Segoe UI", 8), anchor="w", wraplength=220, justify="left").pack(fill="x")

        panel_path = PANELS_DIR / app["panel"]
        runtime_panel_path, _runtime_env = self._resolve_panel_and_env(panel_path)
        btn = ttk.Button(inner, text="Abrir", style="Open.TButton", command=lambda p=panel_path: self._open(p))
        btn.pack(anchor="w", pady=(10, 0))

        if not runtime_panel_path.exists():
            btn.config(state="disabled")
            tk.Label(inner, text="painel nao encontrado", bg="#ffffff", fg="#dc2626", font=("Segoe UI", 7)).pack(anchor="w")

    def _python_executable(self) -> str | None:
        if getattr(sys, "frozen", False):
            return sys.executable
        return sys.executable

    def _resolve_panel_and_env(self, panel_path: Path) -> tuple[Path, dict]:
        """Retorna (caminho_real_do_painel, variaveis_de_ambiente) para o subprocess."""
        if not getattr(sys, "frozen", False):
            return panel_path, {}
        meipass = Path(sys._MEIPASS)
        actual = meipass / "panels" / panel_path.name
        env = os.environ.copy()
        # Adiciona _MEIPASS ao PYTHONPATH para que o painel encontre o pacote core/
        env["PYTHONPATH"] = str(meipass) + os.pathsep + env.get("PYTHONPATH", "")
        # Permite que sap_session.py encontre o .env no diretorio de instalacao
        install_dir = Path(sys.executable).parent
        env.setdefault("ROBOSSAP_INSTALL_DIR", str(install_dir))
        return actual, env

    def _panel_log_path(self, panel_name: str) -> Path:
        log_dir = Path.home() / "Documents" / "SAP Robots" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / f"{Path(panel_name).stem}.log"

    def _open(self, panel_path: Path) -> None:
        python = self._python_executable()
        if python is None:
            messagebox.showerror("Falha ao abrir", "Nao foi possivel localizar o executavel do launcher.")
            return
        actual_path, env = self._resolve_panel_and_env(panel_path)
        if not actual_path.exists():
            messagebox.showerror("Falha ao abrir", f"Painel nao encontrado: {actual_path}")
            return
        if getattr(sys, "frozen", False):
            command = [python, PANEL_RUN_ARG, panel_path.name]
        else:
            command = [python, str(Path(__file__).resolve()), PANEL_RUN_ARG, panel_path.name]
        try:
            log_path = self._panel_log_path(panel_path.name)
            log_handle = log_path.open("a", encoding="utf-8", errors="replace")
            log_handle.write(
                f"\n===== {panel_path.name} iniciado em {__import__('datetime').datetime.now().isoformat()} =====\n"
            )
            log_handle.flush()
            process = subprocess.Popen(
                command,
                cwd=str(Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent),
                env=env or None,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self._child_processes[process.pid] = (process, log_handle, log_path)
            self.root.after(900, lambda pid=process.pid, path=panel_path: self._check_panel_process(pid, path))
        except Exception as exc:
            messagebox.showerror("Falha ao abrir", str(exc))

    def _check_panel_process(self, pid: int, panel_path: Path) -> None:
        entry = self._child_processes.pop(pid, None)
        if entry is None:
            return
        process, log_handle, log_path = entry
        if process.poll() is None:
            self._child_processes[pid] = entry
            self.root.after(900, lambda: self._check_panel_process(pid, panel_path))
            return

        try:
            log_handle.flush()
            log_handle.close()
        except Exception:
            pass

        if process.returncode == 0:
            return

        try:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:].strip()
        except Exception:
            tail = "(nao foi possivel ler o log)"

        messagebox.showerror(
            "Falha ao abrir painel",
            f"O painel {panel_path.name} fechou logo apos iniciar.\n\nCodigo: {process.returncode}\n\nLog: {log_path}\n\n{tail}",
        )


def _panel_runtime_path(panel_name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "panels" / panel_name
    return PANELS_DIR / panel_name


def _run_panel(panel_name: str) -> int:
    panel_path = _panel_runtime_path(panel_name)
    if not panel_path.exists():
        raise FileNotFoundError(f"Painel nao encontrado: {panel_path}")

    panel_dir = str(panel_path.parent)
    if panel_dir not in sys.path:
        sys.path.insert(0, panel_dir)

    if getattr(sys, "frozen", False):
        meipass = str(Path(sys._MEIPASS))
        if meipass not in sys.path:
            sys.path.insert(0, meipass)
        os.environ.setdefault("ROBOSSAP_INSTALL_DIR", str(Path(sys.executable).parent))

    runpy.run_path(str(panel_path), run_name="__main__")
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == PANEL_RUN_ARG:
        try:
            return _run_panel(sys.argv[2])
        except Exception as exc:
            print(f"Falha ao abrir painel: {exc}", file=sys.stderr)
            return 1

    root = tk.Tk()
    MenuPrincipal(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
