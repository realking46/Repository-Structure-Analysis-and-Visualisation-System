import { Handle, NodeProps, Position } from "reactflow";
import { Braces, FileCode2 } from "lucide-react";
import type { RepoNode } from "../lib/api";

type FileNodeData = RepoNode & {
  relation?: "none" | "selected" | "connected" | "dimmed";
  selected?: boolean;
};

function complexityLevel(complexity: number): "low" | "medium" | "high" {
  if (complexity >= 18) return "high";
  if (complexity >= 8) return "medium";
  return "low";
}

export default function FileNode({ data, selected }: NodeProps<FileNodeData>) {
  const level = complexityLevel(data.complexity);

  return (
    <div
      className={`file-node complexity-${level}${selected || data.selected ? " is-selected" : ""} relation-${
        data.relation ?? "none"
      }`}
    >
      <Handle type="target" position={Position.Left} />
      <div className="file-node__top">
        <FileCode2 size={18} aria-hidden="true" />
        <span title={data.path}>{data.label}</span>
      </div>
      <div className="file-node__path" title={data.path}>
        {data.directory || "root"}
      </div>
      <div className="file-node__metrics">
        <span>{data.language}</span>
        <span>{data.loc} LoC</span>
        <span>
          <Braces size={14} aria-hidden="true" />
          {data.complexity}
        </span>
        <span>{data.hotspotScore} hot</span>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
