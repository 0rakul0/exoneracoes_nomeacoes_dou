"""Download continuo dos diarios oficiais, sem GPU, Docling, OCR ou argparse.

Execute: python baixar_diarios_windows.py
Edite as constantes abaixo para ajustar o comportamento.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Evita inicializar validacao spaCy nos coletores somente para download.
from diarios_oficiais.base import BaseGazetteCollector
BaseGazetteCollector.enable_spacy_validation = False

from diarios_oficiais.rodizio_estadual import STATE_SPECS, _iter_state_editions

INTERVALO_ENTRE_RODADAS_HORAS = 6
INTERVALO_APOS_ERRO_MINUTOS = 15
EXECUTAR_CONTINUAMENTE = True
PULAR_ANOS_COMPLETOS = False  # PDF pode faltar mesmo quando o Markdown do ano ja esta completo.
BAIXAR_HTML_BA = True         # DOE/BA publico oferece HTML, nao PDF sem autenticacao.
VALIDAR_PDF_EXISTENTE = True

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


def pdf_valido(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 8:
        return False
    with path.open("rb") as arquivo:
        return arquivo.read(5) == b"%PDF-"


def coletar_rodada(logger: logging.Logger) -> tuple[int, int, int]:
    baixados = existentes = falhas = 0
    hoje = datetime.now().date()
    # Mesmo rodizio do projeto: alterna fontes dentro de cada UF e UFs entre si.
    filas = [(uf, _iter_state_editions(uf, specs, hoje, PULAR_ANOS_COMPLETOS))
             for uf, specs in STATE_SPECS]
    while filas:
        proximas = []
        for uf, iterator in filas:
            try:
                item = next(iterator)
            except StopIteration:
                continue
            except Exception:
                logger.exception("Falha ao percorrer lista de %s", uf)
                falhas += 1
                continue

            coletor, edicao = item.collector, item.edition
            markdown = coletor.markdown_path_for(edicao)
            # Salva o PDF oficial ao lado do futuro Markdown, de forma persistente.
            destino = markdown.with_suffix(".pdf")
            try:
                if uf == "BA" and coletor.gazette_code == "DOBA":
                    if BAIXAR_HTML_BA:
                        if markdown.is_file() and markdown.stat().st_size > 0:
                            existentes += 1
                        else:
                            coletor.load_or_create_markdown(edicao, markdown)
                            baixados += 1
                        logger.info("BA HTML | %s | %s", edicao.publication_date, markdown)
                    else:
                        logger.info("BA HTML ignorado: %s", edicao.publication_date)
                elif destino.exists() and (not VALIDAR_PDF_EXISTENTE or pdf_valido(destino)):
                    existentes += 1
                else:
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    temporario = destino.with_name(destino.name + ".part")
                    try:
                        if temporario.exists():
                            temporario.unlink()
                        resultado = coletor.download_edition_pdf(edicao, temporario)
                        if resultado is not None and Path(resultado) != temporario:
                            raise RuntimeError("Coletor retornou arquivo diferente do destino temporario")
                        if not pdf_valido(temporario):
                            raise RuntimeError("Arquivo recebido nao possui cabecalho PDF valido")
                        os.replace(temporario, destino)
                        baixados += 1
                        logger.info("BAIXADO | %s | %s | %s", uf, edicao.publication_date, destino)
                    finally:
                        temporario.unlink(missing_ok=True)
            except Exception as exc:
                falhas += 1
                logger.exception("FALHA | %s | %s | %s", uf, edicao.publication_date, edicao.section)
                try:
                    coletor.record_collection_failure(edicao, "download_pdf", exc)
                except Exception:
                    logger.exception("Falha ao registrar erro de %s", uf)
            proximas.append((uf, iterator))
        filas = proximas
    return baixados, existentes, falhas


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
