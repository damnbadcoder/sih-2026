# SIH 2026 — Gen AI Platform for Automated Content Transformation

**SIH Team: Firewalls**

Backend for NTRO Problem Statement 26154 (SIH 2026).

## Current Stack

| Component | Technology |
|-----------|-----------|
| API | FastAPI + Uvicorn |
| Validation | Pydantic v2 + pydantic-settings |
| Database | PostgreSQL (asyncpg) |
| ORM | SQLAlchemy 2.x (async) |
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