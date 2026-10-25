from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.mt_doe import MtDoeCollector, parse_acts_from_markdown_file as parse_mt
from diarios_oficiais.estadual.ms_doe import MsDoeCollector, parse_acts_from_markdown_file as parse_ms


class MtMsDoeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patches = [
            patch.object(MtDoeCollector, "enable_spacy_validation", False),
            patch.object(MsDoeCollector, "enable_spacy_validation", False),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.mt = MtDoeCollector(delay_seconds=0, max_attempts=1)
        self.ms = MsDoeCollector(delay_seconds=0, max_attempts=1)
        self.mt.lake_dir = self.root
        self.ms.lake_dir = self.root

    def test_mt_lists_official_and_extra_editions(self):
        self.mt.fetch_json = Mock(return_value=[
            {"id": 19392, "data": "2026-10-23", "numero": 29343, "diario": "Diário Oficial", "suplemento": ""},
            {"id": 19394, "data": "2026-10-23", "numero": 29343, "diario": "Diário Oficial", "suplemento": "Edição Extra"},
            {"id": 19395, "data": "2026-10-23", "numero": 1, "diario": "Diário da Justiça", "suplemento": ""},
        ])
        editions = self.mt.list_editions(date(2026, 10, 23))
        self.assertEqual(len(editions), 2)
        self.assertIn("Edição Extra", editions[1].section)
        self.assertIn("/edicoes/19392/download", editions[0].url)

    def test_ms_lists_main_and_supplement(self):
        self.ms.fetch_json = Mock(return_value={
            "paginaAtual": 1,
            "totalDePaginas": 1,
            "diario": [
                {"id": 1, "numero": 12313, "dataPublicacao": "23-10-2026 07:30", "nomeArquivo": "DO12313_23_10_2026"},
                {"id": 2, "numero": 12313, "numeroSuplemento": 1, "dataPublicacao": "23/10/2026 07:30:00", "nomeArquivo": "DO12313_23_10_2026_SUP_1"},
            ],
        })
        editions = self.ms.list_editions(date(2026, 10, 23))
        self.assertEqual(len(editions), 2)
        self.assertIn("Suplemento 1", editions[1].section)
        self.assertIn("DO12313_23_10_2026.pdf", editions[0].url)

    def test_mt_parser_extracts_exoneration_and_nomination(self):
        edition = Edition(date(2026, 10, 23), "Diario Oficial MT 29343", "https://example.test/mt.pdf")
        path = self.root / "MT" / "DOEMT_2026-10-23.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            "PODER EXECUTIVO\n"
            "EXONERAR, a pedido, o servidor MAYCON JEFFERSON PEREIRA, matrícula funcional nº 357550/001, "
            "do cargo efetivo de Professor Educação Básica, lotado na Secretaria de Estado de Educação.\n"
            "NOMEAR, nos termos da lei, ANA CAROLINA DA SILVA, matrícula nº 123456/001, "
            "para exercer o cargo de Assessora.\n",
            encoding="utf-8",
        )
        acts = parse_mt(self.mt, edition, path)
        self.assertEqual([(act.action_type, act.person_name, act.functional_id) for act in acts], [
            ("exoneracao", "MAYCON JEFFERSON PEREIRA", "357550/001"),
            ("nomeacao", "ANA CAROLINA DA SILVA", "123456/001"),
        ])

    def test_ms_parser_extracts_direct_name_and_table_name(self):
        edition = Edition(date(2026, 10, 23), "Diario Oficial MS 12313", "https://example.test/ms.pdf")
        path = self.root / "MS" / "DOEMS_2026-10-23.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            "ATOS DE PESSOAL DO PODER EXECUTIVO\n"
            "EXONERAR, a pedido, ANA CAROLINA GUEDES ROSA CURY, matrícula nº 55349461, "
            "do cargo efetivo de Analista de Defensoria.\n"
            "EXONERAR, por necessidade do serviço, o militar abaixo relacionado:\n"
            "1. CB BM WAGNER TIAGO DE PÁDUA MELO 423.616-021\n",
            encoding="utf-8",
        )
        acts = parse_ms(self.ms, edition, path)
        self.assertEqual(len(acts), 2)
        self.assertEqual(acts[0].person_name, "ANA CAROLINA GUEDES ROSA CURY")
        self.assertEqual(acts[0].functional_id, "55349461")
        self.assertEqual(acts[1].person_name, "WAGNER TIAGO DE PÁDUA MELO")


if __name__ == "__main__":
    unittest.main()
