from __future__ import annotations

import csv
import json
import sys
import base64
import re
import argparse
from dataclasses import asdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# ============================================================
# EXTRATOR — NORMATIVAS DE CIRCUNSCRIÇÃO / ISP COM LINK
# ============================================================
#
# Corrige o caso em que o Markdown vem assim:
#
#   ## RESOLUÇÃO SESEG Nº 1267 DE 13 DE DEZEMBRO DE 2018
#   ## REVOGA A RESOLUÇÃO SESEG Nº 951...
#
# A versão anterior podia não capturar a norma porque a regex esperava:
#
#   RESOLUÇÃO SESEG Nº ...
#
# sem o prefixo Markdown "##".
#
# Como usar:
#
# 1. Coloque este script na raiz do projeto, ou ajuste MARKDOWN_DIR.
# 2. Confira as configurações abaixo.
# 3. Dê play no PyCharm.
#
# ============================================================


# ------------------------------------------------------------
# CONFIGURAÇÕES FIXAS — só dar play
# ------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Se o script estiver na raiz do projeto, ele vai procurar em LAKE/RJ.
# Se quiser outro caminho, altere aqui.
MARKDOWN_DIR = BASE_DIR / "LAKE" / "RJ"

OUTPUT_CSV = BASE_DIR / "saida" / "ISP" / "DOERJ_normativas_circunscricao.csv"

START_DATE: date | None = None
END_DATE: date | None = None


# ------------------------------------------------------------
# REGEX
# ------------------------------------------------------------

MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")

# Aceita:
#   ## Secretaria de Estado de Segurança
#   ## Secretaria de Estado de Segurança Pública
SECURITY_HEADING_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?Secretaria\s+de\s+Estado\s+de\s+Seguran[çc]a(?:\s+P[úu]blica)?\s*$"
)

# Próxima secretaria encerra o bloco atual.
NEXT_SECRETARIA_HEADING_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?Secretaria\s+de\s+Estado\s+"
)

# Aceita subtítulos dentro da secretaria.
AUTHORITY_HEADING_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?P<authority>"
    r"ATO\s+DO\s+SECRET[ÁA]RIO|"
    r"ATOS\s+DO\s+SECRET[ÁA]RIO|"
    r"DESPACHO\s+DO\s+SECRET[ÁA]RIO|"
    r"DESPACHOS\s+DO\s+SECRET[ÁA]RIO|"
    r"RESOLU[ÇC][ÕO]ES|"
    r"RESOLU[ÇC][ÃA]O|"
    r"PORTARIAS|"
    r"PORTARIA"
    r")\s*$"
)

NORMATIVE_HEADER_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?"
    r"(?P<tipo>RESOLU[ÇC][ÃA]O|PORTARIA|DECRETO|ATO|INSTRU[ÇC][ÃA]O\s+NORMATIVA)"
    r"(?:\s+(?P<sigla>[A-Z]{2,15}))?"
    r"\s+(?:N[º°O]\.?|N\.º|Nº|NO|N\.)\s*"
    r"(?P<numero>[\d./-]+)"
    r"\s+DE\s+"
    r"(?P<data_texto>[^\n\r]+)"
    r"\.?\s*$"
)

RESOLVE_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?RESOLVE\s*:?\s*$"
)

CONSIDERANDO_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?CONSIDERANDO\s*:?\s*$"
)

SECRETARIO_BODY_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?O\s+SECRET[ÁA]RIO\s+DE\s+ESTADO\s+DE\s+SEGURAN[ÇC]A\b"
)

ARTICLE_RE = re.compile(
    r"(?ims)"
    r"(?:^|\n)\s*(?:[-*]\s*)?"
    r"(?P<label>Art\.?\s*\d+[º°]?(?:-[A-Z])?)"
    r"\s*(?P<body>.*?)(?="
    r"\n\s*(?:[-*]\s*)?Art\.?\s*\d+[º°]?(?:-[A-Z])?\s+|"
    r"\n\s*Rio\s+de\s+Janeiro\s*,|"
    r"\n\s*(?:#{1,6}\s*)?ATO\s+DO\s+SECRET[ÁA]RIO\b|"
    r"\n\s*(?:#{1,6}\s*)?(?:RESOLU[ÇC][ÃA]O|PORTARIA|DECRETO)\s+|"
    r"\Z)"
)

RIO_ASSINATURA_RE = re.compile(
    r"(?ims)\n\s*Rio\s+de\s+Janeiro\s*,\s*(?P<assinatura>.+?)\s*$"
)

SPACE_RE = re.compile(r"\s+")

ALLOWED_SECURITY_SIGLAS = {
    "SESEG",
    "SSP",
    "SESP",
    "SEPOL",
    "SEPM",
    "PCERJ",
    "PMERJ",
}

SECURITY_SCOPE_TERMS = [
    "SECRETARIA DE ESTADO DE SEGURANCA",
    "SECRETARIA DE ESTADO DE SEGURANCA PUBLICA",
    "SECRETARIA DE ESTADO DE POLICIA CIVIL",
    "SECRETARIA DE ESTADO DE POLICIA MILITAR",
    "POLICIA CIVIL",
    "POLICIA MILITAR",
    "INSTITUTO DE SEGURANCA PUBLICA",
    "ISP/RJ",
    "ISP-RJ",
    "PCERJ",
    "PMERJ",
]

PUBLICATION_ID_RE = re.compile(r"(?i)\bId\s*:?\s*\d+\.?")

RIO_DE_JANEIRO_RE = re.compile(r"(?i)\bRio\s+de\s+Janeiro\s*,")

NEXT_PUBLICATION_HEADING_AFTER_SIGNATURE_RE = re.compile(
    r"(?i)(?:^|\s)#{1,6}\s*("
    r"SECRETARIA\s+DE\s+ESTADO|"
    r"POL[ÍI]CIA\s+CIVIL|"
    r"CORREGEDORIA|"
    r"ATO\s+DO|"
    r"ATOS\s+DO|"
    r"DESPACHO\s+DO|"
    r"DESPACHOS\s+DO"
    r")\b"
)


@dataclass
class NormativaSeguranca:
    estado: str
    diario: str
    data_publicacao: str
    arquivo_markdown: str
    link: str
    secretaria_bloco: str
    autoridade_bloco: str
    tipo_norma: str
    sigla_norma: str
    numero_norma: str
    data_norma_texto: str
    ementa: str
    considerando: str
    mudancas_resumo: str
    artigos_json: str
    assinatura: str
    texto_norma: str



def normalizar_espacos(value: str) -> str:
    return SPACE_RE.sub(" ", value or "").strip()


def normalizar_para_busca(value: str) -> str:
    """
    Normaliza texto para busca:
    - remove acentos;
    - coloca em maiúsculas;
    - compacta espaços.
    """
    import unicodedata

    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.upper()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def separar_data_e_ementa_cabecalho(data_texto: str) -> tuple[str, str]:
    texto = normalizar_espacos(data_texto)
    match = re.match(
        r"^(?P<data>\d{1,2}\s+DE\s+[A-ZÇ]+(?:\s+DE)?\s+\d{4})(?:\s+(?P<ementa>.+))?$",
        texto,
        flags=re.I,
    )
    if not match:
        return texto, ""
    return normalizar_espacos(match.group("data")), normalizar_espacos(match.group("ementa") or "")


def juntar_unicos_texto(values: list[str]) -> str:
    saida: list[str] = []
    vistos: set[str] = set()
    for value in values:
        item = normalizar_espacos(value)
        if not item:
            continue
        chave = normalizar_para_busca(item)
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(item)
    return " ".join(saida)


def eh_resolucao_seseg(tipo_norma: str, sigla_norma: str) -> bool:
    return normalizar_para_busca(tipo_norma) == "RESOLUCAO" and normalizar_para_busca(sigla_norma) == "SESEG"


CIRCUNSCRICAO_RE = re.compile(
    r"\bCIRCUNSCRI(?:CAO|COES|CIONAL|CIONAIS|CIONARIA|CIONARIAS|CIONADO|CIONADOS|CIONADA|CIONADAS)\b",
    flags=re.I,
)

AREA_ATUACAO_RE = re.compile(
    r"\b(?:AISP|RISP|CISP)\b|"
    r"\b(?:AREA|AREAS|ÁREA|ÁREAS)\s+(?:INTEGRADA|INTEGRADAS)\s+DE\s+SEGURANCA\s+PUBLICA\b|"
    r"\b(?:REGIAO|REGIOES|REGIÃO|REGIÕES)\s+(?:INTEGRADA|INTEGRADAS)\s+DE\s+SEGURANCA\s+PUBLICA\b|"
    r"\b(?:CIRCUNSCRICAO|CIRCUNSCRICOES|CIRCUNSCRIÇÃO|CIRCUNSCRIÇÕES)\s+(?:INTEGRADA|INTEGRADAS)\s+DE\s+SEGURANCA\s+PUBLICA\b|"
    r"\b(?:AREA|AREAS|ÁREA|ÁREAS)\s+DE\s+(?:ATUACAO|ATUAÇÃO|POLICIAMENTO)\b|"
    r"\bLIMITES?\s+(?:TERRITORIAIS|CIRCUNSCRICIONAIS)\b|"
    r"\b(?:ALTERA|ALTERAR|MODIFICA|MODIFICAR|RESTAURA|RESTAURAR|IMPLANTA|IMPLANTAR|CRIA|CRIAR|EXTINGUE|EXTINGUIR|REVOGA|REVOGAR)\b.{0,120}\b(?:DP|DELEGACIA|BPM|AISP|RISP|CISP)\b|"
    r"\b(?:DP|DELEGACIA|BPM|AISP|RISP|CISP)\b.{0,120}\b(?:AREA|ÁREA|LIMITES?|CIRCUNSCRI|ATUACAO|ATUAÇÃO|POLICIAMENTO)\b",
    flags=re.I,
)


def normativa_trata_de_circunscricao(
    ementa: str,
    considerando: str,
    mudancas_resumo: str,
    texto_norma: str,
) -> bool:
    """
    Mantém normativas que tratam de circunscrição ou área de atuação.

    Captura variações como:
        circunscrição
        circunscrições
        circunscricional
        circunscricionais
        circunscricionária
        limites circunscricionais
    """
    texto_busca = normalizar_para_busca(
        " ".join(
            [
                ementa or "",
                considerando or "",
                mudancas_resumo or "",
                texto_norma or "",
            ]
        )
    )
    return bool(CIRCUNSCRICAO_RE.search(texto_busca) or AREA_ATUACAO_RE.search(texto_busca))


def normativa_esta_no_escopo_seguranca(sigla_norma: str, texto_norma: str) -> bool:
    if sigla_norma in ALLOWED_SECURITY_SIGLAS:
        return True

    if sigla_norma:
        return False

    texto_busca = normalizar_para_busca(texto_norma[:5000])
    return any(term in texto_busca for term in SECURITY_SCOPE_TERMS)


def normativa_sem_sigla_tem_escopo_na_ementa(*partes: str) -> bool:
    texto_busca = normalizar_para_busca(" ".join(partes))
    termos = [
        "SEGURANCA PUBLICA",
        "SECRETARIA DE ESTADO DE POLICIA CIVIL",
        "SECRETARIA DE ESTADO DE POLICIA MILITAR",
        "POLICIA CIVIL",
        "POLICIA MILITAR",
        "INSTITUTO DE SEGURANCA PUBLICA",
    ]
    return any(term in texto_busca for term in termos)


IOERJ_BASE_URL = "https://www.ioerj.com.br/portal/modules/conteudoonline/"


def montar_link_ioerj_pela_data(markdown_path: Path) -> str:
    """
    Monta o link da página de edições da IOERJ usando a data no nome do Markdown.

    Exemplo:
        DOERJ_DO_CAMPOS_PODER_EXECUTIVO_2016-01-04.md

    Gera:
        https://www.ioerj.com.br/portal/modules/conteudoonline/do_seleciona_edicao.php?data=MjAxNjAxMDQ=
    """
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", markdown_path.name)

    if not match:
        return ""

    data_str = f"{match.group(1)}{match.group(2)}{match.group(3)}"
    encoded = base64.b64encode(data_str.encode("ascii")).decode("ascii")

    return f"{IOERJ_BASE_URL}do_seleciona_edicao.php?data={encoded}"


def limpar_linha_markdown(value: str) -> str:
    value = re.sub(r"^\s*#{1,6}\s*", "", value or "")
    value = value.strip(" -*\t\r\n")
    return normalizar_espacos(value)


def extrair_data_do_markdown(markdown_path: Path) -> date | None:
    match = MARKDOWN_DATE_RE.search(markdown_path.stem)
    if not match:
        return None
    return date.fromisoformat(match.group(1))


def recortar_blocos_secretaria_seguranca(text: str) -> list[tuple[str, str]]:
    """
    Recorta blocos da Secretaria de Estado de Segurança.

    Aceita:

        ## Secretaria de Estado de Segurança
        Secretaria de Estado de Segurança

    Também tem fallback para textos em que o cabeçalho veio ruim,
    mas existem sinais fortes de atos da SESEG.
    """
    matches = list(SECURITY_HEADING_RE.finditer(text))
    blocos: list[tuple[str, str]] = []

    for match in matches:
        start = match.start()
        secretaria_heading = limpar_linha_markdown(match.group(0))

        next_match = NEXT_SECRETARIA_HEADING_RE.search(text, match.end())
        end = next_match.start() if next_match else len(text)

        blocos.append((secretaria_heading, text[start:end].strip()))

    if blocos:
        return blocos

    texto_normalizado = normalizar_para_busca(text)

    if (
        "SECRETARIA DE ESTADO DE SEGURANCA" in texto_normalizado
        or "SECRETARIO DE ESTADO DE SEGURANCA" in texto_normalizado
        or "RESOLUCAO SESEG" in texto_normalizado
    ):
        return [("Secretaria de Estado de Segurança", text.strip())]

    return blocos


def split_por_autoridade(bloco_secretaria: str) -> list[tuple[str, str]]:
    matches = list(AUTHORITY_HEADING_RE.finditer(bloco_secretaria))

    if not matches:
        return [("", bloco_secretaria)]

    partes: list[tuple[str, str]] = []

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(bloco_secretaria)
        autoridade = limpar_linha_markdown(match.group("authority"))
        partes.append((autoridade, bloco_secretaria[start:end].strip()))

    return partes


def recortar_ate_id_publicacao(texto_norma: str) -> str:
    """
    Evita que uma norma carregue o restante do diário.

    Nos Markdown do DOERJ, o marcador "Id:" costuma encerrar o ato
    publicado. Manter o texto até esse ponto preserva anexos que aparecem
    antes do Id e corta seções administrativas/tabelas que vêm depois.
    """
    candidatos = []

    id_match = PUBLICATION_ID_RE.search(texto_norma)
    if id_match:
        candidatos.append(id_match.end())

    assinatura_match = RIO_DE_JANEIRO_RE.search(texto_norma)
    if assinatura_match:
        next_heading = NEXT_PUBLICATION_HEADING_AFTER_SIGNATURE_RE.search(
            texto_norma,
            assinatura_match.end(),
        )
        if next_heading:
            candidatos.append(next_heading.start())

    if not candidatos:
        return texto_norma.strip()

    return texto_norma[: min(candidatos)].strip()


def encontrar_normas_em_bloco(bloco: str) -> list[tuple[re.Match[str], str]]:
    matches = list(NORMATIVE_HEADER_RE.finditer(bloco))
    normas: list[tuple[re.Match[str], str]] = []

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(bloco)
        texto_norma = recortar_ate_id_publicacao(bloco[start:end])
        normas.append((match, texto_norma))

    return normas


def extrair_ementa(texto_norma: str, header_end_offset: int = 0) -> str:
    """
    Extrai a ementa.

    Agora trata corretamente:
        ## REVOGA A RESOLUÇÃO...
    e para antes de:
        O SECRETÁRIO...
        ## CONSIDERANDO:
        ## RESOLVE:
    """
    texto = texto_norma[header_end_offset:].strip()

    stops = []

    for regex in [SECRETARIO_BODY_RE, CONSIDERANDO_RE, RESOLVE_RE, ARTICLE_RE]:
        match = regex.search(texto)
        if match:
            stops.append(match.start())

    trecho = texto[: min(stops)] if stops else texto[:1500]

    linhas = []
    for linha in trecho.splitlines():
        linha_limpa = limpar_linha_markdown(linha)
        if not linha_limpa:
            continue
        linhas.append(linha_limpa)

    return normalizar_espacos(" ".join(linhas))


def extrair_considerando(texto_norma: str) -> str:
    match = CONSIDERANDO_RE.search(texto_norma)
    if not match:
        return ""

    start = match.end()

    resolve_match = RESOLVE_RE.search(texto_norma, start)
    end = resolve_match.start() if resolve_match else len(texto_norma)

    trecho = texto_norma[start:end]
    linhas = []

    for linha in trecho.splitlines():
        linha_limpa = limpar_linha_markdown(linha)
        if not linha_limpa:
            continue
        linhas.append(linha_limpa)

    return normalizar_espacos(" ".join(linhas))


def extrair_artigos(texto_norma: str) -> list[dict[str, str]]:
    artigos: list[dict[str, str]] = []
    texto_norma = re.sub(
        r"(?<!^)(?<!\n)\s+(Art\.?\s*\d+[^A-Za-z0-9\s]?(?:-[A-Z])?)",
        r"\n\1",
        texto_norma,
    )

    article_re = re.compile(
        r"(?ms)(?:^|\n)\s*(?:[-*]\s*)?"
        r"(?P<label>Art\.?\s*\d+[^A-Za-z0-9\s]?(?:-[A-Z])?)"
        r"\s*(?P<body>.*?)(?="
        r"\n\s*(?:[-*]\s*)?Art\.?\s*\d+[^A-Za-z0-9\s]?(?:-[A-Z])?\s*|"
        r"\n\s*Rio\s+de\s+Janeiro\s*,|"
        r"\n\s*(?:#{1,6}\s*)?(?:RESOLU|PORTARIA|DECRETO)\s+|"
        r"\Z)"
    )

    for match in article_re.finditer(texto_norma):
        label = normalizar_espacos(match.group("label"))
        body = normalizar_espacos(match.group("body").strip(" -"))

        if not body:
            continue

        artigos.append(
            {
                "artigo": label,
                "texto": body,
                "acao": classificar_acao_artigo(body),
                "objeto": extrair_objeto_mudanca(body),
            }
        )

    return artigos


def classificar_acao_artigo(texto_artigo: str) -> str:
    texto = texto_artigo.upper()

    regras = [

        ("revogacao", r"\bREVOGAD[AO]\b|\bREVOGAR\b|\bREVOGA[ -]SE\b|\bREVOGANDO[ -]SE\b"),
        ("extincao", r"\bEXTINGUIR\b|\bFICA\s+EXTINT[AO]\b|\bEXTIN[ÇC][ÃA]O\b"),
        ("alteracao", r"\bALTERAR\b|\bFICA\s+ALTERAD[AO]\b|\bALTERA[ÇC][ÃA]O\b"),
        ("alteracao", r"\bPASSA\s+A\s+(?:INTEGRAR|VIGORAR)\b|\bPASSANDO\s+A\b|\bTRANSFERINDO\b|\bTRANSFERIR\b"),
        ("criacao", r"\bCRIAR\b|\bFICA\s+CRIAD[AO]\b|\bINSTITUIR\b|\bINSTITUI\b"),
        ("designacao_competencia", r"\bCABER[ÁA]\b|\bCOMPETE\b|\bDEVER[ÁA]\b"),
        ("vigencia", r"\bENTRAR[ÁA]\s+EM\s+VIGOR\b|\bENTRA\s+EM\s+VIGOR\b"),
        ("redistribuicao", r"\bDISTRIBUI[ÇC][ÃA]O\b|\bREDISTRIBUI[ÇC][ÃA]O\b"),
        ("policiamento", r"\b[ÁA]REA\s+DE\s+POLICIAMENTO\b|\bPOLICIAMENTO\b"),
    ]

    for label, pattern in regras:
        if re.search(pattern, texto, flags=re.I):
            return label

    return "outros"


def extrair_objeto_mudanca(texto_artigo: str) -> str:
    texto = normalizar_espacos(texto_artigo)

    padroes = [
        r"\bFica\s+revogad[ao]\s+(?P<objeto>.+?)(?:\.|$)",
        r"\bRevogar\s+(?P<objeto>.+?)(?:\.|$)",
        r"\bExtinguir\s+(?P<objeto>.+?)(?:\.|$)",
        r"\bAlterar\s+(?P<objeto>.+?)(?:,?\s+que\s+passar[áa]|\.|$)",
        r"\bCriar\s+(?P<objeto>.+?)(?:\.|$)",
        r"\bInstituir\s+(?P<objeto>.+?)(?:\.|$)",
        r"\bCaber[áa]\s+(?P<objeto>.+?)(?:\.|$)",
    ]

    for pattern in padroes:
        match = re.search(pattern, texto, flags=re.I)
        if match:
            return normalizar_espacos(match.group("objeto"))

    return texto[:350]


def resumir_mudancas(artigos: list[dict[str, str]]) -> str:
    if not artigos:
        return ""

    partes: list[str] = []

    for artigo in artigos:
        label = artigo["artigo"]
        acao = artigo["acao"]
        objeto = artigo["objeto"]

        if acao == "revogacao":
            partes.append(f"{label}: revoga {objeto}")
        elif acao == "extincao":
            partes.append(f"{label}: extingue {objeto}")
        elif acao == "alteracao":
            partes.append(f"{label}: altera {objeto}")
        elif acao == "criacao":
            partes.append(f"{label}: cria/institui {objeto}")
        elif acao == "designacao_competencia":
            partes.append(f"{label}: atribui competência/responsabilidade — {objeto}")
        elif acao == "vigencia":
            partes.append(f"{label}: define vigência")
        else:
            partes.append(f"{label}: {objeto}")

    return " | ".join(partes)


def extrair_assinatura(texto_norma: str) -> str:
    match = RIO_ASSINATURA_RE.search(texto_norma)
    if not match:
        return ""
    assinatura = match.group("assinatura")
    assinatura = re.sub(r"^\s*de\s+\w+\s+de\s+\d{4}\s*", "", assinatura, flags=re.I)
    return normalizar_espacos(assinatura)


def parse_normativas_seguranca_do_texto(
    text: str,
    markdown_path: Path,
    data_publicacao: date,
    link: str = "",
) -> list[NormativaSeguranca]:
    normativas: list[NormativaSeguranca] = []

    blocos_secretaria = recortar_blocos_secretaria_seguranca(text)

    for secretaria_heading, bloco_secretaria in blocos_secretaria:
        partes_autoridade = split_por_autoridade(bloco_secretaria)

        for autoridade, bloco_autoridade in partes_autoridade:
            normas = encontrar_normas_em_bloco(bloco_autoridade)

            for header_match, texto_norma in normas:
                tipo_norma = normalizar_espacos(header_match.group("tipo"))
                sigla_norma = normalizar_espacos(header_match.group("sigla") or "")
                numero_norma = normalizar_espacos(header_match.group("numero"))
                data_norma_texto, ementa_cabecalho = separar_data_e_ementa_cabecalho(
                    header_match.group("data_texto")
                )

                if not normativa_esta_no_escopo_seguranca(sigla_norma, texto_norma):
                    continue

                header_rel_end = header_match.end() - header_match.start()

                ementa = juntar_unicos_texto(
                    [
                        ementa_cabecalho,
                        extrair_ementa(texto_norma, header_end_offset=header_rel_end),
                    ]
                )
                considerando = extrair_considerando(texto_norma)
                artigos = extrair_artigos(texto_norma)
                mudancas_resumo = resumir_mudancas(artigos)
                assinatura = extrair_assinatura(texto_norma)

                if not sigla_norma and not normativa_sem_sigla_tem_escopo_na_ementa(
                    ementa,
                    considerando,
                    mudancas_resumo,
                ):
                    continue

                if not eh_resolucao_seseg(tipo_norma, sigla_norma) and not normativa_trata_de_circunscricao(
                    ementa=ementa,
                    considerando=considerando,
                    mudancas_resumo=mudancas_resumo,
                    texto_norma=texto_norma,
                ):
                    continue

                normativas.append(
                    NormativaSeguranca(
                        estado="RJ",
                        diario="Diário Oficial do Estado do Rio de Janeiro",
                        data_publicacao=data_publicacao.isoformat(),
                        arquivo_markdown=str(markdown_path),
                        link=link,
                        secretaria_bloco=secretaria_heading,
                        autoridade_bloco=autoridade,
                        tipo_norma=tipo_norma,
                        sigla_norma=sigla_norma,
                        numero_norma=numero_norma,
                        data_norma_texto=data_norma_texto,
                        ementa=ementa,
                        considerando=considerando,
                        mudancas_resumo=mudancas_resumo,
                        artigos_json=json.dumps(artigos, ensure_ascii=False),
                        assinatura=assinatura,
                        texto_norma=normalizar_espacos(texto_norma),
                    )
                )

    return normativas


def parse_normativas_seguranca_markdown(markdown_path: Path) -> list[NormativaSeguranca]:
    data_publicacao = extrair_data_do_markdown(markdown_path)

    if data_publicacao is None:
        print(f"Não consegui extrair data do arquivo: {markdown_path}", file=sys.stderr)
        return []

    link = montar_link_ioerj_pela_data(markdown_path)

    text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    return parse_normativas_seguranca_do_texto(
        text=text,
        markdown_path=markdown_path,
        data_publicacao=data_publicacao,
        link=link,
    )


def listar_markdowns(
    markdown_dir: Path,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Path]:
    if not markdown_dir.exists():
        print(f"Diretório não encontrado: {markdown_dir}", file=sys.stderr)
        return []

    arquivos: list[Path] = []

    for markdown_path in sorted(markdown_dir.rglob("*.md")):
        data_publicacao = extrair_data_do_markdown(markdown_path)

        if data_publicacao is None:
            continue
        if start_date is not None and data_publicacao < start_date:
            continue
        if end_date is not None and data_publicacao > end_date:
            continue

        arquivos.append(markdown_path)

    return arquivos


def deduplicar_normativas(normativas: list[NormativaSeguranca]) -> list[NormativaSeguranca]:
    vistas: set[tuple[str, str, str, str]] = set()
    saida: list[NormativaSeguranca] = []

    for normativa in normativas:
        chave = (
            normativa.data_publicacao,
            normativa.tipo_norma,
            normativa.sigla_norma,
            normativa.numero_norma,
        )

        if chave in vistas:
            continue

        vistas.add(chave)
        saida.append(normativa)

    return saida


def gravar_csv(output_path: Path, normativas: list[NormativaSeguranca]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "estado",
        "diario",
        "data_publicacao",
        "arquivo_markdown",
        "link",
        "secretaria_bloco",
        "autoridade_bloco",
        "tipo_norma",
        "sigla_norma",
        "numero_norma",
        "data_norma_texto",
        "ementa",
        "considerando",
        "mudancas_resumo",
        "artigos_json",
        "assinatura",
        "texto_norma",
    ]

    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for normativa in normativas:
            writer.writerow(asdict(normativa))


def parse_date_arg(value: str | None) -> date | None:
    if not value:
        return None

    return date.fromisoformat(value)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrai normativas de circunscrição da área de segurança pública do DOERJ."
    )
    parser.add_argument(
        "--markdown-dir",
        type=Path,
        default=MARKDOWN_DIR,
        help=f"Diretório com Markdown do DOERJ. Padrão: {MARKDOWN_DIR}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_CSV,
        help=f"CSV de saída. Padrão: {OUTPUT_CSV}",
    )
    parser.add_argument(
        "--start-date",
        type=parse_date_arg,
        default=START_DATE,
        help="Data inicial no formato AAAA-MM-DD.",
    )
    parser.add_argument(
        "--end-date",
        type=parse_date_arg,
        default=END_DATE,
        help="Data final no formato AAAA-MM-DD.",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()

    print("=" * 70)
    print("EXTRATOR — NORMATIVAS DE CIRCUNSCRIÇÃO / ISP COM LINK")
    print("=" * 70)

    print(f"\nDiretório de Markdown: {args.markdown_dir}")
    print(f"CSV de saída: {args.output}")

    markdowns = listar_markdowns(
        markdown_dir=args.markdown_dir,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    todas_normativas: list[NormativaSeguranca] = []

    for markdown_path in markdowns:
        try:
            normativas = parse_normativas_seguranca_markdown(markdown_path)
            todas_normativas.extend(normativas)

            if normativas:
                numeros = ", ".join(n.numero_norma for n in normativas)
                print(
                    f"{markdown_path.name}: {len(normativas)} normativa(s): {numeros}",
                    file=sys.stderr,
                )

        except Exception as exc:
            print(f"Falha ao processar {markdown_path}: {exc}", file=sys.stderr)

    todas_normativas = deduplicar_normativas(todas_normativas)
    gravar_csv(args.output, todas_normativas)

    print(
        f"\n{len(markdowns)} arquivos Markdown avaliados; "
        f"{len(todas_normativas)} normativas de circunscrição gravadas em {args.output}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
