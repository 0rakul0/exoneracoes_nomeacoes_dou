from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from diarios_oficiais.extracao.engine import ExtractionProfile, ExtractorEngine, parse_acts


class ExtractionEngineTests(unittest.TestCase):
    def test_custom_rules_are_forwarded(self):
        rules = object()
        collector = SimpleNamespace(state="SP")
        with patch("diarios_oficiais.extracao.parser.parse_acts", return_value=["ok"]) as parser:
            self.assertEqual(parse_acts("NOMEAR", collector, object(), Path("x.md"), regexes=rules), ["ok"])
            self.assertIs(parser.call_args.kwargs["regexes"], rules)

    def test_extract_file_uses_profile(self):
        rules = object()
        collector = SimpleNamespace(state="BA")
        with TemporaryDirectory() as temp:
            path = Path(temp) / "a.md"
            path.write_text("EXONERAR", encoding="utf-8")
            with patch("diarios_oficiais.extracao.parser.parse_acts", return_value=[]) as parser:
                ExtractorEngine(ExtractionProfile("BA", regexes=rules)).extract_file(collector, object(), path)
                self.assertEqual(parser.call_args.args[0], "EXONERAR")
                self.assertIs(parser.call_args.kwargs["regexes"], rules)

    def test_invalid_state_rejected(self):
        with self.assertRaises(ValueError):
            ExtractionProfile("../SP").resolve_rules()


if __name__ == "__main__":
    unittest.main()
