from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from diarios_oficiais.governadores import (
    governador_da_edicao,
    nome_representante_governo,
    origem_representante_governo,
)

DEFAULT_INPUT_DIR = PROJECT_ROOT / "saida"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "saida" / "analises"
DEFAULT_LAKE_DIR = PROJECT_ROOT / "LAKE"

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
CSV_YEAR_RE = re.compile(r"(?:^|_)(?P<year>20\d{2})(?:\.csv)?$", re.I)
YEAR_COMPLETE_MARKER = ".year_complete"


@dataclass(frozen=True)
class GovernmentMilestone:
    date: date
    label: str


def load_spacy_model(model_name: str, enabled: bool) -> Any | None:
    if not enabled:
        return None
    try:
        import spacy
    except ImportError:
        print("spaCy nao instalado; usando apenas filtros heuristicos de nomes.")
        return None

    try:
        return spacy.load(model_name)
    except OSError:
        print(
            f"Modelo spaCy '{model_name}' nao encontrado; "
            f"instale com: python -m spacy download {model_name}"
        )
        return None


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


def spacy_person_validation(value: str, nlp: Any | None) -> tuple[str, str]:
    if nlp is None:
        return "indisponivel", ""
    if not value:
        return "nao", ""

    normalized_name = normalize_text(value)
    entities: list[str] = []
    variants = [value, value.title()]

    for variant in variants:
        doc = nlp(variant)
        for entity in doc.ents:
            entity_text = entity.text.strip()
            label = entity.label_.upper()
            if not entity_text:
                continue
            entities.append(f"{entity_text}:{label}")
            normalized_entity = normalize_text(entity_text)
            if label in {"PER", "PERSON"} and (
                normalized_entity == normalized_name
                or normalized_entity in normalized_name
                or normalized_name in normalized_entity
            ):
                return "sim", "|".join(dict.fromkeys(entities))

    return "nao", "|".join(dict.fromkeys(entities))


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_government_milestone(value: str) -> GovernmentMilestone:
    raw_date, separator, raw_label = value.partition(":")
    milestone_date = parse_date(raw_date)
    label = raw_label.strip() if separator else raw_date
    return GovernmentMilestone(milestone_date, label)


def csv_year(path: Path) -> int | None:
    match = CSV_YEAR_RE.search(path.stem)
    return int(match.group("year")) if match else None


def is_analysis_ready_csv(path: Path, lake_dir: Path = DEFAULT_LAKE_DIR, today: date | None = None) -> bool:
    year = csv_year(path)
    if year is None:
        return True
    today = today or date.today()
    if year >= today.year:
        return True
    state = path.parent.name
    return (lake_dir / state / str(year) / YEAR_COMPLETE_MARKER).exists()


def input_csv_paths(
    root: Path,
    state: str | None,
    ready_years_only: bool = True,
    years: Iterable[int] | None = None,
    lake_dir: Path = DEFAULT_LAKE_DIR,
) -> list[Path]:
    if state:
        paths = sorted((root / state).glob("*.csv"))
    else:
        paths = sorted(path for path in root.glob("*/*.csv") if "analises" not in path.parts)
    paths = [path for path in paths if path.is_file()]
    year_filter = set(years or [])
    if year_filter:
        paths = [path for path in paths if csv_year(path) in year_filter]
    if ready_years_only:
        paths = [path for path in paths if is_analysis_ready_csv(path, lake_dir=lake_dir)]
    return paths


def discover_states(
    root: Path,
    ready_years_only: bool = True,
    years: Iterable[int] | None = None,
    lake_dir: Path = DEFAULT_LAKE_DIR,
) -> list[str]:
    if not root.exists():
        return []
    return sorted(
        path.name.upper()
        for path in root.iterdir()
        if path.is_dir()
        and path.name.lower() != "analises"
        and any(input_csv_paths(root, path.name, ready_years_only=ready_years_only, years=years, lake_dir=lake_dir))
    )


def read_rows(paths: Iterable[Path], nlp: Any | None, spacy_mode: str) -> list[dict[str, str]]:
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
                row["_spacy_pessoa"] = row.get("spacy_pessoa", "")
                row["_spacy_entidades"] = row.get("spacy_entidades", "")
                if nlp is not None or not row["_spacy_pessoa"]:
                    row["_spacy_pessoa"], row["_spacy_entidades"] = spacy_person_validation(row["_nome_limpo"], nlp)
                if (
                    spacy_mode == "filtrar"
                    and not row["_nome_rejeicao"]
                    and row["_spacy_pessoa"] != "sim"
                    and row["_spacy_pessoa"] != "indisponivel"
                ):
                    row["_nome_rejeicao"] = "spacy_nao_confirmou_pessoa"
                row["_cargo_normalizado"] = normalize_text(row.get("cargo", ""))
                row["_orgao_normalizado"] = normalize_text(row.get("orgao", ""))
                if not row.get("governador_edicao", ""):
                    row["governador_edicao"] = governador_da_edicao(row.get("arquivo_markdown", ""))
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
            governor = row.get("governador_edicao", "")
            representative = nome_representante_governo(governor)

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
                "spacy_pessoa": row.get("_spacy_pessoa", ""),
                "spacy_entidades": row.get("_spacy_entidades", ""),
                "cargo": row.get("cargo", ""),
                "orgao": row.get("orgao", ""),
                "assinante": row.get("assinante", ""),
                "cargo_assinante": row.get("cargo_assinante", ""),
                "categoria_assinante": row.get("categoria_assinante", ""),
                "governador_edicao": governor,
                "representante_governo": representative,
                "origem_representante": origem_representante_governo(governor),
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
        governor = row.get("governador_edicao", "")
        rejected.append(
            {
                "motivo_rejeicao": row["_nome_rejeicao"],
                "nome_original_csv": row.get("_nome_original", ""),
                "nome_limpo": row.get("_nome_limpo", ""),
                "spacy_pessoa": row.get("_spacy_pessoa", ""),
                "spacy_entidades": row.get("_spacy_entidades", ""),
                "estado": row.get("estado", ""),
                "data_publicacao": row.get("data_publicacao", ""),
                "tipo_ato": row.get("tipo_ato", ""),
                "cargo": row.get("cargo", ""),
                "orgao": row.get("orgao", ""),
                "assinante": row.get("assinante", ""),
                "cargo_assinante": row.get("cargo_assinante", ""),
                "categoria_assinante": row.get("categoria_assinante", ""),
                "governador_edicao": governor,
                "representante_governo": nome_representante_governo(governor),
                "origem_representante": origem_representante_governo(governor),
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


def generate_temporal_analysis(
    input_dir: Path = DEFAULT_INPUT_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    lake_dir: Path = DEFAULT_LAKE_DIR,
    state: str | None = None,
    government_milestones: Iterable[str] = (),
    spacy_model_name: str = "pt_core_news_sm",
    spacy_mode: str = "filtrar",
    disable_spacy: bool = False,
    ready_years_only: bool = True,
    years: Iterable[int] | None = None,
) -> dict[str, int | str]:
    paths = input_csv_paths(input_dir, state, ready_years_only=ready_years_only, years=years, lake_dir=lake_dir)
    if not paths:
        detail = " pronto para analise" if ready_years_only else ""
        year_detail = f" para os anos {', '.join(str(year) for year in years)}" if years else ""
        raise FileNotFoundError(f"Nenhum CSV{detail}{year_detail} encontrado em {input_dir}")

    milestones = sorted(
        (parse_government_milestone(value) for value in government_milestones),
        key=lambda item: item.date,
    )
    nlp = load_spacy_model(spacy_model_name, enabled=not disable_spacy)
    rows = read_rows(paths, nlp, spacy_mode)
    timeline_rows = build_timeline_rows(rows, milestones)
    return_rows = [row for row in timeline_rows if row["retorno_apos_exoneracao"] == "sim"]
    summary_rows = build_summary_rows(timeline_rows)
    rejected_name_rows = build_rejected_name_rows(rows)

    write_csv(output_dir / "movimentacoes_pessoas.csv", timeline_rows)
    write_csv(output_dir / "retornos_apos_exoneracao.csv", return_rows)
    write_csv(output_dir / "resumo_pessoas.csv", summary_rows)
    write_csv(output_dir / "nomes_suspeitos.csv", rejected_name_rows)

    return {
        "csvs_lidos": len(paths),
        "atos_analisados": len(timeline_rows),
        "pessoas_analisadas": len(summary_rows),
        "retornos_apos_exoneracao": len(return_rows),
        "registros_com_nome_suspeito": len(rejected_name_rows),
        "spacy": "desativado" if disable_spacy else spacy_model_name if nlp is not None else "indisponivel",
        "saida": str(output_dir),
        "anos_csv": ",".join(str(year) for year in sorted({csv_year(path) for path in paths if csv_year(path)})),
    }


def generate_temporal_analysis_for_states(
    input_dir: Path = DEFAULT_INPUT_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    lake_dir: Path = DEFAULT_LAKE_DIR,
    states: Iterable[str] | None = None,
    government_milestones: Iterable[str] = (),
    spacy_model_name: str = "pt_core_news_sm",
    spacy_mode: str = "filtrar",
    disable_spacy: bool = False,
    ready_years_only: bool = True,
    years: Iterable[int] | None = None,
) -> list[dict[str, int | str]]:
    state_list = (
        [state.upper() for state in states]
        if states is not None
        else discover_states(input_dir, ready_years_only=ready_years_only, years=years, lake_dir=lake_dir)
    )
    if not state_list:
        detail = " pronto para analise" if ready_years_only else ""
        year_detail = f" para os anos {', '.join(str(year) for year in years)}" if years else ""
        raise FileNotFoundError(f"Nenhuma UF com CSV{detail}{year_detail} encontrada em {input_dir}")

    results: list[dict[str, int | str]] = []
    for state in state_list:
        result = generate_temporal_analysis(
            input_dir=input_dir,
            output_dir=output_dir / state,
            lake_dir=lake_dir,
            state=state,
            government_milestones=government_milestones,
            spacy_model_name=spacy_model_name,
            spacy_mode=spacy_mode,
            disable_spacy=disable_spacy,
            ready_years_only=ready_years_only,
            years=years,
        )
        result["uf"] = state
        results.append(result)
    return results


def print_results(results: Iterable[dict[str, int | str]]) -> None:
    for result in results:
        print(f"UF: {result['uf']}")
        print(f"CSVs lidos: {result['csvs_lidos']}")
        print(f"Anos analisados: {result['anos_csv']}")
        print(f"Atos analisados: {result['atos_analisados']}")
        print(f"Pessoas analisadas: {result['pessoas_analisadas']}")
        print(f"Retornos apos exoneracao: {result['retornos_apos_exoneracao']}")
        print(f"Registros com nome suspeito: {result['registros_com_nome_suspeito']}")
        print(f"spaCy: {result['spacy']}")
        print(f"Arquivos gerados em: {result['saida']}")


def available_states(root: Path = DEFAULT_INPUT_DIR, include_incomplete: bool = True) -> list[str]:
    return discover_states(root, ready_years_only=not include_incomplete)


def available_years_for_state(
    state: str,
    root: Path = DEFAULT_INPUT_DIR,
    lake_dir: Path = DEFAULT_LAKE_DIR,
    include_incomplete: bool = True,
) -> list[int]:
    return sorted(
        {
            year
            for path in input_csv_paths(
                root,
                state,
                ready_years_only=not include_incomplete,
                lake_dir=lake_dir,
            )
            for year in [csv_year(path)]
            if year is not None
        }
    )


def choose_from_list(title: str, values: list[str]) -> str | None:
    if not values:
        print("Nenhuma opcao encontrada.")
        return None

    print(title)
    for index, value in enumerate(values, start=1):
        print(f"{index}. {value}")
    choice = input("Escolha: ").strip()
    if not choice.isdigit():
        print("Opcao invalida.")
        return None
    index = int(choice)
    if index < 1 or index > len(values):
        print("Opcao invalida.")
        return None
    return values[index - 1]


def run_interactive_menu() -> int:
    print("Analise temporal")
    print("1. Gerar analise para anos prontos")
    print("2. Gerar analise incluindo anos incompletos")
    print("3. Escolher UF e ano")
    print("4. Sair")
    choice = input("Escolha: ").strip()

    try:
        if choice == "1":
            results = generate_temporal_analysis_for_states()
        elif choice == "2":
            results = generate_temporal_analysis_for_states(ready_years_only=False)
        elif choice == "3":
            states = available_states(include_incomplete=True)
            state = choose_from_list("UFs encontradas:", states)
            if not state:
                return 1
            years = [str(year) for year in available_years_for_state(state, include_incomplete=True)]
            selected_year = choose_from_list(f"Anos encontrados para {state}:", years)
            if not selected_year:
                return 1
            ready_only = input("Exigir ano pronto no LAKE? [S/n]: ").strip().lower() != "n"
            results = [
                generate_temporal_analysis(
                    state=state,
                    output_dir=DEFAULT_OUTPUT_DIR / state,
                    ready_years_only=ready_only,
                    years=[int(selected_year)],
                )
            ]
            results[0]["uf"] = state
        elif choice == "4":
            return 0
        else:
            print("Opcao invalida.")
            return 1
    except FileNotFoundError as exc:
        print(str(exc))
        print("Se os CSVs anuais ainda nao existem, rode primeiro: python main.py")
        return 1

    print_results(results)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gera serie temporal de nomeacoes/exoneracoes por pessoa.")
    parser.add_argument("--entrada", type=Path, default=DEFAULT_INPUT_DIR, help="Pasta com CSVs anuais.")
    parser.add_argument("--saida", type=Path, default=DEFAULT_OUTPUT_DIR, help="Pasta de saida da analise.")
    parser.add_argument("--lake", type=Path, default=DEFAULT_LAKE_DIR, help="Pasta LAKE usada para verificar anos concluidos.")
    parser.add_argument("--uf", default=None, help="Filtra uma UF, por exemplo RJ. Se omitir, roda todas as UFs em --entrada.")
    parser.add_argument(
        "--marco-governo",
        action="append",
        default=[],
        help="Marco no formato YYYY-MM-DD ou YYYY-MM-DD:rotulo. Pode repetir.",
    )
    parser.add_argument(
        "--ano",
        action="append",
        type=int,
        default=[],
        help="Ano especifico para analisar. Pode repetir. Exemplo: --ano 2025.",
    )
    parser.add_argument(
        "--spacy-modelo",
        default="pt_core_news_sm",
        help="Modelo spaCy usado para validar nomes de pessoas.",
    )
    parser.add_argument(
        "--spacy-modo",
        choices=["filtrar", "anotar"],
        default="filtrar",
        help="Em 'filtrar', remove nomes nao confirmados pelo spaCy quando o modelo estiver disponivel.",
    )
    parser.add_argument(
        "--sem-spacy",
        action="store_true",
        help="Desativa a validacao por spaCy e usa apenas as regras heuristicas.",
    )
    parser.add_argument(
        "--incluir-anos-incompletos",
        "--incluir-ano-atual",
        dest="incluir_anos_incompletos",
        action="store_true",
        help="Inclui CSVs sem marcador de conclusao no LAKE.",
    )
    return parser


def main() -> int:
    if len(sys.argv) == 1:
        return run_interactive_menu()

    args = build_parser().parse_args()

    try:
        if args.uf:
            results = [
                generate_temporal_analysis(
                    input_dir=args.entrada,
                    output_dir=args.saida,
                    lake_dir=args.lake,
                    state=args.uf,
                    government_milestones=args.marco_governo,
                    spacy_model_name=args.spacy_modelo,
                    spacy_mode=args.spacy_modo,
                    disable_spacy=args.sem_spacy,
                    ready_years_only=not args.incluir_anos_incompletos,
                    years=args.ano or None,
                )
            ]
            results[0]["uf"] = args.uf.upper()
        else:
            results = generate_temporal_analysis_for_states(
                input_dir=args.entrada,
                output_dir=args.saida,
                lake_dir=args.lake,
                government_milestones=args.marco_governo,
                spacy_model_name=args.spacy_modelo,
                spacy_mode=args.spacy_modo,
                disable_spacy=args.sem_spacy,
                ready_years_only=not args.incluir_anos_incompletos,
                years=args.ano or None,
            )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    print_results(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
