from __future__ import annotations

import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin

import urllib3

from diarios_oficiais import config
from diarios_oficiais.base import BaseGazetteCollector, Edition
from diarios_oficiais.estadual.rj_ioerj import edition_slug, parse_acts
from diarios_oficiais.utils_regex import sc_doe as sc_regexes


BASE_URL = "https://portal.doe.sea.sc.gov.br/"
REPOSITORY_PATH = "repositorio"
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")

# Marco publicado pelo próprio portal: DOE 22863 em 19/10/2026. A numeração
# ordinária é sequencial nos dias úteis; o coletor faz uma pequena busca ao
# redor da estimativa para acomodar feriados e edições extras.
EDITION_ANCHOR_DATE = date(2026, 10, 19)
EDITION_ANCHOR_NUMBER = 22863
EDITION_ESTIMATE_TOLERANCE = 16
EXTRA_SUFFIXES = ("-A", "-B", "-C", "-D")


class ScDoeCollector(BaseGazetteCollector):
    state = "SC"
    gazette_code = "DOESC"
    gazette_name = "Diario Oficial do Estado de Santa Catarina"
    start_date = date.fromisoformat(config.SC_START_DATE)

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

    @staticmethod
    def business_day_distance(start: date, end: date) -> int:
        direction = 1 if start <= end else -1
        current = start
        distance = 0
        while current != end:
            current += timedelta(days=direction)
            if current.weekday() < 5:
                distance += direction
        return distance

    def estimated_edition_number(self, publication_date: date) -> int:
        return EDITION_ANCHOR_NUMBER + self.business_day_distance(EDITION_ANCHOR_DATE, publication_date)

    def pdf_url(self, publication_date: date, edition_number: str) -> str:
        return urljoin(
            BASE_URL,
            f"{REPOSITORY_PATH}/{publication_date:%Y/%Y%m%d}/Jornal/{edition_number}.pdf",
        )

    def pdf_exists(self, url: str) -> bool:
        try:
            response = self.session.head(url, timeout=self.http_timeout_seconds, allow_redirects=True)
            return response.status_code == 200 and response.headers.get("content-type", "").lower().startswith("application/pdf")
        except Exception:
            return False

    def list_editions(self, publication_date: date) -> list[Edition]:
        estimate = self.estimated_edition_number(publication_date)
        found: list[str] = []
        for number in range(estimate - EDITION_ESTIMATE_TOLERANCE, estimate + EDITION_ESTIMATE_TOLERANCE + 1):
            ordinary = str(number)
            if self.pdf_exists(self.pdf_url(publication_date, ordinary)):
                found.append(ordinary)
                for suffix in EXTRA_SUFFIXES:
                    candidate = f"{ordinary}{suffix}"
                    if self.pdf_exists(self.pdf_url(publication_date, candidate)):
                        found.append(candidate)

        editions: list[Edition] = []
        for edition_number in sorted(set(found), key=lambda value: (int(re.match(r"\d+", value).group()), value)):
            suffix = " - Edicao Extra" if "-" in edition_number else " - Edicao Ordinaria"
            editions.append(
                Edition(
                    publication_date=publication_date,
                    section=f"Diario Oficial SC {edition_number}{suffix}",
                    url=self.pdf_url(publication_date, edition_number),
                )
            )
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.fetch_bytes(edition.url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DOE/SC para PDF nao parece PDF: {edition.url}")
        destination.write_bytes(pdf_bytes)
        return destination

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
        for path in state_lake_dir.rglob("*.md"):
            match = MARKDOWN_DATE_RE.search(path.stem)
            if match:
                current = date.fromisoformat(match.group(1))
                if latest is None or current > latest:
                    latest = current
        return latest


def state_executive_text(text: str) -> str:
    """Retorna o diario completo, sem descartar cadernos ou Poderes.

    O nome da funcao foi mantido para compatibilidade com chamadas existentes.
    A versao anterior recortava somente ``ATOS DO PODER EXECUTIVO`` e parava
    antes de municipios; isso impedia a coleta de qualquer outro caderno que
    aparecesse na mesma edicao.
    """
    return text


def parse_acts_from_markdown_file(collector: ScDoeCollector, edition: Edition, markdown_path: Path) -> list:
    text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    return parse_acts(state_executive_text(text), collector, edition, markdown_path, regexes=sc_regexes)


def collect_sc(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    collector = ScDoeCollector()
    latest_stored_date = collector.latest_stored_publication_date()
    start_date = start_date_override or (collector.start_date if retroativo else latest_stored_date) or collector.start_date
    end_date = end_date or date.today()
    if end_date < start_date:
        raise ValueError("A data final de SC nao pode ser anterior a data inicial.")
    dates = collector.list_available_dates(start_date, end_date)
    if retroativo:
        dates.reverse()
        print(f"Coleta retroativa SC do presente para tras: {end_date.isoformat()} ate {start_date.isoformat()}.", file=sys.stderr)
    elif start_date_override is not None:
        print(f"Coleta SC: {start_date.isoformat()} a {end_date.isoformat()}.", file=sys.stderr)
    elif latest_stored_date is None:
        print(f"Nenhuma edicao SC encontrada no LAKE; iniciando em {start_date.isoformat()}.", file=sys.stderr)
    else:
        print(f"Ultima data SC no LAKE: {latest_stored_date.isoformat()}. Retomando a partir dessa data.", file=sys.stderr)

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
                print(f"Pulando {publication_date.year}: marcador .year_complete encontrado.", file=sys.stderr)
                skipped_years.add(publication_date.year)
            continue
        if active_year is not None and publication_date.year != active_year:
            finalize_year(active_year)
        active_year = publication_date.year
        try:
            editions = collector.list_editions(publication_date)
        except Exception as exc:
            failed_years.add(publication_date.year)
            print(f"Falha ao listar edicoes SC de {publication_date.isoformat()}: {exc}", file=sys.stderr)
            continue
        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)
            csv_path = collector.yearly_csv_path_for(edition.publication_date)
            try:
                print(f"Processando SC {publication_date.isoformat()} ({edition.section})...", file=sys.stderr)
                collector.load_or_create_markdown(edition, markdown_path)
                acts = parse_acts_from_markdown_file(collector, edition, markdown_path)
                total_new_acts += collector.write_csv(csv_path, acts)
            except Exception as exc:
                failed_years.add(publication_date.year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(f"Falha ao processar SC {publication_date.isoformat()} ({edition.section}); seguindo: {exc}", file=sys.stderr)
    finalize_year(active_year)
    return total_new_acts
