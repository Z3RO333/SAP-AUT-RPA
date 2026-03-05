import json
import queue
import re
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from _panel_utils import ensure_repo_root

ensure_repo_root()

from core.common.layout_maps import load_layout_map
from core.common.runtime import appdata_dir, ensure_dir, run_output_dir
from core.common.session_picker import pick_session


DEFAULTS_FILE = "me21n.defaults.json"
TAX_CODE_OPTIONS = ("S1", "S2")
DEFAULT_DEFAULTS = {
    "tipo_doc": "NB",
    "fornecedor": "",
    "condicao_pagamento": "0001",
    "org_compras": "1000",
    "grupo_compras": "112",
    "empresa": "BEM1",
    "moeda": "BRL",
    "grupo_mercadoria": "",
    "plant_or_center": "101",
    "texto_livre": "gerador",
    "tax_code": "S2",
    "categoria_item": "D",
    "categoria_classif": "F",
    "conta_razao_default": "",
}


def _sort_key(value: str) -> tuple[int, object]:
    text = str(value or "").strip()
    return (0, int(text)) if text.isdigit() else (1, text)


class Me21nPanel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Robo SAP ME21N - Criar Pedido")
        self.root.geometry("1360x860")
        self.root.minsize(1220, 760)
        self.root.configure(bg="#f4f7fb")
        try:
            self.root.state("zoomed")
        except tk.TclError:
            pass

        self.layout_map = load_layout_map("ME21N")
        self.profile_names = list(self.layout_map.get("profiles", {}).keys()) or ["service_item_fk"]
        self.profile_name = self.layout_map.get("defaultProfile", self.profile_names[0])
        self.profile = self.layout_map.get("profiles", {}).get(self.profile_name, {})
        self.profile_capabilities = self.profile.get("capabilities", {})

        defaults = self._merge_defaults(self.profile_name)

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False
        self._runner_api: dict[str, object] | None = None

        self.manual_items: list[dict] = []
        self.selected_item_ref: str | None = None
        self.selected_service_line_ref: str | None = None
        self.last_po_number: str = ""

        self.file_var = tk.StringVar()
        self.dry_run_var = tk.BooleanVar(value=False)
        self.profile_var = tk.StringVar(value=self.profile_name)
        self.status_var = tk.StringVar(
            value="Pronto. Modo guiado da ME21N para servico com item D e imputacao F ou K."
        )
        self.manual_mode_note = tk.StringVar(
            value="Use o modo guiado para preencher como na ME21N. Validar e Executar usam todas as linhas salvas. A selecao na grade serve para editar ou excluir linhas. Texto breve da linha e automatico pelo numero do servico. Preco bruto pode ficar em branco quando o layout usa valor automatico. Glossario: Tipo de imposto = codigo de imposto (MWSKZ); F = Ordem (AUFNR); K = Centro de custo (KOSTL)."
        )
        self.reference_label_var = tk.StringVar(value="Ordem (AUFNR)")

        self.default_vars = {
            "tipo_doc": tk.StringVar(value=defaults["tipo_doc"]),
            "fornecedor": tk.StringVar(value=defaults["fornecedor"]),
            "condicao_pagamento": tk.StringVar(value=defaults["condicao_pagamento"]),
            "org_compras": tk.StringVar(value=defaults["org_compras"]),
            "grupo_compras": tk.StringVar(value=defaults["grupo_compras"]),
            "empresa": tk.StringVar(value=defaults["empresa"]),
            "moeda": tk.StringVar(value=defaults["moeda"]),
            "grupo_mercadoria": tk.StringVar(value=defaults["grupo_mercadoria"]),
            "plant_or_center": tk.StringVar(value=defaults["plant_or_center"]),
            "tax_code": tk.StringVar(value=defaults["tax_code"]),
            "categoria_item": tk.StringVar(value="D"),
            "categoria_classif": tk.StringVar(value=defaults["categoria_classif"]),
            "conta_razao_default": tk.StringVar(value=defaults["conta_razao_default"]),
        }

        self.header_vars = {
            "doc_ref": tk.StringVar(),
            "tipo_doc": tk.StringVar(value=defaults["tipo_doc"]),
            "fornecedor": tk.StringVar(value=defaults["fornecedor"]),
            "condicao_pagamento": tk.StringVar(value=defaults["condicao_pagamento"]),
            "org_compras": tk.StringVar(value=defaults["org_compras"]),
            "grupo_compras": tk.StringVar(value=defaults["grupo_compras"]),
            "empresa": tk.StringVar(value=defaults["empresa"]),
            "moeda": tk.StringVar(value=defaults["moeda"]),
            "incoterms": tk.StringVar(),
            "texto_cabecalho": tk.StringVar(),
        }
        self.item_vars = {
            "item_ref": tk.StringVar(value="10"),
            "texto_livre": tk.StringVar(),
            "categoria_item": tk.StringVar(value="D"),
            "categoria_classif": tk.StringVar(value=defaults["categoria_classif"]),
            "grupo_mercadoria": tk.StringVar(value=defaults["grupo_mercadoria"]),
            "plant_or_center": tk.StringVar(value=defaults["plant_or_center"]),
            "tax_code": tk.StringVar(value=defaults["tax_code"]),
            "observacao_item": tk.StringVar(),
            "conta_razao_default": tk.StringVar(value=defaults["conta_razao_default"]),
        }
        self.service_vars = {
            "line_ref": tk.StringVar(value="10"),
            "numero_servico": tk.StringVar(),
            "quantidade": tk.StringVar(value="1"),
            "preco_bruto": tk.StringVar(),
            "conta_razao": tk.StringVar(),
        }
        self.reference_var = tk.StringVar()

        self._build_styles()
        self._build_layout()
        self._new_item_form()
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
        style.configure("Subtle.TButton", font=("Segoe UI", 9))

    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", height=96)
        header.pack(fill="x")
        header.pack_propagate(False)
        ttk.Label(header, text="Robo SAP ME21N - Criar Pedido", style="HeaderTitle.TLabel").place(x=24, y=18)
        ttk.Label(
            header,
            text="Modo guiado para servico com item D e classificacao F/K, sem perder o modo por planilha.",
            style="HeaderText.TLabel",
        ).place(x=26, y=56)

        wrapper = tk.Frame(self.root, bg="#f4f7fb")
        wrapper.pack(fill="both", expand=True, padx=24, pady=22)

        canvas = tk.Canvas(wrapper, bg="#f4f7fb", highlightthickness=0)
        scrollbar = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        outer = ttk.Frame(canvas, style="Card.TFrame", padding=18)
        canvas_window = canvas.create_window((0, 0), window=outer, anchor="nw")

        def _on_outer_configure(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event) -> None:
            canvas.itemconfigure(canvas_window, width=event.width)

        outer.bind("<Configure>", _on_outer_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"))

        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        controls = ttk.LabelFrame(outer, text="Execucao", style="Section.TLabelframe", padding=12)
        controls.grid(row=0, column=0, sticky="ew")
        ttk.Label(controls, text="Perfil de layout", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        profile_combo = ttk.Combobox(controls, textvariable=self.profile_var, values=self.profile_names, state="readonly", width=22)
        profile_combo.grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(4, 10))
        profile_combo.bind("<<ComboboxSelected>>", self._on_profile_changed)
        ttk.Checkbutton(controls, text="DRY_RUN (nao salva)", variable=self.dry_run_var).grid(
            row=1, column=1, sticky="w", padx=(0, 12), pady=(4, 10)
        )
        ttk.Button(controls, text="Validar", command=self.validate_current_input, style="Accent.TButton").grid(
            row=1, column=2, sticky="w", padx=(0, 8), pady=(4, 10)
        )
        ttk.Button(controls, text="Inspecionar tela SAP", command=self.inspect_sap, style="Subtle.TButton").grid(
            row=1, column=3, sticky="w", padx=(0, 8), pady=(4, 10)
        )
        self.execute_button = ttk.Button(controls, text="Executar", command=self.execute, style="Accent.TButton")
        self.execute_button.grid(row=1, column=4, sticky="w", pady=(4, 10))
        self.copy_po_button = ttk.Button(
            controls,
            text="Copiar pedido",
            command=self.copy_po_number,
            style="Subtle.TButton",
            state="disabled",
        )
        self.copy_po_button.grid(row=1, column=5, sticky="w", padx=(8, 0), pady=(4, 10))

        self.mode_notebook = ttk.Notebook(outer)
        self.mode_notebook.grid(row=1, column=0, sticky="nsew", pady=(14, 12))
        self.mode_notebook.bind("<<NotebookTabChanged>>", lambda _event: self._on_mode_changed())
        self.manual_tab = ttk.Frame(self.mode_notebook, style="Card.TFrame", padding=12)
        self.excel_tab = ttk.Frame(self.mode_notebook, style="Card.TFrame", padding=12)
        self.mode_notebook.add(self.manual_tab, text="Modo Guiado")
        self.mode_notebook.add(self.excel_tab, text="Planilha XLSX")
        self._build_manual_tab()
        self._build_excel_tab()

        status_panel = ttk.Frame(outer, style="Status.TFrame", padding=10)
        status_panel.grid(row=2, column=0, sticky="ew")
        ttk.Label(status_panel, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

        body = ttk.Frame(outer, style="Card.TFrame")
        body.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(body, font=("Consolas", 10), wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        right = ttk.Frame(body, style="Card.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        ttk.Label(right, text="Resumo / validacao", style="Muted.TLabel").pack(anchor="w")
        self.summary_text = scrolledtext.ScrolledText(right, font=("Consolas", 9), wrap="word", height=20)
        self.summary_text.pack(fill="both", expand=True)

    def _build_manual_tab(self) -> None:
        self.manual_tab.columnconfigure(0, weight=1)
        self.manual_tab.rowconfigure(2, weight=1)

        defaults_frame = ttk.LabelFrame(self.manual_tab, text="Padroes Editaveis", style="Section.TLabelframe", padding=12)
        defaults_frame.grid(row=0, column=0, sticky="ew")
        defaults_fields = [
            ("Tipo de documento", "tipo_doc", 0, 0, 16),
            ("Fornecedor", "fornecedor", 0, 2, 14),
            ("Condicao de pagamento", "condicao_pagamento", 0, 4, 16),
            ("Organizacao de compras", "org_compras", 1, 0, 18),
            ("Grupo de compras", "grupo_compras", 1, 2, 16),
            ("Empresa", "empresa", 1, 4, 12),
            ("Moeda", "moeda", 2, 0, 10),
            ("Grupo de mercadoria", "grupo_mercadoria", 2, 2, 20),
            ("Centro (planta)", "plant_or_center", 2, 4, 16),
            ("Tipo de imposto", "tax_code", 3, 0, 16),
            ("Classificacao contabil", "categoria_classif", 3, 2, 16),
            ("Conta contabil", "conta_razao_default", 3, 4, 16),
        ]
        for label, key, row, col, width in defaults_fields:
            ttk.Label(defaults_frame, text=label, style="Muted.TLabel").grid(row=row, column=col, sticky="w", padx=(0, 6), pady=(0, 4))
            if key == "categoria_classif":
                widget = ttk.Combobox(defaults_frame, textvariable=self.default_vars[key], values=("F", "K"), state="readonly", width=width)
            elif key == "tax_code":
                widget = ttk.Combobox(defaults_frame, textvariable=self.default_vars[key], values=TAX_CODE_OPTIONS, state="readonly", width=width)
            else:
                widget = ttk.Entry(defaults_frame, textvariable=self.default_vars[key], width=width)
            widget.grid(row=row, column=col + 1, sticky="ew", padx=(0, 12), pady=(0, 8))
        ttk.Button(defaults_frame, text="Aplicar aos campos", command=self._apply_defaults_to_forms, style="Subtle.TButton").grid(
            row=4, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Button(defaults_frame, text="Salvar padroes", command=self._save_defaults_from_ui, style="Subtle.TButton").grid(
            row=4, column=1, sticky="w", pady=(6, 0)
        )

        header_frame = ttk.LabelFrame(self.manual_tab, text="Cabecalho do Pedido", style="Section.TLabelframe", padding=12)
        header_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        header_fields = [
            ("Referencia do pedido", "doc_ref", 0, 0, 20),
            ("Tipo de documento", "tipo_doc", 0, 2, 14),
            ("Fornecedor", "fornecedor", 0, 4, 14),
            ("Condicao de pagamento", "condicao_pagamento", 0, 6, 14),
            ("Organizacao de compras", "org_compras", 1, 0, 14),
            ("Grupo de compras", "grupo_compras", 1, 2, 14),
            ("Empresa", "empresa", 1, 4, 12),
            ("Moeda", "moeda", 1, 6, 10),
            ("Incoterms", "incoterms", 2, 0, 12),
            ("Texto do cabecalho", "texto_cabecalho", 2, 2, 52),
        ]
        for label, key, row, col, width in header_fields:
            ttk.Label(header_frame, text=label, style="Muted.TLabel").grid(row=row, column=col, sticky="w", padx=(0, 6), pady=(0, 4))
            columnspan = 5 if key == "texto_cabecalho" else 1
            ttk.Entry(header_frame, textvariable=self.header_vars[key], width=width).grid(
                row=row, column=col + 1, columnspan=columnspan, sticky="ew", padx=(0, 12), pady=(0, 8)
            )

        work_area = ttk.Frame(self.manual_tab, style="Card.TFrame")
        work_area.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        work_area.columnconfigure(0, weight=2)
        work_area.columnconfigure(1, weight=3)
        work_area.rowconfigure(0, weight=1)

        items_frame = ttk.LabelFrame(work_area, text="Itens do Pedido", style="Section.TLabelframe", padding=12)
        items_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        items_frame.columnconfigure(0, weight=1)
        items_frame.rowconfigure(1, weight=1)
        ttk.Label(
            items_frame,
            text="Cada item pode ser F (Ordem/AUFNR) ou K (Centro de custo/KOSTL). Os servicos ficam vinculados ao item selecionado.",
            style="Muted.TLabel",
            wraplength=420,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        item_tree_frame = ttk.Frame(items_frame, style="Card.TFrame")
        item_tree_frame.grid(row=1, column=0, sticky="nsew")
        item_tree_frame.columnconfigure(0, weight=1)
        item_tree_frame.rowconfigure(0, weight=1)
        self.item_tree = ttk.Treeview(
            item_tree_frame,
            columns=("item_ref", "texto_livre", "categoria_classif", "grupo_mercadoria", "plant_or_center", "tax_code", "service_line_count"),
            show="headings",
            height=14,
        )
        for column, width, title in (
            ("item_ref", 58, "Item"),
            ("texto_livre", 170, "Texto"),
            ("categoria_classif", 84, "Classif."),
            ("grupo_mercadoria", 132, "Grupo merc."),
            ("plant_or_center", 118, "Centro"),
            ("tax_code", 122, "Tipo de imposto"),
            ("service_line_count", 64, "Linhas"),
        ):
            self.item_tree.heading(column, text=title)
            self.item_tree.column(column, width=width, anchor="w")
        self.item_tree.grid(row=0, column=0, sticky="nsew")
        item_scroll = ttk.Scrollbar(item_tree_frame, orient="vertical", command=self.item_tree.yview)
        item_scroll.grid(row=0, column=1, sticky="ns")
        self.item_tree.configure(yscrollcommand=item_scroll.set)
        self.item_tree.bind("<<TreeviewSelect>>", self._on_item_selected)

        item_buttons = ttk.Frame(items_frame, style="Card.TFrame")
        item_buttons.grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Button(item_buttons, text="Novo item", command=self._new_item_form, style="Subtle.TButton").pack(side="left")
        ttk.Button(item_buttons, text="Salvar item", command=self._save_item, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(item_buttons, text="Excluir item", command=self._remove_selected_item, style="Subtle.TButton").pack(side="left", padx=(8, 0))

        detail_frame = ttk.Frame(work_area, style="Card.TFrame")
        detail_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(1, weight=1)

        item_editor = ttk.LabelFrame(detail_frame, text="Editor do Item", style="Section.TLabelframe", padding=12)
        item_editor.grid(row=0, column=0, sticky="ew")
        item_editor_fields = [
            ("Item ref", "item_ref", 0, 0, 10),
            ("Categoria do item", "categoria_item", 0, 2, 12),
            ("Classificacao contabil", "categoria_classif", 0, 4, 16),
            ("Texto breve", "texto_livre", 1, 0, 52),
            ("Grupo de mercadoria", "grupo_mercadoria", 2, 0, 20),
            ("Centro (planta)", "plant_or_center", 2, 2, 18),
            ("Tipo de imposto", "tax_code", 2, 4, 16),
            ("Conta contabil padrao", "conta_razao_default", 3, 0, 20),
            ("Observacao do item", "observacao_item", 4, 0, 52),
        ]
        for label, key, row, col, width in item_editor_fields:
            ttk.Label(item_editor, text=label, style="Muted.TLabel").grid(row=row, column=col, sticky="w", padx=(0, 6), pady=(0, 4))
            if key == "categoria_item":
                widget = ttk.Entry(item_editor, textvariable=self.item_vars[key], width=width, state="readonly")
            elif key == "categoria_classif":
                widget = ttk.Combobox(item_editor, textvariable=self.item_vars[key], values=("F", "K"), state="readonly", width=width)
                widget.bind("<<ComboboxSelected>>", self._on_item_classification_changed)
            elif key == "tax_code":
                widget = ttk.Combobox(item_editor, textvariable=self.item_vars[key], values=TAX_CODE_OPTIONS, state="readonly", width=width)
            else:
                widget = ttk.Entry(item_editor, textvariable=self.item_vars[key], width=width)
            columnspan = 5 if key in {"texto_livre", "observacao_item"} else 1
            widget.grid(row=row, column=col + 1, columnspan=columnspan, sticky="ew", padx=(0, 12), pady=(0, 8))
        ttk.Label(
            item_editor,
            text="Categoria do item fica travada em D. Classificacao contabil: F = Ordem (AUFNR), K = Centro de custo (KOSTL).",
            style="Muted.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=5, column=0, columnspan=6, sticky="w", pady=(8, 0))

        service_frame = ttk.LabelFrame(detail_frame, text="Linhas de Servico", style="Section.TLabelframe", padding=12)
        service_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        service_frame.columnconfigure(0, weight=1)
        service_frame.rowconfigure(3, weight=1)
        ttk.Label(service_frame, textvariable=self.manual_mode_note, style="Muted.TLabel", wraplength=640, justify="left").grid(
            row=0, column=0, sticky="ew", pady=(0, 8)
        )

        line_editor = ttk.Frame(service_frame, style="Card.TFrame")
        line_editor.grid(row=1, column=0, sticky="ew")
        line_editor.columnconfigure(1, weight=1, minsize=150)
        line_editor.columnconfigure(3, weight=1, minsize=170)
        ttk.Label(line_editor, text="Linha", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=(0, 4))
        ttk.Entry(line_editor, textvariable=self.service_vars["line_ref"], width=10).grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(0, 8))
        ttk.Label(line_editor, text="Numero do servico", style="Muted.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 6), pady=(0, 4))
        ttk.Entry(line_editor, textvariable=self.service_vars["numero_servico"], width=16).grid(row=0, column=3, sticky="ew", padx=(0, 12), pady=(0, 8))
        ttk.Label(line_editor, text="Quantidade", style="Muted.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(0, 4))
        ttk.Entry(line_editor, textvariable=self.service_vars["quantidade"], width=10).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 8))
        ttk.Label(line_editor, text="Preco bruto (opcional)", style="Muted.TLabel").grid(row=1, column=2, sticky="w", padx=(0, 6), pady=(0, 4))
        ttk.Entry(line_editor, textvariable=self.service_vars["preco_bruto"], width=14).grid(row=1, column=3, sticky="ew", padx=(0, 12), pady=(0, 8))

        ttk.Label(line_editor, textvariable=self.reference_label_var, style="Muted.TLabel").grid(
            row=2, column=0, sticky="w", padx=(0, 6), pady=(0, 4)
        )
        ttk.Entry(line_editor, textvariable=self.reference_var, width=18).grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=(0, 8))
        ttk.Label(line_editor, text="Conta contabil", style="Muted.TLabel").grid(row=2, column=2, sticky="w", padx=(0, 6), pady=(0, 4))
        ttk.Entry(line_editor, textvariable=self.service_vars["conta_razao"], width=18).grid(
            row=2, column=3, sticky="ew", padx=(0, 12), pady=(0, 8)
        )

        line_actions = ttk.Frame(service_frame, style="Card.TFrame")
        line_actions.grid(row=2, column=0, sticky="e", pady=(0, 8))
        ttk.Button(line_actions, text="Nova linha", command=self._new_service_form, style="Subtle.TButton").pack(side="left")
        ttk.Button(
            line_actions,
            text="Colar em lote",
            command=self._open_bulk_reference_dialog,
            style="Subtle.TButton",
        ).pack(side="left", padx=(8, 0))
        ttk.Button(line_actions, text="Salvar linha", command=self._save_service_line, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(line_actions, text="Excluir linha", command=self._remove_selected_service_line, style="Subtle.TButton").pack(side="left", padx=(8, 0))

        service_tree_frame = ttk.Frame(service_frame, style="Card.TFrame")
        service_tree_frame.grid(row=3, column=0, sticky="nsew")
        service_tree_frame.columnconfigure(0, weight=1)
        service_tree_frame.rowconfigure(0, weight=1)
        self.service_tree = ttk.Treeview(
            service_tree_frame,
            columns=("line_ref", "numero_servico", "quantidade", "preco_bruto", "reference", "conta_razao"),
            show="headings",
            height=12,
        )
        for column, width, title in (
            ("line_ref", 70, "Linha"),
            ("numero_servico", 150, "Numero do servico"),
            ("quantidade", 104, "Quantidade"),
            ("preco_bruto", 132, "Preco bruto"),
            ("reference", 170, "Ordem"),
            ("conta_razao", 132, "Conta contabil"),
        ):
            self.service_tree.heading(column, text=title)
            self.service_tree.column(column, width=width, minwidth=width, anchor="w", stretch=True)
        self.service_tree.grid(row=0, column=0, sticky="nsew")
        service_scroll = ttk.Scrollbar(service_tree_frame, orient="vertical", command=self.service_tree.yview)
        service_scroll.grid(row=0, column=1, sticky="ns")
        service_scroll_x = ttk.Scrollbar(service_tree_frame, orient="horizontal", command=self.service_tree.xview)
        service_scroll_x.grid(row=1, column=0, sticky="ew")
        self.service_tree.configure(yscrollcommand=service_scroll.set, xscrollcommand=service_scroll_x.set)
        self.service_tree.bind("<<TreeviewSelect>>", self._on_service_selected)

    def _build_excel_tab(self) -> None:
        self.excel_tab.columnconfigure(0, weight=1)
        form = ttk.LabelFrame(self.excel_tab, text="Importacao por planilha", style="Section.TLabelframe", padding=12)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(0, weight=1)
        ttk.Label(
            form,
            text="Use este modo quando ja existir um workbook com CABECALHO, ITENS e SERVICOS.",
            style="Muted.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(form, text="Arquivo XLSX", style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.file_var, width=72).grid(row=2, column=0, sticky="ew", padx=(0, 12), pady=(4, 10))
        ttk.Button(form, text="Selecionar", command=self._select_file, style="Subtle.TButton").grid(row=2, column=1, sticky="w", pady=(4, 10))

    def _defaults_path(self) -> Path:
        return ensure_dir(appdata_dir()) / DEFAULTS_FILE

    def _load_persisted_defaults(self) -> dict:
        path = self._defaults_path()
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _profile_ui_defaults(self, profile_name: str) -> dict:
        profile = self.layout_map.get("profiles", {}).get(profile_name, {})
        defaults = profile.get("uiDefaults", {})
        return defaults if isinstance(defaults, dict) else {}

    def _merge_defaults(self, profile_name: str) -> dict:
        merged = dict(DEFAULT_DEFAULTS)
        merged.update({key: str(value) for key, value in self._profile_ui_defaults(profile_name).items() if value is not None})
        for key, value in self._load_persisted_defaults().items():
            if value is None:
                continue
            normalized = str(value).strip()
            if normalized:
                merged[key] = normalized
        merged["categoria_item"] = "D"
        if merged.get("categoria_classif") not in {"F", "K"}:
            merged["categoria_classif"] = "F"
        merged_tax_code = str(merged.get("tax_code", "")).strip().upper()
        if merged_tax_code not in TAX_CODE_OPTIONS:
            merged["tax_code"] = TAX_CODE_OPTIONS[1]
        else:
            merged["tax_code"] = merged_tax_code
        return merged

    def _save_defaults_from_ui(self) -> None:
        payload = {key: var.get().strip() for key, var in self.default_vars.items()}
        payload["categoria_item"] = "D"
        ensure_dir(self._defaults_path().parent)
        self._defaults_path().write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self.status_var.set("Padroes da ME21N salvos em %APPDATA%\\Robos SAP\\me21n.defaults.json.")

    def _apply_defaults_to_forms(self) -> None:
        self.header_vars["tipo_doc"].set(self.default_vars["tipo_doc"].get().strip())
        self.header_vars["fornecedor"].set(self.default_vars["fornecedor"].get().strip())
        self.header_vars["condicao_pagamento"].set(self.default_vars["condicao_pagamento"].get().strip())
        self.header_vars["org_compras"].set(self.default_vars["org_compras"].get().strip())
        self.header_vars["grupo_compras"].set(self.default_vars["grupo_compras"].get().strip())
        self.header_vars["empresa"].set(self.default_vars["empresa"].get().strip())
        self.header_vars["moeda"].set(self.default_vars["moeda"].get().strip())
        self.item_vars["categoria_item"].set("D")
        self.item_vars["categoria_classif"].set(self.default_vars["categoria_classif"].get().strip() or "F")
        self.item_vars["grupo_mercadoria"].set(self.default_vars["grupo_mercadoria"].get().strip())
        self.item_vars["plant_or_center"].set(self.default_vars["plant_or_center"].get().strip())
        self.item_vars["tax_code"].set(self.default_vars["tax_code"].get().strip())
        self.item_vars["conta_razao_default"].set(self.default_vars["conta_razao_default"].get().strip())
        self.service_vars["conta_razao"].set(self.item_vars["conta_razao_default"].get().strip())
        self._update_reference_ui()
        self.status_var.set("Padroes aplicados ao cabecalho e ao editor do item.")

    def _active_mode(self) -> str:
        return "manual" if self.mode_notebook.select() == str(self.manual_tab) else "excel"

    def _on_mode_changed(self) -> None:
        if self._active_mode() == "manual":
            self.status_var.set("Modo guiado ativo. Preencha itens e linhas como na ME21N. Classificacao contabil: F (Ordem) ou K (Centro de custo).")
        else:
            self.status_var.set("Modo planilha ativo. Selecione um workbook com CABECALHO, ITENS e SERVICOS.")

    def _on_profile_changed(self, _event=None) -> None:
        profile_name = self.profile_var.get().strip() or self.layout_map.get("defaultProfile", self.profile_names[0])
        self.profile_name = profile_name
        self.profile = self.layout_map.get("profiles", {}).get(profile_name, {})
        self.profile_capabilities = self.profile.get("capabilities", {})
        self.status_var.set(f"Perfil ativo: {profile_name}. A UI nao altera seus dados atuais automaticamente.")

    def _current_profile(self) -> tuple[str, dict]:
        profile_name = self.profile_var.get().strip() or self.layout_map.get("defaultProfile", self.profile_names[0])
        return profile_name, self.layout_map["profiles"][profile_name]

    def _thread_safe_chooser(self, sessions: list) -> str | None:
        """Pick a SAP session from the main (Tkinter) thread.

        The SAP session resolver may call this from a background worker thread.
        Tkinter widgets must only be created/manipulated from the main thread, so
        we use root.after() to schedule the picker there and block the worker with
        a threading.Event until the user makes a selection.
        """
        result_holder: list[str | None] = [None]
        done = threading.Event()

        def _show():
            result_holder[0] = pick_session(sessions, self.root)
            done.set()

        self.root.after(0, _show)
        done.wait()
        return result_holder[0]

    def _get_runner_api(self) -> dict[str, object]:
        if self._runner_api is None:
            from core.me21n.runner import inspect_me21n_session, run_job, validate_excel_file, validate_input_rows

            self._runner_api = {
                "inspect_me21n_session": inspect_me21n_session,
                "run_job": run_job,
                "validate_excel_file": validate_excel_file,
                "validate_input_rows": validate_input_rows,
            }
        return self._runner_api

    def _next_item_ref(self) -> str:
        refs = [row.get("item_ref", "") for row in self.manual_items]
        numeric_refs = [int(value) for value in refs if str(value).isdigit()]
        return str((max(numeric_refs) + 10) if numeric_refs else 10)

    def _next_service_line_ref(self, item: dict | None = None) -> str:
        rows = (item or {}).get("service_lines", [])
        numeric_refs = [int(row.get("line_ref", "")) for row in rows if str(row.get("line_ref", "")).isdigit()]
        return str((max(numeric_refs) + 10) if numeric_refs else 10)

    def _item_form_has_content(self) -> bool:
        return any(
            self.item_vars[key].get().strip()
            for key in ("texto_livre", "grupo_mercadoria", "plant_or_center", "tax_code", "observacao_item", "conta_razao_default")
        )

    def _inherited_service_account(self, item: dict | None = None) -> str:
        current_item = item or self._selected_item()
        if current_item:
            return str(current_item.get("conta_razao_default", "")).strip()
        return self.item_vars["conta_razao_default"].get().strip() or self.default_vars["conta_razao_default"].get().strip()

    def _service_form_has_content(self) -> bool:
        numero_servico = self.service_vars["numero_servico"].get().strip()
        preco_bruto = self.service_vars["preco_bruto"].get().strip()
        reference_value = self.reference_var.get().strip()
        conta_razao = self.service_vars["conta_razao"].get().strip()
        quantidade = self.service_vars["quantidade"].get().strip() or "1"
        line_ref = self.service_vars["line_ref"].get().strip()

        current_item = self._selected_item()
        inherited_account = self._inherited_service_account(current_item)
        next_line_ref = self._next_service_line_ref(current_item)
        is_empty_draft = (
            not numero_servico
            and not preco_bruto
            and not reference_value
            and conta_razao == inherited_account
            and quantidade == "1"
            and line_ref == next_line_ref
        )
        return not is_empty_draft

    def _find_item_index(self, item_ref: str | None) -> int | None:
        if not item_ref:
            return None
        for index, row in enumerate(self.manual_items):
            if row.get("item_ref") == item_ref:
                return index
        return None

    def _selected_item(self) -> dict | None:
        index = self._find_item_index(self.selected_item_ref)
        return self.manual_items[index] if index is not None else None

    def _find_service_index(self, item: dict | None, line_ref: str | None) -> int | None:
        if not item or not line_ref:
            return None
        for index, row in enumerate(item.get("service_lines", [])):
            if row.get("line_ref") == line_ref:
                return index
        return None

    def _reference_key(self, categoria_classif: str | None = None) -> str:
        return "centro_custo" if (categoria_classif or self.item_vars["categoria_classif"].get().strip()) == "K" else "ordem"

    def _reference_title(self, categoria_classif: str | None = None) -> str:
        return "Centro de custo (KOSTL)" if (categoria_classif or self.item_vars["categoria_classif"].get().strip()) == "K" else "Ordem (AUFNR)"

    def _update_reference_ui(self) -> None:
        categoria = self.item_vars["categoria_classif"].get().strip() or "F"
        self.reference_label_var.set(self._reference_title(categoria))
        self.service_tree.heading("reference", text=self._reference_title(categoria))

    def _refresh_item_tree(self, focus_item_ref: str | None = None) -> None:
        for item_id in self.item_tree.get_children():
            self.item_tree.delete(item_id)
        for row in sorted(self.manual_items, key=lambda item: _sort_key(item.get("item_ref", ""))):
            item_ref = row["item_ref"]
            self.item_tree.insert(
                "",
                tk.END,
                iid=item_ref,
                values=(
                    item_ref,
                    row.get("texto_livre", ""),
                    row.get("categoria_classif", ""),
                    row.get("grupo_mercadoria", ""),
                    row.get("plant_or_center", ""),
                    row.get("tax_code", ""),
                    len(row.get("service_lines", [])),
                ),
            )
        target = focus_item_ref or self.selected_item_ref
        if target and self.item_tree.exists(target):
            self.item_tree.selection_set(target)
            self.item_tree.focus(target)

    def _refresh_service_tree(self, item: dict | None = None, focus_line_ref: str | None = None) -> None:
        for item_id in self.service_tree.get_children():
            self.service_tree.delete(item_id)
        current_item = item or self._selected_item()
        if not current_item:
            self._update_reference_ui()
            return
        categoria = current_item.get("categoria_classif", "F")
        self._update_reference_ui()
        for row in sorted(current_item.get("service_lines", []), key=lambda service: _sort_key(service.get("line_ref", ""))):
            line_ref = row["line_ref"]
            reference_value = row.get(self._reference_key(categoria), "")
            self.service_tree.insert(
                "",
                tk.END,
                iid=line_ref,
                values=(
                    line_ref,
                    row.get("numero_servico", ""),
                    row.get("quantidade", ""),
                    row.get("preco_bruto", ""),
                    reference_value,
                    row.get("conta_razao", ""),
                ),
            )
        target = focus_line_ref or self.selected_service_line_ref
        if target and self.service_tree.exists(target):
            self.service_tree.selection_set(target)
            self.service_tree.focus(target)

    def _load_item_into_form(self, item: dict) -> None:
        self.item_vars["item_ref"].set(item.get("item_ref", ""))
        self.item_vars["texto_livre"].set(item.get("texto_livre", ""))
        self.item_vars["categoria_item"].set(item.get("categoria_item", "D"))
        self.item_vars["categoria_classif"].set(item.get("categoria_classif", "F"))
        self.item_vars["grupo_mercadoria"].set(item.get("grupo_mercadoria", ""))
        self.item_vars["plant_or_center"].set(item.get("plant_or_center", ""))
        self.item_vars["tax_code"].set(item.get("tax_code", ""))
        self.item_vars["observacao_item"].set(item.get("observacao_item", ""))
        self.item_vars["conta_razao_default"].set(item.get("conta_razao_default", ""))
        self._update_reference_ui()

    def _load_service_line_into_form(self, item: dict, row: dict) -> None:
        categoria = item.get("categoria_classif", "F")
        self.service_vars["line_ref"].set(row.get("line_ref", ""))
        self.service_vars["numero_servico"].set(row.get("numero_servico", ""))
        self.service_vars["quantidade"].set(str(row.get("quantidade", "")))
        preco_bruto = row.get("preco_bruto", "")
        self.service_vars["preco_bruto"].set("" if preco_bruto is None else str(preco_bruto))
        self.service_vars["conta_razao"].set(row.get("conta_razao", ""))
        self.reference_var.set(row.get(self._reference_key(categoria), "") or "")
        self._update_reference_ui()

    def _new_item_form(self) -> None:
        self.selected_item_ref = None
        self.selected_service_line_ref = None
        self.item_vars["item_ref"].set(self._next_item_ref())
        self.item_vars["texto_livre"].set(DEFAULT_DEFAULTS.get("texto_livre", ""))
        self.item_vars["categoria_item"].set("D")
        self.item_vars["categoria_classif"].set(self.default_vars["categoria_classif"].get().strip() or "F")
        self.item_vars["grupo_mercadoria"].set(self.default_vars["grupo_mercadoria"].get().strip())
        self.item_vars["plant_or_center"].set(self.default_vars["plant_or_center"].get().strip())
        self.item_vars["tax_code"].set(self.default_vars["tax_code"].get().strip())
        self.item_vars["observacao_item"].set("")
        self.item_vars["conta_razao_default"].set(self.default_vars["conta_razao_default"].get().strip())
        self._new_service_form()
        self._refresh_service_tree(item={"categoria_classif": self.item_vars["categoria_classif"].get().strip(), "service_lines": []})
        self.status_var.set("Novo item pronto para edicao.")

    def _new_service_form(self) -> None:
        self.selected_service_line_ref = None
        current_item = self._selected_item()
        self.service_vars["line_ref"].set(self._next_service_line_ref(current_item))
        self.service_vars["numero_servico"].set("")
        self.service_vars["quantidade"].set("1")
        self.service_vars["preco_bruto"].set("")
        inherited_account = self._inherited_service_account(current_item)
        self.service_vars["conta_razao"].set(inherited_account)
        self.reference_var.set("")
        self._update_reference_ui()

    def _save_item(self, show_feedback: bool = True) -> bool:
        item_ref = self.item_vars["item_ref"].get().strip()
        if not item_ref:
            if show_feedback:
                messagebox.showwarning("Item", "Item ref obrigatorio.")
            return False

        current_index = self._find_item_index(self.selected_item_ref)
        duplicate_index = self._find_item_index(item_ref)
        if duplicate_index is not None and duplicate_index != current_index:
            if show_feedback:
                messagebox.showwarning("Item", f"O item {item_ref} ja existe.")
            return False

        existing_services = []
        old_categoria = ""
        if current_index is not None:
            existing = self.manual_items[current_index]
            existing_services = [dict(row) for row in existing.get("service_lines", [])]
            old_categoria = existing.get("categoria_classif", "")

        categoria_classif = self.item_vars["categoria_classif"].get().strip() or "F"
        if categoria_classif not in {"F", "K"}:
            categoria_classif = "F"
        tax_code = self.item_vars["tax_code"].get().strip().upper()
        if tax_code not in TAX_CODE_OPTIONS:
            if show_feedback:
                messagebox.showwarning("Item", "Tipo de imposto obrigatorio. Selecione S1 ou S2.")
            return False

        if old_categoria and old_categoria != categoria_classif:
            for row in existing_services:
                if categoria_classif == "F":
                    row["centro_custo"] = ""
                else:
                    row["ordem"] = ""

        item_row = {
            "item_ref": item_ref,
            "texto_livre": self.item_vars["texto_livre"].get().strip(),
            "categoria_item": "D",
            "categoria_classif": categoria_classif,
            "grupo_mercadoria": self.item_vars["grupo_mercadoria"].get().strip(),
            "plant_or_center": self.item_vars["plant_or_center"].get().strip(),
            "tax_code": tax_code,
            "observacao_item": self.item_vars["observacao_item"].get().strip(),
            "conta_razao_default": self.item_vars["conta_razao_default"].get().strip(),
            "service_lines": existing_services,
        }

        if current_index is None:
            self.manual_items.append(item_row)
        else:
            self.manual_items[current_index] = item_row

        self.manual_items.sort(key=lambda item: _sort_key(item.get("item_ref", "")))
        self.selected_item_ref = item_ref
        self._refresh_item_tree(focus_item_ref=item_ref)
        self._refresh_service_tree(self._selected_item())
        self._update_execute_button()
        if show_feedback:
            self.status_var.set(f"Item {item_ref} salvo no modo guiado.")
        return True

    def _remove_selected_item(self) -> None:
        if not self.selected_item_ref:
            messagebox.showwarning("Item", "Selecione um item para excluir.")
            return
        index = self._find_item_index(self.selected_item_ref)
        if index is None:
            return
        removed = self.manual_items.pop(index)
        self.selected_item_ref = None
        self.selected_service_line_ref = None
        self._refresh_item_tree()
        self._new_item_form()
        self._update_execute_button()
        self.status_var.set(f"Item {removed.get('item_ref', '')} removido.")

    def _save_service_line(self, show_feedback: bool = True) -> bool:
        if not self.selected_item_ref:
            if not self._save_item(show_feedback=show_feedback):
                return False
        current_item = self._selected_item()
        if not current_item:
            if show_feedback:
                messagebox.showwarning("Linha de servico", "Salve ou selecione um item antes de adicionar linhas.")
            return False
        if not self._service_form_has_content():
            if show_feedback:
                messagebox.showwarning("Linha de servico", "Preencha a linha antes de salvar.")
            return False

        line_ref = self.service_vars["line_ref"].get().strip()
        if not line_ref:
            if show_feedback:
                messagebox.showwarning("Linha de servico", "Numero da linha obrigatorio.")
            return False
        numero_servico = self.service_vars["numero_servico"].get().strip()
        if not numero_servico:
            if show_feedback:
                messagebox.showwarning("Linha de servico", "Numero do servico obrigatorio.")
            return False
        quantidade = self.service_vars["quantidade"].get().strip() or "1"
        self.service_vars["quantidade"].set(quantidade)

        rows = current_item.get("service_lines", [])
        current_index = self._find_service_index(current_item, self.selected_service_line_ref)
        duplicate_index = self._find_service_index(current_item, line_ref)
        if duplicate_index is not None and duplicate_index != current_index:
            if show_feedback:
                messagebox.showwarning("Linha de servico", f"A linha {line_ref} ja existe neste item.")
            return False

        categoria = current_item.get("categoria_classif", "F")
        preco_bruto = self.service_vars["preco_bruto"].get().strip() or "0,00"
        self.service_vars["preco_bruto"].set(preco_bruto)
        row = {
            "line_ref": line_ref,
            "numero_servico": numero_servico,
            "quantidade": quantidade,
            "preco_bruto": preco_bruto,
            "ordem": self.reference_var.get().strip() if categoria == "F" else "",
            "centro_custo": self.reference_var.get().strip() if categoria == "K" else "",
            "conta_razao": self.service_vars["conta_razao"].get().strip(),
        }
        if current_index is None:
            rows.append(row)
        else:
            rows[current_index] = row
        rows.sort(key=lambda item: _sort_key(item.get("line_ref", "")))
        current_item["service_lines"] = rows
        self.selected_service_line_ref = line_ref
        self._refresh_item_tree(focus_item_ref=current_item["item_ref"])
        self._refresh_service_tree(current_item, focus_line_ref=line_ref)
        self._load_service_line_into_form(current_item, row)
        self._update_execute_button()
        if show_feedback:
            total_lines = len(current_item.get("service_lines", []))
            self.status_var.set(f"Linha {line_ref} salva. Item {current_item['item_ref']}: {total_lines} linha(s). Clique Executar para processar tudo.")
        return True

    def _parse_bulk_references(self, raw_text: str) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()
        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = [part.strip() for part in re.split(r"[;\t,]", line) if part.strip()]
            if not parts:
                continue
            ref = parts[0]
            if ref in seen:
                continue
            seen.add(ref)
            values.append(ref)
        return values

    def _bulk_add_references(self, references: list[str]) -> tuple[int, int]:
        if not self.selected_item_ref:
            if not self._save_item(show_feedback=False):
                return 0, len(references)
        current_item = self._selected_item()
        if not current_item:
            return 0, len(references)

        numero_servico = self.service_vars["numero_servico"].get().strip()
        quantidade = self.service_vars["quantidade"].get().strip() or "1"
        preco_bruto = self.service_vars["preco_bruto"].get().strip() or "0,00"
        conta_razao = self.service_vars["conta_razao"].get().strip() or current_item.get("conta_razao_default", "")
        if not numero_servico:
            messagebox.showwarning("Lote de linhas", "Preencha o campo 'Numero do servico' antes de gerar em lote.")
            return 0, len(references)

        created = 0
        failed = 0
        for reference in references:
            current_item = self._selected_item() or current_item
            self.selected_service_line_ref = None
            self.service_vars["line_ref"].set(self._next_service_line_ref(current_item))
            self.service_vars["numero_servico"].set(numero_servico)
            self.service_vars["quantidade"].set(quantidade)
            self.service_vars["preco_bruto"].set(preco_bruto)
            self.service_vars["conta_razao"].set(conta_razao)
            self.reference_var.set(reference)
            if self._save_service_line(show_feedback=False):
                created += 1
            else:
                failed += 1
        return created, failed

    def _open_bulk_reference_dialog(self) -> None:
        categoria = self.item_vars["categoria_classif"].get().strip() or "F"
        reference_title = self._reference_title(categoria)

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Colar {reference_title}s em lote")
        dialog.geometry("560x360")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=f"Cole uma lista de {reference_title}s (uma por linha).",
            style="Muted.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            frame,
            text="Opcional: se colar uma tabela, a primeira coluna de cada linha sera usada.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        text = scrolledtext.ScrolledText(frame, height=12, wrap="none", font=("Consolas", 10))
        text.pack(fill="both", expand=True)
        text.focus_set()

        actions = ttk.Frame(frame, style="Card.TFrame")
        actions.pack(fill="x", pady=(10, 0))

        def _apply_bulk() -> None:
            raw_text = text.get("1.0", tk.END)
            references = self._parse_bulk_references(raw_text)
            if not references:
                messagebox.showwarning("Lote de linhas", f"Cole ao menos uma {reference_title}.", parent=dialog)
                return
            created, failed = self._bulk_add_references(references)
            if created <= 0:
                messagebox.showwarning("Lote de linhas", "Nenhuma linha foi criada. Revise os campos base.", parent=dialog)
                return
            self.status_var.set(
                f"{created} linha(s) criadas em lote para {reference_title}. Falhas: {failed}."
            )
            dialog.destroy()

        ttk.Button(actions, text="Gerar linhas", command=_apply_bulk, style="Accent.TButton").pack(side="right")
        ttk.Button(actions, text="Cancelar", command=dialog.destroy, style="Subtle.TButton").pack(side="right", padx=(0, 8))

    def _remove_selected_service_line(self) -> None:
        current_item = self._selected_item()
        if not current_item or not self.selected_service_line_ref:
            messagebox.showwarning("Linha de servico", "Selecione uma linha para excluir.")
            return
        index = self._find_service_index(current_item, self.selected_service_line_ref)
        if index is None:
            return
        removed = current_item["service_lines"].pop(index)
        self.selected_service_line_ref = None
        self._refresh_item_tree(focus_item_ref=current_item["item_ref"])
        self._refresh_service_tree(current_item)
        self._new_service_form()
        self._update_execute_button()
        self.status_var.set(f"Linha {removed.get('line_ref', '')} removida.")

    def _update_execute_button(self) -> None:
        total_items = len(self.manual_items)
        total_lines = sum(len(item.get("service_lines", [])) for item in self.manual_items)
        if total_items > 0:
            self.execute_button.configure(text=f"Executar  ({total_items}it / {total_lines}ln)")
        else:
            self.execute_button.configure(text="Executar")

    def _on_item_selected(self, _event=None) -> None:
        selection = self.item_tree.selection()
        if not selection:
            return
        item_ref = selection[0]
        index = self._find_item_index(item_ref)
        if index is None:
            return
        item = self.manual_items[index]
        self.selected_item_ref = item_ref
        self._load_item_into_form(item)
        service_lines = sorted(item.get("service_lines", []), key=lambda row: _sort_key(row.get("line_ref", "")))
        if service_lines:
            last_row = service_lines[-1]
            last_line_ref = str(last_row.get("line_ref", "")).strip()
            self.selected_service_line_ref = last_line_ref or None
            self._refresh_service_tree(item, focus_line_ref=self.selected_service_line_ref)
            self._load_service_line_into_form(item, last_row)
            return
        self.selected_service_line_ref = None
        self._refresh_service_tree(item)
        self._new_service_form()

    def _on_service_selected(self, _event=None) -> None:
        current_item = self._selected_item()
        selection = self.service_tree.selection()
        if not current_item or not selection:
            return
        line_ref = selection[0]
        index = self._find_service_index(current_item, line_ref)
        if index is None:
            return
        row = current_item.get("service_lines", [])[index]
        self.selected_service_line_ref = line_ref
        self._load_service_line_into_form(current_item, row)

    def _on_item_classification_changed(self, _event=None) -> None:
        categoria = self.item_vars["categoria_classif"].get().strip() or "F"
        if categoria == "K":
            self.reference_var.set("")
        self._update_reference_ui()

    def _commit_manual_draft(self) -> bool:
        service_has_content = self._service_form_has_content()
        # Auto-salvar item apenas se editando existente ou se ha linha de servico para vincular
        if self._item_form_has_content() and (self.selected_item_ref is not None or service_has_content):
            if not self._save_item(show_feedback=False):
                messagebox.showwarning("Modo guiado", "Revise o item atual antes de validar ou executar.")
                return False
        if service_has_content:
            if not self._save_service_line(show_feedback=False):
                messagebox.showwarning("Modo guiado", "Revise a linha de servico atual antes de validar ou executar.")
                return False
        return True

    def _manual_rows(self) -> tuple[list[dict], list[dict], list[dict]] | None:
        if not self._commit_manual_draft():
            return None
        if not self.manual_items:
            messagebox.showwarning("Modo guiado", "Adicione ao menos um item.")
            return None

        doc_ref = self.header_vars["doc_ref"].get().strip()
        if not doc_ref:
            doc_ref = f"ME21N_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.header_vars["doc_ref"].set(doc_ref)

        header_rows = [
            {
                "doc_ref": doc_ref,
                "tipo_doc": self.header_vars["tipo_doc"].get().strip(),
                "org_compras": self.header_vars["org_compras"].get().strip(),
                "grupo_compras": self.header_vars["grupo_compras"].get().strip(),
                "empresa": self.header_vars["empresa"].get().strip(),
                "fornecedor": self.header_vars["fornecedor"].get().strip(),
                "moeda": self.header_vars["moeda"].get().strip(),
                "condicao_pagamento": self.header_vars["condicao_pagamento"].get().strip(),
                "incoterms": self.header_vars["incoterms"].get().strip(),
                "texto_cabecalho": self.header_vars["texto_cabecalho"].get().strip(),
            }
        ]
        item_rows: list[dict] = []
        service_rows: list[dict] = []
        for item in sorted(self.manual_items, key=lambda row: _sort_key(row.get("item_ref", ""))):
            item_rows.append(
                {
                    "item_ref": item.get("item_ref", ""),
                    "texto_livre": item.get("texto_livre", ""),
                    "categoria_item": item.get("categoria_item", "D"),
                    "categoria_classif": item.get("categoria_classif", "F"),
                    "grupo_mercadoria": item.get("grupo_mercadoria", ""),
                    "plant_or_center": item.get("plant_or_center", ""),
                    "tax_code": item.get("tax_code", ""),
                    "observacao_item": item.get("observacao_item", ""),
                    "conta_razao_default": item.get("conta_razao_default", ""),
                }
            )
            for service in sorted(item.get("service_lines", []), key=lambda row: _sort_key(row.get("line_ref", ""))):
                service_rows.append(
                    {
                        "item_ref": item.get("item_ref", ""),
                        "line_ref": service.get("line_ref", ""),
                        "numero_servico": service.get("numero_servico", ""),
                        "quantidade": service.get("quantidade", ""),
                        "preco_bruto": service.get("preco_bruto", ""),
                        "ordem": service.get("ordem", ""),
                        "centro_custo": service.get("centro_custo", ""),
                        "conta_razao": service.get("conta_razao", ""),
                    }
                )
        return header_rows, item_rows, service_rows

    def _select_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar planilha ME21N",
            filetypes=[("Arquivos Excel", "*.xlsx"), ("Todos os arquivos", "*.*")],
        )
        if path:
            self.file_var.set(path)

    def _append_log(self, message: str) -> None:
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def _set_last_po_number(self, po_number: str | None) -> None:
        self.last_po_number = str(po_number or "").strip()
        state = "normal" if self.last_po_number else "disabled"
        self.copy_po_button.configure(state=state)

    def copy_po_number(self) -> None:
        if not self.last_po_number:
            messagebox.showwarning("Copiar pedido", "Nenhum numero de pedido disponivel para copiar.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_po_number)
        self.root.update_idletasks()
        self.status_var.set(f"Numero do pedido {self.last_po_number} copiado para a area de transferencia.")

    def _set_summary(self, text: str) -> None:
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.insert("1.0", text)

    def validate_current_input(self) -> None:
        if self._active_mode() == "manual":
            self._validate_manual_input()
            return
        self._validate_excel_input()

    def _validate_excel_input(self) -> None:
        path = self.file_var.get().strip()
        if not path:
            messagebox.showwarning("Validacao", "Selecione um arquivo XLSX.")
            return
        try:
            profile_name, profile = self._current_profile()
            payload, errors, warnings = self._get_runner_api()["validate_excel_file"](path, profile)
            item_count = len(payload.get("items", [])) if payload else 0
            service_line_count = sum(len(item.get("service_lines", [])) for item in payload.get("items", [])) if payload else 0
            summary = {
                "mode": "excel",
                "profile": profile_name,
                "itemCount": item_count,
                "serviceLineCount": service_line_count,
                "payload": payload,
                "errors": errors,
                "warnings": warnings,
            }
            self._set_summary(json.dumps(summary, indent=2, ensure_ascii=False))
            self.status_var.set(
                f"Arquivo validado. Itens: {item_count} | Linhas de servico: {service_line_count}"
                if not errors
                else f"Validacao encontrou {len(errors)} erro(s)."
            )
        except Exception as exc:
            messagebox.showerror("Falha na validacao", str(exc))

    def _validate_manual_input(self) -> None:
        manual_rows = self._manual_rows()
        if manual_rows is None:
            return
        header_rows, item_rows, service_rows = manual_rows
        try:
            profile_name, profile = self._current_profile()
            payload, errors, warnings = self._get_runner_api()["validate_input_rows"](header_rows, item_rows, service_rows, profile)
            item_count = len(payload.get("items", [])) if payload else len(item_rows)
            service_line_count = sum(len(item.get("service_lines", [])) for item in payload.get("items", [])) if payload else len(service_rows)
            summary = {
                "mode": "manual",
                "profile": profile_name,
                "itemCount": item_count,
                "serviceLineCount": service_line_count,
                "payload": payload,
                "errors": errors,
                "warnings": warnings,
            }
            self._set_summary(json.dumps(summary, indent=2, ensure_ascii=False))
            if not errors:
                self._save_defaults_from_ui()
            self.status_var.set(
                f"Modo guiado validado. Itens: {item_count} | Linhas de servico: {service_line_count}"
                if not errors
                else f"Validacao encontrou {len(errors)} erro(s) no modo guiado."
            )
        except Exception as exc:
            messagebox.showerror("Falha na validacao", str(exc))

    def inspect_sap(self) -> None:
        try:
            result = self._get_runner_api()["inspect_me21n_session"](
                {"allow_manual_login": True, "output_dir": str(run_output_dir("ME21N-Inspect"))},
                chooser=self._thread_safe_chooser,
            )
            self._set_summary(json.dumps(result, indent=2, ensure_ascii=False))
            self.status_var.set("Inspecao concluida.")
        except Exception as exc:
            messagebox.showerror("Falha na inspecao", str(exc))

    def execute(self) -> None:
        if self.is_running:
            return
        job_input = self._build_job_input()
        if job_input is None:
            return
        if self._active_mode() == "manual":
            self._save_defaults_from_ui()
        self.is_running = True
        self._set_last_po_number(None)
        self.execute_button.config(state="disabled")
        if self.dry_run_var.get():
            self.status_var.set("Executando ME21N em DRY_RUN (nao salva pedido)...")
        else:
            self.status_var.set("Executando ME21N...")
        worker = threading.Thread(target=self._run_execute, args=(job_input,), daemon=True)
        worker.start()

    def _build_job_input(self) -> dict | None:
        if self._active_mode() == "manual":
            manual_rows = self._manual_rows()
            if manual_rows is None:
                return None
            header_rows, item_rows, service_rows = manual_rows
            return {
                "header_rows": header_rows,
                "item_rows": item_rows,
                "service_rows": service_rows,
                "source_mode": "manual",
            }
        path = self.file_var.get().strip()
        if not path:
            messagebox.showwarning("Validacao", "Selecione um arquivo XLSX.")
            return None
        return {"excel_path": path}

    def _run_execute(self, job_input: dict) -> None:
        try:
            result = self._get_runner_api()["run_job"](
                job_input,
                {
                    "dry_run": self.dry_run_var.get(),
                    "layout_profile": self.profile_var.get().strip(),
                    "allow_manual_login": True,
                    "session_chooser": self._thread_safe_chooser,
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
                    self._append_log(str(payload))
                    continue
                if status == "progress":
                    _stage, current, total = payload
                    self.status_var.set(f"Executando... {current}/{total}")
                    continue
                self.is_running = False
                self.execute_button.config(state="normal")
                if status == "error":
                    self._set_last_po_number(None)
                    self.status_var.set(f"Falha: {payload}")
                    messagebox.showerror("Falha no robo ME21N", str(payload))
                    continue
                self._set_summary(json.dumps(payload, indent=2, ensure_ascii=False))
                business_result = payload.get("business_result", {})
                po_number = business_result.get("poNumber")
                item_count = business_result.get("itemCount", 0)
                service_line_count = business_result.get("serviceLineCount", 0)
                run_log_path = ""
                for artifact in payload.get("artifacts", []):
                    if str(artifact.get("kind", "")).strip().lower() == "log":
                        run_log_path = str(artifact.get("path", "")).strip()
                        break
                if po_number:
                    self._set_last_po_number(po_number)
                    if run_log_path:
                        self._append_log(f"Pedido criado: {po_number} | Log: {run_log_path}")
                    self.status_var.set(
                        f"Concluido. Pedido criado: {po_number} | Itens: {item_count} | Linhas: {service_line_count}"
                    )
                else:
                    self._set_last_po_number(None)
                    if payload.get("status") == "dry_run":
                        suffix = f" | Log: {run_log_path}" if run_log_path else ""
                        self.status_var.set(
                            f"DRY_RUN concluido sem salvar pedido. Desmarque DRY_RUN para criar o numero.{suffix}"
                        )
                        continue
                    self.status_var.set(
                        f"Concluido com status {payload.get('status', '')}. Itens: {item_count} | Linhas: {service_line_count}"
                    )
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)


def main() -> int:
    root = tk.Tk()
    Me21nPanel(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
