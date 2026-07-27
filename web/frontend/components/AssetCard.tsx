"use client";

import { FileText, PlayCircle, Mic, Loader2, Zap, Database, Search, Cpu, AlertCircle, Trash2 } from "lucide-react";
import type { Asset, AssetStatus } from "../lib/types";
import { cn } from "../lib/utils";

interface AssetCardProps {
  asset: Asset;
  onSelect: (id: string) => void;
  onDelete?: (id: string) => void;
  isSelected: boolean;
}

const PROCESSING: AssetStatus[] = [
  "uploading",
  "recognizing",
  "embedding",
  "structuring",
  "kg_extracting",
  "ingesting",
];

function ModalityIcon({ modality, ready }: { modality: Asset["modality"]; ready: boolean }) {
  const cls = ready ? (modality === "pdf" ? "text-dracula-cyan" : "text-dracula-pink") : "text-dracula-comment";
  if (modality === "pdf") return <FileText size={24} className={cls} />;
  if (modality === "audio") return <Mic size={24} className={cls} />;
  return <PlayCircle size={24} className={cls} />;
}

export default function AssetCard({ asset, onSelect, onDelete, isSelected }: AssetCardProps) {
  const s = asset.status;
  const isReady = s === "ready";
  const isFailed = s === "failed";
  const isUploading = s === "uploading";
  const isRaw = s === "raw";
  const isProcessing = PROCESSING.includes(s);

  const getStatusConfig = () => {
    if (isFailed) return { color: "text-dracula-red", border: "border-dracula-red", label: "FAILED", icon: <AlertCircle size={10} /> };
    if (isUploading) return { color: "text-dracula-orange", border: "border-dracula-orange", label: "UPLOADING", icon: <Loader2 size={10} className="animate-spin" /> };
    if (isRaw) return { color: "text-dracula-purple", border: "border-dracula-purple", label: "RAW", icon: <Database size={10} /> };
    if (isProcessing) return { color: "text-dracula-yellow", border: "border-dracula-yellow", label: s.toUpperCase(), icon: <Cpu size={10} className="animate-pulse" /> };
    return { color: "text-dracula-green", border: "border-dracula-green", label: "READY", icon: <Zap size={10} /> };
  };

  const config = getStatusConfig();

  return (
    <div
      onClick={() => isReady && onSelect(asset.id)}
      className={cn(
        "p-3 border rounded flex flex-col justify-between transition-all duration-300 relative overflow-hidden group",
        isSelected
          ? "ring-1 ring-dracula-purple shadow-[0_0_15px_rgba(189,147,249,0.15)] bg-dracula-current border-dracula-purple"
          : "border-dracula-comment bg-dracula-bg",
        isReady ? "cursor-pointer hover:border-dracula-pink" : "cursor-default",
      )}
    >
      <div className="flex items-start justify-between z-10">
        <div className="flex items-center gap-3 min-w-0">
          <ModalityIcon modality={asset.modality} ready={isReady} />
          <div className="overflow-hidden min-w-0">
            <p className="text-sm font-bold truncate text-dracula-fg">{asset.name}</p>
            <p className="text-[10px] text-dracula-comment font-mono uppercase tracking-tighter">
              {asset.modality} • {isReady ? "Indexed" : "Processing"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <div className={cn("text-[9px] font-mono px-1.5 py-0.5 rounded border uppercase tracking-widest", config.border, config.color)}>
            {config.label}
          </div>
          {onDelete && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(asset.id);
              }}
              className="p-1 text-dracula-comment hover:text-dracula-red opacity-0 group-hover:opacity-100"
              title="Delete asset"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>

      <div className="mt-3 min-h-6 z-10">
        {isProcessing || isUploading ? (
          <div className="space-y-1.5">
            <div className={cn("flex items-center gap-1.5 text-[10px] font-mono", config.color)}>
              {config.icon}
              {asset.current_step || s.toUpperCase()}
            </div>
            <div className="w-full bg-dracula-current h-1 rounded-full overflow-hidden relative border border-dracula-comment/20">
              <div className={cn("h-full w-1/3 absolute bg-current shadow-[0_0_8px_currentColor] animate-infinite-scroll", config.color)} />
            </div>
          </div>
        ) : isFailed ? (
          <p className="text-[10px] font-mono text-dracula-red/90 line-clamp-2">{asset.error_message || "Pipeline failed"}</p>
        ) : isRaw ? (
          <div className="flex items-center gap-2 text-[10px] font-mono text-dracula-comment italic">
            <span>{">_"}</span> <span>Awaiting pipeline</span>
          </div>
        ) : (
          <div className="text-[10px] font-mono text-dracula-green/90 font-bold flex items-center gap-1.5">
            <Zap size={10} /> Ready for preview
          </div>
        )}
      </div>

      {isReady && asset.triple_count != null && asset.triple_count > 0 && (
        <div className="mt-2 text-[9px] text-dracula-comment font-mono flex items-center gap-1">
          <Search size={9} /> {asset.triple_count} triples
        </div>
      )}
    </div>
  );
}
