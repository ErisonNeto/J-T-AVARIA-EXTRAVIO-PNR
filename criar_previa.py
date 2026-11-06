"""Gera prévia autônoma offline com dados locais. Não subir ao GitHub!"""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
html=(ROOT/'static/index.html').read_text('utf-8')
css=(ROOT/'static/style.css').read_text('utf-8')
js=(ROOT/'static/app.js').read_text('utf-8')
data=(ROOT/'dados/painel.json').read_text('utf-8')
html=html.replace('<link rel="stylesheet" href="/static/style.css?v=3abas-1" />','<style>'+css+'</style>')
html=html.replace('<script defer src="/static/app.js?v=3abas-1"></script>','')
# Evita fechar tag script por conteúdo vindo de campos livres da planilha.
html=html.replace('</body>', '<script>window.__PAINEL_EMBED__='+data.replace('<','\\u003c')+';</script><script>'+js+'</script></body>')
out=ROOT.parent/'JT_AVARIA_EXTRAVIO_PNR_Preview.html'
out.write_text(html,'utf-8')
print(out,round(out.stat().st_size/1024),'KB')