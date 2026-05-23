from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALISES_DIR = PROJECT_ROOT / "saida" / "analises"
OUTPUT_PATH = ANALISES_DIR / "index.html"


def load_movimentacoes(analyses_dir: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for state_dir in sorted(path for path in analyses_dir.iterdir() if path.is_dir()):
        csv_path = state_dir / "movimentacoes_pessoas.csv"
        if not csv_path.exists():
            continue

        frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        frame["estado"] = state_dir.name.upper()
        frames.append(frame)

    if not frames:
        raise FileNotFoundError(f"Nenhum movimentacoes_pessoas.csv encontrado em {analyses_dir}")

    return pd.concat(frames, ignore_index=True)


def build_records(dataframe: pd.DataFrame) -> list[dict[str, str | int]]:
    dataframe = dataframe.copy()
    dataframe["data_publicacao"] = pd.to_datetime(dataframe["data_publicacao"], errors="coerce")
    dataframe = dataframe[dataframe["data_publicacao"].notna()].copy()
    dataframe["ano"] = dataframe["data_publicacao"].dt.year.astype(int)
    dataframe["mes"] = dataframe["data_publicacao"].dt.strftime("%Y-%m")
    dataframe["data_publicacao"] = dataframe["data_publicacao"].dt.strftime("%Y-%m-%d")

    for column in ["representante_governo", "origem_representante", "orgao", "tipo_ato"]:
        if column not in dataframe.columns:
            dataframe[column] = ""

    if "representante_origem" not in dataframe.columns:
        dataframe["representante_origem"] = (
            dataframe["representante_governo"].replace("", "Nao identificado")
            + " ("
            + dataframe["origem_representante"].replace("", "Nao identificado")
            + ")"
        )
    dataframe["representante_origem"] = dataframe["representante_origem"].replace("", "Nao identificado")
    dataframe["orgao"] = dataframe["orgao"].replace("", "Sem identificacao")
    dataframe["pessoa"] = dataframe.get("nome_normalizado", dataframe.get("nome", "")).replace("", "Nao identificado")

    columns = [
        "estado",
        "ano",
        "mes",
        "data_publicacao",
        "tipo_ato",
        "pessoa",
        "representante_origem",
        "orgao",
    ]
    return dataframe[columns].to_dict(orient="records")


def html_template(records: list[dict[str, str | int]]) -> str:
    data_json = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Analises DOERJ</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f7f7f7; color: #17233c; }}
    main {{ padding: 20px; min-width: 980px; }}
    h1 {{ margin: 0 0 16px; font-size: 24px; }}
    .tabs {{ display: flex; gap: 8px; margin-bottom: 16px; }}
    .tab {{ border: 1px solid #c8d1e6; background: white; color: #17233c; cursor: pointer; padding: 10px 18px; font-weight: 700; }}
    .tab.active {{ background: #1f5eff; border-color: #1f5eff; color: white; }}
    .toolbar {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
    button {{ border: 0; background: #1f5eff; color: white; cursor: pointer; font-weight: 700; padding: 10px 14px; }}
    .status {{ color: #555; font-size: 13px; }}
    .filters {{ display: grid; grid-template-columns: 1fr 1.8fr 1.6fr 1fr; gap: 12px; margin-bottom: 20px; }}
    label {{ display: block; font-size: 16px; margin-bottom: 4px; }}
    select {{ width: 100%; min-height: 38px; border: 1px solid #b9c4df; background: white; padding: 6px; }}
    .cards {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 20px; }}
    .card {{ background: white; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
    .card .label {{ color: #666; font-size: 13px; }}
    .card .value {{ color: #000; font-size: 24px; font-weight: 700; margin-top: 4px; }}
    .graph {{ background: white; margin-top: 16px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; margin-top: 8px; }}
    th, td {{ border-bottom: 1px solid #e3e7f0; padding: 8px; text-align: left; font-size: 13px; }}
    th {{ background: #edf2fb; }}
  </style>
</head>
<body>
<main>
  <h1>Movimentacoes por Governo - Exoneracoes e Nomeacoes por Estado</h1>
  <div id="tabs" class="tabs"></div>
  <div class="toolbar">
    <button id="reload">Recarregar base</button>
    <span id="status" class="status"></span>
  </div>
  <section class="filters">
    <div><label>Ano</label><select id="ano" multiple></select></div>
    <div><label>Representante</label><select id="representante" multiple></select></div>
    <div><label>Orgao</label><select id="orgao" multiple></select></div>
    <div><label>Movimentacao</label><select id="tipo" multiple><option value="exoneracao">Exoneracoes</option><option value="nomeacao">Nomeacoes</option></select></div>
  </section>
  <section id="cards" class="cards"></section>
  <div id="serie" class="graph"></div>
  <section class="grid">
    <div id="fluxo" class="graph"></div>
    <div id="saldo" class="graph"></div>
  </section>
  <div id="timeline" class="graph"></div>
  <div id="orgaos" class="graph"></div>
  <h2>Resumo por Representante</h2>
  <div id="tabela"></div>
</main>
<script>
const BASE = {data_json};
let selectedState = null;

const fmt = new Intl.NumberFormat('pt-BR');
const byId = (id) => document.getElementById(id);
const selectedValues = (id) => Array.from(byId(id).selectedOptions).map(option => option.value);
const unique = (items) => [...new Set(items.filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b)));

function setOptions(id, values) {{
  const select = byId(id);
  const chosen = new Set(selectedValues(id));
  select.innerHTML = values.map(value => `<option value="${{escapeHtml(value)}}">${{escapeHtml(value)}}</option>`).join('');
  Array.from(select.options).forEach(option => option.selected = chosen.has(option.value));
}}

function escapeHtml(value) {{
  return String(value).replace(/[&<>"']/g, char => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}}[char]));
}}

function countBy(rows, keyFn) {{
  const result = new Map();
  for (const row of rows) {{
    const key = keyFn(row);
    result.set(key, (result.get(key) || 0) + 1);
  }}
  return result;
}}

function grouped(rows, keyFn) {{
  const result = new Map();
  for (const row of rows) {{
    const key = keyFn(row);
    if (!result.has(key)) result.set(key, []);
    result.get(key).push(row);
  }}
  return result;
}}

function currentRows() {{
  const years = new Set(selectedValues('ano').map(Number));
  const reps = new Set(selectedValues('representante'));
  const orgaos = new Set(selectedValues('orgao'));
  const tipos = new Set(selectedValues('tipo'));
  return BASE.filter(row =>
    (!selectedState || row.estado === selectedState) &&
    (!years.size || years.has(row.ano)) &&
    (!reps.size || reps.has(row.representante_origem)) &&
    (!orgaos.size || orgaos.has(row.orgao)) &&
    (!tipos.size || tipos.has(row.tipo_ato))
  );
}}

function renderTabs() {{
  const states = unique(BASE.map(row => row.estado));
  selectedState = selectedState || states[0] || null;
  byId('tabs').innerHTML = states.map(state =>
    `<button class="tab ${{state === selectedState ? 'active' : ''}}" data-state="${{state}}">${{state}}</button>`
  ).join('');
  document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => {{
    selectedState = tab.dataset.state;
    refreshOptions();
    render();
  }}));
}}

function refreshOptions() {{
  const stateRows = BASE.filter(row => !selectedState || row.estado === selectedState);
  setOptions('ano', unique(stateRows.map(row => row.ano)).map(String));
  setOptions('representante', unique(stateRows.map(row => row.representante_origem)));
  setOptions('orgao', unique(stateRows.map(row => row.orgao)));
}}

function renderCards(rows) {{
  const exoneracoes = rows.filter(row => row.tipo_ato === 'exoneracao').length;
  const nomeacoes = rows.filter(row => row.tipo_ato === 'nomeacao').length;
  const pessoas = new Set(rows.map(row => row.pessoa)).size;
  const cards = [
    ['Atos', rows.length],
    ['Exoneracoes', exoneracoes],
    ['Nomeacoes', nomeacoes],
    ['Saldo', nomeacoes - exoneracoes],
    ['Pessoas unicas', pessoas],
  ];
  byId('cards').innerHTML = cards.map(([label, value]) =>
    `<div class="card"><div class="label">${{label}}</div><div class="value">${{fmt.format(value)}}</div></div>`
  ).join('');
}}

function renderSerie(rows) {{
  const traces = [];
  const reps = unique(rows.map(row => row.representante_origem)).slice(0, 12);
  for (const rep of reps) {{
    for (const tipo of ['nomeacao', 'exoneracao']) {{
      const values = countBy(rows.filter(row => row.representante_origem === rep && row.tipo_ato === tipo), row => row.mes);
      const months = unique([...values.keys()]);
      traces.push({{
        x: months,
        y: months.map(month => tipo === 'exoneracao' ? -values.get(month) : values.get(month)),
        mode: 'lines+markers',
        name: `${{rep}} - ${{tipo}}`,
        line: {{dash: tipo === 'exoneracao' ? 'dot' : 'solid'}}
      }});
    }}
  }}
  Plotly.react('serie', traces, {{
    title: 'Serie Temporal por Representante - Nomeacoes Acima e Exoneracoes Abaixo',
    height: 520,
    yaxis: {{title: 'Quantidade de atos'}},
    margin: {{l: 70, r: 20, t: 60, b: 50}}
  }}, {{responsive: true}});
}}

function renderFluxo(rows) {{
  const reps = unique(rows.map(row => row.representante_origem));
  const nomeacoes = countBy(rows.filter(row => row.tipo_ato === 'nomeacao'), row => row.representante_origem);
  const exoneracoes = countBy(rows.filter(row => row.tipo_ato === 'exoneracao'), row => row.representante_origem);
  Plotly.react('fluxo', [
    {{x: reps, y: reps.map(rep => nomeacoes.get(rep) || 0), type: 'bar', name: 'Nomeacoes'}},
    {{x: reps, y: reps.map(rep => exoneracoes.get(rep) || 0), type: 'bar', name: 'Exoneracoes'}}
  ], {{title: 'Fluxo por Representante', barmode: 'group', height: 420, margin: {{l: 50, r: 20, t: 60, b: 140}}}}, {{responsive: true}});
}}

function renderSaldo(rows) {{
  const reps = unique(rows.map(row => row.representante_origem));
  const nomeacoes = countBy(rows.filter(row => row.tipo_ato === 'nomeacao'), row => row.representante_origem);
  const exoneracoes = countBy(rows.filter(row => row.tipo_ato === 'exoneracao'), row => row.representante_origem);
  const saldo = reps.map(rep => (nomeacoes.get(rep) || 0) - (exoneracoes.get(rep) || 0));
  Plotly.react('saldo', [{{x: reps, y: saldo, type: 'bar', marker: {{color: saldo.map(value => value >= 0 ? '#2ca02c' : '#d62728')}}}}],
    {{title: 'Saldo Nomeacoes - Exoneracoes', height: 420, margin: {{l: 50, r: 20, t: 60, b: 140}}}}, {{responsive: true}});
}}

function renderTimeline(rows) {{
  const values = countBy(rows, row => `${{row.data_publicacao}}|${{row.representante_origem}}|${{row.tipo_ato}}`);
  const points = [...values.entries()].map(([key, value]) => {{
    const [date, rep, tipo] = key.split('|');
    return {{date, rep, tipo, value}};
  }});
  Plotly.react('timeline', [{{
    x: points.map(point => point.date),
    y: points.map(point => point.rep),
    text: points.map(point => `${{point.tipo}}: ${{point.value}}`),
    mode: 'markers',
    marker: {{size: points.map(point => Math.max(6, Math.sqrt(point.value) * 4)), color: points.map(point => point.tipo === 'nomeacao' ? '#1f77b4' : '#d62728')}}
  }}], {{title: 'Timeline por Representante', height: 500, margin: {{l: 180, r: 20, t: 60, b: 50}}}}, {{responsive: true}});
}}

function renderOrgaos(rows) {{
  const counts = [...countBy(rows, row => row.orgao).entries()].sort((a, b) => b[1] - a[1]).slice(0, 20).reverse();
  Plotly.react('orgaos', [{{x: counts.map(item => item[1]), y: counts.map(item => item[0]), type: 'bar', orientation: 'h'}}],
    {{title: 'Top Orgaos', height: Math.max(460, counts.length * 28 + 120), margin: {{l: 260, r: 20, t: 60, b: 50}}}}, {{responsive: true}});
}}

function renderTable(rows) {{
  const groups = grouped(rows, row => row.representante_origem);
  const tableRows = [...groups.entries()].map(([rep, items]) => {{
    const nomeacoes = items.filter(row => row.tipo_ato === 'nomeacao').length;
    const exoneracoes = items.filter(row => row.tipo_ato === 'exoneracao').length;
    return [rep, items.length, nomeacoes, exoneracoes, nomeacoes - exoneracoes, new Set(items.map(row => row.pessoa)).size];
  }}).sort((a, b) => b[1] - a[1]);
  byId('tabela').innerHTML = `<table><thead><tr><th>Representante</th><th>Atos</th><th>Nomeacoes</th><th>Exoneracoes</th><th>Saldo</th><th>Pessoas</th></tr></thead><tbody>${{tableRows.map(row => `<tr>${{row.map((cell, index) => `<td>${{index ? fmt.format(cell) : escapeHtml(cell)}}</td>`).join('')}}</tr>`).join('')}}</tbody></table>`;
}}

function render() {{
  renderTabs();
  const rows = currentRows();
  renderCards(rows);
  renderSerie(rows);
  renderFluxo(rows);
  renderSaldo(rows);
  renderTimeline(rows);
  renderOrgaos(rows);
  renderTable(rows);
}}

for (const id of ['ano', 'representante', 'orgao', 'tipo']) {{
  byId(id).addEventListener('change', render);
}}
byId('reload').addEventListener('click', () => window.location.reload());
byId('status').textContent = `Base carregada: ${{fmt.format(BASE.length)}} movimentacoes`;
renderTabs();
refreshOptions();
render();
</script>
</body>
</html>"""


def main() -> int:
    records = build_records(load_movimentacoes(ANALISES_DIR))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html_template(records), encoding="utf-8")
    print(f"HTML gerado em: {OUTPUT_PATH}")
    print(f"Registros exportados: {len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
