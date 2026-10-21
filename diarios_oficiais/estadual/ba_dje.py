from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.ba_power import BaPowerCollector, collect_ba_power


BASE_URL = "https://diario.tjba.jus.br/diario/internet/"
SEARCH_PATH = "pesquisar.wsp"
ARCHIVE_PATH = "arquivo.wsp"
DOWNLOAD_PATH = "download.wsp"
EDITION_RE = re.compile(r"ver\(\s*['\"](\d+)['\"]\s*\)")
CADERNO_RE = re.compile(r"abrirCaderno\(\s*(\d+)\s*\)")


class BaDjeCollector(BaPowerCollector):
    state = "BA"
    gazette_code = "DJEBA"
    gazette_name = "Diario da Justica Eletronico da Bahia"

    def _decode_page(self, content: bytes) -> str:
        return content.decode("cp1252", errors="replace")

    def _get_page(self, url: str) -> str:
        response = self.session.get(url, timeout=self.http_timeout_seconds)
        response.raise_for_status()
        return self._decode_page(response.content)

    def _search_editions(self, publication_date: date) -> list[str]:
        search_url = urljoin(BASE_URL, SEARCH_PATH)
        initial = self._get_page(search_url)
        soup = BeautifulSoup(initial, "html.parser")
        form = soup.find("form")
        if form is None:
            raise RuntimeError("Formulario de pesquisa do DJE/BA nao encontrado.")
        payload: dict[str, str] = {}
        for element in form.find_all(["input", "select"]):
            name = element.get("name")
            if not name:
                continue
            if element.name == "select":
                payload[name] = ""
            elif element.get("type") not in {"submit", "button"}:
                payload[name] = str(element.get("value") or "")
        payload.update(
            {
                "tmp.diario.dt_inicio": publication_date.strftime("%d/%m/%Y"),
                "tmp.diario.dt_fim": publication_date.strftime("%d/%m/%Y"),
                "tmp.bntEnviar": "Enviar",
            }
        )
        response = self.session.post(search_url, data=payload, timeout=self.http_timeout_seconds)
        response.raise_for_status()
        result = BeautifulSoup(self._decode_page(response.content), "html.parser")
        edition_ids: list[str] = []
        for anchor in result.find_all("a", onclick=True):
            match = EDITION_RE.search(str(anchor.get("onclick") or ""))
            if match and match.group(1) not in edition_ids:
                edition_ids.append(match.group(1))
        return edition_ids

    def _list_cadernos(self, edition_id: str) -> list[tuple[str, str]]:
        archive_url = urljoin(BASE_URL, ARCHIVE_PATH) + "?" + urlencode({"tmp.diario.nu_edicao": edition_id})
        soup = BeautifulSoup(self._get_page(archive_url), "html.parser")
        cadernos: list[tuple[str, str]] = []
        for anchor in soup.find_all("a", href=True):
            match = CADERNO_RE.search(str(anchor.get("href") or ""))
            if not match:
                continue
            number = match.group(1)
            label = " ".join(anchor.get_text(" ", strip=True).split())
            cadernos.append((number, label or f"Caderno {number}"))
        return cadernos

    def list_editions(self, publication_date: date) -> list[Edition]:
        editions: list[Edition] = []
        for edition_id in self._search_editions(publication_date):
            for caderno_number, caderno_label in self._list_cadernos(edition_id):
                query = urlencode(
                    {
                        "tmp.diario.nu_edicao": edition_id,
                        "tmp.caderno": caderno_number,
                    }
                )
                editions.append(
                    Edition(
                        publication_date=publication_date,
                        section=f"DJE BA {edition_id} - {caderno_label}",
                        url=urljoin(BASE_URL, ARCHIVE_PATH) + "?" + query,
                    )
                )
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        parsed = parse_qs(urlparse(edition.url).query)
        edition_id = (parsed.get("tmp.diario.nu_edicao") or [""])[0]
        caderno_number = (parsed.get("tmp.caderno") or [""])[0]
        if not edition_id or not caderno_number:
            raise RuntimeError(f"URL de caderno DJE/BA invalida: {edition.url}")

        archive_html = self._get_page(edition.url)
        soup = BeautifulSoup(archive_html, "html.parser")
        form = soup.find("form")
        if form is None:
            raise RuntimeError(f"Formulario de download do DJE/BA nao encontrado: {edition.url}")
        payload: dict[str, str] = {}
        for element in form.find_all("input"):
            name = element.get("name")
            if name:
                payload[name] = str(element.get("value") or "")
        payload["tmp.diario.nu_edicao"] = edition_id
        payload["tmp.caderno"] = caderno_number
        response = self.session.post(urljoin(BASE_URL, DOWNLOAD_PATH), data=payload, timeout=self.http_timeout_seconds)
        response.raise_for_status()
        if not response.content.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DJE/BA para PDF nao parece PDF: {edition.url}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return destination


def collect_ba_dje(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    return collect_ba_power(
        BaDjeCollector,
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
