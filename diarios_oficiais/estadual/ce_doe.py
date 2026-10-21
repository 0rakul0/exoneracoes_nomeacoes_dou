from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.ce_power import CePowerCollector, collect_ce_power
from diarios_oficiais.estadual.rj_ioerj import parse_acts
from diarios_oficiais.utils_regex import ce_doe as ce_regexes


BASE_URL = "https://www.ce.gov.br/diario-oficial/"
AJAX_URL = "https://www.ce.gov.br/wp-admin/admin-ajax.php"
PORTAL_PATH = "/publications/search_portal"
OCRDOE_RE = re.compile(r"var OCRDOE = (\{.*?\});")


class CeDoeCollector(CePowerCollector):
    gazette_code = "DOECE"
    gazette_name = "Diario Oficial do Estado do Ceara"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._nonce: str | None = None
        self._editions_by_date: dict[date, list[Edition]] = {}

    def _get_nonce(self) -> str:
        if self._nonce:
            return self._nonce
        response = self.session.get(BASE_URL, timeout=self.http_timeout_seconds)
        response.raise_for_status()
        match = OCRDOE_RE.search(response.text)
        if not match:
            raise RuntimeError("Configuracao OCRDOE do portal do DOE/CE nao encontrada.")
        payload = json.loads(match.group(1))
        nonce = str(payload.get("nonce") or "")
        if not nonce:
            raise RuntimeError("Nonce do portal do DOE/CE nao encontrado.")
        self._nonce = nonce
        return nonce

    def _search_date(self, publication_date: date) -> list[Edition]:
        params = {
            "action": "ocrdoe_proxy",
            "nonce": self._get_nonce(),
            "path": PORTAL_PATH,
            "method": "GET",
            "page": "1",
            "order_by": "date",
            "order_dir": "desc",
            "per_page": "25",
            "start_date": publication_date.isoformat(),
            "end_date": publication_date.isoformat(),
        }
        response = self.session.get(AJAX_URL, params=params, timeout=self.http_timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        editions: list[Edition] = []
        for publication in payload.get("publications") or []:
            raw_date = str(publication.get("date") or publication.get("circulation_date") or "")[:10]
            if raw_date != publication_date.isoformat():
                continue
            for publication_file in publication.get("publication_files") or []:
                url = str(publication_file.get("download_url") or "").strip()
                if not url:
                    continue
                number = str(publication_file.get("journal_number") or publication_file.get("original_filename") or "")
                editions.append(
                    Edition(
                        publication_date=publication_date,
                        section=f"Diario Oficial CE Caderno {number}",
                        url=url,
                    )
                )
        return editions

    def list_editions(self, publication_date: date) -> list[Edition]:
        if publication_date not in self._editions_by_date:
            self._editions_by_date[publication_date] = self._search_date(publication_date)
        return self._editions_by_date[publication_date]

    def parse_acts_from_markdown_file(self, edition: Edition, markdown_path: Path) -> list:
        text = markdown_path.read_text(encoding="utf-8", errors="ignore")
        acts = parse_acts(text, self, edition, markdown_path, regexes=ce_regexes)
        return [
            act
            for act in acts
            if act.person_name.split(maxsplit=1)[0].upper() not in ce_regexes.FALSE_PERSON_STARTS
        ]

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # O endpoint de download da API exige autenticação direta. O portal
        # oficial disponibiliza o mesmo PDF pelo exportador público do seu
        # proxy WordPress, autenticado pelo nonce exposto na página.
        match = re.search(r"(\d+)$", edition.section)
        if not match:
            raise RuntimeError(f"Caderno do DOE/CE sem numero reconhecivel: {edition.section}")
        proxy_url = AJAX_URL + "?" + urlencode(
            {
                "action": "ocrdoe_proxy",
                "nonce": self._get_nonce(),
                "path": "/ocr_documents/export_pdf",
                "method": "GET",
                "date": edition.publication_date.isoformat(),
                "journal_number": match.group(1),
                "include_header": "false",
                "include_missing_report": "false",
                "filename": f"DOE-{edition.publication_date.isoformat()}-Caderno-{match.group(1)}.pdf",
            }
        )
        pdf_bytes = self.fetch_bytes(proxy_url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DOE/CE para PDF nao parece PDF: {edition.url}")
        destination.write_bytes(pdf_bytes)
        return destination


def collect_ce(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    return collect_ce_power(
        CeDoeCollector,
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
