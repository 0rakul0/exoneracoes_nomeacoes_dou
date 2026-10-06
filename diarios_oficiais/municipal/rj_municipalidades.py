"""Coleta a Parte IV — Municipalidades do Diário Oficial do Estado do RJ."""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.rj_ioerj import RjIoerjCollector
from diarios_oficiais.estadual.rj_ioerj import parse_acts


MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")
DEFAULT_START_DATE = date(2026, 1, 1)
MUNICIPALITY_HEADING_RE = re.compile(
    r"\bMUNIC[ÍI]PIO\s+DE\s+(?P<name>[A-ZÀ-Ý][A-ZÀ-Ý'’ -]{2,70}?)"
    r"(?=\s+(?:PREFEITURA|C[ÂA]MARA|ATOS|DECRETO|LEI|PORTARIA|EDITAL|AVISO)\b)",
    re.I,
)


class RjMunicipalidadesCollector(RjIoerjCollector):
    """Aproveita o portal da IOERJ para cobrir municípios da Parte IV."""

    gazette_code = "DOERJ_MUNICIPALIDADES"
    gazette_name = "Diário Oficial do Estado do Rio de Janeiro — Parte IV Municipalidades"
    section_filter = "Municipalidades"
    start_date = DEFAULT_START_DATE

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
        """Não associa atos municipais ao governador estadual."""
        dataframe = super().normalize_csv_frame(dataframe, fieldnames)
        for column in ("governador_edicao", "representante_governo", "origem_representante"):
            dataframe[column] = ""
        return dataframe


def collect_rj_municipalidades(
    start_date_override: date | None = None,
    end_date: date | None = None,
) -> int:
    collector = RjMunicipalidadesCollector()
    latest_stored_date = collector.latest_stored_publication_date()
    start_date = start_date_override or latest_stored_date or collector.start_date
    end_date = end_date or date.today()
    if end_date < start_date:
        raise ValueError("A data final municipal não pode ser anterior à inicial.")

    total_new_acts = 0
    for publication_date in collector.list_available_dates():
        if not start_date <= publication_date <= end_date:
            continue
        try:
            editions = [
                edition
                for edition in collector.list_editions(publication_date)
                if collector.section_filter.casefold() in edition.section.casefold()
            ]
        except Exception as exc:
            print(f"Falha ao listar Parte IV de {publication_date.isoformat()}: {exc}", file=sys.stderr)
            continue

        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)
            try:
                collector.load_or_create_markdown(edition, markdown_path)
                acts = parse_acts_from_markdown_file(collector, edition, markdown_path)
                total_new_acts += collector.write_csv(
                    collector.yearly_csv_path_for(edition.publication_date), acts
                )
            except Exception as exc:
                collector.record_collection_failure(edition, "processar_parte_iv_municipalidades", exc)
                print(
                    f"Falha ao processar Parte IV de {publication_date.isoformat()}: {exc}",
                    file=sys.stderr,
                )
    return total_new_acts


def parse_acts_from_markdown_file(
    collector: RjMunicipalidadesCollector,
    edition: Edition,
    markdown_path: Path,
):
    text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    normalized = re.sub(r"\s+", " ", text)
    markers = [
        (match.start(), normalize_municipality_name(match.group("name")))
        for match in MUNICIPALITY_HEADING_RE.finditer(normalized)
    ]

    def municipality_for_position(position: int) -> str:
        candidates = [name for marker_position, name in markers if marker_position <= position]
        return candidates[-1] if candidates else ""

    return parse_acts(
        text,
        collector,
        edition,
        markdown_path,
        municipality_for_position=municipality_for_position,
    )


def normalize_municipality_name(value: str) -> str:
    return " ".join(token.capitalize() for token in value.split())
