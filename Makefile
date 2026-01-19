.PHONY: run run-network lint format

# Development server (localhost only)
run:
	uvicorn main:app --reload --port 8501

# Development server accessible on LAN
run-network:
	uvicorn main:app --reload --host 0.0.0.0 --port 8501

# Production server
serve:
	uvicorn main:app --host 0.0.0.0 --port 8501

# Linting
lint:
	ruff check .

format:
	ruff format .
