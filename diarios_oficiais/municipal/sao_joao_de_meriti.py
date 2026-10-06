"""Coleta o Diário Oficial de São João de Meriti."""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.rj_ioerj import RjIoerjCollector, edition_slug, parse_acts

BASE_URL = "https://transparencia.meriti.rj.gov.br"
LIST_URL = f"{BASE_URL}/diario_oficial_get.php"
DEFAULT_START_DATE = date(2026, 1, 1)


class SaoJoaoDeMeritiCollector(RjIoerjCollector):
    state, municipality = "RJ", "São João de Meriti"
    gazette_code = "DOM_SAO_JOAO_DE_MERITI"
    gazette_name = "Diário Oficial de São João de Meriti"
    base_url, start_date = BASE_URL, DEFAULT_START_DATE

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._months: dict[tuple[int, int], list[Edition]] = {}

    def list_editions(self, publication_date: date) -> list[Edition]:
        key = publication_date.year, publication_date.month
        if key not in self._months:
            # O portal estabelece a sessão na tela de consulta antes do AJAX.
            self.session.get(f"{BASE_URL}/diario_oficial_busca.php", timeout=self.http_timeout_seconds).raise_for_status()
            response = self.session.post(LIST_URL, data={"mesano": f"{publication_date.month}/{publication_date.year}", "pagina": "1"}, timeout=self.http_timeout_seconds)
            response.raise_for_status()
            editions = []
            for item in response.json():
                raw_date, code = item.get("DATA_PUBLICACAO", ""), item.get("Codigo_ANEXO")
                if raw_date and code:
                    editions.append(Edition(datetime.strptime(raw_date[:10], "%Y-%m-%d").date(), str(item.get("ANEXO") or "Diário Oficial"), f"{BASE_URL}/diario_oficial_get_anexo.php?codigo={code}"))
            self._months[key] = editions
        return [edition for edition in self._months[key] if edition.publication_date == publication_date]

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = self.fetch_bytes(edition.url)
        if not content.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta não parece PDF: {edition.url}")
        destination.write_bytes(content)
        return destination

    def lake_base_path_for(self, edition: Edition) -> Path:
        return self.lake_dir / self.state / f"{edition.publication_date:%Y}" / f"{edition.publication_date:%m}" / f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"

    def normalize_csv_frame(self, dataframe: pd.DataFrame, fieldnames: list[str]) -> pd.DataFrame:
        dataframe = super().normalize_csv_frame(dataframe, fieldnames)
        for column in ("governador_edicao", "representante_governo", "origem_representante"):
            dataframe[column] = ""
        return dataframe


def collect_sao_joao_de_meriti(start_date_override: date | None = None, end_date: date | None = None) -> int:
    collector, total = SaoJoaoDeMeritiCollector(), 0
    current_date, final_date = start_date_override or collector.start_date, end_date or date.today()
    while current_date <= final_date:
        try:
            for edition in collector.list_editions(current_date):
                markdown_path = collector.markdown_path_for(edition)
                collector.load_or_create_markdown(edition, markdown_path)
                acts = parse_acts(markdown_path.read_text(encoding="utf-8", errors="ignore"), collector, edition, markdown_path, municipality_for_position=lambda _: collector.municipality)
                total += collector.write_csv(collector.yearly_csv_path_for(current_date), acts)
        except Exception as exc:
            print(f"Falha no D.O. de São João de Meriti {current_date}: {exc}", file=sys.stderr)
        current_date += timedelta(days=1)
    return total
