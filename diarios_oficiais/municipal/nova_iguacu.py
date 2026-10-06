"""Coleta o Diário Oficial de Nova Iguaçu pelo portal municipal."""

from __future__ import annotations

import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.rj_ioerj import RjIoerjCollector, edition_slug, parse_acts


BASE_URL = "https://doweb.novaiguacu.rj.gov.br"
DEFAULT_START_DATE = date(2026, 1, 1)
DATE_RE = re.compile(r"Edição nº\s*[^<]*?(\d{2}/\d{2}/\d{4})", re.I)
DOWNLOAD_RE = re.compile(r'data-href="(?P<url>/portal/download/diario-oficial/[^"]+)"', re.I)
META_REDIRECT_RE = re.compile(r'url=(?P<url>[^"\'>\s]+)', re.I)


class NovaIguacuCollector(RjIoerjCollector):
    state = "RJ"
    municipality = "Nova Iguaçu"
    gazette_code = "DOM_NOVA_IGUACU"
    gazette_name = "Diário Oficial do Município de Nova Iguaçu"
    base_url = BASE_URL
    start_date = DEFAULT_START_DATE

    def list_editions(self, publication_date: date) -> list[Edition]:
        formatted = publication_date.strftime("%d-%m-%Y")
        url = f"{BASE_URL}/portal/diario-oficial/1/{formatted}/{formatted}/0/0/"
        page = self.fetch_text(url)
        editions: list[Edition] = []
        seen_urls: set[str] = set()
        for date_match in DATE_RE.finditer(page):
            # O botão de download aparece após o título, dentro do mesmo item.
            block = page[date_match.start():date_match.start() + 5_000]
            download_match = DOWNLOAD_RE.search(block)
            if not download_match:
                continue
            edition_date = datetime.strptime(date_match.group(1), "%d/%m/%Y").date()
            if edition_date != publication_date:
                continue
            extra = "Edição extra" if "dof_edicao_extra" in block else "Diário Oficial"
            download_url = f"{BASE_URL}{download_match.group('url')}"
            if download_url in seen_urls:
                continue
            seen_urls.add(download_url)
            editions.append(Edition(edition_date, extra, download_url))
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        redirect_page = self.fetch_text(edition.url)
        redirect_match = META_REDIRECT_RE.search(redirect_page)
        if not redirect_match:
            raise RuntimeError(f"Não encontrei redirecionamento do PDF: {edition.url}")
        pdf_url = f"{BASE_URL}{redirect_match.group('url')}"
        pdf_bytes = self.fetch_bytes(pdf_url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta não parece PDF: {edition.url}")
        destination.write_bytes(pdf_bytes)
        return destination

    def lake_base_path_for(self, edition: Edition) -> Path:
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y}" / f"{edition.publication_date:%m}" / stem

    def normalize_csv_frame(self, dataframe: pd.DataFrame, fieldnames: list[str]) -> pd.DataFrame:
        dataframe = super().normalize_csv_frame(dataframe, fieldnames)
        for column in ("governador_edicao", "representante_governo", "origem_representante"):
            dataframe[column] = ""
        return dataframe


def collect_nova_iguacu(start_date_override: date | None = None, end_date: date | None = None) -> int:
    collector = NovaIguacuCollector()
    start_date = start_date_override or collector.start_date
    end_date = end_date or date.today()
    total = 0
    current_date = start_date
    while current_date <= end_date:
        try:
            editions = collector.list_editions(current_date)
            for edition in editions:
                markdown_path = collector.markdown_path_for(edition)
                collector.load_or_create_markdown(edition, markdown_path)
                text = markdown_path.read_text(encoding="utf-8", errors="ignore")
                acts = parse_acts(text, collector, edition, markdown_path, municipality_for_position=lambda _: collector.municipality)
                total += collector.write_csv(collector.yearly_csv_path_for(current_date), acts)
        except Exception as exc:
            print(f"Falha no D.O. de Nova Iguaçu {current_date.isoformat()}: {exc}", file=sys.stderr)
        current_date += timedelta(days=1)
    return total
