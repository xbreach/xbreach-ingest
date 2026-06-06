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
XBREACH_POSTGRES_HOST=postgres
XBREACH_POSTGRES_PORT=5432
XBREACH_POSTGRES_DB=xbreach
XBREACH_POSTGRES_USER=xbreach
XBREACH_POSTGRES_PASSWORD=xbreach
XBREACH_REDIS_HOST=redis
XBREACH_REDIS_PORT=6379
XBREACH_REDIS_DB=0
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

- `api`: aplicacao FastAPI exposta em `localhost:8000`
- `postgres`: PostgreSQL 16 com dados persistidos em `/data/xbreach/postgres`
- `redis`: Redis 7 com AOF persistido em `/data/xbreach/redis`

Arquivos da aplicacao que precisarem ser persistidos devem usar
`/data/xbreach/storage`.

## Testes

```bash
pytest
```

## CI

O workflow de CI instala as dependencias de desenvolvimento, executa `pytest`,
sobe a aplicacao com Uvicorn e valida se `GET /health` responde com
`{"status":"ok"}`.
