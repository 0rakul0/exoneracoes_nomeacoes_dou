"""Converte a fila de PDFs em Markdown via Docling CPU e extrai atos, sem CLI args."""
from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path

from diarios_oficiais import config
# Deve ser aplicado ANTES de construir o conversor Docling.
config.DOCLING_DEVICE = "cpu"
config.ENABLE_OCR = True
config.PRELOAD_OCR_MODELS = False
config.DOCLING_NUM_THREADS = 6
config.ENABLE_SPACY_VALIDATION = False

from diarios_oficiais.base import BaseGazetteCollector, Edition
BaseGazetteCollector.enable_spacy_validation = False

from diarios_oficiais.fila_processamento import (
    falhar, finalizar, proxima, recuperar_interrompidos,
)
from diarios_oficiais.rodizio_estadual import STATE_SPECS, _parse_acts

INTERVALO_FILA_VAZIA_SEGUNDOS = 30
EXTRAIR_ATOS_CSV = True
THREADS_DOCLING_CPU = 6
config.DOCLING_NUM_THREADS = THREADS_DOCLING_CPU

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "conversao_diarios.log", encoding="utf-8"),
              logging.StreamHandler()],
)
logger = logging.getLogger("conversor_cpu")


def processar(item: dict, fontes: dict) -> None:
    chave = (item["uf"], item["codigo"])
    spec = fontes.get(chave)
    if spec is None:
        raise RuntimeError(f"Coletor nao cadastrado: {chave}")

    pdf = Path(item["arquivo"])
    if not pdf.is_file() or pdf.stat().st_size < 8:
        raise FileNotFoundError(f"PDF nao encontrado: {pdf}")
    with pdf.open("rb") as arq:
        if arq.read(5) != b"%PDF-":
            raise RuntimeError(f"Arquivo nao e PDF: {pdf}")

    coletor = spec.collector_factory()
    edicao = Edition(
        publication_date=date.fromisoformat(item["data_publicacao"]),
        section=item["caderno"],
        url=item["url"],
    )
    markdown = coletor.markdown_path_for(edicao)
    if not markdown.exists() or not markdown.stat().st_size:
        logger.info("Convertendo CPU | %s | %s", item["uf"], pdf)
        try:
            coletor.convert_pdf_to_markdown(pdf, markdown)
            if not markdown.is_file() or markdown.stat().st_size == 0:
                raise RuntimeError("Markdown ausente ou vazio apos conversao")
        except Exception:
            # Nao manter arquivos MD parcialmente escritos como concluidos.
            markdown.unlink(missing_ok=True)
            raise
    else:
        logger.info("Markdown existente | %s", markdown)

    if EXTRAIR_ATOS_CSV:
        atos = _parse_acts(spec.parser, coletor, edicao, markdown)
        novos = coletor.write_csv(coletor.yearly_csv_path_for(edicao.publication_date), atos)
        logger.info("Atos gravados: %s | %s", novos, markdown)
    finalizar(item["arquivo"])


def executar() -> None:
    fontes = {}
    for uf, specs in STATE_SPECS:
        for spec in specs:
            # Codigo derivado da classe: nao cria o coletor ate ser necessario.
            codigo = spec.collector_factory().gazette_code
            fontes[(uf, codigo)] = spec
    recuperados = recuperar_interrompidos()
    logger.info("Conversor CPU iniciado; tarefas recuperadas: %s", recuperados)
    while True:
        try:
            item = proxima()
            if item is None:
                time.sleep(INTERVALO_FILA_VAZIA_SEGUNDOS)
                continue
            try:
                processar(item, fontes)
            except Exception as exc:
                logger.exception("Falha ao converter %s", item["arquivo"])
                falhar(item["arquivo"], exc)
        except KeyboardInterrupt:
            logger.info("Conversor encerrado")
            return
        except Exception:
            logger.exception("Falha no worker; tentando novamente")
            time.sleep(INTERVALO_FILA_VAZIA_SEGUNDOS)


if __name__ == "__main__":
    executar()
