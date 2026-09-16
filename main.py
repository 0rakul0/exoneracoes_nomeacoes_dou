from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import Callable

from diarios_oficiais.base import preload_ocr_models
from diarios_oficiais.config import RJ_COLLECTION_YEAR
from diarios_oficiais.rj_ioerj import collect_rj
from diarios_oficiais.rj_ioerj import report_torch_cuda
from diarios_oficiais.rj_ioerj import RjIoerjCollector
from diarios_oficiais.sp_doe import collect_sp
from diarios_oficiais.sp_legacy import collect_sp_legacy


COLLECTORS_BY_STATE: dict[str, Callable[..., int]] = {
    "RJ": collect_rj,
    "SP": collect_sp,
}

STATES_TO_COLLECT = ["RJ", "SP"]


def collect_state(state: str) -> int:
    state = state.upper()
    collector = COLLECTORS_BY_STATE.get(state)
    if collector:
        return collector()
    raise ValueError(f"Estado ainda nao implementado: {state}")


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
