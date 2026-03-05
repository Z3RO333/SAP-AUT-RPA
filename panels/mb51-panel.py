import queue
import threading
import tkinter as tk
from datetime import date, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

from _panel_utils import ensure_repo_root, open_path

ensure_repo_root()

from core.common.runtime import ensure_dir, run_output_dir
from core.common.session_picker import pick_session
from core.common.sap_session import resolve_session
from core.reports.common import export_dataframe_excel, export_dataframe_pdf
from core.reports.mb51 import executar_mb51


class Mb51Panel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Robo SAP MB51")
        self.root.geometry("940x660")
        self.root.minsize(940, 660)
        self.root.configure(bg="#f4f7fb")

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False
        self.last_output_dir: Path | None = None

        self.centro_var = tk.StringVar()
        self.fornecedor_var = tk.StringVar()
        self.movimento_var = tk.StringVar()
        self.date_from_var = tk.StringVar(value=(date.today() - timedelta(days=30)).strftime("%d.%m.%Y"))
        self.date_to_var = tk.StringVar(value=date.today().strftime("%d.%m.%Y"))
        self.status_var = tk.StringVar(value="Pronto. Informe ao menos um filtro e execute.")

        self._build_styles()
        self._build_layout()
        self._poll_queue()

    def _build_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Header.TFrame", background="#0b2a5b")
        style.configure("HeaderTitle.TLabel", background="#0b2a5b", foreground="#ffffff", font=("Segoe UI Semibold", 18))
        style.configure("HeaderText.TLabel", background="#0b2a5b", foreground="#dbe7f6", font=("Segoe UI", 9))
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Section.TLabelframe", background="#ffffff")
        style.configure("Section.TLabelframe.Label", background="#ffffff", foreground="#111827", font=("Segoe UI Semibold", 10))
        style.configure("Status.TFrame", background="#f1f5f9")
        style.configure("Status.TLabel", background="#f1f5f9", foreground="#111827", font=("Segoe UI Semibold", 9))
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 9))

    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", height=96)
        header.pack(fill="x")
        header.pack_propagate(False)
        ttk.Label(header, text="Robo SAP MB51", style="HeaderTitle.TLabel").place(x=24, y=18)
        ttk.Label(header, text="Extrai documentos de material e gera Excel/PDF.", style="HeaderText.TLabel").place(x=26, y=56)

        outer = ttk.Frame(self.root, style="Card.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=24, pady=22)
        form = ttk.LabelFrame(outer, text="Filtros", style="Section.TLabelframe", padding=12)
        form.pack(fill="x")
        ttk.Label(form, text="Centro").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.centro_var, width=20).grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(4, 10))
        ttk.Label(form, text="Fornecedor").grid(row=0, column=1, sticky="w")
        ttk.Entry(form, textvariable=self.fornecedor_var, width=20).grid(row=1, column=1, sticky="w", padx=(0, 12), pady=(4, 10))
        ttk.Label(form, text="Tp. Mov.").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.movimento_var, width=12).grid(row=1, column=2, sticky="w", padx=(0, 12), pady=(4, 10))
        ttk.Label(form, text="Data inicial").grid(row=0, column=3, sticky="w")
        ttk.Entry(form, textvariable=self.date_from_var, width=16).grid(row=1, column=3, sticky="w", padx=(0, 12), pady=(4, 10))
        ttk.Label(form, text="Data final").grid(row=0, column=4, sticky="w")
        ttk.Entry(form, textvariable=self.date_to_var, width=16).grid(row=1, column=4, sticky="w", pady=(4, 10))
        buttons = ttk.Frame(form)
        buttons.grid(row=2, column=0, columnspan=5, sticky="w")
        self.execute_button = ttk.Button(buttons, text="Executar", command=self.start_execution, style="Accent.TButton")
        self.execute_button.pack(side="left")
        ttk.Button(buttons, text="Abrir pasta", command=self.open_folder).pack(side="left", padx=(8, 0))

        status_panel = ttk.Frame(outer, style="Status.TFrame", padding=10)
        status_panel.pack(fill="x", pady=(14, 10))
        ttk.Label(status_panel, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

        self.files_list = tk.Listbox(outer, font=("Segoe UI", 9))
        self.files_list.pack(fill="both", expand=True)
        self.files_list.bind("<Double-1>", self._open_selected)

    def start_execution(self) -> None:
        if self.is_running:
            return
        if not any([self.centro_var.get().strip(), self.fornecedor_var.get().strip(), self.movimento_var.get().strip()]):
            messagebox.showwarning("Validacao", "Informe pelo menos um filtro.")
            return
        self.files_list.delete(0, tk.END)
        self.execute_button.config(state="disabled")
        self.is_running = True
        worker = threading.Thread(target=self._run, daemon=True)
        worker.start()

    def _run(self) -> None:
        try:
            output_dir = ensure_dir(run_output_dir("MB51", business_key=self.fornecedor_var.get().strip() or self.centro_var.get().strip() or "GERAL"))
            session, _session_meta = resolve_session(allow_manual_login=True, chooser=lambda sessions: pick_session(sessions, self.root))
            df = executar_mb51(
                session,
                centro=self.centro_var.get().strip(),
                fornecedor=self.fornecedor_var.get().strip(),
                tipo_movimento=self.movimento_var.get().strip(),
                data_ini=self.date_from_var.get().strip(),
                data_fim=self.date_to_var.get().strip(),
                callback_log=lambda msg: self.result_queue.put(("log", msg)),
            )
            if df.empty:
                self.result_queue.put(("error", "Nenhum registro encontrado."))
                return
            excel_path = export_dataframe_excel(df, output_dir / "dados_mb51.xlsx")
            pdf_path = export_dataframe_pdf(df, output_dir / "relatorio_mb51.pdf", "Documentos de Material - MB51")
            self.result_queue.put(("success", {"outputDir": str(output_dir), "files": [str(excel_path), str(pdf_path)], "count": len(df.index)}))
        except Exception as exc:
            self.result_queue.put(("error", str(exc)))

    def _poll_queue(self) -> None:
        try:
            while True:
                status, payload = self.result_queue.get_nowait()
                if status == "log":
                    self.status_var.set(str(payload))
                    continue
                self.is_running = False
                self.execute_button.config(state="normal")
                if status == "error":
                    self.status_var.set(f"Falha: {payload}")
                    messagebox.showerror("Falha no robo MB51", str(payload))
                    continue
                self.last_output_dir = Path(payload["outputDir"])
                for item in payload["files"]:
                    self.files_list.insert(tk.END, item)
                self.status_var.set(f"Concluido. Registros extraidos: {payload['count']}")
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)

    def open_folder(self) -> None:
        if self.last_output_dir and self.last_output_dir.exists():
            open_path(str(self.last_output_dir))

    def _open_selected(self, _event=None) -> None:
        selection = self.files_list.curselection()
        if selection:
            open_path(self.files_list.get(selection[0]))


def main() -> int:
    root = tk.Tk()
    Mb51Panel(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
