"""Verifica que o evolutivo oferece detalhes acessíveis nos pontos."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ChartPointTests(unittest.TestCase):
    def test_both_metrics_in_tooltip(self):
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("chart-tooltip-row", js)
        self.assertIn("n(now.count)", js)
        self.assertIn("money(now.value)", js)
        self.assertIn("data-chart-point", js)
        self.assertIn("pointerenter", js)
        self.assertIn("focus',()=>showPoint(index)", js)
        self.assertIn("event.key==='Enter'", js)
        self.assertIn("event.key==='Escape'", js)
        self.assertIn("dates.length<=12 && current[i]>0", js)
        self.assertIn("chartMetric==='count'?n(current[i])", js)

    def test_tooltip_style_and_cache_busting(self):
        css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn(".chart-tooltip[hidden]{display:none}", css)
        self.assertIn(".chart-hit-point{fill:transparent;pointer-events:all}", css)
        self.assertIn("Evolução por data de fechamento do ticket (coluna AC). Passe o mouse ou toque", html)
        self.assertIn("v=3abas-status-fechamento-7", html)


if __name__ == "__main__":
    unittest.main()
