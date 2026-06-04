from __future__ import annotations

import os

from dash import Dash

from analise_temporal.paginas.dashboard import create_layout, register_callbacks


app = Dash(__name__)
server = app.server
app.title = "DOU RJ - Transicoes Markov"
app.layout = create_layout()
register_callbacks(app)


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8052"))
    app.run(host=host, port=port, debug=False, use_reloader=False)
