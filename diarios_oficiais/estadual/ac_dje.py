from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.ac_power import AcPowerCollector, collect_ac_power


BASE_URL = "https://diario.tjac.jus.br/"
DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
LONG_DATE_RE = re.compile(r"^(\d{1,2})\s+de\s+([A-Za-zçÇãÃõÕéÉ]+)\s+de\s+(\d{4})$", re.I)
MONTH_NAMES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3,
    "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}


class AcDjeCollector(AcPowerCollector):
    gazette_code = "DJEAC"
    gazette_name = "Diario da Justica Eletronico do Acre"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._editions_by_date: dict[date, list[tuple[str, str]]] = {}
        self._loaded_months: set[tuple[int, int]] = set()

    def _load_month(self, year: int, month: int) -> None:
        key = (year, month)
        if key in self._loaded_months:
            return
        self._loaded_months.add(key)
        response = self.session.get(
            urljoin(BASE_URL, "edicoes.php"),
            params={"Ano": str(year), "Mes": str(month)},
            timeout=self.http_timeout_seconds,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        # O HTML legado agrupa várias linhas dentro de uma célula malformada;
        # os links de texto (Diario=...) e os links PDF continuam em sequência.
        anchors = soup.find_all("a", href=True)
        for index, anchor in enumerate(anchors):
            diary_href = str(anchor["href"])
            if "Diario=" not in diary_href:
                continue
            raw_date = " ".join(anchor.get_text(" ", strip=True).split())
            match = DATE_RE.fullmatch(raw_date)
            long_match = LONG_DATE_RE.fullmatch(raw_date)
            if match:
                publication_date = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            elif long_match:
                month = MONTH_NAMES.get(long_match.group(2).lower())
                if month is None:
                    continue
                publication_date = date(int(long_match.group(3)), month, int(long_match.group(1)))
            else:
                continue
            pdf_anchor = next(
                (candidate for candidate in anchors[index + 1:] if "PDF=" in str(candidate["href"])),
                None,
            )
            if pdf_anchor is None:
                continue
            parsed = parse_qs(urlparse(diary_href).query)
            diary_number = (parsed.get("Diario") or [""])[0]
            label = f"DJE AC {diary_number}" if diary_number else f"DJE AC {publication_date:%d-%m-%Y}"
            url = urljoin(response.url, str(pdf_anchor["href"]))
            item = (url, label)
            if item not in self._editions_by_date.setdefault(publication_date, []):
                self._editions_by_date[publication_date].append(item)

    def list_editions(self, publication_date: date) -> list[Edition]:
        self._load_month(publication_date.year, publication_date.month)
        return [
            Edition(publication_date=publication_date, section=label, url=url)
            for url, label in self._editions_by_date.get(publication_date, [])
        ]

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.fetch_bytes(edition.url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DJE/AC para PDF nao parece PDF: {edition.url}")
        destination.write_bytes(pdf_bytes)
        return destination


def collect_ac_dje(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    return collect_ac_power(
        AcDjeCollector,
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
