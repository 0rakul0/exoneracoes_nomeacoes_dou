# app.py
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import networkx as nx

from dash import Dash, dcc, html, Input, Output

# =====================================================
# CONFIG
# =====================================================
CSV_PATH = "../saida/analises/RJ/retornos_apos_exoneracao.csv"
TOP_N_TRANSICOES = 30

# =====================================================
# LOAD
# =====================================================
df = pd.read_csv(CSV_PATH)

df["pessoa"] = df["nome_normalizado"]
df["data_nomeacao"] = pd.to_datetime(df["data_publicacao"], errors="coerce")
df["data_exoneracao"] = pd.to_datetime(df["data_exoneracao_anterior"], errors="coerce")
df["ano"] = df["data_nomeacao"].dt.year

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

anos = sorted(df["ano"].dropna().astype(int).unique().tolist())
orgaos = sorted(df["orgao"].dropna().astype(str).unique().tolist())
tempos = sorted(df["tempo_cluster"].dropna().unique().tolist())

app.layout = html.Div(
    style={
        "fontFamily": "Arial",
        "padding": "20px",
        "backgroundColor": "#f7f7f7"
    },
    children=[
        html.H2("Análise de Transições — Exonerações e Nomeações DOU/RJ"),

        html.Div(
            style={
                "display": "grid",
                "gridTemplateColumns": "1fr 1fr 1fr 1fr 1fr",
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
                    html.Label("Órgão"),
                    dcc.Dropdown(
                        id="filtro_orgao",
                        options=[{"label": o, "value": o} for o in orgaos],
                        multi=True,
                        placeholder="Todos"
                    )
                ]),

                html.Div([
                    html.Label("Tempo de retorno"),
                    dcc.Dropdown(
                        id="filtro_tempo",
                        options=[{"label": t, "value": t} for t in tempos],
                        multi=True,
                        placeholder="Todos"
                    )
                ]),

                html.Div([
                    html.Label("Mudou cargo"),
                    dcc.Dropdown(
                        id="filtro_cargo",
                        options=[
                            {"label": "Sim", "value": True},
                            {"label": "Não", "value": False}
                        ],
                        multi=True,
                        placeholder="Todos"
                    )
                ]),

                html.Div([
                    html.Label("Mudou órgão"),
                    dcc.Dropdown(
                        id="filtro_orgao_flag",
                        options=[
                            {"label": "Sim", "value": True},
                            {"label": "Não", "value": False}
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

        dcc.Tabs([
            dcc.Tab(label="🔥 Sankey Animado por Ano", children=[
                dcc.Graph(id="sankey_animado")
            ]),

            dcc.Tab(label="📊 Timeline", children=[
                dcc.Graph(id="timeline_eventos"),
                dcc.Graph(id="timeline_mobilidade")
            ]),

            dcc.Tab(label="Sankey Geral", children=[
                dcc.Graph(id="sankey")
            ]),

            dcc.Tab(label="Rede 3D", children=[
                dcc.Graph(id="network_3d")
            ]),

            dcc.Tab(label="Matriz Markov", children=[
                dcc.Graph(id="heatmap")
            ]),

            dcc.Tab(label="Resumo", children=[
                html.Pre(
                    id="resumo",
                    style={
                        "backgroundColor": "white",
                        "padding": "20px",
                        "borderRadius": "8px",
                        "whiteSpace": "pre-wrap"
                    }
                )
            ]),
        ])
    ]
)


# =====================================================
# CALLBACK
# =====================================================
@app.callback(
    Output("cards", "children"),
    Output("sankey_animado", "figure"),
    Output("timeline_eventos", "figure"),
    Output("timeline_mobilidade", "figure"),
    Output("sankey", "figure"),
    Output("network_3d", "figure"),
    Output("heatmap", "figure"),
    Output("resumo", "children"),
    Input("filtro_ano", "value"),
    Input("filtro_orgao", "value"),
    Input("filtro_tempo", "value"),
    Input("filtro_cargo", "value"),
    Input("filtro_orgao_flag", "value"),
)
def update(ano, orgao, tempo, cargo, orgao_flag):
    dff = df.copy()

    if ano:
        dff = dff[dff["ano"].isin(ano)]

    if orgao:
        dff = dff[dff["orgao"].isin(orgao)]

    if tempo:
        dff = dff[dff["tempo_cluster"].isin(tempo)]

    if cargo:
        dff = dff[dff["mudou_cargo"].isin(cargo)]

    if orgao_flag:
        dff = dff[dff["mudou_orgao"].isin(orgao_flag)]

    _, trans = construir_eventos(dff)
    mat, mat_prob = matriz_transicao(trans)

    total = len(dff)
    pessoas = dff["pessoa"].nunique() if not dff.empty else 0
    media = dff["dias_desde_exoneracao"].mean() if not dff.empty else 0
    tx_cargo = dff["mudou_cargo"].mean() if not dff.empty else 0
    tx_orgao = dff["mudou_orgao"].mean() if not dff.empty else 0

    cards = [
        card("Registros", f"{total:,}".replace(",", ".")),
        card("Pessoas únicas", f"{pessoas:,}".replace(",", ".")),
        card("Média retorno", f"{media:.1f} dias"),
        card("Mudou cargo", f"{tx_cargo:.1%}"),
        card("Mudou órgão", f"{tx_orgao:.1%}"),
    ]

    return (
        cards,
        fig_sankey_animado_por_ano(dff),
        fig_timeline_eventos(dff),
        fig_timeline_mobilidade(dff),
        fig_sankey(trans),
        fig_network_3d(trans),
        fig_heatmap(mat_prob),
        gerar_resumo(dff, trans, mat_prob)
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
    app.run(debug=True)