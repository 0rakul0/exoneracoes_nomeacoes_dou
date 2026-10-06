"""Coleta o Diário Oficial de Campos dos Goytacazes pelo índice oficial."""

from __future__ import annotations

import re
import sys
from datetime import date
from datetime import timedelta
from pathlib import Path

import pandas as pd

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.rj_ioerj import RjIoerjCollector, edition_slug, parse_acts


INDEX_URL = "https://campos.rj.gov.br/diario-oficial/"
ITEM_RE = re.compile(
    r'<h3 class="ldo-titulo">(?P<title>.*?)</h3>.*?href="(?P<url>[^"]+\.pdf)"', re.S | re.I
)
DATE_RE = re.compile(r"(?:de\s+)?(\d{1,2})\s+de\s+([A-Za-zçÇ]+)\s+de\s+(\d{4})", re.I)
MONTHS = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}


class CamposCollector(RjIoerjCollector):
    state = "RJ"
    municipality = "Campos dos Goytacazes"
    gazette_code = "DOM_CAMPOS"
    gazette_name = "Diário Oficial do Município de Campos dos Goytacazes"

    def list_editions(self, publication_date: date) -> list[Edition]:
        editions: list[Edition] = []
        seen_urls: set[str] = set()
        for page in range(1, 30):
            prior_url_count = len(seen_urls)
            url = INDEX_URL if page == 1 else f"{INDEX_URL}page/{page}/"
            content = self.fetch_text(url)
            found = 0
            for match in ITEM_RE.finditer(content):
                title = re.sub(r"<.*?>", " ", match.group("title"))
                parsed = parse_title_date(title)
                if parsed is None:
                    continue
                found += 1
                if match.group("url") in seen_urls:
                    continue
                seen_urls.add(match.group("url"))
                if parsed == publication_date:
                    editions.append(Edition(parsed, title.strip(), match.group("url")))
            if not found or len(seen_urls) == prior_url_count:
                break
        return editions

    def lake_base_path_for(self, edition: Edition) -> Path:
        return self.lake_dir / self.state / f"{edition.publication_date:%Y}" / f"{edition.publication_date:%m}" / f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"

    def normalize_csv_frame(self, dataframe: pd.DataFrame, fieldnames: list[str]) -> pd.DataFrame:
        dataframe = super().normalize_csv_frame(dataframe, fieldnames)
        for column in ("governador_edicao", "representante_governo", "origem_representante"):
            dataframe[column] = ""
        return dataframe


def parse_title_date(title: str) -> date | None:
    match = DATE_RE.search(title)
    if not match:
        return None
    day, month_name, year = match.groups()
    month = MONTHS.get(month_name.casefold())
    return date(int(year), month, int(day)) if month else None


def parse_acts_from_markdown_file(collector: CamposCollector, edition: Edition, markdown_path: Path):
    text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    return parse_acts(text, collector, edition, markdown_path, municipality_for_position=lambda _: collector.municipality)


def collect_campos(start_date_override: date | None = None, end_date: date | None = None) -> int:
    collector = CamposCollector()
    start_date = start_date_override or collector.start_date
    end_date = end_date or date.today()
    if end_date < start_date:
        raise ValueError("A data final de Campos não pode ser anterior à inicial.")

    total = 0
    current_date = start_date
    while current_date <= end_date:
        try:
            editions = collector.list_editions(current_date)
        except Exception as exc:
            print(exc, file=sys.stderr)
            current_date += timedelta(days=1)
            continue
        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)
            try:
                collector.load_or_create_markdown(edition, markdown_path)
                total += collector.write_csv(
                    collector.yearly_csv_path_for(current_date),
                    parse_acts_from_markdown_file(collector, edition, markdown_path),
                )
            except Exception as exc:
                collector.record_collection_failure(edition, "processar_edicao_municipal", exc)
                print(f"Falha no D.O. de Campos {current_date.isoformat()}: {exc}", file=sys.stderr)
        current_date += timedelta(days=1)
    return total
