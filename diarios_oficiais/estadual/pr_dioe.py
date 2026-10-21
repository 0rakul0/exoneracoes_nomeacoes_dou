from __future__ import annotations

import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import urllib3

from diarios_oficiais import config
from diarios_oficiais.base import BaseGazetteCollector, Edition
from diarios_oficiais.estadual.rj_ioerj import edition_slug, parse_acts
from diarios_oficiais.utils_regex import pr_dioe as pr_regexes


BASE_URL = "https://www.dioe.pr.gov.br/"
ALL_EDITIONS_API_PATH = "apifront/portal/edicoes/ultimas_edicoes.json"
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")


class PrDioeCollector(BaseGazetteCollector):
    state = "PR"
    gazette_code = "DOEP"
    gazette_name = "Diario Oficial do Estado do Parana"
    start_date = date.fromisoformat(config.PR_START_DATE)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.session.verify = False
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._editions_by_date: dict[date, list[dict]] | None = None

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

    def fetch_json(self, url: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(url, timeout=self.http_timeout_seconds)
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, dict) else {}
            except Exception as exc:
                last_error = exc
            if attempt < self.max_attempts:
                seconds = min(self.delay_seconds * attempt * 2, 30)
                print(
                    f"Tentativa {attempt} falhou para {url}; tentando de novo em {seconds:.0f}s...",
                    file=sys.stderr,
                )
                time.sleep(seconds)
        raise RuntimeError(f"Falha ao consultar {url}: {last_error}") from last_error

    def list_editions(self, publication_date: date) -> list[Edition]:
        if self._editions_by_date is None:
            # O endpoint edicoes_from_data retorna somente o tipo Executivo.
            # O endpoint sem limite e com todos=1 e o catalogo completo do DIOE,
            # incluindo Assembleia e os demais tipos publicados pelo portal.
            url = urljoin(BASE_URL, f"{ALL_EDITIONS_API_PATH}?sem_limite=1&todos=1")
            data = self.fetch_json(url)
            grouped: dict[date, list[dict]] = {}
            for item in data.get("itens") or []:
                raw_date = str(item.get("data") or "").strip()
                try:
                    publication_item_date = datetime.strptime(raw_date, "%d/%m/%Y").date()
                except ValueError:
                    try:
                        publication_item_date = date.fromisoformat(raw_date[:10])
                    except ValueError:
                        continue
                grouped.setdefault(publication_item_date, []).append(item)
            self._editions_by_date = grouped

        items = self._editions_by_date.get(publication_date, [])
        editions: list[Edition] = []
        for item in items:
            edition_id = item.get("id")
            if not edition_id:
                continue
            number = str(item.get("numero") or edition_id)
            type_name = str(item.get("tipo_edicao_nome") or "Diario Oficial PR").strip()
            section = f"{type_name} PR {number}"
            if item.get("suplemento") not in (None, "", 0, "0", False):
                section += " - Suplemento"
            editions.append(
                Edition(
                    publication_date=publication_date,
                    section=section,
                    url=urljoin(BASE_URL, f"portal/edicoes/download/{edition_id}"),
                )
            )
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.fetch_bytes(edition.url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DIOE/PR para PDF nao parece PDF: {edition.url}")
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


def parse_acts_from_markdown_file(collector: PrDioeCollector, edition: Edition, markdown_path: Path) -> list:
    text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    return parse_acts(text, collector, edition, markdown_path, regexes=pr_regexes)


def collect_pr(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    collector = PrDioeCollector()
    latest_stored_date = collector.latest_stored_publication_date()
    start_date = start_date_override or (collector.start_date if retroativo else latest_stored_date) or collector.start_date
    end_date = end_date or date.today()
    if end_date < start_date:
        raise ValueError("A data final do PR nao pode ser anterior a data inicial.")
    dates = collector.list_available_dates(start_date, end_date)
    if retroativo:
        dates.reverse()
        print(f"Coleta retroativa PR do presente para tras: {end_date.isoformat()} ate {start_date.isoformat()}.", file=sys.stderr)
    elif start_date_override is not None:
        print(f"Coleta PR: {start_date.isoformat()} a {end_date.isoformat()}.", file=sys.stderr)
    elif latest_stored_date is None:
        print(f"Nenhuma edicao PR encontrada no LAKE; iniciando em {start_date.isoformat()}.", file=sys.stderr)
    else:
        print(f"Ultima data PR no LAKE: {latest_stored_date.isoformat()}. Retomando a partir dessa data.", file=sys.stderr)

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
            print(f"Falha ao listar edicoes PR de {publication_date.isoformat()}: {exc}", file=sys.stderr)
            continue
        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)
            csv_path = collector.yearly_csv_path_for(edition.publication_date)
            try:
                print(f"Processando PR {publication_date.isoformat()} ({edition.section})...", file=sys.stderr)
                collector.load_or_create_markdown(edition, markdown_path)
                acts = parse_acts_from_markdown_file(collector, edition, markdown_path)
                total_new_acts += collector.write_csv(csv_path, acts)
            except Exception as exc:
                failed_years.add(publication_date.year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(f"Falha ao processar PR {publication_date.isoformat()} ({edition.section}); seguindo: {exc}", file=sys.stderr)
    finalize_year(active_year)
    return total_new_acts
