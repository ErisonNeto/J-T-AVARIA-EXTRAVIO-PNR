"""Garante que o painel Orlean tenha somente o filtro S/C consolidado."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FilterLayoutTests(unittest.TestCase):
    def test_no_duplicate_management_filters(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="sc"', html)
        self.assertNotIn('id="uf"', html)
        self.assertNotIn("$('uf')", js)
        self.assertIn("r.uf", js)  # UF permanece nos rankings/CSV
        self.assertNotIn('id="coordenador"', html)
        self.assertNotIn('id="supervisor"', html)
        self.assertNotIn('class="filter-card static-filter"', html)
        self.assertNotIn("$('coordenador')", js)
        self.assertNotIn("$('supervisor')", js)
        self.assertIn("managers(r).includes($('sc').value)", js)

    def test_roles_stay_visible_in_reports(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Coordenadores e supervisores", html)
        self.assertIn("Coordenador / Supervisor", html)

    def test_regional_is_fixed_on_server(self):
        backend = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("POSITION('ORLEAN' IN UPPER(COALESCE(rm, '')))", backend)


if __name__ == "__main__":
    unittest.main()
