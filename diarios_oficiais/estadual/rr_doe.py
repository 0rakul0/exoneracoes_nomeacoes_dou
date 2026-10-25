from __future__ import annotations

import html
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from diarios_oficiais import config
from diarios_oficiais.base import Edition
from diarios_oficiais.estadual._daily_pdf import DailyPdfCollector, collect_daily, parse_daily_acts
from diarios_oficiais.utils_regex import rr_doe as regexes


BASE_URL = "https://imprensaoficial.rr.gov.br"
FORM_RE = re.compile(r"<form\b[^>]*action=\"[^\"]*_visualizar-doe/[^\"]*\"[^>]*>(.*?)</form>", re.I | re.S)
INPUT_RE = re.compile(r"<input\b[^>]*name=\"([^\"]+)\"[^>]*value=\"([^\"]*)\"", re.I)
DOE_RE = re.compile(r"(?:^|/)doe-(\d{8})\.pdf$", re.I)


class RrDoeCollector(DailyPdfCollector):
    state = "RR"
    gazette_code = "DOERR"
    gazette_name = "Diario Oficial do Estado de Roraima"
    start_date = date.fromisoformat(config.RR_START_DATE)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loaded_months: set[tuple[int, int]] = set()
        self._editions_by_date: dict[date, list[Edition]] = {}

    def _load_month(self, year: int, month: int):
        key = (year, month)
        if key in self._loaded_months:
            return
        self._loaded_months.add(key)
        url = f"{BASE_URL}/_visualizar-mes/?ano={year}&mes={month:02d}"
        content = self.fetch_text(url)
        for fragment in FORM_RE.findall(content):
            values = {name: html.unescape(value) for name, value in INPUT_RE.findall(fragment)}
            doe = values.get("doe", "")
            match = DOE_RE.search(doe)
            if not match:
                continue
            publication_date = datetime.strptime(match.group(1), "%Y%m%d").date()
            query = urlencode(values)
            self._editions_by_date.setdefault(publication_date, []).append(
                Edition(publication_date, "Diario Oficial RR", f"{BASE_URL}/_visualizar-doe/?{query}")
            )

    def list_editions(self, publication_date: date) -> list[Edition]:
        self._load_month(publication_date.year, publication_date.month)
        return self._editions_by_date.get(publication_date, [])

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        params = {key: values[0] for key, values in parse_qs(urlparse(edition.url).query).items()}
        response = self.session.post(
            f"{BASE_URL}/_visualizar-doe/",
            data=params,
            timeout=self.http_timeout_seconds,
        )
        response.raise_for_status()
        content = response.content
        if not content.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DOE/RR não parece PDF: {edition.url}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return destination


def parse_acts_from_markdown_file(collector, edition, markdown_path):
    return parse_daily_acts(collector, edition, markdown_path, regexes)


def collect_rr(**kwargs):
    return collect_daily(RrDoeCollector, regexes, "RR", **kwargs)
