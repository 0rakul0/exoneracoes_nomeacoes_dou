from __future__ import annotations

from datetime import date
from pathlib import Path

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.pb_power import PbPowerCollector, collect_pb_power


BASE_URL = "https://app.tjpb.jus.br/dje/rest/ultimosdiarios/diario/"


class PbDjeCollector(PbPowerCollector):
    gazette_code = "DJEPB"
    gazette_name = "Diario da Justica Eletronico da Paraiba"

    def edition_url(self, publication_date: date) -> str:
        return f"{BASE_URL}{publication_date:%d_%m_%Y}.pdf"

    def list_editions(self, publication_date: date) -> list[Edition]:
        url = self.edition_url(publication_date)
        response = self.session.get(url, stream=True, timeout=self.http_timeout_seconds)
        response.raise_for_status()
        try:
            marker = response.raw.read(5)
        finally:
            response.close()
        if marker != b"%PDF-":
            return []
        return [Edition(publication_date=publication_date, section=f"DJE PB {publication_date:%d-%m-%Y}", url=url)]

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.fetch_bytes(edition.url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DJE/PB para PDF nao parece PDF: {edition.url}")
        destination.write_bytes(pdf_bytes)
        return destination


def collect_pb_dje(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    return collect_pb_power(
        PbDjeCollector,
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
