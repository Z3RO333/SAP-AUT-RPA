from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"

# Pacotes que precisam ser coletados completamente (submodulos dinamicos)
COLLECT_ALL = [
    "win32com",
    "openpyxl",
    "pandas",
    "reportlab",
]

# Submodulos que precisam ser forçados no bundle para execucao dinamica via runpy.
COLLECT_SUBMODULES = [
    "tkinter",
    "core",
]

# Imports ocultos que o PyInstaller nao detecta automaticamente
HIDDEN_IMPORTS = [
    "pythoncom",
    "win32com.client",
    "win32com.server.policy",
    "win32api",
    "win32con",
    "pywintypes",
    "tkinter.filedialog",
    "tkinter.scrolledtext",
]


def _pyinstaller() -> list[str]:
    exe = shutil.which("pyinstaller")
    if exe:
        return [exe]
    # Fallback: rodar como modulo Python (pip install --user coloca so no PATH as vezes)
    return [sys.executable, "-m", "PyInstaller"]


def main() -> int:
    DIST_DIR.mkdir(exist_ok=True)
    BUILD_DIR.mkdir(exist_ok=True)

    command = [
        *_pyinstaller(),
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name", "RobosSAP",
        "--paths", str(ROOT),
        # Dados estaticos
        "--add-data", f"{ROOT / 'sap'};sap",
        "--add-data", f"{ROOT / 'docs'};docs",
        "--add-data", f"{ROOT / 'templates'};templates",
        # Paineis e modulos core incluidos como dados para execucao via Python do sistema
        "--add-data", f"{ROOT / 'panels'};panels",
        "--add-data", f"{ROOT / 'core'};core",
    ]

    for pkg in COLLECT_ALL:
        command += ["--collect-all", pkg]

    for module_name in COLLECT_SUBMODULES:
        command += ["--collect-submodules", module_name]

    for imp in HIDDEN_IMPORTS:
        command += ["--hidden-import", imp]

    command.append(str(ROOT / "panels" / "menu-principal.py"))

    subprocess.run(command, check=True, cwd=ROOT)
    print(f"Build concluido em: {DIST_DIR / 'RobosSAP'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
