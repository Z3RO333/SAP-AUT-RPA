import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from _panel_utils import ensure_repo_root, pick_session_thread_safe, result_failure_message

ensure_repo_root()

from core.me23n.alimentacao import (
    load_lots_from_excel,
    load_me22n_from_excel,
    run_job,
    run_job_me22n,
)


# ---------------------------------------------------------------------------
# Helpers de parse
# ---------------------------------------------------------------------------

def _looks_like_aufnr(value: str) -> bool:
    digits = "".join(ch for ch in str(value or "").strip() if ch.isdigit())
    return len(digits) >= 7


def _parse_linha(line: str, sakto_default: str) -> dict | None:
    """
    Parseia uma linha de dados de servico. Separadores aceitos: tab ou pipe (|).
    Formatos aceitos:
      AUFNR [SEP VALOR [SEP DESCRICAO [SEP SAKTO]]]
      DESCRICAO [SEP VALOR [SEP AUFNR [SEP SAKTO]]]
    """
    line = line.strip()
    if not line:
        return None
    if "\t" in line:
        parts = [p.strip() for p in line.split("\t")]
    elif "|" in line:
        parts = [p.strip() for p in line.split("|")]
    else:
        parts = [line.strip()]

    first = parts[0] if len(parts) > 0 else ""
    second = parts[1] if len(parts) > 1 else ""
    third = parts[2] if len(parts) > 2 else ""
    sakto = parts[3] if len(parts) > 3 else sakto_default

    # Novo formato: DESCRICAO | VALOR | AUFNR
    if third and _looks_like_aufnr(third) and not _looks_like_aufnr(first):
        descricao = first
        valor = second
        aufnr = third
    else:
        aufnr = first
        valor = second
        descricao = third

    if not aufnr:
        return None
    return {"aufnr": aufnr, "valor": valor, "descricao": descricao, "sakto": sakto}


def _parse_linhas_textarea(raw: str, sakto_default: str) -> list[dict]:
    """Parseia todas as linhas do textarea como linhas de servico simples."""
    linhas = []
    for line in raw.splitlines():
        linha = _parse_linha(line.strip(), sakto_default)
        if linha:
            linhas.append(linha)
    return linhas


# ---------------------------------------------------------------------------
# Panel principal
# ---------------------------------------------------------------------------

class AlimentacaoPedidosPanel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Robo SAP - Alimentacao de Pedidos (ME23N / ME22N)")
        self.root.geometry("1020x760")
        self.root.minsize(980, 720)
        self.root.configure(bg="#f4f7fb")

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False
        self.imported_lots: list[dict] = []

        # ME23N vars
        self.pedido_var = tk.StringVar()
        self.data_var = tk.StringVar()
        self.descricao_var = tk.StringVar(value="CAMAPUA")
        self.qtd_linhas_var = tk.StringVar(value="1")

        # ME22N vars
        self.pedido22_var = tk.StringVar()
        self.srvpos_var = tk.StringVar()
        self.sakto_var = tk.StringVar()
        self.imposto_var = tk.StringVar(value="S2")
        self._itens_acumulados: list[dict] = []  # [{item, linhas}]

        self.status_var = tk.StringVar(value="Pronto.")

        self._build_styles()
        self._build_layout()
        self._poll_queue()

    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", height=96)
        header.pack(fill="x")
        header.pack_propagate(False)
        ttk.Label(header, text="Robo SAP - Alimentacao de Pedidos", style="HeaderTitle.TLabel").place(x=24, y=18)
        ttk.Label(
            header,
            text="ME23N: copia item e preenche AUFNR.  ME22N: preenche linhas completas de servico.",
            style="HeaderText.TLabel",
        ).place(x=26, y=56)

        outer = ttk.Frame(self.root, style="Card.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=24, pady=14)

        # Notebook com abas ME23N / ME22N
        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)

        tab23 = ttk.Frame(self.notebook, style="Card.TFrame", padding=10)
        tab22 = ttk.Frame(self.notebook, style="Card.TFrame", padding=10)
        self.notebook.add(tab23, text="  ME23N — Alimentar AUFNR  ")
        self.notebook.add(tab22, text="  ME22N — Servicos Completos  ")

        self._build_tab_me23n(tab23)
        self._build_tab_me22n(tab22)

        # Status bar
        status_panel = ttk.Frame(outer, style="Status.TFrame", padding=8)
        status_panel.pack(fill="x", pady=(10, 4))
        ttk.Label(status_panel, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

        # Resultados
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
        self.tree.column("detalhe", width=600, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.config(command=self.tree.yview)
        self.tree.tag_configure("ok", foreground="#16a34a")
        self.tree.tag_configure("fail", foreground="#dc2626")

    # ------------------------------------------------------------------
    def _build_tab_me23n(self, parent) -> None:
        manual = ttk.LabelFrame(parent, text="Entrada Manual", style="Section.TLabelframe", padding=12)
        manual.pack(fill="x")

        ttk.Label(manual, text="Pedido (EBELN)", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(manual, textvariable=self.pedido_var, width=24).grid(row=1, column=0, sticky="we", padx=(0, 12), pady=(4, 10))
        ttk.Label(manual, text="Data entrega (YYYY-MM-DD)", style="Muted.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Entry(manual, textvariable=self.data_var, width=20).grid(row=1, column=1, sticky="we", padx=(0, 12), pady=(4, 10))
        ttk.Label(manual, text="Descricao servico", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Entry(manual, textvariable=self.descricao_var, width=28).grid(row=1, column=2, sticky="we", padx=(0, 12), pady=(4, 10))
        ttk.Label(manual, text="Qtd linhas", style="Muted.TLabel").grid(row=0, column=3, sticky="w")
        ttk.Entry(manual, textvariable=self.qtd_linhas_var, width=10).grid(row=1, column=3, sticky="w", pady=(4, 10))

        orders_group = ttk.LabelFrame(parent, text="Ordens AUFNR", style="Section.TLabelframe", padding=12)
        orders_group.pack(fill="both", expand=True, pady=(14, 0))
        ttk.Label(orders_group, text="Uma por linha ou separadas por virgula.", style="Muted.TLabel").pack(anchor="w")
        text_frame = ttk.Frame(orders_group, style="Card.TFrame")
        text_frame.pack(fill="both", expand=True, pady=(4, 10))
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.orders_text = tk.Text(text_frame, height=10, font=("Consolas", 10), yscrollcommand=scrollbar.set)
        self.orders_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.orders_text.yview)

        actions = ttk.Frame(orders_group, style="Card.TFrame")
        actions.pack(fill="x")
        self.execute_btn23 = ttk.Button(actions, text="Executar ME23N", command=self._start_me23n, style="Accent.TButton")
        self.execute_btn23.pack(side="left")
        ttk.Button(actions, text="Importar Planilha", command=self._import_excel_me23n).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Limpar", command=self._clear_me23n).pack(side="left", padx=(8, 0))

    # ------------------------------------------------------------------
    def _build_tab_me22n(self, parent) -> None:
        header_group = ttk.LabelFrame(parent, text="Dados do Pedido", style="Section.TLabelframe", padding=12)
        header_group.pack(fill="x")

        ttk.Label(header_group, text="Pedido (EBELN)", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(header_group, textvariable=self.pedido22_var, width=22).grid(row=1, column=0, sticky="we", padx=(0, 12), pady=(4, 10))

        ttk.Label(header_group, text="Nr Servico (SRVPOS)", style="Muted.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Entry(header_group, textvariable=self.srvpos_var, width=16).grid(row=1, column=1, sticky="we", padx=(0, 12), pady=(4, 10))

        ttk.Label(header_group, text="Conta GL (SAKTO)", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Entry(header_group, textvariable=self.sakto_var, width=14).grid(row=1, column=2, sticky="we", padx=(0, 12), pady=(4, 10))

        ttk.Label(header_group, text="Codigo Imposto", style="Muted.TLabel").grid(row=0, column=3, sticky="w")
        ttk.Entry(header_group, textvariable=self.imposto_var, width=8).grid(row=1, column=3, sticky="w", pady=(4, 10))

        lines_group = ttk.LabelFrame(parent, text="Linhas de Servico", style="Section.TLabelframe", padding=12)
        lines_group.pack(fill="both", expand=True, pady=(14, 0))
        ttk.Label(
            lines_group,
            text="Cole do Excel (tab) ou pipe: AUFNR  VALOR  DESCRICAO  ou  DESCRICAO  VALOR  AUFNR",
            style="Muted.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            lines_group,
            text="Cole as linhas de um grupo, clique 'Adicionar Item', repita para o proximo grupo e depois 'Executar'.",
            style="Muted.TLabel",
        ).pack(anchor="w")

        text_frame22 = ttk.Frame(lines_group, style="Card.TFrame")
        text_frame22.pack(fill="both", expand=True, pady=(4, 6))
        scrollbar22 = ttk.Scrollbar(text_frame22, orient="vertical")
        scrollbar22.pack(side="right", fill="y")
        self.lines_text = tk.Text(text_frame22, height=10, font=("Consolas", 10), yscrollcommand=scrollbar22.set)
        self.lines_text.pack(side="left", fill="both", expand=True)
        scrollbar22.config(command=self.lines_text.yview)

        # Label mostrando itens acumulados
        self._itens_label_var = tk.StringVar(value="Nenhum grupo adicionado.")
        ttk.Label(lines_group, textvariable=self._itens_label_var, style="Muted.TLabel").pack(anchor="w", pady=(0, 6))

        # Botoes principais
        actions22 = ttk.Frame(lines_group, style="Card.TFrame")
        actions22.pack(fill="x")
        self._adicionar_btn = ttk.Button(actions22, text="+ Adicionar Item", command=self._adicionar_item_me22n, style="Accent.TButton")
        self._adicionar_btn.pack(side="left")
        ttk.Button(actions22, text="Desfazer Ultimo", command=self._desfazer_ultimo_me22n).pack(side="left", padx=(6, 0))
        ttk.Separator(actions22, orient="vertical").pack(side="left", padx=10, fill="y")
        self.execute_btn22 = ttk.Button(actions22, text="Executar ME22N", command=self._start_me22n, style="Accent.TButton")
        self.execute_btn22.pack(side="left")
        ttk.Button(actions22, text="Importar Planilha", command=self._import_excel_me22n).pack(side="left", padx=(6, 0))
        ttk.Button(actions22, text="Limpar Tudo", command=self._clear_me22n).pack(side="left", padx=(6, 0))

    # ------------------------------------------------------------------
    # ME23N execution
    # ------------------------------------------------------------------

    def _manual_lot_me23n(self) -> list[dict]:
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

    def _import_excel_me23n(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar planilha ME23N",
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
            self.status_var.set(f"Planilha ME23N carregada com {len(self.imported_lots)} pedido(s).")
        except Exception as exc:
            messagebox.showerror("Erro ao importar", str(exc))

    def _start_me23n(self) -> None:
        if self.is_running:
            return
        lots = self.imported_lots or self._manual_lot_me23n()
        if not lots:
            messagebox.showwarning("Validacao", "Informe um pedido e pelo menos uma ordem AUFNR.")
            return
        self._reset_results()
        self.execute_btn23.config(state="disabled")
        self.execute_btn22.config(state="disabled")
        self.is_running = True
        self.status_var.set(f"Executando ME23N... {len(lots)} pedido(s).")
        threading.Thread(target=self._run_me23n, args=(lots,), daemon=True).start()

    def _run_me23n(self, lots: list[dict]) -> None:
        try:
            result = run_job(
                {"lotes": lots},
                {
                    "allow_manual_login": True,
                    "interactive": True,
                    "session_chooser": lambda sessions: pick_session_thread_safe(self.root, sessions),
                },
                {
                    "log": lambda msg: self.result_queue.put(("log", msg)),
                    "progress": lambda stage, cur, tot: self.result_queue.put(("progress", (stage, cur, tot))),
                    "is_cancelled": lambda: False,
                },
            )
            self.result_queue.put(("success", result.to_dict()))
        except Exception as exc:
            self.result_queue.put(("error", str(exc)))

    # ------------------------------------------------------------------
    # ME22N acumulador de itens
    # ------------------------------------------------------------------

    def _atualizar_label_itens(self) -> None:
        if not self._itens_acumulados:
            self._itens_label_var.set("Nenhum grupo adicionado.")
            return
        partes = [f"Grupo {index} ({len(g['linhas'])} linha(s))" for index, g in enumerate(self._itens_acumulados, start=1)]
        self._itens_label_var.set("Grupos: " + " | ".join(partes))

    def _adicionar_item_me22n(self) -> None:
        sakto = self.sakto_var.get().strip()
        raw = self.lines_text.get("1.0", tk.END)
        linhas = _parse_linhas_textarea(raw, sakto)
        if not linhas:
            messagebox.showwarning("Validacao", "Nenhuma linha valida no campo de texto.")
            return
        proximo_grupo = str(len(self._itens_acumulados) + 1)
        self._itens_acumulados.append({"item": proximo_grupo, "linhas": linhas})
        self.lines_text.delete("1.0", tk.END)
        self._atualizar_label_itens()

    def _desfazer_ultimo_me22n(self) -> None:
        if not self._itens_acumulados:
            return
        ultimo = self._itens_acumulados.pop()
        # Restaura linhas do item desfeito no textarea
        self.lines_text.delete("1.0", tk.END)
        for l in ultimo.get("linhas", []):
            parts = [l.get("aufnr", ""), l.get("valor", ""), l.get("descricao", "")]
            self.lines_text.insert(tk.END, "\t".join(p for p in parts if p) + "\n")
        self._atualizar_label_itens()

    # ------------------------------------------------------------------
    # ME22N execution
    # ------------------------------------------------------------------

    def _manual_lote_me22n(self) -> list[dict] | None:
        pedido = self.pedido22_var.get().strip()
        srvpos = self.srvpos_var.get().strip()
        sakto = self.sakto_var.get().strip()
        imposto = self.imposto_var.get().strip()

        # Usa itens acumulados se houver; senao trata o textarea como item unico
        if self._itens_acumulados:
            itens = self._itens_acumulados
        else:
            raw = self.lines_text.get("1.0", tk.END)
            linhas = _parse_linhas_textarea(raw, sakto)
            if not linhas:
                return None
            itens = [{"item": "1", "linhas": linhas}]

        if not pedido:
            return None
        return [
            {
                "pedido": pedido,
                "srvpos_default": srvpos,
                "sakto_default": sakto,
                "cod_imposto": imposto,
                "itens": itens,
                "linhas": [],
            }
        ]

    def _import_excel_me22n(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar planilha ME22N",
            filetypes=[("Arquivos Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")],
        )
        if not path:
            return
        try:
            lotes = load_me22n_from_excel(path)
            if not lotes:
                raise ValueError("Planilha sem dados validos.")
            sample = lotes[0]
            self.pedido22_var.set(sample.get("pedido", ""))
            self.srvpos_var.set(sample.get("srvpos_default", ""))
            self.sakto_var.set(sample.get("sakto_default", ""))
            self.imposto_var.set(sample.get("cod_imposto", "S2"))
            linhas = sample.get("linhas", [])
            self.lines_text.delete("1.0", tk.END)
            for l in linhas:
                linha_str = l.get("aufnr", "")
                if l.get("valor"):
                    linha_str += f" | {l['valor']}"
                if l.get("descricao"):
                    linha_str += f" | {l['descricao']}"
                self.lines_text.insert(tk.END, linha_str + "\n")
            # Guarda todos os lotes para execucao em lote
            self._me22n_lots = lotes
            self.status_var.set(f"Planilha ME22N carregada: {len(lotes)} pedido(s), {len(linhas)} linhas no primeiro.")
        except Exception as exc:
            messagebox.showerror("Erro ao importar", str(exc))

    def _start_me22n(self) -> None:
        if self.is_running:
            return
        lots = getattr(self, "_me22n_lots", None) or self._manual_lote_me22n()
        if not lots:
            messagebox.showwarning("Validacao", "Informe o pedido e pelo menos uma linha (AUFNR).\nUse '+ Adicionar Item' ou cole diretamente e clique Executar.")
            return
        self._reset_results()
        self.execute_btn23.config(state="disabled")
        self.execute_btn22.config(state="disabled")
        self._adicionar_btn.config(state="disabled")
        self.is_running = True
        self.status_var.set(f"Executando ME22N... {len(lots)} pedido(s).")
        threading.Thread(target=self._run_me22n, args=(lots,), daemon=True).start()

    def _run_me22n(self, lots: list[dict]) -> None:
        try:
            result = run_job_me22n(
                {"lotes": lots},
                {
                    "allow_manual_login": True,
                    "interactive": True,
                    "session_chooser": lambda sessions: pick_session_thread_safe(self.root, sessions),
                },
                {
                    "log": lambda msg: self.result_queue.put(("log", msg)),
                    "progress": lambda stage, cur, tot: self.result_queue.put(("progress", (stage, cur, tot))),
                    "is_cancelled": lambda: False,
                },
            )
            self.result_queue.put(("success", result.to_dict()))
        except Exception as exc:
            self.result_queue.put(("error", str(exc)))

    # ------------------------------------------------------------------
    # Queue polling
    # ------------------------------------------------------------------

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
                self.execute_btn23.config(state="normal")
                self.execute_btn22.config(state="normal")
                self._adicionar_btn.config(state="normal")
                if status == "error":
                    self.status_var.set(f"Falha: {payload}")
                    messagebox.showerror("Falha no robo", str(payload))
                    continue
                failure_message = result_failure_message(payload)
                if failure_message:
                    self.status_var.set(f"Falha: {failure_message}")
                    messagebox.showerror("Falha no robo", failure_message)
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
                # Limpa acumulador apos execucao bem-sucedida
                self._itens_acumulados = []
                self._me22n_lots = []
                self._atualizar_label_itens()
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _reset_results(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _clear_me23n(self) -> None:
        self.imported_lots = []
        self.pedido_var.set("")
        self.data_var.set("")
        self.descricao_var.set("CAMAPUA")
        self.qtd_linhas_var.set("1")
        self.orders_text.delete("1.0", tk.END)
        self._reset_results()
        self.status_var.set("Pronto.")

    def _clear_me22n(self) -> None:
        self._me22n_lots = []
        self._itens_acumulados = []
        self.pedido22_var.set("")
        self.srvpos_var.set("")
        self.sakto_var.set("")
        self.imposto_var.set("S2")
        self.lines_text.delete("1.0", tk.END)
        self._atualizar_label_itens()
        self._reset_results()
        self.status_var.set("Pronto.")


def main() -> int:
    root = tk.Tk()
    AlimentacaoPedidosPanel(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
