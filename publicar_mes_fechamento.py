"""Publicação mensal completa de arbitragens, baseada SOMENTE no fechamento (AC).

Cada envio fica numa versão própria. A versão ativa do mês é alterada apenas
DEPOIS da conferência integral do snapshot, sem DELETE ou TRUNCATE.
Não use este comando com um export filtrado pela declaração (L).
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

import httpx

from importar_excel import combine, norm, parse_arbitration, parse_management
from publicar_postgres_via_api import API_URL, KEY, call, count, list_rows, selected_row

REPO = Path(__file__).resolve().parent
DETALHE = "jt_arbitragem_mensal_detalhe"
ATIVO = "jt_arbitragem_mensal_ativo"
TIPOS = ("Avaria", "Extravio", "PNR")
FINALIZADOS = {"PROCESSOENCERRADO", "ARBITRAGEMFINALIZADA"}


def consultar(session: httpx.Client, sql: str, params=None) -> list[dict]:
    return list_rows(call(session, "/query", {"sql": sql, "params": params or []}))


def tabela_existe(session: httpx.Client, tabela: str) -> bool:
    rows = consultar(
        session,
        "SELECT COUNT(*) AS qtd FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s",
        [tabela],
    )
    return bool(rows and int(rows[0]["qtd"]))


def mes_automatico() -> str:
    """Mês operacional de D-1 no horário de Belém (UTC-3)."""
    ontem = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).date() - dt.timedelta(days=1)
    return ontem.strftime("%Y-%m")


def chave_exportacao_jms(path: Path):
    """Reconhece os nomes numéricos longos do JMS sem usar L como referência."""
    if not path.is_file() or path.suffix.lower() not in (".xls", ".xlsx"):
        return None
    nome = norm(path.stem)
    marcador = "EXPORTARFORMULARIODEDECLARACAODEARBITRAGEM"
    indice = nome.find(marcador)
    if indice < 0:
        return None
    sequencia = nome[indice + len(marcador):]
    data_exportacao = None
    if len(sequencia) >= 14 and sequencia[:14].isdigit():
        try:
            data_exportacao = dt.datetime.strptime(sequencia[:14], "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return data_exportacao


def localizar_exportacao_jms(pastas=None) -> Path:
    """Busca a exportação mais recente em entradas/, raiz e Downloads.

    O timestamp do NOME significa a hora de EXPORTAÇÃO, não o mês de fechamento.
    Uma exportação incompleta não fica 'completa' só porque o nome é reconhecido.
    """
    diretorios = list(pastas) if pastas is not None else [
        REPO / "entradas", REPO, Path.home() / "Downloads",
    ]
    encontrados = []
    for prioridade, diretorio in enumerate(diretorios):
        if not diretorio.is_dir():
            continue
        for arquivo in diretorio.iterdir():
            exportacao = chave_exportacao_jms(arquivo)
            if exportacao is None and "EXPORTARFORMULARIODEDECLARACAODEARBITRAGEM" not in norm(arquivo.stem):
                continue
            if not arquivo.is_file() or arquivo.suffix.lower() not in (".xls", ".xlsx"):
                continue
            if arquivo.name.startswith("~$"):
                continue
            # Timestamp interno é preferível ao horário de cópia do arquivo.
            carimbo = exportacao.timestamp() if exportacao else arquivo.stat().st_mtime
            encontrados.append((carimbo, -prioridade, arquivo.stat().st_mtime, arquivo))
    if not encontrados:
        raise ValueError(
            "Nenhuma exportação do JMS encontrada. Coloque o arquivo "
            "'...Exportar formulário de declaração de arbitragem...xlsx' "
            "em entradas/, na raiz do projeto ou em Downloads; "
            "ou informe --arquivo com o caminho completo."
        )
    encontrados.sort(key=lambda item: item[:3], reverse=True)
    escolhido = encontrados[0][3]
    print(f"EXPORTAÇÃO JMS RECONHECIDA: {escolhido.name}")
    print(f"LOCAL: {escolhido.parent} | candidatos encontrados: {len(encontrados)}")
    if len(encontrados) > 1:
        print("Foi selecionada a exportação mais recente; use --arquivo para escolher outra.")
    if not zipfile.is_zipfile(escolhido):
        raise ValueError(
            f"Arquivo selecionado '{escolhido.name}' não é um Excel OOXML válido. "
            "Converta .xls binário para .xlsx, sem escolher outro arquivo às cegas."
        )
    return escolhido


def mes_valido(value: str) -> str:
    try:
        parsed = dt.date.fromisoformat(value + "-01")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use o formato AAAA-MM.") from exc
    if parsed.strftime("%Y-%m") != value:
        raise argparse.ArgumentTypeError("Use o formato AAAA-MM.")
    return value


def limite_mes(mes: str) -> str:
    y, m = map(int, mes.split("-"))
    hoje = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).date()
    ontem = hoje - dt.timedelta(days=1)
    ultimo = dt.date(y, m, calendar.monthrange(y, m)[1])
    if dt.date(y, m, 1) > ontem:
        raise ValueError("O mês informado ainda não possui dias concluídos até D-1.")
    return min(ontem, ultimo).isoformat()


def carregar_snapshot(arquivo: Path, gestao: Path, mes: str, limite: str):
    if not arquivo.is_file() or not zipfile.is_zipfile(arquivo):
        raise ValueError("O relatório precisa existir e ser Excel OOXML (.xlsx ou .xls com ZIP interno).")
    if not gestao.is_file() or not zipfile.is_zipfile(gestao):
        raise ValueError("A Gestão de Colaboradores não foi localizada em formato válido.")
    gestores = parse_management(gestao)
    if not gestores:
        raise ValueError("Gestão de Colaboradores sem linhas válidas.")
    selecionados = {}
    total = 0
    sem_fechamento = 0
    outros_meses = Counter()
    posteriores = 0
    dias = Counter()
    status = Counter()
    ordinal = Counter()
    for row in parse_arbitration(arquivo):
        total += 1
        ac = row["fechada_em"]
        if not ac:
            sem_fechamento += 1
            continue
        if ac[:7] != mes:
            outros_meses[ac[:7]] += 1
            continue
        if ac > limite:
            posteriores += 1
            continue
        signature = (row["declaracao"], row["remessa"], norm(row["base_responsavel"]))
        numero = ordinal[signature]
        ordinal[signature] += 1
        row["_key"] = json.dumps([*signature, numero], ensure_ascii=False, separators=(",", ":"))
        selecionados[row["_key"]] = row
        dias[ac] += 1
        status[row["status"] or "(vazio)"] += 1
    if posteriores:
        raise ValueError(
            f"{posteriores} fechamento(s) depois de D-1 ({limite}). "
            "Confira a exportação antes de substituir o mês."
        )
    if not selecionados:
        raise ValueError(
            f"O arquivo não contém fechamentos AC para {mes} até {limite}; "
            "substituição bloqueada."
        )
    dataset = combine(
        gestores, selecionados, [arquivo.name], len(selecionados), 0
    )
    linhas = [selected_row(r) for r in dataset["rows"]]
    if not linhas:
        raise ValueError(
            "Nenhum registro do Orlean com fechamento AC neste mês. "
            "Substituição bloqueada para evitar zerar o painel."
        )
    if any(not r["fechada_em"] or r["fechada_em"][:7] != mes for r in linhas):
        raise RuntimeError("Inconsistência: há linhas fora do mês de fechamento.")
    resumo = {
        "linhas_arquivo": total,
        "sem_ac": sem_fechamento,
        "fechamentos_mes_todas_regionais": len(selecionados),
        "fechamentos_orlean": len(linhas),
        "dias_com_fechamento": len(dias),
        "primeiro_fechamento": min(dias),
        "ultimo_fechamento": max(dias),
        "outros_meses": dict(sorted(outros_meses.items())),
        "status_mes_todas_regionais": dict(status),
        "tipos_orlean": dict(Counter(r["tipo"] for r in linhas)),
        "finalizados_orlean": sum(norm(r["status"]) in FINALIZADOS for r in linhas),
        "auditoria_orlean": sum(norm(r["status"]) not in FINALIZADOS for r in linhas),
        "valor_centavos": sum(r["valor_centavos"] for r in linhas),
    }
    return linhas, resumo


def gerar_versao(arquivo: Path, gestao: Path, mes: str) -> str:
    h = hashlib.sha256(mes.encode("ascii"))
    for path in (arquivo, gestao):
        with path.open("rb") as f:
            for bloco in iter(lambda: f.read(1024 * 1024), b""):
                h.update(bloco)
    return h.hexdigest()[:32]


def main():
    p = argparse.ArgumentParser(
        description="Substituição mensal atômica (por versão) de Avaria/Extravio/PNR, usando AC."
    )
    p.add_argument("--arquivo", type=Path, help="Opcional: caminho específico; por padrão detecta a exportação mais recente do JMS")
    p.add_argument("--gestao", type=Path, default=REPO / "Gestão de colaboradores.xlsx")
    p.add_argument("--mes", type=mes_valido, default=mes_automatico(), help="Mês de FECHAMENTO AC (AAAA-MM); padrão: mês de D-1 em Belém")
    p.add_argument("--lote", type=int, default=200)
    p.add_argument("--aplicar", action="store_true", help="Envia snapshot e ativa depois da conferência")
    p.add_argument("--confirmar-mes", type=mes_valido, help="Confirmar explicitamente o mês a substituir")
    p.add_argument("--relatorio-mensal-completo", action="store_true",
                   help="Confirma que o JMS exportou TODO o mês pelo FECHAMENTO AC, e não só um dia")
    p.add_argument("--aceitar-reducao", action="store_true",
                   help="Aceita queda superior a 30%% ante a versão mensal ativa")
    p.add_argument("--aceitar-cobertura-curta", action="store_true",
                   help="Autoriza excepcionalmente relatório com poucos dias de fechamento, após conferência")
    args = p.parse_args()
    if args.arquivo is None:
        args.arquivo = localizar_exportacao_jms()
    else:
        args.arquivo = args.arquivo.expanduser().resolve()
        print(f"EXPORTAÇÃO INFORMADA: {args.arquivo.name} | pasta: {args.arquivo.parent}")
    if not 20 <= args.lote <= 1000:
        p.error("O lote deve ficar entre 20 e 1000.")
    limite = limite_mes(args.mes)
    linhas, resumo = carregar_snapshot(args.arquivo, args.gestao, args.mes, limite)
    versao = gerar_versao(args.arquivo, args.gestao, args.mes)
    print(f"MÊS DE FINALIZAÇÃO (AC): {args.mes} | até {limite}")
    print(f"ARQUIVO: {args.arquivo.name}")
    for chave, valor in resumo.items():
        print(f"  {chave}: {valor}")
    print(f"VERSÃO: {versao}")
    print("Atenção: um arquivo filtrado pela declaração L NÃO é um snapshot mensal completo.")
    primeiro_dia = dt.date.fromisoformat(args.mes + "-01")
    ultimo_dia = dt.date.fromisoformat(limite)
    dias_periodo = (ultimo_dia - primeiro_dia).days + 1
    suspeito = (
        dias_periodo >= 10 and (
            resumo["dias_com_fechamento"] < 5
            or dt.date.fromisoformat(resumo["primeiro_fechamento"]) > primeiro_dia + dt.timedelta(days=7)
            or dt.date.fromisoformat(resumo["ultimo_fechamento"]) < ultimo_dia - dt.timedelta(days=7)
        )
    )
    if suspeito:
        print("ALERTA: cobertura de datas AC parece curta para um relatório mensal completo.")
    if not args.aplicar:
        print("AUDITORIA LOCAL CONCLUÍDA. Nada foi enviado ao PostgreSQL.")
        return
    if suspeito and not args.aceitar_cobertura_curta:
        raise RuntimeError(
            "Cobertura curta de datas de fechamento AC. A substituição foi bloqueada. "
            "Baixe a exportação mensal completa; em casos excepcionais confirme "
            "manualmente com --aceitar-cobertura-curta."
        )
    if args.confirmar_mes != args.mes or not args.relatorio_mensal_completo:
        raise RuntimeError(
            "Publicação bloqueada. Confirme o mês com --confirmar-mes AAAA-MM "
            "e confirme exportação COMPLETA por AC com --relatorio-mensal-completo."
        )
    if not KEY or not API_URL.startswith("https://"):
        raise RuntimeError("JT_API_KEY/JT_API_URL inválidos no .env. Não envie a chave no chat.")
    with httpx.Client() as session:
        if not consultar(session, "SELECT 1 AS ok"):
            raise RuntimeError("JT API indisponível.")
        manifesto_existe = tabela_existe(session, ATIVO)
        detalhes_existem = tabela_existe(session, DETALHE)
        ativo = None
        if manifesto_existe:
            existentes = consultar(
                session, f"SELECT mes, carga_id, total FROM public.{ATIVO} WHERE mes = %s",
                [args.mes],
            )
            ativo = existentes[0] if existentes else None
        if ativo and ativo["carga_id"] == versao:
            print("MÊS JÁ ATIVO com esta versão; nenhum reenvio necessário.")
            return
        if ativo and int(resumo["fechamentos_orlean"]) < int(ativo["total"]) * 0.7 and not args.aceitar_reducao:
            raise RuntimeError(
                f"Nova carga com {len(linhas)} ocorrências, contra {ativo['total']} "
                "na versão ativa. Redução >30% bloqueada; confira a cobertura "
                "mensal e use --aceitar-reducao somente se estiver correta."
            )
        pacote = []
        for item in linhas:
            row = dict(item)
            row["mes"] = args.mes
            row["carga_id"] = versao
            row["chave"] = hashlib.sha256(
                (versao + "|" + str(item["chave"])).encode("utf-8")
            ).hexdigest()
            pacote.append(row)
        print(f"ENVIANDO {len(pacote)} linhas para a versão {versao} (ainda NÃO ativa).")
        for inicio in range(0, len(pacote), args.lote):
            bloco = pacote[inicio:inicio + args.lote]
            call(session, "/import", {
                "tabela": DETALHE,
                "chave": ["chave"],
                "registros": bloco,
                "criar_tabela": not detalhes_existem,
                "adicionar_colunas": False,
            })
            detalhes_existem = True
            print(f"  Pré-carga: {inicio + len(bloco):,}/{len(pacote):,}", flush=True)
        contagem = consultar(
            session,
            f"SELECT COUNT(*) AS qtd, COALESCE(SUM(valor_centavos), 0) AS valor "
            f"FROM public.{DETALHE} WHERE mes = %s AND carga_id = %s",
            [args.mes, versao],
        )
        if not contagem:
            raise RuntimeError("Falha na leitura de conferência no PostgreSQL.")
        n = int(contagem[0]["qtd"])
        valor = int(contagem[0]["valor"])
        if n != len(pacote) or valor != resumo["valor_centavos"]:
            raise RuntimeError(
                f"Validação falhou: {n} linhas e {valor} centavos no PostgreSQL; "
                f"esperado {len(pacote)} e {resumo['valor_centavos']}. "
                "A versão anterior permanece ativa."
            )
        print("Conferência aprovada. Ativando a nova versão mensal.")
        call(session, "/import", {
            "tabela": ATIVO,
            "chave": ["mes"],
            "registros": [{
                "mes": args.mes,
                "carga_id": versao,
                "total": len(pacote),
                "valor_centavos": valor,
                "atualizado_em": dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).isoformat(timespec="seconds"),
            }],
            "criar_tabela": not manifesto_existe,
            "adicionar_colunas": False,
        })
        final = consultar(
            session, f"SELECT mes, carga_id, total FROM public.{ATIVO} WHERE mes = %s",
            [args.mes],
        )
        if not final or final[0]["carga_id"] != versao:
            raise RuntimeError("Manifesto não confirmou ativação. Investigue antes de reenviar.")
        print(
            f"PUBLICAÇÃO MENSAL CONCLUÍDA. {args.mes}: {len(pacote)} fechamentos Orlean. "
            "Demais meses preservados. Render usa a versão ativa."
        )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, zipfile.BadZipFile) as exc:
        print("ERRO:", str(exc), file=sys.stderr)
        sys.exit(1)
