# Deployment (Phase 5)

How the Clinical Documentation Assistant is containerized, configured, and
deployed. Covers the one non-obvious constraint (the backend build context),
the ASR strategy execution, the S3 index bake, and the managed-Postgres path.

## 1. The build-context constraint (read this first)

The backend declares the four upstream engines — `ai-ambient-scribe`,
`phi-deidentifier`, `auto-medical-coder`, `fhir-clinical-summarizer` — as
**local path deps** pointing at sibling repos that live **outside** this
workspace, one level up in the parent folder (any name works — see below).
Docker can only `COPY` files inside the build context, so the backend image
must be built with the context set to the **parent** directory:

```
any-folder-name-you-want/              ← build context for the backend
├── clinical-documentation-assistant/  ← this repo (compose lives here)
│   ├── infra/Dockerfile.backend
│   └── docker-compose.yml
├── ai-ambient-scribe/                 ← path dep
├── phi-deidentifier/                  ← path dep
├── auto-medical-coder/                ← path dep
└── fhir-clinical-summarizer/          ← path dep
```

`docker-compose.yml` encodes this: the `backend` service uses
`context: ..` + `dockerfile: clinical-documentation-assistant/infra/Dockerfile.backend`.
The frontend image's context is just `./frontend` (no sibling deps).

## 2. Local full-stack run

```bash
# 1. Secrets — copy the template and fill in the cloud LLM key.
cp .env.example .env      # set API_KEY at minimum; S3/S1/S2 all read it

# 2. Build + start (from the workspace root). compose reads .env automatically.
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend:  http://localhost:8000  (health: `/health`)
- Postgres: localhost:5432 (clin/clin/clin_doc)

The backend container's entrypoint runs Alembic migrations, seeds the demo
clinician (`clinician` / `changeme`) and a synthetic demo patient (wired to the
bundled R4 fixture), then starts uvicorn. The frontend proxies `/api/*` and
`/health` to the backend over the compose network.

## 3. Environment & secrets

| Variable | Used by | Notes |
|---|---|---|
| `API_KEY` | S1, S2, S3 (shared) | Cloud LLM key (LiteLLM). **Required** for codes/summary/referral. Whatever key matches the provider in `LLM_MODEL`/`MODEL` below. |
| `LLM_MODEL` | S1 / clinical_core, B1 referral | LiteLLM `"<provider>/<model>"` string — not Claude-locked (e.g. `openai/gpt-5`, `gemini/gemini-2.5-pro`, `ollama/llama3`). Default `anthropic/claude-opus-4-8`. |
| `MODEL` | S3 coder | Same LiteLLM `"<provider>/<model>"` convention as `LLM_MODEL`. Bumped off the stale §11 default to `anthropic/claude-sonnet-5`. |
| `PHI_HASH_KEY` | S2 | Only for `hash`/`surrogate`; `mask` (the default) needs none. |
| `PHI_REGIONS` | S2 | Phone-region rules (`NZ,AU`). |
| `DATABASE_URL` | backend | `postgresql+psycopg://…`. Defaults to SQLite for bare local dev. |
| `JWT_SECRET` | backend | Override in any real deployment. |
| `ASR_BACKEND` | backend | `faster_whisper` (cloud) or `mlx_whisper` (local Apple-Silicon dev). |
| `RATE_LIMIT_ENABLED` / `RATE_LIMIT_PER_MINUTE` | backend | Public-demo throttle; off by default. |
| `CATALOGUE_PATH` / `CHROMA_DIR` | S3 | Pinned to absolute paths in the image so the build bake and runtime agree. |

Never commit `.env`. The Dockerfile never copies it — secrets enter via the
compose `environment` block / env file at runtime.

## 4. ASR strategy (Phase 0 Decision B, executed)

M1's `MlxWhisperTranscriber` is Apple-Silicon-only (`mlx-whisper`/Metal) and
won't run on a Linux PaaS container. The cloud demo swaps to `faster-whisper`
(CTranslate2, CPU-friendly, cross-platform, **same Whisper weights**) —
implemented as a B1 adapter, **not** a rewrite of M1:

- `clin_doc/asr.py::FasterWhisperTranscriber` conforms to M1's `Transcriber`
  ABC and mirrors `MlxWhisperTranscriber`'s output mapping (`TranscriptSeg` +
  `WordTiming` with `TimeSpan`), so the downstream `DialogueExtractor` and
  note generator see identical shapes regardless of which transcriber ran.
- `clin_doc/deps.py::get_scribe` reads `ASR_BACKEND`:
  - `faster_whisper` → B1 constructs the `Scribe` graph directly with
    `FasterWhisperTranscriber` injected at the transcriber seam, reusing M1's
    per-seam factories for the note generator (ollama), diarizer, draft store,
    and FHIR exporter. M1's `build_scribe` is **not** edited.
  - `mlx_whisper` (default) → M1's `build_scribe` factory, for local
    Apple-Silicon dev.

`faster-whisper` is an optional extra (`pip install -e .[cloud]`); the module
imports and the app starts without it installed (the heavy import is deferred
to `transcribe`). Tests fake the dep via `sys.modules`.

> M1's note-generation LLM is `ollama`. Confirm the cloud host can run it, or
> swap that piece the same way (out of scope for the time-box; the demo host is
> chosen to support it). If neither ASR nor ollama fit the time-box, fall back
> to pre-baked audio→transcript pairs for the demo only.

## 5. Baking S3's catalogue + index (build, not request-time)

S3's first-run cost is a few minutes: it builds an ICD-10-CM catalogue
(~75k codes) from the CMS zip, then a sentence-transformers + Chroma embedding
index. `Dockerfile.backend` pays that cost **at build time**:

```dockerfile
RUN uv run python -m auto_medical_coder.catalogue \
    && uv run python -m auto_medical_coder.index
```

Both steps are idempotent and need network (CMS zip + MiniLM model). The
`CATALOGUE_PATH` / `CHROMA_DIR` env vars are pinned to `/app/data/...` so the
build and runtime agree (S3 otherwise defaults to a relative `./data`).

## 6. Managed Postgres (production)

The compose `db` service is for local/dev. For a real deployment use a managed
Postgres (Render/Railway/Fly.io Postgres, Neon, etc.):

1. Provision the database; set `DATABASE_URL` to the managed connection string
   (with `?sslmode=require` if the provider needs it).
2. Run migrations: `docker compose run --rm backend uv run alembic upgrade head`
   (or run them in the entrypoint — the image does this on every start).
3. Seed: `docker compose run --rm backend uv run python -m clin_doc.seed`
   (idempotent — safe to repeat).

The app lifespan creates tables + seeds the demo clinician only when running on
SQLite; on Postgres it defers to Alembic + the explicit seed step above.

## 7. Deploy targets (Render / Railway / Fly.io)

The backend image is self-contained (engines + baked index + faster-whisper).
Each platform differs in detail, but the shape is:

- **Backend:** deploy the Dockerfile (build context = parent dir). Set the env
  vars from §3. Expose port 8000. The bundled `HEALTHCHECK` hits `/health`.
- **Frontend:** deploy `infra/Dockerfile.frontend` (context = `frontend/`).
  Set the build arg `BACKEND_URL` to the deployed backend's public URL so the
  Next.js rewrite proxy targets it. Expose port 3000.
- **Postgres:** use the platform's managed offering (§6).
- **Rate limit + synthetic-data banner:** `RATE_LIMIT_ENABLED=true`,
  `SYNTHETIC_DATA_ONLY=true` — both set in the compose env and the image.

> Building the backend image needs the four sibling repos present alongside
> this one. On a PaaS that builds from a single repo, either point the build at
> a monorepo checkout that includes all five repos, or pre-build and push the
> image to a registry and deploy from there. The compose file is the reference
> for the intended build shape.

## 8. Phase 5 acceptance

- [x] Dockerized (backend + frontend), env/secrets via env file, Postgres in compose.
- [x] ASR strategy executed: `FasterWhisperTranscriber` adapter + `ASR_BACKEND` toggle.
- [x] S3 catalogue + index baked into the image build step.
- [x] Seed script for synthetic demo data (`python -m clin_doc.seed`).
- [x] Rate limiting (in-process sliding-window, `RATE_LIMIT_ENABLED`) + structured logging.
- [ ] Deploy to cloud; public demo URL reachable + stable with seeded data.
