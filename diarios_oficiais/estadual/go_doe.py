from __future__ import annotations

import re
from datetime import date

from diarios_oficiais import config
from diarios_oficiais.estadual.am_doe import AmDoeCollector, collect_am
from diarios_oficiais.estadual.rj_ioerj import parse_acts
from diarios_oficiais.utils_regex import go_doe as regexes
from diarios_oficiais.base import Edition


class GoDoeCollector(AmDoeCollector):
    base_url = "https://diariooficial.abc.go.gov.br"
    state = "GO"
    gazette_code = "DOEG"
    gazette_name = "Diario Oficial do Estado de Goias"
    start_date = date.fromisoformat(config.GO_START_DATE)

    def latest_stored_publication_date(self):
        dates = [date.fromisoformat(m.group(1)) for p in (self.lake_dir / self.state).rglob("DOEG_*.md") if (m := re.search(r"_(\d{4}-\d{2}-\d{2})$", p.stem))]
        return max(dates, default=None)


def collect_go(pular_anos_completos=True, start_date_override=None, end_date=None, retroativo=False):
    return collect_am(pular_anos_completos, start_date_override, end_date, retroativo, collector_cls=GoDoeCollector)


def parse_acts_from_markdown_file(collector, edition: Edition, markdown_path):
    return parse_acts(markdown_path.read_text(encoding="utf-8", errors="ignore"), collector, edition, markdown_path, regexes=regexes)
