from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "saida"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "saida" / "relatorio_deduplicacao_atos.csv"
DEFAULT_DRY_RUN_REPORT_PATH = PROJECT_ROOT / "saida" / "relatorio_deduplicacao_atos_dry_run.csv"

KEY_FIELDS = [
    "data_publicacao",
    "caderno",
    "tipo_ato",
    "nome",
    "id_funcional",
    "cargo",
    "orgao",
]


def normalize_key_piece(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\s+", " ", text).strip().upper()
    return text


def row_key(row: dict[str, str], trecho_chars: int) -> tuple[str, ...]:
    key = [normalize_key_piece(row.get(field, "")) for field in KEY_FIELDS]
    key.append(normalize_key_piece(row.get("trecho", ""))[:trecho_chars])
    return tuple(key)


def yearly_csv_paths(input_dir: Path, uf: str | None) -> list[Path]:
    if uf:
        candidates = (input_dir / uf.upper()).glob("*.csv")
    else:
        candidates = input_dir.glob("*/*.csv")
    return sorted(
        path
        for path in candidates
        if path.is_file()
        and path.parent.name.lower() != "analises"
        and re.search(r"_(?:19|20)\d{2}\.csv$", path.name, flags=re.I)
    )


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    temporary_path = path.with_name(f"{path.name}.tmp")
    with temporary_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary_path.replace(path)


def deduplicate_rows(
    rows: list[dict[str, str]],
    trecho_chars: int,
) -> tuple[list[dict[str, str]], int]:
    seen: set[tuple[str, ...]] = set()
    kept: list[dict[str, str]] = []
    removed = 0

    for row in rows:
        key = row_key(row, trecho_chars)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        kept.append(row)

    return kept, removed


def deduplicate_file(path: Path, trecho_chars: int, dry_run: bool) -> dict[str, str | int]:
    fieldnames, rows = read_csv(path)
    missing_fields = [field for field in KEY_FIELDS + ["trecho"] if field not in fieldnames]
    if missing_fields:
        return {
            "arquivo": str(path),
            "linhas_antes": len(rows),
            "linhas_depois": len(rows),
            "duplicatas_removidas": 0,
            "status": f"ignorado: colunas ausentes ({', '.join(missing_fields)})",
        }

    deduplicated_rows, removed = deduplicate_rows(rows, trecho_chars)
    if removed and not dry_run:
        write_csv(path, fieldnames, deduplicated_rows)

    return {
        "arquivo": str(path),
        "linhas_antes": len(rows),
        "linhas_depois": len(deduplicated_rows),
        "duplicatas_removidas": removed,
        "status": "simulado" if dry_run else "atualizado",
    }


def write_report(report_path: Path, results: list[dict[str, str | int]]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "arquivo",
        "linhas_antes",
        "linhas_depois",
        "duplicatas_removidas",
        "status",
    ]
    with report_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deduplica CSVs anuais de atos antes da analise temporal."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Diretorio base dos CSVs anuais. Padrao: saida.",
    )
    parser.add_argument("--uf", default=None, help="Filtra uma UF, por exemplo RJ.")
    parser.add_argument(
        "--trecho-chars",
        type=int,
        default=240,
        help="Quantidade de caracteres normalizados do trecho usada na chave.",
    )
    parser.add_argument(
        "--relatorio",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Caminho do relatorio CSV de deduplicacao.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas calcula duplicatas, sem alterar os CSVs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.dry_run and args.relatorio == DEFAULT_REPORT_PATH:
        args.relatorio = DEFAULT_DRY_RUN_REPORT_PATH
    paths = yearly_csv_paths(args.input_dir, args.uf)
    if not paths:
        print(f"Nenhum CSV anual encontrado em {args.input_dir}.")
        return 0

    results = [
        deduplicate_file(path, trecho_chars=args.trecho_chars, dry_run=args.dry_run)
        for path in paths
    ]
    write_report(args.relatorio, results)

    total_before = sum(int(result["linhas_antes"]) for result in results)
    total_after = sum(int(result["linhas_depois"]) for result in results)
    total_removed = sum(int(result["duplicatas_removidas"]) for result in results)
    mode = "simuladas" if args.dry_run else "removidas"

    print(f"CSVs avaliados: {len(results)}")
    print(f"Linhas antes: {total_before}")
    print(f"Linhas depois: {total_after}")
    print(f"Duplicatas {mode}: {total_removed}")
    print(f"Relatorio: {args.relatorio}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
