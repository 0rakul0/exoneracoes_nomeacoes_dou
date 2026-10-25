from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from scripts import consolidar_dados


class ConsolidarDadosTests(unittest.TestCase):
    def test_escreve_agregado_e_arquivos_por_uf(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            analises = root / "analises"
            consolidado = root / "consolidado"

            for state, person in (("RJ", "Pessoa RJ"), ("SP", "Pessoa SP")):
                state_dir = analises / state
                state_dir.mkdir(parents=True)
                pd.DataFrame(
                    [{
                        "nome_normalizado": person,
                        "data_publicacao": "2026-10-23",
                        "tipo_ato": "Nomeacao",
                        "orgao": "Secretaria de Estado",
                        "cargo": "Assessor",
                        "cargo_assinante": "Governador",
                        "governador_edicao": "Governador Teste - 2026",
                    }]
                ).to_parquet(state_dir / "movimentacoes_pessoas.parquet", index=False)
                pd.DataFrame(
                    [{
                        "nome_normalizado": person,
                        "data_publicacao": "2026-10-23",
                        "data_exoneracao_anterior": "2026-10-01",
                        "orgao": "Secretaria de Estado",
                        "cargo_assinante": "Governador",
                        "governador_edicao": "Governador Teste - 2026",
                        "mudou_cargo_desde_exoneracao": "nao",
                        "mudou_orgao_desde_exoneracao": "nao",
                        "dias_desde_exoneracao": 22,
                        "spacy_entidades": "",
                    }]
                ).to_csv(state_dir / "retornos_apos_exoneracao.csv", index=False)

            with patch.object(consolidar_dados, "ANALISES_DIR", analises), patch.object(
                consolidar_dados, "CONSOLIDADO_DIR", consolidado
            ):
                consolidar_dados.consolidate()

            self.assertEqual(
                sorted(path.name for path in consolidado.iterdir() if path.is_dir()),
                ["RJ", "SP"],
            )
            for state in ("RJ", "SP"):
                state_dir = consolidado / state
                self.assertTrue((state_dir / "movimentacoes.parquet").exists())
                self.assertTrue((state_dir / "retornos.parquet").exists())
                self.assertEqual(
                    set(pd.read_parquet(state_dir / "movimentacoes.parquet")["estado"]),
                    {state},
                )
                self.assertEqual(
                    set(pd.read_parquet(state_dir / "retornos.parquet")["estado"]),
                    {state},
                )

            self.assertEqual(len(pd.read_parquet(consolidado / "movimentacoes.parquet")), 2)
            self.assertEqual(len(pd.read_parquet(consolidado / "retornos.parquet")), 2)


if __name__ == "__main__":
    unittest.main()
