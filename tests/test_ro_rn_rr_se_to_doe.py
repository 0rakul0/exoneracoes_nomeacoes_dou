from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import Mock

from diarios_oficiais.estadual.rn_doe import RnDoeCollector
from diarios_oficiais.estadual.ro_doe import RoDoeCollector
from diarios_oficiais.estadual.rr_doe import RrDoeCollector
from diarios_oficiais.estadual.se_doe import SeDoeCollector
from diarios_oficiais.estadual.to_doe import ToDoeCollector


class RemainingStateTests(unittest.TestCase):
    def test_ro_builds_official_pdf_url(self):
        collector = RoDoeCollector(delay_seconds=0, max_attempts=1)
        collector._pdf_exists = Mock(return_value=True)
        editions = collector.list_editions(date(2026, 10, 23))
        self.assertEqual(len(editions), 1)
        self.assertTrue(editions[0].url.endswith("/2026/10/DOE-23-10-2026.pdf"))

    def test_rn_discovers_main_and_extra_paths(self):
        collector = RnDoeCollector(delay_seconds=0, max_attempts=1)
        collector._pdf_exists = Mock(side_effect=[True, True])
        editions = collector.list_editions(date(2026, 10, 23))
        self.assertEqual(len(editions), 2)
        self.assertTrue(editions[0].url.endswith("/12026-10-23.pdf"))
        self.assertIn("Extra", editions[1].section)

    def test_rr_reads_monthly_form_and_preserves_post_data(self):
        collector = RrDoeCollector(delay_seconds=0, max_attempts=1)
        collector.fetch_text = Mock(return_value='''
            <form action="../_visualizar-doe/" method="post">
              <input type="hidden" name="doe" value="2026/10/doe-20261023.pdf">
              <input type="hidden" name="ano" value="2026">
              <input type="hidden" name="mes" value="10">
            </form>
        ''')
        editions = collector.list_editions(date(2026, 10, 23))
        self.assertEqual(len(editions), 1)
        self.assertIn("doe=2026%2F10%2Fdoe-20261023.pdf", editions[0].url)

    def test_se_reads_public_catalog_json(self):
        collector = SeDoeCollector(delay_seconds=0, max_attempts=1)
        response = Mock()
        response.json.return_value = {
            "itens": [
                {"id": 8020, "suplemento": "Suplemento", "numero": 29996},
                {"id": 8018, "suplemento": "", "numero": 29996},
            ]
        }
        response.raise_for_status = Mock()
        collector.session.get = Mock(return_value=response)
        editions = collector.list_editions(date(2026, 10, 23))
        self.assertEqual(len(editions), 2)
        self.assertTrue(editions[0].url.endswith("/8020"))
        self.assertIn("Suplemento", editions[0].section)

    def test_to_reads_date_search_result(self):
        collector = ToDoeCollector(delay_seconds=0, max_attempts=1)
        response = Mock()
        response.text = '''
          <tr>
            <td>Nº 7169</td><td>23/10/2026</td>
            <td><a href="https://doe.to.gov.br/diario/5810/download" title="Edição 7169">Baixar</a></td>
          </tr>
        '''
        response.raise_for_status = Mock()
        collector.session.get = Mock(return_value=response)
        editions = collector.list_editions(date(2026, 10, 23))
        self.assertEqual(len(editions), 1)
        self.assertEqual(editions[0].url, "https://doe.to.gov.br/diario/5810/download")


if __name__ == "__main__":
    unittest.main()
