# ─────────────────────────────────────────────────────────────
# ai-service — FastAPI: chatbot, deep-scan, DocBot, LaTeX toolkit
# Build context: ./backend_ai   (so backend_ai/.dockerignore applies)
# ─────────────────────────────────────────────────────────────
# Pinned to Debian bookworm so system package names stay stable.
FROM python:3.11-slim-bookworm

# Fail a RUN step if any command in a pipe fails (e.g. the tectonic download).
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System tools:
#   pandoc       DOCX export / LaTeX -> DOCX
#   libglib2.0-0 needed by OpenCV, which pdf2docx (PDF upload) uses
#   tectonic     self-contained LaTeX engine for "Compile PDF"
# curl is only needed to fetch tectonic, so it is removed again.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl pandoc libglib2.0-0 \
 && curl -fsSL https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-musl.tar.gz \
    | tar xz -C /usr/local/bin \
 && chmod +x /usr/local/bin/tectonic \
 && apt-get purge -y curl && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

# Run as an unprivileged user, never root.
RUN useradd --create-home --uid 10001 app

WORKDIR /app
# Dependencies first: this layer is reused until requirements.txt changes.
COPY requirements.txt /app/backend_ai/requirements.txt
RUN pip install -r /app/backend_ai/requirements.txt

COPY --chown=app:app . /app/backend_ai
RUN mkdir -p /app/backend_ai/data /app/backend_ai/deepscan/output \
 && chown -R app:app /app/backend_ai/data /app/backend_ai/deepscan/output

# Numeric so Kubernetes can verify runAsNonRoot.
USER 10001:10001
# Pre-download the TeX packages the deep-scan templates use (IEEE and the
# article-based styles), so the first "Compile PDF" is fast: behind
# CloudFront a request must finish within 60 seconds.
RUN printf '%s\n' \
      '\documentclass[conference]{IEEEtran}' \
      '\usepackage{cite,amsmath,amssymb,amsfonts,graphicx,textcomp,xcolor,float,hyperref}' \
      '\usepackage[utf8]{inputenc}\usepackage[T1]{fontenc}' \
      '\begin{document}\title{Warm-up}\maketitle\section{Intro}IEEE warm-up.\end{document}' > /tmp/ieee.tex \
 && printf '%s\n' \
      '\documentclass[12pt]{article}' \
      '\usepackage[margin=1in]{geometry}\usepackage{times,setspace,natbib,caption,indentfirst}' \
      '\usepackage{amsmath,amssymb,graphicx,float,hyperref}\usepackage[utf8]{inputenc}\usepackage[T1]{fontenc}' \
      '\begin{document}\doublespacing\section{Intro}Article warm-up.\end{document}' > /tmp/article.tex \
 && tectonic -X compile /tmp/ieee.tex --outdir /tmp \
 && tectonic -X compile /tmp/article.tex --outdir /tmp \
 && rm -f /tmp/ieee.* /tmp/article.*

ENV BACKEND_AI_HOST=0.0.0.0 \
    BACKEND_AI_PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]

CMD ["python", "-m", "backend_ai.main"]
