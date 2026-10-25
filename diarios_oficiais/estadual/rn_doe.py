from __future__ import annotations

from datetime import date

from diarios_oficiais import config
from diarios_oficiais.estadual._daily_pdf import DailyPdfCollector, collect_daily, parse_daily_acts
from diarios_oficiais.utils_regex import rn_doe as regexes


BASE_URL = "https://webdisk.diariooficial.rn.gov.br/Jornal"


class RnDoeCollector(DailyPdfCollector):
    state = "RN"
    gazette_code = "DOERN"
    gazette_name = "Diario Oficial do Estado do Rio Grande do Norte"
    start_date = date.fromisoformat(config.RN_START_DATE)

    def edition_specs(self, publication_date: date):
        stem = f"1{publication_date:%Y-%m-%d}"
        return [
            ("Diario Oficial RN", f"{BASE_URL}/{stem}.pdf"),
            ("Diario Oficial RN Extra", f"{BASE_URL}/{stem}E.pdf"),
        ]


def parse_acts_from_markdown_file(collector, edition, markdown_path):
    return parse_daily_acts(collector, edition, markdown_path, regexes)


def collect_rn(**kwargs):
    return collect_daily(RnDoeCollector, regexes, "RN", **kwargs)
