# xbreach ingest

xbreach ingest é o serviço responsável por receber, validar e registrar arquivos
brutos de vazamentos dentro da plataforma xbreach. Ele combina uma API FastAPI,
uma interface operacional para uso interno, persistência em PostgreSQL, Redis
para suporte de infraestrutura e armazenamento local dos arquivos recebidos.

A aplicação foi pensada para manter o fluxo de ingestão rastreável. Cada upload
fica vinculado a uma fonte, a um breach e a um job de processamento, permitindo
acompanhar o histórico, consultar falhas e preservar os metadados necessários
para auditoria.

## O que o projeto entrega

1. Interface web privada com dashboard, listagem de jobs, detalhe de job,
   upload de arquivos e controle de fontes.
2. API autenticada para clientes externos enviarem arquivos de ingestão.
3. Validação de extensão, tamanho, fonte ativa e nome seguro de arquivo.
4. Registro de jobs, erros de ingestão e progresso em banco relacional.
5. Healthcheck com estado da aplicação, PostgreSQL e Redis.
6. Execução local via Docker Compose com migrations aplicadas na inicialização.

## Primeiros passos

Para subir o ambiente completo localmente, use Docker Compose:

```bash
docker compose up --build
```

Depois que os serviços estiverem prontos, acesse:

```text
http://localhost:8000/login
```

As credenciais padrão do ambiente local são:

```text
Email: admin@xbreach.local
Senha: xbreach
```

Esses valores devem ser trocados em qualquer ambiente compartilhado.

## Interface web

A interface web fica protegida por login e foi feita para operação diária. Ela
permite revisar o volume de jobs, acompanhar uploads recentes, filtrar jobs por
status, fonte, data e nome de arquivo, consultar detalhes de processamento e
administrar fontes ativas ou inativas.

Rotas principais:

```text
/dashboard
/jobs
/jobs/{job_id}
/upload
/sources
```

## API para integração

Clientes externos podem obter um token com:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@xbreach.local","password":"xbreach"}'
```

A resposta inclui `access_token`, `token_type` e `expires_in`. Use o token como
Bearer nas chamadas autenticadas:

```bash
curl -X POST http://localhost:8000/api/v1/ingest/upload \
  -H "Authorization: Bearer <access_token>" \
  -F "source_id=2001" \
  -F "breach_name=Example breach" \
  -F "file=@./sample.txt"
```

O endpoint de upload aceita arquivos com extensões permitidas pelo serviço e
retorna o `job_id` criado, além do caminho local onde o arquivo foi armazenado.

## Configuração

A aplicação lê variáveis de ambiente com o prefixo `XBREACH_`. No Docker Compose,
os valores podem vir de um arquivo `.env` ou dos padrões definidos no próprio
`docker-compose.yml`.

Variáveis mais importantes:

```env
XBREACH_ENVIRONMENT=local
XBREACH_DATA_PATH=/data/xbreach
XBREACH_UPLOAD_MAX_FILE_SIZE_BYTES=104857600
XBREACH_LOGIN_EMAIL=admin@xbreach.local
XBREACH_LOGIN_PASSWORD=xbreach
XBREACH_SESSION_SECRET=change-me-in-production-with-32-bytes-minimum
XBREACH_SESSION_MAX_AGE_SECONDS=28800
XBREACH_POSTGRES_HOST=postgres
XBREACH_POSTGRES_PORT=5432
XBREACH_POSTGRES_DB=xbreach
XBREACH_POSTGRES_USER=xbreach
XBREACH_POSTGRES_PASSWORD=xbreach
XBREACH_REDIS_HOST=redis
XBREACH_REDIS_PORT=6379
XBREACH_REDIS_DB=0
```

`XBREACH_SESSION_SECRET` assina os tokens JWT. Em qualquer ambiente real, use um
valor próprio, longo e privado.

## Armazenamento

Uploads locais são gravados abaixo de `XBREACH_DATA_PATH`, seguindo uma estrutura
por data e job:

```text
/data/xbreach/raw/year=YYYY/month=MM/day=DD/{job_id}/
```

Dentro da pasta do job, o serviço mantém o arquivo original normalizado e um
`manifest.json` com metadados do upload.

## Banco de dados

As migrations ficam em `migrations/` e podem ser executadas manualmente com:

```bash
python -m app.infrastructure.migrations
```

No Docker Compose, a API executa as migrations antes de iniciar o Uvicorn.

As principais tabelas são:

```text
sources
breaches
ingestion_jobs
ingestion_job_errors
```

Os identificadores são `BIGINT` e são gerados pela aplicação com o gerador
Snowflake configurado por `XBREACH_APP_ID` e `XBREACH_NODE_ID`.

## Desenvolvimento local sem Docker

Para rodar a aplicação diretamente no Python:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m app.infrastructure.migrations
uvicorn app.main:app --reload
```

A API ficará disponível em:

```text
http://localhost:8000
```

## Healthcheck

```bash
curl http://localhost:8000/health
```

Resposta esperada em um ambiente saudável:

```json
{
  "status": "ok",
  "environment": "local",
  "service": "xbreach-ingest",
  "postgres": "ok",
  "redis": "ok"
}
```

## Testes

```bash
pytest
```

A pipeline de CI instala as dependências de desenvolvimento, executa a suíte de
testes, aplica migrations, sobe a aplicação com Uvicorn e valida o endpoint
`/health`.

## Dicas úteis

1. Clientes externos podem obter um token em `/api/v1/auth/login` e reutilizar o
   `access_token` como Bearer até o tempo definido por
   `XBREACH_SESSION_MAX_AGE_SECONDS`.
2. Antes de enviar arquivos grandes, confirme o valor de
   `XBREACH_UPLOAD_MAX_FILE_SIZE_BYTES`. O padrão atual é 100 MB, mas ele pode
   ser sobrescrito por variável de ambiente.
3. Para uma fonte aparecer no fluxo de upload, ela precisa estar cadastrada e
   ativa. Fontes inativas ou desabilitadas são bloqueadas pela validação do
   serviço.
