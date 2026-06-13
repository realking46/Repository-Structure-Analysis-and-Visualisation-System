import { useCallback, useEffect, useMemo, useState, type MouseEvent } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  useEdgesState,
  useNodesState,
} from "reactflow";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Download,
  Filter,
  FileText,
  Flame,
  FolderTree,
  GitBranch,
  Loader2,
  PlugZap,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import FileNode from "./components/FileNode";
import {
  analyzeRepository,
  AiStatus,
  fetchAiStatus,
  RepoGraph,
  RepoNode,
  summarizeFile,
  SummaryResponse,
} from "./lib/api";

const nodeTypes = { file: FileNode };

function buildFlowNodes(graph: RepoGraph): Node[] {
  const directoryBuckets = new Map<string, RepoNode[]>();
  graph.nodes.forEach((node) => {
    const directory = node.directory || "root";
    directoryBuckets.set(directory, [...(directoryBuckets.get(directory) ?? []), node]);
  });

  const orderedDirectories = Array.from(directoryBuckets.keys()).sort();
  return orderedDirectories.flatMap((directory, column) => {
    const files = directoryBuckets.get(directory) ?? [];
    return files
      .sort((a, b) => a.path.localeCompare(b.path))
      .map((node, row) => ({
        id: node.id,
        type: "file",
        position: {
          x: column * 320,
          y: row * 150,
        },
        data: node,
      }));
  });
}

function buildFlowEdges(graph: RepoGraph): Edge[] {
  return graph.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label,
    animated: true,
    style: { strokeWidth: 2 },
  }));
}

function complexityLevel(complexity: number): "low" | "medium" | "high" {
  if (complexity >= 18) return "high";
  if (complexity >= 8) return "medium";
  return "low";
}

function downloadTextFile(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function safeFilename(value: string) {
  return value.replace(/[^a-z0-9_-]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase() || "repository";
}

function buildMarkdownReport(graph: RepoGraph, aiStatus: AiStatus | null) {
  const topDirectories = graph.directories.slice(0, 8);
  const hotspots = [...graph.nodes]
    .sort((a, b) => b.hotspotScore - a.hotspotScore || b.loc - a.loc)
    .slice(0, 10);
  const lines = [
    `# Repository Analysis Report`,
    "",
    `Root: ${graph.root}`,
    "",
    "## Summary",
    "",
    `- Files: ${graph.totalFiles}`,
    `- Lines of code: ${graph.totalLoc}`,
    `- Internal dependencies: ${graph.edges.length}`,
    `- Skipped files: ${graph.skippedFiles.length}`,
    `- AI provider: ${aiStatus ? `${aiStatus.activeProvider} (${aiStatus.model})` : "unknown"}`,
    `- Cached summaries: ${aiStatus ? aiStatus.cacheEntries : 0}`,
    "",
    "## Top Directories",
    "",
    "| Directory | Files | LoC | Avg Complexity | In | Out | Hotspot |",
    "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ...topDirectories.map(
      (item) =>
        `| ${item.path} | ${item.files} | ${item.totalLoc} | ${item.avgComplexity} | ${item.incomingImports} | ${item.outgoingImports} | ${item.hotspotScore} |`,
    ),
    "",
    "## Hotspot Files",
    "",
    "| File | Language | LoC | Complexity | Used By | Uses | Score |",
    "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ...hotspots.map(
      (node) =>
        `| ${node.path} | ${node.language} | ${node.loc} | ${node.complexity} | ${node.fanIn} | ${node.fanOut} | ${node.hotspotScore} |`,
    ),
    "",
    ...(graph.skippedFiles.length
      ? [
          "## Skipped Files",
          "",
          "| File | Reason | Size | Limit |",
          "| --- | --- | ---: | ---: |",
          ...graph.skippedFiles.map(
            (file) =>
              `| ${file.path} | ${file.reason} | ${file.sizeBytes ?? "unknown"} | ${file.limitBytes} |`,
          ),
          "",
        ]
      : []),
  ];
  return lines.join("\n");
}

export default function App() {
  const [repoPath, setRepoPath] = useState(".");
  const [searchQuery, setSearchQuery] = useState("");
  const [languageFilter, setLanguageFilter] = useState("all");
  const [complexityFilter, setComplexityFilter] = useState("all");
  const [graph, setGraph] = useState<RepoGraph | null>(null);
  const [selectedNode, setSelectedNode] = useState<RepoNode | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [loadingGraph, setLoadingGraph] = useState(false);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const stats = useMemo(() => {
    if (!graph) return null;
    return [
      { label: "Files", value: graph.totalFiles },
      { label: "Imports", value: graph.edges.length },
      { label: "LoC", value: graph.totalLoc },
    ];
  }, [graph]);

  const languageOptions = useMemo(() => {
    if (!graph) return [];
    return Array.from(new Set(graph.nodes.map((node) => node.language))).sort();
  }, [graph]);

  const hotspots = useMemo(() => {
    if (!graph) return [];
    return [...graph.nodes]
      .sort((a, b) => b.hotspotScore - a.hotspotScore || b.loc - a.loc)
      .slice(0, 6);
  }, [graph]);

  const topDirectories = useMemo(() => {
    if (!graph) return [];
    return graph.directories.slice(0, 5);
  }, [graph]);

  const nodesById = useMemo(() => {
    if (!graph) return new Map<string, RepoNode>();
    return new Map(graph.nodes.map((node) => [node.id, node]));
  }, [graph]);

  const selectedDependencies = useMemo(() => {
    if (!selectedNode) return { incoming: [] as RepoNode[], outgoing: [] as RepoNode[] };

    const incoming = edges
      .filter((edge) => edge.target === selectedNode.id)
      .map((edge) => nodesById.get(edge.source))
      .filter((node): node is RepoNode => Boolean(node));
    const outgoing = edges
      .filter((edge) => edge.source === selectedNode.id)
      .map((edge) => nodesById.get(edge.target))
      .filter((node): node is RepoNode => Boolean(node));

    return { incoming, outgoing };
  }, [edges, nodesById, selectedNode]);

  const dependencyNeighborhood = useMemo(() => {
    if (!selectedNode) return new Set<string>();
    return new Set([
      selectedNode.id,
      ...selectedDependencies.incoming.map((node) => node.id),
      ...selectedDependencies.outgoing.map((node) => node.id),
    ]);
  }, [selectedDependencies, selectedNode]);

  const matchesFilters = useCallback(
    (node: RepoNode) => {
      const query = searchQuery.trim().toLowerCase();
      const matchesSearch =
        !query ||
        node.path.toLowerCase().includes(query) ||
        node.language.toLowerCase().includes(query) ||
        node.imports.some((name) => name.toLowerCase().includes(query));
      const matchesLanguage = languageFilter === "all" || node.language === languageFilter;
      const matchesComplexity =
        complexityFilter === "all" || complexityLevel(node.complexity) === complexityFilter;
      return matchesSearch && matchesLanguage && matchesComplexity;
    },
    [complexityFilter, languageFilter, searchQuery],
  );

  const visibleNodeIds = useMemo(() => {
    return new Set(
      nodes.filter((node) => matchesFilters(node.data as RepoNode)).map((node) => node.id),
    );
  }, [matchesFilters, nodes]);

  const visibleStats = useMemo(() => {
    const visibleNodes = nodes.filter((node) => visibleNodeIds.has(node.id));
    const visibleEdges = edges.filter(
      (edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target),
    );
    return {
      files: visibleNodes.length,
      imports: visibleEdges.length,
    };
  }, [edges, nodes, visibleNodeIds]);

  const renderedNodes = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        hidden: !visibleNodeIds.has(node.id),
        data: {
          ...(node.data as RepoNode),
          selected: selectedNode?.id === node.id,
          relation: selectedNode
            ? node.id === selectedNode.id
              ? "selected"
              : dependencyNeighborhood.has(node.id)
                ? "connected"
                : "dimmed"
            : "none",
        },
      })),
    [dependencyNeighborhood, nodes, selectedNode, visibleNodeIds],
  );

  const renderedEdges = useMemo(
    () =>
      edges.map((edge) => ({
        ...edge,
        hidden: !visibleNodeIds.has(edge.source) || !visibleNodeIds.has(edge.target),
        animated: selectedNode ? edge.source === selectedNode.id || edge.target === selectedNode.id : edge.animated,
        style: {
          ...(edge.style ?? {}),
          stroke:
            selectedNode && (edge.source === selectedNode.id || edge.target === selectedNode.id)
              ? "#116466"
              : "#9aa9b3",
          opacity:
            selectedNode && edge.source !== selectedNode.id && edge.target !== selectedNode.id ? 0.24 : 1,
          strokeWidth:
            selectedNode && (edge.source === selectedNode.id || edge.target === selectedNode.id) ? 3 : 2,
        },
      })),
    [edges, selectedNode, visibleNodeIds],
  );

  const loadAiStatus = useCallback(async () => {
    try {
      setAiStatus(await fetchAiStatus());
    } catch (err) {
      setAiStatus(null);
      setError(err instanceof Error ? err.message : "Unable to load AI status");
    }
  }, []);

  useEffect(() => {
    void loadAiStatus();
  }, [loadAiStatus]);

  const loadGraph = useCallback(async () => {
    setLoadingGraph(true);
    setError(null);
    setSummary(null);
    setSelectedNode(null);
    try {
      const nextGraph = await analyzeRepository(repoPath);
      setGraph(nextGraph);
      setNodes(buildFlowNodes(nextGraph));
      setEdges(buildFlowEdges(nextGraph));
      setSearchQuery("");
      setLanguageFilter("all");
      setComplexityFilter("all");
      void loadAiStatus();
    } catch (err) {
      setGraph(null);
      setNodes([]);
      setEdges([]);
      setError(err instanceof Error ? err.message : "Unable to analyze repository");
    } finally {
      setLoadingGraph(false);
    }
  }, [loadAiStatus, repoPath, setEdges, setNodes]);

  const selectNode = useCallback(
    async (nodeData: RepoNode) => {
      if (!graph) return;
      setSelectedNode(nodeData);
      setSummary(null);
      setLoadingSummary(true);
      setError(null);
      try {
        setSummary(await summarizeFile(graph.root, nodeData.path));
        await loadAiStatus();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to summarize file");
      } finally {
        setLoadingSummary(false);
      }
    },
    [graph, loadAiStatus],
  );

  const handleNodeClick = useCallback(
    async (_event: MouseEvent, node: Node<RepoNode>) => {
      await selectNode(node.data);
    },
    [selectNode],
  );

  const exportGraphJson = useCallback(() => {
    if (!graph) return;
    const filename = `${safeFilename(graph.root)}-graph.json`;
    downloadTextFile(filename, JSON.stringify(graph, null, 2), "application/json");
  }, [graph]);

  const exportMarkdownReport = useCallback(() => {
    if (!graph) return;
    const filename = `${safeFilename(graph.root)}-analysis-report.md`;
    downloadTextFile(filename, buildMarkdownReport(graph, aiStatus), "text/markdown");
  }, [aiStatus, graph]);

  return (
    <main className="app-shell">
      <section className="toolbar" aria-label="Repository controls">
        <div className="brand">
          <GitBranch size={22} aria-hidden="true" />
          <div>
            <h1>Repository Graph</h1>
            <p>Dependency map, file metrics, and AI summaries</p>
          </div>
        </div>

        <form
          className="scan-form"
          onSubmit={(event) => {
            event.preventDefault();
            void loadGraph();
          }}
        >
          <label className="path-input">
            <Search size={18} aria-hidden="true" />
            <input
              value={repoPath}
              onChange={(event) => setRepoPath(event.target.value)}
              placeholder="C:/path/to/repository"
            />
          </label>
          <button type="submit" disabled={loadingGraph}>
            {loadingGraph ? <Loader2 className="spin" size={18} /> : <RefreshCw size={18} />}
            Analyze
          </button>
        </form>

        <button type="button" className="ai-status" onClick={() => void loadAiStatus()}>
          <PlugZap size={17} aria-hidden="true" />
          <span>
            <strong>{aiStatus ? aiStatus.activeProvider : "AI"}</strong>
            <small>
              {aiStatus
                ? `${aiStatus.model} - ${aiStatus.cacheEntries} cached`
                : "status"}
            </small>
          </span>
        </button>

        {stats && (
          <div className="stat-strip">
            {stats.map((item) => (
              <div className="stat" key={item.label}>
                <span>{item.value}</span>
                <small>{item.label}</small>
              </div>
            ))}
          </div>
        )}
      </section>

      {error && <div className="error-banner">{error}</div>}

      {graph?.warnings.length ? (
        <div className="warning-banner">
          <strong>{graph.warnings[0]}</strong>
          {graph.skippedFiles.length > 0 && <span>{graph.skippedFiles[0].path}</span>}
        </div>
      ) : null}

      {graph && (
        <section className="filter-bar" aria-label="Graph filters">
          <div className="filter-bar__label">
            <Filter size={18} aria-hidden="true" />
            <span>
              Showing {visibleStats.files} of {graph.totalFiles} files and {visibleStats.imports} of{" "}
              {graph.edges.length} imports
            </span>
          </div>

          <label className="compact-input">
            <Search size={16} aria-hidden="true" />
            <input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Find path, language, import"
            />
          </label>

          <select
            aria-label="Filter by language"
            value={languageFilter}
            onChange={(event) => setLanguageFilter(event.target.value)}
          >
            <option value="all">All languages</option>
            {languageOptions.map((language) => (
              <option value={language} key={language}>
                {language}
              </option>
            ))}
          </select>

          <select
            aria-label="Filter by complexity"
            value={complexityFilter}
            onChange={(event) => setComplexityFilter(event.target.value)}
          >
            <option value="all">All complexity</option>
            <option value="low">Low complexity</option>
            <option value="medium">Medium complexity</option>
            <option value="high">High complexity</option>
          </select>

          <button
            type="button"
            className="ghost-button"
            onClick={() => {
              setSearchQuery("");
              setLanguageFilter("all");
              setComplexityFilter("all");
            }}
          >
            <X size={16} aria-hidden="true" />
            Reset
          </button>

          <button type="button" className="ghost-button" onClick={exportGraphJson}>
            <Download size={16} aria-hidden="true" />
            JSON
          </button>

          <button type="button" className="ghost-button" onClick={exportMarkdownReport}>
            <FileText size={16} aria-hidden="true" />
            Report
          </button>
        </section>
      )}

      <section className="workspace">
        <div className="canvas">
          {graph ? (
            <ReactFlow
              nodes={renderedNodes}
              edges={renderedEdges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={handleNodeClick}
              fitView
            >
              <Background />
              <MiniMap nodeStrokeWidth={3} zoomable pannable />
              <Controls />
            </ReactFlow>
          ) : (
            <div className="empty-state">
              <GitBranch size={44} aria-hidden="true" />
              <h2>Scan a local repository</h2>
              <p>Enter a folder path and the analyzer will map files, imports, LoC, and complexity.</p>
            </div>
          )}
        </div>

        <aside className="details-panel" aria-label="Selected file details">
          {selectedNode ? (
            <>
              <div className="details-header">
                <h2>{selectedNode.label}</h2>
                <span>{selectedNode.language}</span>
              </div>
              <p className="selected-path">{selectedNode.path}</p>
              <div className="metric-grid">
                <div>
                  <strong>{selectedNode.loc}</strong>
                  <span>Lines</span>
                </div>
                <div>
                  <strong>{selectedNode.complexity}</strong>
                  <span>Complexity</span>
                </div>
                <div>
                  <strong>{selectedNode.imports.length}</strong>
                  <span>Imports</span>
                </div>
                <div>
                  <strong>{selectedNode.fanIn}</strong>
                  <span>Used By</span>
                </div>
                <div>
                  <strong>{selectedNode.fanOut}</strong>
                  <span>Uses</span>
                </div>
                <div>
                  <strong>{selectedNode.hotspotScore}</strong>
                  <span>Hotspot</span>
                </div>
              </div>

              <section className="imports-box">
                <h3>Detected Imports</h3>
                {selectedNode.imports.length > 0 ? (
                  <ul>
                    {selectedNode.imports.slice(0, 12).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No imports detected for this file.</p>
                )}
              </section>

              <section className="dependency-box">
                <h3>Dependency Neighborhood</h3>
                <div className="dependency-columns">
                  <div>
                    <h4>
                      <ArrowDownLeft size={15} aria-hidden="true" />
                      Used By
                    </h4>
                    {selectedDependencies.incoming.length > 0 ? (
                      <div className="dependency-list">
                        {selectedDependencies.incoming.map((node) => (
                          <button type="button" key={node.id} onClick={() => void selectNode(node)}>
                            <strong>{node.label}</strong>
                            <small>{node.path}</small>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <p className="muted">No internal files import this file.</p>
                    )}
                  </div>

                  <div>
                    <h4>
                      <ArrowUpRight size={15} aria-hidden="true" />
                      Uses
                    </h4>
                    {selectedDependencies.outgoing.length > 0 ? (
                      <div className="dependency-list">
                        {selectedDependencies.outgoing.map((node) => (
                          <button type="button" key={node.id} onClick={() => void selectNode(node)}>
                            <strong>{node.label}</strong>
                            <small>{node.path}</small>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <p className="muted">No internal outgoing dependencies detected.</p>
                    )}
                  </div>
                </div>
              </section>

              <section className="summary-box">
                <h3>AI Summary</h3>
                {loadingSummary && (
                  <p className="muted">
                    <Loader2 className="spin inline-icon" size={16} />
                    Generating summary...
                  </p>
                )}
                {summary && (
                  <>
                    <p>{summary.summary}</p>
                    <small>
                      {summary.cached ? "Loaded from cache" : "Stored in cache"}
                      {aiStatus ? ` - ${aiStatus.activeProvider} / ${aiStatus.model}` : ""}
                    </small>
                  </>
                )}
              </section>
            </>
          ) : (
            <div className="panel-empty">
              {graph ? (
                <>
                  <div className="details-header">
                    <h2>Overview</h2>
                    <span>{graph.directories.length} dirs</span>
                  </div>
                  <p>Directory rollups and files that deserve an early look.</p>

                  {graph.skippedFiles.length > 0 && (
                    <section className="skipped-box">
                      <h3>Skipped Files</h3>
                      <div className="skipped-list">
                        {graph.skippedFiles.slice(0, 5).map((file) => (
                          <div key={file.path}>
                            <strong>{file.path}</strong>
                            <small>
                              {file.reason} - {file.sizeBytes ?? "unknown"} bytes
                            </small>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  <section className="directory-box">
                    <h3>
                      <FolderTree size={16} aria-hidden="true" />
                      Directories
                    </h3>
                    <div className="directory-list">
                      {topDirectories.map((directory) => (
                        <button
                          type="button"
                          key={directory.path}
                          onClick={() => setSearchQuery(directory.path === "root" ? "" : `${directory.path}/`)}
                        >
                          <span className="directory-main">
                            <strong>{directory.path}</strong>
                            <small>
                              {directory.files} files - {directory.totalLoc} LoC - avg complexity{" "}
                              {directory.avgComplexity}
                            </small>
                          </span>
                          <span className="directory-links">
                            {directory.incomingImports} in - {directory.outgoingImports} out
                          </span>
                        </button>
                      ))}
                    </div>
                  </section>

                  <section className="hotspot-box">
                    <h3>
                      <Flame size={16} aria-hidden="true" />
                      Hotspots
                    </h3>
                    <p>Ranked by LoC, complexity, and dependency pressure.</p>
                  </section>
                  <div className="hotspot-list">
                    {hotspots.map((node, index) => (
                      <button type="button" key={node.id} onClick={() => void selectNode(node)}>
                        <span className="hotspot-rank">{index + 1}</span>
                        <span className="hotspot-main">
                          <strong>{node.label}</strong>
                          <small>{node.path}</small>
                        </span>
                        <span className="hotspot-score">
                          <Flame size={14} aria-hidden="true" />
                          {node.hotspotScore}
                        </span>
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <>
                  <h2>No file selected</h2>
                  <p>Click any node to inspect metrics and request a cached AI explanation.</p>
                </>
              )}
            </div>
          )}
        </aside>
      </section>
    </main>
  );
}
