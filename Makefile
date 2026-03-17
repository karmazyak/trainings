.PHONY: up down migrate ingest backend bot logs

up:
	docker-compose up -d
	@echo "Waiting for PostgreSQL..."
	@sleep 3
	. .venv/bin/activate && alembic upgrade head
	@echo "✓ DB ready"

down:
	docker-compose down

migrate:
	. .venv/bin/activate && alembic upgrade head

ingest:
	curl -s -X POST http://localhost:8000/documents/ingest-folder | python3 -m json.tool

backend:
	. .venv/bin/activate && uvicorn app.main:app --reload --port 8000

bot:
	. .venv/bin/activate && python -m tg_bot

logs:
	docker-compose logs -f
