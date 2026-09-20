# HackaMineD / Docling AI — Claude Project Brief

AI-powered manuscript formatting & research platform built at Hack-NU 2026 by a 4-person team. Takes unstructured PDF/DOCX/TXT manuscripts and restructures them to journal guidelines (IEEE / ACM / Springer / APA7) via a multi-agent LLM pipeline, then offers spell-check, validation, LaTeX compilation, and a research chatbot.

## Repo layout (cleaned up — 2 backends + 1 frontend)

| Folder | Port | Stack | Owner role |
|---|---|---|---|
| `backend/` | 3000 | Express + MongoDB + JWT + Cloudinary | Auth, projects, files, LaTeX compile proxy |
| `backend_ai/` | 8000 | FastAPI (one process, 4 routers) | Chatbot, reconstruct, deep-scan, file-editor, README generator |
| `frontend/` | 5173 (Vite) | React 19 + Zustand + Tailwind | Single SPA |

The 4 hackathon-era Python folders (`backend-chatbot-spellCheck/`, `backend-agent-pipeline/`, `backend-agent-fileEditor/`, `backend-readme-generator-github/`) and the intermediate `services/` folder have been **deleted**. All Python code now lives under `backend_ai/` as proper Python sub-packages.

### `backend_ai/` internal structure

```
backend_ai/
├── main.py              FastAPI entrypoint — mounts the 4 routers + middleware
├── requirements.txt     merged from all 4 legacy services
├── .env                 consolidated secrets (gitignored)
├── common/              shared utilities (JWT verifier)
├── chatbot/             Dockyyy + reconstruct pipeline  → /api/v2/*
├── deepscan/            FormatForge multi-agent pipeline → /deepscan/*
├── file_editor/         DocBot DOCX editor + 23 tools    → /files/*
├── readme_gen/          GitHub README generator          → /readme/*
└── data/                SQLite DBs + documents_store/
```

Each sub-package exposes a single `APIRouter` from `routes.py`. `main.py` includes them at the appropriate prefix. CORS, JWT auth, exception handlers, and lifespan are all wired once in `main.py` — no redundant middleware in sub-routers.

## Core user journey

Dashboard → Upload → Configure (target style) → Process (SSE-streamed agent pipeline) → Validation (compliance score + autofix spelling) → Workspace / LaTeX IDE → Compile PDF.

## Frontend → backend wiring

All API calls go through [`frontend/src/config/api.js`](frontend/src/config/api.js) — one config module, env-var overridable. **Two service roots:**

- `EXPRESS`   → `http://localhost:3000`  — auth, projects, files, LaTeX compile proxy
- `PYTHON_AI` → `http://127.0.0.1:8000`  — chatbot (`/api/v2`), deep-scan (`/deepscan`), file-editor (`/files`), readme-gen (`/readme`)

Exported `ENDPOINTS`: `auth`, `projects`, `latexCompile` (Express), `chatbot`, `deepScan`, `fileEditor`, `readmeGen` (all five Python ones share the same `PYTHON_AI` root).

Override via `VITE_EXPRESS_URL` and `VITE_PYTHON_AI_URL` (see [frontend/.env.example](frontend/.env.example)).

## State management

- `useAuthStore.js` — JWT login/signup, profile, persists token to `localStorage`.
- `useProjectStore.js` — project CRUD + recents, hits Express.
- `useAppStore.js` — transient UI state (uploaded file, current step, validation result, suggestions, logs).
- `useDeepScanStore.js` — isolated 5-step deep-scan pipeline state.

## Persistence

- MongoDB (via `backend/`) — users, projects, embedded files (with `validationReport`).
- Cloudinary — profile pictures and uploaded binaries.
- SQLite `backend_ai/data/dockyyy.db` — Agno chat sessions for the chatbot.
- SQLite `backend_ai/data/agent_sessions.db` — Agno sessions for the file-editor agent.
- In-memory session store — README generator (1h TTL).
- Local disk — `backend_ai/data/documents_store/`, `backend_ai/deepscan/output/`.

## LLM providers

All Python services use **Groq**. Models in play:
- `LLM_MODEL` env var (default `openai/gpt-oss-120b`) — Dockyyy chatbot, file-editor DocBot, deep-scan, LaTeX toolkit (`TOOLKIT_MODEL` overrides the toolkit). Groq retired the Llama chat models in 2026.
- LaTeX repair on a failed compile — controlled by `LATEX_MODEL` env var. Default `openai/gpt-oss-120b`.

## Deep-scan LaTeX generation (stage 2)

The LaTeX is built **deterministically** from the labelled DocIR in
[backend_ai/deepscan/latex_builder.py](backend_ai/deepscan/latex_builder.py): title, author block, abstract,
keywords, `\section`s from detected headings, body paragraphs (run formatting → `\textit`/`\textsuperscript`),
figure captions as floats, numeric citations (`(1)`, `(6, 7)`, superscript `1,2`) as `\cite{refN}`, and
`thebibliography` in source order. The orchestrator hands the merged DocIR over on `FormatResult.docir`
(`docir_raw` = pre-merge, for the author lines).

The LLM then only *polishes* body paragraphs, ~650 words per call (math mode, species names). Each polished
group is accepted only if it keeps ≥95% of the words and every `\cite` (`_polish_acceptable` in
`agno_router.py`); otherwise the structural version stays. Do not go back to asking the model to convert whole
sections: that is what lost 65–80% of the text before.

Stage 1 gotchas fixed along the way and worth keeping: the abstract ends at the keywords line (PNAS puts the
introduction right after it with no heading); the LLM role-correction pass may only fill `UNKNOWN`/weak `BODY`
labels, never override heuristic ones; citeproc entries are registered in order (a `set` shuffled the
bibliography); title-case must not lowercase identifiers (`GrlA`, `LEE1`).
- DuckDuckGo tool is shared by Dockyyy and Agno pipeline agents.

Required env: `GROQ_API_KEY`, `JWT_SECRET_KEY` (must match Express), `MONGO_URI`, `CLOUDINARY_*` (Express only), `GITHUB_TOKEN` (optional). See repo-root [.env.example](.env.example) for the full list.

## Auth

Express signs a JWT on login/signup (HS256, `JWT_SECRET_KEY`, payload `{userId}`, 7d expiry, header `Authorization: Bearer <token>`). The SPA stores it under `localStorage.token`.

`backend_ai/` verifies the same token via [common/jwt_auth.py](backend_ai/common/jwt_auth.py). Two modes:
- `REQUIRE_AUTH=false` (default) — fail-open; anonymous calls still pass.
- `REQUIRE_AUTH=true` — fail-closed; missing/invalid/expired tokens return 401.

Whitelisted paths skip auth: `/healthz`, `/docs`, `/redoc`, `/openapi.json`, `/`, `/favicon.ico`, plus per-router health/info pages (`/deepscan/api/health`, `/files/health`, `/readme/health`, `/readme/info`, …). CORS preflight (OPTIONS) always passes through.

Frontend: [frontend/src/config/api.js](frontend/src/config/api.js) installs a global axios interceptor that attaches `Bearer` auth automatically, plus `authHeaders()` for explicit `fetch()` calls.

## Boot

```bash
# Everything at once via docker:
docker compose up --build

# Or run components individually:
cd backend     && npm install && npm run dev          # Express on :3000
python -m backend_ai.main                              # Python on :8000
cd frontend    && npm install && npm run dev          # Vite SPA on :5173
```

## Conventions / quirks worth knowing

- Express uses ES modules (`"type": "module"` in `backend/package.json`).
- Frontend uses **Tailwind v4** and **React 19** — many lint rules behave differently from v3 / React 18.
- Editors: `react-quill-new` (validation), `@uiw/react-md-editor` (markdown), `monaco-editor` (LaTeX).
- LaTeX compilation: Vite dev proxy `/latex-api` → `https://latexonline.cc`; also `texlive.net` form-post used by `docs/demos/index1.html`.
- `ChatBot.jsx` is "context-aware": on the validation page it reads the live document and silently feeds it to `/api/v2/ask`.
- SSE responses are JSON-per-event, not plain text — frontend parses each line as JSON.

## Cheat sheet for navigation

- Unified entrypoint → [backend_ai/main.py](backend_ai/main.py)
- Chatbot prompts → [backend_ai/chatbot/prompts.py](backend_ai/chatbot/prompts.py)
- Deep-scan pipeline router → [backend_ai/deepscan/agno_router.py](backend_ai/deepscan/agno_router.py)
- File-editor 23 tools → [backend_ai/file_editor/routes.py](backend_ai/file_editor/routes.py)
- README LaTeX templates → [backend_ai/readme_gen/routes.py](backend_ai/readme_gen/routes.py)
- Shared JWT verifier → [backend_ai/common/jwt_auth.py](backend_ai/common/jwt_auth.py)
- Mongoose models → [backend/models/](backend/models/) (User, Project)
- Auth middleware → [backend/middleware/authMiddleware.js](backend/middleware/authMiddleware.js)
- Frontend config → [frontend/src/config/api.js](frontend/src/config/api.js)
- Orchestration → [docker-compose.yml](docker-compose.yml)

## Status

See [README.md](README.md) for the marketing copy. The Phase 0–3 hackathon-cleanup work is done; the codebase is now 2 backends + 1 frontend with no duplicate code, central frontend config, shared JWT, and consolidated env file. Remaining work: persistence/storage hardening (move SQLite to Postgres for multi-instance), structured logs, rate-limiting, background job queue for long-running SSE.
