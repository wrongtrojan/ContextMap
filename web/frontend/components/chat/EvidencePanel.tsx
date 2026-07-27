"use client";

import type { Evidence } from "../../lib/types";
import EvidenceCard from "../EvidenceCard";

interface EvidencePanelProps {
  evidences: Evidence[];
  onJump: (
    assetId: string,
    anchor: number,
    bbox?: string,
    assetName?: string,
  ) => void;
}

/** Inline evidence block shown directly under the user question for this turn. */
export default function EvidencePanel({ evidences, onJump }: EvidencePanelProps) {
  if (evidences.length === 0) return null;

  return (
    <div className="w-full max-w-[85%] ml-0 mr-auto rounded-lg border border-dracula-cyan/25 bg-dracula-current/25 px-2.5 py-2">
      <p className="text-[10px] font-mono uppercase text-dracula-cyan/80 mb-1.5 tracking-widest">
        Evidence · {evidences.length}
      </p>
      <div className="space-y-1.5 max-h-40 overflow-y-auto custom-scrollbar">
        {evidences.map((ev, i) => (
          <EvidenceCard key={ev.id ?? i} evidence={ev} onJump={onJump} />
        ))}
      </div>
    </div>
  );
}
