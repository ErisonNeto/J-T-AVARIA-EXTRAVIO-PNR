"""Diagnóstico seguro da JT API / PostgreSQL para Avaria, Extravio e PNR.

Executar do PC: python diagnosticar_api.py
Não publica nem altera dados e não exibe chave, remessas ou outras informações sigilosas.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)

URL = os.environ.get("JT_API_URL", "").strip().rstrip("/")
KEY = os.environ.get("JT_API_KEY", "").strip()

EXPECTED_COLUMNS = {
    "chave", "declaracao", "remessa", "primaria", "secundaria", "status",
    "declarada_em", "fechada_em", "base_responsavel", "base", "codigo_base",
    "uf", "rm", "coordenador", "supervisor", "tipo", "modalidade",
    "valor_centavos", "data", "descricao", "comentario_decisao",
    "comentario_contestacao",
}


def rows(result):
    if isinstance(result, dict):
        for field in ("rows", "data", "result", "resultado", "registros"):
            if isinstance(result.get(field), list):
                return result[field]
        return []
    if isinstance(result, list):
        return result
    return []


def first_value(result, key=None):
    data = rows(result)
    if not data:
        return None
    item = data[0]
    if isinstance(item, dict):
        return item.get(key) if key else next(iter(item.values()), None)
    if isinstance(item, (list, tuple)):
        return item[0] if item else None
    return None


def request(client, name, sql, params=None):
    try:
        response = client.post(
            URL + "/query",
            headers={"X-API-Key": KEY},
            json={"sql": sql, "params": params or []},
            timeout=httpx.Timeout(45.0, connect=12.0),
        )
    except httpx.HTTPError as exc:
        print(f"{name}: conexão falhou ({type(exc).__name__})")
        return None
    print(f"{name}: HTTP {response.status_code}")
    if response.status_code != 200:
        if response.status_code in (401, 403):
            print("  JT_API_KEY sem autorização ou autenticação rejeitada.")
        elif response.status_code >= 500:
            print("  A API central retornou erro no servidor/consulta PostgreSQL.")
        else:
            print("  Requisição rejeitada; conferir a rota /query e a consulta.")
        return None
    try:
        return response.json()
    except ValueError:
        print("  Resposta JSON inválida.")
        return None


def main():
    if not URL.startswith("https://"):
        print("Erro: configure JT_API_URL com HTTPS no arquivo .env.")
        return 2
    if not KEY:
        print("Erro: configure JT_API_KEY no arquivo .env; não compartilhe a chave.")
        return 2

    with httpx.Client() as client:
        conn = request(client, "1/4 Conexão JT API / PostgreSQL", "SELECT 1 AS ok")
        if conn is None:
            return 1
        print("  Consulta simples executada.")

        exists = request(
            client,
            "2/4 Existência da tabela de arbitragem",
            "SELECT COUNT(*) AS qtd FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s",
            ["public", "jt_arbitragem_ocorrencias"],
        )
        if exists is None:
            return 1
        if str(first_value(exists, "qtd")) != "1":
            print("  Tabela jt_arbitragem_ocorrencias NÃO encontrada em public.")
            print("  A tabela deve ser criada/alimentada via rotina ETL da JT API, fora do dashboard.")
            return 1
        print("  Tabela existente.")

        cols_result = request(
            client,
            "3/4 Estrutura da tabela",
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
            ["public", "jt_arbitragem_ocorrencias"],
        )
        if cols_result is None:
            return 1
        available = set()
        for col in rows(cols_result):
            if isinstance(col, dict):
                available.add(str(col.get("column_name", "")))
            elif isinstance(col, (list, tuple)) and col:
                available.add(str(col[0]))
        missing = sorted(EXPECTED_COLUMNS - available)
        if missing:
            print("  Faltam colunas:", ", ".join(missing))
            return 1
        print("  Todas as colunas esperadas existem.")

        sample = request(
            client,
            "4/4 Consulta exata utilizada pelo dashboard (amostra sem exibição de dados)",
            "SELECT chave, declaracao, remessa, primaria, secundaria, status, "
            "declarada_em, fechada_em, base_responsavel, base, codigo_base, uf, "
            "rm, coordenador, supervisor, tipo, modalidade, valor_centavos, "
            "data, descricao, comentario_decisao, comentario_contestacao "
            "FROM public.jt_arbitragem_ocorrencias "
            "WHERE POSITION('ORLEAN' IN UPPER(COALESCE(rm, ''))) > 0 "
            "ORDER BY data DESC NULLS LAST, chave DESC LIMIT %s OFFSET %s",
            [1, 0],
        )
        if sample is None:
            return 1
        print("  Consulta executou. Registros na amostra:", len(rows(sample)))
        if not rows(sample):
            print("  A tabela existe, mas não há registros para Orlean.")
        else:
            print("  Banco e consulta estão prontos para carregar o dashboard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
