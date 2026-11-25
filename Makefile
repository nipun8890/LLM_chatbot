.PHONY: up down test logs

up:
	@test -f .env || cp .env.example .env
	docker compose up --build -d
	@echo "Frontend: http://localhost:3000  Backend: http://localhost:8000/health"

down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd backend && pip install -r requirements.txt && python -m pytest -q
