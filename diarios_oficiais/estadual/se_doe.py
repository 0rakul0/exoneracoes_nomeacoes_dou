from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests

from diarios_oficiais import config
from diarios_oficiais.base import Edition
from diarios_oficiais.estadual._daily_pdf import DailyPdfCollector, collect_daily, parse_daily_acts
from diarios_oficiais.utils_regex import se_doe as regexes


BASE_URL = "https://iose.se.gov.br"


class SeDoeCollector(DailyPdfCollector):
    state = "SE"
    gazette_code = "DOESE"
    gazette_name = "Diario Oficial do Estado de Sergipe"
    start_date = date.fromisoformat(config.SE_START_DATE)

    def list_editions(self, publication_date: date) -> list[Edition]:
        url = f"{BASE_URL}/apifront/portal/edicoes/edicoes_from_data/{publication_date.isoformat()}.json"
        response = self.session.get(url, timeout=self.http_timeout_seconds)
        response.raise_for_status()
        editions = []
        for item in response.json().get("itens") or []:
            identifier = item.get("id")
            if not identifier:
                continue
            supplement = " Suplemento" if item.get("suplemento") else ""
            section = f"Diario Oficial SE{supplement}"
            editions.append(Edition(publication_date, section, f"{BASE_URL}/portal/edicoes/download/{identifier}"))
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        """Baixa PDF publico, sem salvar HTML de login/visualizacao como PDF.

        O catalogo pode listar edicoes cujo endpoint exige sessao ou permissao.
        Nesses casos, apresenta o status real e nao grava arquivo invalido.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        url = edition.url
        portal = f"{BASE_URL}/diario-oficial"
        self.session.headers.setdefault(
            "Accept", "application/pdf,application/octet-stream;q=0.9,*/*;q=0.5"
        )
        self.session.headers.setdefault("Referer", portal)

        def obter():
            resposta = self.session.get(
                url, timeout=self.http_timeout_seconds, allow_redirects=True
            )
            resposta.raise_for_status()
            return resposta

        resposta = obter()
        if resposta.content.lstrip().startswith(b"%PDF"):
            destination.write_bytes(resposta.content)
            return destination

        tipo = resposta.headers.get("Content-Type", "").lower()
        # Caso o portal dependa apenas de cookies de visitante, tenta uma
        # sessao publica comum uma unica vez. Nao tenta contornar login.
        if "html" in tipo or resposta.content.lstrip().startswith((b"<!DOCTYPE", b"<html")):
            try:
                self.session.get(portal, timeout=self.http_timeout_seconds)
                resposta = obter()
            except requests.RequestException as exc:
                raise RuntimeError(
                    f"IOSE/SE: resposta HTML no endpoint PDF e falha ao renovar "
                    f"sessao publica: {type(exc).__name__}: {exc}"
                ) from exc
            if resposta.content.lstrip().startswith(b"%PDF"):
                destination.write_bytes(resposta.content)
                return destination

        tipo = resposta.headers.get("Content-Type", "desconhecido")
        url_final = resposta.url
        dominio = urlparse(url_final).netloc
        raise RuntimeError(
            "IOSE/SE: edicao listada no catalogo, mas o endpoint nao entregou "
            f"um PDF. HTTP={resposta.status_code}; Content-Type={tipo}; "
            f"dominio_final={dominio}; url_final={url_final}; "
            f"edicao={edition.section}; data={edition.publication_date}. "
            "Pode ser visualizador HTML, acesso restrito ou alteracao do portal. "
            "Nao armazenamos HTML como PDF; coleta dos outros estados continua."
        )


def parse_acts_from_markdown_file(collector, edition, markdown_path):
    return parse_daily_acts(collector, edition, markdown_path, regexes)


def collect_se(**kwargs):
    return collect_daily(SeDoeCollector, regexes, "SE", **kwargs)
