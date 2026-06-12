export type RepoNode = {
  id: string;
  path: string;
  label: string;
  directory: string;
  language: string;
  loc: number;
  complexity: number;
  fanIn: number;
  fanOut: number;
  hotspotScore: number;
  hash: string;
  imports: string[];
};

export type RepoEdge = {
  id: string;
  source: string;
  target: string;
  label: string;
};

export type DirectorySummary = {
  path: string;
  files: number;
  totalLoc: number;
  avgComplexity: number;
  hotspotScore: number;
  internalImports: number;
  incomingImports: number;
  outgoingImports: number;
};

export type SkippedFile = {
  path: string;
  reason: string;
  sizeBytes: number | null;
  limitBytes: number;
};

export type RepoGraph = {
  root: string;
  totalFiles: number;
  totalLoc: number;
  nodes: RepoNode[];
  edges: RepoEdge[];
  directories: DirectorySummary[];
  skippedFiles: SkippedFile[];
  warnings: string[];
};

export type SummaryResponse = {
  path: string;
  summary: string;
  cached: boolean;
};

export type AiStatus = {
  requestedProvider: string;
  activeProvider: "local" | "openai" | "gemini";
  configured: boolean;
  model: string;
  cacheEntries: number;
  cacheEnabled: boolean;
  cachePath: string;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

export async function analyzeRepository(path: string): Promise<RepoGraph> {
  const url = new URL("/api/analyze", API_BASE);
  url.searchParams.set("path", path);
  return parseResponse<RepoGraph>(await fetch(url));
}

export async function fetchAiStatus(): Promise<AiStatus> {
  return parseResponse<AiStatus>(await fetch(`${API_BASE}/api/ai/status`));
}

export async function summarizeFile(root: string, path: string): Promise<SummaryResponse> {
  return parseResponse<SummaryResponse>(
    await fetch(`${API_BASE}/api/summarize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ root, path }),
    }),
  );
}
