from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.am_doe import AmDoeCollector, parse_acts_from_markdown_file as parse_am
from diarios_oficiais.estadual.df_doe import DfDoeCollector, parse_acts_from_markdown_file as parse_df
from diarios_oficiais.estadual.go_doe import GoDoeCollector, parse_acts_from_markdown_file as parse_go
from diarios_oficiais.estadual.al_doe import AlDoeCollector
from diarios_oficiais.estadual.ap_doe import ApDoeCollector
from diarios_oficiais.estadual.ma_doe import MaDoeCollector


class AmDfGoTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patches = [patch.object(cls, "enable_spacy_validation", False) for cls in (AmDoeCollector, DfDoeCollector, GoDoeCollector)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_am_and_go_catalogs_keep_supplements(self):
        for collector, number in ((AmDoeCollector(delay_seconds=0, max_attempts=1), 35809), (GoDoeCollector(delay_seconds=0, max_attempts=1), 24892)):
            collector.fetch_json = Mock(return_value={"erro": False, "itens": [
                {"id": 1, "numero": number, "suplemento": 0, "suplemento_nome": ""},
                {"id": 2, "numero": number, "suplemento": 1, "suplemento_nome": "Suplemento"},
            ]})
            editions = collector.list_editions(date(2026, 10, 23))
            self.assertEqual(len(editions), 2)
            self.assertIn("Suplemento", editions[1].section)
            self.assertIn("/portal/edicoes/download/1", editions[0].url)

    def test_df_catalog_reads_integrated_and_extra_pdfs(self):
        collector = DfDoeCollector(delay_seconds=0, max_attempts=1)
        collector.fetch_html = Mock(return_value=(
            '<script>var lstLinkPdf = {"INTEGRA":[{"nome":"INTEGRA.pdf",'
            '"link":"2026|10_Outubro|DODF 198 23-10-2026|&arquivo=DODF 198 23-10-2026 INTEGRA.pdf"}],'
            '"EDICAO EXTRA":[{"nome":"EDICAO EXTRA A.pdf",'
            '"link":"2026|10_Outubro|DODF 121 23-10-2026 EDICAO EXTRA A|&arquivo=DODF 121 23-10-2026 EDICAO EXTRA A.pdf"}]};'
            ' var materiasDiario = [];</script>'
        ))
        editions = collector.list_editions(date(2026, 10, 23))
        self.assertEqual(len(editions), 2)
        self.assertIn("INTEGRA", editions[0].section)
        self.assertIn("visualizar-pdf", editions[0].url)

    def test_al_ap_and_ma_catalogs(self):
        al = AlDoeCollector(delay_seconds=0, max_attempts=1)
        al.fetch_json = Mock(return_value={"editions": [
            {"id": 10, "number": 2909, "suplement": False, "publication_date": "2026-10-23T03:00:00.000000Z"},
            {"id": 11, "number": 2909, "suplement": True, "publication_date": "2026-10-23T03:00:00.000000Z"},
        ]})
        al_editions = al.list_editions(date(2026, 10, 23))
        self.assertEqual(len(al_editions), 2)
        self.assertIn("Suplemento", al_editions[1].section)
        self.assertIn("downloadPdf/10", al_editions[0].url)

        ap = ApDoeCollector(delay_seconds=0, max_attempts=1)
        ap.fetch_json = Mock(return_value={"erro": False, "itens": [
            {"id": 20, "numero": 8769, "suplemento": 0, "tipo_edicao_nome": "Diário Oficial"},
        ]})
        ap_editions = ap.list_editions(date(2026, 10, 23))
        self.assertEqual(len(ap_editions), 1)
        self.assertIn("8769", ap_editions[0].section)

        ma = MaDoeCollector(delay_seconds=0, max_attempts=1)
        ma.fetch_json = Mock(side_effect=[
            {"cadernos": {"EX": {"listCadernos": [
                {"volume": "Vol. 150, ", "numero": "No. 192", "dataPublicacao": "23/10/2026", "arquivo": "EX20261023"},
            ]}}},
            *([{"cadernos": {}}] * 7),
        ])
        ma_editions = ma.list_editions(date(2026, 10, 23))
        self.assertEqual(len(ma_editions), 1)
        self.assertIn("EX20261023", ma_editions[0].url)

    def parse(self, collector, parser, state, text):
        path = self.root / state / "edicao_2026-10-23.md"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        return parser(collector, Edition(date(2026, 10, 23), "Diario Oficial", "https://example.test/edicao.pdf"), path)

    def test_parsers_extract_personnel_actions(self):
        am = self.parse(AmDoeCollector(delay_seconds=0, max_attempts=1), parse_am, "AM",
                        "EXONERAR, a pedido, MARIA DA SILVA, matrícula nº 12345-6, do cargo efetivo de Analista.\n")
        df = self.parse(DfDoeCollector(delay_seconds=0, max_attempts=1), parse_df,
                        "DF", "NOMEAR JOAO DE SOUZA para exercer o cargo de Assessor.\n")
        go = self.parse(GoDoeCollector(delay_seconds=0, max_attempts=1), parse_go,
                        "GO", "NOMEAR, para compor a comissão, ANA CAROLINA DA SILVA, CPF nº 123.456.789-00, para o cargo de membro.\n")
        self.assertEqual(am[0].action_type, "exoneracao")
        self.assertEqual(am[0].functional_id, "12345-6")
        self.assertEqual(df[0].person_name, "JOAO DE SOUZA")
        self.assertEqual(go[0].action_type, "nomeacao")


if __name__ == "__main__":
    unittest.main()
