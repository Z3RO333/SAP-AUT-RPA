import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from _panel_utils import ensure_repo_root

ensure_repo_root()

from core.common.session_picker import pick_session
from core.me23n.alimentacao import load_lots_from_excel, run_job


class AlimentacaoPedidosPanel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Robo SAP ME23N - Alimentacao de Pedidos")
        self.root.geometry("980x720")
        self.root.minsize(980, 720)
        self.root.configure(bg="#f4f7fb")

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False
        self.imported_lots: list[dict] = []

        self.pedido_var = tk.StringVar()
        self.data_var = tk.StringVar()
        self.descricao_var = tk.StringVar(value="CAMAPUA")
        self.qtd_linhas_var = tk.StringVar(value="1")
        self.status_var = tk.StringVar(value="Pronto. Informe um pedido ou importe uma planilha.")

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
        ttk.Label(header, text="Robo SAP ME23N - Alimentacao", style="HeaderTitle.TLabel").place(x=24, y=18)
        ttk.Label(
            header,
            text="Copia item do pedido, ajusta data e preenche servicos/AUFNR em lote.",
            style="HeaderText.TLabel",
        ).place(x=26, y=56)

        outer = ttk.Frame(self.root, style="Card.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=24, pady=22)

        manual = ttk.LabelFrame(outer, text="Entrada Manual", style="Section.TLabelframe", padding=12)
        manual.pack(fill="x")
        ttk.Label(manual, text="Pedido (EBELN)", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(manual, textvariable=self.pedido_var, width=24).grid(row=1, column=0, sticky="we", padx=(0, 12), pady=(4, 10))
        ttk.Label(manual, text="Data entrega (YYYY-MM-DD)", style="Muted.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Entry(manual, textvariable=self.data_var, width=20).grid(row=1, column=1, sticky="we", padx=(0, 12), pady=(4, 10))
        ttk.Label(manual, text="Descricao servico", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Entry(manual, textvariable=self.descricao_var, width=28).grid(row=1, column=2, sticky="we", padx=(0, 12), pady=(4, 10))
        ttk.Label(manual, text="Qtd linhas", style="Muted.TLabel").grid(row=0, column=3, sticky="w")
        ttk.Entry(manual, textvariable=self.qtd_linhas_var, width=10).grid(row=1, column=3, sticky="w", pady=(4, 10))

        orders_group = ttk.LabelFrame(outer, text="Ordens AUFNR", style="Section.TLabelframe", padding=12)
        orders_group.pack(fill="both", expand=True, pady=(14, 0))
        ttk.Label(orders_group, text="Uma por linha ou separadas por virgula.", style="Muted.TLabel").pack(anchor="w")
        text_frame = ttk.Frame(orders_group, style="Card.TFrame")
        text_frame.pack(fill="both", expand=True, pady=(4, 10))
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.orders_text = tk.Text(text_frame, height=8, font=("Consolas", 10), yscrollcommand=scrollbar.set)
        self.orders_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.orders_text.yview)

        actions = ttk.Frame(orders_group, style="Card.TFrame")
        actions.pack(fill="x")
        self.execute_button = ttk.Button(actions, text="Executar", command=self.start_execution, style="Accent.TButton")
        self.execute_button.pack(side="left")
        ttk.Button(actions, text="Importar Planilha", command=self._import_excel).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Limpar", command=self._clear).pack(side="left", padx=(8, 0))

        status_panel = ttk.Frame(outer, style="Status.TFrame", padding=10)
        status_panel.pack(fill="x", pady=(14, 10))
        ttk.Label(status_panel, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

        ttk.Label(outer, text="Resultados por pedido:", style="Muted.TLabel").pack(anchor="w")
        tree_frame = ttk.Frame(outer, style="Card.TFrame")
        tree_frame.pack(fill="both", expand=True, pady=(4, 0))
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical")
        tree_scroll.pack(side="right", fill="y")
        self.tree = ttk.Treeview(tree_frame, columns=("pedido", "resultado", "detalhe"), show="headings", yscrollcommand=tree_scroll.set)
        self.tree.heading("pedido", text="Pedido")
        self.tree.heading("resultado", text="Resultado")
        self.tree.heading("detalhe", text="Detalhe")
        self.tree.column("pedido", width=140, anchor="center")
        self.tree.column("resultado", width=110, anchor="center")
        self.tree.column("detalhe", width=560, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.config(command=self.tree.yview)
        self.tree.tag_configure("ok", foreground="#16a34a")
        self.tree.tag_configure("fail", foreground="#dc2626")

    def _manual_lot(self) -> list[dict]:
        pedido = self.pedido_var.get().strip()
        values = []
        raw = self.orders_text.get("1.0", tk.END)
        for line in raw.splitlines():
            values.extend(part.strip() for part in line.split(","))
        ordens = [value for value in values if value]
        if not pedido or not ordens:
            return []
        qtd_linhas = int(self.qtd_linhas_var.get().strip() or len(ordens))
        return [
            {
                "pedido": pedido,
                "data_entrega": self.data_var.get().strip(),
                "descricao_servico": self.descricao_var.get().strip(),
                "ordens_aufnr": ordens,
                "qtd_linhas": qtd_linhas,
            }
        ]

    def _import_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar planilha de pedidos",
            filetypes=[("Arquivos Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")],
        )
        if not path:
            return
        try:
            self.imported_lots = load_lots_from_excel(path)
            if not self.imported_lots:
                raise ValueError("Planilha sem dados validos.")
            sample = self.imported_lots[0]
            self.pedido_var.set(sample.get("pedido", ""))
            self.data_var.set(sample.get("data_entrega", ""))
            self.descricao_var.set(sample.get("descricao_servico", ""))
            self.orders_text.delete("1.0", tk.END)
            self.orders_text.insert("1.0", "\n".join(sample.get("ordens_aufnr", [])))
            self.status_var.set(f"Planilha carregada com {len(self.imported_lots)} pedido(s).")
        except Exception as exc:
            messagebox.showerror("Erro ao importar", str(exc))

    def start_execution(self) -> None:
        if self.is_running:
            return
        lots = self.imported_lots or self._manual_lot()
        if not lots:
            messagebox.showwarning("Validacao", "Informe um pedido e pelo menos uma ordem AUFNR.")
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.execute_button.config(state="disabled")
        self.is_running = True
        self.status_var.set(f"Executando... {len(lots)} pedido(s) a processar.")
        worker = threading.Thread(target=self._run, args=(lots,), daemon=True)
        worker.start()

    def _run(self, lots: list[dict]) -> None:
        try:
            result = run_job(
                {"lotes": lots},
                {
                    "allow_manual_login": True,
                    "interactive": True,
                    "session_chooser": lambda sessions: pick_session(sessions, self.root),
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
                    messagebox.showerror("Falha no robo ME23N", str(payload))
                    continue
                results = payload.get("business_result", {}).get("results", [])
                ok = sum(1 for item in results if item.get("success"))
                fail = len(results) - ok
                for item in results:
                    tag = "ok" if item.get("success") else "fail"
                    detail = item.get("message") or ""
                    label = "OK" if item.get("success") else "FALHA"
                    self.tree.insert("", tk.END, values=(item.get("pedido", ""), label, detail), tags=(tag,))
                self.status_var.set(f"Concluido. Sucesso: {ok} | Falha: {fail}")
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)

    def _clear(self) -> None:
        self.imported_lots = []
        self.pedido_var.set("")
        self.data_var.set("")
        self.descricao_var.set("CAMAPUA")
        self.qtd_linhas_var.set("1")
        self.orders_text.delete("1.0", tk.END)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.status_var.set("Pronto. Informe um pedido ou importe uma planilha.")


def main() -> int:
    root = tk.Tk()
    AlimentacaoPedidosPanel(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
