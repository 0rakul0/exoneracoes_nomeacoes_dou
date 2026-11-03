from __future__ import annotations

import base64
import html
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

from diarios_oficiais.base import Act
from diarios_oficiais.base import BaseGazetteCollector
from diarios_oficiais.base import Edition
from diarios_oficiais.config import RJ_COLLECTION_YEAR
from diarios_oficiais.config import TORCH_CUDA_RUNTIME
from diarios_oficiais.governadores import (
    governador_da_edicao,
    nome_representante_governo,
    origem_representante_governo,
)
from diarios_oficiais.utils_regex.common import SPACE_RE
from diarios_oficiais.utils_regex.common import TAG_RE
from diarios_oficiais.utils_regex import rj_ioerj as rj_regexes


BASE_URL = "https://www.ioerj.com.br/portal/modules/conteudoonline/"
CALENDAR_URL = urljoin(BASE_URL, "do_seleciona_data.php")
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")


class RjIoerjCollector(BaseGazetteCollector):
    state = "RJ"
    gazette_code = "DOERJ"
    gazette_name = "Diario Oficial do Estado do Rio de Janeiro"
    section_filter = "Poder Executivo"
    base_url = BASE_URL
    calendar_url = CALENDAR_URL

    def fetch_url_candidates(self, url: str) -> list[str]:
        candidates = [url]
        if url.startswith("https://www.ioerj.com.br/"):
            candidates.append(url.replace("https://", "http://", 1))
        return candidates

    def list_available_dates(self) -> list[date]:
        page = self.fetch_text(self.calendar_url)
        dates: set[date] = set()
        for encoded in rj_regexes.DATE_LINK_RE.findall(page):
            decoded = base64.b64decode(encoded).decode("ascii")
            dates.add(datetime.strptime(decoded, "%Y%m%d").date())
        return sorted(dates)

    def list_editions(self, publication_date: date) -> list[Edition]:
        encoded = base64.b64encode(publication_date.strftime("%Y%m%d").encode("ascii")).decode("ascii")
        url = urljoin(self.base_url, f"do_seleciona_edicao.php?data={encoded}")
        page = self.fetch_text(url)
        raw_editions: list[tuple[str, str]] = []
        for match in rj_regexes.EDITION_LINK_RE.finditer(page):
            label = clean_html(match.group("label"))
            raw_editions.append((label, urljoin(self.base_url, html.unescape(match.group("href")))))

        editions: list[Edition] = []
        label_counts: dict[str, int] = {}
        total_by_label: dict[str, int] = {}
        for label, _ in raw_editions:
            total_by_label[label] = total_by_label.get(label, 0) + 1

        for label, edition_url in raw_editions:
            label_counts[label] = label_counts.get(label, 0) + 1
            edition_label = disambiguate_edition_label(
                label,
                label_counts[label],
                total_by_label[label],
            )
            editions.append(
                Edition(
                    publication_date=publication_date,
                    section=edition_label,
                    url=edition_url,
                )
            )
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        page = self.fetch_text(edition.url)
        key_match = rj_regexes.PDF_KEY_RE.search(page)
        if not key_match:
            raise RuntimeError(f"Nao encontrei chave do PDF na pagina: {edition.url}")
        key = key_match.group("key")
        pdf_url = urljoin(self.base_url, f"mostra_edicao.php?k={key[:12]}P{key[12:]}")
        time.sleep(self.delay_seconds)
        pdf_bytes = self.fetch_bytes(pdf_url)
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"Resposta da IOERJ para PDF nao parece PDF: {pdf_url}")
        eof_index = pdf_bytes.rfind(b"%%EOF")
        if eof_index != -1:
            pdf_bytes = pdf_bytes[: eof_index + len(b"%%EOF") + 1]
        destination.write_bytes(pdf_bytes)
        return destination

    def lake_base_path_for(self, edition: Edition) -> Path:
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y}" / f"{edition.publication_date:%m}" / stem

    def markdown_path_for(self, edition: Edition) -> Path:
        return self.lake_base_path_for(edition).with_suffix(".md")

    def latest_stored_publication_date(self) -> date | None:
        state_lake_dir = self.lake_dir / self.state
        latest_date: date | None = None
        for markdown_path in state_lake_dir.rglob("*.md"):
            match = MARKDOWN_DATE_RE.search(markdown_path.stem)
            if not match:
                continue
            publication_date = date.fromisoformat(match.group(1))
            if latest_date is None or publication_date > latest_date:
                latest_date = publication_date
        return latest_date


def clean_html(value: str) -> str:
    value = TAG_RE.sub(" ", value)
    value = html.unescape(value)
    return SPACE_RE.sub(" ", value).strip()


def disambiguate_edition_label(label: str, occurrence: int, total_occurrences: int) -> str:
    if total_occurrences <= 1 or occurrence <= 1:
        return label
    if re.search(r"\b(?:complementar|suplemento|extra)\b", label, flags=re.I):
        return f"{label} {occurrence}"
    return f"{label} - Edicao {occurrence}"




# Historical public helper names remain importable from the RJ collector.
from diarios_oficiais.extracao.parser import (
    parse_acts,
    representative_for_act,
    clean_representative_name,
    authority_context_markers,
    contextual_signer,
    contextual_signer_name,
    contextual_signer_role,
    secretary_agency_from_phrase,
    secretary_agency_for_marker,
    clean_secretary_agency,
    secretary_name_from_front_page,
    plausible_secretary_name,
    title_case_name,
    title_case_agency,
    extract_functional_id,
    extract_signer,
    parse_acts_from_markdown_file,
    extract_person_name,
    extract_person_names,
    direct_person_name,
    normalize_name,
    valid_person_name,
    clean_piece,
    edition_slug,
)

def collect_rj(pular_anos_completos: bool = True, retroativo: bool = False) -> int:
    collector = RjIoerjCollector()
    latest_stored_date = collector.latest_stored_publication_date()
    if retroativo:
        start_date = date.today()
        end_date = date(RJ_COLLECTION_YEAR, 1, 1)
    else:
        start_date = latest_stored_date or date(RJ_COLLECTION_YEAR, 1, 1)
        end_date = date.today()
    if retroativo:
        print(
            f"Coleta retroativa RJ do presente para tras: {end_date.isoformat()} ate {start_date.isoformat()}.",
            file=sys.stderr,
        )
    elif latest_stored_date is None:
        print(
            f"Nenhuma edicao RJ encontrada no LAKE; iniciando em {start_date.isoformat()}.",
            file=sys.stderr,
        )
    else:
        print(
            f"Ultima edicao RJ encontrada no LAKE: {latest_stored_date.isoformat()}. "
            "Retomando a partir dessa data.",
            file=sys.stderr,
        )
    dates = sorted(
        publication_date
        for publication_date in collector.list_available_dates()
        if end_date <= publication_date <= start_date
        and (not retroativo or publication_date.weekday() < 5)
    )
    if retroativo:
        dates.reverse()

    total_new_acts = 0
    current_year = date.today().year
    active_year: int | None = None
    failed_years: set[int] = set()
    skipped_years: set[int] = set()

    def finalize_year(year: int | None) -> None:
        if year is None or year >= current_year:
            return
        if year in failed_years:
            print(f"Nao marquei {year} como completo porque houve falhas de coleta.", file=sys.stderr)
            return
        collector.mark_year_complete(year)

    for item in dates:
        if pular_anos_completos and collector.is_year_complete(item.year):
            if item.year not in skipped_years:
                print(f"Pulando {item.year}: marcador .year_complete encontrado.", file=sys.stderr)
                skipped_years.add(item.year)
            continue

        if active_year is not None and item.year != active_year:
            finalize_year(active_year)
        active_year = item.year

        try:
            editions = collector.list_editions(item)
        except Exception as exc:
            failed_years.add(item.year)
            print(f"Falha ao listar edicoes de {item.isoformat()}: {exc}", file=sys.stderr)
            continue

        if not editions:
            continue

        print(f"Processando {item.isoformat()}...", file=sys.stderr)
        for edition in editions:
            markdown_path = collector.markdown_path_for(edition)
            csv_path = collector.yearly_csv_path_for(edition.publication_date)
            try:
                collector.load_or_create_markdown(edition, markdown_path)
                acts = parse_acts_from_markdown_file(collector, edition, markdown_path)
                total_new_acts += collector.write_csv(csv_path, acts)
            except Exception as exc:
                failed_years.add(item.year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(
                    f"Falha ao processar {item.isoformat()} ({edition.section}); seguindo para a proxima edicao: {exc}",
                    file=sys.stderr,
                )
                continue

    finalize_year(active_year)
    return total_new_acts


def main() -> int:
    report_torch_cuda()
    total = collect_rj()
    print(f"{total} atos novos gravados nos CSVs anuais")
    return 0


def report_torch_cuda() -> None:
    try:
        import torch
    except ImportError:
        print("PyTorch nao instalado; instale requirements-cuda.txt antes de requirements.txt.", file=sys.stderr)
        return

    cuda_available = torch.cuda.is_available()
    cuda_version = torch.version.cuda or "indisponivel"
    device_name = torch.cuda.get_device_name(0) if cuda_available else "nenhuma GPU CUDA disponivel"
    print(
        f"PyTorch {torch.__version__}; CUDA runtime: {cuda_version}; "
        f"cuda_available={cuda_available}; device={device_name}; expected_runtime={TORCH_CUDA_RUNTIME}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
