from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from diarios_oficiais.base import Edition
from diarios_oficiais.rj_ioerj import (
    RjIoerjCollector,
    parse_acts_from_markdown_file,
)


MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")


def parse_date(value: str) -> date:
    """
    Converte uma string YYYY-MM-DD em date.
    """
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Data inválida: {value!r}. Use o formato YYYY-MM-DD."
        ) from exc


def extrair_data_do_markdown(markdown_path: Path) -> date | None:
    """
    Extrai a data do nome do arquivo Markdown.

    Espera nomes semelhantes a:
        DOERJ_PODER_EXECUTIVO_2026-01-02.md
    """
    match = MARKDOWN_DATE_RE.search(markdown_path.stem)
    if not match:
        return None
    return date.fromisoformat(match.group(1))


def extrair_caderno_do_markdown(markdown_path: Path, collector: RjIoerjCollector) -> str:
    """
    Reconstrói aproximadamente o nome do caderno a partir do nome do arquivo.

    Isso é suficiente para preencher a coluna 'caderno' no CSV local.
    """
    stem = markdown_path.stem

    prefix = f"{collector.gazette_code}_"
    if stem.startswith(prefix):
        stem = stem[len(prefix):]

    match = MARKDOWN_DATE_RE.search(stem)
    if match:
        stem = stem[: match.start()]

    section = stem.replace("_", " ").strip().title()
    return section or "Caderno não identificado"


def processar_markdown_local(
    collector: RjIoerjCollector,
    markdown_path: Path,
) -> tuple[int, int]:
    """
    Lê um Markdown local, extrai atos e grava no CSV anual.

    Retorna:
        (atos_encontrados, atos_novos_gravados)
    """
    publication_date = extrair_data_do_markdown(markdown_path)

    if publication_date is None:
        print(
            f"Não consegui extrair a data do arquivo: {markdown_path}",
            file=sys.stderr,
        )
        return 0, 0

    section = extrair_caderno_do_markdown(markdown_path, collector)

    edition = Edition(
        publication_date=publication_date,
        section=section,
        url="",
    )

    acts = parse_acts_from_markdown_file(
        collector=collector,
        edition=edition,
        markdown_path=markdown_path,
    )

    csv_path = collector.yearly_csv_path_for(publication_date)
    total_novos = collector.write_csv(csv_path, acts)

    print(
        f"{markdown_path.name}: {len(acts)} atos encontrados; "
        f"{total_novos} atos novos gravados em {csv_path}",
        file=sys.stderr,
    )

    return len(acts), total_novos


def listar_markdowns(
    collector: RjIoerjCollector,
    markdown_dir: Path | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Path]:
    """
    Lista arquivos Markdown já existentes no LAKE ou em um diretório informado.
    """
    base_dir = markdown_dir or (collector.lake_dir / collector.state)

    if not base_dir.exists():
        print(f"Diretório não encontrado: {base_dir}", file=sys.stderr)
        return []

    markdowns: list[Path] = []

    for markdown_path in sorted(base_dir.rglob("*.md")):
        publication_date = extrair_data_do_markdown(markdown_path)

        if publication_date is None:
            continue
        if start_date is not None and publication_date < start_date:
            continue
        if end_date is not None and publication_date > end_date:
            continue

        markdowns.append(markdown_path)

    return markdowns


def extrair_atos_rj(
    markdown_dir: Path | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[int, int, int]:
    """
    Extrai nomeações/exonerações de Markdowns locais e grava CSVs anuais.

    Esta etapa NÃO baixa PDF e NÃO consulta a IOERJ.
    Ela apenas processa arquivos .md já existentes.

    Retorna:
        (arquivos_processados, atos_encontrados, atos_novos_gravados)
    """
    collector = RjIoerjCollector()

    markdowns = listar_markdowns(
        collector=collector,
        markdown_dir=markdown_dir,
        start_date=start_date,
        end_date=end_date,
    )

    total_arquivos = 0
    total_atos_encontrados = 0
    total_atos_novos = 0

    for markdown_path in markdowns:
        try:
            atos_encontrados, atos_novos = processar_markdown_local(
                collector=collector,
                markdown_path=markdown_path,
            )
            total_arquivos += 1
            total_atos_encontrados += atos_encontrados
            total_atos_novos += atos_novos

        except Exception as exc:
            print(
                f"Falha ao processar {markdown_path}: {exc}",
                file=sys.stderr,
            )
            continue

    return total_arquivos, total_atos_encontrados, total_atos_novos


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extrai atos de nomeação/exoneração de arquivos Markdown já baixados, "
            "sem acessar a IOERJ."
        )
    )
    parser.add_argument(
        "--markdown-dir",
        type=Path,
        default=None,
        help="Diretório com arquivos .md. Se omitido, usa LAKE/RJ.",
    )
    parser.add_argument(
        "--start-date",
        type=parse_date,
        default=None,
        help="Data inicial no formato YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end-date",
        type=parse_date,
        default=None,
        help="Data final no formato YYYY-MM-DD.",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    total_arquivos, total_atos_encontrados, total_atos_novos = extrair_atos_rj(
        markdown_dir=args.markdown_dir,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    print(
        f"{total_arquivos} arquivos Markdown processados; "
        f"{total_atos_encontrados} atos encontrados; "
        f"{total_atos_novos} atos novos gravados nos CSVs anuais."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
