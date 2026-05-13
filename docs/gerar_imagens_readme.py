from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analise_temporal import base_analise as dashboard


IMAGE_SPECS = {
    "serie_temporal_representante.png": {
        "figure": dashboard.fig_serie_temporal_governo,
        "width": 1765,
        "height": 945,
    },
    "entradas_saidas_representante.png": {
        "figure": dashboard.fig_fluxo_por_governo,
        "width": 1611,
        "height": 594,
    },
    "saldo_liquido_representante.png": {
        "figure": dashboard.fig_saldo_por_governo,
        "width": 1630,
        "height": 625,
    },
    "timeline_movimentacoes.png": {
        "figure": dashboard.fig_timeline_governo,
        "width": 1760,
        "height": 693,
    },
    "orgaos_mais_movimentados_top10.png": {
        "figure": lambda data: dashboard.fig_orgaos_por_governo(
            data,
            dashboard.periodo_movimentacoes(data),
        ),
        "width": 1760,
        "height": 750,
    },
}

README_PATH = PROJECT_ROOT / "README.md"
DEFAULT_UF = "RJ"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "img"
REPRESENTATIVES_START = "<!-- README-DYNAMIC:REPRESENTANTES-START -->"
REPRESENTATIVES_END = "<!-- README-DYNAMIC:REPRESENTANTES-END -->"
BALANCE_START = "<!-- README-DYNAMIC:SALDO-START -->"
BALANCE_END = "<!-- README-DYNAMIC:SALDO-END -->"


def filtered_movements(uf: str):
    data = dashboard.df_mov.copy()
    if uf:
        data = data[data["estado"] == uf.upper()]
    return data


def generate_images(uf: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    data = filtered_movements(uf)
    if data.empty:
        raise ValueError(f"Nenhuma movimentacao encontrada para UF={uf}")

    for filename, spec in IMAGE_SPECS.items():
        figure = spec["figure"](data)
        if filename == "orgaos_mais_movimentados_top10.png":
            figure.update_layout(
                font=dict(size=15),
                legend=dict(font=dict(size=16), title_font=dict(size=18)),
                title_font=dict(size=26),
                margin=dict(l=24, r=24, t=82, b=60),
            )
        figure.write_image(
            output_dir / filename,
            width=spec["width"],
            height=spec["height"],
            scale=1,
        )
        print(f"Imagem gerada: {output_dir / filename}")


def format_int(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def representative_summary(data: pd.DataFrame) -> pd.DataFrame:
    summary = (
        data.groupby(["representante_governo", "origem_representante", "tipo_ato"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    for column in ["exoneracao", "nomeacao"]:
        if column not in summary.columns:
            summary[column] = 0
    summary["saldo"] = summary["nomeacao"] - summary["exoneracao"]
    summary["total"] = summary["nomeacao"] + summary["exoneracao"]
    return summary.sort_values("total", ascending=False).reset_index(drop=True)


def representative_label(row: pd.Series) -> str:
    return f"{row['representante_governo']} ({row['origem_representante']})"


def dynamic_representatives_markdown(summary: pd.DataFrame) -> str:
    top = summary.iloc[0]
    second = summary.iloc[1] if len(summary) > 1 else None
    smaller = [row["representante_governo"] for _, row in summary.iloc[2:5].iterrows()]

    lines = [
        REPRESENTATIVES_START,
        "",
        (
            f"{top['representante_governo']} apresenta o maior volume total de atos, "
            f"com **{format_int(top['total'])} movimentações**, sendo "
            f"**{format_int(top['nomeacao'])} nomeações** e "
            f"**{format_int(top['exoneracao'])} exonerações**."
        ),
        "",
    ]
    if second is not None:
        lines.extend(
            [
                (
                    f"{second['representante_governo']} também apresenta volume expressivo, "
                    f"com **{format_int(second['total'])} atos**, distribuídos entre "
                    f"**{format_int(second['nomeacao'])} nomeações** e "
                    f"**{format_int(second['exoneracao'])} exonerações**."
                ),
                "",
            ]
        )
    if smaller:
        names = ", ".join(smaller[:-1])
        if len(smaller) > 1:
            names = f"{names} e {smaller[-1]}"
        else:
            names = smaller[0]
        lines.append(
            "Representantes com menor período de atuação ou menor escopo institucional "
            f"apresentam volumes mais reduzidos, como {names}."
        )
    lines.extend(["", REPRESENTATIVES_END])
    return "\n".join(lines)


def dynamic_balance_markdown(summary: pd.DataFrame) -> str:
    top_rows = summary.head(5)
    largest_positive = summary.sort_values("saldo", ascending=False).iloc[0]
    largest_negative = summary.sort_values("saldo", ascending=True).iloc[0]

    lines = [
        BALANCE_START,
        "",
        "| Representante | Exonerações | Nomeações | Saldo | Total de atos |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for _, row in top_rows.iterrows():
        lines.append(
            f"| {representative_label(row)} | {format_int(row['exoneracao'])} | "
            f"{format_int(row['nomeacao'])} | {format_int(row['saldo'])} | "
            f"{format_int(row['total'])} |"
        )
    lines.extend(
        [
            "",
            (
                f"O maior saldo positivo aparece em **{largest_positive['representante_governo']}**, "
                f"com **{format_int(largest_positive['saldo'])} nomeações líquidas**."
            ),
            (
                f"Já **{largest_negative['representante_governo']}** apresenta saldo negativo, "
                f"com **{format_int(abs(largest_negative['saldo']))} exonerações a mais do que nomeações**, "
                "indicando predominância de saídas no recorte analisado."
            ),
            "",
            BALANCE_END,
        ]
    )
    return "\n".join(lines)


def replace_marked_block(text: str, start: str, end: str, replacement: str) -> str:
    start_index = text.find(start)
    end_index = text.find(end)
    if start_index == -1 or end_index == -1 or end_index < start_index:
        raise ValueError(f"Marcadores nao encontrados no README: {start} / {end}")
    return text[:start_index] + replacement + text[end_index + len(end):]


def update_readme(data: pd.DataFrame, readme_path: Path = README_PATH) -> None:
    summary = representative_summary(data)
    text = readme_path.read_text(encoding="utf-8")
    text = replace_marked_block(
        text,
        REPRESENTATIVES_START,
        REPRESENTATIVES_END,
        dynamic_representatives_markdown(summary),
    )
    text = replace_marked_block(
        text,
        BALANCE_START,
        BALANCE_END,
        dynamic_balance_markdown(summary),
    )
    readme_path.write_text(text, encoding="utf-8", newline="\n")
    print(f"README atualizado: {readme_path}")


def main() -> int:
    data = filtered_movements(DEFAULT_UF)
    generate_images(DEFAULT_UF, DEFAULT_OUTPUT_DIR)
    update_readme(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
