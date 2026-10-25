from __future__ import annotations

from datetime import date
import re

from diarios_oficiais import config
from diarios_oficiais.estadual.am_doe import AmDoeCollector, collect_am
from diarios_oficiais.estadual.rj_ioerj import parse_acts
from diarios_oficiais.base import Edition
from diarios_oficiais.utils_regex import ap_doe as regexes


class ApDoeCollector(AmDoeCollector):
    base_url = "https://diofe.portal.ap.gov.br"
    state = "AP"
    gazette_code = "DOEAP"
    gazette_name = "Diario Oficial do Estado do Amapa"
    start_date = date.fromisoformat(config.AP_START_DATE)

    def latest_stored_publication_date(self):
        dates = [
            date.fromisoformat(match.group(1))
            for path in (self.lake_dir / self.state).rglob("DOEAP_*.md")
            if (match := re.search(r"_(\d{4}-\d{2}-\d{2})$", path.stem))
        ]
        return max(dates, default=None)


def collect_ap(pular_anos_completos=True, start_date_override=None, end_date=None, retroativo=False):
    return collect_am(pular_anos_completos, start_date_override, end_date, retroativo, collector_cls=ApDoeCollector)


def parse_acts_from_markdown_file(collector, edition: Edition, markdown_path):
    return parse_acts(markdown_path.read_text(encoding="utf-8", errors="ignore"), collector, edition, markdown_path, regexes=regexes)
