import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd

from _panel_utils import ensure_repo_root, pick_session_thread_safe, result_failure_message

ensure_repo_root()

from core.iw32.concluir import run_job


class Iw32ConcluirPanel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Robo SAP IW32 - Concluir Ordens")
        self.root.geometry("880x700")
        self.root.minsize(880, 700)
        self.root.configure(bg="#f4f7fb")

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False

        self.matricula_var = tk.StringVar()
        self.nota_var = tk.StringVar(value="3")
        self.status_var = tk.StringVar(value="Pronto. Informe ordens e execute.")

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
        ttk.Label(header, text="Robo SAP IW32 - Concluir Ordens", style="HeaderTitle.TLabel").place(x=24, y=18)
        ttk.Label(
            header,
            text="Conclui ordens em lote no IW32 com fluxo EXEC/AVEX/CONC.",
            style="HeaderText.TLabel",
        ).place(x=26, y=56)

        outer = ttk.Frame(self.root, style="Card.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=24, pady=22)

        form = ttk.LabelFrame(outer, text="Parametros", style="Section.TLabelframe", padding=12)
        form.pack(fill="x")
        ttk.Label(form, text="Matricula", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.matricula_var, width=24).grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(4, 10))
        ttk.Label(form, text="Nota", style="Muted.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Entry(form, textvariable=self.nota_var, width=10).grid(row=1, column=1, sticky="w", pady=(4, 10))

        text_group = ttk.LabelFrame(outer, text="Ordens", style="Section.TLabelframe", padding=12)
        text_group.pack(fill="both", expand=True, pady=(14, 0))
        ttk.Label(text_group, text="Numeros de ordem (um por linha ou separados por virgula):", style="Muted.TLabel").pack(anchor="w")

        text_frame = ttk.Frame(text_group, style="Card.TFrame")
        text_frame.pack(fill="both", expand=True, pady=(4, 10))
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.orders_text = tk.Text(text_frame, height=9, font=("Consolas", 10), yscrollcommand=scrollbar.set)
        self.orders_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.orders_text.yview)

        button_row = ttk.Frame(text_group, style="Card.TFrame")
        button_row.pack(fill="x")
        self.execute_button = ttk.Button(button_row, text="Executar", command=self.start_execution, style="Accent.TButton")
        self.execute_button.pack(side="left")
        ttk.Button(button_row, text="Importar Planilha", command=self._import_excel).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="Limpar", command=self._clear).pack(side="left", padx=(8, 0))

        status_panel = ttk.Frame(outer, style="Status.TFrame", padding=10)
        status_panel.pack(fill="x", pady=(14, 10))
        ttk.Label(status_panel, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

        ttk.Label(outer, text="Resultados por ordem:", style="Muted.TLabel").pack(anchor="w")
        tree_frame = ttk.Frame(outer, style="Card.TFrame")
        tree_frame.pack(fill="both", expand=True, pady=(4, 0))
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical")
        tree_scroll.pack(side="right", fill="y")
        self.tree = ttk.Treeview(tree_frame, columns=("aufnr", "resultado", "detalhe"), show="headings", yscrollcommand=tree_scroll.set)
        self.tree.heading("aufnr", text="Ordem")
        self.tree.heading("resultado", text="Resultado")
        self.tree.heading("detalhe", text="Detalhe")
        self.tree.column("aufnr", width=120, anchor="center")
        self.tree.column("resultado", width=100, anchor="center")
        self.tree.column("detalhe", width=540, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.config(command=self.tree.yview)
        self.tree.tag_configure("ok", foreground="#16a34a")
        self.tree.tag_configure("fail", foreground="#dc2626")

    def _parse_orders(self) -> list[str]:
        raw = self.orders_text.get("1.0", tk.END)
        values = []
        for line in raw.splitlines():
            values.extend(part.strip() for part in line.split(","))
        return [value for value in values if value]

    def _import_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar planilha de ordens",
            filetypes=[("Arquivos Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")],
        )
        if not path:
            return
        try:
            df = pd.read_excel(path)
            column_map = {str(column).strip().upper(): column for column in df.columns}
            if "ORDEM" not in column_map:
                raise ValueError("Coluna 'ORDEM' nao encontrada na planilha.")
            values = [str(item).strip() for item in df[column_map["ORDEM"]].tolist() if str(item).strip() and str(item).strip().lower() != "nan"]
            if not values:
                raise ValueError("Nenhuma ordem encontrada na planilha.")
            self.orders_text.delete("1.0", tk.END)
            self.orders_text.insert("1.0", "\n".join(values))
            self.status_var.set(f"Importado {len(values)} ordem(ns) da planilha.")
        except Exception as exc:
            messagebox.showerror("Erro ao importar", str(exc))

    def start_execution(self) -> None:
        if self.is_running:
            return
        orders = self._parse_orders()
        if not orders:
            messagebox.showwarning("Validacao", "Informe pelo menos um numero de ordem.")
            return
        if not self.matricula_var.get().strip():
            messagebox.showwarning("Validacao", "Informe a matricula.")
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.execute_button.config(state="disabled")
        self.is_running = True
        self.status_var.set(f"Executando... {len(orders)} ordens a processar.")
        worker = threading.Thread(target=self._run, args=(orders,), daemon=True)
        worker.start()

    def _run(self, orders: list[str]) -> None:
        try:
            result = run_job(
                {
                    "orders": orders,
                    "matricula": self.matricula_var.get().strip(),
                    "nota_key": self.nota_var.get().strip() or "3",
                },
                {
                    "allow_manual_login": True,
                    "interactive": True,
                    "session_chooser": lambda sessions: pick_session_thread_safe(self.root, sessions),
                },
                {
                    "log": lambda message: self.result_queue.put(("log", message)),
                    "progress": lambda stage, current, total: self.result_queue.put(("progress", (stage, current, total))),
                    "is_cancelled": lambda: False,
                },
            )
            self.result_queue.put(("success", result.to_dict()))
        except Exception as exc:
            self.result_queue.put(("error", str(exc)))

    def _poll_queue(self) -> None:
        try:
            while True:
                status, payload = self.result_queue.get_nowait()
                if status == "log":
                    self.status_var.set(str(payload))
                    continue
                if status == "progress":
                    _stage, current, total = payload
                    self.status_var.set(f"Executando... {current}/{total}")
                    continue
                self.is_running = False
                self.execute_button.config(state="normal")
                if status == "error":
                    self.status_var.set(f"Falha: {payload}")
                    messagebox.showerror("Falha no robo IW32", str(payload))
                    continue
                failure_message = result_failure_message(payload)
                if failure_message:
                    self.status_var.set(f"Falha: {failure_message}")
                    messagebox.showerror("Falha no robo IW32", failure_message)
                    continue
                results = payload.get("business_result", {}).get("results", [])
                ok = sum(1 for item in results if item.get("success"))
                fail = len(results) - ok
                for item in results:
                    tag = "ok" if item.get("success") else "fail"
                    detail = item.get("statusBar") or item.get("error") or ""
                    label = "OK" if item.get("success") else "FALHA"
                    self.tree.insert("", tk.END, values=(item.get("aufnr", ""), label, detail), tags=(tag,))
                self.status_var.set(f"Concluido. Sucesso: {ok} | Falha: {fail}")
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)

    def _clear(self) -> None:
        self.orders_text.delete("1.0", tk.END)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.status_var.set("Pronto. Informe ordens e execute.")


def main() -> int:
    root = tk.Tk()
    Iw32ConcluirPanel(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
