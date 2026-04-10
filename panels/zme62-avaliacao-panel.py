import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from _panel_utils import ensure_repo_root

ensure_repo_root()

from core.common.session_picker import pick_session
from core.zme62.avaliacao import allowed_responses, normalize_response, run_job

# Number of evaluation questions shown in the form.
# The core always accepts a dynamic list — change this constant to add/remove fields.
NUM_RESPOSTAS = 4


class Zme62AvaliacaoPanel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Robo SAP - ZME62 Avaliacao de Fornecedores")
        self.root.geometry("920x780")
        self.root.minsize(860, 700)
        self.root.configure(bg="#f4f7fb")

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False

        # Group storage: iid (str) -> group dict
        self._groups: dict[str, dict] = {}
        self._group_counter = 0

        # Load allowed responses from profile, with fallback
        self._allowed_responses = self._load_allowed_responses()
        self._normalized_allowed = {normalize_response(r): r for r in self._allowed_responses}

        # Form variables
        self.ano_var = tk.StringVar()
        self.comentario_var = tk.StringVar()
        self.response_vars = [tk.StringVar(value=self._allowed_responses[0] if self._allowed_responses else "") for _ in range(NUM_RESPOSTAS)]
        self.status_var = tk.StringVar(value="Pronto. Configure os grupos e clique em Executar.")

        self._build_styles()
        self._build_layout()
        self._poll_queue()

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    def _load_allowed_responses(self) -> list[str]:
        try:
            return allowed_responses()
        except Exception:
            return ["SIM", "SIM, MELHORES CONDIÇÕES", "NAO", "TALVEZ"]

    # ------------------------------------------------------------------
    # Styles
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
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", height=96)
        header.pack(fill="x")
        header.pack_propagate(False)
        ttk.Label(header, text="Robo SAP - ZME62 Avaliacao de Fornecedores", style="HeaderTitle.TLabel").place(x=24, y=18)
        ttk.Label(
            header,
            text="Configure grupos de fornecedores com suas combinacoes de respostas e execute em lote.",
            style="HeaderText.TLabel",
        ).place(x=26, y=56)

        outer = ttk.Frame(self.root, style="Card.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=24, pady=14)

        self._build_form(outer)
        self._build_groups_section(outer)

        status_panel = ttk.Frame(outer, style="Status.TFrame", padding=10)
        status_panel.pack(fill="x", pady=(10, 0))
        ttk.Label(status_panel, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

    def _build_form(self, parent: ttk.Frame) -> None:
        form = ttk.LabelFrame(parent, text="Configurar Grupo", style="Section.TLabelframe", padding=12)
        form.pack(fill="x")

        # Row 0: Ano + Comentario
        row0 = ttk.Frame(form, style="Card.TFrame")
        row0.pack(fill="x")
        ttk.Label(row0, text="Ano", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(row0, textvariable=self.ano_var, width=10).grid(row=1, column=0, sticky="w", padx=(0, 16), pady=(4, 0))
        ttk.Label(row0, text="Comentario (opcional)", style="Muted.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Entry(row0, textvariable=self.comentario_var, width=52).grid(row=1, column=1, sticky="we", pady=(4, 0))
        row0.columnconfigure(1, weight=1)

        # Row 1: Response comboboxes
        respostas_frame = ttk.LabelFrame(form, text="Respostas (uma por pergunta)", style="Section.TLabelframe", padding=8)
        respostas_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(
            respostas_frame,
            text="Selecione a resposta correspondente a cada pergunta da avaliacao ZME62, na ordem em que aparecem na tela.",
            style="Muted.TLabel",
            wraplength=750,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))

        combos_frame = ttk.Frame(respostas_frame, style="Card.TFrame")
        combos_frame.pack(fill="x")
        for i, var in enumerate(self.response_vars):
            col_frame = ttk.Frame(combos_frame, style="Card.TFrame")
            col_frame.pack(side="left", padx=(0, 12))
            ttk.Label(col_frame, text=f"Pergunta {i + 1}", style="Muted.TLabel").pack(anchor="w")
            cb = ttk.Combobox(
                col_frame,
                textvariable=var,
                values=self._allowed_responses,
                state="readonly",
                width=26,
            )
            cb.pack(anchor="w", pady=(4, 0))

        # Row 2: Suppliers textarea
        fornecedores_frame = ttk.LabelFrame(form, text="Fornecedores (um por linha)", style="Section.TLabelframe", padding=8)
        fornecedores_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(
            fornecedores_frame,
            text="Cole os codigos de fornecedor, um por linha. Apenas numeros. Duplicidades sao bloqueadas.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 4))
        text_frame = ttk.Frame(fornecedores_frame, style="Card.TFrame")
        text_frame.pack(fill="x")
        scroll = ttk.Scrollbar(text_frame, orient="vertical")
        scroll.pack(side="right", fill="y")
        self.fornecedores_text = tk.Text(
            text_frame,
            height=5,
            width=30,
            font=("Consolas", 9),
            relief="solid",
            borderwidth=1,
            yscrollcommand=scroll.set,
        )
        self.fornecedores_text.pack(side="left", fill="x")
        scroll.config(command=self.fornecedores_text.yview)

        # Add group button
        btn_row = ttk.Frame(form, style="Card.TFrame")
        btn_row.pack(fill="x", pady=(10, 0))
        ttk.Button(btn_row, text="+ Adicionar Grupo", command=self._add_group, style="Accent.TButton").pack(side="left")

    def _build_groups_section(self, parent: ttk.Frame) -> None:
        section = ttk.LabelFrame(parent, text="Grupos Configurados", style="Section.TLabelframe", padding=12)
        section.pack(fill="both", expand=True, pady=(14, 0))

        toolbar = ttk.Frame(section, style="Card.TFrame")
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Remover selecionado", command=self._remove_group).pack(side="left")
        ttk.Button(toolbar, text="Limpar tudo", command=self._clear_groups).pack(side="left", padx=(8, 0))
        self.execute_button = ttk.Button(toolbar, text="Executar", command=self._start_execution, style="Accent.TButton")
        self.execute_button.pack(side="left", padx=(8, 0))

        tree_frame = ttk.Frame(section, style="Card.TFrame")
        tree_frame.pack(fill="both", expand=True, pady=(10, 0))
        scroll = ttk.Scrollbar(tree_frame, orient="vertical")
        scroll.pack(side="right", fill="y")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("grupo", "ano", "fornecedores", "respostas", "comentario"),
            show="headings",
            yscrollcommand=scroll.set,
        )
        for col, heading, width in (
            ("grupo", "#", 50),
            ("ano", "Ano", 70),
            ("fornecedores", "Fornecedores", 200),
            ("respostas", "Respostas", 280),
            ("comentario", "Comentario", 200),
        ):
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.tree.yview)

    # ------------------------------------------------------------------
    # Group management
    # ------------------------------------------------------------------

    def _parse_fornecedores(self) -> tuple[list[str], list[str]]:
        """Parse supplier textarea. Returns (valid_list, error_list)."""
        raw = self.fornecedores_text.get("1.0", tk.END)
        fornecedores = []
        errors = []
        seen: set[str] = set()
        for line in raw.splitlines():
            value = line.strip()
            if not value:
                continue
            if not value.isdigit():
                errors.append(f"'{value}' nao e numerico.")
                continue
            if value in seen:
                errors.append(f"'{value}' duplicado na lista.")
                continue
            seen.add(value)
            fornecedores.append(value)
        return fornecedores, errors

    def _all_existing_fornecedores(self) -> set[str]:
        """Collect all suppliers already registered across all groups."""
        existing: set[str] = set()
        for group in self._groups.values():
            existing.update(group["fornecedores"])
        return existing

    def _add_group(self) -> None:
        ano = self.ano_var.get().strip()
        respostas = [v.get().strip() for v in self.response_vars]
        comentario = self.comentario_var.get().strip()

        # Validate ano
        if not ano:
            messagebox.showwarning("Validacao", "Informe o ano da avaliacao.", parent=self.root)
            return
        if not ano.isdigit():
            messagebox.showwarning("Validacao", "Ano deve conter apenas numeros.", parent=self.root)
            return

        # Validate responses
        empty_respostas = [i + 1 for i, r in enumerate(respostas) if not r]
        if empty_respostas:
            messagebox.showwarning("Validacao", f"Selecione a resposta para a(s) pergunta(s): {empty_respostas}.", parent=self.root)
            return

        invalidos = [r for r in respostas if normalize_response(r) not in self._normalized_allowed]
        if invalidos:
            messagebox.showwarning(
                "Validacao",
                f"Resposta(s) invalida(s): {invalidos}\nValores permitidos: {self._allowed_responses}",
                parent=self.root,
            )
            return

        # Parse suppliers
        fornecedores, parse_errors = self._parse_fornecedores()
        if parse_errors:
            messagebox.showerror("Fornecedores invalidos", "\n".join(parse_errors), parent=self.root)
            return
        if not fornecedores:
            messagebox.showwarning("Validacao", "Cole ao menos um fornecedor.", parent=self.root)
            return

        # Check cross-group duplicates
        existing = self._all_existing_fornecedores()
        duplicates = [f for f in fornecedores if f in existing]
        if duplicates:
            messagebox.showerror(
                "Fornecedor duplicado",
                f"Os fornecedores a seguir ja existem em outro grupo:\n{', '.join(duplicates)}\n\n"
                "Um fornecedor pode pertencer a apenas um grupo por execucao.",
                parent=self.root,
            )
            return

        # Build group and insert into tree
        group_num = len(self._groups) + 1
        iid = str(self._group_counter)
        self._group_counter += 1

        group_data = {
            "ano": ano,
            "respostas": respostas,
            "comentario": comentario,
            "fornecedores": fornecedores,
        }
        self._groups[iid] = group_data

        forn_display = f"{len(fornecedores)} forn.: " + ", ".join(fornecedores[:4])
        if len(fornecedores) > 4:
            forn_display += ", ..."
        resp_display = " | ".join(respostas)
        self.tree.insert("", tk.END, iid=iid, values=(group_num, ano, forn_display, resp_display, comentario))

        # Clear textarea for next group
        self.fornecedores_text.delete("1.0", tk.END)
        total_forn = sum(len(g["fornecedores"]) for g in self._groups.values())
        self.status_var.set(f"{len(self._groups)} grupo(s) configurado(s) | {total_forn} fornecedor(es) no total.")

    def _remove_group(self) -> None:
        for iid in self.tree.selection():
            self._groups.pop(iid, None)
            self.tree.delete(iid)
        self._refresh_group_numbers()
        total_forn = sum(len(g["fornecedores"]) for g in self._groups.values())
        self.status_var.set(f"{len(self._groups)} grupo(s) | {total_forn} fornecedor(es).")

    def _clear_groups(self) -> None:
        self._groups.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.status_var.set("Grupos removidos.")

    def _refresh_group_numbers(self) -> None:
        """Update the group number column after removal."""
        for num, iid in enumerate(self.tree.get_children(), start=1):
            values = list(self.tree.item(iid, "values"))
            values[0] = num
            self.tree.item(iid, values=values)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _build_input_data(self) -> dict:
        groups = []
        for iid in self.tree.get_children():
            group = self._groups[iid]
            groups.append(group)
        return {"groups": groups}

    def _start_execution(self) -> None:
        if self.is_running:
            return
        if not self._groups:
            messagebox.showwarning("Validacao", "Adicione ao menos um grupo antes de executar.", parent=self.root)
            return

        input_data = self._build_input_data()
        total = sum(len(g["fornecedores"]) for g in input_data["groups"])

        self.is_running = True
        self.execute_button.config(state="disabled")
        self.status_var.set(f"Executando... {total} fornecedor(es) a processar.")
        threading.Thread(target=self._run, args=(input_data,), daemon=True).start()

    def _run(self, input_data: dict) -> None:
        try:
            result = run_job(
                input_data,
                {
                    "allow_manual_login": True,
                    "interactive": True,
                    "session_chooser": lambda sessions: pick_session(sessions, self.root),
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
                self.execute_button.config(state="normal")
                if status == "error":
                    self.status_var.set(f"Falha: {payload}")
                    messagebox.showerror("Falha no robo ZME62", str(payload), parent=self.root)
                    continue
                biz = payload.get("business_result", {})
                ok = biz.get("successCount", 0)
                fail = biz.get("failCount", 0)
                total_items = biz.get("totalItems", 0)
                self.status_var.set(f"Concluido. {total_items} processado(s) | Sucesso: {ok} | Falha: {fail}")
                if fail:
                    messagebox.showwarning(
                        "Execucao concluida com falhas",
                        f"{ok} fornecedor(es) avaliado(s) com sucesso.\n{fail} com falha.\n\nConsulte os logs para detalhes.",
                        parent=self.root,
                    )
                else:
                    messagebox.showinfo(
                        "Execucao concluida",
                        f"{ok} fornecedor(es) avaliado(s) com sucesso.",
                        parent=self.root,
                    )
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)


# ---------------------------------------------------------------------------

def main() -> int:
    root = tk.Tk()
    Zme62AvaliacaoPanel(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
