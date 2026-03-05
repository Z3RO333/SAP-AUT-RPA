from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def pick_session(sessions: list[dict], parent: tk.Misc | None = None) -> str | None:
    selected_ref: str | None = None
    root = tk.Toplevel(parent) if parent is not None else tk.Tk()
    root.title("Selecionar sessao SAP")
    root.geometry("840x420")
    root.grab_set()

    frame = ttk.Frame(root, padding=12)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Ha mais de uma sessao SAP disponivel. Escolha a sessao a usar.").pack(anchor="w")

    columns = ("ref", "conn", "client", "user", "tcode", "title")
    tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
    tree.heading("ref", text="Ref")
    tree.heading("conn", text="Conexao")
    tree.heading("client", text="Cliente")
    tree.heading("user", text="Usuario")
    tree.heading("tcode", text="Transacao")
    tree.heading("title", text="Janela")
    tree.column("ref", width=70, anchor="center")
    tree.column("conn", width=180, anchor="w")
    tree.column("client", width=60, anchor="center")
    tree.column("user", width=90, anchor="center")
    tree.column("tcode", width=90, anchor="center")
    tree.column("title", width=320, anchor="w")
    tree.pack(fill="both", expand=True, pady=(8, 10))

    for session in sessions:
        tree.insert(
            "",
            tk.END,
            iid=session["session_ref"],
            values=(
                session["session_ref"],
                session.get("connection_name", ""),
                session.get("client", ""),
                session.get("user", ""),
                session.get("transaction", ""),
                session.get("window_title", ""),
            ),
        )

    def _confirm() -> None:
        nonlocal selected_ref
        selection = tree.selection()
        if selection:
            selected_ref = selection[0]
        root.destroy()

    def _cancel() -> None:
        root.destroy()

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")
    ttk.Button(button_row, text="Usar sessao", command=_confirm).pack(side="left")
    ttk.Button(button_row, text="Cancelar", command=_cancel).pack(side="left", padx=(8, 0))

    if sessions:
        tree.selection_set(sessions[0]["session_ref"])
        tree.focus(sessions[0]["session_ref"])
    tree.bind("<Double-1>", lambda _event: _confirm())
    root.wait_window()
    return selected_ref
