from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

from diarios_oficiais.base import BaseGazetteCollector, Edition
from diarios_oficiais.estadual.rj_ioerj import edition_slug, parse_acts


MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")


class DailyPdfCollector(BaseGazetteCollector):
    """Base para portais estaduais com uma ou mais edições diárias em PDF."""

    def list_available_dates(self, start_date_override=None, end_date=None):
        current = start_date_override or self.start_date
        last = end_date or date.today()
        return [current + timedelta(days=offset) for offset in range((last - current).days + 1)]

    def edition_specs(self, publication_date: date) -> list[tuple[str, str]]:
        raise NotImplementedError

    def _pdf_exists(self, url: str) -> bool:
        try:
            response = self.session.head(url, allow_redirects=True, timeout=self.http_timeout_seconds)
            if response.status_code == 200:
                return True
            if response.status_code not in {403, 405}:
                return False
            response = self.session.get(url, stream=True, timeout=self.http_timeout_seconds)
            return response.status_code == 200 and response.headers.get("Content-Type", "").lower().startswith("application/pdf")
        except requests.RequestException:
            return False

    def list_editions(self, publication_date: date) -> list[Edition]:
        return [
            Edition(publication_date, section, url)
            for section, url in self.edition_specs(publication_date)
            if self._pdf_exists(url)
        ]

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = self.fetch_bytes(edition.url)
        if not content.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do {self.gazette_code} não parece PDF: {edition.url}")
        destination.write_bytes(content)
        return destination

    def lake_base_path_for(self, edition: Edition):
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y/%m}" / stem

    def markdown_path_for(self, edition: Edition):
        return self.lake_base_path_for(edition).with_suffix(".md")

    def latest_stored_publication_date(self):
        dates = [
            date.fromisoformat(match.group(1))
            for path in (self.lake_dir / self.state).rglob(f"{self.gazette_code}_*.md")
            if (match := MARKDOWN_DATE_RE.search(path.stem))
        ]
        return max(dates, default=None)


def parse_daily_acts(collector, edition, markdown_path, regexes):
    return parse_acts(
        markdown_path.read_text(encoding="utf-8", errors="ignore"),
        collector,
        edition,
        markdown_path,
        regexes=regexes,
    )


def collect_daily(
    collector_class,
    parse_regexes,
    label: str,
    pular_anos_completos=True,
    start_date_override=None,
    end_date=None,
    retroativo=False,
):
    collector = collector_class()
    latest = collector.latest_stored_publication_date()
    first = start_date_override or (collector.start_date if retroativo else latest) or collector.start_date
    last = end_date or date.today()
    if last < first:
        raise ValueError(f"A data final de {label} não pode ser anterior à data inicial.")
    dates = collector.list_available_dates(first, last)
    if retroativo:
        dates.reverse()
    total, failed_years = 0, set()
    for publication_date in dates:
        year = publication_date.year
        if pular_anos_completos and collector.is_year_complete(year):
            continue
        try:
            editions = collector.list_editions(publication_date)
        except Exception as exc:
            failed_years.add(year)
            print(f"Falha ao listar edições {label} de {publication_date}: {exc}", file=sys.stderr)
            continue
        for edition in editions:
            try:
                path = collector.markdown_path_for(edition)
                collector.load_or_create_markdown(edition, path)
                total += collector.write_csv(
                    collector.yearly_csv_path_for(publication_date),
                    parse_daily_acts(collector, edition, path, parse_regexes),
                )
            except Exception as exc:
                failed_years.add(year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(f"Falha ao processar {label} {publication_date} ({edition.section}): {exc}", file=sys.stderr)
    for year in {item.year for item in dates} - failed_years:
        if year < date.today().year and first <= date(year, 1, 1) and last >= date(year, 12, 31):
            collector.mark_year_complete(year)
    return total
