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
from diarios_oficiais.config import RJ_COLLECTION_YEAR
from diarios_oficiais.config import TORCH_CUDA_RUNTIME
from diarios_oficiais.governadores import (
    governador_da_edicao,
    nome_representante_governo,
    origem_representante_governo,
)
from diarios_oficiais.utils_regex.common import SPACE_RE
from diarios_oficiais.utils_regex.common import TAG_RE
from diarios_oficiais.utils_regex import rj_ioerj as rj_regexes


BASE_URL = "https://www.ioerj.com.br/portal/modules/conteudoonline/"
CALENDAR_URL = urljoin(BASE_URL, "do_seleciona_data.php")
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")


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
        for encoded in rj_regexes.DATE_LINK_RE.findall(page):
            decoded = base64.b64decode(encoded).decode("ascii")
            dates.add(datetime.strptime(decoded, "%Y%m%d").date())
        return sorted(dates)

    def list_editions(self, publication_date: date) -> list[Edition]:
        encoded = base64.b64encode(publication_date.strftime("%Y%m%d").encode("ascii")).decode("ascii")
        url = urljoin(self.base_url, f"do_seleciona_edicao.php?data={encoded}")
        page = self.fetch_text(url)
        raw_editions: list[tuple[str, str]] = []
        for match in rj_regexes.EDITION_LINK_RE.finditer(page):
            label = clean_html(match.group("label"))
            raw_editions.append((label, urljoin(self.base_url, html.unescape(match.group("href")))))

        editions: list[Edition] = []
        label_counts: dict[str, int] = {}
        total_by_label: dict[str, int] = {}
        for label, _ in raw_editions:
            total_by_label[label] = total_by_label.get(label, 0) + 1

        for label, edition_url in raw_editions:
            label_counts[label] = label_counts.get(label, 0) + 1
            edition_label = disambiguate_edition_label(
                label,
                label_counts[label],
                total_by_label[label],
            )
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
        key_match = rj_regexes.PDF_KEY_RE.search(page)
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

    def latest_stored_publication_date(self) -> date | None:
        state_lake_dir = self.lake_dir / self.state
        latest_date: date | None = None
        for markdown_path in state_lake_dir.rglob("*.md"):
            match = MARKDOWN_DATE_RE.search(markdown_path.stem)
            if not match:
                continue
            publication_date = date.fromisoformat(match.group(1))
            if latest_date is None or publication_date > latest_date:
                latest_date = publication_date
        return latest_date


def clean_html(value: str) -> str:
    value = TAG_RE.sub(" ", value)
    value = html.unescape(value)
    return SPACE_RE.sub(" ", value).strip()


def disambiguate_edition_label(label: str, occurrence: int, total_occurrences: int) -> str:
    if total_occurrences <= 1 or occurrence <= 1:
        return label
    if re.search(r"\b(?:complementar|suplemento|extra)\b", label, flags=re.I):
        return f"{label} {occurrence}"
    return f"{label} - Edicao {occurrence}"




def parse_acts(
    text: str,
    collector: RjIoerjCollector,
    edition: Edition,
    markdown_path: Path,
    regexes=rj_regexes,
) -> list[Act]:
    normalized = SPACE_RE.sub(" ", text)
    context_markers = authority_context_markers(normalized, raw_text=text)
    edition_governor = governador_da_edicao(str(markdown_path))
    acts: list[Act] = []
    seen: set[tuple[str, str, str]] = set()

    for match in regexes.ACT_WINDOW_RE.finditer(normalized):
        action = match.group("action").upper()
        body = match.group("body").strip(" ,.;:-")
        excerpt = f"{action} {body}".strip()
        person_name = extract_person_name(body, regexes=regexes)
        if not person_name:
            continue

        role_match = regexes.ROLE_RE.search(body)
        agency_match = regexes.AGENCY_RE.search(body)
        role = clean_piece(role_match.group(0)) if role_match else ""
        agency = clean_piece(agency_match.group(0)) if agency_match else ""
        functional_id = extract_functional_id(body, regexes=regexes)
        signer_name, signer_role, signer_category = extract_signer(excerpt, regexes=regexes)
        if not signer_role:
            signer_name, signer_role, signer_category = contextual_signer(
                context_markers,
                match.start(),
            )
        representative, representative_origin = representative_for_act(edition_governor)
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
                action_type="nomeacao" if action in {"NOMEAR", "NOMEIA"} else "exoneracao",
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
                edition_governor=edition_governor,
                government_representative=representative,
                representative_origin=representative_origin,
            )
        )
    return acts


def representative_for_act(
    edition_governor: str,
) -> tuple[str, str]:
    # Indicadores de governo pertencem ao titular da edicao, mesmo quando
    # o ato foi assinado por uma secretaria dentro daquele governo.
    return (
        nome_representante_governo(edition_governor),
        origem_representante_governo(edition_governor),
    )


def clean_representative_name(value: str) -> str:
    value = clean_piece(value)
    candidates = [value]
    if "|" in value:
        cells = [clean_piece(cell) for cell in value.split("|")]
        candidates = [cell for cell in cells if cell] + candidates
    for candidate in candidates:
        candidate = re.sub(r"[-–—]{3,}", " ", candidate)
        candidate = clean_piece(re.sub(r"\([^)]*\)", " ", candidate))
        normalized = normalize_name(candidate)
        if plausible_secretary_name(normalized) and valid_person_name(normalized):
            return title_case_name(normalized)
    return ""


def authority_context_markers(text: str, raw_text: str | None = None) -> list[tuple[int, str, str, str]]:
    markers: list[tuple[int, str, str, str]] = []
    raw_text = raw_text or text
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
                    contextual_signer_name(raw_text, text, upper, match.start(), match.end(), role),
                    contextual_signer_role(raw_text, text, upper, match.start(), match.end(), role),
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


def contextual_signer_name(raw_text: str, text: str, text_upper: str, start: int, end: int, role: str) -> str:
    window = text_upper[max(0, start - 160): min(len(text_upper), end + 220)]
    if role == "Governador em exercicio" and "RICARDO COUTO" in window:
        return "RICARDO COUTO DE CASTRO"
    if role in {"Secretario de Estado", "Secretario"}:
        agency = secretary_agency_for_marker(text_upper, start) or secretary_agency_from_phrase(text_upper, start, end)
        if agency:
            secretary_name = secretary_name_from_front_page(raw_text, agency)
            if secretary_name:
                return secretary_name
    return ""


def contextual_signer_role(raw_text: str, text: str, text_upper: str, start: int, end: int, role: str) -> str:
    if role in {"Secretario de Estado", "Secretario"}:
        agency = secretary_agency_for_marker(text_upper, start) or secretary_agency_from_phrase(text_upper, start, end)
        if agency:
            return f"{role} - {title_case_agency(agency)}"
    return role


def secretary_agency_from_phrase(text_upper: str, start: int, end: int) -> str:
    window = text_upper[start:min(len(text_upper), end + 180)]
    match = re.search(
        r"\bSECRET\S*RIO\s+DE\s+ESTADO\s+((?:(?:DA|DE|DO)\s+)?[^,.;#\n]{3,100})",
        window,
        flags=re.I,
    )
    if not match:
        return ""
    return clean_secretary_agency(f"SECRETARIA DE ESTADO {match.group(1)}")


def secretary_agency_for_marker(text_upper: str, start: int) -> str:
    window = text_upper[max(0, start - 500):start]
    matches = list(
        re.finditer(
            r"##\s*(SECRETARIA\s+DE\s+ESTADO\s+(?:(?:DA|DE|DO)\s+)?[^#\n]{3,120})",
            window,
            flags=re.I,
        )
    )
    for match in reversed(matches):
        agency = clean_secretary_agency(match.group(1))
        if agency:
            return agency
    return ""


def clean_secretary_agency(value: str) -> str:
    value = re.split(
        r"\b(?:ATO|ATOS|APOSTILA|APOSTILAS|DESPACHO|DESPACHOS|FUNDA[ÇC][ÃA]O|SUBSECRETARIA|SUPERINTEND[ÊE]NCIA|DIRETORIA|INSTITUTO|USANDO|USO|SUAS\s+ATRIBUIÇÕES|SUAS\s+ATRIBUI[ÇC][ÕO]ES|DE\s+SUAS\s+ATRIBUIÇÕES|DE\s+SUAS\s+ATRIBUI[ÇC][ÕO]ES)\b",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    value = re.sub(r"\s+", " ", value).strip(" #,.;:-")
    if not value.startswith("SECRETARIA DE ESTADO"):
        return ""
    return value


def secretary_name_from_front_page(text: str, agency: str) -> str:
    prefix = SPACE_RE.sub(" ", text[:25000])
    prefix_upper = prefix.upper()
    agency_re = re.escape(agency)
    stop_re = (
        r"SECRETARIA\s+DE\s+ESTADO|CONTROLADORIA\s+GERAL|GABINETE\s+DE\s+SEGURANÇA|"
        r"PROCURADORIA\s+GERAL|VICE-GOVERNADOR|GOVERNO\s+DO\s+ESTADO|S\s+U\s+M|www\.rj\.gov"
    )
    for match in re.finditer(rf"{agency_re}\s+(?P<name>.{{3,120}}?)(?=\s+(?:{stop_re})|$)", prefix_upper, flags=re.I):
        candidate = prefix[match.start("name"):match.end("name")]
        candidate = clean_piece(re.sub(r"\([^)]*\)", " ", candidate))
        if not plausible_secretary_name(candidate):
            continue
        normalized = normalize_name(candidate)
        if valid_person_name(normalized):
            return title_case_name(normalized)

    lines = text[:25000].splitlines()
    for index, line in enumerate(lines):
        if agency not in line.upper():
            continue
        for next_line in lines[index + 1:index + 5]:
            for cell in next_line.split("|"):
                candidate = clean_piece(cell)
                if not plausible_secretary_name(candidate):
                    continue
                normalized = normalize_name(candidate)
                if valid_person_name(normalized):
                    return title_case_name(normalized)

    for match in re.finditer(agency_re, prefix_upper, flags=re.I):
        after = prefix[match.end(): match.end() + 180]
        after = re.split(
            r"\b(?:SECRETARIA\s+DE\s+ESTADO|GABINETE|VICE-GOVERNADORIA|PROCURADORIA|SUMARIO|S\s+U\s+M|ORG[A-ZÃƒÃ“]+OS?)\b",
            after,
            maxsplit=1,
            flags=re.I,
        )[0]
        candidate = clean_piece(after)
        candidate = re.sub(r"^\|+", "", candidate).strip()
        candidate = re.split(r"\s{2,}|\|", candidate, maxsplit=1)[0].strip()
        if not plausible_secretary_name(candidate):
            continue
        normalized = normalize_name(candidate)
        if valid_person_name(normalized):
            return title_case_name(normalized)
    return ""


def plausible_secretary_name(value: str) -> bool:
    normalized = normalize_name(value)
    if not normalized:
        return False
    blocked_terms = {
        "ATO",
        "ATOS",
        "ADJUNTO",
        "AJUDANTE",
        "APOSTILA",
        "APOSTILAS",
        "ASSESSOR",
        "ASSISTENTE",
        "ASSISTENCIA",
        "ASSISTÊNCIA",
        "BINETE",
        "CIDADAO",
        "CIDADÃO",
        "COM",
        "CONGENERE",
        "CONGÊNERE",
        "CONVENIO",
        "CONVÊNIO",
        "CONTAR",
        "COORDENADOR",
        "DECRETO",
        "DESPACHO",
        "DESPACHOS",
        "DESIGNADO",
        "DIREITOS",
        "DISPOE",
        "DISPÕE",
        "DIRETA",
        "EXONERAR",
        "EXPEDIENTE",
        "EXERCICIO",
        "EXERCÍCIO",
        "FURTADOS",
        "GABINETE",
        "GESTAO",
        "GESTÃO",
        "GOVERNADOR",
        "HIDROMETROS",
        "HIDRÔMETROS",
        "IMAGE",
        "INSTRUMENTO",
        "LE",
        "LÊ",
        "LOTERICOS",
        "LOTÉRICOS",
        "MEMBRO",
        "MEMBROS",
        "MINUTA",
        "NATOS",
        "NOMEAR",
        "NOMENCLATURA",
        "OCUPADO",
        "OCUPADA",
        "ONDE",
        "ORGAO",
        "ORGAOS",
        "ÓRGÃO",
        "ÓRGÃOS",
        "PAGINA",
        "PELA",
        "PODER",
        "PORTARIA",
        "PORTAL",
        "PREMIOS",
        "PRÊMIOS",
        "POLITICOS",
        "POLÍTICOS",
        "PUBLICOS",
        "PÚBLICOS",
        "PROVIDENCIAS",
        "PROVIDÊNCIAS",
        "REPRESENTANTES",
        "REPOSICAO",
        "REPOSIÇÃO",
        "SECRETARIADO",
        "SECRETARIO",
        "SECRETARIA",
        "SUPERINTENDENCIA",
        "WWW",
    }
    month_terms = {
        "JANEIRO",
        "FEVEREIRO",
        "MARCO",
        "MARÇO",
        "ABRIL",
        "MAIO",
        "JUNHO",
        "JULHO",
        "AGOSTO",
        "SETEMBRO",
        "OUTUBRO",
        "NOVEMBRO",
        "DEZEMBRO",
    }
    tokens = set(normalized.split())
    if tokens.intersection(blocked_terms) or tokens.intersection(month_terms):
        return False
    if re.search(r"\d", normalized):
        return False
    if sum(1 for token in normalized.split() if len(token) == 1) >= 3:
        return False
    return True


def title_case_name(value: str) -> str:
    lower_words = {"DA", "DE", "DO", "DAS", "DOS", "E"}
    words = []
    for word in value.split():
        words.append(word.lower() if word in lower_words else word.capitalize())
    return " ".join(words)


def title_case_agency(value: str) -> str:
    return title_case_name(value)


def extract_functional_id(body: str, regexes=rj_regexes) -> str:
    match = regexes.FUNCTIONAL_ID_RE.search(body)
    return match.group("id").strip(" .,-;:") if match else ""


def extract_signer(text: str, regexes=rj_regexes) -> tuple[str, str, str]:
    matches = list(regexes.SIGNER_RE.finditer(text))
    if not matches:
        return "", "", ""

    match = matches[-1]
    raw_name = re.split(r"[.;:]\s*", match.group("name"))[-1]
    signer_name = normalize_name(raw_name)
    if re.search(r"\b(?:DO|DA)\s+CARGO\b|\bCARGO\s+EM\s+COMISS", signer_name, flags=re.I):
        return "", "", ""
    if not plausible_secretary_name(signer_name):
        return "", "", ""
    if not valid_person_name(signer_name):
        return "", "", ""

    raw_role = clean_piece(match.group("role"))
    normalized_role = normalize_name(raw_role)
    for category, label, pattern in regexes.SIGNER_CATEGORIES:
        if re.fullmatch(pattern, raw_role, flags=re.I):
            return signer_name, label, category
        if re.fullmatch(pattern, normalized_role, flags=re.I):
            return signer_name, label, category
    return signer_name, raw_role, ""


def parse_acts_from_markdown_file(
    collector: RjIoerjCollector,
    edition: Edition,
    markdown_path: Path,
    regexes=rj_regexes,
) -> list[Act]:
    text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    return parse_acts(text, collector, edition, markdown_path, regexes=regexes)


def extract_person_name(body: str, regexes=rj_regexes) -> str:
    direct = direct_person_name(body)
    if direct:
        return direct

    for match in regexes.NAME_AFTER_ACTION_RE.finditer(body):
        candidate = clean_piece(match.group("name"))
        candidate = normalize_name(candidate)
        if valid_person_name(candidate):
            return candidate
    return ""


def direct_person_name(body: str) -> str:
    candidate_area = re.split(
        r"\s*,?\s*(?:ID\.?\s*FUNC(?:IONAL)?|RG|R\.G\.|CPF)\b|\s+para\s+exer|\s+para\s+exercer|\s+do\s+cargo|\s+da\s+fun[cç][aã]o|\s+no\s+cargo\b|\s*,\s*com\s+validade\b",
        body,
        maxsplit=1,
        flags=re.I,
    )[0]
    candidate_area = re.sub(
        r"^(?:(?:a\s+pedido\s*(?:e\s*)?)|(?:com\s+validade[^,]*,?\s*)|(?:louvad[oa][^,]*,?\s*))+",
        "",
        candidate_area,
        flags=re.I,
    )
    candidate_area = candidate_area.strip(" ,.;:-")
    if "," in candidate_area:
        parts = [part.strip(" ,.;:-") for part in candidate_area.split(",") if part.strip(" ,.;:-")]
        candidate_area = parts[-1] if parts else candidate_area
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
    value = re.sub(r"(?<!\w)#{1,6}\s*", " ", value or "")
    return SPACE_RE.sub(" ", value).strip(" \t\r\n,.;:-'\"")


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

def collect_rj(pular_anos_completos: bool = True) -> int:
    collector = RjIoerjCollector()
    latest_stored_date = collector.latest_stored_publication_date()
    start_date = latest_stored_date or date(RJ_COLLECTION_YEAR, 1, 1)
    if latest_stored_date is None:
        print(
            f"Nenhuma edicao RJ encontrada no LAKE; iniciando em {start_date.isoformat()}.",
            file=sys.stderr,
        )
    else:
        print(
            f"Ultima edicao RJ encontrada no LAKE: {latest_stored_date.isoformat()}. "
            "Retomando a partir dessa data.",
            file=sys.stderr,
        )
    dates = sorted(
        publication_date
        for publication_date in collector.list_available_dates()
        if publication_date >= start_date
    )

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
        if pular_anos_completos and collector.is_year_complete(item.year):
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
