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

    def test_responsive_grid_for_each_tab(self):
        css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns:repeat(3,minmax(0,1fr))", css)
        self.assertIn(".filters-grid.is-extravio{grid-template-columns:repeat(4,minmax(0,1fr))}", css)
        self.assertIn(".filters-grid.is-extravio .filter-card:last-child{grid-column:span 2}", css)
        self.assertIn("max-width:700px", css)
        self.assertIn("classList.toggle('is-extravio',active==='Extravio')", js)

    def test_finalized_kpis_and_separate_audit(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="emConferencia"', html)
        self.assertIn('id="reviewCount"', html)
        self.assertIn('id="reviewValue"', html)
        self.assertIn('id="downloadReview"', html)
        self.assertIn("filtered=scope.filter(isFinal)", js)
        self.assertIn("underReview=scope.filter(r=>!isFinal(r))", js)
        self.assertIn("function currentContextRows(){return filtersWithoutDate(allForTab).filter(isFinal)}", js)
        self.assertIn("renderReview();renderDetails()", js)
        self.assertIn("function exportReview()", js)
        self.assertIn("Data fechamento (AC)", js)

    def test_default_period_is_calendar_week_monday_sunday(self):
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("const currentWeek = () => {const start=monday(localISO(new Date()));return {start,end:shiftDay(start,6)};};", js)
        self.assertIn("renderQuality();period('week');", js)
        self.assertIn("period('week');});", js)
        self.assertIn("if(mode==='week')", js)
        self.assertIn('data-period="week" type="button" class="active"', html)
        self.assertIn("Esta semana (seg–dom)", html)
        self.assertIn("Abertura padrão: semana atual, de segunda a domingo", html)

    def test_regional_is_fixed_on_server(self):
        backend = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("POSITION('ORLEAN' IN UPPER(COALESCE(rm, '')))", backend)


if __name__ == "__main__":
    unittest.main()
