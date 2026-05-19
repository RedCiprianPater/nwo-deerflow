.PHONY: help setup install dev test lint format clean docker-start docker-stop build publish

help: ## Show this help message
	@echo "NWO Deer-Flow - Available Commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Run interactive setup wizard
	@echo "Running NWO Deer-Flow setup..."
	@python scripts/setup.py

install: ## Install dependencies
	pip install -e ".[dev,server]"
	@echo "Dependencies installed!"

dev: ## Start development server
	@echo "Starting development server..."
	uvicorn nwo_deerflow.server:app --reload --host 0.0.0.0 --port 8001

serve: ## Start production server
	@echo "Starting production server..."
	uvicorn nwo_deerflow.server:app --host 0.0.0.0 --port 8001

test: ## Run tests
	pytest --cov=nwo_deerflow --cov-report=term-missing

lint: ## Run linting
	ruff check src/
	mypy src/nwo_deerflow/

format: ## Format code
	black src/ tests/
	ruff check --fix src/ tests/

clean: ## Clean build artifacts
	rm -rf build/ dist/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build: clean ## Build package
	python -m build

twine-check: build ## Check package with twine
	twine check dist/*

publish: twine-check ## Publish to PyPI (requires PYPI_API_TOKEN)
	twine upload dist/*

docker-build: ## Build Docker image
	docker build -t nwo-deerflow:latest .

docker-run: ## Run Docker container
	docker run -p 8001:8001 --env-file .env nwo-deerflow:latest

docker-start: docker-build docker-run ## Build and run Docker container

worker-deploy: ## Deploy Cloudflare Worker
	wrangler deploy worker/worker.ts --name nwo-deerflow-tool20

worker-logs: ## Tail Cloudflare Worker logs
	wrangler tail nwo-deerflow-tool20

check: ## Check prerequisites
	@echo "Checking prerequisites..."
	@python --version
	@pip --version
	@which python
	@echo "All checks passed!"

config: ## Show current configuration
	@nwo-deerflow config
