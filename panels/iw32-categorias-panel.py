import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd

from _panel_utils import ensure_repo_root, pick_session_thread_safe, result_failure_message

ensure_repo_root()

from core.iw32.categorias import configured_category_names, normalize_category_name, run_job
from core.iw32.categorias_input import TIPO_CATEGORIA_MAP, parse_group_orders, parse_manual_rows, tipo_para_categoria


class Iw32CategoriasPanel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Robo SAP IW32 - Categorias")
        self.root.geometry("1040x860")
        self.root.minsize(1040, 860)
        self.root.configure(bg="#f4f7fb")

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False
        self._configured_categories_cache: set[str] | None = None

        self.tipo_var = tk.StringVar(value="Preventiva")
        self.valor_var = tk.StringVar()
        self.numero_servico_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Pronto. Use grupo para valor unico ou colagem linha a linha para valores diferentes.")

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
        ttk.Label(header, text="Robo SAP IW32 - Categorias", style="HeaderTitle.TLabel").place(x=24, y=18)
        ttk.Label(
            header,
            text="Use 'Adicionar grupo' para valor unico ou 'Colar linhas' para valores diferentes por ordem.",
            style="HeaderText.TLabel",
        ).place(x=26, y=56)

        outer = ttk.Frame(self.root, style="Card.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=24, pady=22)

        defaults = ttk.LabelFrame(outer, text="Padroes", style="Section.TLabelframe", padding=12)
        defaults.pack(fill="x")
        defaults.columnconfigure(0, weight=1)
        defaults.columnconfigure(1, weight=1)
        ttk.Label(
            defaults,
            text="Tipo e numero de servico valem para ambos os fluxos. Na colagem linha a linha, eles sao usados quando nao vierem na propria linha.",
            style="Muted.TLabel",
            wraplength=860,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(defaults, text="Tipo padrao", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Combobox(
            defaults,
            textvariable=self.tipo_var,
            values=list(TIPO_CATEGORIA_MAP.keys()),
            state="readonly",
            width=22,
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Label(defaults, text="Numero de servico padrao (opcional)", style="Muted.TLabel").grid(row=1, column=1, sticky="w", pady=(10, 0))
        ttk.Entry(defaults, textvariable=self.numero_servico_var, width=24).grid(row=2, column=1, sticky="w", pady=(4, 0))

        group = ttk.LabelFrame(outer, text="Adicionar grupo", style="Section.TLabelframe", padding=12)
        group.pack(fill="x", pady=(14, 0))
        group.columnconfigure(0, weight=1)

        left = ttk.Frame(group, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        ttk.Label(
            left,
            text="Use este bloco quando varias ordens receberem o mesmo valor. Aceita uma ordem por linha: ordem ou ordem, nome/local.",
            style="Muted.TLabel",
            wraplength=620,
            justify="left",
        ).pack(anchor="w")
        group_text_frame = ttk.Frame(left, style="Card.TFrame")
        group_text_frame.pack(fill="both", expand=True, pady=(6, 0))
        group_scroll = ttk.Scrollbar(group_text_frame, orient="vertical")
        group_scroll.pack(side="right", fill="y")
        self.ordens_text = tk.Text(
            group_text_frame,
            height=5,
            width=48,
            font=("Consolas", 9),
            relief="solid",
            borderwidth=1,
            yscrollcommand=group_scroll.set,
        )
        self.ordens_text.pack(side="left", fill="both", expand=True)
        group_scroll.config(command=self.ordens_text.yview)

        right = ttk.Frame(group, style="Card.TFrame")
        right.grid(row=0, column=1, sticky="n")
        ttk.Label(right, text="Valor do grupo", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(right, textvariable=self.valor_var, width=24).grid(row=1, column=0, sticky="w", pady=(4, 8))
        ttk.Button(right, text="Adicionar grupo", command=self._add_group_rows, style="Accent.TButton").grid(row=2, column=0, sticky="w")

        manual = ttk.LabelFrame(outer, text="Colar linhas", style="Section.TLabelframe", padding=12)
        manual.pack(fill="x", pady=(14, 0))
        ttk.Label(
            manual,
            text="Use este bloco quando cada ordem tiver valor proprio. Uma linha por ordem; separadores aceitos: TAB, ';', ',', '|', ou ordem + valor separados por espacos.",
            style="Muted.TLabel",
            wraplength=900,
            justify="left",
        ).pack(anchor="w")
        ttk.Label(
            manual,
            text="Formato: ordem | valor, ou ordem | nome/local | valor. Tipo e numero_servico sao opcionais; se nao vierem, usa os padroes acima.",
            style="Muted.TLabel",
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))
        manual_text_frame = ttk.Frame(manual, style="Card.TFrame")
        manual_text_frame.pack(fill="both", expand=True, pady=(6, 8))
        manual_scroll = ttk.Scrollbar(manual_text_frame, orient="vertical")
        manual_scroll.pack(side="right", fill="y")
        self.manual_rows_text = tk.Text(
            manual_text_frame,
            height=6,
            width=48,
            font=("Consolas", 9),
            relief="solid",
            borderwidth=1,
            yscrollcommand=manual_scroll.set,
        )
        self.manual_rows_text.pack(side="left", fill="both", expand=True)
        manual_scroll.config(command=self.manual_rows_text.yview)
        ttk.Button(manual, text="Adicionar linhas ao lote", command=self._add_manual_rows, style="Accent.TButton").pack(anchor="w")

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
            columns=("ordem", "nome", "categoria", "valor", "numero_servico", "resultado", "detalhe"),
            show="headings",
            yscrollcommand=scroll.set,
        )
        for column, heading, width in (
            ("ordem", "Ordem", 110),
            ("nome", "Nome / Local", 190),
            ("categoria", "Categoria", 220),
            ("valor", "Valor", 100),
            ("numero_servico", "Nr. Servico", 110),
            ("resultado", "Resultado", 90),
            ("detalhe", "Detalhe", 240),
        ):
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.tree.yview)
        self.tree.tag_configure("ok", foreground="#16a34a")
        self.tree.tag_configure("fail", foreground="#dc2626")

        status_panel = ttk.Frame(outer, style="Status.TFrame", padding=10)
        status_panel.pack(fill="x", pady=(14, 0))
        ttk.Label(status_panel, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

    def _configured_categories(self) -> set[str]:
        if self._configured_categories_cache is None:
            self._configured_categories_cache = set(configured_category_names())
        return self._configured_categories_cache

    def _default_category(self) -> str:
        return tipo_para_categoria(self.tipo_var.get().strip())

    def _category_errors(self, categories: list[str]) -> list[str]:
        configured = self._configured_categories()
        invalid = sorted({normalize_category_name(value) for value in categories if normalize_category_name(value) not in configured})
        return invalid

    def _show_category_error(self, invalid_categories: list[str]) -> None:
        categories = ", ".join(invalid_categories)
        messagebox.showerror(
            "Layout de categorias",
            f"Categoria(s) sem campo configurado no layout IW32-CATEGORIAS: {categories}",
        )

    def _insert_batch_row(self, *, ordem: str, nome: str, categoria: str, valor: str, numero_servico: str) -> None:
        self.tree.insert("", tk.END, values=(ordem, nome, categoria, valor, numero_servico, "", ""))

    def _show_import_feedback(self, added: int, errors: list[dict[str, object]], *, source_label: str) -> None:
        summary = f"{added} linha(s) adicionada(s) ao lote via {source_label}."
        if errors:
            line_numbers = ", ".join(str(item["line_number"]) for item in errors[:10])
            if len(errors) > 10:
                line_numbers = f"{line_numbers}, ..."
            summary = f"{summary} {len(errors)} com erro: linhas {line_numbers}."
            details = "\n".join(f"Linha {item['line_number']}: {item['message']}" for item in errors[:8])
            if len(errors) > 8:
                details = f"{details}\n... e mais {len(errors) - 8} linha(s)."
            messagebox.showwarning("Importacao parcial", details, parent=self.root)
        self.status_var.set(summary)

    def _add_group_rows(self) -> None:
        raw = self.ordens_text.get("1.0", tk.END)
        valor = self.valor_var.get().strip()
        if not raw.strip() or not valor:
            messagebox.showwarning("Validacao", "Cole ao menos uma ordem e informe o valor.")
            return

        categoria = self._default_category()
        invalid_categories = self._category_errors([categoria])
        if invalid_categories:
            self._show_category_error(invalid_categories)
            return

        parsed_rows, errors = parse_group_orders(raw)
        for row in parsed_rows:
            self._insert_batch_row(
                ordem=row["ordem"],
                nome=row["nome"],
                categoria=categoria,
                valor=valor,
                numero_servico=self.numero_servico_var.get().strip(),
            )
        if parsed_rows:
            self.ordens_text.delete("1.0", tk.END)
        self._show_import_feedback(len(parsed_rows), errors, source_label="grupo")

    def _add_manual_rows(self) -> None:
        raw = self.manual_rows_text.get("1.0", tk.END)
        if not raw.strip():
            messagebox.showwarning("Validacao", "Cole ao menos uma linha no bloco 'Colar linhas'.")
            return

        rows, errors = parse_manual_rows(
            raw,
            default_tipo=self.tipo_var.get().strip(),
            default_numero_servico=self.numero_servico_var.get().strip(),
            allowed_categories=self._configured_categories(),
        )
        for row in rows:
            self._insert_batch_row(
                ordem=row["ordem"],
                nome=row["nome"],
                categoria=row["categoria"],
                valor=row["valor"],
                numero_servico=row["numero_servico"],
            )
        if rows:
            self.manual_rows_text.delete("1.0", tk.END)
        self._show_import_feedback(len(rows), errors, source_label="colagem manual")

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
            required = {"ORDEM", "VALOR"}
            if "CATEGORIA" not in column_map and "TIPO" not in column_map:
                raise ValueError("Colunas obrigatorias ausentes: CATEGORIA ou TIPO")
            missing = sorted(required - set(column_map))
            if missing:
                raise ValueError(f"Colunas obrigatorias ausentes: {', '.join(missing)}")

            numero_col = column_map.get("NUMERO_SERVICO")
            imported_rows: list[dict[str, str]] = []
            errors: list[dict[str, object]] = []
            configured = self._configured_categories()

            for excel_row_number, (_, row) in enumerate(df.iterrows(), start=2):
                ordem = self._excel_text(row[column_map["ORDEM"]], numeric=True)
                valor = self._excel_text(row[column_map["VALOR"]])
                numero_servico = self._excel_text(row[numero_col], numeric=True) if numero_col else ""
                if "TIPO" in column_map:
                    categoria = tipo_para_categoria(self._excel_text(row[column_map["TIPO"]]))
                else:
                    categoria = normalize_category_name(self._excel_text(row[column_map["CATEGORIA"]]))

                if not ordem:
                    continue
                if not ordem.isdigit():
                    errors.append(
                        {
                            "line_number": excel_row_number,
                            "message": "Ordem deve conter apenas numeros.",
                        }
                    )
                    continue
                if not valor:
                    errors.append(
                        {
                            "line_number": excel_row_number,
                            "message": "Valor obrigatorio.",
                        }
                    )
                    continue
                if categoria not in configured:
                    errors.append(
                        {
                            "line_number": excel_row_number,
                            "message": f"Categoria nao configurada no layout: {categoria}.",
                        }
                    )
                    continue

                imported_rows.append(
                    {
                        "ordem": ordem,
                        "nome": "",
                        "categoria": categoria,
                        "valor": valor,
                        "numero_servico": numero_servico,
                    }
                )

            self._clear_rows()
            for row in imported_rows:
                self._insert_batch_row(**row)
            self._show_import_feedback(len(imported_rows), errors, source_label="planilha")
        except Exception as exc:
            messagebox.showerror("Erro ao importar", str(exc))

    def _rows(self) -> list[dict[str, str]]:
        rows = []
        for item_id in self.tree.get_children():
            ordem, _nome, categoria, valor, numero_servico, _resultado, _detalhe = self.tree.item(item_id, "values")
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

        invalid_categories = self._category_errors([row["categoria"] for row in rows])
        if invalid_categories:
            self._show_category_error(invalid_categories)
            return

        if not self.numero_servico_var.get().strip():
            ordens_sem_servico = [row["ordem"] for row in rows if not row["numero_servico"]]
            if ordens_sem_servico:
                lista = ", ".join(ordens_sem_servico[:20])
                if len(ordens_sem_servico) > 20:
                    lista = f"{lista}, ..."
                messagebox.showerror(
                    "Numero de servico ausente",
                    f"{len(ordens_sem_servico)} ordem(ns) sem numero de servico:\n{lista}\n\nPreencha o numero de servico padrao ou informe por linha antes de executar.",
                )
                return

        for item_id in self.tree.get_children():
            values = list(self.tree.item(item_id, "values"))
            values[5] = ""
            values[6] = ""
            self.tree.item(item_id, values=values, tags=())
        self.is_running = True
        self.execute_button.config(state="disabled")
        self.status_var.set(f"Executando... {len(rows)} linha(s) a processar.")
        worker = threading.Thread(target=self._run, args=(rows,), daemon=True)
        worker.start()

    def _run(self, rows: list[dict[str, str]]) -> None:
        try:
            result = run_job(
                {"rows": rows},
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
                    messagebox.showerror("Falha no robo IW32 Categorias", str(payload))
                    continue
                failure_message = result_failure_message(payload)
                if failure_message:
                    self.status_var.set(f"Falha: {failure_message}")
                    messagebox.showerror("Falha no robo IW32 Categorias", failure_message)
                    continue
                results = payload.get("business_result", {}).get("results", [])
                items = self.tree.get_children()
                for index, result_item in enumerate(results):
                    if index >= len(items):
                        break
                    item_id = items[index]
                    values = list(self.tree.item(item_id, "values"))
                    values[5] = "OK" if result_item.get("success") else "FALHA"
                    values[6] = result_item.get("statusBar") or result_item.get("error") or ""
                    tag = "ok" if result_item.get("success") else "fail"
                    self.tree.item(item_id, values=values, tags=(tag,))
                ok = sum(1 for item in results if item.get("success"))
                fail = len(results) - ok
                self.status_var.set(f"Concluido. Sucesso: {ok} | Falha: {fail}")
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)

    @staticmethod
    def _excel_text(value, *, numeric: bool = False) -> str:
        if pd.isna(value):
            return ""
        if numeric and isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()


def main() -> int:
    root = tk.Tk()
    Iw32CategoriasPanel(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
