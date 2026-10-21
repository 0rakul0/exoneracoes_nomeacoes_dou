from __future__ import annotations

import re

from diarios_oficiais.utils_regex import ba_doe as _base


# No DOE/PB e no DJE/PB, as formas incidentais em texto corrido aparecem com
# frequência (por exemplo, "nomear o arquivo"). Os atos de pessoal aparecem
# depois de RESOLVE ou de um artigo; usar esse contexto reduz falsos positivos.
ACTION_RE = r"(?:EXONER(?:AR|AD[AO]S?)|NOME(?:AR|AD[AO]S?))"
ACT_WINDOW_RE = re.compile(
    rf"(?:\bRESOLVE\s*:\s*|\bArt\.\s*\d+[º°o]?\s*[-–—:]?\s*)"
    rf"(?P<action>{ACTION_RE})\b(?P<body>.{{0,2200}}?)(?="
    rf"\b(?:{ACTION_RE}|DESIGNAR|DESIGNADO|CESSAR|TORNAR\s+SEM\s+EFEITO|"
    rf"RESOLVE|DECRETO|PORTARIA|RETIFICA(?:R|ÇÃO)?|Art\.)\b|$)",
    re.I | re.S,
)


# Reaproveita as regras estruturais comuns já usadas no DOE/BA, sem atribuir
# ao texto paraibano nomes de órgãos específicos da Bahia.
NAME_AFTER_ACTION_RE = _base.NAME_AFTER_ACTION_RE
TABLE_NAME_RE = _base.TABLE_NAME_RE
ROLE_RE = _base.ROLE_RE
AGENCY_RE = _base.AGENCY_RE
FUNCTIONAL_ID_RE = _base.FUNCTIONAL_ID_RE
SIGNER_CATEGORIES = _base.SIGNER_CATEGORIES
SIGNER_RE = _base.SIGNER_RE
