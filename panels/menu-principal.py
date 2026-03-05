import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


PANELS_DIR = Path(__file__).resolve().parent

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
        "title": "Relatorio Fornecedor",
        "subtitle": "Relatorio Consolidado",
        "description": "Filtra planilha consolidada local e gera relatorio.",
        "panel": "relatorio-fornecedor-panel.py",
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
]

COLS = 3


class MenuPrincipal:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Robos SAP - Menu Principal")
        self.root.configure(bg="#f4f7fb")
        self.root.resizable(True, True)
        self._child_processes: dict[int, subprocess.Popen[str]] = {}

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
        btn = ttk.Button(inner, text="Abrir", style="Open.TButton", command=lambda p=panel_path: self._open(p))
        btn.pack(anchor="w", pady=(10, 0))

        if not panel_path.exists():
            btn.config(state="disabled")
            tk.Label(inner, text="painel nao encontrado", bg="#ffffff", fg="#dc2626", font=("Segoe UI", 7)).pack(anchor="w")

    def _python_executable(self) -> str | None:
        """Retorna o executavel Python para rodar os paineis.
        Em modo script usa sys.executable. Em modo frozen (exe compilado)
        busca o Python instalado no sistema via PATH.
        """
        if not getattr(sys, "frozen", False):
            return sys.executable
        for candidate in ("pythonw.exe", "python.exe", "pythonw", "python"):
            found = shutil.which(candidate)
            if found:
                return found
        return None

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

    def _open(self, panel_path: Path) -> None:
        python = self._python_executable()
        if python is None:
            messagebox.showerror(
                "Python nao encontrado",
                "Instale Python 3 e adicione ao PATH para abrir os paineis.",
            )
            return
        actual_path, env = self._resolve_panel_and_env(panel_path)
        try:
            process = subprocess.Popen(
                [python, str(actual_path)],
                cwd=str(actual_path.parent),
                env=env or None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._child_processes[process.pid] = process
            self.root.after(900, lambda pid=process.pid, path=panel_path: self._check_panel_process(pid, path))
        except Exception as exc:
            messagebox.showerror("Falha ao abrir", str(exc))

    def _check_panel_process(self, pid: int, panel_path: Path) -> None:
        process = self._child_processes.pop(pid, None)
        if process is None:
            return
        if process.poll() is None:
            return

        stdout, stderr = process.communicate()
        details = (stderr or stdout or "").strip()
        if not details and process.returncode == 0:
            details = "O processo do painel encerrou imediatamente sem retornar erro."
        details = details[-4000:]
        messagebox.showerror(
            "Falha ao abrir painel",
            f"O painel {panel_path.name} fechou logo apos iniciar.\n\nCodigo: {process.returncode}\n\n{details}",
        )


def main() -> int:
    root = tk.Tk()
    MenuPrincipal(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
