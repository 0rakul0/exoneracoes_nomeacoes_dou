from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = BASE_DIR / "saida" / "ISP" / "dashboard_cache"


def simplificar_geojson(geojson: dict, tolerance: float = 0.0007) -> dict:
    from shapely.geometry import mapping, shape

    features = []
    for feature in geojson.get("features", []):
        geometry = feature.get("geometry")
        if geometry:
            simplified = shape(geometry).simplify(tolerance, preserve_topology=True)
            feature = dict(feature)
            feature["geometry"] = mapping(simplified)
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    # Importa o painel sem iniciar o servidor; as funcoes dele concentram
    # a leitura e a montagem das camadas territoriais usadas no dashboard.
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    sys.argv = ["painel_normativas_isp.py"]
    from diarios_oficiais.dashboard import painel_normativas_isp as painel

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    outputs: list[Path] = []

    data_path = CACHE_DIR / "o_que_muda_onde.parquet"
    painel.DF.to_parquet(data_path, index=False)
    outputs.append(data_path)

    matrix_path = CACHE_DIR / "matriz_cisp.parquet"
    painel.MATRIX.to_parquet(matrix_path, index=False)
    outputs.append(matrix_path)

    relation_path = CACHE_DIR / "relacao_territorial.parquet"
    painel.load_territory_relation().to_parquet(relation_path, index=False)
    outputs.append(relation_path)

    events_path = CACHE_DIR / "eventos_cisp_expandido.parquet"
    painel.expanded_change_events_cisp().to_parquet(events_path, index=False)
    outputs.append(events_path)

    for layer in ["REGIAO", "RISP", "AISP", "CISP"]:
        geojson = (
            painel.load_territory_geojson("CISP")
            if layer == "CISP"
            else painel.load_grouped_territory_geojson(layer)
        )
        geojson = simplificar_geojson(geojson)
        geojson_path = CACHE_DIR / f"geojson_{layer}.geojson"
        geojson_path.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")
        outputs.append(geojson_path)

    metadata = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "workbook": str(painel.ARGS.workbook),
        "arquivos": [
            {
                "path": str(path),
                "bytes": path.stat().st_size,
            }
            for path in outputs
        ],
    }
    metadata_path = CACHE_DIR / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    outputs.append(metadata_path)

    print("=" * 70)
    print("CACHE DO DASHBOARD ISP")
    print("=" * 70)
    print(f"Pasta: {CACHE_DIR}")
    print("\nArquivos gerados:")
    for path in outputs:
        print(f"- {path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
