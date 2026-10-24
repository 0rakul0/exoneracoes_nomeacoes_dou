from __future__ import annotations

import base64
import binascii
import re
import ssl
import sys
import time
import unicodedata
from collections import Counter
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter

from diarios_oficiais import config
from diarios_oficiais.base import Act, BaseGazetteCollector, Edition
from diarios_oficiais.estadual.rj_ioerj import clean_piece, edition_slug, normalize_name, valid_person_name
from diarios_oficiais.governadores import (
    governador_da_edicao,
    nome_representante_governo,
    origem_representante_governo,
)
from diarios_oficiais.utils_regex import mg_doe as mg_regexes
from diarios_oficiais.utils_regex.common import SPACE_RE


BASE_URL = "https://www.jornalminasgerais.mg.gov.br/"
API_URL = BASE_URL + "api/v1/"
MARKDOWN_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")
INTERMEDIATE_CERTIFICATE = (
    Path(__file__).resolve().parents[1] / "certificates"
    / "sectigo_public_server_authentication_ca_dv_r36.pem"
)


class MgTLSAdapter(HTTPAdapter):
    """Completa a cadeia enviada incorretamente pelo portal, mantendo TLS."""

    def __init__(self) -> None:
        self.ssl_context = ssl.create_default_context(cafile=requests.certs.where())
        self.ssl_context.load_verify_locations(cafile=str(INTERMEDIATE_CERTIFICATE))
        super().__init__()

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self.ssl_context
        return super().init_poolmanager(*args, **kwargs)

    def build_connection_pool_key_attributes(self, request, verify, cert=None):
        # Requests >= 2.32 também define o contexto por requisição.
        host, options = super().build_connection_pool_key_attributes(request, verify, cert)
        if verify is True:
            options["ssl_context"] = self.ssl_context
        return host, options


def without_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value) if not unicodedata.combining(c))


def decode_pdf(encoded: str) -> bytes:
    """Extrai o PDF contíguo entregue pela API em base64, puro ou em CMS.

    A extração remove o envelope PKCS#7; não verifica a assinatura digital.
    """
    try:
        content = base64.b64decode("".join(encoded.split()), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("Arquivo do DOE/MG com base64 invalido.") from exc
    start = content.find(b"%PDF-")
    end = content.rfind(b"%%EOF")
    if start < 0 or end < start:
        raise RuntimeError("Arquivo do DOE/MG nao contem um PDF completo.")
    return content[start:end + len(b"%%EOF")] + b"\n"


class MgDoeCollector(BaseGazetteCollector):
    state = "MG"
    gazette_code = "DOEMG"
    gazette_name = "Diario Oficial do Estado de Minas Gerais"
    section_filter = "Diário do Executivo"
    base_url = BASE_URL
    start_date = date.fromisoformat(config.MG_START_DATE)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.session.mount(BASE_URL, MgTLSAdapter())
        # Apenas o arquivo principal do dia corrente é mantido em memória.
        self._primary_files: dict[str, dict] = {}

    @staticmethod
    def _response_data(response: requests.Response):
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "dados" not in payload:
            raise RuntimeError("Resposta inesperada da API do DOE/MG.")
        if payload.get("erros"):
            raise RuntimeError(f"API do DOE/MG: {payload['erros']}")
        return payload["dados"]

    def _authenticate(self) -> None:
        # Mesmo acesso anônimo usado pelo frontend; não exige conta ou senha.
        response = self.session.post(
            API_URL + "Autenticacao/Autenticar", json={}, timeout=self.http_timeout_seconds,
        )
        token = self._response_data(response)
        if not isinstance(token, str) or not token:
            raise RuntimeError("Token publico do DOE/MG nao encontrado.")
        self.session.headers["Authorization"] = f"Bearer {token}"

    def fetch_json(self, url: str):
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                time.sleep(self.delay_seconds)
                response = self.session.get(url, timeout=self.http_timeout_seconds)
                if response.status_code == 401:
                    self._authenticate()
                    response = self.session.get(url, timeout=self.http_timeout_seconds)
                return self._response_data(response)
            except requests.exceptions.SSLError as exc:
                # Repetir a mesma conexão não corrige uma cadeia inválida.
                raise RuntimeError(
                    "Falha de certificado HTTPS no DOE/MG. Verifique a data/hora "
                    "do sistema e a cadeia de certificados do portal. " + str(exc)
                ) from exc
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                last_error = exc
            if attempt < self.max_attempts:
                print(f"Falha na API DOE/MG; nova tentativa {attempt + 1}: {url}", file=sys.stderr)
                time.sleep(min(self.delay_seconds * attempt * 2, 30))
        raise RuntimeError(f"Falha ao consultar {url}: {last_error}") from last_error

    def list_available_dates(
        self, start_date_override: date | None = None, end_date: date | None = None,
    ) -> list[date]:
        first = start_date_override or self.start_date
        last = end_date or date.today()
        month = first.replace(day=1)
        dates: set[date] = set()
        while month <= last:
            url = API_URL + "Jornal/ListarEdicoesParaCalendario?" + urlencode({
                "MesPublicacao": month.month, "AnoPublicacao": month.year,
            })
            items = self.fetch_json(url)
            if not isinstance(items, list):
                raise RuntimeError(f"Calendario do DOE/MG invalido para {month:%Y-%m}.")
            for item in items:
                publication_date = date.fromisoformat(item["dataPublicacao"][:10])
                if first <= publication_date <= last:
                    dates.add(publication_date)
            month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
        return sorted(dates)

    def list_editions(self, publication_date: date) -> list[Edition]:
        self._primary_files.clear()
        data = self.fetch_json(API_URL + "Jornal/ObterEdicaoPorDataPublicacao?" + urlencode({
            "dataPublicacao": publication_date.isoformat(),
        }))
        if data is None:
            return []
        if not isinstance(data, dict) or data.get("dataPublicacao", "")[:10] != publication_date.isoformat():
            raise RuntimeError(f"Edicao do DOE/MG com data inesperada: {publication_date}.")
        cadernos = data.get("cadernos")
        if not isinstance(cadernos, list):
            raise RuntimeError("Lista de cadernos do DOE/MG ausente.")
        selected = []
        for item in cadernos:
            label = str(item.get("descricao") or "").strip()
            normalized = without_accents(label).casefold()
            if "executivo" in normalized or normalized.startswith("edicao extra"):
                if not item.get("id"):
                    raise RuntimeError(f"Caderno do DOE/MG sem identificador: {label}.")
                selected.append((str(item["id"]), label))
        counts = Counter(label for _, label in selected)
        editions: list[Edition] = []
        seen: set[str] = set()
        for identifier, label in selected:
            if identifier in seen:
                continue
            seen.add(identifier)
            url = API_URL + "Caderno/ObterArquivoCadernoPorId?" + urlencode({"id": identifier})
            if cadernos and str(cadernos[0].get("id")) == identifier and data.get("arquivoCadernoPrincipal"):
                self._primary_files[url] = data["arquivoCadernoPrincipal"]
            section = f"{label} - Caderno {identifier}" if counts[label] > 1 else label
            editions.append(Edition(publication_date, section, url))
        return editions

    def download_edition_pdf(self, edition: Edition, destination: Path) -> Path:
        data = self._primary_files.pop(edition.url, None)
        if data is None:
            data = self.fetch_json(edition.url)
        if not isinstance(data, dict) or not data.get("arquivo"):
            raise RuntimeError(f"Arquivo do DOE/MG ausente: {edition.url}")
        pdf = decode_pdf(data["arquivo"])
        if data.get("arquivoUnico") is not True:
            from pypdf import PdfWriter

            total_pages = int(data.get("totalPaginas") or 0)
            if total_pages < 1:
                raise RuntimeError(f"Quantidade de paginas do DOE/MG invalida: {edition.url}")
            writer = PdfWriter()
            for page in range(1, total_pages + 1):
                if page == data.get("pagina"):
                    page_pdf = pdf
                else:
                    page_data = self.fetch_json(edition.url + f"&pagina={page}")
                    if not isinstance(page_data, dict) or page_data.get("pagina") != page:
                        raise RuntimeError(f"Pagina {page} do DOE/MG ausente: {edition.url}")
                    page_pdf = decode_pdf(page_data.get("arquivo") or "")
                writer.append(BytesIO(page_pdf))
            output = BytesIO()
            writer.write(output)
            pdf = output.getvalue()
            writer.close()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(pdf)
        return destination

    def lake_base_path_for(self, edition: Edition) -> Path:
        stem = f"{self.gazette_code}_{edition_slug(edition.section)}_{edition.publication_date.isoformat()}"
        return self.lake_dir / self.state / f"{edition.publication_date:%Y/%m}" / stem

    def markdown_path_for(self, edition: Edition) -> Path:
        return self.lake_base_path_for(edition).with_suffix(".md")

    def latest_stored_publication_date(self) -> date | None:
        dates = []
        for path in (self.lake_dir / self.state).rglob("DOEMG_*.md"):
            match = MARKDOWN_DATE_RE.search(path.stem)
            if match:
                dates.append(date.fromisoformat(match.group(1)))
        return max(dates, default=None)


def parse_acts(text: str, collector: MgDoeCollector, edition: Edition, markdown_path: Path) -> list[Act]:
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=[a-záéíóúâêôãõç])", "", text)
    governor = governador_da_edicao(str(markdown_path))
    act_matches = list(mg_regexes.ACT_WINDOW_RE.finditer(text))
    acts: list[Act] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    signer_markers: list[tuple[int, str, str, str]] = [
        (m.start(), "", "", "") for m in mg_regexes.SECTION_HEADER_RE.finditer(text)
        if not any(act.start() <= m.start() < act.end() for act in act_matches)
    ]
    for header in mg_regexes.SIGNER_HEADER_RE.finditer(text):
        name = normalize_name(header.group("name"))
        if not valid_person_name(name):
            continue
        for category, role, pattern in mg_regexes.SIGNER_ROLES:
            if re.fullmatch(pattern, header.group("role"), re.I):
                signer_markers.append((header.start(), name, role, category))
                break
    signer_markers.sort(key=lambda marker: marker[0])
    for match in act_matches:
        body = match.group("body")
        normalized = SPACE_RE.sub(" ", body)
        action = "nomeacao" if match.group("action").upper().startswith("NOME") else "exoneracao"
        people = list(mg_regexes.NAME_BEFORE_ID_RE.finditer(normalized))
        if not people:
            people = list(mg_regexes.DIRECT_NAME_RE.finditer(normalized))
        people_with_offsets = [(person, person.end()) for person in people]
        people_with_offsets.extend(
            (person, len(SPACE_RE.sub(" ", body[:person.end()])))
            for pattern in (mg_regexes.TABLE_PERSON_RE, mg_regexes.LIST_PERSON_RE)
            for person in pattern.finditer(body)
        )
        for person, normalized_end in people_with_offsets:
            name = normalize_name(person.group("name"))
            if not valid_person_name(name):
                continue
            groups = person.groupdict()
            identifier = re.sub(r"[.\s]", "", groups.get("id") or "")
            if groups.get("role"):
                role = clean_piece(groups["role"])
                person_body = ""
            else:
                following = normalized[normalized_end:]
                next_person = mg_regexes.NAME_BEFORE_ID_RE.search(following)
                person_body = following[:next_person.start()] if next_person else following
                role_match = mg_regexes.ROLE_RE.search(person_body)
                if not role_match:
                    role_match = mg_regexes.COUNCIL_ROLE_RE.search(normalized[:normalized_end])
                role = clean_piece(role_match.group("role")) if role_match else ""
            agency_match = mg_regexes.AGENCY_RE.search(person_body)
            if not agency_match:
                prefix = SPACE_RE.sub(" ", text[max(0, match.start() - 450):match.start()])
                prefix = re.split(r"[.;]\s+", prefix)[-1]
                agency_match = mg_regexes.AGENCY_RE.search(prefix)
            agency = clean_piece(agency_match.group("agency")) if agency_match else ""
            key = (action, name, identifier, role, agency)
            if key in seen:
                continue
            seen.add(key)
            signer_name, signer_role, signer_category = "", "", ""
            for marker in signer_markers:
                if marker[0] > match.start():
                    break
                signer_name, signer_role, signer_category = marker[1:]
            excerpt = clean_piece(f"{match.group('action')} {body}")
            acts.append(Act(
                state=collector.state, gazette=collector.gazette_name,
                publication_date=edition.publication_date, section=edition.section,
                action_type=action, person_name=name, functional_id=identifier,
                role=role, agency=agency, excerpt=excerpt[:900], source_url=edition.url,
                signer_name=signer_name, signer_role=signer_role, signer_category=signer_category,
                text_path=str(markdown_path), edition_governor=governor,
                government_representative=nome_representante_governo(governor),
                representative_origin=origem_representante_governo(governor),
            ))
    return acts


def parse_acts_from_markdown_file(
    collector: MgDoeCollector, edition: Edition, markdown_path: Path,
) -> list[Act]:
    return parse_acts(markdown_path.read_text(encoding="utf-8", errors="ignore"), collector, edition, markdown_path)


def collect_mg(
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    collector = MgDoeCollector()
    latest = collector.latest_stored_publication_date()
    first = start_date_override or (collector.start_date if retroativo else latest) or collector.start_date
    last = end_date or date.today()
    if last < first:
        raise ValueError("A data final de MG nao pode ser anterior a data inicial.")
    dates = collector.list_available_dates(first, last)
    if retroativo:
        dates.reverse()
    print(f"Coleta MG: {first} a {last}" + (" (do presente para tras)." if retroativo else "."), file=sys.stderr)
    total = 0
    failed_years: set[int] = set()
    processed_years: set[int] = set()
    skipped_years: set[int] = set()
    for publication_date in dates:
        year = publication_date.year
        if pular_anos_completos and collector.is_year_complete(year):
            if year not in skipped_years:
                print(f"Pulando MG {year}: marcador .year_complete encontrado.", file=sys.stderr)
                skipped_years.add(year)
            continue
        processed_years.add(year)
        try:
            editions = collector.list_editions(publication_date)
            if not editions:
                raise RuntimeError("Calendario anuncia edicao, mas nenhum caderno do Executivo foi encontrado.")
        except Exception as exc:
            failed_years.add(year)
            print(f"Falha ao listar edicoes MG de {publication_date}: {exc}", file=sys.stderr)
            continue
        for edition in editions:
            try:
                print(f"Processando MG {publication_date} ({edition.section})...", file=sys.stderr)
                path = collector.markdown_path_for(edition)
                collector.load_or_create_markdown(edition, path)
                acts = parse_acts_from_markdown_file(collector, edition, path)
                total += collector.write_csv(collector.yearly_csv_path_for(publication_date), acts)
            except Exception as exc:
                failed_years.add(year)
                collector.record_collection_failure(edition, "processar_edicao", exc)
                print(f"Falha ao processar MG {publication_date} ({edition.section}): {exc}", file=sys.stderr)
    for year in processed_years - failed_years:
        # Um intervalo parcial não comprova que o ano inteiro foi coletado.
        if year < date.today().year and first <= date(year, 1, 1) and last >= date(year, 12, 31):
            collector.mark_year_complete(year)
    return total
