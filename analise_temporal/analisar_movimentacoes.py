from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


ACTION_ORDER = {"exoneracao": 0, "nomeacao": 1}
ADMINISTRATIVE_TERMS = {
    "AGENTE",
    "ANALISTA",
    "ANEXO",
    "ASSESSOR",
    "ASSISTENTE",
    "ATO",
    "AUDITOR",
    "BOLETIM",
    "CANDIDATOS",
    "CANDIDATAS",
    "CARGO",
    "CARGOS",
    "CHEFE",
    "COMISSAO",
    "COMISSÃO",
    "CONFORME",
    "COORDENADOR",
    "DECRETO",
    "DEPARTAMENTO",
    "DIRETOR",
    "ESTADO",
    "EXTRATO",
    "FUNCAO",
    "FUNÇÃO",
    "FUNCIONAL",
    "GABINETE",
    "ID",
    "INTERNO",
    "LOTADA",
    "LOTADO",
    "MATR",
    "MATRICULA",
    "MEMBROS",
    "PORTARIA",
    "PROCESSO",
    "PROFISSIONAIS",
    "RESOLUCAO",
    "RESOLUÇÃO",
    "SECRETARIA",
    "SERVIDOR",
    "SERVIDORES",
    "SERVIDORA",
    "SIMBOLO",
    "SÍMBOLO",
    "SUBSECRETARIA",
    "VAGA",
    "VINCULADA",
    "VINCULADO",
}
SUSPICIOUS_STARTS = {
    "A",
    "AS",
    "COM",
    "CONFORME",
    "DE",
    "DESTA",
    "DO",
    "EM",
    "OS",
    "POR",
    "QUE",
    "SERVIDOR",
    "SERVIDORES",
    "VINCULADA",
    "VINCULADO",
}
ADMINISTRATIVE_PHRASE_RE = re.compile(
    r"\b("
    r"DO CARGO|DA FUNCAO|DA FUNÇÃO|PARA EXERCER|A CONTAR|ID FUNC|"
    r"PROCESSO|SECRETARIA DE ESTADO|EM VAGA|ATO PROPRIO|ATO PRÓPRIO|"
    r"CANDIDATOS|CANDIDATAS|MEMBROS|SERVIDORES"
    r")\b",
    re.I,
)
NAME_SUFFIX_RE = re.compile(
    r"(?:\s*[-,;]\s*|\s+)(?:MATR(?:ICULA)?\.?|ID\.?\s*(?:FUNCIONAL)?|RG|CPF)\b\s*[: NºNO.]*\s*[\w.\-/]+.*$",
    re.I,
)


@dataclass(frozen=True)
class GovernmentMilestone:
    date: date
    label: str


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"\s+", " ", value).strip().upper()
    return value


def clean_person_name(value: str) -> str:
    value = value or ""
    value = re.sub(r"<!--\s*IMAGE\s*-->", " ", value, flags=re.I)
    value = re.sub(r"/U[0-9A-Fa-f]{4}", " ", value)
    value = re.sub(r"\bPARA\s+EXERCER\b.*$", "", value, flags=re.I)
    value = NAME_SUFFIX_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip(" ,.;:-")
    return value


def name_rejection_reason(value: str) -> str:
    normalized = normalize_text(value)
    tokens = normalized.split()
    reasons: list[str] = []

    if len(tokens) < 2:
        reasons.append("menos_de_2_tokens")
    if len(tokens) > 14:
        reasons.append("mais_de_14_tokens")
    if any(char.isdigit() for char in normalized):
        reasons.append("tem_numero")
    if tokens and tokens[0] in SUSPICIOUS_STARTS:
        reasons.append("inicio_suspeito")
    if ADMINISTRATIVE_PHRASE_RE.search(normalized):
        reasons.append("frase_administrativa")
    if any(token in ADMINISTRATIVE_TERMS for token in tokens):
        reasons.append("termo_administrativo")
    if len(normalized) > 80:
        reasons.append("muito_longo")
    return ";".join(reasons)


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_government_milestone(value: str) -> GovernmentMilestone:
    raw_date, separator, raw_label = value.partition(":")
    milestone_date = parse_date(raw_date)
    label = raw_label.strip() if separator else raw_date
    return GovernmentMilestone(milestone_date, label)


def input_csv_paths(root: Path, state: str | None) -> list[Path]:
    if state:
        paths = sorted((root / state).glob("*.csv"))
    else:
        paths = sorted(path for path in root.glob("*/*.csv") if "analises" not in path.parts)
    return [path for path in paths if path.is_file()]


def read_rows(paths: Iterable[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as file:
            for row_number, row in enumerate(csv.DictReader(file), start=2):
                row = dict(row)
                row["_arquivo_csv"] = str(path)
                row["_linha_csv"] = str(row_number)
                row["_data"] = parse_date(row["data_publicacao"])
                row["_nome_original"] = row.get("nome", "")
                row["_nome_limpo"] = clean_person_name(row.get("nome", ""))
                row["_nome_normalizado"] = normalize_text(row["_nome_limpo"])
                row["_nome_rejeicao"] = name_rejection_reason(row["_nome_limpo"])
                row["_cargo_normalizado"] = normalize_text(row.get("cargo", ""))
                row["_orgao_normalizado"] = normalize_text(row.get("orgao", ""))
                rows.append(row)
    return rows


def latest_milestone(event_date: date, milestones: list[GovernmentMilestone]) -> GovernmentMilestone | None:
    previous = [milestone for milestone in milestones if milestone.date <= event_date]
    return max(previous, key=lambda item: item.date) if previous else None


def build_timeline_rows(
    rows: list[dict[str, str]],
    milestones: list[GovernmentMilestone],
) -> list[dict[str, str]]:
    by_person: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["_nome_normalizado"] and not row["_nome_rejeicao"]:
            by_person[row["_nome_normalizado"]].append(row)

    timeline: list[dict[str, str]] = []
    for person, person_rows in sorted(by_person.items()):
        person_rows.sort(
            key=lambda row: (
                row["_data"],
                ACTION_ORDER.get(row.get("tipo_ato", ""), 99),
                row.get("_arquivo_csv", ""),
                int(row.get("_linha_csv", "0")),
            )
        )

        previous_row: dict[str, str] | None = None
        last_exoneration: dict[str, str] | None = None
        for index, row in enumerate(person_rows, start=1):
            action_type = row.get("tipo_ato", "")
            event_date = row["_data"]
            milestone = latest_milestone(event_date, milestones)

            returned_after_exoneration = action_type == "nomeacao" and last_exoneration is not None
            days_since_exoneration = ""
            role_changed_since_exoneration = ""
            agency_changed_since_exoneration = ""
            exoneration_date = ""
            exoneration_role = ""
            exoneration_agency = ""
            if returned_after_exoneration and last_exoneration is not None:
                days_since_exoneration = str((event_date - last_exoneration["_data"]).days)
                exoneration_date = last_exoneration["data_publicacao"]
                exoneration_role = last_exoneration.get("cargo", "")
                exoneration_agency = last_exoneration.get("orgao", "")
                role_changed_since_exoneration = yes_no(
                    bool(row["_cargo_normalizado"])
                    and bool(last_exoneration["_cargo_normalizado"])
                    and row["_cargo_normalizado"] != last_exoneration["_cargo_normalizado"]
                )
                agency_changed_since_exoneration = yes_no(
                    bool(row["_orgao_normalizado"])
                    and bool(last_exoneration["_orgao_normalizado"])
                    and row["_orgao_normalizado"] != last_exoneration["_orgao_normalizado"]
                )

            timeline_row = {
                "nome_normalizado": person,
                "ordem_pessoa": str(index),
                "estado": row.get("estado", ""),
                "diario": row.get("diario", ""),
                "data_publicacao": row.get("data_publicacao", ""),
                "ano": row.get("data_publicacao", "")[:4],
                "tipo_ato": action_type,
                "nome": row.get("_nome_limpo", ""),
                "nome_original_csv": row.get("_nome_original", ""),
                "cargo": row.get("cargo", ""),
                "orgao": row.get("orgao", ""),
                "caderno": row.get("caderno", ""),
                "fonte_url": row.get("fonte_url", ""),
                "arquivo_markdown": row.get("arquivo_markdown", ""),
                "arquivo_csv": row.get("_arquivo_csv", ""),
                "linha_csv": row.get("_linha_csv", ""),
                "ato_anterior": previous_row.get("tipo_ato", "") if previous_row else "",
                "data_anterior": previous_row.get("data_publicacao", "") if previous_row else "",
                "cargo_anterior": previous_row.get("cargo", "") if previous_row else "",
                "orgao_anterior": previous_row.get("orgao", "") if previous_row else "",
                "dias_desde_anterior": str((event_date - previous_row["_data"]).days) if previous_row else "",
                "retorno_apos_exoneracao": yes_no(returned_after_exoneration),
                "data_exoneracao_anterior": exoneration_date,
                "cargo_exoneracao_anterior": exoneration_role,
                "orgao_exoneracao_anterior": exoneration_agency,
                "dias_desde_exoneracao": days_since_exoneration,
                "mudou_cargo_desde_exoneracao": role_changed_since_exoneration,
                "mudou_orgao_desde_exoneracao": agency_changed_since_exoneration,
                "marco_governo": milestone.label if milestone else "",
                "data_marco_governo": milestone.date.isoformat() if milestone else "",
                "dias_desde_marco_governo": str((event_date - milestone.date).days) if milestone else "",
            }
            timeline.append(timeline_row)

            if action_type == "exoneracao":
                last_exoneration = row
            previous_row = row
    return timeline


def yes_no(value: bool) -> str:
    return "sim" if value else "nao"


def build_summary_rows(timeline_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_person: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in timeline_rows:
        by_person[row["nome_normalizado"]].append(row)

    summary_rows: list[dict[str, str]] = []
    for person, rows in sorted(by_person.items()):
        appointment_rows = [row for row in rows if row["tipo_ato"] == "nomeacao"]
        exoneration_rows = [row for row in rows if row["tipo_ato"] == "exoneracao"]
        return_rows = [row for row in rows if row["retorno_apos_exoneracao"] == "sim"]
        summary_rows.append(
            {
                "nome_normalizado": person,
                "nome_exemplo": rows[0]["nome"],
                "total_atos": str(len(rows)),
                "total_nomeacoes": str(len(appointment_rows)),
                "total_exoneracoes": str(len(exoneration_rows)),
                "total_retornos_apos_exoneracao": str(len(return_rows)),
                "primeira_data": min(row["data_publicacao"] for row in rows),
                "ultima_data": max(row["data_publicacao"] for row in rows),
                "cargos_distintos": str(len({row["cargo"] for row in rows if row["cargo"]})),
                "orgaos_distintos": str(len({row["orgao"] for row in rows if row["orgao"]})),
                "teve_nomeacao_e_exoneracao": yes_no(bool(appointment_rows) and bool(exoneration_rows)),
                "teve_retorno_apos_exoneracao": yes_no(bool(return_rows)),
            }
        )
    return summary_rows


def build_rejected_name_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rejected: list[dict[str, str]] = []
    for row in rows:
        if not row["_nome_rejeicao"]:
            continue
        rejected.append(
            {
                "motivo_rejeicao": row["_nome_rejeicao"],
                "nome_original_csv": row.get("_nome_original", ""),
                "nome_limpo": row.get("_nome_limpo", ""),
                "estado": row.get("estado", ""),
                "data_publicacao": row.get("data_publicacao", ""),
                "tipo_ato": row.get("tipo_ato", ""),
                "cargo": row.get("cargo", ""),
                "orgao": row.get("orgao", ""),
                "fonte_url": row.get("fonte_url", ""),
                "arquivo_markdown": row.get("arquivo_markdown", ""),
                "arquivo_csv": row.get("_arquivo_csv", ""),
                "linha_csv": row.get("_linha_csv", ""),
            }
        )
    return rejected


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as file:
        if not fieldnames:
            return
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera serie temporal de nomeacoes/exoneracoes por pessoa."
    )
    parser.add_argument("--entrada", type=Path, default=Path("saida"), help="Pasta com CSVs anuais.")
    parser.add_argument("--saida", type=Path, default=Path("saida/analises"), help="Pasta de saida da analise.")
    parser.add_argument("--uf", default=None, help="Filtra uma UF, por exemplo RJ.")
    parser.add_argument(
        "--marco-governo",
        action="append",
        default=[],
        help="Marco no formato YYYY-MM-DD ou YYYY-MM-DD:rotulo. Pode repetir.",
    )
    args = parser.parse_args()

    paths = input_csv_paths(args.entrada, args.uf)
    if not paths:
        raise SystemExit(f"Nenhum CSV encontrado em {args.entrada}")

    milestones = sorted(
        (parse_government_milestone(value) for value in args.marco_governo),
        key=lambda item: item.date,
    )
    rows = read_rows(paths)
    timeline_rows = build_timeline_rows(rows, milestones)
    return_rows = [row for row in timeline_rows if row["retorno_apos_exoneracao"] == "sim"]
    summary_rows = build_summary_rows(timeline_rows)
    rejected_name_rows = build_rejected_name_rows(rows)

    write_csv(args.saida / "movimentacoes_pessoas.csv", timeline_rows)
    write_csv(args.saida / "retornos_apos_exoneracao.csv", return_rows)
    write_csv(args.saida / "resumo_pessoas.csv", summary_rows)
    write_csv(args.saida / "nomes_suspeitos.csv", rejected_name_rows)

    print(f"CSVs lidos: {len(paths)}")
    print(f"Atos analisados: {len(timeline_rows)}")
    print(f"Pessoas analisadas: {len(summary_rows)}")
    print(f"Retornos apos exoneracao: {len(return_rows)}")
    print(f"Registros com nome suspeito: {len(rejected_name_rows)}")
    print(f"Arquivos gerados em: {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
