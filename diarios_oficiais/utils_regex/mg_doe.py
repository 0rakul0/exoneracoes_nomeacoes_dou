from __future__ import annotations

import re


ACTION_RE = r"(?:NOMEIA|NOMEAR|EXONERA|EXONERAR)"
ACT_WINDOW_RE = re.compile(
    rf"\b(?P<action>{ACTION_RE})\b(?P<body>.{{0,6000}}?)(?="
    rf"\b(?:{ACTION_RE}|DESIGNA|DESIGNAR|DISPENSA|DISPENSAR|AUTORIZA|"
    r"REMOVE|RETIFICA|TORNAR\s+SEM\s+EFEITO|RESOLVE)\b|"
    r"\.\s*\n|\n\s*\n|$)",
    re.I | re.S,
)

# A capitalização evita interpretar "nomear cada arquivo de vídeo" como
# nomeação de pessoa. Os conectores aceitam maiúsculas e minúsculas.
TOKEN = r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç'’.-]*"
CONNECTOR = rf"(?:[Dd][aeo]s?|[Ee]|{TOKEN})"
NAME = rf"{TOKEN}(?:\s+{CONNECTOR}){{1,12}}?"
ID = r"\d(?:[. \t]*\d){5,8}(?:\s*[-/]\s*\d)?"
NAME_BEFORE_ID_RE = re.compile(
    rf"(?:^|[,;:|]\s*)(?P<name>{NAME})\s*[,|]?\s*"
    rf"(?i:MASP|MATR[IÍ]CULA)\s*[:.]?\s*(?P<id>{ID})",
)
DIRECT_NAME_RE = re.compile(
    rf"(?:^|[,;:]\s*)\s*(?P<name>{NAME})\s*,?\s+"
    r"(?=(?i:para\s+(?:exercer|o\s+cargo|a\s+fun[cç][aã]o)|do\s+cargo|da\s+fun[cç][aã]o)\b)",
)
ROLE_RE = re.compile(
    r"\b(?:para\s+exercer\s+(?:o\s+)?|para\s+(?:o|a)\s+|do\s+|no\s+|da\s+|na\s+)"
    r"(?P<role>(?:cargo|fun[cç][aã]o)\b[^,.;\n]{0,240})",
    re.I,
)
AGENCY_RE = re.compile(
    r"\b(?:da|do|pela|pelo|na|no)\s+(?P<agency>(?:Secretaria\s+de\s+Estado|"
    r"Subsecretaria|Instituto|Funda[cç][aã]o|Universidade|Departamento|"
    r"Pol[ií]cia\s+Civil|Pol[ií]cia\s+Militar|Gabinete|Controladoria|Advocacia)"
    r"(?:(?!,\s*(?:a\s+partir|ficando|para|nos\s+termos)\b|"
    r"\b(?:nomeia|exonera|MASP|para\s+o\s+cargo)\b)[^.;\n]){0,200})",
    re.I,
)
TABLE_PERSON_RE = re.compile(
    rf"(?:^|\n|\|)[ \t]*(?P<name>{TOKEN}(?:[ \t]+{CONNECTOR}){{1,12}}?)[ \t]*[|]?[ \t]+"
    r"(?P<role>(?:Analista|T[eé]cnico|Assistente|Professor|Especialista|"
    r"Gestor|Auxiliar|Agente|M[eé]dico|Enfermeiro)[^|\d]{1,160}?)\s*[|]?\s*"
    rf"(?P<id>{ID})(?=\s|\||$)",
)
LIST_PERSON_RE = re.compile(
    rf"^[ \t]*(?P<name>{TOKEN}(?:[ \t]+{CONNECTOR}){{1,12}}?)[ \t]*,[ \t]*"
    r"(?i:em\s+substitui[cç][aã]o\s+a|titular|suplente)\b",
    re.M,
)
COUNCIL_ROLE_RE = re.compile(
    r"\b(?:como|para)\s+(?P<role>(?:membro(?:\(s\))?|conselheiro[as]?)\b[^,:;]{0,180})",
    re.I,
)

SIGNER_ROLES = [
    ("2", "Governador em exercicio", r"Governador\s+em\s+exerc[ií]cio"),
    ("1", "Governador", r"Governador"),
    ("4", "Secretario de Estado", r"Secret[aá]ri[oa]\s+de\s+Estado"),
    ("5", "Secretario", r"Secret[aá]ri[oa]"),
    ("3", "Diretor-Presidente", r"Diretor[ a]*-\s*Presidente"),
    ("7", "Diretor-Geral", r"Diretor[ a]*-\s*Geral"),
    ("6", "Presidente", r"Presidente"),
    ("8", "Diretor", r"Diretor[a]?"),
    ("9", "Subsecretario", r"Subsecret[aá]ri[oa]"),
    ("10", "Superintendente", r"Superintendente"),
    ("11", "Chefe de Gabinete", r"Chefe\s+de\s+Gabinete"),
]
SIGNER_HEADER_RE = re.compile(
    r"^[ \t]*(?:#+[ \t]*)?(?P<role>"
    + "|".join(pattern for _, _, pattern in SIGNER_ROLES)
    + r")[ \t]*:[ \t]*(?P<name>[^\r\n|]{4,100})",
    re.I | re.M,
)
SECTION_HEADER_RE = re.compile(
    r"^[ \t]*(?:#+[ \t]*)?(?:Secretaria\s+de\s+Estado|Pol[ií]cia\s+(?:Civil|Militar)|"
    r"Controladoria-Geral|Advocacia-Geral|Instituto\s+de|Funda[cç][aã]o\s+|Universidade\s+)",
    re.I | re.M,
)
