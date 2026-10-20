from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin

from diarios_oficiais import config
from diarios_oficiais.base import BaseGazetteCollector, Edition
from diarios_oficiais.estadual.rj_ioerj import (
    edition_slug,
    parse_acts,
)
from diarios_oficiais.utils_regex import es_dio as es_regexes


BASE_URL = "https://ioes.dio.es.gov.br/"
EDITIONS_API_PATH = "apifront/portal/edicoes/edicoes_from_data/"
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")


class EsDioCollector(BaseGazetteCollector):
    state = "ES"
    gazette_code = "DOES"
    gazette_name = "Diario Oficial do Estado do Espirito Santo"
    start_date = date.fromisoformat(config.ES_START_DATE)

    def list_available_dates(
        self,
        start_date_override: date | None = None,
        end_date: date | None = None,
    ) -> list[date]:
        """Retorna dias do intervalo; a API informa por data se houve edição."""
        current = start_date_override or self.start_date
        today = end_date or date.today()
        dates: list[date] = []
        while current <= today:
            dates.append(current)
            current += timedelta(days=1)
        return dates

    def list_editions(self, publication_date: date) -> list[Edition]:
        data = self.fetch_json(
            urljoin(BASE_URL, f"{EDITIONS_API_PATH}{publication_date.isoformat()}.json"),
        )
        items = data.get("itens") or []
        editions: list[Edition] = []
        label_counts: dict[str, int] = {}

        for item in items:
            edition_id = item.get("id")
            if not edition_id:
                continue

            label = str(item.get("tipo_edicao_nome") or "Diario Oficial do Espirito Santo").strip()
            if item.get("suplemento") not in (None, "", 0, "0", False):
                label = f"{label} - Suplemento"
            label_counts[label] = label_counts.get(label, 0) + 1
            if label_counts[label] > 1:
                label = f"{label} - Edicao {label_counts[label]}"

            editions.append(
                Edition(
                    publication_date=publication_date,
                    section=label,
                    url=urljoin(BASE_URL, f"portal/edicoes/download/{edition_id}"),
                )
            )
        return editions

    def fetch_json(self, url: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(url, timeout=self.http_timeout_seconds)
                if response.status_code == 404:
                    return {}
                response.raise_for_status()
                payload = response.json()
                if payload.get("erro"):
                    raise RuntimeError(str(payload.get("msg") or "API retornou erro"))
                return payload
            except Exception as exc:
                last_error = exc
            if attempt < self.max_attempts:
                self.sleep_before_retry(attempt, url)
        raise RuntimeError(f"Falha ao consultar {url}: {last_error}") from last_error

    def sleep_before_retry(self, attempt: int, url: str) -> None:
        import time

        seconds = min(self.delay_seconds * attempt * 2, 30)
        print(
            f"Tentativa {attempt} falhou para {url}; tentando de novo em {seconds:.0f}s...",
            file=sys.stderr,
        )
        time.sleep(seconds)

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.fetch_bytes(edition.url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DIO/ES para PDF nao parece PDF: {edition.url}")
        destination.write_bytes(pdf_bytes)
        return destination

    def lake_base_path_for(self, edition: Edition) -> Path:
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y}" / f"{edition.publication_date:%m}" / stem

    def markdown_path_for(self, edition: Edition) -> Path:
        return self.lake_base_path_for(edition).with_suffix(".md")

    def latest_stored_publication_date(self) -> date | None:
        state_lake_dir = self.lake_dir / self.state
        latest_date: date | None = None
        if not state_lake_dir.exists():
            return None
        for markdown_path in state_lake_dir.rglob("*.md"):
            match = MARKDOWN_DATE_RE.search(markdown_path.stem)
            if not match:
                continue
            publication_date = date.fromisoformat(match.group(1))
            if latest_date is None or publication_date > latest_date:
                latest_date = publication_date
        return latest_date


def state_executive_text(text: str) -> str:
    """Remove o caderno municipal, que vem depois do Executivo no PDF diário."""
    markers = [
        match.start()
        for match in re.finditer(r"\bATOS\s+MUNICIPAIS\b", text, flags=re.I)
    ]
    if not markers:
        return text
    return text[: min(markers)]


def parse_acts_from_markdown_file(
    collector: EsDioCollector,
    edition: Edition,
    markdown_path: Path,
) -> list:
    text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    return parse_acts(
        state_executive_text(text),
        collector,
        edition,
        markdown_path,
        regexes=es_regexes,
    )


def collect_es(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    collector = EsDioCollector()
    latest_stored_date = collector.latest_stored_publication_date()
    start_date = (
        start_date_override
        or (collector.start_date if retroativo else latest_stored_date)
        or collector.start_date
    )
    end_date = end_date or date.today()
    if end_date < start_date:
        raise ValueError("A data final do ES nao pode ser anterior a data inicial.")

    dates = [
        publication_date
        for publication_date in collector.list_available_dates(start_date, end_date)
    ]
    if retroativo:
        dates.reverse()

    if retroativo:
        print(
            f"Coleta retroativa ES do presente para tras: {end_date.isoformat()} "
            f"ate {start_date.isoformat()}.",
            file=sys.stderr,
        )
    elif start_date_override is not None:
        print(
            f"Coleta retroativa ES: {start_date.isoformat()} a {end_date.isoformat()}.",
            file=sys.stderr,
        )
    elif latest_stored_date is None:
        print(
            f"Nenhuma edicao ES encontrada no LAKE; iniciando em {start_date.isoformat()}.",
            file=sys.stderr,
        )
    else:
        print(
            f"Ultima edicao ES encontrada no LAKE: {latest_stored_date.isoformat()}. "
            "Retomando a partir dessa data.",
            file=sys.stderr,
        )

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
                print(
                    f"Pulando {publication_date.year}: marcador .year_complete encontrado.",
                    file=sys.stderr,
                )
                skipped_years.add(publication_date.year)
            continue

        if active_year is not None and publication_date.year != active_year:
            finalize_year(active_year)
        active_year = publication_date.year

        try:
            editions = collector.list_editions(publication_date)
        except Exception as exc:
            failed_years.add(publication_date.year)
            print(f"Falha ao listar edicoes de {publication_date.isoformat()}: {exc}", file=sys.stderr)
            continue

        if not editions:
            continue

        print(f"Processando ES {publication_date.isoformat()}...", file=sys.stderr)
        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)
            csv_path = collector.yearly_csv_path_for(edition.publication_date)
            try:
                collector.load_or_create_markdown(edition, markdown_path)
                acts = parse_acts_from_markdown_file(collector, edition, markdown_path)
                total_new_acts += collector.write_csv(csv_path, acts)
            except Exception as exc:
                failed_years.add(publication_date.year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(
                    f"Falha ao processar ES {publication_date.isoformat()} ({edition.section}); seguindo: {exc}",
                    file=sys.stderr,
                )

    finalize_year(active_year)
    return total_new_acts
