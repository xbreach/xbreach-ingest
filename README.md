# xbreach-ingest

API de ingestao baseada em FastAPI.

## Requisitos

- Python 3.11+
- Docker e Docker Compose

## Estrutura

```text
xbreach-ingest/
├── app/
│   ├── main.py
│   ├── api/
│   ├── core/
│   ├── domain/
│   ├── services/
│   ├── repositories/
│   ├── infrastructure/
│   └── schemas/
├── tests/
├── storage/
├── docker/
├── migrations/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Variaveis de ambiente

A aplicacao carrega variaveis do arquivo `.env` usando o prefixo `XBREACH_`.
Use `.env.example` como referencia.

```env
XBREACH_APP_NAME=xbreach-ingest
XBREACH_APP_VERSION=0.1.0
XBREACH_ENVIRONMENT=local
XBREACH_LOG_LEVEL=INFO
XBREACH_DATA_PATH=/data/xbreach
XBREACH_APP_ID=1
XBREACH_NODE_ID=1
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

`XBREACH_LOGIN_EMAIL` e `XBREACH_LOGIN_PASSWORD` definem o usuario unico de
acesso para a interface web e para a API. Troque `XBREACH_SESSION_SECRET` em
ambientes compartilhados ou de producao, pois ela assina os tokens JWT.

## Autenticacao

O login web em `/login` grava um cookie `HttpOnly` com JWT. Esse mesmo cookie
autoriza chamadas para a API feitas pelo navegador.

Clientes externos podem obter um token com:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@xbreach.local","password":"xbreach"}'
```

Use o `access_token` retornado nas chamadas API:

```bash
curl http://localhost:8000/api/v1/ingest/upload \
  -H "Authorization: Bearer <access_token>"
```

## Executar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

A API ficara disponivel em `http://localhost:8000`.

## Healthcheck

```bash
curl http://localhost:8000/health
```

Resposta esperada:

```json
{
  "status": "ok",
  "environment": "local",
  "service": "xbreach-ingest",
  "postgres": "ok",
  "redis": "ok"
}
```

## Docker Compose

```bash
docker compose up --build
```

O Docker Compose usa o `.env` automaticamente quando o arquivo existir e aplica
valores padrao quando ele nao existir.

O Compose sobe tres servicos na network interna `xbreach-internal`:

- `api`: aplicacao FastAPI exposta em `localhost:8000`, com arquivos em `/data/xbreach`
- `postgres`: PostgreSQL 16 com dados persistidos em `/data/xbreach/postgres`
- `redis`: Redis 7 com AOF persistido em `/data/xbreach/redis`

Uploads locais sao salvos em `/data/xbreach/raw/year=YYYY/month=MM/day=DD/{job_id}/`
com o arquivo `original.<ext>` e o `manifest.json`.

## Banco de dados

As migrations ficam em `migrations/` e sao aplicadas com:

```bash
python -m app.infrastructure.migrations
```

No Docker Compose, a API executa as migrations antes de iniciar o Uvicorn.

A primeira migration cria:

- `sources`
- `breaches`
- `ingestion_jobs`
- `ingestion_job_errors`

Os IDs das tabelas sao `BIGINT` e devem ser gerados pela aplicacao com o
snowflake comum. O snowflake carrega `XBREACH_APP_ID` e `XBREACH_NODE_ID`; o
`APP_ID` identifica o tipo de aplicacao que inseriu o dado. Status de sources e
jobs sao padronizados por constraints no PostgreSQL.

## Testes

```bash
pytest
```

## CI

O workflow de CI instala as dependencias de desenvolvimento, executa `pytest`,
sobe a aplicacao com Uvicorn e valida se `GET /health` responde com
`{"status":"ok"}`.
