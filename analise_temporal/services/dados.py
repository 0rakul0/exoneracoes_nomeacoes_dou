from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALISES_DIR = PROJECT_ROOT / "saida" / "analises"

def governador_da_edicao(markdown_path):
    if not markdown_path:
        return "Não identificado"

    path = Path(str(markdown_path))
    if not path.exists():
        return "Não identificado"

    try:
        text = path.read_text(encoding="utf-8", errors="ignore").upper()
    except OSError:
        return "Não identificado"

    acting_phrase = "GOVERNADOR EM EXERC" in text or "GOVERNADOR EM EXERCÃ" in text
    if acting_phrase:
        acting_name = extract_governor_name_near_acting_phrase(text)
        if acting_name:
            return f"{acting_name} - Governador em exercício"

    governor_name = extract_named_role(text, "GOVERNADOR", stop_role="VICE-GOVERNADOR")
    if governor_name:
        return f"{governor_name} - Governador"

    return "Nao identificado"


def governador_por_data_do_arquivo(path):
    return "Nao identificado"


def extract_governor_name_near_acting_phrase(text):
    known_names = [
        ("LUIZ FERNANDO DE SOUZA", "Luiz Fernando de Souza"),
        ("SERGIO CABRAL", "Sergio Cabral"),
        ("SÉRGIO CABRAL", "Sergio Cabral"),
        ("SÃ‰RGIO CABRAL", "Sergio Cabral"),
        ("RICARDO COUTO", "Ricardo Couto de Castro"),
        ("THIAGO PAMPOLHA", "Thiago Pampolha"),
        ("THIA GO P AM PO LHA", "Thiago Pampolha"),
        ("RODRIGO BACELLAR", "Rodrigo Bacellar"),
        ("CLÁUDIO BOMFIM DE CASTRO E SILVA", "Cláudio Bomfim de Castro e Silva"),
        ("CLAUDIO BOMFIM DE CASTRO E SILVA", "Cláudio Bomfim de Castro e Silva"),
        ("CLÁUDIO CASTRO", "Cláudio Bomfim de Castro e Silva"),
        ("CLAUDIO CASTRO", "Cláudio Bomfim de Castro e Silva"),
    ]

    phrase_re = re.compile(r"GOVERNADOR\s+EM\s+EXERC\S*CIO|GOVERNADOR\s+EM\s+EXERCÃ")
    found_acting_phrase = False
    for match in phrase_re.finditer(text):
        found_acting_phrase = True
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        if line_end == -1:
            line_end = len(text)
        signature = match_known_signature_line(text[line_start:line_end], known_names)
        if signature:
            return signature
        current_line = text[line_start:line_end].upper()
        if not re.search(r"\b(ATOS?|DESPACHOS?|DECRETOS?|EXPEDIENTE)\b", current_line):
            previous_window = text[max(0, line_start - 300):line_start]
            signature = match_known_signature_line(previous_window, known_names)
            if signature:
                return signature

        forward_window = text[match.end(): min(len(text), match.end() + 5000)]
        signature = match_known_signature_line(forward_window, known_names)
        if signature:
            return signature

    if found_acting_phrase:
        vice_governor = extract_named_role(text, "VICE-GOVERNADOR")
        if vice_governor:
            return vice_governor

    return ""


def match_known_signature_line(value, known_names):
    for raw_line in value.splitlines():
        normalized = re.sub(r"(?i)\bID\s*:?\s*\d+.*$", "", raw_line)
        normalized = re.sub(r"(?i)\bGOVERNADOR(?:\s+EM\s+EXERC\S*CIO)?\b", "", normalized)
        normalized = re.sub(r"(?i)\bVICE-GOVERNADOR\b", "", normalized)
        normalized = re.sub(r"[^A-ZÀ-ÜÃÕÇ\s]", " ", normalized.upper())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized:
            continue
        for needle, label in known_names:
            if normalized == needle or normalized.endswith(f" {needle}"):
                return label
    return ""


def extract_named_role(text, role, stop_role=None):
    prefix = text[:15000]
    escaped_role = r"(?<!VICE-)GOVERNADOR" if role.upper() == "GOVERNADOR" else re.escape(role)
    stop_pattern = re.escape(stop_role) if stop_role else r"ÓRG|Ã“RG|GOVERNO DO ESTADO|ATOS DO"
    match = re.search(
        rf"{escaped_role}\s+(?P<name>.{{3,120}}?)(?=\s+{stop_pattern}|\n|$)",
        prefix,
        flags=re.S,
    )
    if not match:
        return ""

    raw_name = re.sub(r"\s+", " ", match.group("name")).strip(" -|,.;:")
    raw_name = raw_name.replace("GONÃ‡ALVES", "Gonçalves")
    candidates = [
        ("LUIZ FERNANDO DE SOUZA", "Luiz Fernando de Souza"),
        ("SERGIO CABRAL", "Sergio Cabral"),
        ("SÉRGIO CABRAL", "Sergio Cabral"),
        ("SÃ‰RGIO CABRAL", "Sergio Cabral"),
        ("WILSON JOS", "Wilson Jose Witzel"),
        ("CLÁUDIO BOMFIM DE CASTRO E SILVA", "Cláudio Bomfim de Castro e Silva"),
        ("CLAUDIO BOMFIM DE CASTRO E SILVA", "Cláudio Bomfim de Castro e Silva"),
        ("CLÃ¡UDIO BOMFIM DE CASTRO E SILVA".upper(), "Cláudio Bomfim de Castro e Silva"),
        ("THIAGO PAMPOLHA", "Thiago Pampolha"),
        ("RICARDO COUTO", "Ricardo Couto de Castro"),
        ("RODRIGO BACELLAR", "Rodrigo Bacellar"),
    ]
    normalized = raw_name.upper()
    for needle, label in candidates:
        if needle in normalized:
            return label
    return ""


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


# =====================================================
# LOAD
# =====================================================
def read_state_csvs(analyses_dir):
    retorno_frames = []
    movimentacao_frames = []
    for state_dir in sorted(path for path in analyses_dir.iterdir() if path.is_dir()):
        state = state_dir.name.upper()
        retornos_path = state_dir / "retornos_apos_exoneracao.csv"
        movimentacoes_path = state_dir / "movimentacoes_pessoas.parquet"
        if not retornos_path.exists() or not movimentacoes_path.exists():
            continue

        retorno_frame = pd.read_csv(retornos_path)
        movimentacao_frame = pd.read_parquet(movimentacoes_path)
        retorno_frame["estado"] = state
        movimentacao_frame["estado"] = state
        retorno_frames.append(retorno_frame)
        movimentacao_frames.append(movimentacao_frame)

    if not retorno_frames or not movimentacao_frames:
        raise FileNotFoundError(f"Nenhuma analise por UF encontrada em {analyses_dir}")

    return pd.concat(retorno_frames, ignore_index=True), pd.concat(movimentacao_frames, ignore_index=True)


df, df_mov = read_state_csvs(ANALISES_DIR)

df["pessoa"] = df["nome_normalizado"]
df["data_nomeacao"] = pd.to_datetime(df["data_publicacao"], errors="coerce")
df["data_exoneracao"] = pd.to_datetime(df["data_exoneracao_anterior"], errors="coerce")
df["ano"] = df["data_nomeacao"].dt.year

df_mov["pessoa"] = df_mov["nome_normalizado"]
df_mov["data_movimentacao"] = pd.to_datetime(df_mov["data_publicacao"], errors="coerce")
df_mov["ano"] = df_mov["data_movimentacao"].dt.year

df["autoridade_assinante"] = (
    df["cargo_assinante"].fillna("").astype(str).str.strip().replace("", "Sem identificação")
)
df_mov["autoridade_assinante"] = (
    df_mov["cargo_assinante"].fillna("").astype(str).str.strip().replace("", "Sem identificação")
)
df["autoria_ato"] = classificar_autoria_ato(df)
df_mov["autoria_ato"] = classificar_autoria_ato(df_mov)
if "governador_edicao" not in df.columns:
    df["governador_edicao"] = "Nao identificado"
if "governador_edicao" not in df_mov.columns:
    df_mov["governador_edicao"] = "Nao identificado"
df["governador_edicao"] = df["governador_edicao"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
df_mov["governador_edicao"] = df_mov["governador_edicao"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
df["representante_governo"] = df["governador_edicao"].map(nome_representante_governo)
df_mov["representante_governo"] = df_mov["governador_edicao"].map(nome_representante_governo)
df["origem_representante"] = df["governador_edicao"].map(origem_representante_governo)
df_mov["origem_representante"] = df_mov["governador_edicao"].map(origem_representante_governo)
for frame in [df, df_mov]:
    frame["representante_governo"] = (
        frame["representante_governo"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
    )
    frame["origem_representante"] = (
        frame["origem_representante"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
    )
    frame["representante_origem"] = frame.apply(
        lambda row: f"{row['representante_governo']} ({row['origem_representante']})",
        axis=1,
    )

# =====================================================
# PREP
# =====================================================
def norm_bool(x):
    if isinstance(x, str):
        return x.strip().lower() == "sim"
    return bool(x)

df["mudou_cargo"] = df["mudou_cargo_desde_exoneracao"].apply(norm_bool)
df["mudou_orgao"] = df["mudou_orgao_desde_exoneracao"].apply(norm_bool)


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


df["tempo_cluster"] = df["dias_desde_exoneracao"].apply(classificar_tempo)


def classificar_estado(row):
    tempo = row["tempo_cluster"]
    cargo = "novo_cargo" if row["mudou_cargo"] else "mesmo_cargo"
    orgao = "novo_orgao" if row["mudou_orgao"] else "mesmo_orgao"
    return f"N_{tempo}_{cargo}_{orgao}"


df["estado_N"] = df.apply(classificar_estado, axis=1)


def prepare_loaded_frames(loaded_df, loaded_df_mov):
    loaded_df["pessoa"] = loaded_df["nome_normalizado"]
    loaded_df["data_nomeacao"] = pd.to_datetime(loaded_df["data_publicacao"], errors="coerce")
    loaded_df["data_exoneracao"] = pd.to_datetime(loaded_df["data_exoneracao_anterior"], errors="coerce")
    loaded_df["ano"] = loaded_df["data_nomeacao"].dt.year

    loaded_df_mov["pessoa"] = loaded_df_mov["nome_normalizado"]
    loaded_df_mov["data_movimentacao"] = pd.to_datetime(loaded_df_mov["data_publicacao"], errors="coerce")
    loaded_df_mov["ano"] = loaded_df_mov["data_movimentacao"].dt.year

    loaded_df["autoridade_assinante"] = (
        loaded_df["cargo_assinante"].fillna("").astype(str).str.strip().replace("", "Sem identificacao")
    )
    loaded_df_mov["autoridade_assinante"] = (
        loaded_df_mov["cargo_assinante"].fillna("").astype(str).str.strip().replace("", "Sem identificacao")
    )
    loaded_df["autoria_ato"] = classificar_autoria_ato(loaded_df)
    loaded_df_mov["autoria_ato"] = classificar_autoria_ato(loaded_df_mov)
    if "governador_edicao" not in loaded_df.columns:
        loaded_df["governador_edicao"] = "Nao identificado"
    if "governador_edicao" not in loaded_df_mov.columns:
        loaded_df_mov["governador_edicao"] = "Nao identificado"
    loaded_df["governador_edicao"] = (
        loaded_df["governador_edicao"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
    )
    loaded_df_mov["governador_edicao"] = (
        loaded_df_mov["governador_edicao"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
    )
    loaded_df["representante_governo"] = loaded_df["governador_edicao"].map(nome_representante_governo)
    loaded_df_mov["representante_governo"] = loaded_df_mov["governador_edicao"].map(nome_representante_governo)
    loaded_df["origem_representante"] = loaded_df["governador_edicao"].map(origem_representante_governo)
    loaded_df_mov["origem_representante"] = loaded_df_mov["governador_edicao"].map(origem_representante_governo)
    for frame in [loaded_df, loaded_df_mov]:
        frame["representante_governo"] = (
            frame["representante_governo"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
        )
        frame["origem_representante"] = (
            frame["origem_representante"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
        )
        frame["representante_origem"] = frame.apply(
            lambda row: f"{row['representante_governo']} ({row['origem_representante']})",
            axis=1,
        )
    loaded_df["mudou_cargo"] = loaded_df["mudou_cargo_desde_exoneracao"].apply(norm_bool)
    loaded_df["mudou_orgao"] = loaded_df["mudou_orgao_desde_exoneracao"].apply(norm_bool)
    loaded_df["tempo_cluster"] = loaded_df["dias_desde_exoneracao"].apply(classificar_tempo)
    loaded_df["estado_N"] = loaded_df.apply(classificar_estado, axis=1)
    return loaded_df, loaded_df_mov


def reload_analysis_base():
    return prepare_loaded_frames(*read_state_csvs(ANALISES_DIR))

