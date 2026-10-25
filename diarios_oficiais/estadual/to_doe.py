from __future__ import annotations

import html
import re
from datetime import date

import requests

from diarios_oficiais import config
from diarios_oficiais.base import Edition
from diarios_oficiais.estadual._daily_pdf import DailyPdfCollector, collect_daily, parse_daily_acts
from diarios_oficiais.utils_regex import to_doe as regexes


BASE_URL = "https://diariooficial.to.gov.br"
DATE_RE = re.compile(r"(\d{2}/\d{2}/\d{4})")
DOWNLOAD_RE = re.compile(r"href=\"(https://doe\.to\.gov\.br/diario/\d+/download)\"[^>]*title=\"Edição\s+(\d+)\"", re.I)


class ToDoeCollector(DailyPdfCollector):
    state = "TO"
    gazette_code = "DOETO"
    gazette_name = "Diario Oficial do Estado do Tocantins"
    start_date = date.fromisoformat(config.TO_START_DATE)

    def list_editions(self, publication_date: date) -> list[Edition]:
        formatted = publication_date.strftime("%d/%m/%Y")
        url = f"{BASE_URL}/busca?por=data&data-inicial={formatted}&data-final={formatted}"
        response = self.session.get(url, timeout=self.http_timeout_seconds)
        response.raise_for_status()
        editions = []
        for fragment in re.findall(r"<tr\b.*?</tr>", response.text, re.I | re.S):
            if formatted not in html.unescape(fragment):
                continue
            match = DOWNLOAD_RE.search(fragment)
            if not match:
                continue
            download_url, number = match.groups()
            editions.append(Edition(publication_date, f"Diario Oficial TO {number}", download_url))
        return editions


def parse_acts_from_markdown_file(collector, edition, markdown_path):
    return parse_daily_acts(collector, edition, markdown_path, regexes)


def collect_to(**kwargs):
    return collect_daily(ToDoeCollector, regexes, "TO", **kwargs)
