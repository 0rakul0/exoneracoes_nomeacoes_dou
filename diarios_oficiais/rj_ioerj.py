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
from diarios_oficiais.utils_regex.common import ACT_WINDOW_RE
from diarios_oficiais.utils_regex.common import AGENCY_RE
from diarios_oficiais.utils_regex.common import FUNCTIONAL_ID_RE
from diarios_oficiais.utils_regex.common import NAME_AFTER_ACTION_RE
from diarios_oficiais.utils_regex.common import ROLE_RE
from diarios_oficiais.utils_regex.common import SIGNER_CATEGORIES
from diarios_oficiais.utils_regex.common import SIGNER_RE
from diarios_oficiais.utils_regex.common import SPACE_RE
from diarios_oficiais.utils_regex.common import TAG_RE
from diarios_oficiais.utils_regex.common import DATE_LINK_RE
from diarios_oficiais.utils_regex.common import EDITION_LINK_RE
from diarios_oficiais.utils_regex.common import PDF_KEY_RE


BASE_URL = "https://www.ioerj.com.br/portal/modules/conteudoonline/"
CALENDAR_URL = urljoin(BASE_URL, "do_seleciona_data.php")


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
        raw_editions: list[tuple[str, str]] = []
        for match in EDITION_LINK_RE.finditer(page):
            label = clean_html(match.group("label"))
            raw_editions.append((label, urljoin(self.base_url, html.unescape(match.group("href")))))

        editions: list[Edition] = []
        label_counts: dict[str, int] = {}
        total_by_label: dict[str, int] = {}
        for label, _ in raw_editions:
            total_by_label[label] = total_by_label.get(label, 0) + 1

        for label, edition_url in raw_editions:
            label_counts[label] = label_counts.get(label, 0) + 1
            edition_label = label
            if total_by_label[label] > 1 and label_counts[label] > 1:
                edition_label = f"{label} - Complementar {label_counts[label]}"
            editions.append(
                Edition(
                    publication_date=publication_date,
                    section=edition_label,
                    url=edition_url,
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




def parse_acts(
    text: str,
    collector: RjIoerjCollector,
    edition: Edition,
    markdown_path: Path,
) -> list[Act]:
    normalized = SPACE_RE.sub(" ", text)
    context_markers = authority_context_markers(normalized)
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
        functional_id = extract_functional_id(body)
        signer_name, signer_role, signer_category = extract_signer(excerpt)
        if not signer_role:
            signer_name, signer_role, signer_category = contextual_signer(
                context_markers,
                match.start(),
            )
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
                functional_id=functional_id,
                role=role,
                agency=agency,
                excerpt=excerpt[:900],
                source_url=edition.url,
                text_path=str(markdown_path),
                signer_name=signer_name,
                signer_role=signer_role,
                signer_category=signer_category,
            )
        )
    return acts


def authority_context_markers(text: str) -> list[tuple[int, str, str, str]]:
    markers: list[tuple[int, str, str, str]] = []
    upper = text.upper()

    marker_patterns = [
        (
            r"\b(?:ATOS\s+DO\s+)?GOVERNADOR(?:\s+DO\s+ESTADO\s+DO\s+RIO\s+DE\s+JANEIRO)?\s*,?\s+EM\s+EXERC\S*CIO\b",
            "Governador em exercicio",
            "2",
        ),
        (
            r"\bRICARDO\s+COUTO\s+DE\s+CASTRO\b.{0,120}\bGOVERNADOR\s+EM\s+EXERC\S*CIO\b",
            "Governador em exercicio",
            "2",
        ),
        (
            r"\b(?:ATOS\s+DO\s+GOVERNADOR|O\s+GOVERNADOR\s+DO\s+ESTADO\s+DO\s+RIO\s+DE\s+JANEIRO)\b(?!\s*,?\s+EM\s+EXERC)",
            "Governador",
            "1",
        ),
        (
            r"\b(?:ATOS|APOSTILAS|DESPACHOS)\s+DO\s+SECRET\S*RIO\s+DE\s+ESTADO\b|\bO\s+SECRET\S*RIO\s+DE\s+ESTADO\b",
            "Secretario de Estado",
            "4",
        ),
        (
            r"\b(?:ATOS|APOSTILAS|DESPACHOS)\s+DO\s+SECRET\S*RIO\b|\bO\s+SECRET\S*RIO\b",
            "Secretario",
            "5",
        ),
    ]

    for pattern, role, category in marker_patterns:
        for match in re.finditer(pattern, upper, flags=re.I | re.S):
            markers.append(
                (
                    match.start(),
                    contextual_signer_name(upper, match.start(), match.end(), role),
                    role,
                    category,
                )
            )

    return sorted(markers, key=lambda item: item[0])


def contextual_signer(
    markers: list[tuple[int, str, str, str]],
    act_start: int,
) -> tuple[str, str, str]:
    if not markers:
        return "", "", ""

    previous_markers = [marker for marker in markers if marker[0] <= act_start]
    if previous_markers:
        return previous_markers[-1][1:]

    next_marker = next((marker for marker in markers if marker[0] > act_start), None)
    if next_marker and next_marker[2] in {"Governador", "Governador em exercicio"}:
        return next_marker[1:]

    return "", "", ""


def contextual_signer_name(text_upper: str, start: int, end: int, role: str) -> str:
    window = text_upper[max(0, start - 160): min(len(text_upper), end + 220)]
    if role == "Governador em exercicio" and "RICARDO COUTO" in window:
        return "RICARDO COUTO DE CASTRO"
    return ""


def extract_functional_id(body: str) -> str:
    match = FUNCTIONAL_ID_RE.search(body)
    return match.group("id").strip(" .,-;:") if match else ""


def extract_signer(text: str) -> tuple[str, str, str]:
    matches = list(SIGNER_RE.finditer(text))
    if not matches:
        return "", "", ""

    match = matches[-1]
    raw_name = re.split(r"[.;:]\s*", match.group("name"))[-1]
    signer_name = normalize_name(raw_name)
    if not valid_person_name(signer_name):
        return "", "", ""

    raw_role = clean_piece(match.group("role"))
    normalized_role = normalize_name(raw_role)
    for category, label, pattern in SIGNER_CATEGORIES:
        if re.fullmatch(pattern, raw_role, flags=re.I):
            return signer_name, label, category
        if re.fullmatch(pattern, normalized_role, flags=re.I):
            return signer_name, label, category
    return signer_name, raw_role, ""


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
    suspicious_starts = {
        "A",
        "O",
        "COM",
        "SEM",
        "PARA",
        "DO",
        "DA",
        "NO",
        "NA",
        "EM",
        "OS",
        "AS",
        "SIMBOLO",
        "SÍMBOLO",
    }
    if tokens[0] in suspicious_starts:
        return False
    blocked = {
        "ALFABETICA",
        "ALFABÉTICA",
        "CANDIDATO",
        "CANDIDATOS",
        "CARGO",
        "CPF",
        "ESTADO",
        "FUNCAO",
        "FUNÇÃO",
        "INSCRICAO",
        "INSCRIÇÃO",
        "ORDEM",
        "PROCESSO",
        "SECRETARIA",
        "SIMBOLO",
        "SÍMBOLO",
    }
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
    failed_years: set[int] = set()
    skipped_years: set[int] = set()

    def finalize_year(year: int | None) -> None:
        if year is None or year >= current_year:
            return
        if year in failed_years:
            print(f"Nao marquei {year} como completo porque houve falhas de coleta.", file=sys.stderr)
            return
        collector.mark_year_complete(year)

    for item in dates:
        if collector.is_year_complete(item.year):
            if item.year not in skipped_years:
                print(f"Pulando {item.year}: marcador .year_complete encontrado.", file=sys.stderr)
                skipped_years.add(item.year)
            continue

        if active_year is not None and item.year != active_year:
            finalize_year(active_year)
        active_year = item.year

        try:
            editions = collector.list_editions(item)
        except Exception as exc:
            failed_years.add(item.year)
            print(f"Falha ao listar edicoes de {item.isoformat()}: {exc}", file=sys.stderr)
            continue

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
            try:
                collector.load_or_create_markdown(edition, markdown_path)
                acts = parse_acts_from_markdown_file(collector, edition, markdown_path)
                total_new_acts += collector.write_csv(csv_path, acts)
            except Exception as exc:
                failed_years.add(item.year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(
                    f"Falha ao processar {item.isoformat()} ({edition.section}); seguindo para a proxima edicao: {exc}",
                    file=sys.stderr,
                )
                continue

    finalize_year(active_year)
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
