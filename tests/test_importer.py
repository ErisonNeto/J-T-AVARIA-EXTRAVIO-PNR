"""Testes sem dados reais da operação. Executar: python -m unittest discover -s tests -v"""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape
import importar_excel as pipeline


def fake_xlsx(path, rows):
    sheet = ['<?xml version="1.0" encoding="utf-8"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for i, cells in enumerate(rows, 1):
        sheet.append('<row r="%d">'%i)
        for col, val in cells.items():
            if isinstance(val, (float,int)):
                sheet.append('<c r="%s%d"><v>%s</v></c>'%(col,i,val))
            else:
                sheet.append('<c r="%s%d" t="inlineStr"><is><t>%s</t></is></c>'%(col,i,escape(str(val))))
        sheet.append('</row>')
    sheet.append('</sheetData></worksheet>')
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('xl/worksheets/sheet1.xml',''.join(sheet))


class PipelineTests(unittest.TestCase):
    def test_groups_do_not_mix_pnr(self):
        self.assertEqual(pipeline.classify('AVARIA 破损'),'Avaria')
        self.assertEqual(pipeline.classify('EXTRAVIO-遗失'),'Extravio')
        self.assertEqual(pipeline.classify('FORA DO PRAZO SLA CADEIA 超SLA时效延误'),'Extravio')
        self.assertEqual(pipeline.classify('Reivindicações rápidas/投诉理赔'),'PNR')
        self.assertEqual(pipeline.classify('ROUBO/SINISTRO'),'Fora do escopo')

    def test_values_in_ag_are_brl(self):
        self.assertEqual(pipeline.money('1.234,56'),123456)
        self.assertEqual(pipeline.money('99.9'),9990)
        self.assertEqual(pipeline.money('0,01'),1)

    def test_xlsx_with_xls_extension_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / 'entradas'
            inputs.mkdir()
            (root / 'dados').mkdir()
            fake_xlsx(inputs / 'Gestão de colaboradores.xlsx', [
                {'A':'Nome da Base','G':'Responsável da Região'},
                {'A':'F PAA-PA','B':'1001','G':'ORLEAN DA SILVA','H':'Coord A'},
            ])
            fake_xlsx(inputs / 'Minha responsabilidade.xls', [
                {'A':'Número de declaração','B':'Número da Remessa',
                 'D':'Tipo de anomalia primária','AG':'Valor a pagar (yuan)'},
                {'A':'TEST-1','B':'BR001','D':'Reivindicações rápidas/投诉理赔',
                 'E':'Assinado não recebido','AE':'F PAA-PA','AG':'12,50',
                 'G':'Arbitragem finalizada','L':'2026-11-07'},
            ])
            with patch.object(pipeline,'ROOT',root), patch.object(pipeline,'DATA',root/'dados'), patch.object(pipeline,'ENTRADAS',inputs):
                result = pipeline.run_import()
                self.assertEqual(result['qtd_por_tipo'],{'PNR':1})
                self.assertEqual(result['valor_total_centavos'],1250)

    def test_historical_import_and_management(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);inputs=root/'entradas';inputs.mkdir();(root/'dados').mkdir()
            mg=[{'A':'Nome da Base','B':'Código da Base','G':'Responsável da Região'},
                {'A':'F PAA-PA','B':'1001','F':'PA','G':'ORLEAN DA SILVA','H':'Coord Teste','I':'Supervisor Teste'},
                {'A':'F PAB-PA','B':'1002','F':'PA','G':'ORLEAN DA SILVA','H':'Coord Teste','I':'Supervisor Teste'},
                {'A':'F OUT-SP','B':'9000','F':'SP','G':'OUTRA REGIÃO','I':'Outra Pessoa'}]
            fake_xlsx(inputs/'Gestão de colaboradores.xlsx',mg)
            head={'A':'Número da declaração','B':'Número da Remessa','D':'Tipo de anomalia primária',
                  'E':'Tipo secundário','AG':'Valor a pagar (yuan)'}
            rows=[head,
                {'A':'Z1','B':'111','D':'AVARIA 破损','E':'Embalagem','AE':'F PAA-PA','L':'2026-11-01','AG':'10,50'},
                {'A':'Z2','B':'222','D':'EXTRAVIO-遗失','E':'Extrav.','AE':'F PAA-PA','L':'2026-11-02','AG':'12,00'},
                {'A':'Z3','B':'333','D':'FORA DO PRAZO SLA CADEIA 超SLA时效延误','AE':'F PAB-PA','L':'2026-11-03','AG':'25,00'},
                {'A':'Z4','B':'444','D':'Reivindicações rápidas/投诉理赔','E':'Assinado não recebido','AE':'F PAA-PA','L':'2026-11-04','AG':'2,00'},
                {'A':'Z5','B':'555','D':'Reivindicações rápidas/投诉理赔','AE':'F OUT-SP','L':'2026-11-04','AG':'99,00'},
                {'A':'Z6','B':'666','D':'ROUBO/SINISTRO','AE':'F PAA-PA','L':'2026-11-04','AG':'1,00'},
                {'A':'Z7','B':'777','D':'AVARIA 破损','AE':'BASE SEM GESTAO','L':'2026-11-04','AG':'1,00'},
                {'A':'Z8','B':'888','D':'EXTRAVIO-遗失','AE':'F PAA-PA','L':'2026-11-04','AG':'4,00'},
                {'A':'Z8','B':'888','D':'EXTRAVIO-遗失','AE':'F PAB-PA','L':'2026-11-04','AG':'7,00'}]
            fake_xlsx(inputs/'arbitragem_1.xlsx',rows)
            with patch.object(pipeline,'ROOT',root),patch.object(pipeline,'DATA',root/'dados'),patch.object(pipeline,'ENTRADAS',inputs):
                first=pipeline.run_import()
                self.assertEqual(first['qtd_por_tipo'],{'Avaria':1,'Extravio':4,'PNR':1})
                self.assertEqual(first['valor_total_centavos'],6050)
                self.assertEqual(first['sem_correspondencia_global'],1)
                self.assertEqual(first['fora_escopo_orlean']['ROUBO/SINISTRO'],1)
                again=pipeline.run_import()
                self.assertEqual(again['total_ativos'],first['total_ativos'])
                self.assertEqual(again['valor_total_centavos'],first['valor_total_centavos'])
                dataset=json.loads((root/'dados/painel.json').read_text('utf-8'))
                self.assertEqual(len(dataset['rows']),6)
                # Mudança na gestão deve reclassificar o histórico preservado.
                mg[1]['H']='NOVO COORDENADOR'
                fake_xlsx(inputs/'Gestão de colaboradores.xlsx',mg)
                after=pipeline.run_import()
                self.assertEqual(after['qtd_por_tipo'],first['qtd_por_tipo'])
                updated=json.loads((root/'dados/painel.json').read_text('utf-8'))
                self.assertEqual(next(x for x in updated['rows'] if x['remessa']=='111')['coordenador'],'NOVO COORDENADOR')


if __name__=='__main__':
    unittest.main()