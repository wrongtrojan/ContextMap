"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import type { OutlineItem } from "../../lib/types";
import { formatAnchor } from "../../lib/utils";

interface OutlineViewProps {
  outline: OutlineItem[];
  loading: boolean;
  modality: "pdf" | "video" | "audio";
  onJump: (anchor: number) => void;
}

function OutlineNode({
  item,
  modality,
  onJump,
  depth = 0,
}: {
  item: OutlineItem;
  modality: "pdf" | "video" | "audio";
  onJump: (anchor: number) => void;
  depth?: number;
}) {
  const [open, setOpen] = useState(depth === 0);
  const hasChildren = item.sub_points && item.sub_points.length > 0;

  return (
    <div className="select-none">
      <div
        className="flex items-center gap-1 py-1 px-2 rounded hover:bg-dracula-current/50 cursor-pointer text-xs group"
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={() => onJump(item.anchor)}
      >
        {hasChildren ? (
          <button
            type="button"
            className="p-0.5 text-dracula-comment"
            onClick={(e) => {
              e.stopPropagation();
              setOpen(!open);
            }}
          >
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
        ) : (
          <span className="w-4" />
        )}
        <span className="flex-1 truncate text-dracula-fg group-hover:text-dracula-cyan">{item.heading}</span>
        <span className="text-[10px] font-mono text-dracula-purple shrink-0">{formatAnchor(item.anchor, modality)}</span>
      </div>
      {open &&
        item.sub_points?.map((sub, i) => (
          <div
            key={i}
            className="flex items-center gap-1 py-1 px-2 rounded hover:bg-dracula-current/50 cursor-pointer text-xs group"
            style={{ paddingLeft: `${(depth + 1) * 12 + 8}px` }}
            onClick={() => onJump(sub.anchor)}
          >
            <span className="w-4" />
            <span className="flex-1 truncate text-dracula-comment group-hover:text-dracula-cyan">{sub.heading}</span>
            <span className="text-[10px] font-mono text-dracula-purple shrink-0">{formatAnchor(sub.anchor, modality)}</span>
          </div>
        ))}
    </div>
  );
}

export default function OutlineView({ outline, loading, modality, onJump }: OutlineViewProps) {
  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 overflow-y-auto custom-scrollbar py-2 min-h-0">
        {loading && <p className="text-xs text-dracula-comment font-mono px-3">Loading structure...</p>}
        {!loading && outline.length === 0 && (
          <p className="text-xs text-dracula-comment font-mono px-3 py-4">Select a ready asset to view outline</p>
        )}
        {outline.map((item, i) => (
          <OutlineNode key={i} item={item} modality={modality} onJump={onJump} />
        ))}
      </div>
    </div>
  );
}
