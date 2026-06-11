from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import httpx


PROMPT = "Explain what this code does in 3 simple sentences."
CACHE_DIR = Path(".cache")
CACHE_FILE = CACHE_DIR / "summaries.json"


def file_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def ai_status() -> dict[str, Any]:
    requested_provider = os.getenv("AI_PROVIDER", "local").lower()
    provider = requested_provider if requested_provider in {"openai", "gemini"} else "local"
    key_env = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}.get(provider)
    configured = provider == "local" or bool(key_env and os.getenv(key_env))
    active_provider = provider if configured else "local"
    model = {
        "openai": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "gemini": os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
        "local": "local-fallback",
    }[active_provider]
    cache = _load_cache()

    return {
        "requestedProvider": requested_provider,
        "activeProvider": active_provider,
        "configured": configured,
        "model": model,
        "cacheEntries": len(cache),
        "cacheEnabled": True,
        "cachePath": CACHE_FILE.as_posix(),
    }


async def summarize_code(file_path: Path, code: str) -> dict[str, Any]:
    digest = file_hash(code)
    cache = _load_cache()
    cache_key = f"{file_path.as_posix()}:{digest}"
    if cache_key in cache:
        return {"summary": cache[cache_key], "cached": True}

    summary = await _call_provider(file_path, code)
    cache[cache_key] = summary
    _save_cache(cache)
    return {"summary": summary, "cached": False}


async def _call_provider(file_path: Path, code: str) -> str:
    provider = os.getenv("AI_PROVIDER", "local").lower()
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        return await _call_openai(file_path, code)
    if provider == "gemini" and os.getenv("GEMINI_API_KEY"):
        return await _call_gemini(file_path, code)
    return _local_summary(file_path, code)


async def _call_openai(file_path: Path, code: str) -> str:
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": f"{PROMPT}\n\nFile: {file_path.as_posix()}\n\n```text\n{code[:12000]}\n```",
            }
        ],
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
    data = response.json()
    return data.get("output_text") or _extract_openai_text(data)


async def _call_gemini(file_path: Path, code: str) -> str:
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={os.environ['GEMINI_API_KEY']}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"{PROMPT}\n\nFile: {file_path.as_posix()}\n\n```text\n{code[:12000]}\n```"
                    }
                ]
            }
        ]
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
    data = response.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return " ".join(part.get("text", "") for part in parts).strip()


def _extract_openai_text(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text", ""))
    return " ".join(chunks).strip()


def _local_summary(file_path: Path, code: str) -> str:
    non_empty = [line.strip() for line in code.splitlines() if line.strip()]
    preview = " ".join(non_empty[:3])[:180]
    name = file_path.name
    if not non_empty:
        return f"{name} is currently empty. It does not define behavior yet. Add code before requesting an AI summary."
    return (
        f"{name} contains {len(non_empty)} non-empty lines of source code. "
        f"It appears to define logic related to: {preview}. "
        "Configure AI_PROVIDER with OpenAI or Gemini credentials for a richer explanation."
    )


def _load_cache() -> dict[str, str]:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict[str, str]) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
