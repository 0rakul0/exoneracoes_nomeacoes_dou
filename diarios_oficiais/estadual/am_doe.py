from __future__ import annotations

import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

from diarios_oficiais import config
from diarios_oficiais.base import BaseGazetteCollector, Edition
from diarios_oficiais.estadual.rj_ioerj import edition_slug, parse_acts
from diarios_oficiais.utils_regex import am_doe as regexes

BASE_URL = "https://diario.imprensaoficial.am.gov.br"
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")


class AmDoeCollector(BaseGazetteCollector):
    state = "AM"
    gazette_code = "DOEAM"
    gazette_name = "Diario Oficial do Estado do Amazonas"
    start_date = date.fromisoformat(config.AM_START_DATE)
    base_url = BASE_URL

    def list_available_dates(self, start_date_override=None, end_date=None):
        current, last = start_date_override or self.start_date, end_date or date.today()
        return [current + timedelta(days=offset) for offset in range((last - current).days + 1)]

    def fetch_json(self, url: str):
        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(url, timeout=self.http_timeout_seconds)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
            if attempt < self.max_attempts:
                time.sleep(min(self.delay_seconds * attempt * 2, 30))
        raise RuntimeError(f"Falha ao consultar o DOE/AM: {url}: {last_error}") from last_error

    def list_editions(self, publication_date: date) -> list[Edition]:
        data = self.fetch_json(f"{self.base_url}/apifront/portal/edicoes/edicoes_from_data/{publication_date.isoformat()}.json")
        if not isinstance(data, dict) or data.get("erro"):
            return []
        editions = []
        for item in data.get("itens") or []:
            identifier = item.get("id")
            if not identifier:
                continue
            number = item.get("numero") or identifier
            supplement = str(item.get("suplemento_nome") or "").strip()
            if not supplement and item.get("suplemento"):
                supplement = "Suplemento"
            section = f"Diario Oficial {self.state} {number}" + (f" - {supplement}" if supplement else "")
            editions.append(Edition(publication_date, section, f"{self.base_url}/portal/edicoes/download/{identifier}"))
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = self.fetch_bytes(edition.url)
        if not content.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DOE/AM não parece PDF: {edition.url}")
        destination.write_bytes(content)
        return destination

    def lake_base_path_for(self, edition):
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y/%m}" / stem

    def markdown_path_for(self, edition):
        return self.lake_base_path_for(edition).with_suffix(".md")

    def latest_stored_publication_date(self):
        dates = [date.fromisoformat(m.group(1)) for p in (self.lake_dir / self.state).rglob("DOEAM_*.md") if (m := MARKDOWN_DATE_RE.search(p.stem))]
        return max(dates, default=None)


def parse_acts_from_markdown_file(collector, edition, markdown_path):
    return parse_acts(markdown_path.read_text(encoding="utf-8", errors="ignore"), collector, edition, markdown_path, regexes=regexes)


def collect_am(pular_anos_completos=True, start_date_override=None, end_date=None, retroativo=False, collector_cls=AmDoeCollector):
    collector = collector_cls()
    latest = collector.latest_stored_publication_date()
    first = start_date_override or (collector.start_date if retroativo else latest) or collector.start_date
    last = end_date or date.today()
    if last < first:
        raise ValueError("A data final de AM não pode ser anterior à data inicial.")
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
            print(f"Falha ao listar edições AM de {publication_date}: {exc}", file=sys.stderr)
            continue
        for edition in editions:
            try:
                path = collector.markdown_path_for(edition)
                collector.load_or_create_markdown(edition, path)
                total += collector.write_csv(collector.yearly_csv_path_for(publication_date), parse_acts_from_markdown_file(collector, edition, path))
            except Exception as exc:
                failed_years.add(year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(f"Falha ao processar AM {publication_date} ({edition.section}): {exc}", file=sys.stderr)
    for year in {d.year for d in dates} - failed_years:
        if year < date.today().year and first <= date(year, 1, 1) and last >= date(year, 12, 31):
            collector.mark_year_complete(year)
    return total
