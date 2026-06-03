from __future__ import annotations

import argparse
import sys
from datetime import date

from diarios_oficiais.config import RJ_COLLECTION_YEAR
from diarios_oficiais.rj_ioerj import RjIoerjCollector


def parse_date(value: str) -> date:
    """
    Converte uma string YYYY-MM-DD em date.

    Exemplo:
        2026-01-01
    """
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Data inválida: {value!r}. Use o formato YYYY-MM-DD."
        ) from exc


def baixar_markdowns_rj(
    start_date: date | None = None,
    end_date: date | None = None,
    somente_poder_executivo: bool = True,
    pular_anos_completos: bool = True,
) -> int:
    """
    Baixa/converte edições da IOERJ para Markdown.

    Esta etapa NÃO extrai atos e NÃO grava CSV analítico.
    Ela apenas:
        1. consulta as datas disponíveis na IOERJ;
        2. lista as edições de cada data;
        3. filtra o caderno Poder Executivo, se configurado;
        4. baixa o PDF quando necessário;
        5. converte o PDF para Markdown;
        6. salva os arquivos no LAKE.

    Depois rode extrair_atos_rj.py para gerar os CSVs anuais.
    """
    collector = RjIoerjCollector()

    if start_date is None:
        latest_stored_date = collector.latest_stored_publication_date()
        start_date = latest_stored_date or date(RJ_COLLECTION_YEAR, 1, 1)

        if latest_stored_date is None:
            print(
                f"Nenhuma edição RJ encontrada no LAKE; iniciando em {start_date.isoformat()}.",
                file=sys.stderr,
            )
        else:
            print(
                f"Última edição RJ encontrada no LAKE: {latest_stored_date.isoformat()}. "
                f"Retomando a partir dessa data.",
                file=sys.stderr,
            )

    print(f"Coleta de Markdown a partir de {start_date.isoformat()}.", file=sys.stderr)
    if end_date is not None:
        print(f"Data final definida: {end_date.isoformat()}.", file=sys.stderr)

    try:
        available_dates = collector.list_available_dates()
    except Exception as exc:
        raise RuntimeError(f"Falha ao listar datas disponíveis na IOERJ: {exc}") from exc

    dates = sorted(
        publication_date
        for publication_date in available_dates
        if publication_date >= start_date
        and (end_date is None or publication_date <= end_date)
    )

    total_markdowns = 0
    failed_years: set[int] = set()
    skipped_years: set[int] = set()
    active_year: int | None = None
    current_year = date.today().year

    def finalize_year(year: int | None) -> None:
        if year is None:
            return
        if year >= current_year:
            return
        if year in failed_years:
            print(
                f"Não marquei {year} como completo porque houve falhas de coleta.",
                file=sys.stderr,
            )
            return
        collector.mark_year_complete(year)

    for publication_date in dates:
        if pular_anos_completos and collector.is_year_complete(publication_date.year):
            if publication_date.year not in skipped_years:
                print(
                    f"Pulando {publication_date.year}: marcador .year_complete encontrado.",
                    file=sys.stderr,
                )
                skipped_years.add(publication_date.year)
            continue

        if active_year is not None and publication_date.year != active_year:
            finalize_year(active_year)
        active_year = publication_date.year

        try:
            editions = collector.list_editions(publication_date)
        except Exception as exc:
            failed_years.add(publication_date.year)
            print(
                f"Falha ao listar edições de {publication_date.isoformat()}: {exc}",
                file=sys.stderr,
            )
            continue

        if somente_poder_executivo:
            editions = [
                edition
                for edition in editions
                if collector.section_filter.lower() in edition.section.lower()
            ]

        if not editions:
            continue

        print(f"Processando {publication_date.isoformat()}...", file=sys.stderr)

        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)

            try:
                collector.load_or_create_markdown(edition, markdown_path)
                total_markdowns += 1
                print(f"Markdown disponível: {markdown_path}", file=sys.stderr)

            except Exception as exc:
                failed_years.add(publication_date.year)
                collector.record_collection_failure(edition, "baixar_markdown", exc)
                print(
                    f"Falha ao baixar/converter {publication_date.isoformat()} "
                    f"({edition.section}); seguindo para a próxima edição: {exc}",
                    file=sys.stderr,
                )
                continue

    finalize_year(active_year)
    return total_markdowns


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Baixa edições da IOERJ e converte os PDFs para Markdown, "
            "sem extrair nomeações/exonerações."
        )
    )
    parser.add_argument(
        "--start-date",
        type=parse_date,
        default=None,
        help="Data inicial no formato YYYY-MM-DD. Se omitida, retoma da última edição no LAKE ou de RJ_COLLECTION_YEAR.",
    )
    parser.add_argument(
        "--end-date",
        type=parse_date,
        default=None,
        help="Data final no formato YYYY-MM-DD. Se omitida, processa até a data mais recente disponível.",
    )
    parser.add_argument(
        "--todos-cadernos",
        action="store_true",
        help="Não filtra apenas Poder Executivo. Baixa todos os cadernos encontrados.",
    )
    parser.add_argument(
        "--ignorar-year-complete",
        action="store_true",
        help="Ignora marcadores .year_complete e reavalia anos já marcados como completos.",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    total = baixar_markdowns_rj(
        start_date=args.start_date,
        end_date=args.end_date,
        somente_poder_executivo=not args.todos_cadernos,
        pular_anos_completos=not args.ignorar_year_complete,
    )

    print(f"{total} arquivos Markdown baixados/atualizados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
