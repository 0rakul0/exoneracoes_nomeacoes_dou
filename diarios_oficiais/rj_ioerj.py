from __future__ import annotations

import base64
import csv
import html
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import requests


STATE = "RJ"
GAZETTE_CODE = "DOERJ"
GAZETTE_NAME = "Diario Oficial do Estado do Rio de Janeiro"
LAKE_DIR = Path("LAKE")
CACHE_DIR = Path(".cache/diarios")
SECTION_FILTER = "Poder Executivo"
DATES_PER_RUN = 1
ENABLE_OCR = False
DOCLING_DEVICE = "cuda"
TORCH_CUDA_RUNTIME = "11.8"
BASE_URL = "https://www.ioerj.com.br/portal/modules/conteudoonline/"
CALENDAR_URL = urljoin(BASE_URL, "do_seleciona_data.php")
USER_AGENT = "exoneracoes-nomeacoes-dou/0.1 (+pesquisa civica)"


DATE_LINK_RE = re.compile(r'href=["\']do_seleciona_edicao\.php\?data=([^"\']+)["\']', re.I)
EDITION_LINK_RE = re.compile(
    r'<a\s+href=["\'](?P<href>mostra_edicao\.php\?session=[^"\']+)["\'][^>]*>(?P<label>.*?)</a>',
    re.I | re.S,
)
PDF_KEY_RE = re.compile(r'var\s+pd\s*=\s*["\'](?P<key>[A-F0-9-]+)["\']', re.I)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


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


class IoerjClient:
    def __init__(self, delay_seconds: float = 1.0) -> None:
        self.delay_seconds = delay_seconds
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def fetch_text(self, url: str) -> str:
        data = self.fetch_bytes(url)
        return data.decode("utf-8", errors="replace")

    def fetch_bytes(self, url: str) -> bytes:
        last_error: Exception | None = None
        candidates = [url]
        if url.startswith("https://www.ioerj.com.br/"):
            candidates.append(url.replace("https://", "http://", 1))

        for candidate in candidates:
            try:
                response = self.session.get(candidate, timeout=60)
                response.raise_for_status()
                return response.content
            except requests.RequestException as exc:
                last_error = exc

        raise RuntimeError(f"Falha ao baixar {url}: {last_error}") from last_error

    def list_available_dates(self) -> list[date]:
        page = self.fetch_text(CALENDAR_URL)
        dates: set[date] = set()
        for encoded in DATE_LINK_RE.findall(page):
            decoded = base64.b64decode(encoded).decode("ascii")
            dates.add(datetime.strptime(decoded, "%Y%m%d").date())
        return sorted(dates)

    def list_editions(self, publication_date: date) -> list[Edition]:
        encoded = base64.b64encode(publication_date.strftime("%Y%m%d").encode("ascii")).decode("ascii")
        url = urljoin(BASE_URL, f"do_seleciona_edicao.php?data={encoded}")
        page = self.fetch_text(url)
        editions: list[Edition] = []
        for match in EDITION_LINK_RE.finditer(page):
            label = clean_html(match.group("label"))
            editions.append(
                Edition(
                    publication_date=publication_date,
                    section=label,
                    url=urljoin(BASE_URL, html.unescape(match.group("href"))),
                )
            )
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        page = self.fetch_text(edition.url)
        key_match = PDF_KEY_RE.search(page)
        if not key_match:
            raise RuntimeError(f"Nao encontrei chave do PDF na pagina: {edition.url}")
        key = key_match.group("key")
        pdf_url = urljoin(BASE_URL, f"mostra_edicao.php?k={key[:12]}P{key[12:]}")
        time.sleep(self.delay_seconds)
        pdf_bytes = self.fetch_bytes(pdf_url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta da IOERJ para PDF nao parece PDF: {pdf_url}")
        eof_index = pdf_bytes.rfind(b"%%EOF")
        if eof_index != -1:
            pdf_bytes = pdf_bytes[: eof_index + len(b"%%EOF") + 1]
        destination.write_bytes(pdf_bytes)
        return destination


def clean_html(value: str) -> str:
    value = TAG_RE.sub(" ", value)
    value = html.unescape(value)
    return SPACE_RE.sub(" ", value).strip()


def convert_pdf_to_markdown(pdf_path: Path, markdown_path: Path, enable_ocr: bool = False) -> str:
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter
        from docling.document_converter import PdfFormatOption
    except ImportError as exc:
        raise RuntimeError("Docling nao esta instalado. Rode: python -m pip install -r requirements.txt") from exc

    pipeline_options = PdfPipelineOptions()
    pipeline_options.accelerator_options.device = DOCLING_DEVICE
    pipeline_options.do_ocr = enable_ocr
    pipeline_options.do_table_structure = False
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    result = converter.convert(str(pdf_path))
    markdown = result.document.export_to_markdown()
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown, encoding="utf-8")
    return markdown


def load_or_create_markdown(
    client: IoerjClient,
    edition: Edition,
    markdown_path: Path,
    enable_ocr: bool,
) -> str:
    if markdown_path.exists():
        return markdown_path.read_text(encoding="utf-8")

    temporary_pdf_path = CACHE_DIR / STATE / f"{markdown_path.stem}.pdf"
    try:
        client.download_edition_pdf(edition, temporary_pdf_path)
        return convert_pdf_to_markdown(temporary_pdf_path, markdown_path, enable_ocr=enable_ocr)
    finally:
        temporary_pdf_path.unlink(missing_ok=True)


ACT_WINDOW_RE = re.compile(
    r"\b(?P<action>EXONERAR|NOMEAR)\b(?P<body>.{0,1200}?)(?=\b(?:EXONERAR|NOMEAR|DESIGNAR|TORNAR SEM EFEITO|RESOLVE|DECRETO|ATO DO|SECRETARIA|Art\.|$))",
    re.I | re.S,
)
NAME_AFTER_ACTION_RE = re.compile(
    r"(?:^|,\s*)(?P<name>[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ.'-]+(?:\s+(?:DE|DA|DO|DAS|DOS|E|[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ.'-]+)){1,9})(?=,|\s+para\s+|\s+do\s+|\s+da\s+)",
    re.I,
)
ROLE_RE = re.compile(
    r"(?:para exercer|do|da)\s+(?:o\s+|a\s+)?(?P<role>cargo(?:\s+em\s+comissao)?|funcao|função|emprego|chefia|direcao|direção|assessoria)[^,.;\n]{0,220}",
    re.I,
)
AGENCY_RE = re.compile(r"\b(?:da|do)\s+(Secretaria|Subsecretaria|Fundacao|Fundação|Instituto|Departamento|Gabinete|Superintendencia|Superintendência|Autarquia)\b[^,.;\n]{0,180}", re.I)


def parse_acts(text: str, edition: Edition, markdown_path: Path) -> list[Act]:
    normalized = SPACE_RE.sub(" ", text)
    acts: list[Act] = []
    seen: set[tuple[str, str, str]] = set()

    for match in ACT_WINDOW_RE.finditer(normalized):
        action = match.group("action").upper()
        body = match.group("body").strip(" ,.;:-")
        excerpt = f"{action} {body}".strip()
        person_name = extract_person_name(body)
        if not person_name:
            continue

        role_match = ROLE_RE.search(body)
        agency_match = AGENCY_RE.search(body)
        role = clean_piece(role_match.group(0)) if role_match else ""
        agency = clean_piece(agency_match.group(0)) if agency_match else ""
        key = (action, person_name, excerpt[:180])
        if key in seen:
            continue
        seen.add(key)

        acts.append(
            Act(
                state=STATE,
                gazette=GAZETTE_NAME,
                publication_date=edition.publication_date,
                section=edition.section,
                action_type="nomeacao" if action == "NOMEAR" else "exoneracao",
                person_name=person_name,
                role=role,
                agency=agency,
                excerpt=excerpt[:900],
                source_url=edition.url,
                text_path=str(markdown_path),
            )
        )
    return acts


def extract_person_name(body: str) -> str:
    direct = direct_person_name(body)
    if direct:
        return direct

    for match in NAME_AFTER_ACTION_RE.finditer(body):
        candidate = clean_piece(match.group("name"))
        candidate = normalize_name(candidate)
        if valid_person_name(candidate):
            return candidate
    return ""


def direct_person_name(body: str) -> str:
    candidate_area = re.split(
        r"\s*,?\s*ID\s+FUNC|\s+para\s+exer|\s+para\s+exercer|\s+do\s+cargo|\s+da\s+fun[cç][aã]o",
        body,
        maxsplit=1,
        flags=re.I,
    )[0]
    candidate_area = re.sub(r"^(?:a\s+pedido|com\s+validade[^,]*|louvado[^,]*|louvada[^,]*)\s*,\s*", "", candidate_area, flags=re.I)
    if "," in candidate_area:
        candidate_area = candidate_area.rsplit(",", 1)[-1]
    candidate = normalize_name(candidate_area)
    return candidate if valid_person_name(candidate) else ""


def normalize_name(value: str) -> str:
    value = clean_piece(value)
    value = re.sub(r"(?<=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])-\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", "", value, flags=re.I)
    return SPACE_RE.sub(" ", value).strip(" ,.;:-").upper()


def valid_person_name(candidate: str) -> bool:
    tokens = candidate.upper().split()
    if len(tokens) < 2 or len(tokens) > 14:
        return False
    if tokens[0] in {"A", "O", "COM", "SEM", "PARA", "DO", "DA", "NO", "NA", "SIMBOLO", "SÍMBOLO"}:
        return False
    blocked = {"CARGO", "FUNCAO", "FUNÇÃO", "SECRETARIA", "ESTADO", "SIMBOLO", "SÍMBOLO", "PROCESSO"}
    return not any(token in blocked for token in tokens[:3])


def clean_piece(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip(" ,.;:-")


def write_csv(path: Path, acts: Iterable[Act]) -> int:
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


def edition_slug(section: str) -> str:
    normalized = html.unescape(section)
    replacements = {
        "ç": "c",
        "Ç": "C",
        "ã": "a",
        "Ã": "A",
        "á": "a",
        "Á": "A",
        "à": "a",
        "À": "A",
        "â": "a",
        "Â": "A",
        "é": "e",
        "É": "E",
        "ê": "e",
        "Ê": "E",
        "í": "i",
        "Í": "I",
        "ó": "o",
        "Ó": "O",
        "ô": "o",
        "Ô": "O",
        "õ": "o",
        "Õ": "O",
        "ú": "u",
        "Ú": "U",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", normalized).strip("_").upper()
    return slug or "caderno"


def lake_base_path_for(edition: Edition) -> Path:
    stem = f"{GAZETTE_CODE}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
    return LAKE_DIR / STATE / f"{edition.publication_date:%Y}" / f"{edition.publication_date:%m}" / stem


def markdown_path_for(edition: Edition) -> Path:
    return lake_base_path_for(edition).with_suffix(".md")


def csv_path_for(edition: Edition) -> Path:
    return lake_base_path_for(edition).with_suffix(".csv")


def collect_next_rj() -> int:
    client = IoerjClient()
    dates = client.list_available_dates()

    total_new_acts = 0
    processed_dates = 0
    for item in dates:
        editions = client.list_editions(item)
        editions = [edition for edition in editions if SECTION_FILTER.lower() in edition.section.lower()]
        missing_editions = [
            edition
            for edition in editions
            if not markdown_path_for(edition).exists() or not csv_path_for(edition).exists()
        ]
        if not missing_editions:
            continue

        print(f"Processando {item.isoformat()}...", file=sys.stderr)
        for edition in missing_editions:
            markdown_path = markdown_path_for(edition)
            csv_path = csv_path_for(edition)
            text = load_or_create_markdown(client, edition, markdown_path, enable_ocr=ENABLE_OCR)
            acts = parse_acts(text, edition, markdown_path)
            total_new_acts += write_csv(csv_path, acts)

        processed_dates += 1
        if processed_dates >= DATES_PER_RUN:
            break
    return total_new_acts


def main() -> int:
    report_torch_cuda()
    total = collect_next_rj()
    print(f"{total} atos novos gravados nos CSVs diarios")
    return 0


def report_torch_cuda() -> None:
    try:
        import torch
    except ImportError:
        print("PyTorch nao instalado; instale requirements-cuda.txt antes de requirements.txt.", file=sys.stderr)
        return

    cuda_available = torch.cuda.is_available()
    cuda_version = torch.version.cuda or "indisponivel"
    device_name = torch.cuda.get_device_name(0) if cuda_available else "nenhuma GPU CUDA disponivel"
    print(
        f"PyTorch {torch.__version__}; CUDA runtime: {cuda_version}; "
        f"cuda_available={cuda_available}; device={device_name}; expected_runtime={TORCH_CUDA_RUNTIME}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
