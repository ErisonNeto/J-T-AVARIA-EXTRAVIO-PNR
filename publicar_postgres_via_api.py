"""Alimenta a tabela de Arbitragem no PostgreSQL da VM pela JT API.

Este é o ETL do PC operacional, NÃO uma funcionalidade do dashboard Render.
Sem --aplicar faz apenas validação, sem escrever no servidor.
Lê relatórios e Gestão localmente usando o importador histórico existente.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv

from importar_excel import DATA, ROOT, run_import

load_dotenv(ROOT / ".env", override=False)
API_URL = os.getenv("JT_API_URL", "https://jt-api.rockettechbr.com.br").strip().rstrip("/")
KEY = os.getenv("JT_API_KEY", "").strip()
TABLE = "jt_arbitragem_ocorrencias"
FIELDS = (
    "chave", "declaracao", "remessa", "primaria", "secundaria", "status",
    "declarada_em", "fechada_em", "base_responsavel", "base", "codigo_base",
    "uf", "rm", "coordenador", "supervisor", "tipo", "modalidade",
    "valor_centavos", "data", "descricao", "comentario_decisao",
    "comentario_contestacao",
)


def call(session: httpx.Client, endpoint: str, payload: dict):
    for attempt in range(3):
        try:
            result = session.post(
                API_URL + endpoint,
                headers={"X-API-Key": KEY},
                json=payload,
                timeout=httpx.Timeout(120.0, connect=15.0),
            )
        except httpx.RequestError as exc:
            if attempt == 2:
                raise RuntimeError("Sem conexão com JT API. Confira a VM e o Cloudflare Tunnel.") from exc
            time.sleep(2 * (attempt + 1))
            continue
        if result.status_code == 200:
            return result.json()
        if result.status_code in (408, 429, 500, 502, 503, 504) and attempt < 2:
            time.sleep(2 * (attempt + 1))
            continue
        raise RuntimeError(
            f"JT API {endpoint}: HTTP {result.status_code}. "
            "Verifique a chave e as permissões; o corpo da resposta não é exibido por segurança."
        )
    raise RuntimeError("Tentativas da JT API esgotadas.")


def list_rows(result):
    if isinstance(result, dict):
        for k in ("rows", "data", "result", "resultado", "registros"):
            if isinstance(result.get(k), list):
                records = result[k]
                cols = result.get("colunas") or ["qtd"]
                return [dict(zip(cols, r)) if isinstance(r, list) else r for r in records]
    if isinstance(result, list):
        return result
    raise RuntimeError("Formato inesperado de consulta da JT API.")


def count(session: httpx.Client):
    result = call(session, "/query", {
        "sql": ("SELECT COUNT(*) AS qtd FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = %s"),
        "params": [TABLE],
    })
    rows = list_rows(result)
    first = rows[0] if rows else {"qtd": 0}
    return int(first.get("qtd", 0))


def selected_row(item):
    out = {field: item.get(field) for field in FIELDS}
    out["chave"] = item["_key"]
    out["valor_centavos"] = int(out["valor_centavos"] or 0)
    for f in ("data", "declarada_em", "fechada_em"):
        out[f] = out[f] or None
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Publica Avaria, Extravio e PNR via JT API /import no PostgreSQL da VM"
    )
    parser.add_argument("--aplicar", action="store_true",
                        help="autoriza o envio de UPSERT para a JT API")
    parser.add_argument("--lote", type=int, default=300)
    args = parser.parse_args()
    if not 20 <= args.lote <= 1000:
        parser.error("--lote precisa estar entre 20 e 1000")
    if not KEY or not API_URL.startswith("https://"):
        parser.error("Configure JT_API_KEY e JT_API_URL HTTPS no .env local ou variáveis de ambiente")

    # Consolidação histórica, deduplicação por declaração/remessa/base e Gestão atual.
    summary = run_import()
    bundle = json.loads((DATA / "painel.json").read_text(encoding="utf-8"))
    source = [selected_row(row) for row in bundle["rows"]]
    counts = summary.get("qtd_por_tipo") or {}
    total = sum(int(row["valor_centavos"]) for row in source)
    print(f"Tabela: {TABLE} | Registros Orlean: {len(source):,} | Valor: R$ {total/100:,.2f}")
    print("Indicadores:", counts)

    with httpx.Client() as sess:
        if not list_rows(call(sess, "/query", {"sql": "SELECT 1 AS ok", "params": []})):
            raise RuntimeError("JT API não conseguiu consultar PostgreSQL.")
        exists = bool(count(sess))
        print("JT API acessível. Tabela de destino:", "existente" if exists else "a criar")
        if not args.aplicar:
            print("VALIDAÇÃO concluída. Nada foi enviado à API. Use --aplicar para publicar.")
            return
        done = 0
        for start in range(0, len(source), args.lote):
            batch = source[start:start + args.lote]
            if not batch:
                continue
            result = call(sess, "/import", {
                "tabela": TABLE,
                "chave": ["chave"],
                "registros": batch,
                "criar_tabela": not exists,
                "adicionar_colunas": False,
            })
            exists = True
            done += len(batch)
            print(f"  Enviado {done:,}/{len(source):,} · UPSERT", flush=True)
        if not source:
            print("Nenhuma ocorrência Orlean para publicar.")
            return
        response = call(sess, "/query", {
            "sql": f"SELECT COUNT(*) AS qtd FROM public.{TABLE} "
                   "WHERE POSITION('ORLEAN' IN UPPER(COALESCE(rm,''))) > 0",
            "params": [],
        })
        records = list_rows(response)
        banco = int(records[0]["qtd"]) if records else 0
        print(f"Conferência: {len(source):,} registros de origem; {banco:,} no banco.")
        if banco < len(source):
            raise RuntimeError(
                "Banco tem menos registros do que o processamento local; confira os lotes."
            )
        print("PUBLICAÇÃO CONCLUÍDA. Dados no PostgreSQL; dashboard lê pela JT API /query.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError) as exc:
        print("ERRO:", str(exc), file=sys.stderr)
        sys.exit(1)
