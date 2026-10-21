from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.ba_power import BaPowerCollector, collect_ba_power


BASE_URL = "https://egbanet.egba.ba.gov.br/"
SUBTHEME_PATH = "alba/"
EDITIONS_API_PATH = "apifront/portal/edicoes/edicoes_from_data/"
class BaDoelCollector(BaPowerCollector):
    state = "BA"
    gazette_code = "DOELBA"
    gazette_name = "Diario Oficial Eletronico do Legislativo da Bahia"

    def list_editions(self, publication_date: date) -> list[Edition]:
        url = urljoin(BASE_URL, f"{SUBTHEME_PATH}{EDITIONS_API_PATH}{publication_date.isoformat()}.json")
        response = self.session.get(url, params={"subtheme": "alba"}, timeout=self.http_timeout_seconds)
        response.raise_for_status()
        data = response.json()
        if data.get("erro"):
            return []
        editions: list[Edition] = []
        for item in data.get("itens") or []:
            edition_id = item.get("id")
            if not edition_id:
                continue
            label = str(item.get("tipo_edicao_nome") or "Diario Oficial Legislativo BA").strip()
            number = str(item.get("numero") or edition_id)
            if item.get("suplemento") not in (None, "", 0, "0", False):
                label += " - Suplemento"
            editions.append(
                Edition(
                    publication_date=publication_date,
                    section=f"{label} {number}",
                    url=urljoin(BASE_URL, f"{SUBTHEME_PATH}portal/edicoes/download/{edition_id}"),
                )
            )
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.fetch_bytes(edition.url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DOEL/BA para PDF nao parece PDF: {edition.url}")
        destination.write_bytes(pdf_bytes)
        return destination


def collect_ba_doel(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    return collect_ba_power(
        BaDoelCollector,
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
