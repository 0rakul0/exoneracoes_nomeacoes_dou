from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import Callable

from diarios_oficiais.base import preload_ocr_models
from diarios_oficiais.config import RJ_COLLECTION_YEAR
from diarios_oficiais.estadual.rj_ioerj import collect_rj
from diarios_oficiais.estadual.rj_ioerj import report_torch_cuda
from diarios_oficiais.estadual.rj_ioerj import RjIoerjCollector
from diarios_oficiais.estadual.sp_doe import collect_sp
from diarios_oficiais.estadual.sp_legacy import collect_sp_legacy
from diarios_oficiais.municipal.rio_de_janeiro import collect_rio_de_janeiro
from diarios_oficiais.municipal.rj_municipalidades import collect_rj_municipalidades
from diarios_oficiais.municipal.niteroi import collect_niteroi
from diarios_oficiais.municipal.campos_dos_goytacazes import collect_campos
from diarios_oficiais.municipal.sao_goncalo import collect_sao_goncalo
from diarios_oficiais.municipal.duque_de_caxias import collect_duque_de_caxias
from diarios_oficiais.municipal.nova_iguacu import collect_nova_iguacu
from diarios_oficiais.municipal.sao_joao_de_meriti import collect_sao_joao_de_meriti


COLLECTORS_BY_STATE: dict[str, Callable[..., int]] = {
    "RJ": collect_rj,
    "SP": collect_sp,
}

STATES_TO_COLLECT = ["RJ", "SP"]


MUNICIPAL_RJ_COLLECTORS: list[tuple[str, Callable[[date | None, date | None], int]]] = [
    ("Rio de Janeiro", collect_rio_de_janeiro),
    ("Parte IV — Municipalidades", collect_rj_municipalidades),
    ("Niterói", collect_niteroi),
    ("Campos dos Goytacazes", collect_campos),
    ("São Gonçalo", collect_sao_goncalo),
    ("Duque de Caxias", collect_duque_de_caxias),
    ("Nova Iguaçu", collect_nova_iguacu),
    ("São João de Meriti", collect_sao_joao_de_meriti),
]


def collect_state(state: str) -> int:
    state = state.upper()
    collector = COLLECTORS_BY_STATE.get(state)
    if collector:
        return collector()
    raise ValueError(f"Estado ainda nao implementado: {state}")


def collect_all_municipal_rj(start_date: date | None, end_date: date | None) -> dict[str, int]:
    """Executa, sequencialmente, os conectores municipais já integrados."""
    totals: dict[str, int] = {}
    for name, collector in MUNICIPAL_RJ_COLLECTORS:
        print(f"Coletando diário municipal: {name}...", file=sys.stderr)
        totals[name] = collector(start_date, end_date)
    return totals


def sondar_novas_edicoes_rj() -> int:
    collector = RjIoerjCollector(delay_seconds=0)
    latest_stored_date = collector.latest_stored_publication_date()
    start_date = latest_stored_date or date(RJ_COLLECTION_YEAR, 1, 1)

    print(
        f"Ultima data no LAKE/RJ: {latest_stored_date.isoformat() if latest_stored_date else 'nenhuma'}",
        file=sys.stderr,
    )
    print(f"Sondando IOERJ a partir de {start_date.isoformat()} (inclusive)...", file=sys.stderr)

    available_dates = [
        publication_date
        for publication_date in collector.list_available_dates()
        if publication_date >= start_date
    ]
    if not available_dates:
        print("Nenhuma data nova encontrada na IOERJ.")
        return 0

    missing_count = 0
    for publication_date in available_dates:
        editions = [
            edition
            for edition in collector.list_editions(publication_date)
            if collector.section_filter.lower() in edition.section.lower()
        ]
        if not editions:
            continue

        print(publication_date.isoformat())
        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)
            status = "ok" if markdown_path.exists() else "pendente"
            if status == "pendente":
                missing_count += 1
            print(f"  [{status}] {edition.section} -> {markdown_path}")

    print(f"Edicoes pendentes de Markdown: {missing_count}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coleta atos de nomeacao/exoneracao nos diarios oficiais.")
    parser.add_argument(
        "--sondar-novas",
        action="store_true",
        help="Lista edicoes da IOERJ a partir da ultima data local, sem baixar PDF nem extrair atos.",
    )
    parser.add_argument(
        "--sem-preload-ocr",
        action="store_true",
        help="Nao carrega modelos OCR antes da coleta. O fallback OCR ainda pode carregar sob demanda.",
    )
    parser.add_argument(
        "--ignorar-year-complete",
        action="store_true",
        help="Ignora marcadores .year_complete e reavalia anos ja marcados como completos.",
    )
    parser.add_argument(
        "--coletar-sp-legado",
        action="store_true",
        help="Coleta o acervo legado de SP (Executivo - Secao II) no intervalo informado.",
    )
    parser.add_argument(
        "--coletar-rio-municipal",
        action="store_true",
        help="Coleta o Diário Oficial do Município do Rio de Janeiro.",
    )
    parser.add_argument(
        "--coletar-rj-municipalidades",
        action="store_true",
        help="Coleta a Parte IV — Municipalidades do DOERJ.",
    )
    parser.add_argument(
        "--coletar-niteroi",
        action="store_true",
        help="Coleta o Diário Oficial do Município de Niterói.",
    )
    parser.add_argument(
        "--coletar-campos",
        action="store_true",
        help="Coleta o Diário Oficial do Município de Campos dos Goytacazes.",
    )
    parser.add_argument(
        "--coletar-sao-goncalo",
        action="store_true",
        help="Coleta o Diário Oficial do Município de São Gonçalo.",
    )
    parser.add_argument(
        "--coletar-municipais-rj",
        action="store_true",
        help="Coleta, em uma única execução, todos os diários municipais do RJ já integrados.",
    )
    parser.add_argument(
        "--coletar-duque-de-caxias",
        action="store_true",
        help="Coleta o Boletim Oficial do Município de Duque de Caxias.",
    )
    parser.add_argument("--coletar-nova-iguacu", action="store_true", help="Coleta o Diário Oficial de Nova Iguaçu.")
    parser.add_argument(
        "--rio-municipal-data-inicial",
        type=date.fromisoformat,
        help="Data inicial YYYY-MM-DD para --coletar-rio-municipal.",
    )
    parser.add_argument(
        "--rio-municipal-data-final",
        type=date.fromisoformat,
        help="Data final YYYY-MM-DD para --coletar-rio-municipal.",
    )
    parser.add_argument(
        "--sp-legado-data-inicial",
        type=date.fromisoformat,
        help="Data inicial YYYY-MM-DD para --coletar-sp-legado.",
    )
    parser.add_argument(
        "--sp-legado-data-final",
        type=date.fromisoformat,
        help="Data final YYYY-MM-DD para --coletar-sp-legado.",
    )
    parser.add_argument(
        "--sp-data-inicial",
        type=date.fromisoformat,
        help="Forca a data inicial da coleta regular de SP (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--sp-data-final",
        type=date.fromisoformat,
        help="Data final da coleta regular de SP (YYYY-MM-DD). Requer --sp-data-inicial.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    report_torch_cuda()

    if args.sondar_novas:
        return sondar_novas_edicoes_rj()

    if args.coletar_sp_legado:
        if not args.sp_legado_data_inicial or not args.sp_legado_data_final:
            raise SystemExit(
                "Use --sp-legado-data-inicial e --sp-legado-data-final com --coletar-sp-legado."
            )
        total = collect_sp_legacy(args.sp_legado_data_inicial, args.sp_legado_data_final)
        print(f"SP legado: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.rio_municipal_data_final and not args.rio_municipal_data_inicial:
        raise SystemExit(
            "Use --rio-municipal-data-inicial junto com --rio-municipal-data-final."
        )

    if args.coletar_municipais_rj:
        totals = collect_all_municipal_rj(
            start_date=args.rio_municipal_data_inicial,
            end_date=args.rio_municipal_data_final,
        )
        for municipality, total in totals.items():
            print(f"{municipality}: {total} atos novos gravados nos CSVs anuais")
        print(f"Total municipal RJ: {sum(totals.values())} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_rio_municipal:
        total = collect_rio_de_janeiro(
            start_date_override=args.rio_municipal_data_inicial,
            end_date=args.rio_municipal_data_final,
        )
        print(f"Rio de Janeiro (municipal): {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_rj_municipalidades:
        total = collect_rj_municipalidades(
            start_date_override=args.rio_municipal_data_inicial,
            end_date=args.rio_municipal_data_final,
        )
        print(f"RJ (Parte IV — Municipalidades): {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_niteroi:
        total = collect_niteroi(
            start_date_override=args.rio_municipal_data_inicial,
            end_date=args.rio_municipal_data_final,
        )
        print(f"Niterói: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_campos:
        total = collect_campos(
            start_date_override=args.rio_municipal_data_inicial,
            end_date=args.rio_municipal_data_final,
        )
        print(f"Campos dos Goytacazes: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_sao_goncalo:
        total = collect_sao_goncalo(
            start_date_override=args.rio_municipal_data_inicial,
            end_date=args.rio_municipal_data_final,
        )
        print(f"São Gonçalo: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_duque_de_caxias:
        total = collect_duque_de_caxias(
            start_date_override=args.rio_municipal_data_inicial,
            end_date=args.rio_municipal_data_final,
        )
        print(f"Duque de Caxias: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_nova_iguacu:
        total = collect_nova_iguacu(args.rio_municipal_data_inicial, args.rio_municipal_data_final)
        print(f"Nova Iguaçu: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.sp_data_final and not args.sp_data_inicial:
        raise SystemExit("Use --sp-data-inicial junto com --sp-data-final.")

    if args.sp_data_inicial:
        total = collect_sp(
            pular_anos_completos=not args.ignorar_year_complete,
            start_date_override=args.sp_data_inicial,
            end_date=args.sp_data_final,
        )
        print(f"SP: {total} atos novos gravados nos CSVs anuais")
        return 0

    if not args.sem_preload_ocr:
        preload_ocr_models()

    total_by_state: dict[str, int] = {}
    for state in STATES_TO_COLLECT:
        try:
            if state in {"RJ", "SP"}:
                total_by_state[state] = COLLECTORS_BY_STATE[state](
                    pular_anos_completos=not args.ignorar_year_complete,
                )
            else:
                total_by_state[state] = collect_state(state)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

    for state, total in total_by_state.items():
        print(f"{state}: {total} atos novos gravados nos CSVs anuais")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
