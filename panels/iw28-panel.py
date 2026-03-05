import tkinter as tk
from tkinter import messagebox


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(
        "IW28 pendente",
        "IW28 ainda nao foi implementado nesta fase. Use o painel IW38 por enquanto.",
    )
    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
