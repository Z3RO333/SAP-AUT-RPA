import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from _panel_utils import ensure_repo_root, open_path

ensure_repo_root()

from core.common.runtime import ensure_dir, run_output_dir
from core.reports.common import export_dataframe_excel, export_dataframe_pdf
from core.reports.relatorio_fornecedor import apply_filters, load_report


class RelatorioFornecedorPanel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Relatorio Fornecedor")
        self.root.geometry("980x720")
        self.root.minsize(980, 720)
        self.root.configure(bg="#f4f7fb")

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False
        self.last_output_dir: Path | None = None

        self.file_var = tk.StringVar()
        self.fornecedor_var = tk.StringVar()
        self.centro_var = tk.StringVar()
        self.period_start_var = tk.StringVar()
        self.period_end_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Pronto. Selecione uma planilha consolidada e aplique filtros.")

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
        style.configure("Muted.TLabel", background="#ffffff", foreground="#475569", font=("Segoe UI", 9))
        style.configure("Status.TFrame", background="#f1f5f9")
        style.configure("Status.TLabel", background="#f1f5f9", foreground="#111827", font=("Segoe UI Semibold", 9))
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 9))

    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", height=96)
        header.pack(fill="x")
        header.pack_propagate(False)
        ttk.Label(header, text="Relatorio Fornecedor", style="HeaderTitle.TLabel").place(x=24, y=18)
        ttk.Label(header, text="Filtra uma base consolidada de fornecedor e exporta Excel/PDF.", style="HeaderText.TLabel").place(x=26, y=56)

        outer = ttk.Frame(self.root, style="Card.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=24, pady=22)
        form = ttk.LabelFrame(outer, text="Filtros", style="Section.TLabelframe", padding=12)
        form.pack(fill="x")
        ttk.Label(form, text="Planilha", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.file_var, width=70).grid(row=1, column=0, sticky="we", padx=(0, 10), pady=(4, 10))
        ttk.Button(form, text="Selecionar", command=self._pick_file).grid(row=1, column=1, sticky="w", pady=(4, 10))
        ttk.Label(form, text="Fornecedor", style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.fornecedor_var, width=20).grid(row=3, column=0, sticky="w", padx=(0, 10), pady=(4, 10))
        ttk.Label(form, text="Centro", style="Muted.TLabel").grid(row=2, column=1, sticky="w")
        ttk.Entry(form, textvariable=self.centro_var, width=20).grid(row=3, column=1, sticky="w", padx=(0, 10), pady=(4, 10))
        ttk.Label(form, text="Periodo inicial (YYYY-MM-DD)", style="Muted.TLabel").grid(row=2, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.period_start_var, width=18).grid(row=3, column=2, sticky="w", padx=(0, 10), pady=(4, 10))
        ttk.Label(form, text="Periodo final (YYYY-MM-DD)", style="Muted.TLabel").grid(row=2, column=3, sticky="w")
        ttk.Entry(form, textvariable=self.period_end_var, width=18).grid(row=3, column=3, sticky="w", pady=(4, 10))
        buttons = ttk.Frame(form)
        buttons.grid(row=4, column=0, columnspan=4, sticky="w")
        self.execute_button = ttk.Button(buttons, text="Processar", command=self.start_execution, style="Accent.TButton")
        self.execute_button.pack(side="left")
        ttk.Button(buttons, text="Abrir pasta", command=self.open_folder).pack(side="left", padx=(8, 0))

        status_panel = ttk.Frame(outer, style="Status.TFrame", padding=10)
        status_panel.pack(fill="x", pady=(14, 10))
        ttk.Label(status_panel, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

        self.files_list = tk.Listbox(outer, font=("Segoe UI", 9))
        self.files_list.pack(fill="both", expand=True)
        self.files_list.bind("<Double-1>", self._open_selected)

    def _pick_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar planilha consolidada",
            filetypes=[("Arquivos Excel", "*.xlsx *.xls"), ("CSV", "*.csv"), ("Todos os arquivos", "*.*")],
        )
        if path:
            self.file_var.set(path)

    def start_execution(self) -> None:
        if self.is_running:
            return
        if not self.file_var.get().strip():
            messagebox.showwarning("Validacao", "Selecione uma planilha.")
            return
        self.files_list.delete(0, tk.END)
        self.is_running = True
        self.execute_button.config(state="disabled")
        worker = threading.Thread(target=self._run, daemon=True)
        worker.start()

    def _run(self) -> None:
        try:
            source = self.file_var.get().strip()
            output_dir = ensure_dir(run_output_dir("RelatorioFornecedor", business_key=Path(source).stem))
            df = load_report(source)
            filtered = apply_filters(
                df,
                fornecedor=self.fornecedor_var.get().strip(),
                centro=self.centro_var.get().strip(),
                period_start=self.period_start_var.get().strip(),
                period_end=self.period_end_var.get().strip(),
            )
            if filtered.empty:
                self.result_queue.put(("error", "Nenhum registro encontrado apos aplicar os filtros."))
                return
            excel_path = export_dataframe_excel(filtered, output_dir / "relatorio_fornecedor_filtrado.xlsx")
            pdf_path = export_dataframe_pdf(filtered, output_dir / "relatorio_fornecedor_filtrado.pdf", "Relatorio Consolidado por Fornecedor")
            self.result_queue.put(("success", {"outputDir": str(output_dir), "files": [str(excel_path), str(pdf_path)], "count": len(filtered.index)}))
        except Exception as exc:
            self.result_queue.put(("error", str(exc)))

    def _poll_queue(self) -> None:
        try:
            while True:
                status, payload = self.result_queue.get_nowait()
                self.is_running = False
                self.execute_button.config(state="normal")
                if status == "error":
                    self.status_var.set(f"Falha: {payload}")
                    messagebox.showerror("Falha", str(payload))
                    continue
                self.last_output_dir = Path(payload["outputDir"])
                for file_path in payload["files"]:
                    self.files_list.insert(tk.END, file_path)
                self.status_var.set(f"Concluido. Registros exportados: {payload['count']}")
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
    RelatorioFornecedorPanel(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
