from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALISES_DIR = PROJECT_ROOT / "saida" / "analises"
CONSOLIDADO_DIR = PROJECT_ROOT / "saida" / "consolidado"

RETORNO_COLUMNS = [
    "nome_normalizado", "data_publicacao", "data_exoneracao_anterior",
    "orgao", "cargo_assinante", "governador_edicao",
    "mudou_cargo_desde_exoneracao", "mudou_orgao_desde_exoneracao",
    "dias_desde_exoneracao",
]
MOVIMENTACAO_COLUMNS = [
    "nome_normalizado", "data_publicacao", "tipo_ato", "orgao",
    "cargo_assinante", "governador_edicao",
]
CATEGORY_COLUMNS = [
    "estado", "tipo_ato", "orgao", "cargo_assinante", "autoria_ato",
    "governador_edicao", "representante_governo", "origem_representante",
    "representante_origem",
]

MOV_COLUMNS_KEEP = [
    "estado", "ano", "tipo_ato", "orgao", "cargo_assinante", "autoria_ato",
    "governador_edicao", "representante_governo", "origem_representante",
    "representante_origem", "pessoa", "data_movimentacao",
]
RET_COLUMNS_KEEP = [
    "estado", "ano", "orgao", "cargo_assinante", "autoria_ato",
    "governador_edicao", "representante_governo", "origem_representante",
    "representante_origem", "pessoa", "data_nomeacao", "data_exoneracao",
    "mudou_cargo", "mudou_orgao", "tempo_cluster", "estado_N",
    "dias_desde_exoneracao",
]


def nome_representante_governo(governo: str) -> str:
    governo = str(governo or "Nao identificado").strip()
    if " - " not in governo:
        return governo
    return governo.split(" - ", 1)[0].strip() or "Nao identificado"


def origem_representante_governo(governo: str) -> str:
    nome = nome_representante_governo(governo)
    origem_por_nome = {
        "Andre Ceciliano": "ALERJ",
        "Claudio Bomfim de Castro e Silva": "Executivo estadual",
        "Francisco Dornelles": "Vice-governadoria",
        "Luiz Fernando de Souza": "Executivo estadual",
        "Paulo Melo": "ALERJ",
        "Rodrigo Bacellar": "ALERJ",
        "Ricardo Couto de Castro": "TJ-RJ",
        "Sergio Cabral": "Executivo estadual",
        "Thiago Pampolha": "Vice-governadoria",
        "Wilson Jose Witzel": "Executivo estadual",
    }
    if nome == "Nao identificado":
        return "Nao identificado"
    if nome in origem_por_nome:
        return origem_por_nome[nome]
    if "Governador em exerc" in str(governo or ""):
        return "Vice-governadoria"
    return "Executivo estadual"


def classificar_autoria_ato(frame: pd.DataFrame) -> pd.Series:
    cargos = frame["cargo_assinante"].fillna("").astype(str).str.strip()
    secretaria = cargos.str.match(r"^(?:Subsecret.rio|Secret.rio)(?:\b|\s+-)", case=False)
    governador = cargos.str.match(r"^Governador(?:\b|\s+-)", case=False)
    autoria = pd.Series("Outro/Nao identificado", index=frame.index)
    autoria.loc[governador] = "Governador"
    autoria.loc[secretaria] = "Secretaria/Subsecretaria"
    return autoria


def compact_frame(frame: pd.DataFrame) -> None:
    for column in CATEGORY_COLUMNS:
        if column in frame.columns:
            frame[column] = frame[column].astype("category")


def norm_bool(x):
    if isinstance(x, str):
        return x.strip().lower() == "sim"
    return bool(x)


def classificar_tempo(dias):
    if pd.isna(dias):
        return "desconhecido"
    if dias == 0:
        return "imediato"
    if dias < 30:
        return "curto"
    if dias <= 180:
        return "medio"
    return "longo"


def classificar_estado(row):
    tempo = row["tempo_cluster"]
    cargo = "novo_cargo" if row["mudou_cargo"] else "mesmo_cargo"
    orgao = "novo_orgao" if row["mudou_orgao"] else "mesmo_orgao"
    return f"N_{tempo}_{cargo}_{orgao}"


def process_mov(df_mov: pd.DataFrame) -> pd.DataFrame:
    df_mov["pessoa"] = df_mov["nome_normalizado"]
    df_mov["data_movimentacao"] = pd.to_datetime(df_mov["data_publicacao"], errors="coerce")
    if "ano" not in df_mov.columns:
        df_mov["ano"] = df_mov["data_movimentacao"].dt.year
    else:
        df_mov["ano"] = pd.to_numeric(df_mov["ano"], errors="coerce").astype("Int64")
    df_mov["ano"] = df_mov["ano"].fillna(df_mov["data_movimentacao"].dt.year).astype(int)
    df_mov["autoridade_assinante"] = (
        df_mov["cargo_assinante"].fillna("").astype(str).str.strip().replace("", "Sem identificacao")
    )
    if "autoria_ato" not in df_mov.columns:
        df_mov["autoria_ato"] = classificar_autoria_ato(df_mov)
    df_mov["governador_edicao"] = (
        df_mov["governador_edicao"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
    )
    df_mov["representante_governo"] = df_mov["governador_edicao"].map(nome_representante_governo)
    df_mov["origem_representante"] = df_mov["governador_edicao"].map(origem_representante_governo)
    for frame in [df_mov]:
        frame["representante_governo"] = (
            frame["representante_governo"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
        )
        frame["origem_representante"] = (
            frame["origem_representante"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
        )
        frame["representante_origem"] = (
            frame["representante_governo"].astype(str) + " (" + frame["origem_representante"].astype(str) + ")"
        )
    compact_frame(df_mov)
    return df_mov[MOV_COLUMNS_KEEP]


def process_ret(df: pd.DataFrame) -> pd.DataFrame:
    df["pessoa"] = df["nome_normalizado"]
    df["data_nomeacao"] = pd.to_datetime(df["data_publicacao"], errors="coerce")
    df["data_exoneracao"] = pd.to_datetime(df["data_exoneracao_anterior"], errors="coerce")
    if "ano" not in df.columns:
        df["ano"] = df["data_nomeacao"].dt.year
    else:
        df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df["ano"] = df["ano"].fillna(df["data_nomeacao"].dt.year).astype(int)
    df["autoridade_assinante"] = (
        df["cargo_assinante"].fillna("").astype(str).str.strip().replace("", "Sem identificacao")
    )
    if "autoria_ato" not in df.columns:
        df["autoria_ato"] = classificar_autoria_ato(df)
    df["governador_edicao"] = (
        df["governador_edicao"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
    )
    df["representante_governo"] = df["governador_edicao"].map(nome_representante_governo)
    df["origem_representante"] = df["governador_edicao"].map(origem_representante_governo)
    for frame in [df]:
        frame["representante_governo"] = (
            frame["representante_governo"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
        )
        frame["origem_representante"] = (
            frame["origem_representante"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
        )
        frame["representante_origem"] = (
            frame["representante_governo"].astype(str) + " (" + frame["origem_representante"].astype(str) + ")"
        )
    df["mudou_cargo"] = df["mudou_cargo_desde_exoneracao"].apply(norm_bool)
    df["mudou_orgao"] = df["mudou_orgao_desde_exoneracao"].apply(norm_bool)
    df["tempo_cluster"] = df["dias_desde_exoneracao"].apply(classificar_tempo)
    df["estado_N"] = df.apply(classificar_estado, axis=1)
    compact_frame(df)
    return df[RET_COLUMNS_KEEP]


def consolidate():
    CONSOLIDADO_DIR.mkdir(parents=True, exist_ok=True)

    mov_frames = []
    ret_frames = []

    for state_dir in sorted(ANALISES_DIR.iterdir()):
        if not state_dir.is_dir():
            continue
        state = state_dir.name.upper()
        ret_path = state_dir / "retornos_apos_exoneracao.csv"
        mov_path = state_dir / "movimentacoes_pessoas.parquet"
        if not ret_path.exists() or not mov_path.exists():
            print(f"  Pulando {state_dir.name}: dados incompletos")
            continue

        print(f"  Processando {state}...")
        raw_mov = pd.read_parquet(mov_path, columns=MOVIMENTACAO_COLUMNS)
        raw_ret = pd.read_csv(ret_path, usecols=lambda c: c in RETORNO_COLUMNS)

        raw_mov["estado"] = state
        raw_ret["estado"] = state

        mov_frames.append(process_mov(raw_mov))
        ret_frames.append(process_ret(raw_ret))

    if not mov_frames:
        print("ERRO: Nenhum dado encontrado.")
        sys.exit(1)

    mov = pd.concat(mov_frames, ignore_index=True)
    ret = pd.concat(ret_frames, ignore_index=True)

    mov_path = CONSOLIDADO_DIR / "movimentacoes.parquet"
    ret_path = CONSOLIDADO_DIR / "retornos.parquet"

    mov.to_parquet(mov_path, index=False, compression="zstd")
    ret.to_parquet(ret_path, index=False, compression="zstd")

    print(f"\nOK: Consolidado salvo em {CONSOLIDADO_DIR}")
    print(f"  movimentacoes.parquet: {len(mov)} linhas, {mov_path.stat().st_size / 1024**2:.1f} MB")
    print(f"  retornos.parquet:      {len(ret)} linhas, {ret_path.stat().st_size / 1024**2:.1f} MB")


if __name__ == "__main__":
    consolidate()
