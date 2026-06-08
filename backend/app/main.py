from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .ai import ai_status, summarize_code
from .analyzer import analyze_repository


app = FastAPI(title="Repository Structure Analysis API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SummaryRequest(BaseModel):
    root: str
    path: str


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/ai/status")
def get_ai_status() -> dict:
    return ai_status()


@app.get("/api/analyze")
def analyze(path: str = Query(".", description="Local repository path to scan")) -> dict:
    try:
        return analyze_repository(_resolve_repository_path(path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/summarize")
async def summarize(request: SummaryRequest) -> dict:
    root = Path(request.root).expanduser().resolve()
    target = (root / request.path).resolve()

    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="Repository root does not exist.")
    if root not in target.parents and target != root:
        raise HTTPException(status_code=400, detail="Requested file is outside the repository root.")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Requested file was not found.")

    try:
        code = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        code = target.read_text(encoding="latin-1", errors="ignore")

    result = await summarize_code(Path(request.path), code)
    return {"path": request.path, **result}


def _resolve_repository_path(path: str) -> Path:
    requested = Path(path).expanduser()
    if requested.is_absolute():
        return requested

    cwd = Path.cwd()
    candidates = []
    if cwd.name.lower() == "backend":
        candidates.append(cwd.parent / requested)
    candidates.append(cwd / requested)

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()
