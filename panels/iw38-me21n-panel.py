import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from _panel_utils import ensure_repo_root

ensure_repo_root()

from core.common.logging import ExecutionLogger
from core.common.run_context import RunContext
from core.common.runtime import ensure_dir, run_output_dir
from core.common.sap_session import resolve_session
from core.common.session_picker import pick_session


class Iw38Me21nPanel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Robo SAP - IW38 → ME21N")
        self.root.geometry("700x560")
        self.root.minsize(600, 480)
        self.root.configure(bg="#f4f7fb")
        try:
            self.root.state("zoomed")
        except tk.TclError:
            pass

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False

        self.tcode_var = tk.StringVar(value="IW38")
        self.status_var = tk.StringVar(value="Cole as ordens e clique Executar.")

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
        style.configure("Subtle.TButton", font=("Segoe UI", 9))

    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", height=90)
        header.pack(fill="x")
        header.pack_propagate(False)
        ttk.Label(header, text="IW38 \u2192 ME21N - Criar Pedido por Ordens", style="HeaderTitle.TLabel").place(x=24, y=16)
        ttk.Label(
            header,
            text="Cola as ordens, executa o relatorio IW38, seleciona tudo e abre a criacao de pedido ME21N.",
            style="HeaderText.TLabel",
        ).place(x=26, y=54)

        outer = ttk.Frame(self.root, style="Card.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=24, pady=18)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        top = ttk.LabelFrame(outer, text="Configuracao", style="Section.TLabelframe", padding=12)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(top, text="Transacao", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(top, textvariable=self.tcode_var, width=12).grid(row=0, column=1, sticky="w", padx=(0, 20))
        ttk.Label(
            top,
            text="Normalmente IW38. Altere somente se o seu ambiente usa outro codigo de transacao.",
            style="Muted.TLabel",
        ).grid(row=0, column=2, sticky="w")

        ordens_frame = ttk.LabelFrame(outer, text="Numeros de Ordem (AUFNR)", style="Section.TLabelframe", padding=12)
        ordens_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        ordens_frame.columnconfigure(0, weight=1)
        ordens_frame.rowconfigure(1, weight=1)
        ttk.Label(
            ordens_frame,
            text="Cole os numeros de ordem abaixo — um por linha. O robo carrega tudo na selecao multipla do SAP.",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.ordens_text = scrolledtext.ScrolledText(ordens_frame, height=14, font=("Consolas", 10), wrap="none")
        self.ordens_text.grid(row=1, column=0, sticky="nsew")

        controls = ttk.Frame(outer, style="Card.TFrame")
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.execute_button = ttk.Button(controls, text="Executar", command=self._execute, style="Accent.TButton")
        self.execute_button.pack(side="left")
        ttk.Button(controls, text="Limpar", command=self._clear, style="Subtle.TButton").pack(side="left", padx=(8, 0))

        status_panel = ttk.Frame(outer, style="Status.TFrame", padding=10)
        status_panel.grid(row=3, column=0, sticky="ew")
        ttk.Label(status_panel, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

        self.log_text = scrolledtext.ScrolledText(outer, height=7, font=("Consolas", 9), wrap="word")
        self.log_text.grid(row=4, column=0, sticky="ew", pady=(10, 0))

    def _clear(self) -> None:
        self.ordens_text.delete("1.0", tk.END)
        self.log_text.delete("1.0", tk.END)
        self.status_var.set("Pronto.")

    def _parse_ordens(self) -> list[str]:
        raw = self.ordens_text.get("1.0", tk.END)
        ordens = []
        for line in raw.splitlines():
            value = line.strip()
            if value:
                ordens.append(value)
        return ordens

    def _append_log(self, message: str) -> None:
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def _thread_safe_chooser(self, sessions: list) -> str | None:
        result_holder: list[str | None] = [None]
        done = threading.Event()

        def _show():
            result_holder[0] = pick_session(sessions, self.root)
            done.set()

        self.root.after(0, _show)
        done.wait()
        return result_holder[0]

    def _execute(self) -> None:
        if self.is_running:
            return
        ordens = self._parse_ordens()
        if not ordens:
            messagebox.showwarning("Ordens", "Cole ao menos uma ordem antes de executar.")
            return
        tcode_name = self.tcode_var.get().strip() or "IW38"
        self.is_running = True
        self.execute_button.config(state="disabled")
        self.status_var.set(f"Executando com {len(ordens)} ordem(ns)...")
        self.log_text.delete("1.0", tk.END)
        worker = threading.Thread(target=self._run, args=(ordens, tcode_name), daemon=True)
        worker.start()

    def _run(self, ordens: list[str], tcode_name: str) -> None:
        from core.iw38_me21n.driver import execute_iw38_me21n

        try:
            session, _info = resolve_session(allow_manual_login=True, chooser=self._thread_safe_chooser)
            output_dir = run_output_dir("IW38-ME21N")
            ensure_dir(output_dir)
            logger = ExecutionLogger(
                output_dir / "run.log",
                callback=lambda msg: self.result_queue.put(("log", msg)),
            )
            context = RunContext(logger=logger)
            execute_iw38_me21n(session, ordens, context, tcode_name=tcode_name)
            self.result_queue.put(("success", len(ordens)))
        except Exception as exc:
            self.result_queue.put(("error", str(exc)))

    def _poll_queue(self) -> None:
        try:
            while True:
                status, payload = self.result_queue.get_nowait()
                if status == "log":
                    self._append_log(str(payload))
                    continue
                self.is_running = False
                self.execute_button.config(state="normal")
                if status == "error":
                    self.status_var.set(f"Falha: {payload}")
                    messagebox.showerror("Falha no robo", str(payload))
                else:
                    self.status_var.set(f"Concluido. {payload} ordem(ns) processadas. ME21N aberta no SAP.")
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)


def main() -> int:
    root = tk.Tk()
    Iw38Me21nPanel(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
