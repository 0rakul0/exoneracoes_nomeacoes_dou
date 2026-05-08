from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from pathlib import Path


UNKNOWN_GOVERNOR = "Nao identificado"
UNKNOWN_ORIGIN = "Nao identificado"

KNOWN_GOVERNORS = [
    ("WILSON JOS", "Wilson Jose Witzel"),
    ("CLÁUDIO BOMFIM DE CASTRO E SILVA", "Claudio Bomfim de Castro e Silva"),
    ("CLAUDIO BOMFIM DE CASTRO E SILVA", "Claudio Bomfim de Castro e Silva"),
    ("CLÃ¡UDIO BOMFIM DE CASTRO E SILVA".upper(), "Claudio Bomfim de Castro e Silva"),
    ("CLÁUDIO CASTRO", "Claudio Bomfim de Castro e Silva"),
    ("CLAUDIO CASTRO", "Claudio Bomfim de Castro e Silva"),
    ("THIAGO PAMPOLHA", "Thiago Pampolha"),
    ("THIA GO P AM PO LHA", "Thiago Pampolha"),
    ("RICARDO COUTO", "Ricardo Couto de Castro"),
    ("RODRIGO BACELLAR", "Rodrigo Bacellar"),
]


@lru_cache(maxsize=4096)
def governador_da_edicao(markdown_path: str) -> str:
    if not markdown_path:
        return UNKNOWN_GOVERNOR

    path = Path(str(markdown_path))
    date_governor = governador_por_periodo(path)
    if date_governor:
        return date_governor

    if not path.exists():
        return UNKNOWN_GOVERNOR

    try:
        text = path.read_text(encoding="utf-8", errors="ignore").upper()
    except OSError:
        return UNKNOWN_GOVERNOR

    acting_name = extract_governor_name_near_acting_phrase(text)
    if acting_name:
        return f"{acting_name} - Governador em exercicio"

    governor_name = extract_named_role(text, "GOVERNADOR", stop_role="VICE-GOVERNADOR")
    if governor_name:
        return f"{governor_name} - Governador"

    return governador_por_data_do_arquivo(path)


def nome_representante_governo(governador_edicao: str) -> str:
    governador_edicao = str(governador_edicao or UNKNOWN_GOVERNOR).strip()
    if " - " not in governador_edicao:
        return governador_edicao or UNKNOWN_GOVERNOR
    return governador_edicao.split(" - ", 1)[0].strip() or UNKNOWN_GOVERNOR


def origem_representante_governo(governador_edicao: str) -> str:
    nome = nome_representante_governo(governador_edicao)
    origem_por_nome = {
        "Thiago Pampolha": "Vice-governadoria",
        "Rodrigo Bacellar": "ALERJ",
        "Ricardo Couto de Castro": "TJ-RJ",
    }
    if nome == UNKNOWN_GOVERNOR:
        return UNKNOWN_ORIGIN
    return origem_por_nome.get(nome, "Executivo estadual")


def governador_por_periodo(path: Path) -> str:
    publication_date = publication_date_from_path(path)
    if publication_date is None:
        return ""
    if date(2020, 8, 28) <= publication_date < date(2021, 5, 1):
        return "Claudio Bomfim de Castro e Silva - Governador em exercicio"
    return ""


def governador_por_data_do_arquivo(path: Path) -> str:
    publication_date = publication_date_from_path(path)
    if publication_date is None:
        return UNKNOWN_GOVERNOR

    if publication_date < date(2020, 8, 28):
        return "Wilson Jose Witzel - Governador"
    if publication_date < date(2021, 5, 1):
        return "Claudio Bomfim de Castro e Silva - Governador em exercicio"
    return "Claudio Bomfim de Castro e Silva - Governador"


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
    phrase_re = re.compile(r"(?<!VICE-)GOVERNADOR\s+EM\s+EXERC\S*CIO|(?<!VICE-)GOVERNADOR\s+EM\s+EXERCÃ")
    for match in phrase_re.finditer(text):
        window = text[max(0, match.start() - 140): min(len(text), match.end() + 2600)]
        known = match_known_name(window)
        if known:
            return known

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
