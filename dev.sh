#!/bin/sh
# Local (non-Docker) dev bring-up: Postgres in Docker (small, no build needed),
# backend + frontend run natively on the Mac via uv/npm — uses mlx-whisper
# (Apple Silicon ASR) and a local Ollama for note drafting instead of the
# faster-whisper/CUDA-torch path baked into the Docker image, so there's no
# multi-GB image build for local dev. Run this yourself in a terminal (it
# starts long-lived processes) rather than backgrounding it blindly.
set -e
cd "$(dirname "$0")"

OLLAMA_MODEL="qwen2.5:7b-instruct-q4_K_M"

echo "==> Ollama"
if ! command -v ollama >/dev/null 2>&1; then
  echo "    not installed, installing via brew..."
  brew install ollama
fi
if ! curl -fsS http://localhost:11434 >/dev/null 2>&1; then
  echo "    not running, starting..."
  brew services start ollama
  for i in $(seq 1 20); do
    curl -fsS http://localhost:11434 >/dev/null 2>&1 && break
    sleep 1
  done
fi
if ! ollama list | grep -q "$OLLAMA_MODEL"; then
  echo "    pulling $OLLAMA_MODEL (first run only, several GB)..."
  ollama pull "$OLLAMA_MODEL"
fi

echo "==> Postgres (Docker, db service only)"
docker compose up -d db

echo "==> Backend deps (uv sync --extra local-mac)"
(cd backend && uv sync --extra local-mac)

echo "==> DB migrations + seed (idempotent, safe on every run)"
(cd backend && uv run --env-file ../.env alembic upgrade head && uv run --env-file ../.env python -m clin_doc.seed)

echo "==> Starting backend on :8000 (Ctrl+C to stop both)"
# --env-file: each engine's pydantic-settings resolves its own "env_file=.env"
# relative to CWD (backend/), so without this the root .env is silently never
# loaded and everything falls back to class defaults (e.g. auto-medical-coder
# defaults MODEL to anthropic/claude-sonnet-4-5 with no key -> 503s).
(cd backend && uv run --env-file ../.env uvicorn clin_doc.main:app --reload --port 8000) &
BACKEND_PID=$!

echo "==> Frontend deps (npm install)"
(cd frontend && npm install)

trap "kill $BACKEND_PID 2>/dev/null" EXIT

echo "==> Starting frontend on :3000"
(cd frontend && npm run dev)
