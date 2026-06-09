from __future__ import annotations

import ast
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hpp",
}

MAX_SOURCE_FILE_BYTES = int(os.getenv("MAX_SOURCE_FILE_BYTES", str(1024 * 1024)))

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    ".venv-win",
    "venv",
    "env",
    "__pycache__",
    "site-packages",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".vite",
    ".idea",
    ".vscode",
    "coverage",
    ".cache",
}

JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:.+?\s+from\s+)?|export\s+.+?\s+from\s+|require\()\s*['"]([^'"]+)['"]"""
)
GO_IMPORT_BLOCK_RE = re.compile(r"import\s*\((.*?)\)", re.DOTALL)
GO_IMPORT_LINE_RE = re.compile(r'import\s+(?:(?:[\w.]+)\s+)?"([^"]+)"')
RUST_MOD_RE = re.compile(r"\b(?:use|mod)\s+([A-Za-z_][A-Za-z0-9_:]*)")
JAVA_IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([A-Za-z0-9_.*]+);", re.MULTILINE)
C_INCLUDE_RE = re.compile(r"^\s*#\s*include\s+[<\"]([^>\"]+)[>\"]", re.MULTILINE)

COMPLEXITY_PATTERNS = (
    r"\bif\b",
    r"\bfor\b",
    r"\bwhile\b",
    r"\bcase\b",
    r"\bcatch\b",
    r"\bexcept\b",
    r"\belif\b",
    r"\bmatch\b",
    r"\b&&\b",
    r"\|\|",
    r"\?",
)


@dataclass(frozen=True)
class FileInfo:
    path: Path
    rel_path: str
    loc: int
    complexity: int
    language: str
    content_hash: str
    imports: tuple[str, ...]


def analyze_repository(root: str | Path) -> dict:
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise ValueError(f"Repository path does not exist or is not a directory: {root_path}")

    files, skipped_files = _filter_scannable_files(root_path, _iter_source_files(root_path))
    infos = [_analyze_file(path, root_path) for path in files]
    by_rel_path = {info.rel_path: info for info in infos}
    edges = _build_edges(infos, by_rel_path)
    metrics = _dependency_metrics(infos, edges)
    nodes = [
        {
            "id": info.rel_path,
            "path": info.rel_path,
            "label": Path(info.rel_path).name,
            "directory": _directory_for(info.rel_path),
            "language": info.language,
            "loc": info.loc,
            "complexity": info.complexity,
            "hash": info.content_hash,
            "imports": list(info.imports),
            "fanIn": metrics[info.rel_path]["fanIn"],
            "fanOut": metrics[info.rel_path]["fanOut"],
            "hotspotScore": _hotspot_score(
                info.loc,
                info.complexity,
                metrics[info.rel_path]["fanIn"],
                metrics[info.rel_path]["fanOut"],
            ),
        }
        for info in infos
    ]

    return {
        "root": str(root_path),
        "totalFiles": len(infos),
        "totalLoc": sum(info.loc for info in infos),
        "nodes": nodes,
        "edges": edges,
        "directories": _directory_summaries(nodes, edges),
        "skippedFiles": skipped_files,
        "warnings": _scan_warnings(skipped_files),
    }


def _iter_source_files(root: Path) -> Iterable[Path]:
    stack = [root]
    while stack:
        current = stack.pop()
        for path in current.iterdir():
            if path.is_dir():
                if path.name not in IGNORED_DIRS:
                    stack.append(path)
                continue
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                yield path


def _filter_scannable_files(root: Path, candidates: Iterable[Path]) -> tuple[list[Path], list[dict]]:
    files: list[Path] = []
    skipped: list[dict] = []
    for path in candidates:
        rel_path = path.relative_to(root).as_posix()
        try:
            size = path.stat().st_size
        except OSError as exc:
            skipped.append(
                {
                    "path": rel_path,
                    "reason": f"Unable to read file metadata: {exc.__class__.__name__}",
                    "sizeBytes": None,
                    "limitBytes": MAX_SOURCE_FILE_BYTES,
                }
            )
            continue
        if size > MAX_SOURCE_FILE_BYTES:
            skipped.append(
                {
                    "path": rel_path,
                    "reason": "File exceeds scan size limit",
                    "sizeBytes": size,
                    "limitBytes": MAX_SOURCE_FILE_BYTES,
                }
            )
            continue
        files.append(path)
    return files, skipped


def _scan_warnings(skipped_files: list[dict]) -> list[str]:
    if not skipped_files:
        return []
    return [
        f"Skipped {len(skipped_files)} source file(s) because they exceeded safety limits or could not be inspected."
    ]


def _analyze_file(path: Path, root: Path) -> FileInfo:
    text = _read_text(path)
    rel_path = path.relative_to(root).as_posix()
    loc = _count_loc(text)
    complexity = _estimate_complexity(text)
    language = _language_for(path.suffix.lower())
    imports = tuple(sorted(set(_extract_imports(path, text))))
    content_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
    return FileInfo(path, rel_path, loc, complexity, language, content_hash, imports)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="ignore")


def _count_loc(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip() and not line.strip().startswith("//"))


def _estimate_complexity(text: str) -> int:
    score = 1
    for pattern in COMPLEXITY_PATTERNS:
        score += len(re.findall(pattern, text))
    return score


def _language_for(ext: str) -> str:
    return {
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "React JSX",
        ".ts": "TypeScript",
        ".tsx": "React TSX",
        ".mjs": "JavaScript",
        ".cjs": "JavaScript",
        ".java": "Java",
        ".go": "Go",
        ".rs": "Rust",
        ".c": "C",
        ".cc": "C++",
        ".cpp": "C++",
        ".cxx": "C++",
        ".h": "C/C++ Header",
        ".hpp": "C++ Header",
    }.get(ext, ext.lstrip(".").upper())


def _extract_imports(path: Path, text: str) -> list[str]:
    ext = path.suffix.lower()
    if ext == ".py":
        return _extract_python_imports(text)
    if ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        return [match.group(1) for match in JS_IMPORT_RE.finditer(text)]
    if ext == ".go":
        imports = [match.group(1) for match in GO_IMPORT_LINE_RE.finditer(text)]
        for block in GO_IMPORT_BLOCK_RE.findall(text):
            imports.extend(re.findall(r'"([^"]+)"', block))
        return imports
    if ext == ".rs":
        return [match.group(1).replace("::", "/") for match in RUST_MOD_RE.finditer(text)]
    if ext == ".java":
        return [match.group(1) for match in JAVA_IMPORT_RE.finditer(text)]
    if ext in {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"}:
        return [match.group(1) for match in C_INCLUDE_RE.finditer(text)]
    return []


def _extract_python_imports(text: str) -> list[str]:
    imports: list[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            prefix = "." * node.level + module
            for alias in node.names:
                if alias.name == "*":
                    imports.append(prefix)
                elif module:
                    imports.append(prefix)
                    imports.append(f"{prefix}.{alias.name}")
                elif node.level:
                    imports.append(f"{'.' * node.level}{alias.name}")
                elif prefix:
                    imports.append(f"{prefix}.{alias.name}")
                else:
                    imports.append(alias.name)
    return imports


def _build_edges(infos: list[FileInfo], by_rel_path: dict[str, FileInfo]) -> list[dict]:
    module_index = _build_module_index(infos)
    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for info in infos:
        for import_name in info.imports:
            target = _resolve_import(info, import_name, module_index, by_rel_path)
            if target and target != info.rel_path and (info.rel_path, target) not in seen:
                seen.add((info.rel_path, target))
                edges.append(
                    {
                        "id": f"{info.rel_path}->{target}",
                        "source": info.rel_path,
                        "target": target,
                        "label": import_name,
                    }
                )
    return edges


def _dependency_metrics(infos: list[FileInfo], edges: list[dict]) -> dict[str, dict[str, int]]:
    metrics = {info.rel_path: {"fanIn": 0, "fanOut": 0} for info in infos}
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        metrics.setdefault(source, {"fanIn": 0, "fanOut": 0})["fanOut"] += 1
        metrics.setdefault(target, {"fanIn": 0, "fanOut": 0})["fanIn"] += 1
    return metrics


def _hotspot_score(loc: int, complexity: int, fan_in: int, fan_out: int) -> int:
    return loc + complexity * 10 + fan_in * 8 + fan_out * 5


def _directory_for(rel_path: str) -> str:
    parent = Path(rel_path).parent
    return parent.as_posix() if str(parent) != "." else "root"


def _directory_summaries(nodes: list[dict], edges: list[dict]) -> list[dict]:
    summaries: dict[str, dict] = {}
    node_dirs = {node["id"]: node["directory"] for node in nodes}

    for node in nodes:
        directory = node["directory"]
        summary = summaries.setdefault(
            directory,
            {
                "path": directory,
                "files": 0,
                "totalLoc": 0,
                "totalComplexity": 0,
                "hotspotScore": 0,
                "internalImports": 0,
                "incomingImports": 0,
                "outgoingImports": 0,
            },
        )
        summary["files"] += 1
        summary["totalLoc"] += node["loc"]
        summary["totalComplexity"] += node["complexity"]
        summary["hotspotScore"] += node["hotspotScore"]

    for edge in edges:
        source_dir = node_dirs.get(edge["source"])
        target_dir = node_dirs.get(edge["target"])
        if not source_dir or not target_dir:
            continue
        if source_dir == target_dir:
            summaries[source_dir]["internalImports"] += 1
        else:
            summaries[source_dir]["outgoingImports"] += 1
            summaries[target_dir]["incomingImports"] += 1

    for summary in summaries.values():
        files = summary["files"] or 1
        summary["avgComplexity"] = round(summary.pop("totalComplexity") / files, 1)

    return sorted(
        summaries.values(),
        key=lambda item: (-item["hotspotScore"], item["path"]),
    )


def _build_module_index(infos: list[FileInfo]) -> dict[str, str]:
    index: dict[str, str] = {}
    for info in infos:
        rel = Path(info.rel_path)
        stem_path = rel.with_suffix("").as_posix()
        dotted = stem_path.replace("/", ".")
        index[stem_path] = info.rel_path
        index[dotted] = info.rel_path
        if rel.name == "__init__.py":
            pkg = rel.parent.as_posix().replace("/", ".")
            index[pkg] = info.rel_path
    return index


def _resolve_import(
    source: FileInfo,
    import_name: str,
    module_index: dict[str, str],
    by_rel_path: dict[str, FileInfo],
) -> str | None:
    normalized = import_name.strip().strip(";")
    if not normalized:
        return None

    if normalized.startswith("."):
        source_dir = Path(source.rel_path).parent
        level = len(normalized) - len(normalized.lstrip("."))
        remainder = normalized[level:].replace(".", "/")
        base = source_dir
        for _ in range(max(level - 1, 0)):
            base = base.parent
        candidate = (base / remainder).as_posix() if remainder else base.as_posix()
        resolved = _resolve_path_candidate(candidate, by_rel_path)
        if resolved:
            return resolved

    if normalized.startswith(("./", "../")):
        candidate = (Path(source.rel_path).parent / normalized).as_posix()
        return _resolve_path_candidate(candidate, by_rel_path)

    sibling_candidate = (Path(source.rel_path).parent / normalized).as_posix()
    resolved_sibling = _resolve_path_candidate(sibling_candidate, by_rel_path)
    if resolved_sibling:
        return resolved_sibling

    candidates = [
        normalized,
        normalized.replace(".", "/"),
        normalized.replace("::", "/"),
    ]
    for candidate in candidates:
        if candidate in module_index:
            return module_index[candidate]
        resolved = _resolve_path_candidate(candidate, by_rel_path)
        if resolved:
            return resolved
    return None


def _resolve_path_candidate(candidate: str, by_rel_path: dict[str, FileInfo]) -> str | None:
    clean = Path(candidate).as_posix().lstrip("/")
    possible = [clean]
    for ext in SUPPORTED_EXTENSIONS:
        possible.append(f"{clean}{ext}")
    possible.extend([f"{clean}/index.js", f"{clean}/index.ts", f"{clean}/__init__.py", f"{clean}/mod.rs"])

    for path in possible:
        normalized = Path(path).as_posix()
        if normalized in by_rel_path:
            return normalized
    return None
