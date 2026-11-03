"""Parity and ownership tests for the shared national parser."""
from __future__ import annotations
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from diarios_oficiais.extracao import parser
from diarios_oficiais.extracao.engine import parse_acts
from diarios_oficiais.estadual import rj_ioerj
from diarios_oficiais.utils_regex import rj_ioerj as rj_rules


class ParserMigrationTests(unittest.TestCase):
    def test_legacy_exports_refer_to_shared_functions(self):
        for name in ("parse_acts", "extract_person_names", "normalize_name", "valid_person_name", "edition_slug", "extract_signer"):
            self.assertIs(getattr(rj_ioerj, name), getattr(parser, name))

    def test_engine_keeps_rules_and_raw_markdown(self):
        fake = SimpleNamespace(state="RJ")
        with patch("diarios_oficiais.extracao.parser.parse_acts", return_value=["act"]) as fn:
            self.assertEqual(parse_acts("RAW  TEXT", fake, None, Path("a.md"), regexes=rj_rules), ["act"])
            self.assertEqual(fn.call_args.args[0], "RAW  TEXT")
            self.assertIs(fn.call_args.kwargs["regexes"], rj_rules)

    def test_collector_not_defined_in_parser(self):
        self.assertFalse(hasattr(parser, "RjIoerjCollector"))


if __name__ == "__main__":
    unittest.main()
