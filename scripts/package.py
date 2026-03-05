from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_SCRIPT = ROOT / "installer" / "RobosSAP.iss"


def _iscc() -> str:
    exe = shutil.which("iscc")
    if exe:
        return exe
    default_path = Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")
    if default_path.exists():
        return str(default_path)
    raise RuntimeError("ISCC.exe nao encontrado. Instale o Inno Setup 6.")


def main() -> int:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build.py")], check=True, cwd=ROOT)
    subprocess.run([_iscc(), str(INSTALLER_SCRIPT)], check=True, cwd=ROOT)
    print("Instalador gerado com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
