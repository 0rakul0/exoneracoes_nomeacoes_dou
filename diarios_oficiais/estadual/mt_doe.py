from __future__ import annotations

import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

import requests

from diarios_oficiais import config
from diarios_oficiais.base import BaseGazetteCollector, Edition
from diarios_oficiais.estadual.rj_ioerj import edition_slug, parse_acts
from diarios_oficiais.utils_regex import mt_doe as mt_regexes


BASE_URL = "https://api.iomat.mt.gov.br/transparencia/v1"
DIARIO_ID = 1
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")


class MtDoeCollector(BaseGazetteCollector):
    state = "MT"
    gazette_code = "DOEMT"
    gazette_name = "Diario Oficial do Estado de Mato Grosso"
    start_date = date.fromisoformat(config.MT_START_DATE)

    def list_available_dates(self, start_date_override: date | None = None, end_date: date | None = None) -> list[date]:
        current = start_date_override or self.start_date
        last = end_date or date.today()
        dates: list[date] = []
        while current <= last:
            dates.append(current)
            current += timedelta(days=1)
        return dates

    def fetch_json(self, url: str, params: dict[str, object] | None = None):
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.http_timeout_seconds)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
            if attempt < self.max_attempts:
                time.sleep(min(self.delay_seconds * attempt * 2, 30))
        raise RuntimeError(f"Falha ao consultar o IOMAT/MT: {url}: {last_error}") from last_error

    def list_editions(self, publication_date: date) -> list[Edition]:
        payload = self.fetch_json(
            f"{BASE_URL}/diarios/{DIARIO_ID}/edicoes",
            {"data": publication_date.isoformat()},
        )
        if not isinstance(payload, list):
            raise RuntimeError("Resposta inesperada da API de edições do IOMAT/MT.")
        editions: list[Edition] = []
        seen: set[str] = set()
        for item in payload:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            if str(item.get("diario") or "").strip().casefold() != "diário oficial":
                continue
            identifier = str(item["id"])
            if identifier in seen:
                continue
            seen.add(identifier)
            number = str(item.get("numero") or identifier)
            supplement = str(item.get("suplemento") or "").strip()
            section = f"Diario Oficial MT {number}"
            if supplement:
                section += f" - {supplement}"
            url = f"{BASE_URL}/diarios/{DIARIO_ID}/edicoes/{identifier}/download?{urlencode({'formato': 'pdf'})}"
            editions.append(Edition(publication_date, section, url))
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.fetch_bytes(edition.url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DOE/MT não parece PDF: {edition.url}")
        destination.write_bytes(pdf_bytes)
        return destination

    def lake_base_path_for(self, edition: Edition) -> Path:
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y/%m}" / stem

    def markdown_path_for(self, edition: Edition) -> Path:
        return self.lake_base_path_for(edition).with_suffix(".md")

    def latest_stored_publication_date(self) -> date | None:
        dates = []
        for path in (self.lake_dir / self.state).rglob("DOEMT_*.md"):
            match = MARKDOWN_DATE_RE.search(path.stem)
            if match:
                dates.append(date.fromisoformat(match.group(1)))
        return max(dates, default=None)


def parse_acts_from_markdown_file(collector: MtDoeCollector, edition: Edition, markdown_path: Path) -> list:
    text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    return parse_acts(text, collector, edition, markdown_path, regexes=mt_regexes)


def collect_mt(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    collector = MtDoeCollector()
    latest = collector.latest_stored_publication_date()
    first = start_date_override or (collector.start_date if retroativo else latest) or collector.start_date
    last = end_date or date.today()
    if last < first:
        raise ValueError("A data final de MT não pode ser anterior à data inicial.")
    dates = collector.list_available_dates(first, last)
    if retroativo:
        dates.reverse()
    total = 0
    failed_years: set[int] = set()
    for publication_date in dates:
        year = publication_date.year
        if pular_anos_completos and collector.is_year_complete(year):
            continue
        try:
            editions = collector.list_editions(publication_date)
        except Exception as exc:
            failed_years.add(year)
            print(f"Falha ao listar edições MT de {publication_date}: {exc}", file=sys.stderr)
            continue
        for edition in editions:
            try:
                print(f"Processando MT {publication_date} ({edition.section})...", file=sys.stderr)
                markdown_path = collector.markdown_path_for(edition)
                collector.load_or_create_markdown(edition, markdown_path)
                acts = parse_acts_from_markdown_file(collector, edition, markdown_path)
                total += collector.write_csv(collector.yearly_csv_path_for(publication_date), acts)
            except Exception as exc:
                failed_years.add(year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(f"Falha ao processar MT {publication_date} ({edition.section}): {exc}", file=sys.stderr)
    for year in {publication_date.year for publication_date in dates} - failed_years:
        if year < date.today().year and first <= date(year, 1, 1) and last >= date(year, 12, 31):
            collector.mark_year_complete(year)
    return total
