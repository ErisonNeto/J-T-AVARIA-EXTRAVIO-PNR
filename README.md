# J&T Express — Avaria • Extravio • PNR

Dashboard operacional interno, no padrão visual dos indicadores J&T **SLA e Shipping Time**. Um único projeto com três abas independentes e os mesmos filtros de gestão.

## Indicadores e regras

| Aba | `D` — anomalia primária |
| --- | --- |
| **Avaria** | `AVARIA 破损` |
| **Extravio** | `EXTRAVIO-遗失` e `FORA DO PRAZO SLA CADEIA 超SLA时效延误` |
| **PNR** | `Reivindicações rápidas/投诉理赔` |

**PNR não entra mais na soma de Extravio.** SLA Cadeia continua em Extravio, mas pode ser filtrado separadamente em *Origem do extravio*. Outros tipos de origem ficam fora dessas três abas.

Campos do relatório: `B` remessa; `D` anomalia primária; `E` secundária; `AE` base responsável; `AG` valor a pagar em **reais** (apesar do rótulo yuan); `L` data da declaração; `AC` fechamento; `AB`, `AK`, `AL` descrições de auditoria.

O vínculo com a **Gestão de Colaboradores** usa o nome da base em `AE`, com normalização de caixa, espaços e acentos, buscando R/M, coordenador, supervisor, UF e código. Apenas bases reconhecidas do **R/M Orlean** integram os KPIs. Bases sem correspondência são apontadas na conferência global, **não atribuídas a ninguém**. Gestões conflitantes não são adivinhadas.

**Critério de contagem:** cada linha válida de responsabilização (declaração + remessa + base + ordinal de ocorrências repetidas na planilha) conta uma ocorrência. A mesma remessa pode responsabilizar mais de uma base; não fazer `drop_duplicates` só pelo número da remessa. Totais dos rankings de **Coordenador** e **Supervisor** não devem ser somados entre cargos, pois uma ocorrência pode ser atribuída aos dois. Cada valor vem em centavos para impedir erro de ponto flutuante.

## Funcionalidades

- Três abas independentes, com filtros de data, UF, S/C (coordenador **ou** supervisor), coordenador, supervisor, base, secundária e busca de remessa/declaração.
- Filtro específico **Extravio convencional / SLA Cadeia** na aba de Extravio.
- 4 KPIs: valor, ocorrências, bases ofensoras e responsáveis envolvidos; custo médio e comparações anteriores.
- Evolução diária ou semanal (semanas sempre **segunda a domingo**); quantidade ou valor; referência deslocada de 7 dias.
- Rankings de bases e responsáveis, ordenáveis por quantidade/custo, completos e exportáveis.
- Auditoria das anomalias secundárias com colunas originais D/E; nenhum julgamento automático de coerência.
- Remessas detalhadas, com descrição/decisão/contestação, paginação e **CSV por aba e filtros** com campos vazios para avaliação do S/C.
- Importador idempotente: novos relatórios atualizam o histórico por identidade da responsabilização; nova Gestão reaplica os vínculos ao histórico inteiro.
- Importação de XLSX pela interface autenticada ou pelo comando Python, sem bibliotecas de leitura de planilha.
- Autenticação HTTP Basic nas rotas que servem dados e recebem planilhas; HTML e JS não contêm informações privadas no GitHub.

## Executar no Windows

Requer Python 3.11 ou superior. No PowerShell:

```powershell
cd "C:\caminho\J-T-AVARIA-EXTRAVIO-PNR"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Abra `http://127.0.0.1:8000`. No modo `python app.py`, se **nenhuma senha** estiver configurada, o servidor fica acessível **apenas neste computador**, para desenvolvimento local.

### Importar dados (interface)

1. Expanda **Importar novas planilhas XLSX** no fim do dashboard.
2. Selecione a planilha de **Gestão de colaboradores** e um ou mais arquivos de **Exportar formulário de declaração de arbitragem**. A primeira aba de cada planilha precisa seguir o modelo enviado.
3. Clique em **Importar e atualizar dashboard**. Os arquivos e o histórico são salvos na pasta `entradas/` e `dados/`.
4. Cargas posteriores podem conter somente relatórios de arbitragem. Quando a Gestão mudar, importe a nova versão para atualizar os vínculos históricos.

### Importar pelo terminal

Copie os arquivos `.xlsx` para `entradas/` e execute:

```powershell
python importar_excel.py
```

O importador aceita **vários arquivos de dias diferentes**, preserva registros já existentes e atualiza o painel. Para descartar o histórico existente e reconstruir tudo apenas com os arquivos disponíveis, execute `python importar_excel.py --zerar-historico` **somente se tiver backup**.

**Arquivos produzidos:** `dados/historico.json.gz`, `dados/gestao.json` e `dados/painel.json` — **não enviar ao GitHub**.

## Configurar no Render

O repositório contém `render.yaml` para `Blueprint`, ou configure um Web Service Python com:

- **Build:** `pip install -r requirements.txt`
- **Start:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
- **Health check:** `/api/health`
- **Variáveis de ambiente:** `APP_ENV=production`, `DASH_USER` e `DASH_PASSWORD` fortes.

**Dados não vêm pré-carregados do GitHub público.** Depois de publicar, abra o painel com usuário/senha e importe Gestão + Arbitragem pelo formulário. No **Render Free**, o disco é **efêmero**: planilhas e dados importados podem desaparecer após reinício/redeploy. Para persistência, crie um serviço com **Persistent Disk**, configure a montagem (ex.: `/var/data`) e `JT_STORAGE=/var/data/jt`. Faça backup do diretório `JT_STORAGE` periodicamente. Se estiver usando um banco PostgreSQL em uma VM, **esta versão não se conecta automaticamente a ele** — essa integração seria separada.

Para produção, não publique planilhas, CSVs, screenshots reais ou o HTML de prévia no GitHub. O `.gitignore` protege os arquivos mais comuns, mas verifique o `git status` antes de cada push. O repositório público não substitui autenticação, cuidado com os downloads e gestão de acessos.

## Comandos de conferência

```powershell
python -m unittest discover -s tests -v
python importar_excel.py
python criar_previa.py
```

`criar_previa.py` gera um HTML autônomo **com todos os dados reais embutidos**, exclusivo para uso local. **Não publique esse arquivo.**

## Estrutura

```text
app.py                   FastAPI + Basic Auth + importação pelo painel
importar_excel.py        Parser XLSX em streaming, histórico, vínculo gestão
static/index.html        Tela 3 abas
static/style.css         Padrão visual SLA / Shipping Time
static/app.js            Filtros, gráficos SVG, rankings, CSV e navegação
render.yaml              Serviço Render
requirements.txt         Dependências do servidor
.env.example             Exemplo de variáveis sem senhas reais
criar_previa.py          Gera HTML offline local (dados não vão ao GitHub)
tests/test_importer.py   Testes sintéticos de classificação e reconciliação
entradas/                XLSX privados (ignorados no Git)
dados/                   Histórico privado (ignorado no Git)
```