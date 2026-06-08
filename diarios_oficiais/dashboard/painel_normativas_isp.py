from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import subprocess
import sys
import textwrap
import unicodedata
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET
from urllib.request import urlopen

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKBOOK_DIR = PROJECT_ROOT / "saida" / "ISP" / "o_que_muda_onde_muda"
DEFAULT_WORKBOOK = DEFAULT_WORKBOOK_DIR / "ISP_o_que_muda_onde_muda.xlsx"
DEFAULT_CACHE_DIR = PROJECT_ROOT / ".cache" / "geodata"
DEFAULT_DASHBOARD_CACHE_DIR = PROJECT_ROOT / "saida" / "ISP" / "dashboard_cache"
IBGE_RJ_MUNICIPIOS_GEOJSON = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/33"
    "?formato=application/vnd.geo+json&qualidade=minima&intrarregiao=municipio"
)
IBGE_RJ_MUNICIPIOS_API = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/33/municipios"
TERRITORY_CACHE_DIR = DEFAULT_CACHE_DIR / "isp_territorios"
TERRITORY_RELATION_URL = "https://www.ispdados.rj.gov.br/Arquivos/Relacao_RISPxAISPxCISP.csv"
TERRITORY_KML_URLS = {
    "RISP": "https://www.ispdados.rj.gov.br/Arquivos/RISPkml.rar",
    "AISP": "https://www.ispdados.rj.gov.br/Arquivos/AISPkml.rar",
    "CISP": "https://www.ispdados.rj.gov.br/Arquivos/CISPkml.rar",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dashboard das normativas de area de atuacao do ISP.",
    )
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8053)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--boundary-geojson", type=Path)
    parser.add_argument("--boundary-key", help="Campo do GeoJSON com o numero da unidade, ex.: cisp.")
    parser.add_argument("--boundary-type", choices=["CISP", "AISP", "RISP"], default="CISP")
    return parser.parse_args()


ARGS = parse_args()


def resolve_workbook_path(workbook: Path) -> Path:
    workbook = workbook.expanduser()
    if workbook.exists():
        return workbook

    if workbook == DEFAULT_WORKBOOK:
        candidates = sorted(
            DEFAULT_WORKBOOK_DIR.glob("ISP_o_que_muda_onde_muda*.xlsx"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0]

    expected = DEFAULT_WORKBOOK
    raise FileNotFoundError(
        "Workbook nao encontrado. Gere primeiro a matriz com "
        "diarios_oficiais/tratamentos/gerar_matriz_cisp_alteracoes.py "
        f"ou informe --workbook. Caminho esperado: {expected}"
    )


ARGS.workbook = resolve_workbook_path(ARGS.workbook)


def dashboard_cache_path(name: str) -> Path:
    return DEFAULT_DASHBOARD_CACHE_DIR / name


def cache_is_fresh(path: Path, source: Path | None = None) -> bool:
    if not path.exists():
        return False
    if source is not None and source.exists() and path.stat().st_mtime < source.stat().st_mtime:
        return False
    return True


def normalize_text(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().upper()


def safe_text(value: object, limit: int = 220) -> str:
    text = "" if pd.isna(value) else re.sub(r"\s+", " ", str(value)).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def wrap_hover_text(value: object, width: int = 64, limit: int = 650) -> str:
    text = safe_text(value, limit)
    if not text:
        return ""

    parts = []
    for part in text.split(" | "):
        wrapped = textwrap.wrap(part.strip(), width=width, break_long_words=False, break_on_hyphens=False)
        parts.append("<br>".join(wrapped) if wrapped else part.strip())
    return "<br>".join(parts)


def download_json(url: str, output: Path) -> dict | list:
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists():
        raw = urlopen(url, timeout=60).read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        output.write_bytes(raw)
    return json.loads(output.read_text(encoding="utf-8"))


def download_file(url: str, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists():
        output.write_bytes(urlopen(url, timeout=120).read())
    return output


@lru_cache(maxsize=1)
def load_territory_relation() -> pd.DataFrame:
    parquet_path = dashboard_cache_path("relacao_territorial.parquet")
    if cache_is_fresh(parquet_path):
        return pd.read_parquet(parquet_path)

    path = download_file(TERRITORY_RELATION_URL, TERRITORY_CACHE_DIR / "relacao_risp_aisp_cisp.csv")
    try:
        df = pd.read_csv(path, sep=";", dtype=str, keep_default_na=False)
    except UnicodeDecodeError:
        df = pd.read_csv(path, sep=";", dtype=str, keep_default_na=False, encoding="latin1")
    df.columns = [str(col).strip() for col in df.columns]
    for col in ["RISP", "AISP", "CISP"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64").astype(str).replace("<NA>", "")
    return df


def ensure_kml(layer: str) -> Path:
    layer = layer.upper()
    kml_path = TERRITORY_CACHE_DIR / f"{layer}.kml"
    if kml_path.exists():
        return kml_path

    rar_path = download_file(TERRITORY_KML_URLS[layer], TERRITORY_CACHE_DIR / f"{layer}kml.rar")
    extract_dir = TERRITORY_CACHE_DIR / layer
    extract_dir.mkdir(parents=True, exist_ok=True)

    tar_exe = shutil.which("tar")
    if not tar_exe:
        raise RuntimeError("Nao encontrei tar.exe para extrair os arquivos RAR de KML do ISP.")

    subprocess.run([tar_exe, "-xf", str(rar_path), "-C", str(extract_dir)], check=True)
    extracted = extract_dir / "doc.kml"
    if not extracted.exists():
        raise FileNotFoundError(f"KML nao encontrado dentro de {rar_path}")

    shutil.copyfile(extracted, kml_path)
    return kml_path


def parse_kml_coordinates(value: str | None) -> list[list[float]]:
    coords = []
    for item in (value or "").strip().split():
        parts = item.split(",")
        if len(parts) < 2:
            continue
        try:
            coords.append([float(parts[0]), float(parts[1])])
        except ValueError:
            continue
    return coords


@lru_cache(maxsize=3)
def load_territory_geojson(layer: str) -> dict:
    layer = layer.upper()
    path = ensure_kml(layer)
    root = ET.parse(path).getroot()
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    grouped: dict[str, list[list[list[list[float]]]]] = {}

    for placemark in root.findall(".//k:Placemark", ns):
        unit = safe_text(placemark.findtext("k:name", default="", namespaces=ns), 80)
        unit = str(int(float(unit))) if re.fullmatch(r"\d+(?:\.0+)?", unit) else unit.strip()
        if not unit:
            continue

        polygons = []
        for polygon in placemark.findall(".//k:Polygon", ns):
            rings = []
            outer = polygon.find(".//k:outerBoundaryIs/k:LinearRing/k:coordinates", ns)
            outer_coords = parse_kml_coordinates(outer.text if outer is not None else "")
            if not outer_coords:
                continue
            rings.append(outer_coords)
            for inner in polygon.findall(".//k:innerBoundaryIs/k:LinearRing/k:coordinates", ns):
                inner_coords = parse_kml_coordinates(inner.text)
                if inner_coords:
                    rings.append(inner_coords)
            polygons.append(rings)

        if polygons:
            grouped.setdefault(unit, []).extend(polygons)

    features = []
    for unit, polygons in sorted(grouped.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0]):
        geometry = (
            {"type": "Polygon", "coordinates": polygons[0]}
            if len(polygons) == 1
            else {"type": "MultiPolygon", "coordinates": polygons}
        )
        features.append(
            {
                "type": "Feature",
                "id": unit,
                "properties": {"id": unit, "unidade": unit, "camada": layer, "label": f"{layer} {unit}"},
                "geometry": geometry,
            }
        )

    return {"type": "FeatureCollection", "features": features}


@lru_cache(maxsize=4)
def load_grouped_territory_geojson(layer: str) -> dict:
    layer = layer.upper()
    cache_path = dashboard_cache_path(f"geojson_{layer}.geojson")
    if cache_is_fresh(cache_path):
        return json.loads(cache_path.read_text(encoding="utf-8"))

    from shapely.geometry import mapping, shape
    from shapely.ops import unary_union

    if layer == "CISP":
        return load_territory_geojson("CISP")

    rel = load_territory_relation()
    cisp_geojson = load_territory_geojson("CISP")
    cisp_shapes = {
        str(feature["id"]): shape(feature["geometry"])
        for feature in cisp_geojson.get("features", [])
    }

    features = []
    group_col = "Região de Governo" if layer == "REGIAO" else layer
    for unit, group in rel.groupby(group_col, sort=True):
        geometries = [cisp_shapes[cisp] for cisp in group["CISP"].astype(str).unique() if cisp in cisp_shapes]
        if not geometries:
            continue
        merged = unary_union(geometries)
        unit = str(int(float(unit))) if re.fullmatch(r"\d+(?:\.0+)?", str(unit)) else str(unit)
        features.append(
            {
                "type": "Feature",
                "id": unit,
                "properties": {"id": unit, "unidade": unit, "camada": layer, "label": f"{layer} {unit}"},
                "geometry": mapping(merged),
            }
        )

    features.sort(key=lambda feature: int(feature["id"]) if str(feature["id"]).isdigit() else str(feature["id"]))
    return {"type": "FeatureCollection", "features": features}


def join_unique(values: pd.Series, limit: int = 18) -> str:
    seen = []
    for value in values:
        text = safe_text(value, 500)
        if text and text not in seen:
            seen.append(text)
    suffix = "" if len(seen) <= limit else f" +{len(seen) - limit}"
    return " | ".join(seen[:limit]) + suffix


def territory_frame(layer: str) -> pd.DataFrame:
    rel = load_territory_relation()
    layer = layer.upper()

    if layer == "RISP":
        df = (
            rel.groupby("RISP", as_index=False)
            .agg(
                aisp=("AISP", lambda values: ", ".join(sorted(set(values), key=lambda x: int(x)))),
                cisp_qtd=("CISP", "nunique"),
                municipios_qtd=("Município", "nunique"),
                municipios=("Município", join_unique),
                regioes=("Região de Governo", join_unique),
            )
            .rename(columns={"RISP": "id"})
        )
    elif layer == "AISP":
        df = (
            rel.groupby(["RISP", "AISP"], as_index=False)
            .agg(
                cisp=("CISP", lambda values: ", ".join(sorted(set(values), key=lambda x: int(x)))),
                cisp_qtd=("CISP", "nunique"),
                municipios_qtd=("Município", "nunique"),
                municipios=("Município", join_unique),
                regioes=("Região de Governo", join_unique),
            )
            .rename(columns={"AISP": "id"})
        )
    elif layer == "REGIAO":
        df = (
            rel.groupby("Região de Governo", as_index=False)
            .agg(
                risp=("RISP", lambda values: ", ".join(sorted(set(values), key=lambda x: int(x)))),
                aisp=("AISP", lambda values: ", ".join(sorted(set(values), key=lambda x: int(x)))),
                cisp=("CISP", lambda values: ", ".join(sorted(set(values), key=lambda x: int(x)))),
                cisp_qtd=("CISP", "nunique"),
                municipios_qtd=("Município", "nunique"),
                municipios=("Município", join_unique),
            )
            .rename(columns={"Região de Governo": "id"})
        )
        df["regioes"] = df["id"]
    else:
        df = (
            rel.groupby(["RISP", "AISP", "CISP"], as_index=False)
            .agg(
                unidade_territorial=("Unidade Territorial", join_unique),
                municipios=("Município", join_unique),
                municipios_qtd=("Município", "nunique"),
                regioes=("Região de Governo", join_unique),
            )
            .rename(columns={"CISP": "id"})
        )
        df["cisp_qtd"] = 1

    df["id"] = df["id"].astype(str)
    df["numero"] = pd.to_numeric(df["id"], errors="coerce")
    if df["numero"].isna().all():
        df["numero"] = pd.factorize(df["id"])[0] + 1
    df["label"] = layer + " " + df["id"]
    df["camada"] = layer
    return df


def filter_territory(
    layer: str,
    risp: list[str] | None,
    aisp: list[str] | None,
    cisp: list[str] | None,
    regioes: list[str] | None,
    texto: str | None,
) -> pd.DataFrame:
    df = territory_frame(layer)
    if "regioes" in df.columns and regioes:
        filtro_regioes = [str(v) for v in regioes]
        df = df[df["regioes"].astype(str).apply(lambda value: any(regiao in value for regiao in filtro_regioes))]
    if "RISP" in df.columns and risp:
        df = df[df["RISP"].isin([str(v) for v in risp])]
    if "AISP" in df.columns and aisp:
        df = df[df["AISP"].isin([str(v) for v in aisp])]
    if layer.upper() == "CISP" and cisp:
        df = df[df["id"].isin([str(v) for v in cisp])]
    if texto:
        needle = normalize_text(texto)
        haystack = df.fillna("").astype(str).agg(" ".join, axis=1).map(normalize_text)
        df = df[haystack.str.contains(re.escape(needle), na=False)]
    return df


def territorial_norm_options() -> list[dict[str, object]]:
    event_rows = DF[
        DF["data_norma"].notna()
        & DF["unidade_tipo"].isin(["CISP", "AISP", "RISP"])
        & DF["unidade_numero_norm"].astype(str).str.strip().ne("")
    ].copy()
    if event_rows.empty:
        return []
    event_rows = event_rows.sort_values(["data_norma", "norma_id"], ascending=[False, True])
    options = []
    seen = set()
    for _, row in event_rows.iterrows():
        norma = safe_text(row.get("norma_id", ""), 180)
        if not norma or norma in seen:
            continue
        seen.add(norma)
        data = pd.to_datetime(row.get("data_norma", ""), errors="coerce")
        label = norma if pd.isna(data) else f"{data:%Y-%m-%d} - {norma}"
        options.append({"label": label, "value": norma})
    return options


@lru_cache(maxsize=1)
def expanded_change_events_cisp() -> pd.DataFrame:
    parquet_path = dashboard_cache_path("eventos_cisp_expandido.parquet")
    if cache_is_fresh(parquet_path, ARGS.workbook):
        return pd.read_parquet(parquet_path)

    rel = load_territory_relation()
    event_rows = DF[
        DF["data_norma"].notna()
        & DF["unidade_tipo"].isin(["CISP", "AISP", "RISP"])
        & DF["unidade_numero_norm"].astype(str).str.strip().ne("")
    ].copy()

    rows = []
    for _, event in event_rows.iterrows():
        unit = str(event.get("unidade_numero_norm", "")).strip()
        unit_type = str(event.get("unidade_tipo", "")).strip().upper()

        if unit_type == "CISP":
            related = rel[rel["CISP"].astype(str).eq(unit)]
        elif unit_type == "AISP":
            related = rel[rel["AISP"].astype(str).eq(unit)]
        elif unit_type == "RISP":
            related = rel[rel["RISP"].astype(str).eq(unit)]
        else:
            continue

        for _, terr in related.iterrows():
            rows.append(
                {
                    "data_norma": event["data_norma"],
                    "data_label": event["data_norma"].strftime("%Y-%m-%d"),
                    "norma_id": safe_text(event.get("norma_id", ""), 180),
                    "acao_detectada": safe_text(event.get("acao_detectada", ""), 80),
                    "o_que_mudou": safe_text(event.get("o_que_mudou", ""), 420),
                    "CISP": str(terr["CISP"]),
                    "AISP": str(terr["AISP"]),
                    "RISP": str(terr["RISP"]),
                    "REGIAO": str(terr["Região de Governo"]),
                    "unidade_origem": f"{unit_type} {unit}",
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "data_norma", "data_label", "norma_id", "acao_detectada", "o_que_mudou",
                "CISP", "AISP", "RISP", "REGIAO", "unidade_origem",
            ]
        )

    return pd.DataFrame(rows).drop_duplicates(
        subset=["data_label", "norma_id", "acao_detectada", "CISP", "unidade_origem"]
    )


def timeline_events_for_layer(layer: str, territory_df: pd.DataFrame, normas: list[str] | None = None) -> pd.DataFrame:
    layer = layer.upper()
    events = expanded_change_events_cisp()

    if events.empty or territory_df.empty:
        return pd.DataFrame()

    if normas:
        events = events[events["norma_id"].isin([str(norma) for norma in normas])]

    selected_ids = set(territory_df["id"].astype(str))
    events = events[events[layer].astype(str).isin(selected_ids)].copy()
    if events.empty:
        return pd.DataFrame()

    grouped = (
        events.groupby(["data_norma", "data_label", layer], as_index=False)
        .agg(
            eventos=("norma_id", "nunique"),
            normas=("norma_id", join_unique),
            acoes=("acao_detectada", join_unique),
            cisp_afetadas=("CISP", "nunique"),
            unidades_origem=("unidade_origem", join_unique),
            historia=("o_que_mudou", join_unique),
        )
        .rename(columns={layer: "id"})
    )

    dates = grouped[["data_norma", "data_label"]].drop_duplicates().sort_values("data_norma")
    base = (
        territory_df[["id", "label", "numero"]]
        .astype({"id": str})
        .merge(dates, how="cross")
    )
    timeline = base.merge(grouped, on=["id", "data_norma", "data_label"], how="left")
    timeline["eventos"] = timeline["eventos"].fillna(0).astype(int)
    timeline["cisp_afetadas"] = timeline["cisp_afetadas"].fillna(0).astype(int)
    for col in ["normas", "acoes", "unidades_origem", "historia"]:
        timeline[col] = timeline[col].fillna("")

    return timeline.sort_values(["data_norma", "numero", "id"])


@lru_cache(maxsize=1)
def load_municipality_geojson() -> dict:
    geojson = download_json(IBGE_RJ_MUNICIPIOS_GEOJSON, ARGS.cache_dir / "rj_municipios_ibge.geojson")
    municipios = download_json(IBGE_RJ_MUNICIPIOS_API, ARGS.cache_dir / "rj_municipios_ibge.json")
    nomes_por_codigo = {str(item["id"]): item["nome"] for item in municipios}
    for feature in geojson.get("features", []):
        codigo = str(feature.get("properties", {}).get("codarea", ""))
        feature.setdefault("properties", {})["nome"] = nomes_por_codigo.get(codigo, codigo)
        feature["properties"]["nome_norm"] = normalize_text(feature["properties"]["nome"])
    return geojson


@lru_cache(maxsize=1)
def load_boundary_geojson() -> dict | None:
    if not ARGS.boundary_geojson:
        return None
    data = json.loads(ARGS.boundary_geojson.read_text(encoding="utf-8"))
    key = ARGS.boundary_key
    if key:
        for feature in data.get("features", []):
            raw_value = feature.get("properties", {}).get(key)
            if raw_value is not None:
                feature.setdefault("properties", {})["unidade_numero_norm"] = str(int(float(raw_value)))
    return data


def load_data(workbook: Path) -> pd.DataFrame:
    parquet_path = dashboard_cache_path("o_que_muda_onde.parquet")
    if cache_is_fresh(parquet_path, workbook):
        return pd.read_parquet(parquet_path)

    if not workbook.exists():
        raise FileNotFoundError(f"Workbook nao encontrado: {workbook}")

    df = pd.read_excel(workbook, sheet_name="O_que_muda_onde")
    for col in ["data_publicacao", "data_norma"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    df["ano_norma"] = df["data_norma"].dt.year.fillna(df["ano_publicacao"]).astype("Int64")
    df["unidade_tipo"] = df["unidade_tipo"].fillna("NAO_IDENTIFICADO").astype(str)
    df["acao_detectada"] = df["acao_detectada"].fillna("sem classificacao").astype(str)
    df["norma_id"] = df["norma_id"].fillna("Sem norma identificada").astype(str)
    df["municipio_norm"] = df.apply(
        lambda row: normalize_text(row["unidade_nome"]) if row["unidade_tipo"] == "MUNICIPIO" else "",
        axis=1,
    )
    df["unidade_numero_norm"] = (
        pd.to_numeric(df["unidade_numero"], errors="coerce")
        .astype("Int64")
        .astype(str)
        .replace("<NA>", "")
    )
    df["ementa_curta"] = df["ementa_limpa"].map(lambda value: safe_text(value, 260))
    df["mudanca_curta"] = df["o_que_mudou"].map(lambda value: safe_text(value, 320))
    return df


DF = load_data(ARGS.workbook)


def build_diario_lookup(df: pd.DataFrame) -> dict[str, str]:
    lookup = {}
    source = df[["norma_id", "data_publicacao"]].dropna(subset=["norma_id"]).drop_duplicates()
    for _, row in source.iterrows():
        data_publicacao = pd.to_datetime(row["data_publicacao"], errors="coerce")
        if pd.isna(data_publicacao):
            continue
        lookup[normalize_text(row["norma_id"])] = f"D.O. {data_publicacao:%Y-%m-%d}"
    return lookup


DIARIO_POR_NORMA = build_diario_lookup(DF)


def incluir_data_diario_na_celula(value: object) -> object:
    text = safe_text(value, 10_000)
    if not text or "D.O." in text:
        return value

    partes = []
    alterou = False
    for item in text.split(" | "):
        item_limpo = item.strip()
        chave_item = normalize_text(item_limpo)
        data_diario = next((data for norma, data in DIARIO_POR_NORMA.items() if norma in chave_item), "")
        if data_diario:
            partes.append(f"{item_limpo} [{data_diario}]")
            alterou = True
        else:
            partes.append(item_limpo)

    return " | ".join(partes) if alterou else value


def load_matrix(workbook: Path) -> pd.DataFrame:
    parquet_path = dashboard_cache_path("matriz_cisp.parquet")
    if cache_is_fresh(parquet_path, workbook):
        return pd.read_parquet(parquet_path)

    if not workbook.exists():
        raise FileNotFoundError(f"Workbook nao encontrado: {workbook}")
    df = pd.read_excel(workbook, sheet_name="Matriz_CISP")
    df.columns = [str(col) for col in df.columns]
    if "CISP" in df.columns:
        df["CISP"] = pd.to_numeric(df["CISP"], errors="coerce").astype("Int64").astype(str)
    for col in df.columns:
        if col != "CISP":
            df[col] = df[col].map(incluir_data_diario_na_celula)
    return df


MATRIX = load_matrix(ARGS.workbook)
MATRIX_DATE_COLS = [col for col in MATRIX.columns if col != "CISP"]

PAGE_CSS = """
body { margin: 0; background: #f4f6f8; color: #17212b; font-family: Arial, sans-serif; }
.page { padding: 18px; }
.title-row { display: flex; align-items: end; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
h1 { margin: 0; font-size: 24px; font-weight: 700; letter-spacing: 0; }
.source { color: #52616f; font-size: 12px; max-width: 760px; }
.filters { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; align-items: end; }
.filter label { display: block; color: #43515e; font-size: 12px; font-weight: 700; margin-bottom: 5px; }
.filter .Select-control { min-height: 36px; height: 36px; border-color: #cfd8e3; }
.filter .Select-placeholder,
.filter .Select--single > .Select-control .Select-value { line-height: 34px; }
.filter .Select-multi-value-wrapper { max-height: 34px; overflow: hidden; }
.filter .Select-input { height: 34px; }
.filter .Select-input > input { line-height: 20px; padding: 7px 0; }
.filter .Select-value { margin-top: 4px; max-width: calc(100% - 18px); }
.filter .dash-dropdown { min-width: 0; }
.segmented-control { display: flex; align-items: center; min-height: 36px; padding: 0 8px; border: 1px solid #cfd8e3; border-radius: 6px; background: white; overflow: hidden; }
.segmented-control label { margin: 0 10px 0 0; font-size: 12px; font-weight: 600; color: #23303b; white-space: nowrap; }
.segmented-control input { margin-right: 4px; }
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 12px; }
.kpi { background: white; border: 1px solid #d9e0e7; border-radius: 6px; padding: 12px 14px; }
.kpi-label { color: #5b6a78; font-size: 12px; font-weight: 700; }
.kpi-value { font-size: 25px; font-weight: 700; margin-top: 3px; }
.grid { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(360px, .9fr); gap: 12px; align-items: start; }
.map-pair { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; align-items: stretch; }
.map-pair .panel { min-width: 0; }
.panel { background: white; border: 1px solid #d9e0e7; border-radius: 6px; padding: 10px; }
.charts { display: grid; grid-template-columns: 1fr; gap: 12px; }
.table-wrap { max-height: 520px; overflow: auto; }
.data-table { border-collapse: collapse; width: 100%; min-width: 980px; table-layout: fixed; font-size: 12px; }
.data-table th { position: sticky; top: 0; background: #eef2f6; text-align: left; padding: 7px; border-bottom: 1px solid #cfd8e3; }
.data-table td { padding: 7px; border-bottom: 1px solid #e4e9ef; vertical-align: top; white-space: normal; overflow-wrap: anywhere; word-break: normal; line-height: 1.35; }
.data-table td.long-text { max-height: 96px; overflow: hidden; }
.matrix-table { border-collapse: collapse; width: max-content; min-width: 100%; font-size: 11px; }
.matrix-table th { position: sticky; top: 0; z-index: 2; background: #eef2f6; padding: 7px; border: 1px solid #d5dde6; white-space: nowrap; }
.matrix-table th:first-child { left: 0; z-index: 3; }
.matrix-table td { max-width: 220px; min-width: 105px; padding: 6px; border: 1px solid #e2e7ee; vertical-align: top; }
.matrix-table td:first-child { position: sticky; left: 0; z-index: 1; background: #f8fafc; min-width: 58px; font-weight: 700; text-align: center; }
.matrix-hit { background: #fff1d6; color: #23303b; }
.matrix-empty { background: white; color: #9aa5b1; }
.tab-shell { margin-top: 8px; }
.slider-panel { background: white; border: 1px solid #d9e0e7; border-radius: 6px; padding: 14px 18px 18px; margin-bottom: 12px; }
.slider-title { display: flex; justify-content: space-between; gap: 12px; color: #43515e; font-size: 12px; font-weight: 700; margin-bottom: 8px; }
.section-note { color: #5b6a78; font-size: 12px; margin: -4px 0 10px; }
.table-section { margin-top: 12px; }
.table-section:first-child { margin-top: 0; }
@media (max-width: 1100px) {
    .filters, .grid, .map-pair, .kpis { grid-template-columns: 1fr; }
}
"""


def dropdown_options(values: list[object]) -> list[dict[str, object]]:
    return [{"label": str(value), "value": value} for value in values if pd.notna(value)]


def filter_data(
    anos: list[int] | None,
    tipos: list[str] | None,
    acoes: list[str] | None,
    normas: list[str] | None,
    texto: str | None,
) -> pd.DataFrame:
    df = DF.copy()
    if anos:
        df = df[df["ano_norma"].isin(anos)]
    if tipos:
        df = df[df["unidade_tipo"].isin(tipos)]
    if acoes:
        df = df[df["acao_detectada"].isin(acoes)]
    if normas:
        df = df[df["norma_id"].isin(normas)]
    if texto:
        needle = normalize_text(texto)
        haystack = (
            df["norma_id"].map(normalize_text)
            + " "
            + df["ementa_limpa"].map(normalize_text)
            + " "
            + df["o_que_mudou"].map(normalize_text)
        )
        df = df[haystack.str.contains(re.escape(needle), na=False)]
    return df


def municipality_frame(df: pd.DataFrame) -> pd.DataFrame:
    municipios = df[df["unidade_tipo"] == "MUNICIPIO"].copy()
    geojson = load_municipality_geojson()
    nomes = {
        feature["properties"]["nome_norm"]: (feature["properties"]["codarea"], feature["properties"]["nome"])
        for feature in geojson.get("features", [])
    }
    if municipios.empty:
        return pd.DataFrame(columns=["codarea", "municipio", "normativas", "unidades", "normas"])

    municipios["codarea"] = municipios["municipio_norm"].map(lambda value: nomes.get(value, ("", ""))[0])
    municipios["municipio"] = municipios["municipio_norm"].map(lambda value: nomes.get(value, ("", value.title()))[1])
    municipios = municipios[municipios["codarea"] != ""]
    if municipios.empty:
        return pd.DataFrame(columns=["codarea", "municipio", "normativas", "unidades", "normas"])

    grouped = (
        municipios.groupby(["codarea", "municipio"], as_index=False)
        .agg(
            normativas=("norma_id", "nunique"),
            unidades=("unidade_nome", "count"),
            normas=("norma_id", lambda values: " | ".join(sorted(set(map(str, values)))[:8])),
        )
        .sort_values(["normativas", "municipio"], ascending=[False, True])
    )
    return grouped


def unit_boundary_frame(df: pd.DataFrame) -> pd.DataFrame:
    boundary = load_boundary_geojson()
    if boundary is None:
        return pd.DataFrame(columns=["unidade_numero_norm", "unidade", "normativas", "normas"])
    units = df[df["unidade_tipo"] == ARGS.boundary_type].copy()
    if units.empty:
        return pd.DataFrame(columns=["unidade_numero_norm", "unidade", "normativas", "normas"])
    return (
        units.groupby("unidade_numero_norm", as_index=False)
        .agg(
            normativas=("norma_id", "nunique"),
            unidade=("unidade_numero_norm", lambda values: f"{ARGS.boundary_type} {values.iloc[0]}"),
            normas=("norma_id", lambda values: " | ".join(sorted(set(map(str, values)))[:8])),
        )
        .sort_values("normativas", ascending=False)
    )


def empty_map(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title=title,
        mapbox={"style": "carto-positron", "center": {"lat": -22.4, "lon": -43.4}, "zoom": 6.4},
        margin={"l": 0, "r": 0, "t": 44, "b": 0},
        height=620,
        annotations=[
            {
                "text": "Sem feicoes geograficas para os filtros selecionados.",
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
            }
        ],
    )
    return fig


def make_municipality_map(df: pd.DataFrame) -> go.Figure:
    geojson = load_municipality_geojson()
    data = municipality_frame(df)
    if data.empty:
        return empty_map("Municipios citados nas normativas")
    fig = px.choropleth_map(
        data,
        geojson=geojson,
        locations="codarea",
        featureidkey="properties.codarea",
        color="normativas",
        hover_name="municipio",
        hover_data={"codarea": False, "normativas": True, "unidades": True, "normas": True},
        color_continuous_scale="YlOrRd",
        center={"lat": -22.4, "lon": -43.4},
        zoom=5.4,
        opacity=0.7,
        height=620,
    )
    fig.update_layout(
        title="Municipios citados nas normativas",
        coloraxis_colorbar={"title": "Normas"},
        margin={"l": 0, "r": 0, "t": 44, "b": 0},
    )
    return fig


def make_boundary_map(df: pd.DataFrame) -> go.Figure:
    boundary = load_boundary_geojson()
    data = unit_boundary_frame(df)
    if boundary is None:
        return empty_map("GeoJSON de CISP/AISP/RISP nao informado")
    if data.empty:
        return empty_map(f"{ARGS.boundary_type} nas normativas")
    fig = px.choropleth_map(
        data,
        geojson=boundary,
        locations="unidade_numero_norm",
        featureidkey="properties.unidade_numero_norm",
        color="normativas",
        hover_name="unidade",
        hover_data={"unidade_numero_norm": False, "normativas": True, "normas": True},
        color_continuous_scale="YlGnBu",
        center={"lat": -22.4, "lon": -43.4},
        zoom=6.4,
        opacity=0.65,
        height=620,
    )
    fig.update_layout(
        title=f"{ARGS.boundary_type} nas normativas",
        coloraxis_colorbar={"title": "Normas"},
        margin={"l": 0, "r": 0, "t": 44, "b": 0},
    )
    return fig


def make_timeline(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()
    data = (
        df.dropna(subset=["data_norma"])
        .groupby([pd.Grouper(key="data_norma", freq="YS"), "acao_detectada"], as_index=False)
        .agg(normativas=("norma_id", "nunique"))
    )
    fig = px.bar(data, x="data_norma", y="normativas", color="acao_detectada", barmode="stack")
    fig.update_layout(
        title="Normativas por ano e acao detectada",
        xaxis_title="Ano",
        yaxis_title="Normativas",
        legend_title="Acao",
        margin={"l": 40, "r": 12, "t": 48, "b": 36},
        height=330,
    )
    return fig


def make_unit_bar(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()
    data = (
        df.groupby("unidade_tipo", as_index=False)
        .agg(registros=("norma_id", "count"), normativas=("norma_id", "nunique"))
        .sort_values("registros", ascending=False)
    )
    fig = px.bar(data, x="unidade_tipo", y="registros", color="normativas", text="registros")
    fig.update_layout(
        title="Registros por tipo de unidade",
        xaxis_title="Tipo",
        yaxis_title="Registros",
        coloraxis_colorbar={"title": "Normas"},
        margin={"l": 40, "r": 12, "t": 48, "b": 36},
        height=330,
    )
    return fig


def make_table(df: pd.DataFrame) -> html.Table:
    cols = ["data_norma", "norma_id", "unidade_tipo", "unidade_numero", "unidade_nome", "acao_detectada", "mudanca_curta"]
    view = df.sort_values(["data_norma", "norma_id"], ascending=[False, True]).head(80).copy()
    view["data_norma"] = view["data_norma"].dt.strftime("%Y-%m-%d").fillna("")
    header = html.Thead(html.Tr([html.Th(col) for col in cols]))
    body = html.Tbody(
        [
            html.Tr([html.Td(row[col]) for col in cols])
            for _, row in view[cols].fillna("").iterrows()
        ]
    )
    return html.Table([header, body], className="data-table")


def matrix_slider_marks() -> dict[int, str]:
    if not MATRIX_DATE_COLS:
        return {}
    marks = {}
    last = len(MATRIX_DATE_COLS)
    for idx, col in enumerate(MATRIX_DATE_COLS):
        year = pd.to_datetime(col, errors="coerce").year
        pos = idx + 1
        if pos in {1, last} or (pos - 1) % 5 == 0:
            marks[pos] = str(year)
    return marks


def matrix_for_period(anos: list[int] | None, periodo: list[int] | None) -> pd.DataFrame:
    matrix = MATRIX.copy()
    date_cols = MATRIX_DATE_COLS.copy()
    if periodo and len(periodo) == 2 and date_cols:
        start = max(1, min(int(periodo[0]), len(date_cols))) - 1
        end = max(1, min(int(periodo[1]), len(date_cols))) - 1
        if start > end:
            start, end = end, start
        date_cols = date_cols[start : end + 1]

    if anos:
        anos_set = set(anos)
        date_cols = [col for col in date_cols if pd.to_datetime(col, errors="coerce").year in anos_set]

    keep = ["CISP"] + date_cols
    return matrix[keep] if len(keep) > 1 else matrix[["CISP"]]


def make_matrix_heatmap(matrix: pd.DataFrame) -> go.Figure:
    date_cols = [col for col in matrix.columns if col != "CISP"]
    if not date_cols:
        return go.Figure().update_layout(
            title="Matriz CISP sem colunas para os filtros selecionados",
            height=360,
            margin={"l": 40, "r": 12, "t": 48, "b": 36},
        )

    presence = matrix[date_cols].notna().astype(int)
    fig = go.Figure(
        data=[
            go.Heatmap(
                z=presence.values,
                x=date_cols,
                y=matrix["CISP"].astype(str),
                colorscale=[[0, "#f7f9fb"], [1, "#d65f21"]],
                showscale=False,
                xgap=2,
                ygap=1,
                hovertemplate="CISP %{y}<br>Data %{x}<br>Marcacao: %{z}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="Matriz CISP - celulas preenchidas",
        height=430,
        margin={"l": 48, "r": 12, "t": 48, "b": 80},
    )
    fig.update_xaxes(
        title="Data da norma",
        type="category",
        categoryorder="array",
        categoryarray=date_cols,
        tickangle=-45,
    )
    fig.update_yaxes(title="CISP", type="category")
    return fig


def make_matrix_table(matrix: pd.DataFrame) -> html.Table:
    header = html.Thead(html.Tr([html.Th(col) for col in matrix.columns]))
    rows = []
    for _, row in matrix.fillna("").iterrows():
        cells = []
        for col in matrix.columns:
            value = row[col]
            class_name = "matrix-hit" if col != "CISP" and str(value).strip() else "matrix-empty"
            if col == "CISP":
                class_name = ""
            cells.append(html.Td(safe_text(value, 140), className=class_name))
        rows.append(html.Tr(cells))
    return html.Table([header, html.Tbody(rows)], className="matrix-table")


def make_matrix_summary(matrix: pd.DataFrame) -> html.Div:
    date_cols = [col for col in matrix.columns if col != "CISP"]
    filled = int(matrix[date_cols].notna().sum().sum()) if date_cols else 0
    units = int((matrix[date_cols].notna().sum(axis=1) > 0).sum()) if date_cols else 0
    return html.Div(
        [
            html.Div([html.Div("CISP na matriz", className="kpi-label"), html.Div(str(len(matrix)), className="kpi-value")], className="kpi"),
            html.Div([html.Div("Datas", className="kpi-label"), html.Div(str(len(date_cols)), className="kpi-value")], className="kpi"),
            html.Div([html.Div("Celulas preenchidas", className="kpi-label"), html.Div(str(filled), className="kpi-value")], className="kpi"),
            html.Div([html.Div("CISP com marcacao", className="kpi-label"), html.Div(str(units), className="kpi-value")], className="kpi"),
        ],
        className="kpis",
    )


def make_kpis(df: pd.DataFrame) -> list[html.Div]:
    values = [
        ("Normativas", df["norma_id"].nunique()),
        ("Registros", len(df)),
        ("CISP", df.loc[df["unidade_tipo"] == "CISP", "unidade_numero_norm"].replace("", pd.NA).nunique()),
        ("Municipios mapeados", len(municipality_frame(df))),
    ]
    return [
        html.Div([html.Div(label, className="kpi-label"), html.Div(f"{value:,}".replace(",", "."), className="kpi-value")], className="kpi")
        for label, value in values
    ]


def make_territory_kpis(layer: str, df: pd.DataFrame) -> list[html.Div]:
    if "RISP" in df.columns:
        risp_qtd = df["RISP"].nunique()
    elif "risp" in df.columns:
        risp_qtd = len(set(", ".join(df["risp"].astype(str)).replace(" ", "").split(",")) - {""})
    elif layer == "RISP":
        risp_qtd = len(df)
    else:
        risp_qtd = 0

    values = [
        (f"{layer} visiveis", len(df)),
        ("CISP abrangidas", int(df["cisp_qtd"].sum()) if "cisp_qtd" in df.columns else len(df)),
        ("Municipios", int(df["municipios_qtd"].sum()) if "municipios_qtd" in df.columns else 0),
        ("RISP", risp_qtd),
    ]
    return [
        html.Div([html.Div(label, className="kpi-label"), html.Div(f"{value:,}".replace(",", "."), className="kpi-value")], className="kpi")
        for label, value in values
    ]


def make_territory_map(layer: str, df: pd.DataFrame) -> go.Figure:
    geojson = load_grouped_territory_geojson(layer)
    if df.empty:
        return empty_map(f"{layer} - divisao territorial ISP")

    hover_data = {"id": False, "numero": False}
    for col in ["RISP", "AISP", "risp", "aisp", "cisp", "cisp_qtd", "municipios_qtd", "municipios", "regioes", "unidade_territorial"]:
        if col in df.columns:
            hover_data[col] = True

    fig = px.choropleth_map(
        df,
        geojson=geojson,
        locations="id",
        featureidkey="properties.id",
        color="numero",
        hover_name="label",
        hover_data=hover_data,
        color_continuous_scale="Viridis",
        center={"lat": -22.15, "lon": -42.65},
        zoom=6.35,
        opacity=0.72,
        height=560,
    )
    fig.update_layout(
        title=f"{layer} - divisao territorial da seguranca publica",
        coloraxis_colorbar={"title": layer},
        margin={"l": 0, "r": 0, "t": 44, "b": 0},
    )
    return fig


def make_change_timeline_map(layer: str, df: pd.DataFrame, normas: list[str] | None = None) -> go.Figure:
    geojson = load_grouped_territory_geojson(layer)
    timeline = timeline_events_for_layer(layer, df, normas)
    if timeline.empty:
        return empty_map("Linha do tempo sem eventos para a selecao")

    timeline = timeline.copy()
    timeline["normas_hover"] = timeline["normas"].map(lambda value: wrap_hover_text(value, 56, 520))
    timeline["acoes_hover"] = timeline["acoes"].map(lambda value: wrap_hover_text(value, 44, 260))
    timeline["historia_hover"] = timeline["historia"].map(lambda value: wrap_hover_text(value, 62, 620))

    max_events = max(1, int(timeline["eventos"].max()))
    fig = px.choropleth_map(
        timeline,
        geojson=geojson,
        locations="id",
        featureidkey="properties.id",
        color="eventos",
        animation_frame="data_label",
        hover_name="label",
        hover_data={
            "id": False,
            "numero": False,
            "data_norma": False,
            "data_label": True,
            "eventos": True,
            "cisp_afetadas": True,
            "acoes_hover": True,
            "normas_hover": True,
            "unidades_origem": True,
            "historia_hover": True,
        },
        labels={
            "data_label": "Data",
            "eventos": "Normas",
            "cisp_afetadas": "CISP afetadas",
            "acoes_hover": "Acoes",
            "normas_hover": "Normas",
            "unidades_origem": "Unidades origem",
            "historia_hover": "Resumo",
        },
        color_continuous_scale=[[0, "#edf2f7"], [0.01, "#f7c66a"], [1, "#b8321f"]],
        range_color=(0, max_events),
        center={"lat": -22.15, "lon": -42.65},
        zoom=6.35,
        opacity=0.76,
        height=560,
    )
    fig.update_layout(
        title="Linha do tempo das mudancas territoriais detectadas",
        coloraxis_colorbar={"title": "Eventos"},
        hoverlabel={"align": "left", "font_size": 12},
        margin={"l": 0, "r": 0, "t": 44, "b": 0},
    )
    fig.update_traces(marker_line_width=0.7, marker_line_color="#ffffff")
    return fig


def make_timeline_story_table(layer: str, df: pd.DataFrame, normas: list[str] | None = None) -> html.Div:
    timeline = timeline_events_for_layer(layer, df, normas)
    if timeline.empty:
        return html.Div("Sem eventos territoriais para a selecao atual.", className="section-note")

    events = timeline[timeline["eventos"].gt(0)].copy()
    if events.empty:
        return html.Div("Sem eventos territoriais para a selecao atual.", className="section-note")

    normas_view = (
        events[["data_label", "normas", "acoes"]]
        .drop_duplicates()
        .sort_values("data_label", ascending=False)
        .head(12)
        .copy()
    )
    normas_view = normas_view.rename(columns={"data_label": "data", "normas": "norma", "acoes": "acoes"})

    view = (
        events.sort_values(["data_norma", "eventos"], ascending=[False, False])
        .head(18)
        .copy()
    )
    columns = ["data_label", "label", "eventos", "cisp_afetadas", "acoes", "normas", "historia"]
    labels = {
        "data_label": "Data",
        "label": "Territorio",
        "eventos": "Eventos",
        "cisp_afetadas": "CISP afetadas",
        "acoes": "Acoes",
        "normas": "Normas",
        "historia": "O que aconteceu",
    }
    return html.Div(
        [
            html.H3("Normas na linha do tempo"),
            html.Div(
                "Normas que geram eventos territoriais na selecao atual.",
                className="section-note",
            ),
            make_html_table(
                normas_view,
                ["data", "norma", "acoes"],
                {"data": "Data", "norma": "Norma", "acoes": "Acoes"},
                limit=300,
            ),
            html.H3("Historias recentes detectadas"),
            html.Div(
                "Eventos extraidos das normas e projetados sobre a malha territorial atual.",
                className="section-note",
            ),
            make_html_table(view, columns, labels, limit=360),
        ]
    )


def make_html_table(df: pd.DataFrame, columns: list[str], labels: dict[str, str], limit: int = 260) -> html.Table:
    cols = [col for col in columns if col in df.columns]
    header = html.Thead(html.Tr([html.Th(labels.get(col, col)) for col in cols]))
    body = html.Tbody(
        [
            html.Tr(
                [
                    html.Td(
                        safe_text(row[col], limit),
                        className="long-text" if len(str(row[col])) > 90 else "",
                    )
                    for col in cols
                ]
            )
            for _, row in df[cols].fillna("").iterrows()
        ]
    )
    return html.Table([header, body], className="data-table")


def selected_cisp_detail(layer: str, df: pd.DataFrame) -> pd.DataFrame:
    rel = load_territory_relation().copy()
    layer = layer.upper()

    if df.empty:
        return rel.iloc[0:0].copy()

    selected = set(df["id"].astype(str))
    if layer == "RISP":
        rel = rel[rel["RISP"].astype(str).isin(selected)]
    elif layer == "AISP":
        rel = rel[rel["AISP"].astype(str).isin(selected)]
    elif layer == "REGIAO":
        rel = rel[rel["Região de Governo"].astype(str).isin(selected)]
    else:
        rel = rel[rel["CISP"].astype(str).isin(selected)]

    rel["numero_cisp"] = pd.to_numeric(rel["CISP"], errors="coerce")
    return rel.sort_values(["RISP", "AISP", "numero_cisp"]).drop(columns=["numero_cisp"])


def make_territory_table(layer: str, df: pd.DataFrame) -> html.Div:
    base_cols = {
        "REGIAO": ["id", "risp", "aisp", "cisp_qtd", "municipios_qtd", "municipios"],
        "RISP": ["id", "aisp", "cisp_qtd", "municipios_qtd", "municipios", "regioes"],
        "AISP": ["RISP", "id", "cisp", "cisp_qtd", "municipios_qtd", "municipios", "regioes"],
        "CISP": ["RISP", "AISP", "id", "unidade_territorial", "municipios", "regioes"],
    }
    labels = {
        "id": layer,
        "aisp": "AISP abrangidas",
        "risp": "RISP abrangidas",
        "cisp": "CISP abrangidas",
        "cisp_qtd": "Qtd. CISP",
        "municipios_qtd": "Qtd. municipios",
        "municipios": "Municipios",
        "regioes": "Regiao de governo",
        "unidade_territorial": "Unidade territorial",
        "RISP": "RISP",
        "AISP": "AISP",
        "CISP": "CISP",
        "Unidade Territorial": "Unidade territorial",
        "Município": "Municipio",
        "Região de Governo": "Regiao de governo",
    }
    view = df.sort_values("numero").copy()
    cisp_detail = selected_cisp_detail(layer, df)
    detail_cols = ["RISP", "AISP", "CISP", "Unidade Territorial", "Município", "Região de Governo"]

    sections = [
        html.Div(
            [
                html.H3(f"{layer} filtradas"),
                html.Div(
                    f"{len(view)} territorio(s) na camada selecionada. "
                    f"{len(cisp_detail)} CISP detalhada(s) dentro da selecao.",
                    className="section-note",
                ),
                make_html_table(view, base_cols[layer], labels),
            ],
            className="table-section",
        )
    ]

    if layer != "CISP":
        sections.append(
            html.Div(
                [
                    html.H3("CISP dentro da selecao"),
                    html.Div(
                        "Detalhamento da hierarquia territorial usada para compor a camada do mapa.",
                        className="section-note",
                    ),
                    make_html_table(cisp_detail, detail_cols, labels, limit=320),
                ],
                className="table-section",
            )
        )

    return html.Div(sections)


def create_territory_layout() -> html.Div:
    rel = load_territory_relation()
    risp_options = dropdown_options(sorted(rel["RISP"].dropna().unique(), key=lambda x: int(x)))
    aisp_options = dropdown_options(sorted(rel["AISP"].dropna().unique(), key=lambda x: int(x)))
    cisp_options = dropdown_options(sorted(rel["CISP"].dropna().unique(), key=lambda x: int(x)))
    regiao_options = dropdown_options(sorted(rel["Região de Governo"].dropna().unique()))
    norma_options = territorial_norm_options()
    slider_max = max(1, len(MATRIX_DATE_COLS))

    return html.Div(
        [
            html.Div(
                [
                    html.H1("ISP - Territorios RISP/AISP/CISP"),
                    html.Div(
                        "Fontes: Relacao RISP x AISP x CISP e KMLs oficiais do ISP/Dados Abertos RJ.",
                        className="source",
                    ),
                ],
                className="title-row",
            ),
            dcc.Tabs(
                id="abas-dashboard",
                value="territorios",
                className="tab-shell",
                children=[
                    dcc.Tab(
                        label="Territorios",
                        value="territorios",
                        children=[
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Label("Camada"),
                                            dcc.RadioItems(
                                                id="territorio-camada",
                                                options=[
                                                    {"label": "Regiao", "value": "REGIAO"},
                                                    {"label": "RISP", "value": "RISP"},
                                                    {"label": "AISP", "value": "AISP"},
                                                    {"label": "CISP", "value": "CISP"},
                                                ],
                                                value="REGIAO",
                                                inline=True,
                                                className="segmented-control",
                                            ),
                                        ],
                                        className="filter",
                                    ),
                                    html.Div([html.Label("Regiao"), dcc.Dropdown(id="territorio-regiao", options=regiao_options, multi=True)], className="filter"),
                                    html.Div([html.Label("RISP"), dcc.Dropdown(id="territorio-risp", options=risp_options, multi=True)], className="filter"),
                                    html.Div([html.Label("AISP"), dcc.Dropdown(id="territorio-aisp", options=aisp_options, multi=True)], className="filter"),
                                    html.Div([html.Label("CISP"), dcc.Dropdown(id="territorio-cisp", options=cisp_options, multi=True)], className="filter"),
                                    html.Div([html.Label("Norma"), dcc.Dropdown(id="territorio-norma", options=norma_options, multi=True)], className="filter"),
                                    html.Div([html.Label("Busca territorial"), dcc.Input(id="territorio-busca", type="text", debounce=True, placeholder="Ex.: Paqueta, Niteroi, 26", style={"width": "100%", "height": "36px", "boxSizing": "border-box"})], className="filter"),
                                ],
                                className="filters",
                            ),
                            html.Div(id="territorio-kpis", className="kpis"),
                            html.Div(
                                [
                                    html.Div(
                                        [dcc.Graph(id="territorio-mapa", config={"displayModeBar": True, "scrollZoom": True})],
                                        className="panel",
                                    ),
                                    html.Div(
                                        [dcc.Graph(id="territorio-timeline-mapa", config={"displayModeBar": True, "scrollZoom": True})],
                                        className="panel",
                                    ),
                                ],
                                className="map-pair",
                            ),
                            html.Div([html.Div(id="territorio-timeline-historias", className="table-wrap")], className="panel", style={"marginTop": "12px"}),
                            html.Div([html.Div(id="territorio-tabela", className="table-wrap")], className="panel", style={"marginTop": "12px"}),
                        ],
                    ),
                    dcc.Tab(
                        label="Matriz CISP",
                        value="matriz",
                        children=[
                            html.Div(id="matriz-resumo", style={"marginTop": "12px"}),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Span("Janela temporal da matriz"),
                                            html.Span(id="matriz-periodo-label"),
                                        ],
                                        className="slider-title",
                                    ),
                                    dcc.RangeSlider(
                                        id="matriz-periodo",
                                        min=1,
                                        max=slider_max,
                                        step=1,
                                        value=[1, slider_max],
                                        marks=matrix_slider_marks(),
                                        allowCross=False,
                                        tooltip={"placement": "bottom", "always_visible": False},
                                        updatemode="drag",
                                    ),
                                ],
                                className="slider-panel",
                            ),
                            html.Div([dcc.Graph(id="matriz-heatmap", config={"displayModeBar": True})], className="panel"),
                            html.Div([html.H3("Matriz CISP"), html.Div(id="matriz-tabela", className="table-wrap")], className="panel", style={"marginTop": "12px"}),
                        ],
                    ),
                ],
            ),
        ],
        className="page",
    )


def create_layout() -> html.Div:
    return create_territory_layout()

    anos = sorted(int(value) for value in DF["ano_norma"].dropna().unique())
    tipos = sorted(DF["unidade_tipo"].dropna().unique())
    acoes = sorted(DF["acao_detectada"].dropna().unique())
    normas = sorted(DF["norma_id"].dropna().unique())
    map_options = [{"label": "Municipios IBGE", "value": "municipio"}]
    slider_min = 1
    slider_max = max(1, len(MATRIX_DATE_COLS))
    if ARGS.boundary_geojson:
        map_options.append({"label": f"{ARGS.boundary_type} GeoJSON", "value": "boundary"})

    return html.Div(
        [
            dcc.Store(id="filtered-count"),
            html.Div(
                [
                    html.Div(
                        [
                            html.H1("ISP - Normativas de area de atuacao"),
                            html.Div(
                                f"Base: {ARGS.workbook} | referencia municipal: malha IBGE RJ",
                                className="source",
                            ),
                        ],
                        className="title-row",
                    ),
                    html.Div(
                        [
                            html.Div([html.Label("Ano"), dcc.Dropdown(id="filtro-ano", options=dropdown_options(anos), multi=True)], className="filter"),
                            html.Div([html.Label("Tipo de unidade"), dcc.Dropdown(id="filtro-tipo", options=dropdown_options(tipos), multi=True)], className="filter"),
                            html.Div([html.Label("Acao"), dcc.Dropdown(id="filtro-acao", options=dropdown_options(acoes), multi=True)], className="filter"),
                            html.Div([html.Label("Norma"), dcc.Dropdown(id="filtro-norma", options=dropdown_options(normas), multi=True)], className="filter"),
                            html.Div([html.Label("Busca textual"), dcc.Input(id="busca-texto", type="text", debounce=True, placeholder="Ex.: Riocentro, 26 DP, revogacao", style={"width": "100%", "height": "36px"})], className="filter"),
                        ],
                        className="filters",
                    ),
                    html.Div(id="kpis", className="kpis"),
                    dcc.Tabs(
                        id="abas-dashboard",
                        value="mapa",
                        className="tab-shell",
                        children=[
                            dcc.Tab(
                                label="Mapa e registros",
                                value="mapa",
                                children=[
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Div([html.Label("Mapa"), dcc.RadioItems(id="mapa-tipo", options=map_options, value="municipio", inline=True)]),
                                                    dcc.Graph(
                                                        id="mapa",
                                                        config={
                                                            "displayModeBar": True,
                                                            "scrollZoom": True,
                                                        },
                                                    ),
                                                ],
                                                className="panel",
                                            ),
                                            html.Div(
                                                [
                                                    html.Div(className="charts", children=[dcc.Graph(id="timeline"), dcc.Graph(id="barra-unidades")]),
                                                ],
                                                className="charts",
                                            ),
                                        ],
                                        className="grid",
                                    ),
                                    html.Div([html.H3("Registros filtrados"), html.Div(id="tabela", className="table-wrap")], className="panel", style={"marginTop": "12px"}),
                                ],
                            ),
                            dcc.Tab(
                                label="Matriz CISP",
                                value="matriz",
                                children=[
                                    html.Div(id="matriz-resumo", style={"marginTop": "12px"}),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Span("Janela temporal da matriz"),
                                                    html.Span(id="matriz-periodo-label"),
                                                ],
                                                className="slider-title",
                                            ),
                                            dcc.RangeSlider(
                                                id="matriz-periodo",
                                                min=slider_min,
                                                max=slider_max,
                                                step=1,
                                                value=[slider_min, slider_max],
                                                marks=matrix_slider_marks(),
                                                allowCross=False,
                                                tooltip={"placement": "bottom", "always_visible": False},
                                                updatemode="drag",
                                            ),
                                        ],
                                        className="slider-panel",
                                    ),
                                    html.Div([dcc.Graph(id="matriz-heatmap", config={"displayModeBar": True})], className="panel"),
                                    html.Div([html.H3("Matriz CISP"), html.Div(id="matriz-tabela", className="table-wrap")], className="panel", style={"marginTop": "12px"}),
                                ],
                            ),
                        ],
                    ),
                ],
                className="page",
            ),
        ]
    )


app = Dash(__name__)
server = app.server
app.title = "ISP - Normativas de area de atuacao"
app.index_string = f"""
<!DOCTYPE html>
<html>
    <head>
        {{%metas%}}
        <title>{{%title%}}</title>
        {{%favicon%}}
        {{%css%}}
        <style>{PAGE_CSS}</style>
    </head>
    <body>
        {{%app_entry%}}
        <footer>
            {{%config%}}
            {{%scripts%}}
            {{%renderer%}}
        </footer>
    </body>
</html>
"""
app.layout = create_layout()


@app.callback(
    Output("territorio-kpis", "children"),
    Output("territorio-mapa", "figure"),
    Output("territorio-timeline-mapa", "figure"),
    Output("territorio-timeline-historias", "children"),
    Output("territorio-tabela", "children"),
    Input("territorio-camada", "value"),
    Input("territorio-regiao", "value"),
    Input("territorio-risp", "value"),
    Input("territorio-aisp", "value"),
    Input("territorio-cisp", "value"),
    Input("territorio-norma", "value"),
    Input("territorio-busca", "value"),
)
def update_dashboard(camada, regioes, risp, aisp, cisp, normas, texto):
    camada = camada or "REGIAO"
    df = filter_territory(camada, risp, aisp, cisp, regioes, texto)
    return (
        make_territory_kpis(camada, df),
        make_territory_map(camada, df),
        make_change_timeline_map(camada, df, normas),
        make_timeline_story_table(camada, df, normas),
        make_territory_table(camada, df),
    )


@app.callback(
    Output("matriz-resumo", "children"),
    Output("matriz-periodo-label", "children"),
    Output("matriz-heatmap", "figure"),
    Output("matriz-tabela", "children"),
    Input("matriz-periodo", "value"),
)
def update_matrix(matriz_periodo):
    matrix = matrix_for_period(None, matriz_periodo)
    date_cols = [col for col in matrix.columns if col != "CISP"]
    periodo_label = f"{date_cols[0]} ate {date_cols[-1]}" if date_cols else "sem datas no filtro"
    return (
        make_matrix_summary(matrix),
        periodo_label,
        make_matrix_heatmap(matrix),
        make_matrix_table(matrix),
    )


def main() -> None:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    app.run(host=ARGS.host, port=ARGS.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
