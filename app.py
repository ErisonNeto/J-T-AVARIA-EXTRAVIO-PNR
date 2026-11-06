"""J&T | Avaria, Extravio e PNR — aplicação protegida para uso interno.

Produção: DASH_USER e DASH_PASSWORD obrigatórios. Dados nunca precisam ser
publicados no GitHub; admin envia planilhas pelo painel ou importa no servidor.
"""
from __future__ import annotations

import hmac
import os
import threading
import uuid
import zipfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

from importar_excel import DATA, ENTRADAS, run_import

ROOT = Path(__file__).resolve().parent
app = FastAPI(title='J&T | Avaria • Extravio • PNR', docs_url=None, redoc_url=None)
security = HTTPBasic(auto_error=False)
import_lock = threading.Lock()
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


def authorize(credentials: HTTPBasicCredentials | None = Depends(security)):
    user = os.environ.get('DASH_USER', '')
    password = os.environ.get('DASH_PASSWORD', '')
    local = os.environ.get('APP_ENV', 'production').lower() == 'local'
    if not user and not password and local:
        return True
    if not user or not password:
        raise HTTPException(503, 'Configure DASH_USER e DASH_PASSWORD no ambiente de produção.')
    if not credentials or not (hmac.compare_digest(credentials.username, user)
                               and hmac.compare_digest(credentials.password, password)):
        raise HTTPException(401, 'Credenciais inválidas.',
                            headers={'WWW-Authenticate': 'Basic realm="J&T Indicadores"'})
    return True


@app.get('/')
def home(_=Depends(authorize)):
    return FileResponse(ROOT / 'static' / 'index.html', headers={'Cache-Control': 'no-store'})


@app.get('/api/health')
def health():
    return {'status': 'ok', 'indicador': 'avaria_extravio_pnr',
            'dados_carregados': (DATA / 'painel.json').exists()}


@app.get('/api/dados')
def data(_=Depends(authorize)):
    path = DATA / 'painel.json'
    if not path.is_file():
        raise HTTPException(404, 'Ainda não existem dados. Importe Gestão e Arbitragem no painel.')
    return FileResponse(path, media_type='application/json',
                        headers={'Cache-Control': 'no-store, max-age=0', 'X-Content-Type-Options': 'nosniff'})


@app.post('/api/importar')
def upload(arquivos: list[UploadFile] = File(...), _=Depends(authorize)):
    """Recebe XLSX, atualiza histórico e refaz a correspondência com a gestão."""
    if not 1 <= len(arquivos) <= 12:
        raise HTTPException(400, 'Selecione de 1 a 12 arquivos XLSX por importação.')
    if not import_lock.acquire(blocking=False):
        raise HTTPException(409, 'Já existe uma importação em andamento.')
    try:
        ENTRADAS.mkdir(parents=True, exist_ok=True)
        saved = []
        for upload_file in arquivos:
            name = (upload_file.filename or '').replace('\\', '/').split('/')[-1].strip()
            if not name.lower().endswith('.xlsx') or len(name) > 190 or name.startswith('~$'):
                raise HTTPException(400, f'Arquivo não permitido: {name[:70]}')
            tmp = ENTRADAS / f'.upload_{uuid.uuid4().hex}.tmp'
            size = 0
            try:
                with tmp.open('wb') as f:
                    while chunk := upload_file.file.read(1024 * 1024):
                        size += len(chunk)
                        if size > 25 * 1024 * 1024:
                            raise HTTPException(413, f'{name}: arquivo acima do limite de 25 MB.')
                        f.write(chunk)
                if not zipfile.is_zipfile(tmp):
                    raise HTTPException(400, f'{name}: não é um XLSX válido.')
                with zipfile.ZipFile(tmp) as z:
                    if sum(e.file_size for e in z.infolist()) > 150 * 1024 * 1024 or len(z.infolist()) > 3000:
                        raise HTTPException(413, f'{name}: conteúdo do XLSX muito grande.')
                    if 'xl/worksheets/sheet1.xml' not in z.namelist():
                        raise HTTPException(400, f'{name}: primeira aba não localizada.')
                tmp.replace(ENTRADAS / name)
                saved.append(name)
            finally:
                tmp.unlink(missing_ok=True)
        try:
            result = run_import()
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            raise HTTPException(422, f'Falha ao interpretar os arquivos: {exc}') from exc
        return {'status': 'ok', 'arquivos': saved,
                'total': result['total_ativos'], 'por_tipo': result['qtd_por_tipo'],
                'total_reais': result['valor_total_centavos'] / 100}
    finally:
        import_lock.release()


if __name__ == '__main__':
    import uvicorn
    os.environ.setdefault('APP_ENV', 'local')
    # No modo sem senha, a interface fica acessível apenas neste computador.
    host = '127.0.0.1' if not os.getenv('DASH_PASSWORD') else '0.0.0.0'
    uvicorn.run(app, host=host, port=int(os.getenv('PORT', '8000')))