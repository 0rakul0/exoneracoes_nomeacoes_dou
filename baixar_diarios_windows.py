"""Download continuo dos diarios oficiais, sem GPU, Docling, OCR ou argparse.

Execute: python baixar_diarios_windows.py
Edite as constantes abaixo para ajustar o comportamento.
"""
from __future__ import annotations

import heapq
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Evita inicializar validacao spaCy nos coletores somente para download.
from diarios_oficiais.fila_processamento import registrar
from diarios_oficiais.base import BaseGazetteCollector
BaseGazetteCollector.enable_spacy_validation = False

from diarios_oficiais.rodizio_estadual import STATE_SPECS, _iter_collector_editions

INTERVALO_ENTRE_RODADAS_HORAS = 6
INTERVALO_APOS_ERRO_MINUTOS = 15
EXECUTAR_CONTINUAMENTE = True
PULAR_ANOS_COMPLETOS = False  # PDF pode faltar mesmo quando o Markdown do ano ja esta completo.
BAIXAR_HTML_BA = True         # DOE/BA publico oferece HTML, nao PDF sem autenticacao.
VALIDAR_PDF_EXISTENTE = True
INTERVALO_ATUALIZACAO_RECENTES_MINUTOS = 60
QUANTIDADE_DIAS_RECENTES = 3
VERIFICAR_RECENTES_A_CADA_EDICOES = 50
TENTATIVAS_POR_DOWNLOAD = 1
TIMEOUT_REQUISICAO_SEGUNDOS = 15
PAUSA_UF_COM_ERRO_MINUTOS = 30

# Evita insistir no mesmo estado quando a fonte esta indisponivel.
UF_EM_PAUSA: dict[str, float] = {}

RAIZ = Path(__file__).resolve().parent
LOG_DIR = RAIZ / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
ARQUIVO_LOG = LOG_DIR / "download_diarios.log"


def logger_configurado() -> logging.Logger:
    logger = logging.getLogger("download_diarios")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        for handler in (
            logging.FileHandler(ARQUIVO_LOG, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ):
            handler.setFormatter(fmt)
            logger.addHandler(handler)
        logger.propagate = False
    return logger


def configurar_coletor(coletor):
    """Configura uma unica tentativa por arquivo e timeout curto."""
    coletor.max_attempts = TENTATIVAS_POR_DOWNLOAD
    coletor.http_timeout_seconds = TIMEOUT_REQUISICAO_SEGUNDOS
    return coletor


def uf_disponivel(uf: str) -> bool:
    return time.monotonic() >= UF_EM_PAUSA.get(uf, 0)


def pausar_uf(uf: str, logger: logging.Logger) -> None:
    limite = time.monotonic() + PAUSA_UF_COM_ERRO_MINUTOS * 60
    if uf_disponivel(uf):
        logger.warning(
            "PULANDO UF %s por %s minutos apos falha; seguindo para outro estado.",
            uf, PAUSA_UF_COM_ERRO_MINUTOS,
        )
    UF_EM_PAUSA[uf] = limite


def pdf_valido(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 8:
        return False
    with path.open("rb") as arquivo:
        return arquivo.read(5) == b"%PDF-"


def processar_edicao(item, logger: logging.Logger) -> tuple[int, int, int]:
    """Processa uma edicao; retorna (baixados, existentes, falhas)."""
    uf, coletor, edicao = item.state, item.collector, item.edition
    markdown = coletor.markdown_path_for(edicao)
    destino = markdown.with_suffix(".pdf")
    try:
        if uf == "BA" and coletor.gazette_code == "DOBA":
            if not BAIXAR_HTML_BA:
                return 0, 0, 0
            existente = markdown.is_file() and markdown.stat().st_size > 0
            if not existente:
                coletor.load_or_create_markdown(edicao, markdown)
            registrar(uf, coletor.gazette_code, edicao.publication_date.isoformat(),
                      edicao.section, edicao.url, markdown)
            logger.info("HTML | BA | %s | %s", edicao.publication_date, markdown)
            return (0, 1, 0) if existente else (1, 0, 0)

        if destino.exists() and (not VALIDAR_PDF_EXISTENTE or pdf_valido(destino)):
            registrar(uf, coletor.gazette_code, edicao.publication_date.isoformat(),
                      edicao.section, edicao.url, destino)
            return 0, 1, 0

        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_name(destino.name + ".part")
        try:
            temporario.unlink(missing_ok=True)
            resultado = coletor.download_edition_pdf(edicao, temporario)
            if resultado is not None and Path(resultado) != temporario:
                raise RuntimeError("Coletor retornou arquivo diferente do destino temporario")
            if not pdf_valido(temporario):
                raise RuntimeError("Arquivo recebido nao possui cabecalho PDF valido")
            os.replace(temporario, destino)
            registrar(uf, coletor.gazette_code, edicao.publication_date.isoformat(),
                      edicao.section, edicao.url, destino)
            logger.info("BAIXADO | %s | %s | %s", uf, edicao.publication_date, destino)
            return 1, 0, 0
        finally:
            temporario.unlink(missing_ok=True)
    except Exception as exc:
        logger.exception("FALHA | %s | %s | %s", uf, edicao.publication_date, edicao.section)
        try:
            coletor.record_collection_failure(edicao, "download_pdf", exc)
        except Exception:
            logger.exception("Falha ao registrar erro de %s", uf)
        pausar_uf(uf, logger)
        return 0, 0, 1


def coletar_recentes(logger: logging.Logger) -> tuple[int, int, int]:
    """Prioridade absoluta: ultimos dias em todas as fontes, antes do historico."""
    contagem = [0, 0, 0]
    hoje = datetime.now().date()
    # Primeiro a data de hoje em TODAS as UFs; depois ontem, anteontem.
    fontes = []
    for uf, specs in STATE_SPECS:
        for spec in specs:
            try:
                fontes.append((uf, spec, configurar_coletor(spec.collector_factory())))
            except Exception:
                logger.exception("Falha ao inicializar fonte recente %s", uf)
                contagem[2] += 1

    from diarios_oficiais.rodizio_estadual import PendingEdition
    for atraso in range(QUANTIDADE_DIAS_RECENTES):
        dia = hoje - timedelta(days=atraso)
        for uf, spec, coletor in fontes:
            if not uf_disponivel(uf):
                continue
            try:
                edicoes = coletor.list_editions(dia)
            except Exception:
                logger.exception("Falha ao listar recentes %s %s", uf, dia)
                contagem[2] += 1
                pausar_uf(uf, logger)
                continue
            for edicao in edicoes:
                if not uf_disponivel(uf):
                    break
                resultado = processar_edicao(
                    PendingEdition(uf, coletor, edicao, spec.parser), logger
                )
                for i in range(3):
                    contagem[i] += resultado[i]
    logger.info(
        "Recentes verificados | novos=%s existentes=%s falhas=%s",
        *contagem,
    )
    return tuple(contagem)


def coletar_rodada(logger: logging.Logger) -> tuple[int, int, int]:
    totais = [0, 0, 0]
    def acumular(resultado):
        for i in range(3):
            totais[i] += resultado[i]

    # 1. Hoje e dois dias anteriores, em todas as UFs, SEM aguardar o historico.
    acumular(coletar_recentes(logger))
    proxima_verificacao = time.monotonic() + INTERVALO_ATUALIZACAO_RECENTES_MINUTOS * 60

    # 2. Um iterador por fonte, ordenado por data decrescente.
    # Heap garante que todas as edicoes mais recentes saiam antes das antigas,
    # mesmo quando um estado possui varios diarios/cadernos.
    filas = []
    contador = 0

    def avancar(iterator):
        nonlocal contador
        try:
            item = next(iterator)
        except StopIteration:
            return
        except Exception:
            logger.exception("Falha ao obter proxima edicao historica")
            totais[2] += 1
            return
        contador += 1
        heapq.heappush(
            filas, (-item.edition.publication_date.toordinal(), contador, item, iterator)
        )

    hoje = datetime.now().date()
    for uf, specs in STATE_SPECS:
        for spec in specs:
            iterator = _iter_collector_editions(
                spec, configurar_coletor(spec.collector_factory()), hoje, PULAR_ANOS_COMPLETOS
            )
            avancar(iterator)

    processadas = 0
    while filas:
        if (
            time.monotonic() >= proxima_verificacao
            or (
                processadas >= VERIFICAR_RECENTES_A_CADA_EDICOES
                and datetime.now().date() != hoje
            )
        ):
            acumular(coletar_recentes(logger))
            hoje = datetime.now().date()
            proxima_verificacao = (
                time.monotonic() + INTERVALO_ATUALIZACAO_RECENTES_MINUTOS * 60
            )
            processadas = 0
        _, _, item, iterator = heapq.heappop(filas)
        if uf_disponivel(item.state):
            acumular(processar_edicao(item, logger))
        # Avancar impede que uma UF com erro prenda as demais.
        # A edicao pulada sera verificada na proxima rodada.
        processadas += 1
        avancar(iterator)
    return tuple(totais)

def executar() -> int:
    logger = logger_configurado()
    logger.info("Download sem processamento iniciado. Para encerrar use Ctrl+C.")
    while True:
        erro_geral = False
        try:
            novos, existentes, falhas = coletar_rodada(logger)
            logger.info("Rodada concluida: novos=%s existentes=%s falhas=%s",
                        novos, existentes, falhas)
        except KeyboardInterrupt:
            logger.info("Interrompido pelo usuario")
            return 0
        except Exception:
            erro_geral = True
            logger.exception("Falha geral na rodada")
        if not EXECUTAR_CONTINUAMENTE:
            return 1 if erro_geral else 0
        espera = (INTERVALO_APOS_ERRO_MINUTOS * 60 if erro_geral
                  else INTERVALO_ENTRE_RODADAS_HORAS * 3600)
        logger.info("Proxima rodada apos %.1f minutos", espera / 60)
        try:
            time.sleep(espera)
        except KeyboardInterrupt:
            logger.info("Interrompido pelo usuario")
            return 0


if __name__ == "__main__":
    raise SystemExit(executar())
