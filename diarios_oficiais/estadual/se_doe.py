from __future__ import annotations

from datetime import date
from pathlib import Path

from diarios_oficiais import config
from diarios_oficiais.base import Edition
from diarios_oficiais.estadual._daily_pdf import DailyPdfCollector, collect_daily, parse_daily_acts
from diarios_oficiais.utils_regex import se_doe as regexes


BASE_URL = "https://iose.se.gov.br"


class SeDoeCollector(DailyPdfCollector):
    state = "SE"
    gazette_code = "DOESE"
    gazette_name = "Diario Oficial do Estado de Sergipe"
    start_date = date.fromisoformat(config.SE_START_DATE)

    def list_editions(self, publication_date: date) -> list[Edition]:
        url = f"{BASE_URL}/apifront/portal/edicoes/edicoes_from_data/{publication_date.isoformat()}.json"
        response = self.session.get(url, timeout=self.http_timeout_seconds)
        response.raise_for_status()
        editions = []
        for item in response.json().get("itens") or []:
            identifier = item.get("id")
            if not identifier:
                continue
            supplement = " Suplemento" if item.get("suplemento") else ""
            section = f"Diario Oficial SE{supplement}"
            editions.append(Edition(publication_date, section, f"{BASE_URL}/portal/edicoes/download/{identifier}"))
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = self.fetch_bytes(edition.url)
        if not content.startswith(b"%PDF"):
            raise RuntimeError(
                "A IOSE retornou uma página HTML em vez do PDF; o download do SE pode exigir "
                "acesso/certificado no portal oficial."
            )
        destination.write_bytes(content)
        return destination


def parse_acts_from_markdown_file(collector, edition, markdown_path):
    return parse_daily_acts(collector, edition, markdown_path, regexes)


def collect_se(**kwargs):
    return collect_daily(SeDoeCollector, regexes, "SE", **kwargs)
