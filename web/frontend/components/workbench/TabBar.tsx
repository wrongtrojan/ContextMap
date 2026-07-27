"use client";

import { FileText, Mic, Network, PlayCircle, Settings, X } from "lucide-react";
import type { AssetModality, EditorTab } from "../../lib/types";
import { cn } from "../../lib/utils";

interface TabBarProps {
  tabs: EditorTab[];
  activeTabId: string | null;
  onSelect: (assetId: string) => void;
  onClose: (assetId: string) => void;
}

function TabIcon({ tab }: { tab: EditorTab }) {
  const cls = "shrink-0 text-dracula-comment";
  if (tab.kind === "kg") return <Network size={14} className={cls} />;
  if (tab.kind === "settings") return <Settings size={14} className={cls} />;
  const modality: AssetModality | undefined = tab.modality;
  if (modality === "pdf") return <FileText size={14} className="shrink-0 text-dracula-cyan/80" />;
  if (modality === "audio") return <Mic size={14} className="shrink-0 text-dracula-pink/80" />;
  if (modality === "video") return <PlayCircle size={14} className="shrink-0 text-dracula-pink/80" />;
  return <FileText size={14} className={cls} />;
}

function tabLabel(tab: EditorTab): string {
  if (tab.kind === "kg") return "Graph";
  if (tab.kind === "settings") return "Settings";
  return tab.name;
}

export default function TabBar({ tabs, activeTabId, onSelect, onClose }: TabBarProps) {
  if (tabs.length === 0) return null;

  return (
    <div
      className="flex items-center bg-[var(--wb-tabbar-bg)] border-b border-dracula-comment/20 overflow-x-auto custom-scrollbar shrink-0"
      style={{ height: "var(--wb-header-h)" }}
    >
      {tabs.map((tab) => {
        const active = activeTabId === tab.assetId;
        return (
          <div
            key={tab.assetId}
            className={cn(
              "group relative flex items-center gap-1.5 h-full px-3 border-r border-dracula-comment/20 cursor-pointer font-mono shrink-0 max-w-[160px]",
              active
                ? "bg-[var(--wb-tab-active)] text-dracula-fg"
                : "text-dracula-comment hover:bg-dracula-current/30 hover:text-dracula-fg",
            )}
            style={{ fontSize: "var(--wb-header-text)" }}
            onClick={() => onSelect(tab.assetId)}
          >
            {active && (
              <span
                className="absolute left-0 top-1/2 -translate-y-1/2 h-4 bg-dracula-purple rounded-r"
                style={{ width: "var(--wb-accent-bar-w)" }}
              />
            )}
            <TabIcon tab={tab} />
            <span className="truncate">{tabLabel(tab)}</span>
            <button
              type="button"
              className={cn(
                "p-0.5 hover:bg-dracula-comment/20 rounded shrink-0",
                active ? "opacity-60 hover:opacity-100" : "opacity-0 group-hover:opacity-100",
              )}
              onClick={(e) => {
                e.stopPropagation();
                onClose(tab.assetId);
              }}
            >
              <X size={12} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
