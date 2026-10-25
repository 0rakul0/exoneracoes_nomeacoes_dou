from __future__ import annotations

from datetime import date

from diarios_oficiais import config
from diarios_oficiais.estadual._daily_pdf import DailyPdfCollector, collect_daily, parse_daily_acts
from diarios_oficiais.utils_regex import ro_doe as regexes


BASE_URL = "https://diof.ro.gov.br/data/uploads"


class RoDoeCollector(DailyPdfCollector):
    state = "RO"
    gazette_code = "DOERO"
    gazette_name = "Diario Oficial do Estado de Rondonia"
    start_date = date.fromisoformat(config.RO_START_DATE)

    def edition_specs(self, publication_date: date):
        url = f"{BASE_URL}/{publication_date:%Y/%m}/DOE-{publication_date:%d-%m-%Y}.pdf"
        return [("Diario Oficial RO", url)]


def parse_acts_from_markdown_file(collector, edition, markdown_path):
    return parse_daily_acts(collector, edition, markdown_path, regexes)


def collect_ro(**kwargs):
    return collect_daily(RoDoeCollector, regexes, "RO", **kwargs)
