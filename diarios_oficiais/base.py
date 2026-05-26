from __future__ import annotations

import sys
import time
import re
from dataclasses import dataclass
from datetime import date
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable

import requests
import pandas as pd

from diarios_oficiais import config
from diarios_oficiais.governadores import (
    governador_da_edicao,
    nome_representante_governo,
    origem_representante_governo,
)


UNICODE_ESCAPE_RE = re.compile(r"/U([0-9A-Fa-f]{4})")


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
    functional_id: str
    role: str
    agency: str
    excerpt: str
    source_url: str
    text_path: str
    signer_name: str = ""
    signer_role: str = ""
    signer_category: str = ""
    edition_governor: str = ""
    government_representative: str = ""
    representative_origin: str = ""
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


def preload_ocr_models() -> None:
    if not config.USE_DOCLING or not config.ENABLE_OCR or not config.PRELOAD_OCR_MODELS:
        return

    print("Carregando modelos OCR antes da coleta...", file=sys.stderr)
    get_docling_converter(enable_ocr=True)
    print("Modelos OCR carregados.", file=sys.stderr)


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
    docling_page_chunk_size = config.DOCLING_PAGE_CHUNK_SIZE
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
            try:
                markdown = self.convert_pdf_to_markdown_with_docling_chunks(pdf_path, enable_ocr=False)
                if self.enable_ocr and self.markdown_needs_ocr(markdown, pdf_path):
                    print(
                        f"Texto embutido insuficiente em {pdf_path.name}; acionando OCR...",
                        file=sys.stderr,
                    )
                    markdown = self.convert_pdf_to_markdown_with_docling_chunks(pdf_path, enable_ocr=True)
            except Exception as exc:
                print(
                    f"Docling falhou em {pdf_path.name}; usando extracao simples com pypdf: {exc}",
                    file=sys.stderr,
                )
                markdown = self.extract_pdf_text_to_markdown(pdf_path)
        markdown = self.clean_markdown_text(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown, encoding="utf-8")
        return markdown

    def clean_markdown_text(self, markdown: str) -> str:
        return UNICODE_ESCAPE_RE.sub(
            lambda match: chr(int(match.group(1), 16)),
            markdown,
        )

    def markdown_needs_ocr(self, markdown: str, pdf_path: Path) -> bool:
        text = re.sub(r"<!--.*?-->", " ", markdown, flags=re.S)
        text = re.sub(r"\s+", "", text)
        if len(text) < config.OCR_FALLBACK_MIN_CHARS:
            return True

        try:
            from pypdf import PdfReader
        except ImportError:
            return False

        try:
            page_count = max(1, len(PdfReader(str(pdf_path)).pages))
        except Exception:
            return False

        return len(text) < page_count * config.OCR_FALLBACK_MIN_CHARS_PER_PAGE

    def convert_pdf_to_markdown_with_docling_chunks(self, pdf_path: Path, enable_ocr: bool) -> str:
        try:
            from pypdf import PdfReader
            from pypdf import PdfWriter
        except ImportError as exc:
            raise RuntimeError("pypdf nao esta instalado; nao foi possivel dividir PDF em blocos.") from exc

        chunk_size = max(1, int(self.docling_page_chunk_size))
        reader = PdfReader(str(pdf_path))
        page_count = len(reader.pages)
        converter = get_docling_converter(enable_ocr=enable_ocr)
        markdown_parts: list[str] = []
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        with TemporaryDirectory(prefix=f"{pdf_path.stem}_docling_", dir=self.cache_dir) as temporary_dir:
            temporary_root = Path(temporary_dir)
            for start in range(0, page_count, chunk_size):
                end = min(start + chunk_size, page_count)
                chunk_path = temporary_root / f"{pdf_path.stem}_p{start + 1:04d}_{end:04d}.pdf"
                writer = PdfWriter()
                for page_index in range(start, end):
                    writer.add_page(reader.pages[page_index])
                with chunk_path.open("wb") as file:
                    writer.write(file)

                print(
                    f"Docling {pdf_path.name}: paginas {start + 1}-{end} de {page_count} "
                    f"({'OCR' if enable_ocr else 'texto embutido'})",
                    file=sys.stderr,
                )
                result = converter.convert(str(chunk_path))
                chunk_markdown = result.document.export_to_markdown().strip()
                if chunk_markdown:
                    markdown_parts.append(f"<!-- paginas {start + 1}-{end} -->\n\n{chunk_markdown}")

        return "\n\n".join(markdown_parts).strip()

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
            markdown = markdown_path.read_text(encoding="utf-8")
            cleaned_markdown = self.clean_markdown_text(markdown)
            if cleaned_markdown != markdown:
                markdown_path.write_text(cleaned_markdown, encoding="utf-8")
            return cleaned_markdown

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

    def is_year_complete(self, year: int) -> bool:
        return self.year_complete_marker_path(year).exists()

    def mark_year_complete(self, year: int) -> None:
        marker_path = self.year_complete_marker_path(year)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text("complete\n", encoding="utf-8")

    def record_collection_failure(self, edition: Edition, stage: str, error: Exception) -> None:
        path = self.lake_dir / self.state / f"{edition.publication_date:%Y}" / "falhas_coleta.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        row = pd.DataFrame(
            [
                {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "data_publicacao": edition.publication_date.isoformat(),
                    "caderno": edition.section,
                    "etapa": stage,
                    "url": edition.url,
                    "erro": str(error),
                }
            ]
        )
        header = not path.exists()
        row.to_csv(path, mode="a", header=header, index=False, encoding="utf-8", lineterminator="\n")

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
            "id_funcional",
            "assinante",
            "cargo_assinante",
            "categoria_assinante",
            "governador_edicao",
            "representante_governo",
            "origem_representante",
            "spacy_pessoa",
            "spacy_entidades",
            "nome_parse_confiavel",
            "cargo",
            "orgao",
            "trecho",
            "fonte_url",
            "arquivo_markdown",
        ]
        existing_df = self.read_existing_csv_frame(path, fieldnames)
        dedup_subset = ["data_publicacao", "tipo_ato", "nome", "_trecho_chave"]
        existing_key_df = existing_df.assign(_trecho_chave=existing_df["trecho"].str.slice(0, 180))
        existing_keys = set(map(tuple, existing_key_df[dedup_subset].to_numpy()))
        seen_keys = set(existing_keys)

        new_rows: list[dict[str, str]] = []
        for act in acts:
            row_key = (
                act.publication_date.isoformat(),
                act.action_type,
                act.person_name,
                act.excerpt[:180],
            )
            if row_key in seen_keys:
                continue

            spacy_person = act.spacy_person
            spacy_entities = act.spacy_entities
            name_parse_reliable = act.name_parse_reliable
            if not spacy_person and not name_parse_reliable:
                spacy_person, spacy_entities, name_parse_reliable = self.validate_person_name_with_spacy(
                    act.person_name
                )
            if self.spacy_mode == "filter" and spacy_person == "nao":
                continue

            new_rows.append(
                {
                    "estado": act.state,
                    "diario": act.gazette,
                    "data_publicacao": act.publication_date.isoformat(),
                    "caderno": act.section,
                    "tipo_ato": act.action_type,
                    "nome": act.person_name,
                    "id_funcional": act.functional_id,
                    "assinante": act.signer_name,
                    "cargo_assinante": act.signer_role,
                    "categoria_assinante": act.signer_category,
                    "governador_edicao": act.edition_governor,
                    "representante_governo": nome_representante_governo(act.edition_governor),
                    "origem_representante": origem_representante_governo(act.edition_governor),
                    "spacy_pessoa": spacy_person,
                    "spacy_entidades": spacy_entities,
                    "nome_parse_confiavel": name_parse_reliable,
                    "cargo": act.role,
                    "orgao": act.agency,
                    "trecho": act.excerpt,
                    "fonte_url": act.source_url,
                    "arquivo_markdown": act.text_path,
                }
            )
            seen_keys.add(row_key)

        if not new_rows and path.exists():
            return 0

        new_df = pd.DataFrame(new_rows, columns=fieldnames)
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        combined_df = self.normalize_csv_frame(combined_df, fieldnames)
        if self.spacy_mode == "filter":
            combined_df = combined_df[combined_df["spacy_pessoa"] != "nao"].copy()
        combined_df["_trecho_chave"] = combined_df["trecho"].str.slice(0, 180)
        combined_df = combined_df.drop_duplicates(subset=dedup_subset, keep="first")
        final_keys = set(map(tuple, combined_df[dedup_subset].to_numpy()))
        new_count = len(final_keys - existing_keys)
        combined_df = combined_df.drop(columns=["_trecho_chave"])

        temporary_path = path.with_name(f"{path.name}.tmp")
        for attempt in range(1, 4):
            try:
                combined_df.to_csv(temporary_path, index=False, encoding="utf-8", lineterminator="\n")
                temporary_path.replace(path)
                break
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(0.5 * attempt)
        return new_count

    def read_existing_csv_frame(self, path: Path, fieldnames: list[str]) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame(columns=fieldnames)
        dataframe = pd.read_csv(path, dtype=str, keep_default_na=False)
        return self.normalize_csv_frame(dataframe, fieldnames)

    def normalize_csv_frame(self, dataframe: pd.DataFrame, fieldnames: list[str]) -> pd.DataFrame:
        dataframe = dataframe.copy()
        for field in fieldnames:
            if field not in dataframe.columns:
                dataframe[field] = ""
        dataframe = dataframe[fieldnames].fillna("").astype(str)

        missing_spacy_mask = (dataframe["spacy_pessoa"] == "") & (dataframe["nome"] != "")
        for index, row in dataframe.loc[missing_spacy_mask].iterrows():
            (
                dataframe.at[index, "spacy_pessoa"],
                dataframe.at[index, "spacy_entidades"],
                dataframe.at[index, "nome_parse_confiavel"],
            ) = self.validate_person_name_with_spacy(row["nome"])
        markdown_governor_mask = dataframe["arquivo_markdown"] != ""
        for index, row in dataframe.loc[markdown_governor_mask].iterrows():
            dataframe.at[index, "governador_edicao"] = governador_da_edicao(row["arquivo_markdown"])
        for index, row in dataframe.iterrows():
            governor = row["governador_edicao"]
            dataframe.at[index, "representante_governo"] = nome_representante_governo(governor)
            dataframe.at[index, "origem_representante"] = origem_representante_governo(governor)
        return dataframe
