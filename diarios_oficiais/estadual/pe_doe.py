from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

from diarios_oficiais import config
from diarios_oficiais.base import BaseGazetteCollector, Edition
from diarios_oficiais.estadual.rj_ioerj import edition_slug, parse_acts
from diarios_oficiais.utils_regex import pe_doe as regexes


BASE_URL = "https://diariooficial.cepe.com.br/diariooficial"
S3_ENDPOINT = "https://cepebr-prod.s3.sa-east-1.amazonaws.com"
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")


class PeDoeCollector(BaseGazetteCollector):
    state = "PE"
    gazette_code = "DOEPE"
    gazette_name = "Diario Oficial do Estado de Pernambuco"
    start_date = date.fromisoformat(config.PE_START_DATE)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # O CloudFront do portal rejeita o User-Agent identificador do projeto.
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://diariooficial.cepe.com.br/diariooficialweb/",
            }
        )
        self._metadata_cache: dict[tuple[str, date], dict | None] = {}

    def list_available_dates(self, start_date_override=None, end_date=None):
        current, last = start_date_override or self.start_date, end_date or date.today()
        return [current + timedelta(days=offset) for offset in range((last - current).days + 1)]

    def _metadata(self, endpoint: str, query_date: date) -> dict | None:
        key = (endpoint, query_date)
        if key in self._metadata_cache:
            return self._metadata_cache[key]
        url = f"{BASE_URL}/public/visualizar-jornal/{endpoint}"
        response = self.session.get(
            url,
            params={"codigoDiario": 1, "dataPublicacao": query_date.strftime("%d-%m-%Y")},
            timeout=self.http_timeout_seconds,
        )
        if response.status_code == 400:
            result = None
        else:
            response.raise_for_status()
            result = response.json() if response.content else None
        self._metadata_cache[key] = result
        return result

    def _s3_url(self, query_date: date, extra: bool) -> str:
        # O portal constrói o mesmo caminho no navegador para a versão impressa.
        stem = query_date.strftime("%d-%m-%Y") + ("E" if extra else "")
        return f"{S3_ENDPOINT}/1/arquivos/resumoDiario/{query_date:%d-%m-%Y}/{stem}.pdf"

    @staticmethod
    def _metadata_date(metadata: dict | None) -> date | None:
        if not metadata:
            return None
        raw_date = str(metadata.get("date") or "")[:10]
        try:
            return date.fromisoformat(raw_date)
        except ValueError:
            return None

    def list_editions(self, publication_date: date) -> list[Edition]:
        editions: list[Edition] = []
        # O endpoint de edição normal responde o fechamento do dia anterior;
        # por isso consultamos o dia seguinte para obter a data solicitada.
        main_query_date = publication_date + timedelta(days=1)
        metadata = self._metadata("buscarJornal", main_query_date)
        if self._metadata_date(metadata) == publication_date:
            editions.append(Edition(publication_date, "Diario Oficial PE", self._s3_url(main_query_date, False)))

        extra_metadata = self._metadata("buscarJornalExtra", publication_date)
        if self._metadata_date(extra_metadata) == publication_date:
            editions.append(Edition(publication_date, "Diario Oficial PE Extra", self._s3_url(publication_date, True)))
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = self.fetch_bytes(edition.url)
        if not content.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta do DOE/PE não parece PDF: {edition.url}")
        destination.write_bytes(content)
        return destination

    def lake_base_path_for(self, edition):
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y/%m}" / stem

    def markdown_path_for(self, edition):
        return self.lake_base_path_for(edition).with_suffix(".md")

    def latest_stored_publication_date(self):
        dates = [
            date.fromisoformat(match.group(1))
            for path in (self.lake_dir / self.state).rglob("DOEPE_*.md")
            if (match := MARKDOWN_DATE_RE.search(path.stem))
        ]
        return max(dates, default=None)


def parse_acts_from_markdown_file(collector, edition, markdown_path):
    return parse_acts(markdown_path.read_text(encoding="utf-8", errors="ignore"), collector, edition, markdown_path, regexes=regexes)


def collect_pe(pular_anos_completos=True, start_date_override=None, end_date=None, retroativo=False):
    collector = PeDoeCollector()
    latest = collector.latest_stored_publication_date()
    first = start_date_override or (collector.start_date if retroativo else latest) or collector.start_date
    last = end_date or date.today()
    if last < first:
        raise ValueError("A data final de PE não pode ser anterior à data inicial.")
    dates = collector.list_available_dates(first, last)
    if retroativo:
        dates.reverse()
    total, failed_years = 0, set()
    for publication_date in dates:
        year = publication_date.year
        if pular_anos_completos and collector.is_year_complete(year):
            continue
        try:
            editions = collector.list_editions(publication_date)
        except Exception as exc:
            failed_years.add(year)
            print(f"Falha ao listar edições PE de {publication_date}: {exc}", file=sys.stderr)
            continue
        for edition in editions:
            try:
                path = collector.markdown_path_for(edition)
                collector.load_or_create_markdown(edition, path)
                total += collector.write_csv(collector.yearly_csv_path_for(publication_date), parse_acts_from_markdown_file(collector, edition, path))
            except Exception as exc:
                failed_years.add(year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(f"Falha ao processar PE {publication_date} ({edition.section}): {exc}", file=sys.stderr)
    for year in {item.year for item in dates} - failed_years:
        if year < date.today().year and first <= date(year, 1, 1) and last >= date(year, 12, 31):
            collector.mark_year_complete(year)
    return total
