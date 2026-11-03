"""Shared national parser for nomination and dismissal acts.

Preserves the matching behavior of the historical RJ implementation while
allowing the existing source-specific regex profiles to remain independent.
"""
from __future__ import annotations
import html
import re
from pathlib import Path
from typing import Callable
from diarios_oficiais.base import Act, Edition
from diarios_oficiais.governadores import (
    governador_da_edicao,
    nome_representante_governo,
    origem_representante_governo,
)
from diarios_oficiais.utils_regex.common import SPACE_RE, TAG_RE
from diarios_oficiais.utils_regex import rj_ioerj as rj_regexes

def parse_acts(
    text: str,
    collector: RjIoerjCollector,
    edition: Edition,
    markdown_path: Path,
    regexes=rj_regexes,
    municipality_for_position: Callable[[int], str] | None = None,
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
        person_names: list[str] = []
        before_name_re = getattr(regexes, "BEFORE_ACTION_NAME_RE", None)
        if before_name_re is not None:
            before_action = normalized[max(0, match.start() - 2600):match.start()]
            previous_matches = list(before_name_re.finditer(before_action))
            if previous_matches:
                candidate = clean_piece(previous_matches[-1].group("name"))
                candidate = normalize_name(candidate)
                if valid_person_name(candidate):
                    person_names = [candidate]
        if not person_names:
            person_names = extract_person_names(body, regexes=regexes)
        if not person_names:
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
        for person_name in person_names:
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
                    action_type="nomeacao" if action.startswith("NOME") else "exoneracao",
                    person_name=person_name,
                    functional_id=functional_id,
                    role=role,
                    agency=agency,
                    excerpt=excerpt[:900],
                    source_url=edition.url,
                    text_path=str(markdown_path),
                    municipality=municipality_for_position(match.start()) if municipality_for_position else "",
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
    direct_name_re = getattr(regexes, "DIRECT_NAME_RE", None)
    if direct_name_re is not None:
        for match in direct_name_re.finditer(body):
            candidate = clean_piece(match.group("name"))
            candidate = normalize_name(candidate)
            if valid_person_name(candidate):
                return candidate

    for name_re in (
        getattr(regexes, "TABLE_NAME_RE", None),
        getattr(regexes, "LIST_NAME_RE", None),
    ):
        if name_re is None:
            continue
        for match in name_re.finditer(body):
            candidate = clean_piece(match.group("name"))
            candidate = normalize_name(candidate)
            if valid_person_name(candidate):
                return candidate

    direct = direct_person_name(body)
    if direct:
        return direct

    for match in regexes.NAME_AFTER_ACTION_RE.finditer(body):
        candidate = clean_piece(match.group("name"))
        candidate = normalize_name(candidate)
        if valid_person_name(candidate):
            return candidate
    return ""


def extract_person_names(body: str, regexes=rj_regexes) -> list[str]:
    multi_name_re = getattr(regexes, "MULTI_NAME_RE", None)
    if multi_name_re is None:
        person_name = extract_person_name(body, regexes=regexes)
        return [person_name] if person_name else []

    trigger_re = getattr(regexes, "MULTI_NAME_TRIGGER_RE", None)
    if trigger_re is not None and not trigger_re.search(body):
        person_name = extract_person_name(body, regexes=regexes)
        return [person_name] if person_name else []

    names: list[str] = []
    for match in multi_name_re.finditer(body):
        candidate = clean_piece(match.group("name"))
        candidate = normalize_name(candidate)
        tokens = candidate.split()
        blocked_prefixes = getattr(regexes, "NAME_PREFIX_BLACKLIST", set())
        if tokens and tokens[0] in blocked_prefixes:
            continue
        if valid_person_name(candidate) and candidate not in names:
            names.append(candidate)
    if names:
        return names

    person_name = extract_person_name(body, regexes=regexes)
    return [person_name] if person_name else []


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
    if any(char.isdigit() for char in candidate):
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
        "ACORDO",
        "ALFABETICA",
        "ALFABÉTICA",
        "ART",
        "ARTIGO",
        "CANDIDATO",
        "CANDIDATOS",
        "CARGO",
        "CONFORME",
        "CPF",
        "DECRETO",
        "ESTADO",
        "FUNCAO",
        "FUNÇÃO",
        "FINAL",
        "INSCRICAO",
        "INSCRIÇÃO",
        "INCISO",
        "HOMOLOGADA",
        "HOMOLOGADO",
        "LEI",
        "PELA",
        "PELO",
        "NOS",
        "ORDEM",
        "OCUPANTE",
        "PORTARIA",
        "PROCESSO",
        "QUADRO",
        "RESOLVE",
        "SECRETARIA",
        "SERVIDOR",
        "SERVIDORA",
        "SIMBOLO",
        "SÍMBOLO",
        "TERMOS",
        "RESULTADO",
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

