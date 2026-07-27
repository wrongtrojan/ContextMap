"use client";

import { FileQuestion } from "lucide-react";

export default function EmptyEditorPane() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-dracula-comment gap-4">
      <FileQuestion size={48} className="opacity-40" />
      <div className="text-center">
        <p className="text-sm font-mono text-dracula-fg/80">No editor open</p>
        <p className="text-xs mt-1">Select a ready asset from Explorer to preview</p>
      </div>
    </div>
  );
}
