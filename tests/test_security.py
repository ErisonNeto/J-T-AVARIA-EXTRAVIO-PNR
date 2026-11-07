"""Valida acesso direto sem DASH_USER/DASH_PASSWORD e mantém JT_API_KEY no servidor."""
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import app


class PublicDashboardTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app)

    def test_html_nao_exige_autenticacao(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("WWW-Authenticate", response.headers)

    def test_consulta_nao_exige_usuario_ou_senha(self):
        with patch.object(app, "cached_data", return_value=app.bundle([])):
            result = self.client.get("/api/dados")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["rows"], [])

    def test_api_exige_chave_apenas_para_falar_com_vm(self):
        with patch.dict("os.environ", {"JT_API_KEY": ""}):
            with self.assertRaises(app.HTTPException) as context:
                app.query_api("SELECT 1", [])
            self.assertEqual(context.exception.status_code, 503)
            self.assertIn("JT_API_KEY", context.exception.detail)


if __name__ == "__main__":
    unittest.main()
