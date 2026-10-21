from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.pb_power import PbPowerCollector, collect_pb_power


BASE_URL = "https://auniao.pb.gov.br/"
YEAR_PATH = "servicos/doe"
MONTH_NAMES = {
    1: "janeiro",
    2: "fevereiro",
    3: "marco",
    4: "abril",
    5: "maio",
    6: "junho",
    7: "julho",
    8: "agosto",
    9: "setembro",
    10: "outubro",
    11: "novembro",
    12: "dezembro",
}
DATE_RE = re.compile(r"(?:diario-oficial|Di.rio Oficial)[-_ ](\d{2})[-_](\d{2})[-_](\d{4})", re.I)


class PbDoeCollector(PbPowerCollector):
    gazette_code = "DOEPB"
    gazette_name = "Diario Oficial do Estado da Paraiba"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._editions_by_date: dict[date, list[str]] = {}
        self._loaded_months: set[tuple[int, int]] = set()

    def _load_month(self, year: int, month: int) -> None:
        key = (year, month)
        if key in self._loaded_months:
            return
        self._loaded_months.add(key)
        month_url = urljoin(BASE_URL, f"{YEAR_PATH}/{year}/{MONTH_NAMES[month]}")
        response = self.session.get(month_url, timeout=self.http_timeout_seconds)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        for anchor in soup.find_all("a", href=True):
            href = urljoin(response.url, str(anchor["href"]))
            label = " ".join(anchor.get_text(" ", strip=True).split())
            match = DATE_RE.search(f"{label} {href}")
            if not match:
                continue
            edition_date = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            if edition_date.year != year or edition_date.month != month:
                continue
            if href.endswith("/view"):
                href = href[:-5]
            if href not in self._editions_by_date.setdefault(edition_date, []):
                self._editions_by_date[edition_date].append(href)

    def list_editions(self, publication_date: date) -> list[Edition]:
        self._load_month(publication_date.year, publication_date.month)
        editions: list[Edition] = []
        for index, url in enumerate(self._editions_by_date.get(publication_date, []), start=1):
            suffix = f" {index}" if len(self._editions_by_date[publication_date]) > 1 else ""
            editions.append(
                Edition(
                    publication_date=publication_date,
                    section=f"Diario Oficial PB{suffix}",
                    url=url,
                )
            )
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.fetch_bytes(edition.url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DOE/PB para PDF nao parece PDF: {edition.url}")
        destination.write_bytes(pdf_bytes)
        return destination


def collect_pb(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    return collect_pb_power(
        PbDoeCollector,
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
