from __future__ import annotations

import re
import sys
from datetime import date
from datetime import timedelta
from pathlib import Path
from urllib.parse import urljoin

from diarios_oficiais import config
from diarios_oficiais.base import BaseGazetteCollector
from diarios_oficiais.base import Edition
from diarios_oficiais.rj_ioerj import edition_slug
from diarios_oficiais.rj_ioerj import parse_acts_from_markdown_file
from diarios_oficiais.utils_regex import sp_doe as sp_regexes


WEB_SEARCH_API_URL = "https://do-api-web-search.doe.sp.gov.br/"
PDF_API_URL = "https://do-api-publication-pdf.doe.sp.gov.br/"


class SpDoeCollector(BaseGazetteCollector):
    state = "SP"
    gazette_code = "DOESP"
    gazette_name = "Diario Oficial do Estado de Sao Paulo"
    journal_name = config.SP_JOURNAL_NAME
    section_name = config.SP_SECTION_NAME
    web_search_api_url = WEB_SEARCH_API_URL
    pdf_api_url = PDF_API_URL
    start_date = date.fromisoformat(config.SP_START_DATE)

    def list_available_dates(self) -> list[date]:
        today = date.today()
        dates: list[date] = []
        current = today
        while current >= self.start_date:
            dates.append(current)
            current -= timedelta(days=1)
        return dates

    def list_editions(self, publication_date: date) -> list[Edition]:
        journal = self.find_journal(publication_date, self.journal_name)
        if not journal:
            return []

        section = self.find_section(publication_date, journal["id"], self.section_name)
        if not section:
            return []

        pdf_url = self.edition_pdf_url(publication_date, journal["id"], section["id"])
        if not pdf_url:
            return []

        return [
            Edition(
                publication_date=publication_date,
                section=f"{journal['name']} - {section['name']}",
                url=pdf_url,
            )
        ]

    def find_journal(self, publication_date: date, name: str) -> dict[str, str] | None:
        data = self.fetch_json(
            urljoin(self.web_search_api_url, "v2/journals"),
            {"date": self.format_api_date(publication_date)},
        )
        return find_item_by_name(data.get("items", []), name)

    def find_section(
        self,
        publication_date: date,
        journal_id: str,
        name: str,
    ) -> dict[str, str] | None:
        data = self.fetch_json(
            urljoin(self.web_search_api_url, "v2/sections"),
            {
                "journalId": journal_id,
                "date": self.format_api_date(publication_date),
            },
        )
        return find_item_by_name(data.get("items", []), name)

    def edition_pdf_url(self, publication_date: date, journal_id: str, section_id: str) -> str:
        data = self.fetch_json(
            urljoin(self.pdf_api_url, "v1/editions/url"),
            {
                "JournalId": journal_id,
                "RootSectionId": section_id,
                "EditionDate": self.format_api_date(publication_date),
            },
        )
        if data.get("isError"):
            return ""
        return str(data.get("url") or "")

    def fetch_json(self, url: str, params: dict[str, str]) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.http_timeout_seconds)
                if response.status_code == 404:
                    return {}
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_error = exc
            if attempt < self.max_attempts:
                self.sleep_before_retry(attempt, url)
        raise RuntimeError(f"Falha ao consultar {url}: {last_error}") from last_error

    def sleep_before_retry(self, attempt: int, url: str) -> None:
        import time

        sleep_seconds = min(self.delay_seconds * attempt * 2, 30)
        print(
            f"Tentativa {attempt} falhou para {url}; tentando de novo em {sleep_seconds:.0f}s...",
            file=sys.stderr,
        )
        time.sleep(sleep_seconds)

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.fetch_bytes(edition.url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DOESP para PDF nao parece PDF: {edition.url}")
        destination.write_bytes(pdf_bytes)
        return destination

    def lake_base_path_for(self, edition: Edition) -> Path:
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y}" / f"{edition.publication_date:%m}" / stem

    def markdown_path_for(self, edition: Edition) -> Path:
        return self.lake_base_path_for(edition).with_suffix(".md")

    @staticmethod
    def format_api_date(value: date) -> str:
        return f"{value.year}-{value.month}-{value.day}"


def find_item_by_name(items: list[dict], name: str) -> dict[str, str] | None:
    wanted = normalize_name(name)
    for item in items:
        if normalize_name(str(item.get("name", ""))) == wanted:
            return item
    return None


def normalize_name(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def collect_sp() -> int:
    collector = SpDoeCollector()
    dates = collector.list_available_dates()

    total_new_acts = 0
    current_year = date.today().year
    active_year: int | None = None
    failed_years: set[int] = set()
    skipped_years: set[int] = set()

    def finalize_year(year: int | None) -> None:
        if year is None or year >= current_year:
            return
        if year == collector.start_date.year and collector.start_date != date(year, 1, 1):
            return
        if year in failed_years:
            print(f"Nao marquei {year} como completo porque houve falhas de coleta.", file=sys.stderr)
            return
        collector.mark_year_complete(year)

    for item in dates:
        if collector.is_year_complete(item.year):
            if item.year not in skipped_years:
                print(f"Pulando {item.year}: marcador .year_complete encontrado.", file=sys.stderr)
                skipped_years.add(item.year)
            continue

        if active_year is not None and item.year != active_year:
            finalize_year(active_year)
        active_year = item.year

        try:
            editions = collector.list_editions(item)
        except Exception as exc:
            failed_years.add(item.year)
            print(f"Falha ao listar edicoes de {item.isoformat()}: {exc}", file=sys.stderr)
            continue

        if not editions:
            continue

        print(f"Processando SP {item.isoformat()}...", file=sys.stderr)
        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)
            csv_path = collector.yearly_csv_path_for(edition.publication_date)
            try:
                collector.load_or_create_markdown(edition, markdown_path)
                acts = parse_acts_from_markdown_file(
                    collector,
                    edition,
                    markdown_path,
                    regexes=sp_regexes,
                )
                total_new_acts += collector.write_csv(csv_path, acts)
            except Exception as exc:
                failed_years.add(item.year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(
                    f"Falha ao processar SP {item.isoformat()} ({edition.section}); seguindo: {exc}",
                    file=sys.stderr,
                )
                continue

    finalize_year(active_year)
    return total_new_acts
