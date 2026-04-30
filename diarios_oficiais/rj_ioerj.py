from __future__ import annotations

import base64
import html
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin

from diarios_oficiais.base import Act
from diarios_oficiais.base import BaseGazetteCollector
from diarios_oficiais.base import Edition
from diarios_oficiais.config import TORCH_CUDA_RUNTIME


BASE_URL = "https://www.ioerj.com.br/portal/modules/conteudoonline/"
CALENDAR_URL = urljoin(BASE_URL, "do_seleciona_data.php")


DATE_LINK_RE = re.compile(r'href=["\']do_seleciona_edicao\.php\?data=([^"\']+)["\']', re.I)
EDITION_LINK_RE = re.compile(
    r'<a\s+href=["\'](?P<href>mostra_edicao\.php\?session=[^"\']+)["\'][^>]*>(?P<label>.*?)</a>',
    re.I | re.S,
)
PDF_KEY_RE = re.compile(r'var\s+pd\s*=\s*["\'](?P<key>[A-F0-9-]+)["\']', re.I)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


class RjIoerjCollector(BaseGazetteCollector):
    state = "RJ"
    gazette_code = "DOERJ"
    gazette_name = "Diario Oficial do Estado do Rio de Janeiro"
    section_filter = "Poder Executivo"
    base_url = BASE_URL
    calendar_url = CALENDAR_URL

    def fetch_url_candidates(self, url: str) -> list[str]:
        candidates = [url]
        if url.startswith("https://www.ioerj.com.br/"):
            candidates.append(url.replace("https://", "http://", 1))
        return candidates

    def list_available_dates(self) -> list[date]:
        page = self.fetch_text(self.calendar_url)
        dates: set[date] = set()
        for encoded in DATE_LINK_RE.findall(page):
            decoded = base64.b64decode(encoded).decode("ascii")
            dates.add(datetime.strptime(decoded, "%Y%m%d").date())
        return sorted(dates)

    def list_editions(self, publication_date: date) -> list[Edition]:
        encoded = base64.b64encode(publication_date.strftime("%Y%m%d").encode("ascii")).decode("ascii")
        url = urljoin(self.base_url, f"do_seleciona_edicao.php?data={encoded}")
        page = self.fetch_text(url)
        editions: list[Edition] = []
        for match in EDITION_LINK_RE.finditer(page):
            label = clean_html(match.group("label"))
            editions.append(
                Edition(
                    publication_date=publication_date,
                    section=label,
                    url=urljoin(self.base_url, html.unescape(match.group("href"))),
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
        pdf_url = urljoin(self.base_url, f"mostra_edicao.php?k={key[:12]}P{key[12:]}")
        time.sleep(self.delay_seconds)
        pdf_bytes = self.fetch_bytes(pdf_url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta da IOERJ para PDF nao parece PDF: {pdf_url}")
        eof_index = pdf_bytes.rfind(b"%%EOF")
        if eof_index != -1:
            pdf_bytes = pdf_bytes[: eof_index + len(b"%%EOF") + 1]
        destination.write_bytes(pdf_bytes)
        return destination

    def lake_base_path_for(self, edition: Edition) -> Path:
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y}" / f"{edition.publication_date:%m}" / stem

    def markdown_path_for(self, edition: Edition) -> Path:
        return self.lake_base_path_for(edition).with_suffix(".md")


def clean_html(value: str) -> str:
    value = TAG_RE.sub(" ", value)
    value = html.unescape(value)
    return SPACE_RE.sub(" ", value).strip()


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


def parse_acts(
    text: str,
    collector: RjIoerjCollector,
    edition: Edition,
    markdown_path: Path,
) -> list[Act]:
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
                state=collector.state,
                gazette=collector.gazette_name,
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


def parse_acts_from_markdown_file(
    collector: RjIoerjCollector,
    edition: Edition,
    markdown_path: Path,
) -> list[Act]:
    acts: list[Act] = []
    seen: set[tuple[str, str, str]] = set()

    for block in collector.iter_text_blocks(markdown_path):
        for act in parse_acts(block, collector, edition, markdown_path):
            key = (act.action_type, act.person_name, act.excerpt[:180])
            if key in seen:
                continue
            seen.add(key)
            acts.append(act)
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


def collect_rj() -> int:
    collector = RjIoerjCollector()
    dates = sorted(collector.list_available_dates(), reverse=True)

    total_new_acts = 0
    current_year = date.today().year
    active_year: int | None = None
    skipped_years: set[int] = set()
    for item in dates:
        if collector.is_year_complete(item.year):
            if item.year not in skipped_years:
                print(f"Pulando {item.year}: marcador .year_complete encontrado.", file=sys.stderr)
                skipped_years.add(item.year)
            continue

        if active_year is not None and item.year != active_year and active_year < current_year:
            collector.mark_year_complete(active_year)
        active_year = item.year

        editions = collector.list_editions(item)
        editions = [
            edition
            for edition in editions
            if collector.section_filter.lower() in edition.section.lower()
        ]
        if not editions:
            continue

        print(f"Processando {item.isoformat()}...", file=sys.stderr)
        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)
            csv_path = collector.yearly_csv_path_for(edition.publication_date)
            collector.load_or_create_markdown(edition, markdown_path)
            acts = parse_acts_from_markdown_file(collector, edition, markdown_path)
            total_new_acts += collector.write_csv(csv_path, acts)

    if active_year is not None and active_year < current_year:
        collector.mark_year_complete(active_year)
    return total_new_acts


def main() -> int:
    report_torch_cuda()
    total = collect_rj()
    print(f"{total} atos novos gravados nos CSVs anuais")
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
