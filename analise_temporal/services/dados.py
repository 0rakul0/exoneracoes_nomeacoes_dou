from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALISES_DIR = PROJECT_ROOT / "saida" / "analises"
CONSOLIDADO_DIR = PROJECT_ROOT / "saida" / "consolidado"
CONSOLIDATED_MOV = CONSOLIDADO_DIR / "movimentacoes.parquet"
CONSOLIDATED_RET = CONSOLIDADO_DIR / "retornos.parquet"


def _load_consolidated():
    return (
        pd.read_parquet(CONSOLIDATED_RET),
        pd.read_parquet(CONSOLIDATED_MOV),
    )


def _consolidar():
    script = PROJECT_ROOT / "scripts" / "consolidar_dados.py"
    if not script.exists():
        raise FileNotFoundError(
            f"Script de consolidacao nao encontrado: {script}. "
            "Execute python scripts/consolidar_dados.py manualmente."
        )
    subprocess.run([sys.executable, str(script)], check=True, cwd=str(PROJECT_ROOT))


if CONSOLIDATED_MOV.exists() and CONSOLIDATED_RET.exists():
    df, df_mov = _load_consolidated()
else:
    print("Consolidado nao encontrado. Executando consolidacao...")
    _consolidar()
    df, df_mov = _load_consolidated()


def reload_analysis_base():
    _consolidar()
    return _load_consolidated()

