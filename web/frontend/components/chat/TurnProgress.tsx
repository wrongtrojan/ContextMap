"use client";

import type { ChatStatus } from "../../lib/types";
import { cn } from "../../lib/utils";

const STEPS: { key: ChatStatus; label: string }[] = [
  { key: "preparing", label: "Prepare" },
  { key: "researching", label: "Research" },
  { key: "evaluating", label: "Evaluate" },
  { key: "strengthening", label: "Strengthen" },
  { key: "finalizing", label: "Finalize" },
];

interface TurnProgressProps {
  status: ChatStatus;
  currentStep?: string | null;
}

export default function TurnProgress({ status, currentStep }: TurnProgressProps) {
  if (status === "idle" || status === "failed") return null;

  const activeIdx = STEPS.findIndex((s) => s.key === status);

  return (
    <div className="px-3 py-2 border-b border-dracula-comment/20 bg-dracula-current/30 shrink-0">
      <div className="flex items-center gap-1">
        {STEPS.map((step, i) => (
          <div key={step.key} className="flex-1 flex flex-col items-center gap-1">
            <div
              className={cn(
                "h-1 w-full rounded-full transition-colors",
                i < activeIdx
                  ? "bg-dracula-purple/70"
                  : i === activeIdx
                    ? "bg-dracula-purple"
                    : "bg-dracula-comment/30",
              )}
            />
            <span
              className={cn(
                "text-[8px] font-mono uppercase tracking-wide",
                i === activeIdx ? "text-dracula-purple" : i < activeIdx ? "text-dracula-comment" : "text-dracula-comment/50",
              )}
            >
              {step.label}
            </span>
          </div>
        ))}
      </div>
      {currentStep && (
        <p className="text-[10px] font-mono text-dracula-cyan mt-1.5 truncate">{currentStep}</p>
      )}
    </div>
  );
}
