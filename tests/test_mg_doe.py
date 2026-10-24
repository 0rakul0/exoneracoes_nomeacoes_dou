from __future__ import annotations

import base64
import ssl
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests
from pypdf import PdfReader, PdfWriter

from diarios_oficiais.base import Edition
from diarios_oficiais.estadual.mg_doe import API_URL, MgDoeCollector, MgTLSAdapter, collect_mg, decode_pdf, parse_acts
from diarios_oficiais.governadores import governador_da_edicao


class MgDoeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spacy = patch.object(MgDoeCollector, "enable_spacy_validation", False)
        self.spacy.start()
        self.addCleanup(self.spacy.stop)
        self.collector = MgDoeCollector(delay_seconds=0, max_attempts=2)
        self.collector.lake_dir = self.root
        self.addCleanup(self.collector.session.close)
        governador_da_edicao.cache_clear()

    @staticmethod
    def response(data=None, status=200, errors=None):
        response = Mock(status_code=status)
        response.json.return_value = {"dados": data, "erros": errors or []}
        if status >= 400:
            response.raise_for_status.side_effect = requests.HTTPError(str(status))
        return response

    def test_authenticates_and_refreshes_public_token(self):
        self.collector.session = Mock(headers={})
        self.collector.session.get.side_effect = [
            self.response(status=401), self.response([]),
            self.response(status=401), self.response([]),
        ]
        self.collector.session.post.side_effect = [self.response("first"), self.response("renewed")]
        self.assertEqual(self.collector.fetch_json(API_URL + "calendar"), [])
        self.assertEqual(self.collector.fetch_json(API_URL + "calendar"), [])
        self.assertEqual(self.collector.session.headers["Authorization"], "Bearer renewed")

    def test_api_error_is_not_an_empty_calendar(self):
        self.collector.session = Mock()
        self.collector.session.get.return_value = self.response(errors=["indisponivel"])
        with self.assertRaisesRegex(RuntimeError, "indisponivel"):
            self.collector.fetch_json(API_URL + "calendar")
        self.assertEqual(self.collector.session.get.call_count, 2)

    def test_tls_completes_chain_only_for_mg_and_keeps_verification(self):
        adapter = self.collector.session.get_adapter(API_URL)
        self.assertIsInstance(adapter, MgTLSAdapter)
        self.assertNotIsInstance(self.collector.session.get_adapter("https://example.test"), MgTLSAdapter)
        self.assertIs(self.collector.session.verify, True)
        self.assertTrue(adapter.ssl_context.check_hostname)
        self.assertEqual(adapter.ssl_context.verify_mode, ssl.CERT_REQUIRED)
        common_names = [value for certificate in adapter.ssl_context.get_ca_certs()
                        for group in certificate["subject"] for key, value in group if key == "commonName"]
        self.assertIn("Sectigo Public Server Authentication CA DV R36", common_names)
        request = requests.Request("GET", API_URL).prepare()
        _, options = adapter.build_connection_pool_key_attributes(request, True)
        self.assertIs(options["ssl_context"], adapter.ssl_context)

    def test_tls_failure_is_reported_without_repeating_same_connection(self):
        self.collector.session = Mock()
        self.collector.session.get.side_effect = requests.exceptions.SSLError("CERTIFICATE_VERIFY_FAILED")
        with self.assertRaisesRegex(RuntimeError, "Falha de certificado HTTPS"):
            self.collector.fetch_json(API_URL + "calendar")
        self.collector.session.get.assert_called_once()

    def test_calendar_filters_range_and_crosses_year(self):
        self.collector.fetch_json = Mock(side_effect=[
            [{"dataPublicacao": "2025-12-30T00:00:00"}, {"dataPublicacao": "2025-12-31T00:00:00"}],
            [{"dataPublicacao": "2026-01-03T00:00:00"}, {"dataPublicacao": "2026-01-03T00:00:00"}],
        ])
        dates = self.collector.list_available_dates(date(2025, 12, 31), date(2026, 1, 3))
        self.assertEqual(dates, [date(2025, 12, 31), date(2026, 1, 3)])
        self.assertIn("MesPublicacao=1&AnoPublicacao=2026", self.collector.fetch_json.call_args.args[0])

    def test_selects_executive_and_extra_and_reuses_primary_file(self):
        pdf = b"%PDF-1.7\nexample\n%%EOF\n"
        primary = {"arquivo": base64.b64encode(pdf).decode(), "arquivoUnico": True}
        self.collector.fetch_json = Mock(return_value={
            "dataPublicacao": "2026-10-07T00:00:00",
            "cadernos": [
                {"id": 331096, "descricao": "Diário do Executivo"},
                {"id": 331097, "descricao": "Diário dos Municípios Mineiros"},
                {"id": 331098, "descricao": "Diário de Terceiros"},
                {"id": 331099, "descricao": "Edição Extra"},
            ],
            "arquivoCadernoPrincipal": primary,
        })
        editions = self.collector.list_editions(date(2026, 10, 7))
        self.assertEqual([e.section for e in editions], ["Diário do Executivo", "Edição Extra"])
        self.assertNotEqual(self.collector.markdown_path_for(editions[0]), self.collector.markdown_path_for(editions[1]))
        path = self.collector.download_edition_pdf(editions[0], self.root / "edition.pdf")
        self.assertEqual(path.read_bytes(), pdf)
        self.collector.fetch_json.assert_called_once()

    def test_empty_day_and_wrong_date(self):
        self.collector.fetch_json = Mock(return_value=None)
        self.assertEqual(self.collector.list_editions(date(2026, 10, 18)), [])
        self.collector.fetch_json.return_value = {"dataPublicacao": "2026-10-17", "cadernos": []}
        with self.assertRaisesRegex(RuntimeError, "data inesperada"):
            self.collector.list_editions(date(2026, 10, 18))

    def test_decodes_signed_pdf_and_rejects_invalid_download(self):
        pdf = b"%PDF-1.7\ncontent\n%%EOF"
        self.assertEqual(decode_pdf(base64.b64encode(b"cms-envelope" + pdf + b"signature").decode()), pdf + b"\n")
        for value in ("not base64!!", base64.b64encode(b"<html>error</html>").decode()):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                decode_pdf(value)

    def test_assembles_separate_pages_in_order(self):
        def page_data(number, width):
            writer = PdfWriter()
            writer.add_blank_page(width=width, height=200)
            output = BytesIO()
            writer.write(output)
            return {"arquivo": base64.b64encode(output.getvalue()).decode(), "arquivoUnico": False,
                    "totalPaginas": 2, "pagina": number}
        self.collector.fetch_json = Mock(side_effect=[page_data(1, 100), page_data(2, 150)])
        edition = Edition(date(2026, 10, 23), "Diário do Executivo", API_URL + "Caderno/ObterArquivoCadernoPorId?id=1")
        path = self.collector.download_edition_pdf(edition, self.root / "pages.pdf")
        self.assertEqual([int(p.mediabox.width) for p in PdfReader(path).pages], [100, 150])
        self.assertTrue(self.collector.fetch_json.call_args.args[0].endswith("&pagina=2"))

    def parse(self, text):
        path = self.root / "MG/DOEMG_2026-10-23.md"
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8")
        governador_da_edicao.cache_clear()
        return parse_acts(text, self.collector, Edition(date(2026, 10, 23), "Diário do Executivo", "https://example.test"), path)

    def test_realistic_mg_acts_with_legal_citations_tables_and_masp(self):
        # Trechos adaptados do PDF oficial de 23/10/2026; sem carregar o acervo.
        text = (Path(__file__).parent / "fixtures/mg_executivo.txt").read_text(encoding="utf-8")
        acts = self.parse(text)
        self.assertEqual(len(acts), 6)
        self.assertEqual([(a.person_name, a.functional_id) for a in acts[:2]], [
            ("ANDRÉ SILVA COUTINHO", "1563433-0"), ("ANA LÚCIA BARBOSA FARIA", "1532788-5"),
        ])
        self.assertEqual(acts[2].action_type, "exoneracao")
        self.assertEqual(acts[3].action_type, "nomeacao")
        self.assertIn("DAI-13", acts[3].role)
        self.assertEqual(acts[3].functional_id, "1569793-1")
        self.assertEqual(acts[3].agency, "Instituto de Desenvolvimento do Norte e Nordeste de Minas Gerais")
        self.assertEqual(acts[3].signer_name, "HENRIQUE OLIVEIRA CARVALHO")
        self.assertEqual(acts[-1].signer_name, "LUCIANA LOPES NOMINATO BRAGA")
        self.assertEqual(acts[-1].agency, "Instituto de Previdência dos Servidores do Estado de Minas Gerais")
        self.assertTrue(all(a.edition_governor == "Mateus Simões de Almeida - Governador" for a in acts))

    def test_direct_name_without_masp_and_distinct_positions(self):
        acts = self.parse("NOMEAR JOÃO DA SILVA para exercer o cargo de Diretor.\n"
                          "NOMEAR JOÃO DA SILVA para exercer o cargo de Assessor.\n"
                          "EXONERAR MARIA DE SOUZA do cargo de Diretora.\n")
        self.assertEqual(len(acts), 3)
        self.assertIn("Diretor", acts[0].role)
        self.assertIn("Assessor", acts[1].role)
        self.assertEqual(acts[-1].person_name, "MARIA DE SOUZA")

    def test_markdown_table_keeps_individual_roles_and_ids(self):
        acts = self.parse("EXONERA os servidores:\n"
                          "| Nome | Cargo | Masp |\n| --- | --- | --- |\n"
                          "| João da Silva | Analista de Gestão | 1.234.567-8 |\n"
                          "| Maria de Souza | Técnico Administrativo | 1.345.678-9 |\n")
        self.assertEqual([(a.person_name, a.functional_id, a.role) for a in acts], [
            ("JOÃO DA SILVA", "1234567-8", "Analista de Gestão"),
            ("MARIA DE SOUZA", "1345678-9", "Técnico Administrativo"),
        ])

    def test_role_and_agency_do_not_absorb_each_other(self):
        agency = "Instituto de Previdência dos Servidores do Estado de Minas Gerais"
        cases = [
            ("para o cargo de Diretor da Secretaria de Estado de Saúde",
             "cargo de Diretor", "Secretaria de Estado de Saúde"),
            (f"do {agency}, do cargo de Analista", "cargo de Analista", agency),
            (f"do {agency} do cargo de Analista", "cargo de Analista", agency),
            ("para exercer a função de Assessor na Fundação João Pinheiro",
             "função de Assessor", "Fundação João Pinheiro"),
            ("do cargo de provimento efetivo de Analista da Polícia Civil e de Atividades Governamentais",
             "cargo de provimento efetivo de Analista da Polícia Civil e de Atividades Governamentais", ""),
            ("para o cargo de Diretor da Secretaria de Estado de Agricultura, Pecuária e Abastecimento",
             "cargo de Diretor", "Secretaria de Estado de Agricultura, Pecuária e Abastecimento"),
        ]
        for body, role, expected_agency in cases:
            with self.subTest(body=body):
                acts = self.parse(f"NOMEIA, nos termos da lei, JOÃO DA SILVA, MASP 1234567-8, {body}, a partir de 01/10/2026.\n")
                self.assertEqual(len(acts), 1)
                self.assertEqual(acts[0].role, role)
                self.assertEqual(acts[0].agency, expected_agency)

    def test_police_agency_header_survives_long_context_but_not_new_section(self):
        for header in (
            "Polícia Civil do Estado de Minas Gerais",
            "ATOS ASSINADOS PELA SENHORA CHEFE DA POLÍCIA CIVIL DE MINAS GERAIS",
        ):
            with self.subTest(header=header):
                acts = self.parse(
                    header + "\n" + "Texto intermediário.\n" * 60
                    + "EXONERA os servidores:\n"
                    "João da Silva Analista de Gestão 1.234.567-8 I Unidade Técnica\n\n"
                    "Secretaria de Estado de Saúde\n"
                    "NOMEIA, nos termos da lei, MARIA DE SOUZA, MASP 1345678-9, "
                    "para o cargo de Diretora.\n"
                )
                self.assertEqual(len(acts), 2)
                self.assertEqual(acts[0].agency, header if header.startswith("Polícia") else
                                 "POLÍCIA CIVIL DE MINAS GERAIS")
                self.assertEqual(acts[0].role, "Analista de Gestão")
                self.assertEqual(acts[1].agency, "")

    def test_parenthesized_agency_prepositions_from_october_22(self):
        agency = "Secretaria de Estado de Infraestrutura, Mobilidade e Parcerias"
        role = "cargo de provimento em comissão DAD-6 OP1101462"
        for preposition in ("do(a)", "da", "no(a)", "pela(o)"):
            for separator in (" ", ", de recrutamento amplo, "):
                with self.subTest(preposition=preposition, separator=separator):
                    acts = self.parse(
                        "nomeia, nos termos da lei, CARLOS EDUARDO MAGALHÃES PAULINO, "
                        f"MASP 1194572-2, para o {role}{separator}{preposition} "
                        "Secretaria de Estado de Infraestrutura, Mobilidade e\n"
                        "Parcerias, a contar de 22/10/2026.\n"
                    )
                    self.assertEqual(len(acts), 1)
                    self.assertEqual(acts[0].role, role)
                    self.assertEqual(acts[0].agency, agency)

    def test_partial_year_is_not_marked_complete(self):
        collector = Mock(start_date=date(2025, 1, 1))
        collector.latest_stored_publication_date.return_value = None
        collector.list_available_dates.return_value = [date(2025, 10, 23)]
        collector.is_year_complete.return_value = False
        collector.list_editions.return_value = [Edition(date(2025, 10, 23), "Executivo", "https://example.test")]
        collector.markdown_path_for.return_value = self.root / "unused.md"
        collector.write_csv.return_value = 2
        with patch("diarios_oficiais.estadual.mg_doe.MgDoeCollector", return_value=collector), \
             patch("diarios_oficiais.estadual.mg_doe.parse_acts_from_markdown_file", return_value=[]):
            total = collect_mg(start_date_override=date(2025, 10, 23), end_date=date(2025, 10, 23))
        self.assertEqual(total, 2)
        collector.mark_year_complete.assert_not_called()

    def test_council_appointment_does_not_include_replaced_member(self):
        acts = self.parse(
            "nomeia, usando da competência delegada pelo Decreto nº 48.415, "
            "o(s) representante(s) abaixo relacionado(s) como membro(s) junto ao "
            "Conselho Estadual de Assistência Social - CEAS, a contar de 03/09/2026:\n"
            "Conselho Regional de Serviço Social de Minas Gerais\n"
            "ADRIELLE NUNES PARREIRAS, em substituição a LUDMILLA LAMARTINE DE SOUZA, TITULAR\n"
        )
        self.assertEqual([a.person_name for a in acts], ["ADRIELLE NUNES PARREIRAS"])
        self.assertIn("Conselho Estadual de Assistência Social", acts[0].role)

    def test_cli_dispatches_mg_range_and_retroactive_flag(self):
        import main
        with patch.object(main, "report_torch_cuda"), patch.object(main, "collect_mg", return_value=0) as collect, \
             patch("sys.argv", ["main.py", "--coletar-mg", "--mg-retroativo", "--mg-data-inicial", "2026-10-07",
                                "--mg-data-final", "2026-10-23"]):
            self.assertEqual(main.main(), 0)
        collect.assert_called_once_with(pular_anos_completos=True, start_date_override=date(2026, 10, 7),
                                        end_date=date(2026, 10, 23), retroativo=True)


if __name__ == "__main__":
    unittest.main()
