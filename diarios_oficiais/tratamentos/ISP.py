from __future__ import annotations

import subprocess
import sys
from pathlib import Path


# ============================================================
# PIPELINE ISP
# ============================================================
#
# Como usar:
#   de play neste arquivo.
#
# O script usa os artefatos ja existentes do extrator e roda:
#   1. tratamento das normativas de area de atuacao;
#   2. matriz CISP / O_que_muda_onde;
#   3. cache Parquet + GeoJSON simplificado para o painel.
#
# Depois disso, suba o painel com:
#   subir_dash_isp.bat
# ============================================================


BASE_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent

PYTHON = sys.executable

SCRIPTS = [
    SCRIPTS_DIR / "tratar_normativas_area_atuacao_isp.py",
    SCRIPTS_DIR / "gerar_matriz_cisp_alteracoes.py",
    SCRIPTS_DIR / "gerar_cache_dashboard_isp.py",
]


def executar(script: Path) -> None:
    if not script.exists():
        raise FileNotFoundError(f"Script nao encontrado: {script}")

    print("\n" + "=" * 70)
    print(script.name)
    print("=" * 70)
    subprocess.run([PYTHON, str(script)], cwd=BASE_DIR, check=True)


def main() -> None:
    print("=" * 70)
    print("PIPELINE ISP")
    print("=" * 70)
    print(f"Pasta base: {BASE_DIR}")
    print(f"Python: {PYTHON}")

    for script in SCRIPTS:
        executar(script)

    print("\n" + "=" * 70)
    print("PIPELINE ISP CONCLUIDO")
    print("=" * 70)
    print("Agora voce pode subir o painel com subir_dash_isp.bat.")


if __name__ == "__main__":
    main()
