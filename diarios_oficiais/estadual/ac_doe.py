from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.ac_power import AcPowerCollector, collect_ac_power


BASE_URL = "https://diario.ac.gov.br/"
DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


class AcDoeCollector(AcPowerCollector):
    gazette_code = "DOEAC"
    gazette_name = "Diario Oficial do Estado do Acre"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._editions_by_date: dict[date, list[tuple[str, str]]] = {}
        self._loaded_months: set[tuple[int, int]] = set()

    def _add_row(self, row, response_url: str) -> None:
        cells = row.find_all("td")
        if len(cells) < 2:
            return
        raw_date = " ".join(cells[0].get_text(" ", strip=True).split())
        match = DATE_RE.fullmatch(raw_date)
        if not match:
            return
        publication_date = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        anchor = cells[1].find("a", href=True)
        if anchor is None:
            return
        url = urljoin(response_url, str(anchor["href"]))
        description = " ".join(anchor.get_text(" ", strip=True).split()) or "Caderno"
        item = (url, description)
        if item not in self._editions_by_date.setdefault(publication_date, []):
            self._editions_by_date[publication_date].append(item)

    def _load_month(self, year: int, month: int) -> None:
        key = (year, month)
        if key in self._loaded_months:
            return
        self._loaded_months.add(key)
        response = self.session.post(BASE_URL, data={"mesano": f"{month:02d}/{year}"}, timeout=self.http_timeout_seconds)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        for row in soup.find_all("tr"):
            self._add_row(row, response.url)

        # A edição do dia corrente aparece no destaque da página inicial,
        # antes de entrar na listagem mensal fechada.
        if (year, month) == (date.today().year, date.today().month):
            current = self.session.get(BASE_URL, timeout=self.http_timeout_seconds)
            current.raise_for_status()
            current_soup = BeautifulSoup(current.content, "html.parser")
            for anchor in current_soup.find_all("a", href=True):
                if "download.php" not in str(anchor["href"]):
                    continue
                text = " ".join(anchor.get_text(" ", strip=True).split())
                match = re.search(r"(\d{1,2}) de ([A-Za-zçÇãÃõÕéÉ]+) de (\d{4})", text, re.I)
                if not match:
                    continue
                month_names = {
                    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3,
                    "abril": 4, "maio": 5, "junho": 6, "julho": 7,
                    "agosto": 8, "setembro": 9, "outubro": 10,
                    "novembro": 11, "dezembro": 12,
                }
                current_date = date(int(match.group(3)), month_names.get(match.group(2).lower(), 0), int(match.group(1)))
                if current_date.month == month and current_date.year == year:
                    self._editions_by_date.setdefault(current_date, []).append(
                        (urljoin(current.url, str(anchor["href"])), "Caderno atual")
                    )

    def list_editions(self, publication_date: date) -> list[Edition]:
        self._load_month(publication_date.year, publication_date.month)
        entries = self._editions_by_date.get(publication_date, [])
        editions: list[Edition] = []
        for index, (url, description) in enumerate(entries, start=1):
            suffix = f" {index}" if len(entries) > 1 else ""
            editions.append(
                Edition(
                    publication_date=publication_date,
                    section=f"DOE AC {description}{suffix}",
                    url=url,
                )
            )
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.fetch_bytes(edition.url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DOE/AC para PDF nao parece PDF: {edition.url}")
        destination.write_bytes(pdf_bytes)
        return destination


def collect_ac(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    return collect_ac_power(
        AcDoeCollector,
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
