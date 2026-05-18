import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from _panel_utils import ensure_repo_root, pick_session_thread_safe, result_failure_message

ensure_repo_root()

from core.iw32.liberar import run_job


class Iw32LiberarPanel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Robo SAP IW32 - Liberar Ordens")
        self.root.geometry("860x620")
        self.root.minsize(860, 620)
        self.root.configure(bg="#f4f7fb")

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False

        self.status_var = tk.StringVar(value="Pronto. Cole os numeros de ordem abaixo e clique Executar.")

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
        ttk.Label(header, text="Robo SAP IW32 - Liberar Ordens", style="HeaderTitle.TLabel").place(x=24, y=18)
        ttk.Label(header, text="Cole os numeros de ordem (um por linha) e execute para liberar em lote.", style="HeaderText.TLabel").place(x=26, y=56)

        outer = ttk.Frame(self.root, style="Card.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=24, pady=22)

        input_group = ttk.LabelFrame(outer, text="Ordens a liberar", style="Section.TLabelframe", padding=12)
        input_group.pack(fill="both", expand=True)

        ttk.Label(input_group, text="Numeros de ordem (um por linha):", style="Muted.TLabel").pack(anchor="w")

        text_frame = ttk.Frame(input_group, style="Card.TFrame")
        text_frame.pack(fill="both", expand=True, pady=(4, 10))

        scrollbar = ttk.Scrollbar(text_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self.orders_text = tk.Text(
            text_frame,
            height=8,
            font=("Consolas", 10),
            yscrollcommand=scrollbar.set,
            relief="solid",
            borderwidth=1,
        )
        self.orders_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.orders_text.yview)

        btn_row = ttk.Frame(input_group, style="Card.TFrame")
        btn_row.pack(fill="x")
        self.execute_button = ttk.Button(btn_row, text="Executar", command=self.start_execution, style="Accent.TButton")
        self.execute_button.pack(side="left")
        ttk.Button(btn_row, text="Limpar", command=self._clear).pack(side="left", padx=(8, 0))

        status_panel = ttk.Frame(outer, style="Status.TFrame", padding=10)
        status_panel.pack(fill="x", pady=(14, 10))
        ttk.Label(status_panel, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

        ttk.Label(outer, text="Resultados por ordem:", style="Muted.TLabel").pack(anchor="w")

        tree_frame = ttk.Frame(outer, style="Card.TFrame")
        tree_frame.pack(fill="both", expand=True, pady=(4, 0))

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical")
        tree_scroll.pack(side="right", fill="y")

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("aufnr", "resultado", "detalhe"),
            show="headings",
            height=8,
            yscrollcommand=tree_scroll.set,
        )
        self.tree.heading("aufnr", text="Ordem")
        self.tree.heading("resultado", text="Resultado")
        self.tree.heading("detalhe", text="Detalhe")
        self.tree.column("aufnr", width=120, anchor="center")
        self.tree.column("resultado", width=100, anchor="center")
        self.tree.column("detalhe", width=500, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.config(command=self.tree.yview)

        self.tree.tag_configure("ok", foreground="#16a34a")
        self.tree.tag_configure("fail", foreground="#dc2626")

    def start_execution(self) -> None:
        if self.is_running:
            return

        raw = self.orders_text.get("1.0", tk.END)
        orders = [line.strip() for line in raw.splitlines() if line.strip()]

        if not orders:
            messagebox.showwarning("Validacao", "Informe pelo menos um numero de ordem.")
            return

        for item in self.tree.get_children():
            self.tree.delete(item)

        self.execute_button.config(state="disabled")
        self.status_var.set(f"Executando... {len(orders)} ordens a processar.")
        self.is_running = True

        worker = threading.Thread(target=self._run, args=(orders,), daemon=True)
        worker.start()

    def _run(self, orders: list[str]) -> None:
        try:
            result = run_job(
                {"orders": orders},
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
                ok = sum(1 for r in results if r.get("success"))
                fail = len(results) - ok

                for r in results:
                    tag = "ok" if r.get("success") else "fail"
                    detalhe = r.get("statusBar") or r.get("error") or ""
                    label = "OK" if r.get("success") else "FALHA"
                    self.tree.insert("", tk.END, values=(r.get("aufnr", ""), label, detalhe), tags=(tag,))

                self.status_var.set(f"Concluido. Sucesso: {ok} | Falha: {fail}")
        except queue.Empty:
            pass

        self.root.after(200, self._poll_queue)

    def _clear(self) -> None:
        self.orders_text.delete("1.0", tk.END)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.status_var.set("Pronto. Cole os numeros de ordem abaixo e clique Executar.")


def main() -> int:
    root = tk.Tk()
    Iw32LiberarPanel(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
