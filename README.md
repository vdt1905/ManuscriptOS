# HackaMineD: AI-Powered Research & Manuscript Formatting System

Welcome to **HackaMineD**, a full-stack, AI-agent-powered ecosystem designed to radically simplify the academic and technical writing process. 

HackaMineD takes unstructured manuscripts (PDF, DOCX, TXT), runs them through a sophisticated multi-agent pipeline, and restructures them to strictly adhere to complex publication guidelines (IEEE, ACM, Springer, etc.)—complete with spell checking, document validation, LaTeX compilation, and a helpful research assistant bot.

---

## 🎯 Core Features

1. **Agno Multi-Agent Pipeline (`api.py`)** 🤖
   - **Formatter Agent:** Restructures unstructured text into the exact heading hierarchy and citation style required by the target journal.
   - **Reviewer Agent:** Polishes the output to guarantee academic tone and formatting consistency.
   - **Markdown Agent:** Standardizes the output into clean, reliable Markdown.
   - **LaTeX Converter:** Intelligently converts the resulting Markdown into a 100% compilable, conference-ready LaTeX (`.tex`) document.

2. **Automated Error Checking & Validation** 🛡️
   - **Spell Checker:** Scans the text and generates contextual auto-fix suggestions for misspelled words.
   - **Formatting Validation:** Compares the final output structure against the journal's strict guidelines to generate a **Compliance Score** (0-100%).
   - **Side-by-Side Editor:** The "Validation Area" securely allows users to review the original manuscript alongside the generated Markdown, auto-applying spelling fixes or investigating dropped citations.

3. **LaTeX IDE & PDF Compilation** 📄
   - Contains a built-in code editor for raw `.tex` inspection.
   - Connects to an external compiling API to instantly render your manuscript into a downloadable PDF.
   
4. **Dockyyy: The Interactive Research Assistant** 🦆
   - A floating companion bot seamlessly integrated throughout the app.
   - Built with Groq (Llama-3.3 70b) and integrated with DuckDuckGo.
   - Has native context awareness: On the Validation page, it invisibly reads your current document. Ask it questions like *"Does my methodology section look correct?"* and it will answer based on your actual paper!

5. **Project & File Management Workspace** 🗂️
   - Robust filesystem allowing users to upload `.txt`, `.docx`, and `.pdf` files.
   - Full history state, saving all Original, Reconstructed Markdown, and Generated LaTeX versions.

---

## 🛠️ Tech Stack Architecture

### Frontend (`/frontend`)
- **Framework:** React.js (Vite)
- **Styling:** Tailwind CSS + Framer Motion for premium micro-animations.
- **State Management:** Zustand (`useAppStore.js`) + React Router for navigation.
- **Editors:** 
  - `react-quill-new` (For Side-by-Side visual Validation)
  - `@uiw/react-md-editor` (For Markdown editing)
  - `monaco-editor` (For raw LaTeX editing)
- **Key Files:**
  - `Process.jsx` - Manages the SSE streaming UI when the agents are running.
  - `ValidationArea.jsx` - The side-by-side reconciliation tool.
  - `ProjectWorkspace.jsx` - File tree and tabbed IDE.
  - `ChatBot.jsx` - The global Dockyyy component.

### Pipeline API (`/backend_ai`)
- **Framework:** FastAPI
- **LLM Orchestration:** `Agno` (Agents, Workflows)
- **LLM Engine:** Groq (Llama-3 & Llama-4-Maverick 17b)
- **Tools:** DuckDuckGo Web Search, PySpellChecker
- **Key Files:**
  - `api.py` - The core engine containing the Agentic Pipeline and the SSE `/reconstruct/stream` endpoint. Also houses the `/ask` endpoint for Dockyyy.
  
### Node Backend (`/backend`)
- **Framework:** Express.js + Node.js
- **Database:** MongoDB (Mongoose)
- **Features:** JWT Authentication, Project CRUD operations, and GridFS/S3 file storage handling.

---

## 🚀 Getting Started

All secrets live in **one file: the repo-root `.env`** (gitignored). Docker Compose, Express and FastAPI all read it.

| Key | Required | Notes |
|---|---|---|
| `GROQ_API_KEY` | yes | LLM calls |
| `JWT_SECRET_KEY` | yes | shared by Express (signs) and FastAPI (verifies) |
| `MONGO_URI` | yes for local run | e.g. an Atlas `mongodb+srv://…/hackamined` URI. Under Docker, unset falls back to the bundled `mongo` container |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | yes | profile pictures and uploads |
| `OPENAI_API_KEY`, `GITHUB_TOKEN`, `LATEX_MODEL`, `LLM_PROVIDER`, `LLM_MODEL`, `REQUIRE_AUTH` | no | see `docker-compose.yml` for defaults |
| `BACKEND_AI_PORT` | no | FastAPI port (default `8000`), used by both the local run and the published docker port |
| `VITE_EXPRESS_URL`, `VITE_AI_URL` | no | where the browser reaches the two backends (defaults `http://localhost:3000` / `http://localhost:8000`) |

### How the pieces fit together

```
React (Vite, :5173) ──▶ Express  (:3000) ──▶ MongoDB
                    └─▶ FastAPI (:8000) ──▶ Groq, tectonic, pandoc
```

Three processes, no reverse proxy: the browser calls each backend on its own
port, and both backends send permissive CORS headers. You can run them with
Docker or directly on your machine.

### Option A: Docker

```bash
docker compose up --build          # frontend, Express, FastAPI, Mongo
```

Open http://localhost:5173. (For live-reload while editing the frontend, run
`npm run dev` in `frontend/` instead and stop the compose `frontend` service.)

### AWS, Kubernetes, Terraform, CI/CD

The full DevOps setup is described step by step in **[DEVOPS.md](DEVOPS.md)**:
production on AWS (EC2 + S3 + CloudFront, all created by Terraform), a Kubernetes
staging stage, hardened images, and a GitHub Actions pipeline with security gates.

### Option B: Run locally (without Docker)

Needs **Node 20+**, **Anaconda or Miniconda**, and `MONGO_URI` set in `.env`.

**One-time setup** (PowerShell, from the repo root):

```powershell
# Python 3.11 + the LaTeX engine (tectonic) + pandoc, isolated in .\.venv
conda create -y -p .\.venv --override-channels -c conda-forge python=3.11 tectonic pandoc
.\.venv\python.exe -m pip install -r backend_ai\requirements.txt

npm install --prefix backend
npm install --prefix frontend

# Pre-download the core TeX packages (~40 s) so the first "Compile PDF" doesn't time out
Set-Content $env:TEMP\warm.tex '\documentclass{article}\begin{document}x\end{document}'
.\.venv\Library\bin\tectonic.exe -X compile $env:TEMP\warm.tex --outdir $env:TEMP
```

**Every time:**

```powershell
.\dev-local.ps1
```

This opens three windows (FastAPI, Express, Vite). Open the `Local:` URL printed in the Vite window, normally http://localhost:5173. To stop a service, close its window.

<details>
<summary>Or start the three services by hand</summary>

```powershell
# Terminal 1: FastAPI. tectonic and pandoc must be on PATH for the LaTeX features.
$env:PATH = "$PWD\.venv;$PWD\.venv\Library\bin;$PWD\.venv\Scripts;$env:PATH"
.\.venv\python.exe -m backend_ai.main

# Terminal 2: Express (:3000)
npm start --prefix backend

# Terminal 3: frontend
npm run dev --prefix frontend
```
</details>

**Troubleshooting**

- *"Port 8000 is already in use"*: another app is on it. Set `BACKEND_AI_PORT` and `VITE_AI_URL` in `.env` to a free port (they must agree).
- *Vite says "Port 5173 is in use, trying another one"*: harmless. Use the URL it prints.
- *Requests fail with "Network Error" / "Failed to fetch"*: the backend that URL points at isn't running. Check `VITE_EXPRESS_URL` and `VITE_AI_URL` in `.env` against what is actually listening, and start the missing service.
- *First PDF compile of a new document class is slow*: tectonic downloads the packages it needs once, then caches them.
- *Login works under Docker but not locally, or the reverse*: they can use different databases (the Docker `mongo` container vs. `MONGO_URI`), so an account made in one doesn't exist in the other.

---

## 📖 The User Journey

1. **Dashboard:** Start a new job or view history.
2. **Upload:** Drop an unstructured Word doc or PDF file.
3. **Configure:** Select the required target format (e.g. `IEEE`). The LLM intelligently parses your chosen format requirements.
4. **Process:** Watch the magic happen. The pipeline streams Server-Sent Events (SSE) to the UI, showing exactly which agents are formatting, reviewing, and checking your document live.
5. **Validation:** Review the Compliance Score. Use the "Autofix" button to automatically patch spelling errors highlighted by the system.
6. **Workspace / LaTeX:** Jump into the IDE, make final text adjustments, and hit **Compile PDF** to download your publication-ready manuscript!
