# SIH 2026 — Gen AI Platform for Automated Content Transformation

Backend for NTRO Problem Statement 26154 (SIH 2026).

## Current Stack

| Component | Technology |
|-----------|-----------|
| API      | FastAPI + Uvicorn |
| Validation | Pydantic v2 + pydantic-settings |
| Database | PostgreSQL (asyncpg) |
| ORM     | SQLAlchemy 2.x (async) |
| Migrations | Alembic |
| Containerization | Docker + Docker Compose |

## Prerequisites

- Python 3.12+
- Docker + Docker Compose

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Copy environment template
cp .env.example .env
```

## Running with Docker Compose

```bash
# Start PostgreSQL and the API
docker compose up --build

# Verify PostgreSQL health
docker compose ps
```

The API will be available at `http://localhost:8000`.

## Running locally

```bash
# Start PostgreSQL only (Docker)
docker compose up -d db

# Run Alembic migrations
alembic upgrade head

# Start the API
uvicorn app.main:app --reload
```

## Health Endpoint

```bash
curl http://localhost:8000/health
# => {"status":"ok"}
```

## Running Tests

```bash
pytest
```

## Alembic

Migrations are managed with Alembic and read `DATABASE_URL` from your `.env`:

```bash
# Generate a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1

# Show current revision
alembic current
```