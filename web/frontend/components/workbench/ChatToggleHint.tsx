"use client";

export default function ChatToggleHint() {
  return (
    <div className="absolute right-4 bottom-4 z-30 pointer-events-none">
      <span className="text-[10px] font-mono text-dracula-comment/60">Ctrl+L to toggle chat</span>
    </div>
  );
}
