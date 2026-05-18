import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from _panel_utils import ensure_repo_root, pick_session_thread_safe

ensure_repo_root()

from core.zme62.avaliacao import run_email_job


def _result_failure_message(payload: dict) -> str:
    result_status = str(payload.get("status", "") or "")
    if result_status not in ("error", "cancelled"):
        return ""

    errors = [str(item) for item in payload.get("errors", []) if str(item).strip()]
    if errors:
        return "\n".join(errors[:5])
    if result_status == "cancelled":
        return "Execucao cancelada antes de concluir o envio."
    return "O robo terminou com erro antes de processar os fornecedores."


class Zme62EnvioEmailPanel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Robo SAP - ZME62 Envio de Emails")
        self.root.geometry("760x560")
        self.root.minsize(700, 500)
        self.root.configure(bg="#f4f7fb")

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False

        self.ano_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Pronto. Informe o ano e os fornecedores ja avaliados.")

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
        ttk.Label(header, text="Robo SAP - ZME62 Envio de Emails", style="HeaderTitle.TLabel").place(x=24, y=18)
        ttk.Label(
            header,
            text="Envia por email avaliacoes finais ja salvas na ZME62.",
            style="HeaderText.TLabel",
        ).place(x=26, y=56)

        outer = ttk.Frame(self.root, style="Card.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=24, pady=14)

        form = ttk.LabelFrame(outer, text="Envio", style="Section.TLabelframe", padding=12)
        form.pack(fill="both", expand=True)

        top_row = ttk.Frame(form, style="Card.TFrame")
        top_row.pack(fill="x")
        ttk.Label(top_row, text="Ano da avaliacao", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(top_row, textvariable=self.ano_var, width=12).grid(row=1, column=0, sticky="w", pady=(4, 0))

        fornecedores_frame = ttk.LabelFrame(form, text="Fornecedores (um por linha)", style="Section.TLabelframe", padding=8)
        fornecedores_frame.pack(fill="both", expand=True, pady=(14, 0))
        ttk.Label(
            fornecedores_frame,
            text="Cole os codigos dos fornecedores que ja possuem avaliacao final salva.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 6))

        text_frame = ttk.Frame(fornecedores_frame, style="Card.TFrame")
        text_frame.pack(fill="both", expand=True)
        scroll = ttk.Scrollbar(text_frame, orient="vertical")
        scroll.pack(side="right", fill="y")
        self.fornecedores_text = tk.Text(
            text_frame,
            height=12,
            width=30,
            font=("Consolas", 9),
            relief="solid",
            borderwidth=1,
            yscrollcommand=scroll.set,
        )
        self.fornecedores_text.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.fornecedores_text.yview)

        button_row = ttk.Frame(form, style="Card.TFrame")
        button_row.pack(fill="x", pady=(12, 0))
        self.execute_button = ttk.Button(
            button_row,
            text="Enviar emails",
            command=self._start_execution,
            style="Accent.TButton",
        )
        self.execute_button.pack(side="left")

        status_panel = ttk.Frame(outer, style="Status.TFrame", padding=10)
        status_panel.pack(fill="x", pady=(10, 0))
        ttk.Label(status_panel, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

    def _parse_fornecedores(self) -> tuple[list[str], list[str]]:
        raw = self.fornecedores_text.get("1.0", tk.END)
        fornecedores: list[str] = []
        errors: list[str] = []
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

    def _build_items(self, fornecedores: list[str], ano: str) -> list[dict]:
        return [
            {
                "fornecedor": fornecedor,
                "ano": ano,
                "grupo": 1,
            }
            for fornecedor in fornecedores
        ]

    def _start_execution(self) -> None:
        if self.is_running:
            return

        ano = self.ano_var.get().strip()
        if not ano:
            messagebox.showwarning("Validacao", "Informe o ano da avaliacao.", parent=self.root)
            return
        if not ano.isdigit():
            messagebox.showwarning("Validacao", "Ano deve conter apenas numeros.", parent=self.root)
            return

        fornecedores, errors = self._parse_fornecedores()
        if errors:
            messagebox.showerror("Fornecedores invalidos", "\n".join(errors), parent=self.root)
            return
        if not fornecedores:
            messagebox.showwarning("Validacao", "Cole ao menos um fornecedor.", parent=self.root)
            return

        items = self._build_items(fornecedores, ano)
        self.is_running = True
        self.execute_button.config(state="disabled")
        self.status_var.set(f"Enviando emails... 0/{len(items)}")
        threading.Thread(target=self._run, args=(items,), daemon=True).start()

    def _run(self, items: list[dict]) -> None:
        try:
            result = run_email_job(
                {"items": items},
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

    def _poll_queue(self) -> None:
        try:
            while True:
                status, payload = self.result_queue.get_nowait()
                if status == "log":
                    self.status_var.set(str(payload))
                    continue
                if status == "progress":
                    _stage, current, total = payload
                    self.status_var.set(f"Enviando emails... {current}/{total}")
                    continue

                self.is_running = False
                self.execute_button.config(state="normal")

                if status == "error":
                    self.status_var.set(f"Falha: {payload}")
                    messagebox.showerror("Falha no envio de emails ZME62", str(payload), parent=self.root)
                    continue

                failure_message = _result_failure_message(payload)
                if failure_message:
                    self.status_var.set(f"Falha: {failure_message}")
                    messagebox.showerror("Falha no envio de emails ZME62", failure_message, parent=self.root)
                    continue

                biz = payload.get("business_result", {})
                ok = biz.get("successCount", 0)
                fail = biz.get("failCount", 0)
                total_items = biz.get("totalItems", 0)
                self.status_var.set(f"Envio concluido. {total_items} processado(s) | Sucesso: {ok} | Falha: {fail}")
                if fail:
                    messagebox.showwarning(
                        "Envio concluido com falhas",
                        f"{ok} fornecedor(es) enviado(s) com sucesso.\n{fail} com falha.\n\nConsulte os logs para detalhes.",
                        parent=self.root,
                    )
                else:
                    messagebox.showinfo(
                        "Envio concluido",
                        f"{ok} fornecedor(es) enviado(s) com sucesso.",
                        parent=self.root,
                    )
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)


def main() -> int:
    root = tk.Tk()
    Zme62EnvioEmailPanel(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
