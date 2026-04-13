.PHONY: dev prod seed test migrate new-migration down clean logs

dev:  ## Start dev environment
	docker compose up --build

prod:  ## Start production environment
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

seed:  ## Seed demo data
	docker compose exec backend python seed_demo.py

test:  ## Run tests
	docker compose exec backend pytest -v

migrate:  ## Run database migrations
	docker compose exec backend alembic upgrade head

new-migration:  ## Create new migration (usage: make new-migration msg="add foo table")
	docker compose exec backend alembic revision --autogenerate -m "$(msg)"

down:  ## Stop all services
	docker compose down

clean:  ## Stop all and remove volumes
	docker compose down -v

logs:  ## Tail all logs
	docker compose logs -f
