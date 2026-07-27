"use client";

import { Minus, Plus } from "lucide-react";
import { cn } from "../../lib/utils";

interface ZoomControlsProps {
  scale: number;
  min?: number;
  max?: number;
  step?: number;
  onScaleChange: (scale: number) => void;
  className?: string;
}

export function clampScale(value: number, min = 0.5, max = 3): number {
  return Math.min(max, Math.max(min, Math.round(value * 100) / 100));
}

export function handleZoomWheel(
  e: React.WheelEvent,
  scale: number,
  onScaleChange: (scale: number) => void,
  min = 0.5,
  max = 3,
) {
  if (!e.ctrlKey && !e.metaKey) return;
  e.preventDefault();
  onScaleChange(clampScale(scale - e.deltaY * 0.001, min, max));
}

/** Top-right +/- zoom control (no bottom slider). */
export default function ZoomControls({
  scale,
  min = 0.5,
  max = 3,
  step = 0.1,
  onScaleChange,
  className,
}: ZoomControlsProps) {
  const pct = Math.round(scale * 100);

  return (
    <div
      className={cn(
        "absolute top-3 right-3 z-40 flex items-center gap-0.5 rounded-md border border-dracula-comment/40 bg-dracula-bg/90 backdrop-blur-sm shadow-lg",
        className,
      )}
    >
      <button
        type="button"
        title="Zoom out"
        disabled={scale <= min}
        onClick={() => onScaleChange(clampScale(scale - step, min, max))}
        className="p-1.5 text-dracula-comment hover:text-dracula-fg hover:bg-dracula-purple/20 disabled:opacity-30 disabled:pointer-events-none"
      >
        <Minus size={14} />
      </button>
      <button
        type="button"
        title="Reset zoom"
        onClick={() => onScaleChange(1)}
        className="min-w-[3rem] px-1 text-[10px] font-mono text-dracula-comment hover:text-dracula-fg"
      >
        {pct}%
      </button>
      <button
        type="button"
        title="Zoom in"
        disabled={scale >= max}
        onClick={() => onScaleChange(clampScale(scale + step, min, max))}
        className="p-1.5 text-dracula-comment hover:text-dracula-fg hover:bg-dracula-purple/20 disabled:opacity-30 disabled:pointer-events-none"
      >
        <Plus size={14} />
      </button>
    </div>
  );
}
