"use client";

import { FileText, PlayCircle, Mic } from "lucide-react";
import type { Evidence } from "../lib/types";
import { formatAnchor } from "../lib/utils";

interface EvidenceCardProps {
  evidence: Evidence;
  onJump: (
    assetId: string,
    anchor: number,
    bbox?: string,
    assetName?: string,
  ) => void;
}

/** Serialize bbox whether stored as JSON string or number[]. */
export function normalizeBbox(raw: unknown): string | undefined {
  if (raw == null) return undefined;
  if (typeof raw === "string") {
    const trimmed = raw.trim();
    if (!trimmed) return undefined;
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed) && parsed.length >= 4) return JSON.stringify(parsed.slice(0, 4));
    } catch {
      return trimmed;
    }
    return trimmed;
  }
  if (Array.isArray(raw) && raw.length >= 4) {
    return JSON.stringify(raw.slice(0, 4).map(Number));
  }
  return undefined;
}

export default function EvidenceCard({ evidence, onJump }: EvidenceCardProps) {
  const { metadata, content } = evidence;
  const modality = metadata.modality ?? "pdf";
  const isVideo = modality === "video";
  const isAudio = modality === "audio";
  const anchor = isVideo || isAudio ? (metadata.timestamp ?? 0) : (metadata.page_label ?? 1);
  const assetId = metadata.asset_id ?? "";
  const assetName = metadata.asset_name;
  const bbox = normalizeBbox(metadata.bbox);

  return (
    <div
      onClick={() => {
        if (!assetId && !assetName) return;
        onJump(assetId, anchor, bbox, assetName);
      }}
      className="group flex flex-col gap-1.5 p-2 bg-dracula-bg/40 border border-dracula-comment/20 rounded-md hover:border-dracula-pink/50 transition-all cursor-pointer"
    >
      <div className="flex items-center justify-between text-[10px]">
        <div className="flex items-center gap-1.5 text-dracula-cyan truncate">
          {isVideo ? <PlayCircle size={12} /> : isAudio ? <Mic size={12} /> : <FileText size={12} />}
          <span className="truncate max-w-[150px] font-mono">{assetName ?? assetId.slice(-8)}</span>
        </div>
        <span className="text-dracula-purple font-mono bg-dracula-purple/10 px-1.5 py-0.5 rounded">
          {formatAnchor(anchor, modality)}
        </span>
      </div>
      {content && (
        <p className="text-[10px] text-dracula-comment italic line-clamp-2 leading-tight">&ldquo;{content}&rdquo;</p>
      )}
    </div>
  );
}
