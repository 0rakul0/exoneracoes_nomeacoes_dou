"""Coleta atos do Diário Oficial do Município do Rio de Janeiro (D.O. Rio)."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from datetime import timedelta
from pathlib import Path

import pandas as pd

from diarios_oficiais.base import Act
from diarios_oficiais.base import BaseGazetteCollector
from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.rj_ioerj import edition_slug
from diarios_oficiais.estadual.rj_ioerj import parse_acts
from diarios_oficiais.utils_regex import rj_ioerj as rj_regexes


BASE_URL = "https://doweb.rio.rj.gov.br"
EDITIONS_BY_DATE_URL = f"{BASE_URL}/apifront/portal/edicoes/edicoes_from_data/{{date}}.json"
DOWNLOAD_URL = f"{BASE_URL}/portal/edicoes/download/{{edition_id}}"
DEFAULT_START_DATE = date(2026, 1, 1)
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})(?:_|$)")


class RioDeJaneiroMunicipalCollector(BaseGazetteCollector):
    """Coletor do D.O. Rio mantido pela Imprensa da Cidade."""

    state = "RJ"
    municipality = "Rio de Janeiro"
    gazette_code = "DOM_RIO"
    gazette_name = "Diário Oficial do Município do Rio de Janeiro"
    base_url = BASE_URL
    start_date = DEFAULT_START_DATE

    def list_editions(self, publication_date: date) -> list[Edition]:
        url = EDITIONS_BY_DATE_URL.format(date=publication_date.isoformat())
        payload = json.loads(self.fetch_text(url))
        if payload.get("erro"):
            return []

        editions: list[Edition] = []
        for item in payload.get("itens", []):
            edition_id = str(item.get("id") or "").strip()
            if not edition_id:
                continue
            supplement = item.get("suplemento")
            label = "D.O. Rio"
            if supplement not in (None, "", 0, "0"):
                label += f" - Suplemento {supplement}"
            label += f" - Edicao {edition_id}"
            editions.append(
                Edition(
                    publication_date=publication_date,
                    section=label,
                    url=DOWNLOAD_URL.format(edition_id=edition_id),
                )
            )
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.fetch_bytes(edition.url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do D.O. Rio nao parece PDF: {edition.url}")
        destination.write_bytes(pdf_bytes)
        return destination

    def lake_base_path_for(self, edition: Edition) -> Path:
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y}" / f"{edition.publication_date:%m}" / stem

    def markdown_path_for(self, edition: Edition) -> Path:
        return self.lake_base_path_for(edition).with_suffix(".md")

    def latest_stored_publication_date(self) -> date | None:
        latest_date: date | None = None
        for markdown_path in (self.lake_dir / self.state).rglob(f"{self.gazette_code}_*.md"):
            match = MARKDOWN_DATE_RE.search(markdown_path.stem)
            if not match:
                continue
            publication_date = date.fromisoformat(match.group(1))
            if latest_date is None or publication_date > latest_date:
                latest_date = publication_date
        return latest_date

    def normalize_csv_frame(self, dataframe: pd.DataFrame, fieldnames: list[str]) -> pd.DataFrame:
        """Evita atribuir governador estadual a atos municipais."""
        dataframe = super().normalize_csv_frame(dataframe, fieldnames)
        for column in ("governador_edicao", "representante_governo", "origem_representante"):
            dataframe[column] = ""
        return dataframe


def parse_acts_from_markdown_file(
    collector: RioDeJaneiroMunicipalCollector,
    edition: Edition,
    markdown_path: Path,
) -> list[Act]:
    text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    return parse_acts(
        text,
        collector,
        edition,
        markdown_path,
        regexes=rj_regexes,
        municipality_for_position=lambda _: collector.municipality,
    )


def collect_rio_de_janeiro(
    start_date_override: date | None = None,
    end_date: date | None = None,
) -> int:
    """Coleta o intervalo solicitado, retomando da última edição salva por padrão."""
    collector = RioDeJaneiroMunicipalCollector()
    latest_stored_date = collector.latest_stored_publication_date()
    start_date = start_date_override or latest_stored_date or collector.start_date
    end_date = end_date or date.today()
    if end_date < start_date:
        raise ValueError("A data final municipal não pode ser anterior à inicial.")

    total_new_acts = 0
    current_date = start_date
    while current_date <= end_date:
        try:
            editions = collector.list_editions(current_date)
        except Exception as exc:
            print(f"Falha ao listar edições municipais de {current_date.isoformat()}: {exc}", file=sys.stderr)
            current_date += timedelta(days=1)
            continue

        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)
            csv_path = collector.yearly_csv_path_for(edition.publication_date)
            try:
                collector.load_or_create_markdown(edition, markdown_path)
                acts = parse_acts_from_markdown_file(collector, edition, markdown_path)
                total_new_acts += collector.write_csv(csv_path, acts)
            except Exception as exc:
                collector.record_collection_failure(edition, "processar_edicao_municipal", exc)
                print(
                    f"Falha ao processar D.O. Rio de {current_date.isoformat()} ({edition.section}): {exc}",
                    file=sys.stderr,
                )
        current_date += timedelta(days=1)
    return total_new_acts


def main() -> int:
    total = collect_rio_de_janeiro()
    print(f"{total} atos municipais novos gravados nos CSVs anuais")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
