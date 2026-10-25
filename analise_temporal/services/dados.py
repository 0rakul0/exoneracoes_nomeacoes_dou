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


def load_state_consolidated(state: str):
    """Carrega os consolidados de uma UF, retornando (retornos, movimentacoes)."""
    state_dir = CONSOLIDADO_DIR / state.upper()
    mov_path = state_dir / "movimentacoes.parquet"
    ret_path = state_dir / "retornos.parquet"
    if not mov_path.exists() or not ret_path.exists():
        raise FileNotFoundError(
            f"Consolidado da UF {state.upper()} nao encontrado em {state_dir}. "
            "Execute python scripts/consolidar_dados.py."
        )
    return pd.read_parquet(ret_path), pd.read_parquet(mov_path)


def available_consolidated_states() -> list[str]:
    """Lista as UFs que possuem os dois arquivos consolidados por estado."""
    states = []
    for state_dir in sorted(CONSOLIDADO_DIR.iterdir() if CONSOLIDADO_DIR.exists() else []):
        if not state_dir.is_dir():
            continue
        if (state_dir / "movimentacoes.parquet").exists() and (state_dir / "retornos.parquet").exists():
            states.append(state_dir.name.upper())
    return states


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

