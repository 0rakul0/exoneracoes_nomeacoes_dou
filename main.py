from __future__ import annotations

from typing import Callable

from analise_temporal.analisar_movimentacoes import generate_temporal_analysis_for_states
from diarios_oficiais.rj_ioerj import collect_rj
from diarios_oficiais.rj_ioerj import report_torch_cuda


COLLECTORS_BY_STATE: dict[str, Callable[[], int]] = {
    "RJ": collect_rj,
}

STATES_TO_COLLECT = ["RJ"]
GOVERNMENT_MILESTONES: list[str] = []


def collect_state(state: str) -> int:
    state = state.upper()
    collector = COLLECTORS_BY_STATE.get(state)
    if collector:
        return collector()
    raise ValueError(f"Estado ainda nao implementado: {state}")


def main() -> int:
    report_torch_cuda()

    total_by_state: dict[str, int] = {}
    for state in STATES_TO_COLLECT:
        try:
            total_by_state[state] = collect_state(state)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

    for state, total in total_by_state.items():
        print(f"{state}: {total} atos novos gravados nos CSVs anuais")

    try:
        results = generate_temporal_analysis_for_states(
            government_milestones=GOVERNMENT_MILESTONES,
            complete_years_only=True,
        )
    except FileNotFoundError as exc:
        print(f"Analise temporal nao gerada: {exc}")
        return 0

    for result in results:
        print(f"UF analisada: {result['uf']}")
        print(f"CSVs de analise temporal gerados em: {result['saida']}")
        print(f"CSVs lidos: {result['csvs_lidos']}")
        print(f"Anos analisados: {result['anos_csv']}")
        print(f"Pessoas analisadas: {result['pessoas_analisadas']}")
        print(f"Retornos apos exoneracao: {result['retornos_apos_exoneracao']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
