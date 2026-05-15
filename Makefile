.PHONY: build up down logs shell test clean lint

DOCKER_COMPOSE = docker compose -f docker/docker-compose.yml
SHELL := /bin/bash

build:
	$(DOCKER_COMPOSE) build

up:
	$(DOCKER_COMPOSE) up -d

down:
	$(DOCKER_COMPOSE) down

logs:
	$(DOCKER_COMPOSE) logs -f

shell:
	$(DOCKER_COMPOSE) exec dr-agent /bin/bash

test:
	$(DOCKER_COMPOSE) run --rm dr-agent python -m pytest tests/ -v

lint:
	$(DOCKER_COMPOSE) run --rm dr-agent python -m ruff check src/ tests/

typecheck:
	$(DOCKER_COMPOSE) run --rm dr-agent python -m mypy src/

clean:
	$(DOCKER_COMPOSE) down -v
	rm -rf artifacts/*.json

setup:
	@echo "--- Prerequisites ---"
	@echo "1. Create Gitea admin token: Gitea UI -> Settings -> Applications -> Generate Token"
	@echo "2. Set env vars:"
	@echo "   GITLAB_TOKEN=<your-gitlab-pat>"
	@echo "   GITEA_TOKEN=<your-gitea-admin-token>"
	@echo "   WEBHOOK_URL=<your-webhook-endpoint>"
	@echo "   GITEA_DB_PASSWORD=<db-password>"
	@echo ""
	@echo "Then run: make build && make up"
	@echo "Then run: make setup-mirrors"

setup-mirrors:
	$(DOCKER_COMPOSE) run --rm dr-agent python scripts/setup-mirrors.py

check:
	$(DOCKER_COMPOSE) exec dr-agent python src/dr_agent.py --check

summary:
	$(DOCKER_COMPOSE) exec dr-agent python src/dr_agent.py --summary

restore:
	@echo "Usage: make restore REPO=my-project DEST=/path/to/restore"
	$(DOCKER_COMPOSE) run --rm dr-agent python scripts/restore-from-gitea.py --repo $(REPO) --dest $(DEST)
