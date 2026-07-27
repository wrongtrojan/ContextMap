"use client";

import { cn } from "../../lib/utils";

interface PanelHeaderProps {
  title: string;
  actions?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}

export default function PanelHeader({ title, actions, className, children }: PanelHeaderProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-between shrink-0 border-b border-dracula-comment/20 bg-[var(--wb-tabbar-bg)]",
        "h-[var(--wb-header-h)] px-[var(--wb-header-px)]",
        className,
      )}
    >
      {children ?? (
        <span
          className="font-mono uppercase tracking-widest text-dracula-comment truncate"
          style={{ fontSize: "var(--wb-header-text)" }}
        >
          {title}
        </span>
      )}
      {actions && <div className="flex items-center gap-1 shrink-0">{actions}</div>}
    </div>
  );
}
