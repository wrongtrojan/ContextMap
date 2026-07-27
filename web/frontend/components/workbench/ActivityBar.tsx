"use client";

import { Files, Network, Settings } from "lucide-react";
import type { ActivityView } from "../../lib/types";
import { cn } from "../../lib/utils";

interface ActivityBarProps {
  activeActivity: ActivityView;
  onSelectActivity: (view: ActivityView) => void;
  onOpenSettings: () => void;
}

function ActivityButton({
  active,
  title,
  onClick,
  children,
}: {
  active: boolean;
  title: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={cn(
        "w-10 h-10 flex items-center justify-center rounded relative transition-colors",
        active
          ? "text-dracula-fg bg-dracula-current/40"
          : "text-dracula-comment hover:text-dracula-fg hover:bg-dracula-current/30",
      )}
    >
      {active && (
        <span
          className="absolute left-0 top-1/2 -translate-y-1/2 h-4 bg-dracula-purple rounded-r"
          style={{ width: "var(--wb-accent-bar-w)" }}
        />
      )}
      {children}
    </button>
  );
}

export default function ActivityBar({
  activeActivity,
  onSelectActivity,
  onOpenSettings,
}: ActivityBarProps) {
  return (
    <div className="w-12 flex flex-col items-center py-2 gap-1 bg-[var(--wb-activitybar-bg)] border-r border-dracula-comment/20 shrink-0">
      <ActivityButton
        active={activeActivity === "explorer"}
        title="Explorer"
        onClick={() => onSelectActivity("explorer")}
      >
        <Files size={20} />
      </ActivityButton>
      <ActivityButton
        active={activeActivity === "kg"}
        title="Knowledge Graph"
        onClick={() => onSelectActivity("kg")}
      >
        <Network size={20} />
      </ActivityButton>
      <div className="flex-1" />
      <ActivityButton
        active={activeActivity === "settings"}
        title="Settings"
        onClick={onOpenSettings}
      >
        <Settings size={20} />
      </ActivityButton>
    </div>
  );
}
