"""Coleta retroativa dos diários estaduais em rodízio por caderno."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterator

from diarios_oficiais.base import BaseGazetteCollector, Edition
from diarios_oficiais.estadual.ac_doe import AcDoeCollector
from diarios_oficiais.estadual.ac_dje import AcDjeCollector
from diarios_oficiais.estadual.ba_dje import BaDjeCollector
from diarios_oficiais.estadual.ba_doe import BaDoeCollector
from diarios_oficiais.estadual.ba_doel import BaDoelCollector
from diarios_oficiais.estadual.ce_doe import CeDoeCollector
from diarios_oficiais.estadual.es_dio import EsDioCollector
from diarios_oficiais.estadual.pr_dioe import PrDioeCollector
from diarios_oficiais.estadual.pb_dje import PbDjeCollector
from diarios_oficiais.estadual.pb_doe import PbDoeCollector
from diarios_oficiais.estadual.rj_ioerj import (
    RjIoerjCollector,
    parse_acts_from_markdown_file as parse_rj_acts,
)
from diarios_oficiais.estadual.rs_doe import RsDoeCollector
from diarios_oficiais.estadual.sc_doe import ScDoeCollector
from diarios_oficiais.estadual.sp_doe import (
    SpDoeCollector,
    parse_acts_from_markdown_file as parse_sp_acts,
)
from diarios_oficiais.estadual.ba_doe import parse_acts_from_markdown_file as parse_ba_acts
from diarios_oficiais.estadual.es_dio import parse_acts_from_markdown_file as parse_es_acts
from diarios_oficiais.estadual.pr_dioe import parse_acts_from_markdown_file as parse_pr_acts
from diarios_oficiais.estadual.rs_doe import parse_acts_from_markdown_file as parse_rs_acts
from diarios_oficiais.estadual.sc_doe import parse_acts_from_markdown_file as parse_sc_acts


Parser = Callable[[BaseGazetteCollector, Edition, Path], list]


@dataclass(frozen=True)
class CollectorSpec:
    """Um diário que participa da fila de um estado."""

    state: str
    collector_factory: Callable[[], BaseGazetteCollector]
    parser: Parser | None = None


@dataclass(frozen=True)
class PendingEdition:
    state: str
    collector: BaseGazetteCollector
    edition: Edition
    parser: Parser | None


STATE_SPECS: tuple[tuple[str, tuple[CollectorSpec, ...]], ...] = (
    ("RJ", (CollectorSpec("RJ", RjIoerjCollector, parse_rj_acts),)),
    ("SP", (CollectorSpec("SP", SpDoeCollector, parse_sp_acts),)),
    ("ES", (CollectorSpec("ES", EsDioCollector, parse_es_acts),)),
    (
        "BA",
        (
            CollectorSpec("BA", BaDoeCollector, parse_ba_acts),
            CollectorSpec("BA", BaDoelCollector),
            CollectorSpec("BA", BaDjeCollector),
        ),
    ),
    ("SC", (CollectorSpec("SC", ScDoeCollector, parse_sc_acts),)),
    ("PR", (CollectorSpec("PR", PrDioeCollector, parse_pr_acts),)),
    ("RS", (CollectorSpec("RS", RsDoeCollector, parse_rs_acts),)),
    (
        "PB",
        (
            CollectorSpec("PB", PbDoeCollector),
            CollectorSpec("PB", PbDjeCollector),
        ),
    ),
    (
        "AC",
        (
            CollectorSpec("AC", AcDoeCollector),
            CollectorSpec("AC", AcDjeCollector),
        ),
    ),
    ("CE", (CollectorSpec("CE", CeDoeCollector),)),
)


def _parse_acts(
    parser: Parser | None,
    collector: BaseGazetteCollector,
    edition: Edition,
    markdown_path: Path,
) -> list:
    if parser is not None:
        return parser(collector, edition, markdown_path)
    parse_method = getattr(collector, "parse_acts_from_markdown_file", None)
    if parse_method is None:
        raise RuntimeError(f"Parser de atos nao configurado para {collector.gazette_code}.")
    return parse_method(edition, markdown_path)


def _start_date(collector: BaseGazetteCollector) -> date:
    configured = getattr(collector, "start_date", None)
    if configured is not None:
        return configured
    # O RJ usa RJ_COLLECTION_YEAR em vez de um atributo start_date.
    from diarios_oficiais.config import RJ_COLLECTION_YEAR

    return date(RJ_COLLECTION_YEAR, 1, 1)


def _dates_for(collector: BaseGazetteCollector, today: date) -> list[date]:
    start_date = _start_date(collector)
    if isinstance(collector, (RjIoerjCollector, SpDoeCollector)):
        available_dates = collector.list_available_dates()
    else:
        available_dates = collector.list_available_dates(start_date, today)
    return sorted(
        (
            publication_date
            for publication_date in available_dates
            if start_date <= publication_date <= today and publication_date.weekday() < 5
        ),
        reverse=True,
    )


def _iter_collector_editions(
    spec: CollectorSpec,
    collector: BaseGazetteCollector,
    today: date,
    skip_complete_years: bool,
) -> Iterator[PendingEdition]:
    skipped_years: set[int] = set()
    for publication_date in _dates_for(collector, today):
        if skip_complete_years and collector.is_year_complete(publication_date.year):
            if publication_date.year not in skipped_years:
                print(
                    f"Pulando {collector.gazette_code} {publication_date.year}: "
                    "marcador de ano completo encontrado.",
                    file=sys.stderr,
                )
                skipped_years.add(publication_date.year)
            continue

        try:
            editions = collector.list_editions(publication_date)
        except Exception as exc:
            print(
                f"Falha ao listar edicoes {collector.gazette_code} de "
                f"{publication_date.isoformat()}: {exc}",
                file=sys.stderr,
            )
            continue

        for edition in editions:
            yield PendingEdition(spec.state, collector, edition, spec.parser)


def _iter_state_editions(
    state: str,
    specs: tuple[CollectorSpec, ...],
    today: date,
    skip_complete_years: bool,
) -> Iterator[PendingEdition]:
    """Intercala as fontes que compõem um mesmo estado."""
    iterators = [
        _iter_collector_editions(spec, spec.collector_factory(), today, skip_complete_years)
        for spec in specs
    ]
    active = list(iterators)
    while active:
        next_active: list[Iterator[PendingEdition]] = []
        for iterator in active:
            try:
                yield next(iterator)
            except StopIteration:
                continue
            next_active.append(iterator)
        active = next_active


def collect_estaduais_em_rodizio(
    *,
    skip_complete_years: bool = True,
    today: date | None = None,
) -> int:
    """Processa um caderno por estado, alternando estados a cada caderno."""
    current_date = today or date.today()
    print(
        f"Rodizio retroativo dos diarios estaduais: {current_date.isoformat()} para tras.",
        file=sys.stderr,
    )

    state_iterators = [
        (state, _iter_state_editions(state, specs, current_date, skip_complete_years))
        for state, specs in STATE_SPECS
    ]
    total_new_acts = 0

    while state_iterators:
        next_states: list[tuple[str, Iterator[PendingEdition]]] = []
        for state, iterator in state_iterators:
            try:
                pending = next(iterator)
            except StopIteration:
                print(f"Fila do {state} concluida.", file=sys.stderr)
                continue

            collector = pending.collector
            edition = pending.edition
            markdown_path = collector.markdown_path_for(edition)
            csv_path = collector.yearly_csv_path_for(edition.publication_date)
            print(
                f"Rodizio: processando {pending.state} "
                f"{edition.publication_date.isoformat()} ({edition.section})...",
                file=sys.stderr,
            )
            try:
                collector.load_or_create_markdown(edition, markdown_path)
                acts = _parse_acts(pending.parser, collector, edition, markdown_path)
                total_new_acts += collector.write_csv(csv_path, acts)
            except Exception as exc:
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(
                    f"Falha ao processar {pending.state} "
                    f"{edition.publication_date.isoformat()} ({edition.section}); seguindo: {exc}",
                    file=sys.stderr,
                )
            next_states.append((state, iterator))
        state_iterators = next_states

    return total_new_acts
