from __future__ import annotations

import sys
import os
from pathlib import Path

from dash import Dash

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analise_temporal.paginas.dashboard import create_layout, register_callbacks
from analise_temporal.services.dados import df, df_mov
from analise_temporal.services.graficos import (
    fig_fluxo_por_governo,
    fig_orgaos_por_governo,
    fig_saldo_por_governo,
    fig_serie_temporal_governo,
    fig_timeline_governo,
    periodo_movimentacoes,
)


app = Dash(__name__)
server = app.server
app.title = "DOU RJ - Transicoes Markov"
app.layout = create_layout()
register_callbacks(app)


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8052"))
    app.run(host=host, debug=False, port=port, use_reloader=False)
