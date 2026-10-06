"""Coleta o Boletim Oficial de Duque de Caxias pelo portal de Transparência."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.rj_ioerj import RjIoerjCollector, edition_slug, parse_acts


DEFAULT_START_DATE = date(2026, 1, 1)
LIST_URL = "https://transparencia.duquedecaxias.rj.gov.br/diario_oficial_get.php"
DOWNLOAD_URL = "https://transparencia.duquedecaxias.rj.gov.br/diario_oficial_get_anexo.php?codigo={code}"


class DuqueDeCaxiasCollector(RjIoerjCollector):
    state = "RJ"
    municipality = "Duque de Caxias"
    gazette_code = "DOM_DUQUE_DE_CAXIAS"
    gazette_name = "Boletim Oficial do Município de Duque de Caxias"
    base_url = "https://transparencia.duquedecaxias.rj.gov.br"
    start_date = DEFAULT_START_DATE

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._editions_by_month: dict[tuple[int, int], list[Edition]] = {}

    def list_editions(self, publication_date: date) -> list[Edition]:
        key = (publication_date.year, publication_date.month)
        if key not in self._editions_by_month:
            response = self.session.post(
                LIST_URL,
                data={"mesano": f"{publication_date:%m/%Y}", "pagina": "1"},
                timeout=self.http_timeout_seconds,
            )
            response.raise_for_status()
            raw_editions = response.json()
            editions: list[Edition] = []
            for item in raw_editions:
                raw_date = item.get("DATA_PUBLICACAO", "")
                code = item.get("Codigo_ANEXO")
                if not raw_date or not code:
                    continue
                edition_date = datetime.strptime(raw_date[:10], "%Y-%m-%d").date()
                label = str(item.get("ANEXO") or item.get("DESCRICAO") or "Boletim Oficial")
                editions.append(
                    Edition(
                        publication_date=edition_date,
                        section=label,
                        url=DOWNLOAD_URL.format(code=code),
                    )
                )
            self._editions_by_month[key] = editions
        return [edition for edition in self._editions_by_month[key] if edition.publication_date == publication_date]

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.fetch_bytes(edition.url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta não parece PDF: {edition.url}")
        destination.write_bytes(pdf_bytes)
        return destination

    def lake_base_path_for(self, edition: Edition) -> Path:
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y}" / f"{edition.publication_date:%m}" / stem

    def normalize_csv_frame(self, dataframe: pd.DataFrame, fieldnames: list[str]) -> pd.DataFrame:
        dataframe = super().normalize_csv_frame(dataframe, fieldnames)
        for column in ("governador_edicao", "representante_governo", "origem_representante"):
            dataframe[column] = ""
        return dataframe


def collect_duque_de_caxias(start_date_override: date | None = None, end_date: date | None = None) -> int:
    collector = DuqueDeCaxiasCollector()
    start_date = start_date_override or collector.start_date
    end_date = end_date or date.today()
    if end_date < start_date:
        raise ValueError("A data final de Duque de Caxias não pode ser anterior à inicial.")

    total = 0
    current_date = start_date
    while current_date <= end_date:
        try:
            editions = collector.list_editions(current_date)
        except Exception as exc:
            print(f"Falha ao listar D.O. de Duque de Caxias: {exc}", file=sys.stderr)
            current_date += timedelta(days=1)
            continue
        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)
            try:
                collector.load_or_create_markdown(edition, markdown_path)
                text = markdown_path.read_text(encoding="utf-8", errors="ignore")
                acts = parse_acts(text, collector, edition, markdown_path, municipality_for_position=lambda _: collector.municipality)
                total += collector.write_csv(collector.yearly_csv_path_for(current_date), acts)
            except Exception as exc:
                collector.record_collection_failure(edition, "processar_edicao_municipal", exc)
                print(f"Falha no B.O. de Duque de Caxias {current_date.isoformat()}: {exc}", file=sys.stderr)
        current_date += timedelta(days=1)
    return total
