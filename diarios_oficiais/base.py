from __future__ import annotations

import csv
import sys
import time
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import requests

from diarios_oficiais import config


@dataclass(frozen=True)
class Edition:
    publication_date: date
    section: str
    url: str


@dataclass(frozen=True)
class Act:
    state: str
    gazette: str
    publication_date: date
    section: str
    action_type: str
    person_name: str
    role: str
    agency: str
    excerpt: str
    source_url: str
    text_path: str


@lru_cache(maxsize=2)
def get_docling_converter(enable_ocr: bool = False):
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter
        from docling.document_converter import PdfFormatOption
    except ImportError as exc:
        raise RuntimeError("Docling nao esta instalado. Rode: python -m pip install -r requirements.txt") from exc

    pipeline_options = PdfPipelineOptions()
    pipeline_options.accelerator_options.device = config.DOCLING_DEVICE
    pipeline_options.accelerator_options.num_threads = config.DOCLING_NUM_THREADS
    pipeline_options.do_ocr = enable_ocr
    pipeline_options.do_table_structure = config.DOCLING_DO_TABLE_STRUCTURE
    pipeline_options.do_code_enrichment = config.DOCLING_DO_CODE_ENRICHMENT
    pipeline_options.do_formula_enrichment = config.DOCLING_DO_FORMULA_ENRICHMENT
    pipeline_options.do_picture_classification = config.DOCLING_DO_PICTURE_CLASSIFICATION
    pipeline_options.do_picture_description = config.DOCLING_DO_PICTURE_DESCRIPTION
    pipeline_options.force_backend_text = config.DOCLING_FORCE_BACKEND_TEXT
    pipeline_options.generate_page_images = config.DOCLING_GENERATE_PAGE_IMAGES
    pipeline_options.generate_picture_images = config.DOCLING_GENERATE_PICTURE_IMAGES
    pipeline_options.generate_table_images = config.DOCLING_GENERATE_TABLE_IMAGES
    pipeline_options.generate_parsed_pages = config.DOCLING_GENERATE_PARSED_PAGES
    pipeline_options.layout_batch_size = config.DOCLING_LAYOUT_BATCH_SIZE
    pipeline_options.ocr_batch_size = config.DOCLING_OCR_BATCH_SIZE
    pipeline_options.table_batch_size = config.DOCLING_TABLE_BATCH_SIZE
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )


class BaseGazetteCollector:
    state = ""
    gazette_code = ""
    gazette_name = ""
    enable_ocr = config.ENABLE_OCR

    lake_dir = config.LAKE_DIR
    output_dir = config.OUTPUT_DIR
    cache_dir = config.CACHE_DIR
    user_agent = config.USER_AGENT

    http_delay_seconds = config.HTTP_DELAY_SECONDS
    http_max_attempts = config.HTTP_MAX_ATTEMPTS
    http_timeout_seconds = config.HTTP_TIMEOUT_SECONDS

    markdown_parse_block_size = config.MARKDOWN_PARSE_BLOCK_SIZE
    markdown_parse_overlap_size = config.MARKDOWN_PARSE_OVERLAP_SIZE

    def __init__(
        self,
        delay_seconds: float | None = None,
        max_attempts: int | None = None,
    ) -> None:
        self.delay_seconds = delay_seconds if delay_seconds is not None else self.http_delay_seconds
        self.max_attempts = max_attempts if max_attempts is not None else self.http_max_attempts
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

    def fetch_text(self, url: str) -> str:
        data = self.fetch_bytes(url)
        return data.decode("utf-8", errors="replace")

    def fetch_bytes(self, url: str) -> bytes:
        last_error: Exception | None = None
        candidates = self.fetch_url_candidates(url)

        for attempt in range(1, self.max_attempts + 1):
            for candidate in candidates:
                try:
                    response = self.session.get(candidate, timeout=self.http_timeout_seconds)
                    response.raise_for_status()
                    return response.content
                except requests.RequestException as exc:
                    last_error = exc
            if attempt < self.max_attempts:
                sleep_seconds = min(self.delay_seconds * attempt * 2, 30)
                print(
                    f"Tentativa {attempt} falhou para {url}; tentando de novo em {sleep_seconds:.0f}s...",
                    file=sys.stderr,
                )
                time.sleep(sleep_seconds)

        raise RuntimeError(f"Falha ao baixar {url}: {last_error}") from last_error

    def fetch_url_candidates(self, url: str) -> list[str]:
        return [url]

    def convert_pdf_to_markdown(self, pdf_path: Path, markdown_path: Path) -> str:
        if not config.USE_DOCLING:
            markdown = self.extract_pdf_text_to_markdown(pdf_path)
        else:
            converter = get_docling_converter(enable_ocr=self.enable_ocr)
            try:
                result = converter.convert(str(pdf_path))
                markdown = result.document.export_to_markdown()
            except Exception as exc:
                print(
                    f"Docling falhou em {pdf_path.name}; usando extracao simples com pypdf: {exc}",
                    file=sys.stderr,
                )
                markdown = self.extract_pdf_text_to_markdown(pdf_path)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown, encoding="utf-8")
        return markdown

    def extract_pdf_text_to_markdown(self, pdf_path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("pypdf nao esta instalado; nao foi possivel aplicar fallback de texto.") from exc

        reader = PdfReader(str(pdf_path))
        pages: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append(f"## Pagina {index}\n\n{text.strip()}")
        return "\n\n".join(pages).strip()

    def load_or_create_markdown(self, edition: Edition, markdown_path: Path) -> str:
        if markdown_path.exists():
            return markdown_path.read_text(encoding="utf-8")

        temporary_pdf_path = self.cache_dir / self.state / f"{markdown_path.stem}.pdf"
        if not temporary_pdf_path.exists():
            self.download_edition_pdf(edition, temporary_pdf_path)
        return self.convert_pdf_to_markdown(temporary_pdf_path, markdown_path)

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        raise NotImplementedError

    def iter_text_blocks(self, path: Path) -> Iterable[str]:
        overlap = ""
        with path.open(encoding="utf-8") as file:
            while True:
                block = file.read(self.markdown_parse_block_size)
                if not block:
                    if overlap:
                        yield overlap
                    break
                yield overlap + block
                overlap = (overlap + block)[-self.markdown_parse_overlap_size:]

    def yearly_csv_path_for(self, publication_date: date) -> Path:
        return self.output_dir / self.state / f"{self.gazette_code}_{publication_date:%Y}.csv"

    def write_csv(self, path: Path, acts: Iterable[Act]) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "estado",
            "diario",
            "data_publicacao",
            "caderno",
            "tipo_ato",
            "nome",
            "cargo",
            "orgao",
            "trecho",
            "fonte_url",
            "arquivo_markdown",
        ]
        rows: list[dict[str, str]] = []
        seen: set[tuple[str, str, str, str]] = set()

        if path.exists():
            with path.open(newline="", encoding="utf-8") as file:
                for row in csv.DictReader(file):
                    normalized_row = {field: row.get(field, "") for field in fieldnames}
                    key = (
                        normalized_row["data_publicacao"],
                        normalized_row["tipo_ato"],
                        normalized_row["nome"],
                        normalized_row["trecho"][:180],
                    )
                    rows.append(normalized_row)
                    seen.add(key)

        new_count = 0
        for act in acts:
            row = {
                "estado": act.state,
                "diario": act.gazette,
                "data_publicacao": act.publication_date.isoformat(),
                "caderno": act.section,
                "tipo_ato": act.action_type,
                "nome": act.person_name,
                "cargo": act.role,
                "orgao": act.agency,
                "trecho": act.excerpt,
                "fonte_url": act.source_url,
                "arquivo_markdown": act.text_path,
            }
            key = (row["data_publicacao"], row["tipo_ato"], row["nome"], row["trecho"][:180])
            if key in seen:
                continue
            rows.append(row)
            seen.add(key)
            new_count += 1

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return new_count
