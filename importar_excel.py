"""Importação histórica de Avaria/Extravio/PNR J&T.

Uso: colocar Gestão de colaboradores.xlsx e um ou mais relatórios de
'Exportar formulário de declaração de arbitragem' na pasta do projeto
(ou em entradas/) e executar: python importar_excel.py

Implementado só com a biblioteca padrão do Python. Não acessa Supabase,
Google Drive ou a API local, nem converte o valor AG para yuan.
"""
from __future__ import annotations
import argparse
import datetime as dt
import gzip
import json
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STORAGE = Path(__import__('os').environ.get('JT_STORAGE', str(ROOT))).resolve()
DATA = STORAGE / 'dados'
ENTRADAS = STORAGE / 'entradas'
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
GER_COLS = {'A', 'B', 'F', 'G', 'H', 'I', 'O'}
ARB_COLS = {'A', 'B', 'D', 'E', 'G', 'L', 'AC', 'AE', 'AG', 'AB', 'AK', 'AL'}

def norm(text):
    s = unicodedata.normalize('NFKD', str(text or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c)).upper()
    return re.sub(r'[^A-Z0-9]', '', s)

def money(s):
    if s is None or str(s).strip() == '':
        return 0
    s = str(s).strip().replace('R$', '').replace(' ', '')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return int((Decimal(s) * 100).quantize(Decimal('1')))
    except InvalidOperation:
        raise ValueError(f'Valor AG inválido: {s!r}')

def date(s):
    if not s:
        return ''
    text = str(s).strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}', text):
        return text[:10]
    if re.match(r'^\d{2}/\d{2}/\d{4}', text):
        d, m, y = text[:10].split('/')
        return f'{y}-{m}-{d}'
    try:
        val = float(text)
        if 20000 < val < 100000:
            return (dt.datetime(1899, 12, 30) + dt.timedelta(days=val)).date().isoformat()
    except ValueError:
        pass
    return ''

def xml_rows(path, keep):
    """Lê somente colunas necessárias, em fluxo, evitando dependências pesadas."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            with z.open('xl/sharedStrings.xml') as f:
                for _, el in ET.iterparse(f, events=['end']):
                    if el.tag == NS + 'si':
                        shared.append(''.join(t.text or '' for t in el.iter(NS + 't')))
                        el.clear()
        sheet = 'xl/worksheets/sheet1.xml'
        if sheet not in z.namelist():
            raise ValueError(f'Planilha inicial ausente em {path.name}')
        with z.open(sheet) as f:
            for _, el in ET.iterparse(f, events=['end']):
                if el.tag != NS + 'row':
                    continue
                out = {}
                for c in el.findall(NS + 'c'):
                    ref = c.get('r', '')
                    m = re.match(r'[A-Z]+', ref)
                    if not m or m.group(0) not in keep:
                        continue
                    col = m.group(0)
                    v = c.find(NS + 'v')
                    raw = v.text if v is not None else None
                    t = c.get('t')
                    if t == 's' and raw is not None:
                        raw = shared[int(raw)]
                    elif t == 'inlineStr':
                        inline = c.find(NS + 'is')
                        raw = ''.join(x.text or '' for x in inline.iter(NS + 't')) if inline is not None else ''
                    if raw is not None:
                        out[col] = raw.strip() if isinstance(raw, str) else raw
                yield out
                el.clear()

def classify(raw):
    x = norm(raw)
    if x.startswith('AVARIA'):
        return 'Avaria'
    if x.startswith('EXTRAVIO') or x.startswith('FORADOPRAZOSLACADEIA'):
        return 'Extravio'
    if x.startswith('REIVINDICACOESRAPIDAS'):
        return 'PNR'
    return 'Fora do escopo'

def subtype(raw):
    x = norm(raw)
    if x.startswith('AVARIA'):
        return 'Avaria'
    if x.startswith('EXTRAVIO'):
        return 'Extravio convencional'
    if x.startswith('FORADOPRAZOSLACADEIA'):
        return 'SLA Cadeia'
    if x.startswith('REIVINDICACOESRAPIDAS'):
        return 'PNR / Reivindicação rápida'
    return 'Outros'

def txt(s):
    return str(s or '').strip()

def parse_management(p):
    stream = xml_rows(p, GER_COLS)
    header = next(stream, {})
    if norm(header.get('A')) != 'NOMEDABASE' or norm(header.get('G')) != 'RESPONSAVELDAREGIAO':
        raise ValueError(f'{p.name}: formato da Gestão de Colaboradores inesperado')
    out = []
    for r in stream:
        if not r.get('A'):
            continue
        out.append({'base': txt(r.get('A')), 'codigo': txt(r.get('B')), 'uf': txt(r.get('F')),
                    'rm': txt(r.get('G')), 'coordenador': txt(r.get('H')),
                    'supervisor': txt(r.get('I')), 'situacao': txt(r.get('O'))})
    return out

def parse_arbitration(p):
    stream = xml_rows(p, ARB_COLS)
    header = next(stream, {})
    if norm(header.get('B')) != 'NUMERODAREMESSA' or norm(header.get('AG')) != 'VALORAPAGARYUAN':
        raise ValueError(f'{p.name}: colunas B e AG não correspondem ao arquivo de arbitragem')
    for r in stream:
        if not r.get('A') or not r.get('B'):
            continue
        yield {
            'declaracao': txt(r.get('A')), 'remessa': txt(r.get('B')),
            'primaria': txt(r.get('D')), 'secundaria': txt(r.get('E')),
            'status': txt(r.get('G')), 'declarada_em': date(r.get('L')),
            'fechada_em': date(r.get('AC')), 'base_responsavel': txt(r.get('AE')),
            'valor_centavos': money(r.get('AG')),
            'descricao': txt(r.get('AB')), 'comentario_decisao': txt(r.get('AK')),
            'comentario_contestacao': txt(r.get('AL')),
        }

def write_json(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    pending = p.with_name(p.name + '.tmp')
    pending.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    pending.replace(p)

def load_history(p):
    if not p.exists():
        return {}
    with gzip.open(p, 'rt', encoding='utf-8') as f:
        rows = json.load(f)
    return {r['_key']: r for r in rows}

def combine(gestao, raw, source, import_count, dup_count):
    idx = defaultdict(list)
    for m in gestao:
        idx[norm(m['base'])].append(m)
    consolidated = {}
    ambiguos = []
    for k, items in idx.items():
        # Duplicatas idênticas da gestão não devem gerar falso 'sem vínculo'.
        signatures = {(norm(x['rm']), norm(x['codigo']), norm(x['coordenador']), norm(x['supervisor'])) for x in items}
        if len(signatures) == 1:
            consolidated[k] = items[0]
        else:
            # Uma duplicata com gestões divergentes fica retida para conferência.
            ambiguos.append(k)
    valid_orlean = {norm(k): v for k, v in consolidated.items() if 'ORLEAN' in norm(v['rm'])}
    mapped = []
    missing = Counter()
    missing_examples = {}
    excluded = Counter()
    for item in raw.values():
        key = norm(item['base_responsavel'])
        matched = consolidated.get(key)
        if matched is None:
            missing[item['base_responsavel'] or '(base não informada)'] += 1
            if item['base_responsavel'] not in missing_examples:
                missing_examples[item['base_responsavel']] = item['declaracao']
            continue
        if 'ORLEAN' not in norm(matched['rm']):
            continue
        group = classify(item['primaria'])
        if group == 'Fora do escopo':
            excluded[item['primaria'] or '(sem tipo)'] += 1
            continue
        r = dict(item)
        r.update({'tipo': group, 'modalidade': subtype(item['primaria']), 'base': matched['base'],
                  'codigo_base': matched['codigo'], 'uf': matched['uf'], 'rm': matched['rm'],
                  'coordenador': matched['coordenador'], 'supervisor': matched['supervisor'],
                  'sc': matched['coordenador'] or matched['supervisor'] or 'Sem S/C cadastrado'})
        r['data'] = item['fechada_em'] or item['declarada_em']
        mapped.append(r)
    mapped.sort(key=lambda r: (r['data'], r['declaracao']), reverse=True)
    all_dates = [r['data'] for r in mapped if r['data']]
    orlean_mg = {norm(m['base']) for m in gestao if 'ORLEAN' in norm(m['rm'])}
    stats = Counter(r['tipo'] for r in mapped)
    totals = {k: sum(r['valor_centavos'] for r in mapped if r['tipo'] == k) for k in ['Avaria', 'Extravio', 'PNR']}
    summary = {
        'origem': source, 'gerado_em': dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).isoformat(timespec='seconds'),
        'rm': 'ORLEAN DA SILVA DO NASCIMENTO', 'moeda': 'BRL',
        'coluna_data': 'AC - Data de fechamento; fallback L - Data de declaração',
        'total_na_exportacao': len(raw), 'total_ativos': len(mapped),
        'qtd_por_tipo': dict(stats), 'valor_por_tipo_centavos': totals,
        'valor_total_centavos': sum(r['valor_centavos'] for r in mapped),
        'datas': {'min': min(all_dates) if all_dates else '', 'max': max(all_dates) if all_dates else ''},
        'bases_gestao_orlean': len(orlean_mg),
        'bases_ofensoras': len({r['base'] for r in mapped}),
        'sem_correspondencia_global': sum(missing.values()),
        'sem_correspondencia_detalhes': [{'base': k, 'qtd': v, 'exemplo': missing_examples.get(k, '')}
                                           for k, v in missing.most_common(150)],
        'ambiguidade_na_gestao': [m['base'] for m in gestao if norm(m['base']) in ambiguos][:30],
        'fora_escopo_orlean': dict(excluded),
        'importados_nesta_execucao': import_count,
        'duplicidades_sobrescritas': dup_count,
        'criterio': 'Apenas bases vinculadas ao R/M Orlean na Gestão. Valores AG já estão em reais.',
    }
    return {'meta': summary, 'rows': mapped}

def run_import(zerar_historico=False):
    DATA.mkdir(exist_ok=True)
    files = sorted([*ROOT.glob('*.xlsx'), *ENTRADAS.glob('*.xlsx')],
                   key=lambda p: (p.stat().st_mtime, p.name))
    sources = []
    mg_files = [p for p in files if 'gest' in norm(p.name).lower()]
    if mg_files:
        management_path = mg_files[-1]
        gestao = parse_management(management_path)
        write_json(DATA / 'gestao.json', gestao)
        print(f'Gestão: {management_path.name} | {len(gestao)} registros')
    elif (DATA / 'gestao.json').exists():
        gestao = json.loads((DATA / 'gestao.json').read_text(encoding='utf-8'))
        management_path = None
        print('Gestão: utilizando versão salva anteriormente')
    else:
        print('ERRO: coloque a Gestão de colaboradores.xlsx na pasta ou em entradas/.')
        sys.exit(2)
    history_path = DATA / 'historico.json.gz'
    archive = {} if zerar_historico else load_history(history_path)
    imports = 0; dup = 0
    arbitration_files = [p for p in files if p not in mg_files]
    for path in arbitration_files:
        this = 0; duplicates = 0
        occur = Counter()
        try:
            for row in parse_arbitration(path):
                # Uma declaração pode responsabilizar DUAS bases distintas.
                # Não é correto deduplicar apenas pelo número de declaração/remessa.
                signature = (row['declaracao'], row['remessa'], norm(row['base_responsavel']))
                ordinal = occur[signature]
                occur[signature] += 1
                row['_key'] = json.dumps([*signature, ordinal], ensure_ascii=False, separators=(',', ':'))
                if row['_key'] in archive:
                    duplicates += 1
                archive[row['_key']] = row
                this += 1
        except (ValueError, zipfile.BadZipFile) as exc:
            print(f'Arquivo ignorado: {path.name}: {exc}')
            continue
        imports += this; dup += duplicates
        sources.append(path.name)
        print(f'Arbitragem: {path.name} | {this} registros | {duplicates} já existentes')
    if not archive:
        print('ERRO: nenhum registro de arbitragem importado.')
        sys.exit(2)
    bundle = combine(gestao, archive, sources or ['Histórico salvo'], imports, dup)
    temp_hist = history_path.with_name(history_path.name + '.tmp')
    with gzip.open(temp_hist, 'wt', encoding='utf-8', compresslevel=6) as f:
        json.dump(list(archive.values()), f, ensure_ascii=False, separators=(',', ':'))
    temp_hist.replace(history_path)
    write_json(DATA / 'painel.json', bundle)
    m = bundle['meta']
    print('\n' + '=' * 64)
    print(f"Total histórico: {m['total_na_exportacao']:,} | Orlean no escopo: {m['total_ativos']:,}")
    for k in ['Avaria', 'Extravio', 'PNR']:
        print(f"{k:10} {m['qtd_por_tipo'].get(k,0):6,} | R$ {m['valor_por_tipo_centavos'][k]/100:,.2f}")
    print(f"TOTAL R$ {m['valor_total_centavos']/100:,.2f} | Bases: {m['bases_ofensoras']}")
    print(f"Sem correspondência com a Gestão (todos os R/M): {m['sem_correspondencia_global']:,}")
    print('Arquivos gerados: dados/painel.json, dados/gestao.json, dados/historico.json.gz')
    print('Execute: python app.py')
    return m

def main():
    parser = argparse.ArgumentParser(description='Importar Avaria, Extravio e PNR da J&T')
    parser.add_argument('--zerar-historico', action='store_true', help='descartar importações anteriores')
    args = parser.parse_args()
    run_import(zerar_historico=args.zerar_historico)

if __name__ == '__main__':
    main()