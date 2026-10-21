from __future__ import annotations

from datetime import date

from diarios_oficiais import config
from diarios_oficiais.estadual.pb_power import PbPowerCollector, collect_pb_power


class AcPowerCollector(PbPowerCollector):
    """Base comum para os diarios oficiais separados do Acre."""

    state = "AC"
    start_date = date.fromisoformat(config.AC_START_DATE)


def collect_ac_power(
    collector_class: type[AcPowerCollector],
    pular_anos_completos: bool = True,
    start_date_override: date | None = None,
    end_date: date | None = None,
    retroativo: bool = False,
) -> int:
    return collect_pb_power(
        collector_class,
        pular_anos_completos=pular_anos_completos,
        start_date_override=start_date_override,
        end_date=end_date,
        retroativo=retroativo,
    )
