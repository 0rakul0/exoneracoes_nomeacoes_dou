from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

from diarios_oficiais import config
from diarios_oficiais.base import BaseGazetteCollector, Edition
from diarios_oficiais.estadual.rj_ioerj import edition_slug, parse_acts
from diarios_oficiais.utils_regex import df_doe as regexes

BASE_URL = "https://www.dodf.df.gov.br"
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")
LINKS_RE = re.compile(r"var\s+lstLinkPdf\s*=\s*(\{.*?\});\s*var\s+materiasDiario", re.S)


class DfDoeCollector(BaseGazetteCollector):
    state = "DF"
    gazette_code = "DODF"
    gazette_name = "Diario Oficial do Distrito Federal"
    start_date = date.fromisoformat(config.DF_START_DATE)

    def list_available_dates(self, start_date_override=None, end_date=None):
        current, last = start_date_override or self.start_date, end_date or date.today()
        return [current + timedelta(days=offset) for offset in range((last - current).days + 1)]

    def fetch_html(self, publication_date: date) -> str:
        instant = datetime.combine(publication_date, dtime.min, ZoneInfo("America/Sao_Paulo"))
        url = f"{BASE_URL}/dodf/jornal/diario?data={int(instant.timestamp())}"
        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(url, timeout=self.http_timeout_seconds)
                response.raise_for_status()
                return response.text
            except requests.RequestException as exc:
                last_error = exc
            if attempt < self.max_attempts:
                time.sleep(min(self.delay_seconds * attempt * 2, 30))
        raise RuntimeError(f"Falha ao consultar o DODF: {url}: {last_error}") from last_error

    def list_editions(self, publication_date: date) -> list[Edition]:
        html = self.fetch_html(publication_date)
        match = LINKS_RE.search(html)
        if not match:
            return []
        links = json.loads(match.group(1))
        editions = []
        for group, items in links.items():
            for item in items or []:
                link = str(item.get("link") or "")
                if "&arquivo=" not in link:
                    continue
                pasta, arquivo = link.split("&arquivo=", 1)
                section = f"Diario Oficial DF {group} {Path(arquivo).stem}"
                url = f"{BASE_URL}/dodf/jornal/visualizar-pdf?{urlencode({'pasta': pasta, 'arquivo': arquivo})}"
                editions.append(Edition(publication_date, section, url))
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = self.fetch_bytes(edition.url)
        if not content.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DODF não parece PDF: {edition.url}")
        destination.write_bytes(content)
        return destination

    def lake_base_path_for(self, edition):
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y/%m}" / stem

    def markdown_path_for(self, edition):
        return self.lake_base_path_for(edition).with_suffix(".md")

    def latest_stored_publication_date(self):
        dates = [date.fromisoformat(m.group(1)) for p in (self.lake_dir / self.state).rglob("DODF_*.md") if (m := MARKDOWN_DATE_RE.search(p.stem))]
        return max(dates, default=None)


def parse_acts_from_markdown_file(collector, edition, markdown_path):
    return parse_acts(markdown_path.read_text(encoding="utf-8", errors="ignore"), collector, edition, markdown_path, regexes=regexes)


def collect_df(pular_anos_completos=True, start_date_override=None, end_date=None, retroativo=False):
    collector = DfDoeCollector()
    latest = collector.latest_stored_publication_date()
    first = start_date_override or (collector.start_date if retroativo else latest) or collector.start_date
    last = end_date or date.today()
    if last < first:
        raise ValueError("A data final de DF não pode ser anterior à data inicial.")
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
            print(f"Falha ao listar edições DF de {publication_date}: {exc}", file=sys.stderr)
            continue
        for edition in editions:
            try:
                path = collector.markdown_path_for(edition)
                collector.load_or_create_markdown(edition, path)
                total += collector.write_csv(collector.yearly_csv_path_for(publication_date), parse_acts_from_markdown_file(collector, edition, path))
            except Exception as exc:
                failed_years.add(year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(f"Falha ao processar DF {publication_date} ({edition.section}): {exc}", file=sys.stderr)
    for year in {d.year for d in dates} - failed_years:
        if year < date.today().year and first <= date(year, 1, 1) and last >= date(year, 12, 31):
            collector.mark_year_complete(year)
    return total
