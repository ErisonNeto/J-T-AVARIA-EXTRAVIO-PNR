"""Testes sintéticos de integração com a JT API — sem dados reais."""
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

import app as dashboard


class APIBackendTests(unittest.TestCase):
    def sample(self, kind, cents, i):
        return {
            "chave": str(i), "declaracao": str(i), "remessa": "BR26" + str(i),
            "tipo": kind, "primaria": "EXTRAVIO-遗失" if kind == "Extravio" else kind,
            "secundaria": "Teste", "base": "BASE A", "codigo_base": "1",
            "rm": "ORLEAN DA SILVA DO NASCIMENTO", "valor_centavos": cents,
            "data": "2026-11-06",
        }

    def test_api_receives_positional_rows_with_colunas(self):
        payload = {"colunas": ["data", "valor_centavos"],
                   "rows": [["2026-11-06", 1500]]}
        self.assertEqual(
            dashboard.rows_of(payload), [{"data": "2026-11-06", "valor_centavos": 1500}]
        )

    def test_three_tabs_independent(self):
        records = [
            self.sample("Avaria", 1500, 1),
            self.sample("Extravio", 2500, 2),
            self.sample("PNR", 500, 3),
        ]
        result = dashboard.bundle(records)
        self.assertEqual(result["meta"]["qtd_por_tipo"],
                         {"Avaria": 1, "Extravio": 1, "PNR": 1})
        self.assertEqual(result["meta"]["valor_total_centavos"], 4500)
        self.assertEqual(result["meta"]["valor_por_tipo_centavos"]["PNR"], 500)
        self.assertEqual(result["meta"]["datas"]["max"], "2026-11-06")

    def test_closure_date_overrides_legacy_declaration_date(self):
        row = self.sample("Avaria", 1200, 42)
        row["data"] = "2026-11-06"  # legado: AC usada como data
        row["declarada_em"] = "2026-10-31"
        row["fechada_em"] = "2026-11-06"
        out = dashboard.bundle([row])
        self.assertEqual(out["rows"][0]["data"], "2026-11-06")
        self.assertEqual(out["rows"][0]["fechada_em"], "2026-11-06")
        self.assertEqual(out["meta"]["datas"]["max"], "2026-11-06")

    def test_review_statuses_do_not_become_financially_final(self):
        rows = [
            dict(self.sample("Avaria", 1000, 1), status="Processo encerrado"),
            dict(self.sample("Extravio", 2500, 2), status="Arbitragem finalizada"),
            dict(self.sample("Extravio", 3300, 3), status="Revogado"),
            dict(self.sample("PNR", 400, 4), status="Apelação a ser atribuída"),
            dict(self.sample("PNR", 500, 5), status="Apelação no andamento"),
            dict(self.sample("Avaria", 700, 6), status=""),
            dict(self.sample("Avaria", 800, 7), status="Novo status desconhecido"),
        ]
        bundle = dashboard.bundle(rows)
        finalized = [r for r in bundle["rows"] if r["situacao_financeira"] == "finalizado"]
        review = [r for r in bundle["rows"] if r["situacao_financeira"] == "conferencia"]
        self.assertEqual(len(finalized), 2)
        self.assertEqual(bundle["meta"]["total_finalizados"], 2)
        self.assertEqual(bundle["meta"]["valor_finalizados_centavos"], 3500)
        self.assertEqual(bundle["meta"]["total_conferencia"], 5)
        self.assertEqual(bundle["meta"]["valor_conferencia_centavos"], 5700)
        self.assertEqual(sum(r["valor_centavos"] for r in finalized), 3500)
        self.assertEqual(len(review), 5)
        self.assertEqual(sum(r["valor_centavos"] for r in review), 5700)
        self.assertEqual(bundle["meta"]["total_ativos"], 7)
        self.assertEqual(bundle["meta"]["valor_total_centavos"], 9200)
        self.assertEqual(dashboard.financial_status(" processo  encerrado "), "finalizado")
        self.assertEqual(dashboard.financial_status("APELAÇÃO NO ANDAMENTO"), "conferencia")

    def test_invalid_financial_amount_fails_loudly(self):
        with self.assertRaises(HTTPException):
            dashboard.normalize_rows([self.sample("PNR", "inválido", 1)])

    def test_missing_api_key_is_not_silent(self):
        with patch.dict("os.environ", {"JT_API_KEY": ""}):
            with self.assertRaises(HTTPException) as ex:
                dashboard.query_api("SELECT 1", [])
            self.assertEqual(ex.exception.status_code, 503)

    def test_dashboard_does_not_accept_report_uploads(self):
        with patch.dict("os.environ", {
            "APP_ENV": "local", "DASH_USER": "", "DASH_PASSWORD": ""
        }):
            client = TestClient(dashboard.app)
            response = client.post("/api/importar")
            self.assertEqual(response.status_code, 404)
            with patch.object(dashboard, "cached_data", return_value=dashboard.bundle([])):
                result = client.get("/api/dados")
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()["rows"], [])

    def test_fixed_sql_only_orlean_and_paginates(self):
        self.assertIn("ORLEAN", dashboard.QUERY)
        self.assertIn("jt_arbitragem_ocorrencias", dashboard.QUERY)
        with patch.object(dashboard, "query_api", return_value=[
            self.sample("Avaria", 100, 1)
        ]) as mock:
            rows = dashboard.read_database()
            self.assertEqual(len(rows), 1)
            self.assertEqual(mock.call_args.args[1], [500, 0])


if __name__ == "__main__":
    unittest.main()
