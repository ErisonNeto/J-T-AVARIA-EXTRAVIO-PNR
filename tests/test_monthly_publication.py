"""Testes sintéticos para a substituição mensal estrita pela coluna AC."""
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import publicar_mes_fechamento as mensal


def fake_xlsx(path, rows):
    content = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>',
    ]
    for i, row in enumerate(rows, 1):
        content.append(f'<row r="{i}">')
        for col, value in row.items():
            content.append(
                f'<c r="{col}{i}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
            )
        content.append('</row>')
    content.append('</sheetData></worksheet>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", "".join(content))


class MonthlyClosureTests(unittest.TestCase):
    def test_month_uses_closure_not_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            gestao = folder / "Gestão de colaboradores.xlsx"
            excel = folder / "arbitragem_mes.xlsx"
            fake_xlsx(gestao, [
                {"A": "Nome da Base", "G": "Responsável da Região"},
                {"A": "F GP-PA", "B": "500", "G": "ORLEAN DA SILVA", "H": "Coordenador"},
                {"A": "F EX-SP", "B": "900", "G": "OUTRO RM"},
            ])
            head = {"A": "Número de declaração", "B": "Número da Remessa",
                    "AG": "Valor a pagar (yuan)"}
            fake_xlsx(excel, [
                head,
                {"A": "OUT-01", "B": "BR01", "D": "AVARIA 破损",
                 "L": "2020-10-27", "AC": "2020-11-06", "AE": "F GP-PA",
                 "G": "Arbitragem finalizada", "AG": "13.10"},
                {"A": "SEM-AC", "B": "BR02", "D": "EXTRAVIO-遗失",
                 "L": "2020-11-09", "AE": "F GP-PA",
                 "G": "Processo encerrado", "AG": "99.00"},
                {"A": "OUT-MES", "B": "BR03", "D": "EXTRAVIO-遗失",
                 "L": "2020-11-02", "AC": "2020-12-02", "AE": "F GP-PA",
                 "G": "Processo encerrado", "AG": "23.00"},
                {"A": "OUT-REG", "B": "BR04", "D": "AVARIA 破损",
                 "L": "2020-11-05", "AC": "2020-11-06", "AE": "F EX-SP",
                 "G": "Processo encerrado", "AG": "33.00"},
                {"A": "REV-01", "B": "BR05", "D": "Reivindicações rápidas/投诉理赔",
                 "L": "2020-11-04", "AC": "2020-11-09", "AE": "F GP-PA",
                 "G": "Apelação no andamento", "AG": "7.00"},
            ])
            rows, info = mensal.carregar_snapshot(
                excel, gestao, "2020-11", "2020-11-30"
            )
            self.assertEqual({r["declaracao"] for r in rows}, {"OUT-01", "REV-01"})
            self.assertEqual(info["linhas_arquivo"], 5)
            self.assertEqual(info["sem_ac"], 1)
            self.assertEqual(info["fechamentos_orlean"], 2)
            self.assertEqual(info["finalizados_orlean"], 1)
            self.assertEqual(info["auditoria_orlean"], 1)
            self.assertEqual(info["valor_centavos"], 2010)
            self.assertEqual(rows[0]["data"], rows[0]["fechada_em"])

    def test_reject_month_with_no_ac(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            gestao = folder / "Gestão de colaboradores.xlsx"
            excel = folder / "sem_fechamentos.xlsx"
            fake_xlsx(gestao, [
                {"A": "Nome da Base", "G": "Responsável da Região"},
                {"A": "F GP-PA", "G": "ORLEAN DA SILVA"},
            ])
            fake_xlsx(excel, [
                {"A": "Declaração", "B": "Número da Remessa", "AG": "Valor a pagar (yuan)"},
                {"A": "D", "B": "R", "L": "2020-11-06",
                 "D": "AVARIA 破损", "AE": "F GP-PA", "AG": "100"},
            ])
            with self.assertRaisesRegex(ValueError, "não contém fechamentos AC"):
                mensal.carregar_snapshot(excel, gestao, "2020-11", "2020-11-30")


if __name__ == "__main__":
    unittest.main()
