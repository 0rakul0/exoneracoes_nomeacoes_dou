from __future__ import annotations

import re

from diarios_oficiais.utils_regex.common import NAME_CONNECTOR_RE
from diarios_oficiais.utils_regex.common import NAME_TOKEN_RE
from diarios_oficiais.utils_regex.common import SIGNER_CATEGORIES
from diarios_oficiais.utils_regex.common import signer_re


DATE_LINK_RE = re.compile(r'href=["\']do_seleciona_edicao\.php\?data=([^"\']+)["\']', re.I)
EDITION_LINK_RE = re.compile(
    r'<a\s+href=["\'](?P<href>mostra_edicao\.php\?session=[^"\']+)["\'][^>]*>(?P<label>.*?)</a>',
    re.I | re.S,
)
PDF_KEY_RE = re.compile(r'var\s+pd\s*=\s*["\'](?P<key>[A-F0-9-]+)["\']', re.I)

ACT_WINDOW_RE = re.compile(
    r"\b(?P<action>EXONERAR|NOMEAR)\b(?P<body>.{0,1200}?)(?=\b(?:EXONERAR|NOMEAR|DESIGNAR|TORNAR SEM EFEITO|RESOLVE|DECRETO|ATO DO|SECRETARIA|Art\.)|$)",
    re.I | re.S,
)
NAME_AFTER_ACTION_RE = re.compile(
    rf"(?:^|,\s*)(?P<name>{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,9}})(?=,|\s+para\s+|\s+do\s+|\s+da\s+)",
    re.I,
)
ROLE_RE = re.compile(
    r"(?:para exercer|do|da)\s+(?:o\s+|a\s+)?(?P<role>cargo(?:\s+em\s+comiss[a\u00e3]o)?|funcao|fun\u00e7\u00e3o|emprego|chefia|direcao|dire\u00e7\u00e3o|assessoria)[^,.;\n]{0,220}",
    re.I,
)
AGENCY_RE = re.compile(
    r"\b(?:da|do)\s+(Secretaria|Subsecretaria|Fundacao|Funda\u00e7\u00e3o|Instituto|Departamento|Gabinete|Superintendencia|Superintend\u00eancia|Autarquia)\b[^,.;\n]{0,180}",
    re.I,
)
FUNCTIONAL_ID_RE = re.compile(
    r"\bID\s+FUNCIONAL\s*(?:N[\u00ba\u00b0O.]*)?\s*(?P<id>[\d.\-/]+)",
    re.I,
)
SIGNER_RE = signer_re(SIGNER_CATEGORIES)
