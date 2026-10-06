from __future__ import annotations

import sys
import time
from datetime import date
from datetime import timedelta
from pathlib import Path

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.rj_ioerj import edition_slug
from diarios_oficiais.estadual.rj_ioerj import parse_acts_from_markdown_file
from diarios_oficiais.estadual.sp_doe import SpDoeCollector
from diarios_oficiais.utils_regex import sp_doe as sp_regexes


LEGACY_BASE_URL = "https://diariooficial.imprensaoficial.com.br/doflash/prototipo"
LEGACY_SECTION_SLUG = "exec2"
LEGACY_SECTION_NAME = "Executivo - Seção II"
PORTUGUESE_MONTHS = (
    "Janeiro",
    "Fevereiro",
    "Marco",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)


class SpLegacyCollector(SpDoeCollector):
    """Coleta páginas do acervo legado do DOESP, anterior ao PDF diário atual."""

    legacy_base_url = LEGACY_BASE_URL
    legacy_section_slug = LEGACY_SECTION_SLUG
    legacy_section_name = LEGACY_SECTION_NAME

    def page_url_for(self, publication_date: date, page_number: int) -> str:
        month_name = PORTUGUESE_MONTHS[publication_date.month - 1]
        return (
            f"{self.legacy_base_url}/{publication_date:%Y}/{month_name}/"
            f"{publication_date:%d}/{self.legacy_section_slug}/pdf/pg_{page_number:04d}.pdf"
        )

    def markdown_path_for_page(self, publication_date: date, page_number: int) -> Path:
        stem = (
            f"{self.gazette_code}_{edition_slug(self.legacy_section_name)}_"
            f"{publication_date.isoformat()}_PAGINA_{page_number:04d}"
        )
        return (
            self.lake_dir
            / self.state
            / f"{publication_date:%Y}"
            / f"{publication_date:%m}"
            / f"{stem}.md"
        )

    def pdf_cache_path_for_page(self, publication_date: date, page_number: int) -> Path:
        return (
            self.cache_dir
            / self.state
            / "legado"
            / f"{publication_date:%Y}"
            / f"{publication_date:%m}"
            / f"{publication_date.isoformat()}_pagina_{page_number:04d}.pdf"
        )

    def download_legacy_page(self, publication_date: date, page_number: int) -> tuple[Edition, Path] | None:
        url = self.page_url_for(publication_date, page_number)
        edition = Edition(
            publication_date=publication_date,
            section=self.legacy_section_name,
            url=url,
        )
        pdf_path = self.pdf_cache_path_for_page(publication_date, page_number)
        if pdf_path.exists():
            return edition, pdf_path

        response = self.session.get(url, timeout=self.http_timeout_seconds)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        pdf_bytes = response.content
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do acervo legado nao parece PDF: {url}")

        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)
        return edition, pdf_path


def iter_dates(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def collect_sp_legacy(start_date: date, end_date: date, max_pages: int = 1_000) -> int:
    """Coleta o caderno Executivo - Seção II no acervo legado, por página."""
    if end_date < start_date:
        raise ValueError("A data final deve ser igual ou posterior à data inicial.")
    if max_pages < 1:
        raise ValueError("max_pages deve ser maior que zero.")

    collector = SpLegacyCollector()
    total_new_acts = 0
    for publication_date in iter_dates(start_date, end_date):
        print(f"Processando acervo legado SP {publication_date.isoformat()}...", file=sys.stderr)
        for page_number in range(1, max_pages + 1):
            try:
                downloaded = collector.download_legacy_page(publication_date, page_number)
            except Exception as exc:
                print(
                    f"Falha ao baixar pagina {page_number} de {publication_date.isoformat()}: {exc}",
                    file=sys.stderr,
                )
                break
            if downloaded is None:
                break

            edition, pdf_path = downloaded
            markdown_path = collector.markdown_path_for_page(publication_date, page_number)
            csv_path = collector.yearly_csv_path_for(publication_date)
            try:
                if markdown_path.exists():
                    markdown = markdown_path.read_text(encoding="utf-8")
                else:
                    markdown = collector.convert_pdf_to_markdown(pdf_path, markdown_path)
                if markdown.strip():
                    acts = parse_acts_from_markdown_file(
                        collector,
                        edition,
                        markdown_path,
                        regexes=sp_regexes,
                    )
                    total_new_acts += collector.write_csv(csv_path, acts)
            except Exception as exc:
                collector.record_collection_failure(edition, "processar_pagina_legado", exc)
                print(
                    f"Falha ao processar pagina {page_number} de {publication_date.isoformat()}: {exc}",
                    file=sys.stderr,
                )
            time.sleep(collector.delay_seconds)
        else:
            raise RuntimeError(
                f"Limite de {max_pages} paginas atingido em {publication_date.isoformat()}; "
                "a coleta foi interrompida para evitar um percurso incompleto."
            )

    return total_new_acts
