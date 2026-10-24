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
from diarios_oficiais.estadual.es_dio import collect_es
from diarios_oficiais.estadual.ba_doe import collect_ba
from diarios_oficiais.estadual.ba_doel import collect_ba_doel
from diarios_oficiais.estadual.ba_dje import collect_ba_dje
from diarios_oficiais.estadual.sc_doe import collect_sc
from diarios_oficiais.estadual.pr_dioe import collect_pr
from diarios_oficiais.estadual.rs_doe import collect_rs
from diarios_oficiais.estadual.pb_doe import collect_pb
from diarios_oficiais.estadual.pb_dje import collect_pb_dje
from diarios_oficiais.estadual.ac_doe import collect_ac
from diarios_oficiais.estadual.ac_dje import collect_ac_dje
from diarios_oficiais.estadual.ce_doe import collect_ce
from diarios_oficiais.rodizio_estadual import collect_estaduais_em_rodizio
from diarios_oficiais.municipal.rio_de_janeiro import collect_rio_de_janeiro
from diarios_oficiais.municipal.rj_municipalidades import collect_rj_municipalidades
from diarios_oficiais.municipal.niteroi import collect_niteroi
from diarios_oficiais.municipal.campos_dos_goytacazes import collect_campos
from diarios_oficiais.municipal.sao_goncalo import collect_sao_goncalo
from diarios_oficiais.municipal.duque_de_caxias import collect_duque_de_caxias
from diarios_oficiais.municipal.nova_iguacu import collect_nova_iguacu
from diarios_oficiais.municipal.sao_joao_de_meriti import collect_sao_joao_de_meriti


def collect_ba_all(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    """Coleta o DOE/BA, o DOEL/BA e o DJE/BA no mesmo intervalo."""
    total = collect_ba(
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
    total += collect_ba_doel(
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
    total += collect_ba_dje(
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
    return total


def collect_pb_all(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    """Coleta o DOE/PB e o DJE/PB no mesmo intervalo."""
    total = collect_pb(
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
    total += collect_pb_dje(
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
    return total


def collect_ac_all(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    """Coleta o DOE/AC e o DJE/AC no mesmo intervalo."""
    total = collect_ac(
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
    total += collect_ac_dje(
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
    return total


def collect_ce_all(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    """Coleta os cadernos publicados pelo DOE/CE no mesmo intervalo."""
    return collect_ce(
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )


COLLECTORS_BY_STATE: dict[str, Callable[..., int]] = {
    "RJ": collect_rj,
    "SP": collect_sp,
    "ES": collect_es,
    "BA": collect_ba_all,
    "SC": collect_sc,
    "PR": collect_pr,
    "RS": collect_rs,
    "PB": collect_pb_all,
    "AC": collect_ac_all,
    "CE": collect_ce_all,
}

STATES_TO_COLLECT = ["RJ", "SP", "ES", "BA", "SC", "PR", "RS", "PB", "AC", "CE"]


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
        "--rj-retroativo",
        action="store_true",
        help="Coleta o RJ a partir de hoje, retrocedendo pelo historico disponivel.",
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
    parser.add_argument(
        "--sp-retroativo",
        action="store_true",
        help="Coleta o SP a partir de hoje, retrocedendo pelo historico disponivel.",
    )
    parser.add_argument(
        "--coletar-es",
        action="store_true",
        help="Coleta o Diário Oficial do Estado do Espírito Santo no intervalo informado.",
    )
    parser.add_argument(
        "--es-retroativo",
        action="store_true",
        help="Coleta o ES da data de hoje para trás até ES_START_DATE.",
    )
    parser.add_argument(
        "--es-data-inicial",
        type=date.fromisoformat,
        help="Forca a data inicial da coleta do ES (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--es-data-final",
        type=date.fromisoformat,
        help="Data final da coleta do ES (YYYY-MM-DD). Requer --es-data-inicial.",
    )
    parser.add_argument(
        "--coletar-ba",
        action="store_true",
        help="Coleta o Diário Oficial do Estado da Bahia no intervalo informado.",
    )
    parser.add_argument(
        "--ba-retroativo",
        action="store_true",
        help="Coleta a BA da data de hoje para trás até BA_START_DATE.",
    )
    parser.add_argument(
        "--ba-data-inicial",
        type=date.fromisoformat,
        help="Forca a data inicial da coleta da BA (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--ba-data-final",
        type=date.fromisoformat,
        help="Data final da coleta da BA (YYYY-MM-DD). Requer --ba-data-inicial.",
    )
    parser.add_argument(
        "--coletar-sc",
        action="store_true",
        help="Coleta o Diário Oficial do Estado de Santa Catarina no intervalo informado.",
    )
    parser.add_argument(
        "--sc-retroativo",
        action="store_true",
        help="Coleta SC da data de hoje para trás até SC_START_DATE.",
    )
    parser.add_argument(
        "--sc-data-inicial",
        type=date.fromisoformat,
        help="Forca a data inicial da coleta de SC (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--sc-data-final",
        type=date.fromisoformat,
        help="Data final da coleta de SC (YYYY-MM-DD). Requer --sc-data-inicial.",
    )
    parser.add_argument(
        "--coletar-pr",
        action="store_true",
        help="Coleta todos os tipos do Diário Oficial do Paraná no intervalo informado.",
    )
    parser.add_argument(
        "--pr-retroativo",
        action="store_true",
        help="Coleta o PR da data de hoje para trás até PR_START_DATE.",
    )
    parser.add_argument(
        "--pr-data-inicial",
        type=date.fromisoformat,
        help="Forca a data inicial da coleta do PR (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--pr-data-final",
        type=date.fromisoformat,
        help="Data final da coleta do PR (YYYY-MM-DD). Requer --pr-data-inicial.",
    )
    parser.add_argument(
        "--coletar-rs",
        action="store_true",
        help="Coleta o Diário Oficial do Estado do Rio Grande do Sul no intervalo informado.",
    )
    parser.add_argument(
        "--rs-retroativo",
        action="store_true",
        help="Coleta o RS da data de hoje para trás até RS_START_DATE.",
    )
    parser.add_argument(
        "--rs-data-inicial",
        type=date.fromisoformat,
        help="Forca a data inicial da coleta do RS (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--rs-data-final",
        type=date.fromisoformat,
        help="Data final da coleta do RS (YYYY-MM-DD). Requer --rs-data-inicial.",
    )
    parser.add_argument(
        "--coletar-pb",
        action="store_true",
        help="Coleta o DOE/PB e o DJE/PB no intervalo informado.",
    )
    parser.add_argument(
        "--pb-retroativo",
        action="store_true",
        help="Coleta a PB da data de hoje para trás até PB_START_DATE.",
    )
    parser.add_argument(
        "--pb-data-inicial",
        type=date.fromisoformat,
        help="Forca a data inicial da coleta da PB (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--pb-data-final",
        type=date.fromisoformat,
        help="Data final da coleta da PB (YYYY-MM-DD). Requer --pb-data-inicial.",
    )
    parser.add_argument(
        "--coletar-ac",
        action="store_true",
        help="Coleta o DOE/AC e o DJE/AC no intervalo informado.",
    )
    parser.add_argument(
        "--ac-retroativo",
        action="store_true",
        help="Coleta o AC da data de hoje para trás até AC_START_DATE.",
    )
    parser.add_argument(
        "--ac-data-inicial",
        type=date.fromisoformat,
        help="Forca a data inicial da coleta do AC (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--ac-data-final",
        type=date.fromisoformat,
        help="Data final da coleta do AC (YYYY-MM-DD). Requer --ac-data-inicial.",
    )
    parser.add_argument(
        "--coletar-ce",
        action="store_true",
        help="Coleta os cadernos do DOE/CE no intervalo informado.",
    )
    parser.add_argument(
        "--ce-retroativo",
        action="store_true",
        help="Coleta o CE da data de hoje para trás até CE_START_DATE.",
    )
    parser.add_argument(
        "--estaduais-rodizio-retroativo",
        action="store_true",
        help="Coleta os diários estaduais em rodízio, um caderno por estado, de hoje para trás.",
    )
    parser.add_argument(
        "--ce-data-inicial",
        type=date.fromisoformat,
        help="Forca a data inicial da coleta do CE (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--ce-data-final",
        type=date.fromisoformat,
        help="Data final da coleta do CE (YYYY-MM-DD). Requer --ce-data-inicial.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    report_torch_cuda()

    if args.sondar_novas:
        return sondar_novas_edicoes_rj()

    if args.estaduais_rodizio_retroativo:
        total = collect_estaduais_em_rodizio(
            skip_complete_years=not args.ignorar_year_complete,
        )
        print(f"Rodízio estadual: {total} atos novos gravados nos CSVs anuais")
        return 0

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

    if args.rj_retroativo:
        total = collect_rj(
            pular_anos_completos=not args.ignorar_year_complete,
            retroativo=True,
        )
        print(f"RJ retroativo: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.sp_data_final and not args.sp_data_inicial:
        raise SystemExit("Use --sp-data-inicial junto com --sp-data-final.")

    if args.sp_retroativo:
        total = collect_sp(
            pular_anos_completos=not args.ignorar_year_complete,
            retroativo=True,
        )
        print(f"SP retroativo: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.sp_data_inicial:
        total = collect_sp(
            pular_anos_completos=not args.ignorar_year_complete,
            start_date_override=args.sp_data_inicial,
            end_date=args.sp_data_final,
        )
        print(f"SP: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.es_data_final and not args.es_data_inicial:
        raise SystemExit("Use --es-data-inicial junto com --es-data-final.")

    if args.es_retroativo:
        total = collect_es(
            pular_anos_completos=not args.ignorar_year_complete,
            retroativo=True,
        )
        print(f"ES retroativo: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_es or args.es_data_inicial:
        total = collect_es(
            pular_anos_completos=not args.ignorar_year_complete,
            start_date_override=args.es_data_inicial,
            end_date=args.es_data_final,
        )
        print(f"ES: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.ba_data_final and not args.ba_data_inicial:
        raise SystemExit("Use --ba-data-inicial junto com --ba-data-final.")

    if args.ba_retroativo:
        total = collect_ba_all(
            pular_anos_completos=not args.ignorar_year_complete,
            retroativo=True,
        )
        print(f"BA retroativo: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_ba or args.ba_data_inicial:
        total = collect_ba_all(
            pular_anos_completos=not args.ignorar_year_complete,
            start_date_override=args.ba_data_inicial,
            end_date=args.ba_data_final,
        )
        print(f"BA: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.sc_data_final and not args.sc_data_inicial:
        raise SystemExit("Use --sc-data-inicial junto com --sc-data-final.")

    if args.sc_retroativo:
        total = collect_sc(
            pular_anos_completos=not args.ignorar_year_complete,
            retroativo=True,
        )
        print(f"SC retroativo: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_sc or args.sc_data_inicial:
        total = collect_sc(
            pular_anos_completos=not args.ignorar_year_complete,
            start_date_override=args.sc_data_inicial,
            end_date=args.sc_data_final,
        )
        print(f"SC: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.pr_data_final and not args.pr_data_inicial:
        raise SystemExit("Use --pr-data-inicial junto com --pr-data-final.")

    if args.pr_retroativo:
        total = collect_pr(
            pular_anos_completos=not args.ignorar_year_complete,
            retroativo=True,
        )
        print(f"PR retroativo: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_pr or args.pr_data_inicial:
        total = collect_pr(
            pular_anos_completos=not args.ignorar_year_complete,
            start_date_override=args.pr_data_inicial,
            end_date=args.pr_data_final,
        )
        print(f"PR: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.rs_data_final and not args.rs_data_inicial:
        raise SystemExit("Use --rs-data-inicial junto com --rs-data-final.")

    if args.rs_retroativo:
        total = collect_rs(
            pular_anos_completos=not args.ignorar_year_complete,
            retroativo=True,
        )
        print(f"RS retroativo: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_rs or args.rs_data_inicial:
        total = collect_rs(
            pular_anos_completos=not args.ignorar_year_complete,
            start_date_override=args.rs_data_inicial,
            end_date=args.rs_data_final,
        )
        print(f"RS: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.pb_data_final and not args.pb_data_inicial:
        raise SystemExit("Use --pb-data-inicial junto com --pb-data-final.")

    if args.pb_retroativo:
        total = collect_pb_all(
            pular_anos_completos=not args.ignorar_year_complete,
            retroativo=True,
        )
        print(f"PB retroativo: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_pb or args.pb_data_inicial:
        total = collect_pb_all(
            pular_anos_completos=not args.ignorar_year_complete,
            start_date_override=args.pb_data_inicial,
            end_date=args.pb_data_final,
        )
        print(f"PB: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.ac_data_final and not args.ac_data_inicial:
        raise SystemExit("Use --ac-data-inicial junto com --ac-data-final.")

    if args.ac_retroativo:
        total = collect_ac_all(
            pular_anos_completos=not args.ignorar_year_complete,
            retroativo=True,
        )
        print(f"AC retroativo: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_ac or args.ac_data_inicial:
        total = collect_ac_all(
            pular_anos_completos=not args.ignorar_year_complete,
            start_date_override=args.ac_data_inicial,
            end_date=args.ac_data_final,
        )
        print(f"AC: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.ce_data_final and not args.ce_data_inicial:
        raise SystemExit("Use --ce-data-inicial junto com --ce-data-final.")

    if args.ce_retroativo:
        total = collect_ce_all(
            pular_anos_completos=not args.ignorar_year_complete,
            retroativo=True,
        )
        print(f"CE retroativo: {total} atos novos gravados nos CSVs anuais")
        return 0

    if args.coletar_ce or args.ce_data_inicial:
        total = collect_ce_all(
            pular_anos_completos=not args.ignorar_year_complete,
            start_date_override=args.ce_data_inicial,
            end_date=args.ce_data_final,
        )
        print(f"CE: {total} atos novos gravados nos CSVs anuais")
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
