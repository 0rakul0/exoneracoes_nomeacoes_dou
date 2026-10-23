from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import urllib3

from diarios_oficiais import config
from diarios_oficiais.base import BaseGazetteCollector, Edition
from diarios_oficiais.estadual.rj_ioerj import edition_slug, parse_acts
from diarios_oficiais.utils_regex import ba_doe as ba_regexes


MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")


class BaPowerCollector(BaseGazetteCollector):
    """Base comum para os diarios separados dos Poderes da Bahia."""

    state = "BA"
    start_date = date.fromisoformat(config.BA_START_DATE)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.session.verify = False
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def list_available_dates(
        self,
        start_date_override: date | None = None,
        end_date: date | None = None,
    ) -> list[date]:
        current = start_date_override or self.start_date
        last_date = end_date or date.today()
        dates: list[date] = []
        while current <= last_date:
            dates.append(current)
            current += timedelta(days=1)
        return dates

    def lake_base_path_for(self, edition: Edition) -> Path:
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y}" / f"{edition.publication_date:%m}" / stem

    def markdown_path_for(self, edition: Edition) -> Path:
        return self.lake_base_path_for(edition).with_suffix(".md")

    def latest_stored_publication_date(self) -> date | None:
        state_lake_dir = self.lake_dir / self.state
        latest: date | None = None
        if not state_lake_dir.exists():
            return None
        for path in state_lake_dir.rglob(f"{self.gazette_code}_*.md"):
            match = MARKDOWN_DATE_RE.search(path.stem)
            if match:
                current = date.fromisoformat(match.group(1))
                if latest is None or current > latest:
                    latest = current
        return latest

    def year_complete_marker_path(self, year: int) -> Path:
        # Cada diario da BA tem seu proprio marcador; o DOE estadual nao pode
        # fazer o DOEL ou o DJE serem pulados por engano.
        return self.lake_dir / self.state / str(year) / f".{self.gazette_code.lower()}_year_complete"

    def parse_acts_from_markdown_file(self, edition: Edition, markdown_path: Path) -> list:
        text = markdown_path.read_text(encoding="utf-8", errors="ignore")
        return parse_acts(text, self, edition, markdown_path, regexes=ba_regexes)


def collect_ba_power(
    collector_class: type[BaPowerCollector],
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    collector = collector_class()
    latest_stored_date = collector.latest_stored_publication_date()
    start_date = start_date_override or (collector.start_date if retroativo else latest_stored_date) or collector.start_date
    end_date = end_date or date.today()
    if end_date < start_date:
        raise ValueError(f"A data final do {collector.state} nao pode ser anterior a data inicial.")
    dates = collector.list_available_dates(start_date, end_date)
    if retroativo:
        dates = [publication_date for publication_date in dates if publication_date.weekday() < 5]
        dates.reverse()
        print(
            f"Coleta retroativa {collector.gazette_code} do presente para tras: "
            f"{end_date.isoformat()} ate {start_date.isoformat()}.",
            file=sys.stderr,
        )
    elif start_date_override is not None:
        print(f"Coleta {collector.gazette_code}: {start_date.isoformat()} a {end_date.isoformat()}.", file=sys.stderr)
    elif latest_stored_date is None:
        print(f"Nenhuma edicao {collector.gazette_code} encontrada no LAKE; iniciando em {start_date.isoformat()}.", file=sys.stderr)
    else:
        print(f"Ultima data {collector.gazette_code} no LAKE: {latest_stored_date.isoformat()}. Retomando a partir dessa data.", file=sys.stderr)

    total_new_acts = 0
    current_year = date.today().year
    active_year: int | None = None
    failed_years: set[int] = set()
    skipped_years: set[int] = set()

    def finalize_year(year: int | None) -> None:
        if year is None or year >= current_year or year in failed_years:
            return
        collector.mark_year_complete(year)

    for publication_date in dates:
        if pular_anos_completos and collector.is_year_complete(publication_date.year):
            if publication_date.year not in skipped_years:
                print(f"Pulando {collector.gazette_code} {publication_date.year}: marcador de ano completo encontrado.", file=sys.stderr)
                skipped_years.add(publication_date.year)
            continue
        if active_year is not None and publication_date.year != active_year:
            finalize_year(active_year)
        active_year = publication_date.year
        try:
            editions = collector.list_editions(publication_date)
        except Exception as exc:
            failed_years.add(publication_date.year)
            print(f"Falha ao listar edicoes {collector.gazette_code} de {publication_date.isoformat()}: {exc}", file=sys.stderr)
            continue
        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)
            csv_path = collector.yearly_csv_path_for(edition.publication_date)
            try:
                print(f"Processando {collector.gazette_code} {publication_date.isoformat()} ({edition.section})...", file=sys.stderr)
                collector.load_or_create_markdown(edition, markdown_path)
                acts = collector.parse_acts_from_markdown_file(edition, markdown_path)
                total_new_acts += collector.write_csv(csv_path, acts)
            except Exception as exc:
                failed_years.add(publication_date.year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(f"Falha ao processar {collector.gazette_code} {publication_date.isoformat()} ({edition.section}); seguindo: {exc}", file=sys.stderr)
    finalize_year(active_year)
    return total_new_acts
