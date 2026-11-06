"""Seguranca: nenhuma rota sensivel pode ficar aberta sem autenticacao."""
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from app import authorize


class SecurityTests(unittest.TestCase):
    def test_producao_sem_senha_rejeita_acesso(self):
        with patch.dict(os.environ, {'APP_ENV': 'production', 'DASH_USER': '', 'DASH_PASSWORD': ''}):
            with self.assertRaises(HTTPException) as error:
                authorize(None)
            self.assertEqual(error.exception.status_code, 503)

    def test_credenciais_incorretas_rejeitadas(self):
        with patch.dict(os.environ, {'APP_ENV': 'production', 'DASH_USER': 'interno', 'DASH_PASSWORD': 'senha-teste'}):
            with self.assertRaises(HTTPException) as error:
                authorize(HTTPBasicCredentials(username='interno', password='errada'))
            self.assertEqual(error.exception.status_code, 401)
            self.assertIn('WWW-Authenticate', error.exception.headers)

    def test_credenciais_corretas_aceitas(self):
        with patch.dict(os.environ, {'APP_ENV': 'production', 'DASH_USER': 'interno', 'DASH_PASSWORD': 'senha-teste'}):
            self.assertTrue(authorize(HTTPBasicCredentials(username='interno', password='senha-teste')))

    def test_modo_local_sem_senha_apenas_explicitamente(self):
        with patch.dict(os.environ, {'APP_ENV': 'local', 'DASH_USER': '', 'DASH_PASSWORD': ''}):
            self.assertTrue(authorize(None))


if __name__ == '__main__':
    unittest.main()
