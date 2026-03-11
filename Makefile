.PHONY: infra backend frontend dev

infra:
	docker compose up -d

backend:
	cd backend && \
		python3.13 -m venv .venv || true
	cd backend && . .venv/bin/activate && \
		pip install -r requirements.txt && \
		python -m uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm install && npm run dev

dev: infra
	@echo "Run backend and frontend in separate terminals:" 
	@echo "  make backend"
	@echo "  make frontend"
