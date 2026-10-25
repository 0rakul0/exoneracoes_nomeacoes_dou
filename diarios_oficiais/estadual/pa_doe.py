from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

from diarios_oficiais import config
from diarios_oficiais.base import BaseGazetteCollector, Edition
from diarios_oficiais.estadual.rj_ioerj import edition_slug, parse_acts
from diarios_oficiais.utils_regex import pa_doe as regexes


BASE_URL = "https://www.ioepa.com.br/pages"
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")


class PaDoeCollector(BaseGazetteCollector):
    state = "PA"
    gazette_code = "DOEPA"
    gazette_name = "Diario Oficial do Estado do Para"
    start_date = date.fromisoformat(config.PA_START_DATE)
    base_url = BASE_URL

    def list_available_dates(self, start_date_override=None, end_date=None):
        current, last = start_date_override or self.start_date, end_date or date.today()
        return [current + timedelta(days=offset) for offset in range((last - current).days + 1)]

    def _url_for(self, publication_date: date, suffix: str) -> str:
        return f"{self.base_url}/{publication_date.year}/{publication_date:%Y.%m.%d}.{suffix}.pdf"

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
        editions: list[Edition] = []
        for suffix, label in (("DOE", ""), ("EXTRA", " Extra")):
            url = self._url_for(publication_date, suffix)
            if self._pdf_exists(url):
                editions.append(Edition(publication_date, f"Diario Oficial PA{label}", url))
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = self.fetch_bytes(edition.url)
        if not content.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DOE/PA não parece PDF: {edition.url}")
        destination.write_bytes(content)
        return destination

    def lake_base_path_for(self, edition):
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y/%m}" / stem

    def markdown_path_for(self, edition):
        return self.lake_base_path_for(edition).with_suffix(".md")

    def latest_stored_publication_date(self):
        dates = [
            date.fromisoformat(match.group(1))
            for path in (self.lake_dir / self.state).rglob("DOEPA_*.md")
            if (match := MARKDOWN_DATE_RE.search(path.stem))
        ]
        return max(dates, default=None)


def parse_acts_from_markdown_file(collector, edition, markdown_path):
    return parse_acts(markdown_path.read_text(encoding="utf-8", errors="ignore"), collector, edition, markdown_path, regexes=regexes)


def collect_pa(pular_anos_completos=True, start_date_override=None, end_date=None, retroativo=False):
    collector = PaDoeCollector()
    latest = collector.latest_stored_publication_date()
    first = start_date_override or (collector.start_date if retroativo else latest) or collector.start_date
    last = end_date or date.today()
    if last < first:
        raise ValueError("A data final de PA não pode ser anterior à data inicial.")
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
            print(f"Falha ao listar edições PA de {publication_date}: {exc}", file=sys.stderr)
            continue
        for edition in editions:
            try:
                path = collector.markdown_path_for(edition)
                collector.load_or_create_markdown(edition, path)
                total += collector.write_csv(collector.yearly_csv_path_for(publication_date), parse_acts_from_markdown_file(collector, edition, path))
            except Exception as exc:
                failed_years.add(year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(f"Falha ao processar PA {publication_date} ({edition.section}): {exc}", file=sys.stderr)
    for year in {item.year for item in dates} - failed_years:
        if year < date.today().year and first <= date(year, 1, 1) and last >= date(year, 12, 31):
            collector.mark_year_complete(year)
    return total
