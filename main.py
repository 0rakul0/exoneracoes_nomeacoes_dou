from __future__ import annotations

import traceback
from typing import Callable

from diarios_oficiais.base import preload_ocr_models
from diarios_oficiais.rj_ioerj import collect_rj
from diarios_oficiais.rj_ioerj import report_torch_cuda
from diarios_oficiais.sp_doe import collect_sp


COLLECTORS_BY_STATE: dict[str, Callable[[], int]] = {
    "RJ": collect_rj,
    "SP": collect_sp,
}

STATES_TO_COLLECT = ["RJ", "SP"]


def collect_state(state: str) -> int:
    state = state.upper()
    collector = COLLECTORS_BY_STATE.get(state)
    if collector:
        return collector()
    raise ValueError(f"Estado ainda nao implementado: {state}")


def main() -> int:
    report_torch_cuda()
    preload_ocr_models()

    total_by_state: dict[str, int] = {}
    for state in STATES_TO_COLLECT:
        try:
            total_by_state[state] = collect_state(state)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

    for state, total in total_by_state.items():
        print(f"{state}: {total} atos novos gravados nos CSVs anuais")
    return 0


if __name__ == "__main__":
    while True:
        try:
            raise SystemExit(main())
        except SystemExit as exc:
            if exc.code in (None, 0):
                raise
            print(f"Erro ao executar main(): {exc}. Tentando novamente...")
        except Exception:
            traceback.print_exc()
            print("Erro ao executar main(). Tentando novamente...")
