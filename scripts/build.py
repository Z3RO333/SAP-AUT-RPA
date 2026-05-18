from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"

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

# Modulos opcionais/testes que deixam o pacote enorme e criam problemas ao
# copiar/extrair em outros computadores.
EXCLUDE_MODULES = [
    "matplotlib",
    "pytest",
    "_pytest",
    "pandas.tests",
    "numpy.tests",
    "pyarrow.tests",
    "openpyxl.tests",
    "reportlab.tests",
    "win32com.test",
    "win32com.demos",
]


def _pyinstaller() -> list[str]:
    exe = shutil.which("pyinstaller")
    if exe:
        return [exe]
    # Fallback: rodar como modulo Python (pip install --user coloca so no PATH as vezes)
    return [sys.executable, "-m", "PyInstaller"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera o executavel RobosSAP.")
    parser.add_argument(
        "--portable",
        action="store_true",
        help="Gera um unico RobosSAP-Portable.exe em vez da pasta onedir.",
    )
    args = parser.parse_args()

    DIST_DIR.mkdir(exist_ok=True)
    BUILD_DIR.mkdir(exist_ok=True)

    command = [
        *_pyinstaller(),
        "--noconfirm",
        "--clean",
        "--onefile" if args.portable else "--onedir",
        "--name", "RobosSAP-Portable" if args.portable else "RobosSAP",
        "--paths", str(ROOT),
        # Dados estaticos
        "--add-data", f"{ROOT / 'sap'};sap",
        "--add-data", f"{ROOT / 'docs'};docs",
        "--add-data", f"{ROOT / 'templates'};templates",
        # Paineis e modulos core incluidos como dados para execucao via Python do sistema
        "--add-data", f"{ROOT / 'panels'};panels",
        "--add-data", f"{ROOT / 'core'};core",
    ]

    for module_name in COLLECT_SUBMODULES:
        command += ["--collect-submodules", module_name]

    for imp in HIDDEN_IMPORTS:
        command += ["--hidden-import", imp]

    for module_name in EXCLUDE_MODULES:
        command += ["--exclude-module", module_name]

    command.append(str(ROOT / "panels" / "menu-principal.py"))

    subprocess.run(command, check=True, cwd=ROOT)
    if args.portable:
        print(f"Build concluido em: {DIST_DIR / 'RobosSAP-Portable.exe'}")
    else:
        print(f"Build concluido em: {DIST_DIR / 'RobosSAP'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
