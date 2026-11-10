"""Executa a coleta estadual retroativa continuamente, sem argumentos CLI.

Execute com: python coletar_continuamente.py
Para configurar, edite as constantes abaixo.
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from diarios_oficiais.rodizio_estadual import collect_estaduais_em_rodizio

# Configuracoes editaveis, sem argparse.
INTERVALO_ENTRE_RODADAS_HORAS = 6
INTERVALO_APOS_ERRO_MINUTOS = 15
PULAR_ANOS_COMPLETOS = True
EXECUTAR_CONTINUAMENTE = True

RAIZ = Path(__file__).resolve().parent
PASTA_LOGS = RAIZ / "logs"
PASTA_LOGS.mkdir(parents=True, exist_ok=True)


def configurar_logs() -> logging.Logger:
    logger = logging.getLogger("coleta_continua")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    formato = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    arquivo = logging.FileHandler(
        PASTA_LOGS / "coleta_continua.log", encoding="utf-8"
    )
    terminal = logging.StreamHandler(sys.stdout)
    for handler in (arquivo, terminal):
        handler.setFormatter(formato)
        logger.addHandler(handler)
    logger.propagate = False
    return logger


def executar() -> int:
    logger = configurar_logs()
    logger.info("Coleta iniciada; para encerrar, pressione Ctrl+C.")
    while True:
        inicio = datetime.now()
        houve_erro = False
        try:
            logger.info("Iniciando rodizio retroativo das 27 UFs.")
            total = collect_estaduais_em_rodizio(
                skip_complete_years=PULAR_ANOS_COMPLETOS,
            )
            logger.info(
                "Rodada concluida | inicio=%s | atos_novos=%s",
                inicio.isoformat(timespec="seconds"),
                total,
            )
        except KeyboardInterrupt:
            logger.info("Coleta interrompida pelo usuario.")
            return 0
        except Exception:
            houve_erro = True
            logger.exception("Falha geral na rodada; nova tentativa programada.")

        if not EXECUTAR_CONTINUAMENTE:
            return 1 if houve_erro else 0

        espera = (
            INTERVALO_APOS_ERRO_MINUTOS * 60
            if houve_erro
            else INTERVALO_ENTRE_RODADAS_HORAS * 3600
        )
        logger.info("Proxima rodada em %.1f minutos.", espera / 60)
        try:
            time.sleep(espera)
        except KeyboardInterrupt:
            logger.info("Coleta interrompida pelo usuario.")
            return 0


if __name__ == "__main__":
    raise SystemExit(executar())
