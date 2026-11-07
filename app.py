"""J&T | Avaria / Extravio / PNR — dashboard que lê o PostgreSQL via JT API.

Nenhuma planilha ou arquivo local é recebido pelo serviço Render.
Os dados ficam no PostgreSQL da VM e chegam pela JT API /query.
"""
from __future__ import annotations

import hmac
import os
import time
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)
app = FastAPI(title="J&T | Avaria • Extravio • PNR", docs_url=None, redoc_url=None)
security = HTTPBasic(auto_error=False)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

API_URL = os.getenv("JT_API_URL", "https://jt-api.rockettechbr.com.br").strip().rstrip("/")
TABLE = "jt_arbitragem_ocorrencias"

# Campos fixos, sem interpolar dados fornecidos por usuários na consulta SQL.
COLS = (
    "chave", "declaracao", "remessa", "primaria", "secundaria", "status",
    "declarada_em", "fechada_em", "base_responsavel", "base", "codigo_base",
    "uf", "rm", "coordenador", "supervisor", "tipo", "modalidade",
    "valor_centavos", "data", "descricao", "comentario_decisao",
    "comentario_contestacao",
)
QUERY = (
    "SELECT " + ", ".join(COLS) +
    " FROM public." + TABLE +
    " WHERE POSITION('ORLEAN' IN UPPER(COALESCE(rm, ''))) > 0"
    " ORDER BY data DESC NULLS LAST, chave DESC"
)
PAGE_SIZE = 500
MAX_ROWS = 100000

FINAL_STATUSES = {"PROCESSO ENCERRADO", "ARBITRAGEM FINALIZADA"}


def financial_status(status: str) -> str:
    """Somente dois estados explícitos entram nos KPIs financeiros.

    Revogados, recursos, vazios e estados ainda não catalogados são preservados
    no histórico, mas enviados à seção de conferência (nunca tratados como pagos).
    """
    plain = unicodedata.normalize("NFKD", str(status or ""))
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    normalized = " ".join(plain.upper().split())
    return "finalizado" if normalized in FINAL_STATUSES else "conferencia"



def authorize(credentials: HTTPBasicCredentials | None = Depends(security)):
    user = os.getenv("DASH_USER", "")
    password = os.getenv("DASH_PASSWORD", "")
    local = os.getenv("APP_ENV", "production").lower() == "local"
    if local and not user and not password:
        return True
    if not user or not password:
        raise HTTPException(503, "Defina DASH_USER e DASH_PASSWORD no Render.")
    if credentials is None or not (
        hmac.compare_digest(credentials.username, user)
        and hmac.compare_digest(credentials.password, password)
    ):
        raise HTTPException(
            401, "Usuário ou senha inválidos.",
            headers={"WWW-Authenticate": 'Basic realm="J&T Indicadores"'},
        )
    return True


def rows_of(result, columns=COLS):
    """Aceita o formato {rows,colunas}, lista de objetos ou linhas posicionais."""
    if isinstance(result, dict):
        colunas = result.get("colunas") or columns
        for name in ("rows", "data", "result", "resultado", "registros"):
            if isinstance(result.get(name), list):
                return rows_of(result[name], colunas)
        raise RuntimeError("Formato desconhecido de resposta da JT API.")
    if not isinstance(result, list):
        raise RuntimeError("JT API /query não retornou uma lista de linhas.")
    output = []
    for row in result:
        if isinstance(row, dict):
            output.append(row)
        elif isinstance(row, (list, tuple)) and len(row) == len(columns):
            output.append(dict(zip(columns, row)))
        else:
            raise RuntimeError("Colunas da JT API não correspondem ao SQL do indicador.")
    return output


def query_api(sql: str, params: list):
    if not API_URL.startswith("https://"):
        raise HTTPException(503, "JT_API_URL deve ser a URL HTTPS da JT API.")
    key = os.getenv("JT_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "Configure JT_API_KEY no servidor Render.")
    try:
        response = httpx.post(
            API_URL + "/query",
            headers={"X-API-Key": key},
            json={"sql": sql, "params": params},
            timeout=httpx.Timeout(120.0, connect=15.0),
        )
    except httpx.HTTPError:
        raise HTTPException(503, "A JT API está indisponível ou inacessível.") from None
    if response.status_code != 200:
        if response.status_code in (401, 403):
            raise HTTPException(503, "JT_API_KEY não autorizada pela JT API.")
        if response.status_code >= 500:
            raise HTTPException(503, "Falha na consulta do PostgreSQL pela JT API.")
        raise HTTPException(
            503,
            "A consulta de arbitragem falhou. Confira a tabela "
            "jt_arbitragem_ocorrencias no PostgreSQL e as permissões da JT API.",
        )
    try:
        return rows_of(response.json())
    except (ValueError, RuntimeError):
        raise HTTPException(503, "JT API retornou um formato inválido para o indicador.") from None


def read_database():
    all_rows = []
    offset = 0
    while True:
        batch = query_api(QUERY + " LIMIT %s OFFSET %s", [PAGE_SIZE, offset])
        all_rows.extend(batch)
        if len(all_rows) > MAX_ROWS:
            raise HTTPException(503, "O histórico excede 100.000 ocorrências; implementar consulta por período.")
        if len(batch) < PAGE_SIZE:
            break
        offset += len(batch)
    return all_rows


def normalize_rows(records):
    out = []
    for row in records:
        item = {name: row.get(name) for name in COLS}
        # Data operacional do ticket: fechamento (AC), inclusive em históricos antigos.
        item["data"] = str(item.get("fechada_em") or item.get("declarada_em") or item.get("data") or "")[:10]
        item["fechada_em"] = str(item.get("fechada_em") or "")[:10]
        item["declarada_em"] = str(item.get("declarada_em") or "")[:10]
        for field in ("chave", "declaracao", "remessa", "primaria", "secundaria",
                      "status", "base_responsavel", "base", "codigo_base", "uf",
                      "rm", "coordenador", "supervisor", "tipo", "modalidade",
                      "descricao", "comentario_decisao", "comentario_contestacao"):
            item[field] = str(item.get(field) or "").strip()
        try:
            item["valor_centavos"] = int(item.get("valor_centavos") or 0)
        except (TypeError, ValueError):
            raise HTTPException(503, "Valor financeiro inválido no banco; revise valor_centavos.") from None
        item["situacao_financeira"] = financial_status(item["status"])
        if item["tipo"] not in {"Avaria", "Extravio", "PNR"}:
            raise HTTPException(503, "Indicador inválido cadastrado na arbitragem: revise a origem dos dados.")
        out.append(item)
    out.sort(key=lambda row: (row['data'], row['chave']), reverse=True)
    return out


def bundle(records):
    rows = normalize_rows(records)
    types = ("Avaria", "Extravio", "PNR")
    quantities = Counter(r["tipo"] for r in rows)
    dates = sorted(r["data"] for r in rows if r["data"])
    amounts = {group: sum(r["valor_centavos"] for r in rows if r["tipo"] == group)
               for group in types}
    return {
        "meta": {
            "origem": ["PostgreSQL jt_indicadores / JT API /query"],
            "rm": "ORLEAN",
            "moeda": "BRL",
            "coluna_data": "Data de fechamento (AC); fallback declaração (L)",
            "total_na_exportacao": None,
            "total_ativos": len(rows),
            "qtd_por_tipo": {group: quantities[group] for group in types},
            "valor_por_tipo_centavos": amounts,
            "valor_total_centavos": sum(r["valor_centavos"] for r in rows),
            "datas": {"min": dates[0] if dates else "", "max": dates[-1] if dates else ""},
            "bases_gestao_orlean": None,
            "bases_ofensoras": len({r["codigo_base"] or r["base"] for r in rows}),
            "sem_correspondencia_global": None,
            "sem_correspondencia_detalhes": [],
            "fora_escopo_orlean": None,
            "criterio": "Consulta central JT API /query; sem upload pelo dashboard. Valores em BRL.",
        },
        "rows": rows,
    }


@lru_cache(maxsize=4)
def cached_data(bucket: int):
    return bundle(read_database())


@app.get("/")
def home(_=Depends(authorize)):
    return FileResponse(ROOT / "static" / "index.html",
                        headers={"Cache-Control": "no-store"})


@app.get("/api/health")
def health():
    return {
        "status": "ok", "indicador": "avaria_extravio_pnr",
        "fonte": "jt-api", "api_configurada": bool(os.getenv("JT_API_KEY")),
        "tabela": TABLE,
    }


@app.get("/api/dados")
def data(_=Depends(authorize)):
    ttl = max(5, int(os.getenv("JT_API_CACHE_SECONDS", "60")))
    result = cached_data(int(time.time() // ttl))
    return result


if __name__ == "__main__":
    import uvicorn
    os.environ.setdefault("APP_ENV", "local")
    host = "127.0.0.1" if not os.getenv("DASH_PASSWORD") else "0.0.0.0"
    uvicorn.run(app, host=host, port=int(os.getenv("PORT", "8000")))
