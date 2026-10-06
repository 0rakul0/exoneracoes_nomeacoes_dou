"""Coleta o Diário Oficial da Prefeitura de São Gonçalo."""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.rj_ioerj import RjIoerjCollector, edition_slug, parse_acts


DEFAULT_START_DATE = date(1998, 2, 3)
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")


class SaoGoncaloCollector(RjIoerjCollector):
    """Usa o arquivo diário publicado no portal oficial da prefeitura."""

    state = "RJ"
    municipality = "São Gonçalo"
    gazette_code = "DOM_SAO_GONCALO"
    gazette_name = "Diário Oficial do Município de São Gonçalo"
    base_url = "https://do.pmsg.rj.gov.br"
    start_date = DEFAULT_START_DATE

    @staticmethod
    def pdf_url_for(publication_date: date) -> str:
        return f"https://do.pmsg.rj.gov.br/diario/{publication_date:%Y_%m_%d}.pdf"

    def list_editions(self, publication_date: date) -> list[Edition]:
        url = self.pdf_url_for(publication_date)
        try:
            response = self.session.head(url, timeout=self.http_timeout_seconds, allow_redirects=True)
            if response.status_code == 404:
                return []
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(f"Falha ao consultar D.O. de São Gonçalo: {url}: {exc}") from exc
        return [Edition(publication_date=publication_date, section="Diário Oficial", url=url)]

    def lake_base_path_for(self, edition: Edition) -> Path:
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y}" / f"{edition.publication_date:%m}" / stem

    def latest_stored_publication_date(self) -> date | None:
        latest_date: date | None = None
        for markdown_path in (self.lake_dir / self.state).rglob(f"{self.gazette_code}_*.md"):
            match = MARKDOWN_DATE_RE.search(markdown_path.stem)
            if match:
                candidate = date.fromisoformat(match.group(1))
                latest_date = max(latest_date, candidate) if latest_date else candidate
        return latest_date

    def normalize_csv_frame(self, dataframe: pd.DataFrame, fieldnames: list[str]) -> pd.DataFrame:
        dataframe = super().normalize_csv_frame(dataframe, fieldnames)
        for column in ("governador_edicao", "representante_governo", "origem_representante"):
            dataframe[column] = ""
        return dataframe


def collect_sao_goncalo(start_date_override: date | None = None, end_date: date | None = None) -> int:
    collector = SaoGoncaloCollector()
    start_date = start_date_override or collector.latest_stored_publication_date() or collector.start_date
    end_date = end_date or date.today()
    if end_date < start_date:
        raise ValueError("A data final de São Gonçalo não pode ser anterior à inicial.")

    total = 0
    current_date = start_date
    while current_date <= end_date:
        try:
            editions = collector.list_editions(current_date)
        except Exception as exc:
            print(exc, file=sys.stderr)
            current_date += timedelta(days=1)
            continue
        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)
            try:
                collector.load_or_create_markdown(edition, markdown_path)
                text = markdown_path.read_text(encoding="utf-8", errors="ignore")
                acts = parse_acts(
                    text, collector, edition, markdown_path,
                    municipality_for_position=lambda _: collector.municipality,
                )
                total += collector.write_csv(collector.yearly_csv_path_for(current_date), acts)
            except Exception as exc:
                collector.record_collection_failure(edition, "processar_edicao_municipal", exc)
                print(f"Falha no D.O. de São Gonçalo {current_date.isoformat()}: {exc}", file=sys.stderr)
        current_date += timedelta(days=1)
    return total
