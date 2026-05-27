# Bookmark API

A lightweight FastAPI + SQLite + SQLAlchemy REST API for bookmark and category management.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run

```bash
uvicorn app.main:app --reload
```

API documentation is available at:

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## Test

```bash
pytest
```

## Project Structure

```text
app/
  api/        REST route registration
  core/       application settings
  db/         database engine and session setup
  models/     SQLAlchemy models
  schemas/    Pydantic schemas
  services/   business logic
  main.py     FastAPI application factory
```
