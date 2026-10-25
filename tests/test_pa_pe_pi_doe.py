from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import Mock

from diarios_oficiais.estadual.pa_doe import PaDoeCollector
from diarios_oficiais.estadual.pe_doe import PeDoeCollector
from diarios_oficiais.estadual.pi_doe import PiDoeCollector


class PaPePiTests(unittest.TestCase):
    def test_pa_discovers_main_and_extra_pdf_urls(self):
        collector = PaDoeCollector(delay_seconds=0, max_attempts=1)
        collector._pdf_exists = Mock(side_effect=[True, True])
        editions = collector.list_editions(date(2026, 10, 23))
        self.assertEqual(len(editions), 2)
        self.assertIn("2026.10.23.DOE.pdf", editions[0].url)
        self.assertIn("Extra", editions[1].section)

    def test_pe_uses_cepe_catalog_and_s3_path(self):
        collector = PeDoeCollector(delay_seconds=0, max_attempts=1)
        collector._metadata = Mock(side_effect=[
            {"date": "2026-10-23T22:58:03.789", "name": "jornal-23-10-2026.pdf"},
            {"date": "2026-10-23T18:00:33.888", "name": "jornal-23-10-2026.pdf"},
        ])
        editions = collector.list_editions(date(2026, 10, 23))
        self.assertEqual(len(editions), 2)
        self.assertIn("cepebr-prod.s3.sa-east-1.amazonaws.com", editions[0].url)
        self.assertIn("arquivos/resumoDiario", editions[0].url)

    def test_pi_reads_official_datatables_link(self):
        collector = PiDoeCollector(delay_seconds=0, max_attempts=1)
        response = Mock()
        response.json.return_value = {
            "data": [[
                '<a href="../doe/files/diarios/anexo/abc/DOEPI_203_2026.pdf">PDF</a>',
                "203/2026",
                "23/10/2026",
            ]]
        }
        response.raise_for_status = Mock()
        collector.session.post = Mock(return_value=response)
        editions = collector.list_editions(date(2026, 10, 23))
        self.assertEqual(len(editions), 1)
        self.assertTrue(editions[0].url.endswith("/doe/files/diarios/anexo/abc/DOEPI_203_2026.pdf"))


if __name__ == "__main__":
    unittest.main()
