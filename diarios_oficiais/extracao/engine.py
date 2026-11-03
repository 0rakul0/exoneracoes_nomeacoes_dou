"""National extraction interface; preserves state rules during migration."""
from __future__ import annotations
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExtractionProfile:
    state: str
    gazette: str = ""
    regexes: Any = None

    def resolve_rules(self) -> Any:
        if self.regexes is not None:
            return self.regexes
        state = self.state.strip().lower()
        if not state.isalpha() or len(state) != 2:
            raise ValueError(f"Invalid state: {self.state!r}")
        module = "rj_ioerj" if state == "rj" else f"{state}_doe"
        try:
            return import_module(f"diarios_oficiais.utils_regex.{module}")
        except ModuleNotFoundError as exc:
            if exc.name == f"diarios_oficiais.utils_regex.{module}":
                raise ValueError(f"Missing extraction rules for {self.state!r}") from exc
            raise


class ExtractorEngine:
    def __init__(self, profile: ExtractionProfile):
        self.profile = profile

    def extract(self, text: str, collector: Any, edition: Any, path: Path):
        return parse_acts(text, collector, edition, path, regexes=self.profile.resolve_rules())

    def extract_file(self, collector: Any, edition: Any, path: Path):
        return self.extract(path.read_text(encoding="utf-8", errors="ignore"), collector, edition, path)


def parse_acts(text, collector, edition, markdown_path, regexes=None, **kwargs):
    # Legacy parser remains the implementation until parity has been validated.
    from diarios_oficiais.estadual.rj_ioerj import parse_acts as legacy_parse_acts
    if regexes is None:
        regexes = ExtractionProfile(state=collector.state).resolve_rules()
    return legacy_parse_acts(text, collector, edition, markdown_path, regexes=regexes, **kwargs)


def parse_acts_from_markdown_file(collector, edition, markdown_path, regexes=None):
    profile = ExtractionProfile(
        state=collector.state,
        gazette=getattr(collector, "gazette_code", ""),
        regexes=regexes,
    )
    return ExtractorEngine(profile).extract_file(collector, edition, markdown_path)
