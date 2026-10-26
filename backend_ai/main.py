"""
HackaMineD — Unified Python Backend
====================================

One FastAPI app on one port (8000) hosts every Python-side service:

    Chatbot + Reconstruct   (root):   /api/v2/ask, /api/v2/reconstruct/stream
    Deep-Scan / FormatForge (/deepscan): /deepscan/api/v2/pipeline/stream, etc.
    File-Editor / DocBot    (/files):    /files/documents/..., /files/chat
    README Generator        (/readme):   /readme/api/v1/..., GET /readme/

Each domain lives in its own sub-package under backend-ai/ (chatbot/,
deepscan/, file_editor/, readme_gen/) and exposes an APIRouter.

Pair this with the Express backend (port 3000) — the only two backend
processes in the system.

Run:
    pip install -r backend-ai/requirements.txt
    python -m backend-ai.main           # or: uvicorn backend-ai.main:app --reload
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

# Load backend_ai/.env if present, then the repo-root .env (shared with Express
# and docker compose) for anything still unset. Neither overrides variables that
# are already in the environment, so docker compose's values take precedence.
HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")

# Default DB + data paths so the sub-routers don't write to a stray cwd.
os.environ.setdefault("DOCKYYY_DB_PATH",         str(HERE / "data" / "dockyyy.db"))
os.environ.setdefault("AGENT_SESSIONS_DB_PATH",  str(HERE / "data" / "agent_sessions.db"))
os.environ.setdefault("DOCUMENTS_DIR",           str(HERE / "data" / "documents_store"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend-ai")

# --------------------------------------------------------------------------
# Sub-routers + cross-cutting middleware
# --------------------------------------------------------------------------
from .chatbot import router as chatbot_router
from .deepscan import router as deepscan_router
from .file_editor import router as file_editor_router
from .latex_toolkit import router as latex_toolkit_router
from .common import JWTAuthMiddleware, DEFAULT_PUBLIC_PATHS


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("HackaMineD backend-ai starting")
    yield
    logger.info("HackaMineD backend-ai shutting down")


app = FastAPI(
    title="HackaMineD — Unified Python Backend",
    description="Chatbot, reconstruct pipeline, deep-scan, file-editor, and README generator on one port.",
    version="1.0.0",
    lifespan=lifespan,
)

# --------------------------------------------------------------------------
# Middleware stack (order matters — added last runs first)
# --------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*", "Authorization", "X-Session-Token"],
    # The SPA calls this service cross-origin, and a browser hides custom
    # response headers unless they are listed here (the compile endpoint
    # returns its auto-fix notes in X-Latex-Notes).
    expose_headers=["X-Latex-Notes", "Content-Disposition"],
)
app.add_middleware(
    JWTAuthMiddleware,
    public_paths=DEFAULT_PUBLIC_PATHS + (
        # Deep-scan public paths
        "/deepscan/api/health",
        "/deepscan/api/v2/health",
        "/deepscan/docs",
        "/deepscan/redoc",
        "/deepscan/openapi.json",
        # File-editor public paths
        "/files/health",
        "/files/docs",
        "/files/redoc",
        "/files/openapi.json",
        # LaTeX-toolkit public paths (catalog + templates are read-only)
        "/toolkit/health",
        "/toolkit/info",
        "/toolkit/templates",
    ),
)


# --------------------------------------------------------------------------
# Unified exception handler
# --------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# --------------------------------------------------------------------------
# Service health
# --------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "service": "backend-ai",
        "mounts": {
            "chatbot":       "(root) — /api/v2/ask",
            "deepscan":      "/deepscan",
            "file_editor":   "/files",
            "latex_toolkit": "/toolkit",
        },
    }


# --------------------------------------------------------------------------
# Mount the four sub-routers
# --------------------------------------------------------------------------
app.include_router(chatbot_router)
app.include_router(deepscan_router, prefix="/deepscan")
app.include_router(file_editor_router, prefix="/files")
app.include_router(latex_toolkit_router, prefix="/toolkit")


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("BACKEND_AI_HOST", "127.0.0.1")
    port = int(os.getenv("BACKEND_AI_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, reload=False)
