import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd

from _panel_utils import ensure_repo_root

ensure_repo_root()

from core.common.session_picker import pick_session
from core.iw32.categorias import category_names, run_job


class Iw32CategoriasPanel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Robo SAP IW32 - Categorias")
        self.root.geometry("980x760")
        self.root.minsize(980, 760)
        self.root.configure(bg="#f4f7fb")

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False

        categories = category_names() or ["GERADOR"]
        self.categoria_var = tk.StringVar(value=categories[0])
        self.numero_servico_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Pronto. Monte o lote manualmente ou importe uma planilha.")

        self._build_styles()
        self._build_layout(categories)
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

    def _build_layout(self, categories: list[str]) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", height=96)
        header.pack(fill="x")
        header.pack_propagate(False)
        ttk.Label(header, text="Robo SAP IW32 - Categorias", style="HeaderTitle.TLabel").place(x=24, y=18)
        ttk.Label(
            header,
            text="Preenche valores por categoria em lote via IW32 usando mapeamento externo em JSON.",
            style="HeaderText.TLabel",
        ).place(x=26, y=56)

        outer = ttk.Frame(self.root, style="Card.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=24, pady=22)

        form = ttk.LabelFrame(outer, text="Adicionar linha", style="Section.TLabelframe", padding=12)
        form.pack(fill="x")
        self.ordem_var = tk.StringVar()
        self.valor_var = tk.StringVar()
        ttk.Label(form, text="Ordem", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.ordem_var, width=18).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(4, 10))
        ttk.Label(form, text="Categoria", style="Muted.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Combobox(form, textvariable=self.categoria_var, values=categories, state="readonly", width=24).grid(row=1, column=1, sticky="w", padx=(0, 10), pady=(4, 10))
        ttk.Label(form, text="Valor", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.valor_var, width=16).grid(row=1, column=2, sticky="w", padx=(0, 10), pady=(4, 10))
        ttk.Label(form, text="Numero de servico (opcional)", style="Muted.TLabel").grid(row=0, column=3, sticky="w")
        ttk.Entry(form, textvariable=self.numero_servico_var, width=18).grid(row=1, column=3, sticky="w", pady=(4, 10))
        ttk.Button(form, text="Adicionar", command=self._add_row, style="Accent.TButton").grid(row=1, column=4, sticky="w", padx=(12, 0))

        batch = ttk.LabelFrame(outer, text="Lote", style="Section.TLabelframe", padding=12)
        batch.pack(fill="both", expand=True, pady=(14, 0))
        toolbar = ttk.Frame(batch, style="Card.TFrame")
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Importar planilha", command=self._import_excel).pack(side="left")
        ttk.Button(toolbar, text="Remover selecionada", command=self._remove_selected).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Limpar lote", command=self._clear_rows).pack(side="left", padx=(8, 0))
        self.execute_button = ttk.Button(toolbar, text="Executar", command=self.start_execution, style="Accent.TButton")
        self.execute_button.pack(side="left", padx=(8, 0))

        tree_frame = ttk.Frame(batch, style="Card.TFrame")
        tree_frame.pack(fill="both", expand=True, pady=(10, 0))
        scroll = ttk.Scrollbar(tree_frame, orient="vertical")
        scroll.pack(side="right", fill="y")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("ordem", "categoria", "valor", "numero_servico", "resultado", "detalhe"),
            show="headings",
            yscrollcommand=scroll.set,
        )
        for column, width in (
            ("ordem", 120),
            ("categoria", 180),
            ("valor", 100),
            ("numero_servico", 140),
            ("resultado", 100),
            ("detalhe", 320),
        ):
            self.tree.heading(column, text=column.replace("_", " ").title())
            self.tree.column(column, width=width, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.tree.yview)
        self.tree.tag_configure("ok", foreground="#16a34a")
        self.tree.tag_configure("fail", foreground="#dc2626")

        status_panel = ttk.Frame(outer, style="Status.TFrame", padding=10)
        status_panel.pack(fill="x", pady=(14, 0))
        ttk.Label(status_panel, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

    def _add_row(self) -> None:
        ordem = self.ordem_var.get().strip()
        categoria = self.categoria_var.get().strip()
        valor = self.valor_var.get().strip()
        numero_servico = self.numero_servico_var.get().strip()
        if not ordem or not categoria or not valor:
            messagebox.showwarning("Validacao", "Informe ordem, categoria e valor.")
            return
        self.tree.insert("", tk.END, values=(ordem, categoria, valor, numero_servico, "", ""))
        self.ordem_var.set("")
        self.valor_var.set("")

    def _import_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar planilha de categorias",
            filetypes=[("Arquivos Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")],
        )
        if not path:
            return
        try:
            df = pd.read_excel(path)
            column_map = {str(column).strip().upper(): column for column in df.columns}
            required = {"ORDEM", "CATEGORIA", "VALOR"}
            missing = sorted(required - set(column_map))
            if missing:
                raise ValueError(f"Colunas obrigatorias ausentes: {', '.join(missing)}")
            numero_col = column_map.get("NUMERO_SERVICO")
            self._clear_rows()
            imported = 0
            for _, row in df.iterrows():
                ordem = str(row[column_map["ORDEM"]]).strip()
                categoria = str(row[column_map["CATEGORIA"]]).strip().upper()
                valor = str(row[column_map["VALOR"]]).strip()
                numero_servico = str(row[numero_col]).strip() if numero_col else ""
                if not ordem or ordem.lower() == "nan":
                    continue
                self.tree.insert("", tk.END, values=(ordem, categoria, valor, numero_servico, "", ""))
                imported += 1
            self.status_var.set(f"Importado {imported} registro(s) da planilha.")
        except Exception as exc:
            messagebox.showerror("Erro ao importar", str(exc))

    def _rows(self) -> list[dict]:
        rows = []
        for item_id in self.tree.get_children():
            ordem, categoria, valor, numero_servico, _resultado, _detalhe = self.tree.item(item_id, "values")
            rows.append(
                {
                    "ordem": ordem,
                    "categoria": categoria,
                    "valor": valor,
                    "numero_servico": numero_servico,
                }
            )
        return rows

    def _remove_selected(self) -> None:
        for item_id in self.tree.selection():
            self.tree.delete(item_id)

    def _clear_rows(self) -> None:
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)

    def start_execution(self) -> None:
        if self.is_running:
            return
        rows = self._rows()
        if not rows:
            messagebox.showwarning("Validacao", "Adicione ou importe ao menos uma linha.")
            return
        for item_id in self.tree.get_children():
            values = list(self.tree.item(item_id, "values"))
            values[4] = ""
            values[5] = ""
            self.tree.item(item_id, values=values, tags=())
        self.is_running = True
        self.execute_button.config(state="disabled")
        self.status_var.set(f"Executando... {len(rows)} linha(s) a processar.")
        worker = threading.Thread(target=self._run, args=(rows,), daemon=True)
        worker.start()

    def _run(self, rows: list[dict]) -> None:
        try:
            result = run_job(
                {"rows": rows},
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
                    messagebox.showerror("Falha no robo IW32 Categorias", str(payload))
                    continue
                results = payload.get("business_result", {}).get("results", [])
                items = self.tree.get_children()
                for index, result_item in enumerate(results):
                    if index >= len(items):
                        break
                    item_id = items[index]
                    values = list(self.tree.item(item_id, "values"))
                    values[4] = "OK" if result_item.get("success") else "FALHA"
                    values[5] = result_item.get("statusBar") or result_item.get("error") or ""
                    tag = "ok" if result_item.get("success") else "fail"
                    self.tree.item(item_id, values=values, tags=(tag,))
                ok = sum(1 for item in results if item.get("success"))
                fail = len(results) - ok
                self.status_var.set(f"Concluido. Sucesso: {ok} | Falha: {fail}")
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)


def main() -> int:
    root = tk.Tk()
    Iw32CategoriasPanel(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
