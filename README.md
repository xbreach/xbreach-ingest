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
  "service": "xbreach-ingest"
}
```

## Docker Compose

```bash
docker compose up --build
```

O Docker Compose usa o `.env` automaticamente quando o arquivo existir e aplica
valores padrao quando ele nao existir.

## Testes

```bash
pytest
```

## CI

O workflow de CI instala as dependencias de desenvolvimento, executa `pytest`,
sobe a aplicacao com Uvicorn e valida se `GET /health` responde com
`{"status":"ok"}`.
