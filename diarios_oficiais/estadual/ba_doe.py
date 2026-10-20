from __future__ import annotations

import html
import re
import sys
import time
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests
import urllib3

from diarios_oficiais import config
from diarios_oficiais.base import BaseGazetteCollector, Edition
from diarios_oficiais.estadual.rj_ioerj import edition_slug, parse_acts
from diarios_oficiais.utils_regex import ba_doe as ba_regexes


BASE_URL = "https://doe.ba.gov.br/"
EDITIONS_API_PATH = "apifront/portal/edicoes/edicoes_from_data/"
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")


class _SummaryParser(HTMLParser):
    """Lê o sumário HTML preservando o caderno e a hierarquia da matéria."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.li_stack: list[dict[str, str]] = []
        self.folder_node: dict[str, str] | None = None
        self.link: dict[str, str] | None = None
        self.links: list[tuple[str, str, list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.lower() == "li":
            self.li_stack.append({"folder": ""})
        elif tag.lower() == "span" and "folder" in (attributes.get("class") or "").split():
            self.folder_node = self.li_stack[-1] if self.li_stack else None
        elif tag.lower() == "a" and "linkMateria" in (attributes.get("class") or "").split():
            self.link = {
                "id": attributes.get("identificador") or attributes.get("data-materia-id") or "",
                "title": "",
            }

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "span":
            self.folder_node = None
        elif tag.lower() == "a" and self.link is not None:
            folders = [node["folder"].strip() for node in self.li_stack if node["folder"].strip()]
            if self.link["id"]:
                self.links.append((self.link["id"], self.link["title"].strip(), folders))
            self.link = None
        elif tag.lower() == "li" and self.li_stack:
            self.li_stack.pop()

    def handle_data(self, data: str) -> None:
        if self.folder_node is not None:
            self.folder_node["folder"] += data
        if self.link is not None:
            self.link["title"] += data


class _TextParser(HTMLParser):
    BLOCK_TAGS = {"br", "div", "p", "li", "tr", "td", "h1", "h2", "h3", "h4"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"style", "script", "noscript"}:
            self.skip_depth += 1
        elif self.skip_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"style", "script", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        elif self.skip_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0:
            self.parts.append(data)


def html_to_text(source: str) -> str:
    parser = _TextParser()
    parser.feed(source)
    text = html.unescape("".join(parser.parts))
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


class BaDoeCollector(BaseGazetteCollector):
    state = "BA"
    gazette_code = "DOBA"
    gazette_name = "Diario Oficial do Estado da Bahia"
    start_date = date.fromisoformat(config.BA_START_DATE)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # O portal oficial atualmente entrega uma cadeia incompleta para o
        # certificado TLS. A consulta continua restrita ao host oficial.
        self.session.verify = False
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def list_available_dates(
        self,
        start_date_override: date | None = None,
        end_date: date | None = None,
    ) -> list[date]:
        current = start_date_override or self.start_date
        last_date = end_date or date.today()
        dates: list[date] = []
        while current <= last_date:
            dates.append(current)
            current += timedelta(days=1)
        return dates

    def fetch_json(self, url: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(url, timeout=self.http_timeout_seconds)
                response.raise_for_status()
                payload = response.json()
                return {} if payload.get("erro") else payload
            except Exception as exc:
                last_error = exc
            if attempt < self.max_attempts:
                seconds = min(self.delay_seconds * attempt * 2, 30)
                print(f"Tentativa {attempt} falhou para {url}; tentando de novo em {seconds:.0f}s...", file=sys.stderr)
                time.sleep(seconds)
        raise RuntimeError(f"Falha ao consultar {url}: {last_error}") from last_error

    def list_editions(self, publication_date: date) -> list[Edition]:
        data = self.fetch_json(urljoin(BASE_URL, f"{EDITIONS_API_PATH}{publication_date.isoformat()}.json"))
        editions: list[Edition] = []
        counts: dict[str, int] = {}
        for item in data.get("itens") or []:
            edition_id = item.get("id")
            if not edition_id:
                continue
            number = str(item.get("numero") or edition_id)
            label = f"Diario Oficial do Estado da Bahia - Edicao {number}"
            if item.get("suplemento") not in (None, "", 0, "0", False):
                label += " - Suplemento"
            counts[label] = counts.get(label, 0) + 1
            if counts[label] > 1:
                label += f" - Edicao {counts[label]}"
            editions.append(
                Edition(
                    publication_date=publication_date,
                    section=label,
                    url=urljoin(BASE_URL, f"portal/visualizacoes/html/{edition_id}"),
                )
            )
        return editions

    def edition_id(self, edition: Edition) -> str:
        match = re.search(r"/(\d+)(?:/)?$", edition.url)
        if not match:
            raise RuntimeError(f"URL de edicao BA sem identificador: {edition.url}")
        return match.group(1)

    def load_or_create_markdown(self, edition: Edition, markdown_path: Path) -> str:
        if markdown_path.exists():
            return markdown_path.read_text(encoding="utf-8", errors="ignore")

        edition_id = self.edition_id(edition)
        summary = self.fetch_text(urljoin(BASE_URL, f"html/{edition_id}.html"))
        parser = _SummaryParser()
        parser.feed(summary)
        parts: list[str] = []
        for identifier, title, folders in parser.links:
            if not folders or folders[0].strip().upper() != "EXECUTIVO":
                continue
            content_url = urljoin(BASE_URL, f"apifront/portal/edicoes/publicacoes_ver_conteudo/{identifier}")
            try:
                content = html_to_text(self.fetch_text(content_url))
            except Exception as exc:
                print(f"Falha ao ler materia BA {identifier}: {exc}", file=sys.stderr)
                continue
            if not content:
                continue
            path_label = " / ".join(folders + ([title.strip()] if title.strip() else []))
            parts.append(f"## {path_label}\n\n{content}")

        if not parts:
            raise RuntimeError(f"Nenhuma materia do EXECUTIVO encontrada na edicao BA {edition_id}")
        markdown = self.clean_markdown_text("\n\n".join(parts))
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown, encoding="utf-8")
        return markdown

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        raise RuntimeError(
            "O PDF certificado do DOE/BA exige login; a coleta publica usa a versao HTML oficial da edicao."
        )

    def lake_base_path_for(self, edition: Edition) -> Path:
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y}" / f"{edition.publication_date:%m}" / stem

    def markdown_path_for(self, edition: Edition) -> Path:
        return self.lake_base_path_for(edition).with_suffix(".md")

    def latest_stored_publication_date(self) -> date | None:
        state_lake_dir = self.lake_dir / self.state
        latest: date | None = None
        if not state_lake_dir.exists():
            return None
        for path in state_lake_dir.rglob("*.md"):
            match = MARKDOWN_DATE_RE.search(path.stem)
            if match:
                current = date.fromisoformat(match.group(1))
                if latest is None or current > latest:
                    latest = current
        return latest


def parse_acts_from_markdown_file(collector: BaDoeCollector, edition: Edition, markdown_path: Path) -> list:
    text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    return parse_acts(text, collector, edition, markdown_path, regexes=ba_regexes)


def collect_ba(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    collector = BaDoeCollector()
    latest_stored_date = collector.latest_stored_publication_date()
    start_date = start_date_override or (collector.start_date if retroativo else latest_stored_date) or collector.start_date
    end_date = end_date or date.today()
    if end_date < start_date:
        raise ValueError("A data final da BA nao pode ser anterior a data inicial.")
    dates = collector.list_available_dates(start_date, end_date)
    if retroativo:
        dates.reverse()
        print(f"Coleta retroativa BA do presente para tras: {end_date.isoformat()} ate {start_date.isoformat()}.", file=sys.stderr)
    elif start_date_override is not None:
        print(f"Coleta BA: {start_date.isoformat()} a {end_date.isoformat()}.", file=sys.stderr)
    elif latest_stored_date is None:
        print(f"Nenhuma edicao BA encontrada no LAKE; iniciando em {start_date.isoformat()}.", file=sys.stderr)
    else:
        print(f"Ultima data BA no LAKE: {latest_stored_date.isoformat()}. Retomando a partir dessa data.", file=sys.stderr)

    total_new_acts = 0
    current_year = date.today().year
    active_year: int | None = None
    failed_years: set[int] = set()
    skipped_years: set[int] = set()

    def finalize_year(year: int | None) -> None:
        if year is None or year >= current_year or year in failed_years:
            return
        collector.mark_year_complete(year)

    for publication_date in dates:
        if pular_anos_completos and collector.is_year_complete(publication_date.year):
            if publication_date.year not in skipped_years:
                print(f"Pulando {publication_date.year}: marcador .year_complete encontrado.", file=sys.stderr)
                skipped_years.add(publication_date.year)
            continue
        if active_year is not None and publication_date.year != active_year:
            finalize_year(active_year)
        active_year = publication_date.year
        try:
            editions = collector.list_editions(publication_date)
        except Exception as exc:
            failed_years.add(publication_date.year)
            print(f"Falha ao listar edicoes BA de {publication_date.isoformat()}: {exc}", file=sys.stderr)
            continue
        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)
            csv_path = collector.yearly_csv_path_for(edition.publication_date)
            try:
                print(f"Processando BA {publication_date.isoformat()}...", file=sys.stderr)
                collector.load_or_create_markdown(edition, markdown_path)
                acts = parse_acts_from_markdown_file(collector, edition, markdown_path)
                total_new_acts += collector.write_csv(csv_path, acts)
            except Exception as exc:
                failed_years.add(publication_date.year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(f"Falha ao processar BA {publication_date.isoformat()} ({edition.section}); seguindo: {exc}", file=sys.stderr)
    finalize_year(active_year)
    return total_new_acts
