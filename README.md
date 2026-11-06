# J&T Express — Avaria, Extravio e PNR

**Painel de consulta do PostgreSQL existente**, usando a **JT Server API v2.0** hospedada no servidor Windows da empresa e publicada pelo Cloudflare Tunnel: https://jt-api.rockettechbr.com.br.

O dashboard **não recebe planilhas e não possui botão de importação**. No Render, o backend acessa a JT API por \`POST /query\`, com a credencial \`X-API-Key\` guardada no ambiente do servidor. O navegador nunca recebe a chave ou executa SQL arbitrário. Os dados não precisam ser enviados ao GitHub ou guardados no disco do Render.

## Indicadores

| Aba | Coluna D (anomalia primária) |
|---|---|
| Avaria | AVARIA 破损 |
| Extravio | EXTRAVIO-遗失 **ou** FORA DO PRAZO SLA CADEIA 超SLA时效延误 |
| PNR | Reivindicações rápidas/投诉理赔 |

**PNR não entra na aba de Extravio.** Extravio convencional e SLA Cadeia ficam na mesma aba, com filtro por origem.

Cada aba tem KPIs de custo, quantidade, bases e S/C envolvidos; evoluções diária/semanal (semana de segunda a domingo e comparações semanais), rankings de bases, coordenadores e supervisores, tabela de anomalias secundárias para auditoria, detalhamento e downloads em CSV.

O filtro R/M permanece Orlean, e os demais filtros são data, UF, base, coordenador, supervisor, S/C, anomalia secundária e busca por remessa/declaração. Os valores da coluna AG já estão em **reais (BRL)** e não recebem conversão cambial.

## Arquitetura real do projeto

\`\`\`text
Usuário (navegador)
     │
     │ HTTPS /api/dados  (autenticação do dashboard)
     ▼
Render · FastAPI app.py
     │
     │ POST https://jt-api.rockettechbr.com.br/query
     │ Header X-API-Key
     │ SQL fixo e paginado
     ▼
JT SERVER · Cloudflare Tunnel · FastAPI
     │
     ▼
VM Windows · PostgreSQL · jt_indicadores
     └── public.jt_arbitragem_ocorrencias
\`\`\`

**Atenção:** o servidor PostgreSQL e a rota genérica \`/query\` já existem. A tabela específica \`jt_arbitragem_ocorrencias\` é a integração deste novo indicador: **não foi verificado que ela exista no banco**. O dashboard exibirá um erro claro até que a tabela seja alimentada. Nenhuma consulta fabricará dados quando a API estiver offline.

### Campos armazenados na tabela

\`chave\`, \`declaracao\`, \`remessa\`, \`primaria\`, \`secundaria\`, \`status\`, \`declarada_em\`, \`fechada_em\`, \`base_responsavel\`, \`base\`, \`codigo_base\`, \`uf\`, \`rm\`, \`coordenador\`, \`supervisor\`, \`tipo\`, \`modalidade\`, \`valor_centavos\`, \`data\`, \`descricao\`, \`comentario_decisao\`, \`comentario_contestacao\`.

A chave estável distingue declaração, remessa, base e ocorrências repetidas para manter UPSERT idempotente. O SQL seleciona somente linhas do R/M Orlean e devolve até 100 mil ocorrências (acima disso, é exibido erro explícito, sem ocultar dados).

As informações de gestão são resolvidas na rotina ETL; **o painel não inventa coordenador nem supervisor** quando uma base não é encontrada. A auditoria de bases sem vínculo precisa ser feita na origem/carga, antes da inclusão no recorte Orlean.

## Executar no PC com VS Code

Na pasta do repositório:

\`\`\`powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
\`\`\`

Copie \`.env.example\` para \`.env\`:

\`\`\`powershell
Copy-Item .env.example .env
\`\`\`

No arquivo \`.env\` local, mantenha \`APP_ENV=local\` e configure a **sua chave existente** \`JT_API_KEY\`. Não coloque essa chave no GitHub.

Inicie:

\`\`\`powershell
.\.venv\Scripts\python.exe app.py
\`\`\`

Abra http://127.0.0.1:8000. Mesmo no modo local, **é obrigatório configurar JT_API_KEY** para o backend consultar a API. Somente o login do próprio dashboard é dispensado em desenvolvimento local.

## Como alimentar o banco (sem upload no dashboard)

A consulta no painel só funciona com a tabela de arbitragens preenchida. O script \`publicar_postgres_via_api.py\` segue a mesma arquitetura de carga dos outros indicadores J&T: no **PC operacional**, lê o histórico local, atualiza o cruzamento com a Gestão e faz UPSERT por meio da **rota \`POST /import\` já existente na JT API**.

Coloque os XLSX da Arbitragem e a planilha Gestão de Colaboradores na pasta local \`entradas/\`. Não inclua os arquivos na publicação do Render e não envie ao GitHub.

Para validar sem enviar nenhum registro:

\`\`\`powershell
.\.venv\Scripts\python.exe publicar_postgres_via_api.py
\`\`\`

Para autorizar a carga no banco:

\`\`\`powershell
.\.venv\Scripts\python.exe publicar_postgres_via_api.py --aplicar
\`\`\`

A rotina reutiliza \`importar_excel.py\` **somente no PC operacional**, como etapa de ETL, nunca como upload por usuários no dashboard. Isso permite integrar o script à rotina diária/agendada de cargas da J&T sem mudar a interface.

A tabela pode ser criada automaticamente pelo endpoint genérico \`/import\` quando a API permitir essa operação; a criação e o primeiro envio precisam ser feitos antes do painel online mostrar as ocorrências. O script valida acesso antes de realizar UPSERT. A base histórica privada \`dados/\` fica excluída do Git.

**Não é possível inferir valores de arbitragem apenas das tabelas SLA, Shipping Time e T0.** É necessário que essas ocorrências tenham sido carregadas na tabela própria. A API já existente transporta e consulta os dados, mas não cria as informações de origem.

## Deploy Render

Conecte o repositório em **New → Blueprint** ou configure:

- **Build command:** \`pip install -r requirements.txt\`
- **Start command:** \`uvicorn app:app --host 0.0.0.0 --port $PORT\`
- **Health check:** \`/api/health\`
- **Environment:** \`APP_ENV=production\`, \`JT_API_URL=https://jt-api.rockettechbr.com.br\`, \`JT_API_KEY\` (secreta), \`DASH_USER\` e \`DASH_PASSWORD\` (secretos).

Não é necessário configurar disco persistente no Render. A tabela fica na VM e existe cache de até 60 segundos por instância para a consulta do dashboard. Se a VM ou o Cloudflare Tunnel estiverem offline, o dashboard informará indisponibilidade em vez de mostrar números inventados.

## Arquivos

\`\`\`text
app.py                        FastAPI, autenticação, consulta paginada à JT API
static/index.html             Três abas, KPIs, filtros, tabelas e auditoria
static/style.css              Visual compatível SLA / Shipping Time
static/app.js                 Filtros, evolução, rankings e exportação CSV
publicar_postgres_via_api.py  ETL do PC → POST /import → banco J&T
importar_excel.py             Leitura/deduplicação da fonte, somente no PC ETL
requirements.txt              Dependências
render.yaml                   Blueprint do Render
.env.example                  Modelo de variáveis sem chaves reais
tests/                        Testes sintéticos sem informações operacionais
\`\`\`

## Validação

\`\`\`powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
\`\`\`

O GitHub Actions executa os testes e confere se não existem planilhas e histórico privados versionados. O dashboard não oferece importação de arquivos XLSX nem registra tokens no JavaScript.

**Privacidade:** este repositório é público. Nunca suba \`.env\`, a chave \`JT_API_KEY\`, arquivos \`.xlsx\` ou diretórios \`entradas/\` e \`dados/\`.
