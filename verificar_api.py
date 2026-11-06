"""Diagnóstico somente leitura da JT API/PostgreSQL, sem mostrar a chave.
Execute: python verificar_api.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
API = os.getenv("JT_API_URL", "").strip().rstrip("/")
KEY = os.getenv("JT_API_KEY", "").strip()
TABLE = "jt_arbitragem_ocorrencias"
COLUMNS = {
    "chave", "declaracao", "remessa", "primaria", "secundaria", "status",
    "declarada_em", "fechada_em", "base_responsavel", "base", "codigo_base",
    "uf", "rm", "coordenador", "supervisor", "tipo", "modalidade",
    "valor_centavos", "data", "descricao", "comentario_decisao", "comentario_contestacao"
}

def query(sql, params=None):
    try:
        response = httpx.post(API + "/query", json={"sql": sql, "params": params or []},
                              headers={"X-API-Key": KEY},
                              timeout=httpx.Timeout(45, connect=10))
    except httpx.HTTPError as exc:
        raise RuntimeError("JT API inacessível pela rede (" + type(exc).__name__ + ").") from None
    if response.status_code in (401, 403):
        raise RuntimeError("Chave JT_API_KEY recusada (HTTP " + str(response.status_code) + ").")
    if response.status_code != 200:
        raise RuntimeError("Consulta da JT API falhou (HTTP " + str(response.status_code) + ").")
    try:
        result = response.json()
    except ValueError:
        raise RuntimeError("JT API não retornou JSON.") from None
    if isinstance(result, dict):
        for k in ("rows", "data", "result", "resultado", "registros"):
            if isinstance(result.get(k), list):
                result = result[k]
                break
    if not isinstance(result, list):
        raise RuntimeError("Formato de resposta da JT API não reconhecido.")
    return result

def cell(row, name, index=0):
    if isinstance(row, dict):
        if name in row:
            return row[name]
        if len(row) == 1:
            return next(iter(row.values()))
    if isinstance(row, (list, tuple)) and len(row) > index:
        return row[index]
    raise RuntimeError("Formato de coluna inesperado: " + name)

def main():
    if not API.startswith("https://") or not KEY:
        raise RuntimeError("Configure JT_API_URL HTTPS e JT_API_KEY no .env local.")
    print("[1/4] Verificando conexão JT API / PostgreSQL...")
    result = query("SELECT 1 AS ok")
    if not result or int(cell(result[0], "ok")) != 1:
        raise RuntimeError("PostgreSQL não respondeu SELECT 1.")
    print("OK: conexão estabelecida.")
    print("[2/4] Conferindo tabela de arbitragem...")
    result = query("SELECT COUNT(*) AS qtd FROM information_schema.tables WHERE table_schema='public' AND table_name=%s", [TABLE])
    if not result or int(cell(result[0], "qtd")) == 0:
        print("PENDENTE: tabela public." + TABLE + " ainda não existe.")
        return 3
    print("OK: tabela existente.")
    print("[3/4] Conferindo as colunas...")
    result = query("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s", [TABLE])
    missing = COLUMNS - {str(cell(row, "column_name")) for row in result}
    if missing:
        print("ERRO: faltam colunas:", ", ".join(sorted(missing)))
        return 4
    print("OK: esquema completo.")
    print("[4/4] Conferindo registros Orlean...")
    result = query("SELECT tipo, COUNT(*) AS qtd, COALESCE(SUM(valor_centavos),0) AS centavos FROM public." + TABLE + " WHERE POSITION('ORLEAN' IN UPPER(COALESCE(rm,''))) > 0 GROUP BY tipo ORDER BY tipo")
    total = 0
    for row in result:
        kind = cell(row, "tipo", 0)
        count = int(cell(row, "qtd", 1))
        cents = int(cell(row, "centavos", 2))
        total += count
        print("%s: %s ocorrências, R$ %.2f" % (kind, count, cents / 100))
    if not total:
        print("PENDENTE: sem registros Orlean nesta tabela.")
        return 5
    print("OK: dados disponíveis para o dashboard.")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print("ERRO:", exc)
        sys.exit(1)
