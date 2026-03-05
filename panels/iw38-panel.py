import json
import os
import queue
import threading
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

from _panel_utils import ensure_repo_root, open_path

ensure_repo_root()

from core.common.runtime import ensure_dir, run_output_dir
from core.common.session_picker import pick_session
from core.common.sap_session import resolve_session
from core.reports.common import export_dataframe_excel, export_dataframe_pdf
from core.reports.iw38 import executar_iw38


class Iw38Panel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Robo SAP IW38")
        self.root.geometry("920x660")
        self.root.minsize(920, 660)
        self.root.configure(bg="#f4f7fb")

        self.result_manifest = None
        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False

        self.code_var = tk.StringVar()
        self.date_from_var = tk.StringVar(value=(date.today() - timedelta(days=7)).isoformat())
        self.date_to_var = tk.StringVar(value=date.today().isoformat())
        self.pdf_mode_var = tk.StringVar(value="individual")
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Pronto para executar. O app permite escolher a sessao SAP quando houver mais de uma.")

        self._build_styles()
        self._build_layout()
        self._poll_queue()

    def _build_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Header.TFrame", background="#0b2a5b")
        style.configure("HeaderTitle.TLabel", background="#0b2a5b", foreground="#ffffff", font=("Segoe UI Semibold", 18))
        style.configure("HeaderText.TLabel", background="#0b2a5b", foreground="#dbe7f6", font=("Segoe UI", 9))
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

        ttk.Label(header, text="Robo SAP IW38", style="HeaderTitle.TLabel").place(x=24, y=18)
        ttk.Label(
            header,
            text="Consulta ordens na IW38, filtra status aceitos e gera PDF individual ou consolidado.",
            style="HeaderText.TLabel",
        ).place(x=26, y=56)

        outer = ttk.Frame(self.root, style="Card.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=24, pady=22)

        input_group = ttk.LabelFrame(outer, text="Parametros", style="Section.TLabelframe", padding=16)
        input_group.pack(fill="x")

        ttk.Label(input_group, text="Codigo").grid(row=0, column=0, sticky="w")
        ttk.Entry(input_group, textvariable=self.code_var, width=20).grid(row=1, column=0, sticky="we", padx=(0, 18), pady=(4, 10))

        ttk.Label(input_group, text="Data inicial").grid(row=0, column=1, sticky="w")
        ttk.Entry(input_group, textvariable=self.date_from_var, width=18).grid(row=1, column=1, sticky="we", padx=(0, 18), pady=(4, 10))

        ttk.Label(input_group, text="Data final").grid(row=0, column=2, sticky="w")
        ttk.Entry(input_group, textvariable=self.date_to_var, width=18).grid(row=1, column=2, sticky="we", padx=(0, 18), pady=(4, 10))

        ttk.Label(input_group, text="Formato PDF").grid(row=0, column=3, sticky="w")
        mode_combo = ttk.Combobox(input_group, textvariable=self.pdf_mode_var, values=("individual", "consolidated"), state="readonly", width=20)
        mode_combo.grid(row=1, column=3, sticky="we", pady=(4, 10))

        self.execute_button = ttk.Button(input_group, text="Executar", command=self.start_execution, style="Accent.TButton")
        self.execute_button.grid(row=2, column=0, sticky="w", pady=(6, 0))

        self.open_folder_button = ttk.Button(input_group, text="Abrir pasta", command=self.open_output_folder, state="disabled")
        self.open_folder_button.grid(row=2, column=1, sticky="w", pady=(6, 0))

        self.open_file_button = ttk.Button(input_group, text="Abrir arquivo", command=self.open_selected_file, state="disabled")
        self.open_file_button.grid(row=2, column=2, sticky="w", pady=(6, 0))

        status_panel = ttk.Frame(outer, style="Status.TFrame", padding=16)
        status_panel.pack(fill="x", pady=(16, 14))
        ttk.Label(status_panel, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

        ttk.Label(outer, text="Pasta de saida", style="Muted.TLabel").pack(anchor="w")
        ttk.Entry(outer, textvariable=self.output_var, state="readonly").pack(fill="x", pady=(4, 14))

        ttk.Label(outer, text="Arquivos gerados", style="Muted.TLabel").pack(anchor="w")
        files_frame = ttk.Frame(outer, style="Card.TFrame")
        files_frame.pack(fill="both", expand=True, pady=(4, 0))

        scrollbar = ttk.Scrollbar(files_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self.files_listbox = tk.Listbox(
            files_frame,
            height=10,
            activestyle="none",
            font=("Segoe UI", 9),
            exportselection=False,
            yscrollcommand=scrollbar.set,
        )
        self.files_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.files_listbox.yview)
        self.files_listbox.bind("<<ListboxSelect>>", self._on_selection_change)

        ttk.Label(outer, text="O layout ativo da IW38 vem do arquivo sap/layouts/iw38.json.", style="Muted.TLabel").pack(anchor="w", pady=(12, 0))

    def start_execution(self) -> None:
        if self.is_running:
            return

        code = self.code_var.get().strip()
        date_from = self.date_from_var.get().strip()
        date_to = self.date_to_var.get().strip()
        pdf_mode = self.pdf_mode_var.get().strip()

        if not code:
            messagebox.showwarning("Validacao", "Informe o codigo antes de executar.")
            return

        if not self._is_iso_date(date_from) or not self._is_iso_date(date_to):
            messagebox.showwarning("Validacao", "Use o formato de data YYYY-MM-DD.")
            return

        if date_to < date_from:
            messagebox.showwarning("Validacao", "A data final nao pode ser menor que a data inicial.")
            return

        self.result_manifest = None
        self.output_var.set("")
        self.files_listbox.delete(0, tk.END)
        self.open_folder_button.config(state="disabled")
        self.open_file_button.config(state="disabled")
        self.execute_button.config(state="disabled")
        self.status_var.set("Executando robo IW38. Aguarde o SAP e a geracao do PDF.")
        self.is_running = True

        worker = threading.Thread(
            target=self._run_runner,
            args=(code, date_from, date_to, pdf_mode),
            daemon=True,
        )
        worker.start()

    def _run_runner(self, code: str, date_from: str, date_to: str, pdf_mode: str) -> None:
        try:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = ensure_dir(run_output_dir("IW38", business_key=code, run_id=run_id))
            orders_path = output_dir / "orders.xlsx"
            log_path = output_dir / "run.log"
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write(f"{datetime.now().isoformat(timespec='seconds')} [INFO] Iniciando IW38 local.\n")
            session, _session_meta = resolve_session(allow_manual_login=True, chooser=lambda sessions: pick_session(sessions, self.root))
            df = executar_iw38(session, code=code, date_from=date_from, date_to=date_to, callback_log=lambda msg: self.result_queue.put(("log", msg)))
            if df.empty:
                self.result_queue.put(("error", "Nenhuma ordem valida foi retornada pelo SAP."))
                return
            export_dataframe_excel(df, orders_path)
            pdf_path = output_dir / f"IW38_{code}_{pdf_mode}.pdf"
            export_dataframe_pdf(df, pdf_path, "Ordens por Centro de Trabalho - IW38", f"Codigo: {code} | Periodo: {date_from} a {date_to}")
            manifest = {
                "transaction": "IW38",
                "code": code,
                "pdfMode": pdf_mode,
                "outputDir": str(output_dir),
                "totalOrders": len(df.index),
                "generatedFiles": [str(orders_path), str(pdf_path)],
                "warnings": [],
            }
            self.result_queue.put(("success", manifest))

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
                    messagebox.showerror("Falha no robo IW38", str(payload))
                    continue

                self.result_manifest = payload
                self.output_var.set(payload.get("outputDir", ""))
                self.files_listbox.delete(0, tk.END)
                for file_path in payload.get("generatedFiles", []):
                    self.files_listbox.insert(tk.END, file_path)

                if payload.get("outputDir"):
                    self.open_folder_button.config(state="normal")
                if self.files_listbox.size() > 0:
                    self.open_file_button.config(state="normal")

                self.status_var.set(f"Concluido. Ordens processadas: {payload.get('totalOrders', 0)}")
        except queue.Empty:
            pass

        self.root.after(200, self._poll_queue)

    def open_output_folder(self) -> None:
        if not self.result_manifest:
            return

        output_dir = self.result_manifest.get("outputDir", "")
        if output_dir and Path(output_dir).exists():
            open_path(output_dir)

    def open_selected_file(self) -> None:
        selection = self.files_listbox.curselection()
        if not selection:
            return

        file_path = self.files_listbox.get(selection[0])
        if file_path and Path(file_path).exists():
            open_path(file_path)

    def _on_selection_change(self, _event=None) -> None:
        state = "normal" if self.files_listbox.curselection() else "disabled"
        self.open_file_button.config(state=state)

    @staticmethod
    def _is_iso_date(value: str) -> bool:
        try:
            year, month, day = value.split("-")
            if len(year) != 4 or len(month) != 2 or len(day) != 2:
                return False
            date.fromisoformat(value)
            return True
        except ValueError:
            return False
def main() -> int:
    root = tk.Tk()
    Iw38Panel(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
