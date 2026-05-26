from __future__ import annotations

from dash import Input, Output, State, ctx, dcc, html

from analise_temporal.services import dados
from analise_temporal.services.graficos import (
    fig_fluxo_por_governo,
    fig_orgaos_por_governo,
    fig_saldo_por_governo,
    fig_serie_temporal_governo,
    fig_timeline_governo,
    periodo_anos,
    periodo_movimentacoes,
    tabela_resumo_governos,
)


def opcoes_iniciais():
    df = dados.df
    df_mov = dados.df_mov
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
    representantes = sorted(
        set(df["representante_origem"].dropna().astype(str).unique().tolist()).union(
            set(df_mov["representante_origem"].dropna().astype(str).unique().tolist())
        )
    )
    return estados, anos, orgaos, representantes


def create_layout():
    estados, anos, orgaos, governadores_edicao = opcoes_iniciais()
    return html.Div(
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
                    "gridTemplateColumns": "1fr 1.8fr 1.6fr 1.4fr 1fr",
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
                        html.Label("Governo"),
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
                        html.Label("Autoria do ato"),
                        dcc.Dropdown(
                            id="filtro_autoria",
                            options=[
                                {"label": "Governador", "value": "Governador"},
                                {"label": "Secretaria/Subsecretaria", "value": "Secretaria/Subsecretaria"},
                                {"label": "Outro/Nao identificado", "value": "Outro/Nao identificado"},
                            ],
                            multi=True,
                            placeholder="Todas"
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
                    "gridTemplateColumns": "repeat(7, 1fr)",
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
                html.H3("Resumo por Governo"),
                    html.Div(id="tabela_governos"),
                ],
            ),
        ]
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


def register_callbacks(app):
    @app.callback(
        Output("filtro_governador_edicao", "options"),
        Output("filtro_governador_edicao", "value"),
        Input("filtro_estado", "value"),
        Input("recarregar_base", "n_clicks"),
        State("filtro_governador_edicao", "value"),
    )
    def atualizar_opcoes_representante(estado, recarregar_clicks, selecionados):
        base = dados.df_mov.copy()
        if estado:
            base = base[base["estado"] == estado]
        representantes = sorted(base["representante_origem"].dropna().astype(str).unique().tolist())
        options = [{"label": representante, "value": representante} for representante in representantes]

        selecionados = selecionados or []
        selecionados_validos = [valor for valor in selecionados if valor in representantes]
        return options, selecionados_validos


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
        Input("filtro_autoria", "value"),
        Input("filtro_tipo_ato", "value"),
    )
    def update(recarregar_clicks, estado, ano, governador_edicao, orgao, autoria, tipo_ato):
        reload_status = ""
        if recarregar_clicks and ctx.triggered_id == "recarregar_base":
            dados.df, dados.df_mov = dados.reload_analysis_base()
            reload_status = f"Base recarregada: {len(dados.df_mov):,} movimentacoes".replace(",", ".")

        dff_mov = dados.df_mov.copy()

        if estado:
            dff_mov = dff_mov[dff_mov["estado"] == estado]

        periodo_top_orgaos = periodo_anos(ano) if ano else periodo_movimentacoes(dff_mov)

        if ano:
            dff_mov = dff_mov[dff_mov["ano"].isin(ano)]

        if governador_edicao:
            dff_mov = dff_mov[dff_mov["representante_origem"].isin(governador_edicao)]

        if orgao:
            dff_mov = dff_mov[dff_mov["orgao"].isin(orgao)]

        if autoria:
            dff_mov = dff_mov[dff_mov["autoria_ato"].isin(autoria)]

        if tipo_ato:
            dff_mov = dff_mov[dff_mov["tipo_ato"].isin(tipo_ato)]

        total = len(dff_mov)
        pessoas = dff_mov["pessoa"].nunique() if not dff_mov.empty else 0
        total_exoneracoes = int((dff_mov["tipo_ato"] == "exoneracao").sum()) if not dff_mov.empty else 0
        total_nomeacoes = int((dff_mov["tipo_ato"] == "nomeacao").sum()) if not dff_mov.empty else 0
        total_governador = int((dff_mov["autoria_ato"] == "Governador").sum()) if not dff_mov.empty else 0
        total_secretarias = int((dff_mov["autoria_ato"] == "Secretaria/Subsecretaria").sum()) if not dff_mov.empty else 0
        saldo = total_nomeacoes - total_exoneracoes

        cards = [
            card("Atos no governo", f"{total:,}".replace(",", ".")),
            card("Atos do governador", f"{total_governador:,}".replace(",", ".")),
            card("Atos de secretarias", f"{total_secretarias:,}".replace(",", ".")),
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
            fig_orgaos_por_governo(dff_mov, periodo_top_orgaos),
            tabela_resumo_governos(dff_mov),
            reload_status,
        )
