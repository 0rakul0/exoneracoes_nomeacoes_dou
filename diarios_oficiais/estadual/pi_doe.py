from __future__ import annotations

import html
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from diarios_oficiais import config
from diarios_oficiais.base import BaseGazetteCollector, Edition
from diarios_oficiais.estadual.rj_ioerj import edition_slug, parse_acts
from diarios_oficiais.utils_regex import pi_doe as regexes


BASE_URL = "https://www.diario.pi.gov.br"
LIST_URL = f"{BASE_URL}/doe/Api/listardiarios.json"
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")
HREF_RE = re.compile(r'href="([^"]+\.pdf)"', re.I)


class PiDoeCollector(BaseGazetteCollector):
    state = "PI"
    gazette_code = "DOEPI"
    gazette_name = "Diario Oficial do Estado do Piaui"
    start_date = date.fromisoformat(config.PI_START_DATE)

    def list_available_dates(self, start_date_override=None, end_date=None):
        current, last = start_date_override or self.start_date, end_date or date.today()
        return [current + timedelta(days=offset) for offset in range((last - current).days + 1)]

    def list_editions(self, publication_date: date) -> list[Edition]:
        response = self.session.post(
            LIST_URL,
            data={
                "draw": "1",
                "start": "0",
                "length": "100",
                "filter_numero": "",
                "filter_data": publication_date.isoformat(),
            },
            timeout=self.http_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        editions: list[Edition] = []
        for row in payload.get("data") or []:
            if len(row) < 3:
                continue
            raw_link, raw_number, raw_date = map(str, row[:3])
            try:
                listed_date = datetime.strptime(raw_date.strip(), "%d/%m/%Y").date()
            except ValueError:
                try:
                    listed_date = date.fromisoformat(raw_date.strip())
                except ValueError:
                    continue
            if listed_date != publication_date:
                continue
            match = HREF_RE.search(html.unescape(raw_link).replace("\\/", "/"))
            if not match:
                continue
            url = match.group(1)
            if url.startswith("../"):
                url = f"{BASE_URL}/{url[3:]}"
            elif url.startswith("/"):
                url = f"{BASE_URL}{url}"
            else:
                url = f"{BASE_URL}/doe/{url}"
            editions.append(Edition(publication_date, f"Diario Oficial PI {raw_number.strip()}", url))
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = self.fetch_bytes(edition.url)
        if not content.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DOE/PI não parece PDF: {edition.url}")
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
            for path in (self.lake_dir / self.state).rglob("DOEPI_*.md")
            if (match := MARKDOWN_DATE_RE.search(path.stem))
        ]
        return max(dates, default=None)


def parse_acts_from_markdown_file(collector, edition, markdown_path):
    return parse_acts(markdown_path.read_text(encoding="utf-8", errors="ignore"), collector, edition, markdown_path, regexes=regexes)


def collect_pi(pular_anos_completos=True, start_date_override=None, end_date=None, retroativo=False):
    collector = PiDoeCollector()
    latest = collector.latest_stored_publication_date()
    first = start_date_override or (collector.start_date if retroativo else latest) or collector.start_date
    last = end_date or date.today()
    if last < first:
        raise ValueError("A data final de PI não pode ser anterior à data inicial.")
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
            print(f"Falha ao listar edições PI de {publication_date}: {exc}", file=sys.stderr)
            continue
        for edition in editions:
            try:
                path = collector.markdown_path_for(edition)
                collector.load_or_create_markdown(edition, path)
                total += collector.write_csv(collector.yearly_csv_path_for(publication_date), parse_acts_from_markdown_file(collector, edition, path))
            except Exception as exc:
                failed_years.add(year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(f"Falha ao processar PI {publication_date} ({edition.section}): {exc}", file=sys.stderr)
    for year in {item.year for item in dates} - failed_years:
        if year < date.today().year and first <= date(year, 1, 1) and last >= date(year, 12, 31):
            collector.mark_year_complete(year)
    return total
