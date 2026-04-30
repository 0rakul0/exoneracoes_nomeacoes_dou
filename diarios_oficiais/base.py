from __future__ import annotations

import csv
import sys
import time
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

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
    spacy_person: str = ""
    spacy_entities: str = ""
    name_parse_reliable: str = ""


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


@lru_cache(maxsize=2)
def get_spacy_model(model_name: str) -> Any | None:
    try:
        import spacy
    except ImportError:
        print("spaCy nao instalado; a coleta vai apenas anotar validacao indisponivel.", file=sys.stderr)
        return None

    try:
        return spacy.load(model_name)
    except OSError:
        print(
            f"Modelo spaCy '{model_name}' nao encontrado; "
            f"instale com: python -m spacy download {model_name}",
            file=sys.stderr,
        )
        return None


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
    enable_spacy_validation = config.ENABLE_SPACY_VALIDATION
    spacy_model_name = config.SPACY_MODEL
    spacy_mode = config.SPACY_MODE

    def __init__(
        self,
        delay_seconds: float | None = None,
        max_attempts: int | None = None,
    ) -> None:
        self.delay_seconds = delay_seconds if delay_seconds is not None else self.http_delay_seconds
        self.max_attempts = max_attempts if max_attempts is not None else self.http_max_attempts
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        self.spacy_model = (
            get_spacy_model(self.spacy_model_name) if self.enable_spacy_validation else None
        )

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
            return self.extract_pdfium_text_to_markdown(pdf_path)
        except Exception as exc:
            print(
                f"pypdfium2 falhou em {pdf_path.name}; usando pypdf: {exc}",
                file=sys.stderr,
            )
            return self.extract_pypdf_text_to_markdown(pdf_path)

    def extract_pdfium_text_to_markdown(self, pdf_path: Path) -> str:
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:
            raise RuntimeError("pypdfium2 nao esta instalado.") from exc

        document = pdfium.PdfDocument(str(pdf_path))
        pages: list[str] = []
        try:
            for index in range(len(document)):
                page = document.get_page(index)
                try:
                    text_page = page.get_textpage()
                    try:
                        text = text_page.get_text_range() or ""
                    finally:
                        text_page.close()
                finally:
                    page.close()
                pages.append(f"## Pagina {index + 1}\n\n{text.strip()}")
        finally:
            document.close()
        return "\n\n".join(pages).strip()

    def extract_pypdf_text_to_markdown(self, pdf_path: Path) -> str:
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

    def year_complete_marker_path(self, year: int) -> Path:
        return self.lake_dir / self.state / str(year) / ".year_complete"

    def mark_year_complete(self, year: int) -> None:
        marker_path = self.year_complete_marker_path(year)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text("complete\n", encoding="utf-8")

    def validate_person_name_with_spacy(self, person_name: str) -> tuple[str, str, str]:
        if not self.enable_spacy_validation:
            return "desativado", "", "indisponivel"
        if self.spacy_model is None:
            return "indisponivel", "", "indisponivel"
        if not person_name.strip():
            return "nao", "", "nao"

        normalized_name = self.normalize_entity_text(person_name)
        entities: list[str] = []
        variants = [person_name, person_name.title()]

        for variant in variants:
            doc = self.spacy_model(variant)
            for entity in doc.ents:
                entity_text = entity.text.strip()
                label = entity.label_.upper()
                if not entity_text:
                    continue
                entities.append(f"{entity_text}:{label}")
                normalized_entity = self.normalize_entity_text(entity_text)
                if label in {"PER", "PERSON"} and (
                    normalized_entity == normalized_name
                    or normalized_entity in normalized_name
                    or normalized_name in normalized_entity
                ):
                    return "sim", "|".join(dict.fromkeys(entities)), "sim"

        return "nao", "|".join(dict.fromkeys(entities)), "nao"

    @staticmethod
    def normalize_entity_text(value: str) -> str:
        import unicodedata

        value = unicodedata.normalize("NFKD", value or "")
        value = "".join(char for char in value if not unicodedata.combining(char))
        return " ".join(value.upper().split())

    def write_csv(self, path: Path, acts: Iterable[Act]) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "estado",
            "diario",
            "data_publicacao",
            "caderno",
            "tipo_ato",
            "nome",
            "spacy_pessoa",
            "spacy_entidades",
            "nome_parse_confiavel",
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
                    if not normalized_row["spacy_pessoa"] and normalized_row["nome"]:
                        (
                            normalized_row["spacy_pessoa"],
                            normalized_row["spacy_entidades"],
                            normalized_row["nome_parse_confiavel"],
                        ) = self.validate_person_name_with_spacy(normalized_row["nome"])
                    if self.spacy_mode == "filter" and normalized_row["spacy_pessoa"] == "nao":
                        continue
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
            spacy_person = act.spacy_person
            spacy_entities = act.spacy_entities
            name_parse_reliable = act.name_parse_reliable
            if not spacy_person and not name_parse_reliable:
                spacy_person, spacy_entities, name_parse_reliable = self.validate_person_name_with_spacy(
                    act.person_name
                )
            if self.spacy_mode == "filter" and spacy_person == "nao":
                continue

            row = {
                "estado": act.state,
                "diario": act.gazette,
                "data_publicacao": act.publication_date.isoformat(),
                "caderno": act.section,
                "tipo_ato": act.action_type,
                "nome": act.person_name,
                "spacy_pessoa": spacy_person,
                "spacy_entidades": spacy_entities,
                "nome_parse_confiavel": name_parse_reliable,
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
