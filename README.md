# Repository Structure Analysis and Visualisation System

An interactive developer tool for scanning a local Git repository, mapping source files and import relationships, showing basic metrics, and generating cached AI summaries for selected files.

## Features

- Traverses a local repository without executing project code.
- Detects dependencies from Python imports, JavaScript/TypeScript imports, Go imports, Rust `use`/`mod`, Java imports, and C/C++ includes.
- Calculates lines of code and a lightweight complexity score per file.
- Ranks hotspot files using LoC, complexity, incoming dependencies, and outgoing dependencies.
- Summarizes directories by file count, LoC, average complexity, and cross-folder imports.
- Skips oversized source files with explicit scan warnings instead of blocking large-repo analysis.
- Exposes graph data as JSON from a FastAPI backend.
- Renders files and dependency edges on a draggable, zoomable React Flow canvas.
- Filters the graph by file path, language, imported symbol, and complexity band.
- Highlights a selected file's dependency neighborhood and lists incoming/outgoing files.
- Exports the current graph as JSON and a Markdown analysis report.
- Summarizes clicked files through OpenAI or Gemini, with local hash-based caching to control API cost.
- Shows active AI provider, model, and cache entry count in the UI.
- Falls back to a local deterministic summary when no AI API key is configured.

## Project Structure

```text
backend/
  app/
    analyzer.py      # Repository traversal, import extraction, metrics, graph edges
    ai.py            # AI provider calls and local summary cache
    main.py          # FastAPI routes
  requirements.txt
frontend/
  src/
    components/      # React Flow custom node
    lib/             # API client types and fetch helpers
    App.tsx
```

## Backend Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

If `python` points to an MSYS/MinGW interpreter on Windows, use your Windows Python path instead, for example `C:\Users\LENOVO\anaconda3\python.exe -m venv .venv`.

The API runs on `http://localhost:8000`.

Useful endpoints:

- `GET /api/health`
- `GET /api/analyze?path=C:/path/to/repo`
- `GET /api/ai/status`
- `POST /api/summarize` with JSON body `{"root":"C:/path/to/repo","path":"src/file.py"}`

Run backend tests:

```powershell
cd backend
.\run-tests.bat
```

## AI Configuration

Copy `backend/.env.example` to `backend/.env` and set one provider:

```text
AI_PROVIDER=openai
OPENAI_API_KEY=your_key_here
```

or:

```text
AI_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
```

Summaries are cached in `backend/.cache/summaries.json` using the file path and content hash, so a file is re-analyzed only after its contents change.

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

The UI runs on `http://localhost:5173`.

If the backend runs somewhere else, create `frontend/.env`:

```text
VITE_API_BASE=http://localhost:8000
```

## Evaluation Notes

- Keep the GitHub repository private until evaluation.
- Add the GDSC evaluator as a collaborator when instructed.
- Make daily commits showing visible progress.
- Submission deadline: 16 June.
