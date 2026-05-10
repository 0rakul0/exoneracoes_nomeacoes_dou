# app.py
import re
from datetime import date

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import networkx as nx

from functools import lru_cache
from pathlib import Path

from dash import Dash, dcc, html, Input, Output, ctx

# =====================================================
# CONFIG
# =====================================================
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALISES_DIR = PROJECT_ROOT / "saida" / "analises"
TOP_N_TRANSICOES = 30
TOP_N_ORGAOS = 20


@lru_cache(maxsize=4096)
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

    return governador_por_data_do_arquivo(path)


def governador_por_data_do_arquivo(path):
    match = re.search(r"(20\d{2})-(\d{2})-(\d{2})", path.name)
    if not match:
        return "Não identificado"

    publication_date = date(
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
    )

    if publication_date < date(2020, 8, 28):
        return "Wilson José Witzel - Governador"
    if publication_date < date(2021, 5, 1):
        return "Cláudio Bomfim de Castro e Silva - Governador em exercício"
    return "Cláudio Bomfim de Castro e Silva - Governador"


def extract_governor_name_near_acting_phrase(text):
    known_names = [
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
    for match in phrase_re.finditer(text):
        window = text[max(0, match.start() - 120): min(len(text), match.end() + 120)]
        for needle, label in known_names:
            if needle in window:
                return label

    vice_governor = extract_named_role(text, "VICE-GOVERNADOR")
    if vice_governor:
        return vice_governor

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
        ("WILSON JOS", "Wilson José Witzel"),
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
        "Thiago Pampolha": "Vice-governadoria",
        "Rodrigo Bacellar": "ALERJ",
        "Ricardo Couto de Castro": "TJ-RJ",
    }
    if nome == "Nao identificado":
        return "Nao identificado"
    return origem_por_nome.get(nome, "Executivo estadual")


# =====================================================
# LOAD
# =====================================================
def read_state_csvs(analyses_dir):
    retorno_frames = []
    movimentacao_frames = []
    for state_dir in sorted(path for path in analyses_dir.iterdir() if path.is_dir()):
        state = state_dir.name.upper()
        retornos_path = state_dir / "retornos_apos_exoneracao.csv"
        movimentacoes_path = state_dir / "movimentacoes_pessoas.csv"
        if not retornos_path.exists() or not movimentacoes_path.exists():
            continue

        retorno_frame = pd.read_csv(retornos_path)
        movimentacao_frame = pd.read_csv(movimentacoes_path)
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
if "governador_edicao" not in df.columns:
    df["governador_edicao"] = "Nao identificado"
if "governador_edicao" not in df_mov.columns:
    df_mov["governador_edicao"] = "Nao identificado"
df["governador_edicao"] = df["governador_edicao"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
df_mov["governador_edicao"] = df_mov["governador_edicao"].fillna("").astype(str).str.strip().replace("", "Nao identificado")
if "representante_governo" not in df.columns:
    df["representante_governo"] = df["governador_edicao"].map(nome_representante_governo)
if "representante_governo" not in df_mov.columns:
    df_mov["representante_governo"] = df_mov["governador_edicao"].map(nome_representante_governo)
if "origem_representante" not in df.columns:
    df["origem_representante"] = df["governador_edicao"].map(origem_representante_governo)
if "origem_representante" not in df_mov.columns:
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
    if "representante_governo" not in loaded_df.columns:
        loaded_df["representante_governo"] = loaded_df["governador_edicao"].map(nome_representante_governo)
    if "representante_governo" not in loaded_df_mov.columns:
        loaded_df_mov["representante_governo"] = loaded_df_mov["governador_edicao"].map(nome_representante_governo)
    if "origem_representante" not in loaded_df.columns:
        loaded_df["origem_representante"] = loaded_df["governador_edicao"].map(origem_representante_governo)
    if "origem_representante" not in loaded_df_mov.columns:
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

# =====================================================
# CORE
# =====================================================
def construir_eventos(dff):
    eventos = []

    for _, row in dff.iterrows():
        pessoa = row["pessoa"]

        if pd.notna(row["data_exoneracao"]):
            eventos.append({
                "pessoa": pessoa,
                "data": row["data_exoneracao"],
                "estado": "E"
            })

        if pd.notna(row["data_nomeacao"]):
            eventos.append({
                "pessoa": pessoa,
                "data": row["data_nomeacao"],
                "estado": row["estado_N"]
            })

    ev = pd.DataFrame(eventos)

    if ev.empty:
        return ev, pd.DataFrame(columns=["estado", "prox_estado", "count"])

    ev["data"] = pd.to_datetime(ev["data"], errors="coerce")
    ev = ev.dropna(subset=["data"])
    ev = ev.sort_values(["pessoa", "data"])

    ev["prox_estado"] = ev.groupby("pessoa")["estado"].shift(-1)

    trans = (
        ev.dropna(subset=["prox_estado"])
        .groupby(["estado", "prox_estado"])
        .size()
        .reset_index(name="count")
    )

    return ev, trans


def matriz_transicao(trans):
    if trans.empty:
        return pd.DataFrame(), pd.DataFrame()

    estados = sorted(set(trans["estado"]).union(set(trans["prox_estado"])))

    matriz = (
        trans.pivot(index="estado", columns="prox_estado", values="count")
        .reindex(index=estados, columns=estados, fill_value=0)
    )

    row_sums = matriz.sum(axis=1)
    matriz_prob = matriz.div(row_sums.replace(0, 1), axis=0)

    return matriz, matriz_prob


def estado_estacionario(mat_prob):
    if mat_prob.empty:
        return {}

    P = mat_prob.values.copy()

    if P.shape[0] == 0 or P.shape[0] != P.shape[1]:
        return {}

    row_sums = P.sum(axis=1)
    for i, s in enumerate(row_sums):
        if s == 0:
            P[i, i] = 1.0

    try:
        eigvals, eigvecs = np.linalg.eig(P.T)
        vec = eigvecs[:, np.isclose(eigvals, 1)]

        if vec.size == 0:
            return {}

        vec = vec.real[:, 0]
        vec = vec / vec.sum()

        return dict(zip(mat_prob.index.tolist(), vec))

    except Exception:
        return {}


# =====================================================
# FIGURES
# =====================================================
def fig_sankey(trans):
    if trans.empty:
        return go.Figure().update_layout(title="Sem dados para Sankey")

    trans = trans.sort_values("count", ascending=False).head(TOP_N_TRANSICOES)

    labels = sorted(set(trans["estado"]).union(set(trans["prox_estado"])))
    idx = {label: i for i, label in enumerate(labels)}

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=18,
            thickness=18,
            line=dict(color="black", width=0.4),
            label=labels
        ),
        link=dict(
            source=trans["estado"].map(idx),
            target=trans["prox_estado"].map(idx),
            value=trans["count"],
            customdata=trans[["estado", "prox_estado", "count"]],
            hovertemplate=(
                "De: %{customdata[0]}<br>"
                "Para: %{customdata[1]}<br>"
                "Volume: %{customdata[2]}<extra></extra>"
            )
        )
    )])

    fig.update_layout(
        title="Sankey de Transições",
        height=520,
        font_size=11
    )

    return fig


def fig_barras_movimentacoes(dff_mov):
    if dff_mov.empty:
        return go.Figure().update_layout(title="Sem dados para quantitativos")

    base = (
        dff_mov.dropna(subset=["ano"])
        .assign(ano=lambda data: data["ano"].astype(int))
        .groupby(["ano", "tipo_ato"])
        .size()
        .reset_index(name="quantidade")
    )

    fig = px.bar(
        base,
        x="ano",
        y="quantidade",
        color="tipo_ato",
        barmode="group",
        text="quantidade",
        category_orders={"tipo_ato": ["exoneracao", "nomeacao"]},
        labels={
            "ano": "Ano",
            "quantidade": "Quantidade",
            "tipo_ato": "Tipo de ato",
        },
        title="Quantitativo de Exonerações e Nomeações por Ano",
    )

    fig.update_traces(texttemplate="%{text:,}", textposition="outside")
    fig.update_layout(
        height=520,
        uniformtext_minsize=10,
        uniformtext_mode="hide",
        yaxis_title="Quantidade de atos",
        xaxis=dict(dtick=1),
    )

    return fig


def fig_barras_movimentacoes_por_orgao(dff_mov):
    if dff_mov.empty:
        return go.Figure().update_layout(title="Sem dados para órgãos")

    base = dff_mov.copy()
    base["orgao_grafico"] = base["orgao"].fillna("").astype(str).str.strip()
    base = base[base["orgao_grafico"] != ""]

    if base.empty:
        return go.Figure().update_layout(title="Sem órgãos identificados para os filtros selecionados")

    ranking = (
        base.groupby("orgao_grafico")
        .size()
        .sort_values(ascending=False)
        .head(TOP_N_ORGAOS)
        .index
    )
    base = base[base["orgao_grafico"].isin(ranking)]

    barras = (
        base.groupby(["orgao_grafico", "tipo_ato"])
        .size()
        .reset_index(name="quantidade")
    )
    barras["fluxo"] = barras.apply(
        lambda row: -row["quantidade"] if row["tipo_ato"] == "exoneracao" else row["quantidade"],
        axis=1,
    )
    barras["rotulo"] = barras["quantidade"].map(lambda value: f"{value:,}".replace(",", "."))

    ordem_orgaos = (
        barras.assign(abs_fluxo=barras["fluxo"].abs())
        .groupby("orgao_grafico")["abs_fluxo"]
        .sum()
        .sort_values()
        .index
        .tolist()
    )

    fig = px.bar(
        barras,
        x="fluxo",
        y="orgao_grafico",
        color="tipo_ato",
        orientation="h",
        text="rotulo",
        category_orders={
            "tipo_ato": ["exoneracao", "nomeacao"],
            "orgao_grafico": ordem_orgaos,
        },
        labels={
            "fluxo": "Saídas / Entradas",
            "orgao_grafico": "Órgão",
            "tipo_ato": "Tipo de ato",
        },
        title=f"Entradas e Saídas por Órgão - Top {TOP_N_ORGAOS} órgãos identificados",
    )

    fig.add_vline(x=0, line_width=1, line_color="#444")
    fig.update_layout(
        height=760,
        xaxis=dict(
            title="Exonerações à esquerda, nomeações à direita",
            tickformat=",d",
        ),
        yaxis_title="",
        legend_title_text="Tipo de ato",
    )

    return fig


def fig_sankey_animado_por_ano(dff):
    anos = sorted(dff["ano"].dropna().unique())

    if len(anos) == 0:
        return go.Figure().update_layout(title="Sem dados para Sankey animado")

    trans_por_ano = {}

    labels_global = set()

    for ano in anos:
        _, trans = construir_eventos(dff[dff["ano"] == ano])
        trans = trans.sort_values("count", ascending=False).head(TOP_N_TRANSICOES)
        trans_por_ano[ano] = trans

        labels_global.update(trans["estado"].tolist())
        labels_global.update(trans["prox_estado"].tolist())

    labels = sorted(labels_global)
    idx = {label: i for i, label in enumerate(labels)}

    def sankey_data(ano):
        trans = trans_por_ano[ano]

        return go.Sankey(
            node=dict(
                pad=18,
                thickness=18,
                line=dict(color="black", width=0.4),
                label=labels
            ),
            link=dict(
                source=trans["estado"].map(idx),
                target=trans["prox_estado"].map(idx),
                value=trans["count"],
                customdata=trans[["estado", "prox_estado", "count"]],
                hovertemplate=(
                    "Ano: " + str(int(ano)) + "<br>"
                    "De: %{customdata[0]}<br>"
                    "Para: %{customdata[1]}<br>"
                    "Volume: %{customdata[2]}<extra></extra>"
                )
            )
        )

    fig = go.Figure(data=[sankey_data(anos[0])])

    frames = [
        go.Frame(
            data=[sankey_data(ano)],
            name=str(int(ano))
        )
        for ano in anos
    ]

    fig.frames = frames

    fig.update_layout(
        title=f"Sankey Animado por Ano — {int(anos[0])}",
        height=560,
        font_size=11,
        updatemenus=[{
            "type": "buttons",
            "showactive": False,
            "buttons": [
                {
                    "label": "▶ Play",
                    "method": "animate",
                    "args": [None, {
                        "frame": {"duration": 900, "redraw": True},
                        "fromcurrent": True
                    }]
                },
                {
                    "label": "⏸ Pause",
                    "method": "animate",
                    "args": [[None], {
                        "frame": {"duration": 0, "redraw": False},
                        "mode": "immediate"
                    }]
                }
            ]
        }],
        sliders=[{
            "active": 0,
            "steps": [
                {
                    "label": str(int(ano)),
                    "method": "animate",
                    "args": [[str(int(ano))], {
                        "frame": {"duration": 500, "redraw": True},
                        "mode": "immediate"
                    }]
                }
                for ano in anos
            ]
        }]
    )

    return fig


def fig_timeline_eventos(dff):
    if dff.empty:
        return go.Figure().update_layout(title="Sem dados para timeline")

    timeline = (
        dff.groupby(["ano", "tempo_cluster"])
        .size()
        .reset_index(name="eventos")
        .sort_values("ano")
    )

    fig = px.line(
        timeline,
        x="ano",
        y="eventos",
        color="tempo_cluster",
        markers=True,
        title="Timeline de Retornos por Ano e Tipo de Tempo"
    )

    fig.update_layout(height=420)

    return fig


def fig_timeline_movimentacoes(dff_mov):
    if dff_mov.empty:
        return go.Figure().update_layout(title="Sem dados para timeline de movimentações")

    base = dff_mov.dropna(subset=["data_movimentacao"]).copy()
    if base.empty:
        return go.Figure().update_layout(title="Sem datas válidas para timeline de movimentações")

    base["mes"] = base["data_movimentacao"].dt.to_period("M").dt.to_timestamp()
    timeline = (
        base.groupby(["mes", "tipo_ato"])
        .size()
        .reset_index(name="quantidade")
        .sort_values("mes")
    )

    fig = px.bar(
        timeline,
        x="mes",
        y="quantidade",
        color="tipo_ato",
        barmode="group",
        text="quantidade",
        category_orders={"tipo_ato": ["exoneracao", "nomeacao"]},
        labels={
            "mes": "Mês",
            "quantidade": "Quantidade",
            "tipo_ato": "Tipo de ato",
        },
        title="Timeline de Exonerações e Nomeações",
    )

    fig.update_traces(texttemplate="%{text:,}", textposition="outside")
    fig.update_layout(
        height=460,
        uniformtext_minsize=9,
        uniformtext_mode="hide",
        yaxis_title="Quantidade de atos",
    )

    return fig


def fig_serie_temporal_governo(dff_mov):
    if dff_mov.empty:
        return go.Figure().update_layout(title="Sem dados para serie temporal")

    base = dff_mov.dropna(subset=["data_movimentacao"]).copy()
    if base.empty:
        return go.Figure().update_layout(title="Sem datas validas para serie temporal")

    base["periodo"] = base["data_movimentacao"].dt.to_period("M").dt.to_timestamp()
    serie = (
        base.groupby(["periodo", "representante_governo", "tipo_ato"])
        .agg(
            quantidade=("tipo_ato", "size"),
            papeis=("governador_edicao", papeis_governo),
            origem=("origem_representante", origem_representante_agregada),
        )
        .reset_index()
        .sort_values(["representante_governo", "tipo_ato", "periodo"])
    )
    if serie.empty:
        return go.Figure().update_layout(title="Sem dados para serie temporal")

    governos = (
        serie.groupby("representante_governo")["quantidade"]
        .sum()
        .sort_values(ascending=False)
        .index
        .tolist()
    )
    palette = px.colors.qualitative.Dark24 + px.colors.qualitative.Set2 + px.colors.qualitative.Plotly
    color_by_government = {
        governo: palette[index % len(palette)]
        for index, governo in enumerate(governos)
    }
    origin_by_government = serie.groupby("representante_governo")["origem"].first().to_dict()

    fig = go.Figure()
    action_config = {
        "nomeacao": {"label": "Nomeacoes", "sign": 1, "dash": "solid"},
        "exoneracao": {"label": "Exoneracoes", "sign": -1, "dash": "dot"},
    }

    for governo in governos:
        origem = origin_by_government.get(governo, origem_representante_governo(governo))
        short_government = f"{rotulo_representante_curto(governo)} ({origem})"
        for action_type in ["nomeacao", "exoneracao"]:
            current = serie[
                (serie["representante_governo"] == governo)
                & (serie["tipo_ato"] == action_type)
            ]
            if current.empty:
                continue

            config = action_config[action_type]
            signed_quantity = current["quantidade"] * config["sign"]
            fig.add_trace(
                go.Scatter(
                    x=current["periodo"],
                    y=signed_quantity,
                    mode="lines+markers",
                    name=f"{short_government} - {config['label']}",
                    legendgroup=governo,
                    line=dict(
                        color=color_by_government[governo],
                        width=2.5,
                        dash=config["dash"],
                    ),
                    marker=dict(size=6, color=color_by_government[governo]),
                    customdata=current[["representante_governo", "origem", "papeis", "tipo_ato", "quantidade"]],
                    hovertemplate=(
                        "Periodo: %{x|%Y-%m}<br>"
                        "Representante: %{customdata[0]}<br>"
                        "Origem: %{customdata[1]}<br>"
                        "Papel na edicao: %{customdata[2]}<br>"
                        "Movimentacao: %{customdata[3]}<br>"
                        "Quantidade: %{customdata[4]:,}<extra></extra>"
                    ),
                )
            )

    max_quantity = int(serie["quantidade"].max())
    upper_tick = max(1, max_quantity)
    tick_step = max(1, int(np.ceil(upper_tick / 4)))
    positive_ticks = list(range(0, upper_tick + tick_step, tick_step))
    tickvals = sorted({-value for value in positive_ticks if value} | set(positive_ticks))

    fig.add_hline(
        y=0,
        line_width=2,
        line_color="#222",
        annotation_text="tempo",
        annotation_position="bottom right",
    )
    fig.update_layout(
        title="Serie Temporal por Representante - Nomeacoes Acima e Exoneracoes Abaixo",
        height=700,
        hovermode="closest",
        legend_title_text="Representante, origem e movimentacao",
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            groupclick="toggleitem",
        ),
        margin=dict(l=24, r=300, t=70, b=70),
        xaxis=dict(
            title="Tempo",
            rangeslider=dict(visible=True, thickness=0.08),
            rangeselector=dict(
                buttons=[
                    dict(count=6, label="6m", step="month", stepmode="backward"),
                    dict(count=1, label="1a", step="year", stepmode="backward"),
                    dict(count=3, label="3a", step="year", stepmode="backward"),
                    dict(step="all", label="Tudo"),
                ]
            ),
        ),
        yaxis=dict(
            title="Quantidade de atos",
            tickvals=tickvals,
            ticktext=[f"{abs(value):,}".replace(",", ".") for value in tickvals],
            zeroline=False,
        ),
    )
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0,
        y=1.03,
        text="Nomeacoes",
        showarrow=False,
        font=dict(size=12, color="#333"),
    )
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0,
        y=-0.08,
        text="Exoneracoes",
        showarrow=False,
        font=dict(size=12, color="#333"),
    )
    return fig


def nome_representante_governo(governo: str) -> str:
    governo = str(governo or "Nao identificado").strip()
    if " - " not in governo:
        return governo
    return governo.split(" - ", 1)[0].strip() or "Nao identificado"


def origem_representante_governo(governo: str) -> str:
    nome = nome_representante_governo(governo)
    origem_por_nome = {
        "Thiago Pampolha": "Vice-governadoria",
        "Rodrigo Bacellar": "ALERJ",
        "Ricardo Couto de Castro": "TJ-RJ",
    }
    return origem_por_nome.get(nome, "Executivo estadual")


def origem_representante_agregada(values) -> str:
    origens = []
    for value in values.dropna().astype(str):
        if value and value not in origens:
            origens.append(value)
    return " / ".join(origens) if origens else "Nao identificado"


def papeis_governo(values) -> str:
    papeis = []
    for value in values.dropna().astype(str):
        if " - " in value:
            papel = value.split(" - ", 1)[1].strip()
        else:
            papel = value.strip()
        if papel and papel not in papeis:
            papeis.append(papel)
    return " / ".join(papeis) if papeis else "Nao identificado"


def rotulo_representante_curto(governo: str) -> str:
    nome = nome_representante_governo(governo)
    partes = nome.split()
    if len(partes) >= 2:
        return f"{partes[0]} {partes[-1]}"
    return nome


def rotulo_governo_curto(governo: str) -> str:
    governo = str(governo or "Nao identificado").strip()
    if " - " not in governo:
        return governo
    nome, cargo = governo.split(" - ", 1)
    partes = nome.split()
    if len(partes) >= 2:
        nome = f"{partes[0]} {partes[-1]}"
    return f"{nome} - {cargo}"


def fig_fluxo_por_governo(dff_mov):
    if dff_mov.empty:
        return go.Figure().update_layout(title="Sem dados para governos")

    base = (
        dff_mov.groupby(["representante_origem", "tipo_ato"])
        .size()
        .reset_index(name="quantidade")
    )
    base["fluxo"] = base.apply(
        lambda row: -row["quantidade"] if row["tipo_ato"] == "exoneracao" else row["quantidade"],
        axis=1,
    )
    base["rotulo"] = base["quantidade"].map(lambda value: f"{value:,}".replace(",", "."))
    ordem = (
        base.assign(abs_fluxo=base["fluxo"].abs())
        .groupby("representante_origem")["abs_fluxo"]
        .sum()
        .sort_values()
        .index
        .tolist()
    )

    fig = px.bar(
        base,
        x="fluxo",
        y="representante_origem",
        color="tipo_ato",
        orientation="h",
        text="rotulo",
        category_orders={
            "tipo_ato": ["exoneracao", "nomeacao"],
            "representante_origem": ordem,
        },
        labels={
            "fluxo": "Saídas / Entradas",
            "representante_origem": "Representante",
            "tipo_ato": "Movimentação",
        },
        title="Entradas e Saídas por Representante",
    )
    fig.add_vline(x=0, line_width=1, line_color="#444")
    fig.update_layout(
        height=max(460, 48 * max(1, len(ordem)) + 160),
        xaxis_title="Exonerações à esquerda, nomeações à direita",
        yaxis_title="",
        legend_title_text="Movimentação",
        margin=dict(l=24, r=24, t=70, b=50),
    )
    return fig


def fig_saldo_por_governo(dff_mov):
    if dff_mov.empty:
        return go.Figure().update_layout(title="Sem dados para saldo")

    base = (
        dff_mov.groupby(["representante_origem", "tipo_ato"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    for col in ["exoneracao", "nomeacao"]:
        if col not in base.columns:
            base[col] = 0
    base["saldo"] = base["nomeacao"] - base["exoneracao"]
    base = base.sort_values("saldo")
    base["cor"] = base["saldo"].apply(lambda value: "Mais entradas" if value >= 0 else "Mais saídas")

    fig = px.bar(
        base,
        x="saldo",
        y="representante_origem",
        color="cor",
        orientation="h",
        text=base["saldo"].map(lambda value: f"{value:,}".replace(",", ".")),
        labels={"saldo": "Nomeações menos exonerações", "representante_origem": "Representante", "cor": ""},
        title="Saldo Líquido por Representante",
        color_discrete_map={"Mais entradas": "#287c5a", "Mais saídas": "#b4423c"},
    )
    fig.add_vline(x=0, line_width=1, line_color="#444")
    fig.update_layout(
        height=max(420, 44 * max(1, len(base)) + 150),
        yaxis_title="",
        showlegend=True,
        margin=dict(l=24, r=24, t=70, b=50),
    )
    return fig


def fig_timeline_governo(dff_mov):
    if dff_mov.empty:
        return go.Figure().update_layout(title="Sem dados para timeline")

    base = dff_mov.dropna(subset=["data_movimentacao"]).copy()
    if base.empty:
        return go.Figure().update_layout(title="Sem datas válidas para timeline")

    selected_governments = base["representante_origem"].nunique()
    if selected_governments <= 3:
        base["periodo"] = base["data_movimentacao"].dt.to_period("M").dt.to_timestamp()
        x_label = "Mês"
    else:
        base["periodo"] = base["data_movimentacao"].dt.year.astype(int)
        x_label = "Ano"

    timeline = (
        base.groupby(["periodo", "representante_origem", "tipo_ato"])
        .size()
        .reset_index(name="quantidade")
        .sort_values("periodo")
    )

    fig = px.bar(
        timeline,
        x="periodo",
        y="quantidade",
        color="tipo_ato",
        facet_row="representante_origem" if selected_governments <= 3 else None,
        barmode="group",
        labels={
            "periodo": x_label,
            "quantidade": "Quantidade",
            "tipo_ato": "Movimentação",
            "representante_origem": "Representante",
        },
        title="Timeline de Movimentações por Representante",
        category_orders={"tipo_ato": ["exoneracao", "nomeacao"]},
    )
    fig.update_layout(
        height=520 if selected_governments > 3 else max(420, selected_governments * 280),
        legend_title_text="Movimentação",
        margin=dict(l=24, r=24, t=70, b=50),
    )
    fig.for_each_annotation(lambda annotation: annotation.update(text=annotation.text.split("=")[-1]))
    return fig


def fig_orgaos_por_governo(dff_mov):
    if dff_mov.empty:
        return go.Figure().update_layout(title="Sem dados para órgãos")

    base = dff_mov.copy()
    base["orgao_grafico"] = base["orgao"].fillna("").astype(str).str.strip()
    base = base[base["orgao_grafico"] != ""]
    if base.empty:
        return go.Figure().update_layout(title="Sem órgãos identificados para os filtros selecionados")

    ranking = (
        base.groupby("orgao_grafico")
        .size()
        .sort_values(ascending=False)
        .head(TOP_N_ORGAOS)
        .index
    )
    base = base[base["orgao_grafico"].isin(ranking)]
    barras = base.groupby(["orgao_grafico", "tipo_ato"]).size().reset_index(name="quantidade")
    barras["fluxo"] = barras.apply(
        lambda row: -row["quantidade"] if row["tipo_ato"] == "exoneracao" else row["quantidade"],
        axis=1,
    )
    ordem = (
        barras.assign(abs_fluxo=barras["fluxo"].abs())
        .groupby("orgao_grafico")["abs_fluxo"]
        .sum()
        .sort_values()
        .index
        .tolist()
    )

    fig = px.bar(
        barras,
        x="fluxo",
        y="orgao_grafico",
        color="tipo_ato",
        orientation="h",
        category_orders={"tipo_ato": ["exoneracao", "nomeacao"], "orgao_grafico": ordem},
        labels={"fluxo": "Saídas / Entradas", "orgao_grafico": "Órgão", "tipo_ato": "Movimentação"},
        title=f"Órgãos Mais Movimentados - Top {TOP_N_ORGAOS}",
    )
    fig.add_vline(x=0, line_width=1, line_color="#444")
    fig.update_layout(
        height=780,
        xaxis_title="Exonerações à esquerda, nomeações à direita",
        yaxis_title="",
        legend_title_text="Movimentação",
        margin=dict(l=24, r=24, t=70, b=50),
    )
    return fig


def tabela_resumo_governos(dff_mov):
    if dff_mov.empty:
        return html.Div("Sem dados para os filtros selecionados.")

    base = (
        dff_mov.groupby(["representante_origem", "tipo_ato"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    for col in ["exoneracao", "nomeacao"]:
        if col not in base.columns:
            base[col] = 0
    base["saldo"] = base["nomeacao"] - base["exoneracao"]
    base["atos"] = base["nomeacao"] + base["exoneracao"]
    base = base.sort_values("atos", ascending=False)

    header = html.Tr([
        html.Th("Representante"),
        html.Th("Exonerações"),
        html.Th("Nomeações"),
        html.Th("Saldo"),
        html.Th("Atos"),
    ])
    rows = [
        html.Tr([
            html.Td(row["representante_origem"]),
            html.Td(f"{int(row['exoneracao']):,}".replace(",", ".")),
            html.Td(f"{int(row['nomeacao']):,}".replace(",", ".")),
            html.Td(f"{int(row['saldo']):,}".replace(",", ".")),
            html.Td(f"{int(row['atos']):,}".replace(",", ".")),
        ])
        for _, row in base.iterrows()
    ]
    return html.Table(
        [html.Thead(header), html.Tbody(rows)],
        style={
            "width": "100%",
            "borderCollapse": "collapse",
            "backgroundColor": "white",
        },
    )


def fig_timeline_mobilidade(dff):
    if dff.empty:
        return go.Figure().update_layout(title="Sem dados para mobilidade")

    base = (
        dff.groupby("ano")
        .agg(
            total=("pessoa", "count"),
            mudou_cargo=("mudou_cargo", "sum"),
            mudou_orgao=("mudou_orgao", "sum")
        )
        .reset_index()
    )

    base["tx_mudou_cargo"] = base["mudou_cargo"] / base["total"]
    base["tx_mudou_orgao"] = base["mudou_orgao"] / base["total"]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=base["ano"],
        y=base["tx_mudou_cargo"],
        mode="lines+markers",
        name="Taxa mudança de cargo"
    ))

    fig.add_trace(go.Scatter(
        x=base["ano"],
        y=base["tx_mudou_orgao"],
        mode="lines+markers",
        name="Taxa mudança de órgão"
    ))

    fig.update_layout(
        title="Timeline de Mobilidade",
        yaxis_tickformat=".0%",
        height=420
    )

    return fig


def fig_heatmap(mat_prob):
    if mat_prob.empty:
        return go.Figure().update_layout(title="Sem dados para matriz")

    fig = px.imshow(
        mat_prob,
        text_auto=".2f",
        aspect="auto",
        title="Matriz de Transição"
    )

    fig.update_layout(height=520)

    return fig


def fig_network_3d(trans):
    if trans.empty:
        return go.Figure().update_layout(title="Sem dados para rede 3D")

    trans = trans.sort_values("count", ascending=False).head(TOP_N_TRANSICOES)

    G = nx.DiGraph()

    for _, row in trans.iterrows():
        G.add_edge(row["estado"], row["prox_estado"], weight=row["count"])

    pos = nx.spring_layout(G, dim=3, k=0.75, seed=42)

    edge_x, edge_y, edge_z = [], [], []

    for u, v in G.edges():
        x0, y0, z0 = pos[u]
        x1, y1, z1 = pos[v]

        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]
        edge_z += [z0, z1, None]

    edge_trace = go.Scatter3d(
        x=edge_x,
        y=edge_y,
        z=edge_z,
        mode="lines",
        line=dict(width=2),
        hoverinfo="none"
    )

    node_x, node_y, node_z, node_text, node_size = [], [], [], [], []

    for node in G.nodes():
        x, y, z = pos[node]
        grau = G.degree(node)

        node_x.append(x)
        node_y.append(y)
        node_z.append(z)
        node_text.append(f"{node}<br>Grau: {grau}")
        node_size.append(8 + grau * 4)

    node_trace = go.Scatter3d(
        x=node_x,
        y=node_y,
        z=node_z,
        mode="markers+text",
        text=[n.split("<br>")[0] for n in node_text],
        hovertext=node_text,
        hoverinfo="text",
        textposition="top center",
        marker=dict(
            size=node_size,
            opacity=0.85,
            color=node_size,
            colorscale="Viridis"
        )
    )

    fig = go.Figure(data=[edge_trace, node_trace])

    fig.update_layout(
        title="Rede de Transições 3D",
        height=620,
        showlegend=False,
        margin=dict(l=0, r=0, b=0, t=40),
        scene=dict(
            xaxis=dict(showbackground=False, showticklabels=False, title=""),
            yaxis=dict(showbackground=False, showticklabels=False, title=""),
            zaxis=dict(showbackground=False, showticklabels=False, title="")
        )
    )

    return fig


def gerar_resumo(dff, trans, mat_prob):
    if dff.empty:
        return "Sem dados para os filtros selecionados."

    total = len(dff)
    pessoas = dff["pessoa"].nunique()
    media_dias = dff["dias_desde_exoneracao"].mean()
    mediana_dias = dff["dias_desde_exoneracao"].median()
    tx_cargo = dff["mudou_cargo"].mean()
    tx_orgao = dff["mudou_orgao"].mean()

    steady = estado_estacionario(mat_prob)

    linhas = [
        "RESUMO ANALÍTICO",
        "",
        f"Registros filtrados: {total:,}".replace(",", "."),
        f"Pessoas únicas: {pessoas:,}".replace(",", "."),
        f"Tempo médio de retorno: {media_dias:.2f} dias",
        f"Mediana do retorno: {mediana_dias:.2f} dias",
        f"Taxa de mudança de cargo: {tx_cargo:.2%}",
        f"Taxa de mudança de órgão: {tx_orgao:.2%}",
        "",
        "Top transições:"
    ]

    top = trans.sort_values("count", ascending=False).head(10)

    for _, row in top.iterrows():
        linhas.append(f"{row['estado']} → {row['prox_estado']}: {row['count']}")

    linhas.append("")
    linhas.append("Estado estacionário:")

    if steady:
        for k, v in sorted(steady.items(), key=lambda x: x[1], reverse=True):
            linhas.append(f"{k}: {v:.4f}")
    else:
        linhas.append("Não calculável para o filtro atual.")

    return "\n".join(linhas)


# =====================================================
# APP
# =====================================================
app = Dash(__name__)
app.title = "DOU RJ - Transições Markov"

estados = sorted(df_mov["estado"].dropna().astype(str).unique().tolist())
anos = sorted(
    set(df["ano"].dropna().astype(int).unique().tolist()).union(
        set(df_mov["ano"].dropna().astype(int).unique().tolist())
    )
)
orgaos = sorted(
    set(df["orgao"].dropna().astype(str).unique().tolist()).union(
        set(df_mov["orgao"].dropna().astype(str).unique().tolist())
    )
)
tempos = sorted(df["tempo_cluster"].dropna().unique().tolist())
autoridades_assinantes = sorted(
    set(df["autoridade_assinante"].dropna().astype(str).unique().tolist()).union(
        set(df_mov["autoridade_assinante"].dropna().astype(str).unique().tolist())
    )
)
governadores_edicao = sorted(
    set(df["representante_origem"].dropna().astype(str).unique().tolist()).union(
        set(df_mov["representante_origem"].dropna().astype(str).unique().tolist())
    )
)

app.layout = html.Div(
    style={
        "fontFamily": "Arial",
        "padding": "20px",
        "backgroundColor": "#f7f7f7"
    },
    children=[
        html.H2("Movimentacoes por Governo - Exoneracoes e Nomeacoes por Estado"),

        dcc.Tabs(
            id="filtro_estado",
            value=estados[0] if estados else None,
            children=[dcc.Tab(label=estado, value=estado) for estado in estados],
            style={"marginBottom": "16px"},
        ),

        html.Div(
            style={"display": "flex", "alignItems": "center", "gap": "12px", "marginBottom": "16px"},
            children=[
                html.Button(
                    "Recarregar base",
                    id="recarregar_base",
                    n_clicks=0,
                    style={
                        "backgroundColor": "#1f5eff",
                        "border": "0",
                        "color": "white",
                        "cursor": "pointer",
                        "fontWeight": "bold",
                        "padding": "10px 14px",
                    },
                ),
                html.Div(id="recarregar_status", style={"color": "#555", "fontSize": "13px"}),
            ],
        ),

        html.Div(
            style={
                "display": "grid",
                "gridTemplateColumns": "1fr 1.8fr 1.6fr 1fr",
                "gap": "12px",
                "marginBottom": "20px"
            },
            children=[
                html.Div([
                    html.Label("Ano"),
                    dcc.Dropdown(
                        id="filtro_ano",
                        options=[{"label": str(a), "value": a} for a in anos],
                        multi=True,
                        placeholder="Todos"
                    )
                ]),

                html.Div([
                    html.Label("Representante"),
                    dcc.Dropdown(
                        id="filtro_governador_edicao",
                        options=[{"label": a, "value": a} for a in governadores_edicao],
                        multi=True,
                        placeholder="Todos"
                    )
                ]),

                html.Div([
                    html.Label("Órgão"),
                    dcc.Dropdown(
                        id="filtro_orgao",
                        options=[{"label": o, "value": o} for o in orgaos],
                        multi=True,
                        placeholder="Todos"
                    )
                ]),

                html.Div([
                    html.Label("Movimentação"),
                    dcc.Dropdown(
                        id="filtro_tipo_ato",
                        options=[
                            {"label": "Exonerações", "value": "exoneracao"},
                            {"label": "Nomeações", "value": "nomeacao"}
                        ],
                        multi=True,
                        placeholder="Todos"
                    )
                ]),
            ]
        ),

        html.Div(
            id="cards",
            style={
                "display": "grid",
                "gridTemplateColumns": "repeat(5, 1fr)",
                "gap": "12px",
                "marginBottom": "20px"
            }
        ),

        html.Div(
            style={"marginTop": "16px"},
            children=[dcc.Graph(id="serie_temporal_governo")],
        ),

        html.Div(
            style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginTop": "16px"},
            children=[
                dcc.Graph(id="fluxo_governos"),
                dcc.Graph(id="saldo_governos"),
            ],
        ),

        html.Div(
            style={"marginTop": "16px"},
            children=[dcc.Graph(id="timeline_governo")],
        ),

        html.Div(
            style={"marginTop": "16px"},
            children=[dcc.Graph(id="orgaos_governo")],
        ),

        html.Div(
            style={"marginTop": "16px"},
            children=[
                html.H3("Resumo por Representante"),
                html.Div(id="tabela_governos"),
            ],
        ),
    ]
)


# =====================================================
# CALLBACK
# =====================================================
@app.callback(
    Output("cards", "children"),
    Output("fluxo_governos", "figure"),
    Output("saldo_governos", "figure"),
    Output("serie_temporal_governo", "figure"),
    Output("timeline_governo", "figure"),
    Output("orgaos_governo", "figure"),
    Output("tabela_governos", "children"),
    Output("recarregar_status", "children"),
    Input("recarregar_base", "n_clicks"),
    Input("filtro_estado", "value"),
    Input("filtro_ano", "value"),
    Input("filtro_governador_edicao", "value"),
    Input("filtro_orgao", "value"),
    Input("filtro_tipo_ato", "value"),
)
def update(recarregar_clicks, estado, ano, governador_edicao, orgao, tipo_ato):
    global df, df_mov
    reload_status = ""
    if recarregar_clicks and ctx.triggered_id == "recarregar_base":
        df, df_mov = reload_analysis_base()
        reload_status = f"Base recarregada: {len(df_mov):,} movimentacoes".replace(",", ".")

    dff_mov = df_mov.copy()

    if estado:
        dff_mov = dff_mov[dff_mov["estado"] == estado]

    if ano:
        dff_mov = dff_mov[dff_mov["ano"].isin(ano)]

    if governador_edicao:
        dff_mov = dff_mov[dff_mov["representante_origem"].isin(governador_edicao)]

    if orgao:
        dff_mov = dff_mov[dff_mov["orgao"].isin(orgao)]

    if tipo_ato:
        dff_mov = dff_mov[dff_mov["tipo_ato"].isin(tipo_ato)]

    total = len(dff_mov)
    pessoas = dff_mov["pessoa"].nunique() if not dff_mov.empty else 0
    total_exoneracoes = int((dff_mov["tipo_ato"] == "exoneracao").sum()) if not dff_mov.empty else 0
    total_nomeacoes = int((dff_mov["tipo_ato"] == "nomeacao").sum()) if not dff_mov.empty else 0
    saldo = total_nomeacoes - total_exoneracoes

    cards = [
        card("Atos", f"{total:,}".replace(",", ".")),
        card("Exonerações", f"{total_exoneracoes:,}".replace(",", ".")),
        card("Nomeações", f"{total_nomeacoes:,}".replace(",", ".")),
        card("Saldo", f"{saldo:,}".replace(",", ".")),
        card("Pessoas únicas", f"{pessoas:,}".replace(",", ".")),
    ]

    return (
        cards,
        fig_fluxo_por_governo(dff_mov),
        fig_saldo_por_governo(dff_mov),
        fig_serie_temporal_governo(dff_mov),
        fig_timeline_governo(dff_mov),
        fig_orgaos_por_governo(dff_mov),
        tabela_resumo_governos(dff_mov),
        reload_status,
    )


def card(titulo, valor):
    return html.Div(
        style={
            "backgroundColor": "white",
            "padding": "16px",
            "borderRadius": "10px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.08)"
        },
        children=[
            html.Div(titulo, style={"fontSize": "13px", "color": "#666"}),
            html.Div(valor, style={"fontSize": "24px", "fontWeight": "bold"})
        ]
    )


# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(debug=False, port=8052, use_reloader=False)
