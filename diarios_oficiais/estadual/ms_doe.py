from __future__ import annotations

import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from diarios_oficiais import config
from diarios_oficiais.base import BaseGazetteCollector, Edition
from diarios_oficiais.estadual.rj_ioerj import edition_slug, parse_acts
from diarios_oficiais.utils_regex import ms_doe as ms_regexes


BASE_URL = "https://www.diariooficial.ms.gov.br"
LIST_PATH = "/api/diarios/listar-todos/"
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")


def parse_publication_date(value: str) -> date | None:
    for pattern in ("%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            continue
    return None


class MsDoeCollector(BaseGazetteCollector):
    state = "MS"
    gazette_code = "DOEMS"
    gazette_name = "Diario Oficial do Estado de Mato Grosso do Sul"
    start_date = date.fromisoformat(config.MS_START_DATE)

    def list_available_dates(self, start_date_override: date | None = None, end_date: date | None = None) -> list[date]:
        current = start_date_override or self.start_date
        last = end_date or date.today()
        dates: list[date] = []
        while current <= last:
            dates.append(current)
            current += timedelta(days=1)
        return dates

    def fetch_json(self, params: dict[str, object]):
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(BASE_URL + LIST_PATH, params=params, timeout=self.http_timeout_seconds)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
            if attempt < self.max_attempts:
                time.sleep(min(self.delay_seconds * attempt * 2, 30))
        raise RuntimeError(f"Falha ao consultar o DOE/MS: {last_error}") from last_error

    def list_editions(self, publication_date: date) -> list[Edition]:
        page = 1
        editions: list[Edition] = []
        seen: set[str] = set()
        while True:
            payload = self.fetch_json({
                "pagina": page,
                "registrosPorPagina": 100,
                "dataInicial": publication_date.isoformat(),
                "dataFinal": publication_date.isoformat(),
            })
            if not isinstance(payload, dict):
                raise RuntimeError("Resposta inesperada da API de listagem do DOE/MS.")
            records = payload.get("diario") or []
            if not isinstance(records, list):
                raise RuntimeError("Lista de diários do DOE/MS ausente.")
            for item in records:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                if item.get("suspenso") is True:
                    continue
                item_date = parse_publication_date(str(item.get("dataPublicacao") or ""))
                if item_date != publication_date:
                    continue
                identifier = str(item["id"])
                if identifier in seen:
                    continue
                seen.add(identifier)
                number = str(item.get("numero") or identifier)
                supplement_number = str(item.get("numeroSuplemento") or "").strip()
                section = f"Diario Oficial MS {number}"
                if supplement_number:
                    section += f" - Suplemento {supplement_number}"
                filename = str(item.get("nomeArquivo") or "").strip()
                if not filename:
                    raise RuntimeError(f"Registro do DOE/MS sem nome de arquivo: {identifier}")
                url = str(item.get("caminhoArquivo") or "").strip()
                if not url:
                    url = f"https://assets.imprensaoficial.ms.gov.br/public/prd/Diario%20Oficial/{publication_date:%Y/%m/%d}/{filename}.pdf"
                editions.append(Edition(publication_date, section, url))
            total_pages = int(payload.get("totalDePaginas") or page)
            if page >= total_pages:
                break
            page += 1
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.fetch_bytes(edition.url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DOE/MS não parece PDF: {edition.url}")
        destination.write_bytes(pdf_bytes)
        return destination

    def lake_base_path_for(self, edition: Edition) -> Path:
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y/%m}" / stem

    def markdown_path_for(self, edition: Edition) -> Path:
        return self.lake_base_path_for(edition).with_suffix(".md")

    def latest_stored_publication_date(self) -> date | None:
        dates = []
        for path in (self.lake_dir / self.state).rglob("DOEMS_*.md"):
            match = MARKDOWN_DATE_RE.search(path.stem)
            if match:
                dates.append(date.fromisoformat(match.group(1)))
        return max(dates, default=None)


def parse_acts_from_markdown_file(collector: MsDoeCollector, edition: Edition, markdown_path: Path) -> list:
    text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    return parse_acts(text, collector, edition, markdown_path, regexes=ms_regexes)


def collect_ms(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    collector = MsDoeCollector()
    latest = collector.latest_stored_publication_date()
    first = start_date_override or (collector.start_date if retroativo else latest) or collector.start_date
    last = end_date or date.today()
    if last < first:
        raise ValueError("A data final de MS não pode ser anterior à data inicial.")
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
            print(f"Falha ao listar edições MS de {publication_date}: {exc}", file=sys.stderr)
            continue
        for edition in editions:
            try:
                print(f"Processando MS {publication_date} ({edition.section})...", file=sys.stderr)
                markdown_path = collector.markdown_path_for(edition)
                collector.load_or_create_markdown(edition, markdown_path)
                acts = parse_acts_from_markdown_file(collector, edition, markdown_path)
                total += collector.write_csv(collector.yearly_csv_path_for(publication_date), acts)
            except Exception as exc:
                failed_years.add(year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(f"Falha ao processar MS {publication_date} ({edition.section}): {exc}", file=sys.stderr)
    for year in {publication_date.year for publication_date in dates} - failed_years:
        if year < date.today().year and first <= date(year, 1, 1) and last >= date(year, 12, 31):
            collector.mark_year_complete(year)
    return total
