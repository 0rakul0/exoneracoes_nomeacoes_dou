from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from pathlib import Path


UNKNOWN_GOVERNOR = "Nao identificado"
UNKNOWN_ORIGIN = "Nao identificado"

KNOWN_GOVERNORS = [
    ("LUIZ FERNANDO DE SOUZA", "Luiz Fernando de Souza"),
    ("SERGIO CABRAL", "Sergio Cabral"),
    ("SÉRGIO CABRAL", "Sergio Cabral"),
    ("SÃ‰RGIO CABRAL", "Sergio Cabral"),
    ("WILSON JOS", "Wilson Jose Witzel"),
    ("CLÁUDIO BOMFIM DE CASTRO E SILVA", "Claudio Bomfim de Castro e Silva"),
    ("CLAUDIO BOMFIM DE CASTRO E SILVA", "Claudio Bomfim de Castro e Silva"),
    ("CLÃ¡UDIO BOMFIM DE CASTRO E SILVA".upper(), "Claudio Bomfim de Castro e Silva"),
    ("CLÁUDIO CASTRO", "Claudio Bomfim de Castro e Silva"),
    ("CLAUDIO CASTRO", "Claudio Bomfim de Castro e Silva"),
    ("CLAÚDIO CASTRO", "Claudio Bomfim de Castro e Silva"),
    ("BOMFIM DE CASTRO E SILVA", "Claudio Bomfim de Castro e Silva"),
    ("THIAGO PAMPOLHA", "Thiago Pampolha"),
    ("THIA GO P AM PO LHA", "Thiago Pampolha"),
    ("THIAGO PA M P O L H A", "Thiago Pampolha"),
    ("RICARDO COUTO", "Ricardo Couto de Castro"),
    ("RODRIGO BACELLAR", "Rodrigo Bacellar"),
    ("FRANCISCO DORNELLES", "Francisco Dornelles"),
    ("FARNCISCO DORNELLES", "Francisco Dornelles"),
    ("ANDRÉ CECILIANO", "Andre Ceciliano"),
    ("ANDRE CECILIANO", "Andre Ceciliano"),
    ("PAULO MELO", "Paulo Melo"),
]

KNOWN_SP_GOVERNORS = [
    ("TARCISIO DE FREITAS", "Tarcisio de Freitas"),
    ("TARCÍSIO DE FREITAS", "Tarcisio de Freitas"),
    ("RODRIGO GARCIA", "Rodrigo Garcia"),
    ("JOAO DORIA", "Joao Doria"),
    ("JOÃO DORIA", "Joao Doria"),
]


@lru_cache(maxsize=4096)
def governador_da_edicao(markdown_path: str) -> str:
    if not markdown_path:
        return UNKNOWN_GOVERNOR

    path = Path(str(markdown_path))
    if "SP" in path.parts:
        return governador_sp_da_edicao(path)

    if not path.exists():
        return UNKNOWN_GOVERNOR

    try:
        text = path.read_text(encoding="utf-8", errors="ignore").upper()
    except OSError:
        return UNKNOWN_GOVERNOR

    acting_name = extract_governor_name_near_acting_phrase(text)
    if acting_name:
        return f"{acting_name} - Governador em exercicio"

    header_name = extract_governor_header_name(text)
    if header_name:
        return f"{header_name} - Governador"

    governor_name = extract_named_role(text, "GOVERNADOR", stop_role="VICE-GOVERNADOR")
    if governor_name:
        return f"{governor_name} - Governador"

    governor_name = extract_known_name_after_governor_label(text)
    if governor_name:
        return f"{governor_name} - Governador"

    governor_name = match_known_signature_line(text)
    if governor_name:
        return f"{governor_name} - Governador"

    return UNKNOWN_GOVERNOR


def governador_sp_da_edicao(path: Path) -> str:
    publication_date = publication_date_from_path(path)
    if publication_date is not None:
        if publication_date >= date(2023, 1, 1):
            return "Tarcisio de Freitas - Governador"
        if publication_date >= date(2022, 4, 1):
            return "Rodrigo Garcia - Governador"
        if publication_date >= date(2019, 1, 1):
            return "Joao Doria - Governador"

    if not path.exists():
        return UNKNOWN_GOVERNOR

    try:
        text = path.read_text(encoding="utf-8", errors="ignore").upper()
    except OSError:
        return UNKNOWN_GOVERNOR

    known_name = match_known_sp_name(text[:20000])
    if known_name:
        return f"{known_name} - Governador"
    return UNKNOWN_GOVERNOR


def nome_representante_governo(governador_edicao: str) -> str:
    governador_edicao = str(governador_edicao or UNKNOWN_GOVERNOR).strip()
    if " - " not in governador_edicao:
        return governador_edicao or UNKNOWN_GOVERNOR
    return governador_edicao.split(" - ", 1)[0].strip() or UNKNOWN_GOVERNOR


def origem_representante_governo(governador_edicao: str) -> str:
    nome = nome_representante_governo(governador_edicao)
    origem_por_nome = {
        "Andre Ceciliano": "ALERJ",
        "Claudio Bomfim de Castro e Silva": "Executivo estadual",
        "Francisco Dornelles": "Vice-governadoria",
        "Luiz Fernando de Souza": "Executivo estadual",
        "Paulo Melo": "ALERJ",
        "Rodrigo Bacellar": "ALERJ",
        "Ricardo Couto de Castro": "TJ-RJ",
        "Sergio Cabral": "Executivo estadual",
        "Thiago Pampolha": "Vice-governadoria",
        "Wilson Jose Witzel": "Executivo estadual",
    }
    if nome == UNKNOWN_GOVERNOR:
        return UNKNOWN_ORIGIN
    if nome in origem_por_nome:
        return origem_por_nome[nome]
    if "Governador em exercicio" in str(governador_edicao or ""):
        return "Vice-governadoria"
    return "Executivo estadual"


def governador_por_periodo(path: Path) -> str:
    return ""


def governador_por_data_do_arquivo(path: Path) -> str:
    return UNKNOWN_GOVERNOR


def publication_date_from_path(path: Path) -> date | None:
    match = re.search(r"(20\d{2})-(\d{2})-(\d{2})", path.name)
    if not match:
        return None
    return date(
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
    )


def extract_governor_name_near_acting_phrase(text: str) -> str:
    heading_re = re.compile(
        r"(?im)^\s*(?:#+\s*)?GOVERNADOR\s+EM\s+EXER\S*"
        r"(?:\s+(?P<same_line>[^\r\n|]{4,100})|\s*\r?\n\s*(?:#+\s*)?(?P<next_line>[^\r\n|]{4,100}))\s*$",
    )
    for match in heading_re.finditer(text[:5000]):
        name = canonical_or_signed_name(match.group("same_line") or match.group("next_line"))
        if name:
            return name

    signature_re = re.compile(
        r"(?im)^\s*(?:#+\s*)?(?P<name>[^\r\n|]{4,120})\s*\r?\n"
        r"\s*(?:#+\s*)?GOVERNADOR\s+EM\s+EXER",
    )
    for match in signature_re.finditer(text[:50000]):
        context = text[max(0, match.start() - 1800):match.start()]
        if not re.search(
            r"O\s+GOVERNADOR\s+DO\s+ESTADO|RIO\s+DE\s+JANEIRO\s*,?\s+\d{1,2}\s+DE\s+",
            context,
            flags=re.I,
        ):
            continue
        name = canonical_or_signed_name(match.group("name"))
        if name:
            return name

    phrase_re = re.compile(
        r"(?<!VICE-)GOVERNADOR"
        r"(?:\s+DO\s+ESTADO\s+DO\s+RIO\s+DE\s+JANEIRO\s*,?)?"
        r"\s+EM\s+EXER",
        flags=re.I,
    )
    for match in phrase_re.finditer(text[:50000]):
        window = text[max(0, match.start() - 180): min(len(text), match.end() + 1600)]
        known = match_known_name(window)
        if known:
            return known

    return ""


def extract_governor_header_name(text: str) -> str:
    inline_re = re.compile(
        r"(?im)^\s*(?:#+\s*)?GOVERNADOR\s+(?!EM\b)(?P<name>[^\r\n|]{4,100})\s*$",
    )
    next_line_re = re.compile(
        r"(?im)^\s*(?:#+\s*)?GOVERNADOR\s*$\r?\n\s*(?:#+\s*)?(?P<name>[^\r\n|]{4,100})\s*$",
    )
    for pattern in (inline_re, next_line_re):
        for match in pattern.finditer(text[:5000]):
            name = canonical_or_signed_name(match.group("name"))
            if name:
                return name
    return ""


def match_known_signature_line(value: str) -> str:
    for raw_line in value.splitlines():
        if "GOVERNADOR" in raw_line.upper():
            known = match_known_name(raw_line)
            if known:
                return known
        normalized = re.sub(r"(?i)\bID\s*:?\s*\d+.*$", "", raw_line)
        normalized = re.sub(r"(?i)\bGOVERNADOR(?:\s+EM\s+EXERC\S*CIO)?\b", "", normalized)
        normalized = re.sub(r"(?i)\bVICE-GOVERNADOR\b", "", normalized)
        normalized = re.sub(r"[^A-ZÀ-ÜÃÕÇ\s]", " ", normalized.upper())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized:
            continue
        for needle, label in KNOWN_GOVERNORS:
            if normalized == needle or normalized.endswith(f" {needle}"):
                return label
    return ""


def extract_known_name_after_governor_label(text: str) -> str:
    for match in re.finditer(r"(?<!VICE-)GOVERNADOR\s+(?P<tail>.{0,180})", text[:50000], flags=re.S):
        known_name = match_known_name(match.group("tail"))
        if known_name:
            return known_name
    return ""


def extract_named_role(text: str, role: str, stop_role: str | None = None) -> str:
    prefix = text[:15000]
    escaped_role = r"(?<!VICE-)GOVERNADOR" if role.upper() == "GOVERNADOR" else re.escape(role)
    stop_pattern = re.escape(stop_role) if stop_role else r"ÓRG|Ã“RG|GOVERNO DO ESTADO|ATOS DO"
    matches = re.finditer(
        rf"{escaped_role}\s+(?P<name>.{{3,140}}?)(?=\s+{stop_pattern}|\n|$)",
        prefix,
        flags=re.S,
    )
    for match in matches:
        raw_name = re.sub(r"\s+", " ", match.group("name")).strip(" -|,.;:")
        normalized = raw_name.upper()
        if re.search(r"\b(EXCELENT|SENHOR|DEPUTADO|PRESIDENTE\s+DA\s+ASSEMBLEIA)\b", normalized):
            continue
        known_name = match_known_name(normalized)
        if known_name:
            return known_name
    return ""


def match_known_name(value: str) -> str:
    normalized = value.upper()
    for needle, label in KNOWN_GOVERNORS:
        if needle in normalized:
            return label
    return ""


def canonical_or_signed_name(value: str) -> str:
    known_name = match_known_name(value)
    if known_name:
        return known_name

    candidate = re.sub(r"(?i)<!--\s*IMAGE\s*-->|#+", " ", str(value or ""))
    candidate = re.sub(r"(?i)^.*?\bRIO\s+DE\s+JANEIRO\s*,?\s+\d{1,2}\s+DE\s+\w+\s+DE\s+\d{4}\s+", "", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" ,.;:-")
    tokens = candidate.upper().split()
    blocked = {
        "ANEXO",
        "ATO",
        "ATOS",
        "DECRETA",
        "DECRETO",
        "DECRETOS",
        "DESPACHO",
        "DO",
        "EM",
        "ESTADO",
        "EXCELENTISSIMO",
        "EXCELENTÍSSIMO",
        "EXERCICIO",
        "EXERCÍCIO",
        "EXPEDIENTE",
        "GOVERNADOR",
        "ID",
        "SECRETARIA",
        "SENHOR",
        "UNICO",
        "ÚNICO",
    }
    if len(tokens) < 2 or len(tokens) > 8:
        return ""
    if any(token in blocked for token in tokens) or any(char.isdigit() for char in candidate):
        return ""
    if sum(len(token) == 1 for token in tokens) >= 2:
        return ""
    if not all(re.fullmatch(r"[A-ZÀ-ÜÃÕÇ]+|DA|DE|DO|DAS|DOS|E", token) for token in tokens):
        return ""
    lower_words = {"DA", "DE", "DO", "DAS", "DOS", "E"}
    return " ".join(token.lower() if token in lower_words else token.capitalize() for token in tokens)


def match_known_sp_name(value: str) -> str:
    normalized = value.upper()
    for needle, label in KNOWN_SP_GOVERNORS:
        if needle in normalized:
            return label
    return ""
