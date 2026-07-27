"use client";

import { Network } from "lucide-react";

export default function KgComingSoonPane() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-8 gap-3">
      <div className="w-12 h-12 rounded-full bg-dracula-current/40 flex items-center justify-center text-dracula-purple">
        <Network size={24} />
      </div>
      <div>
        <p className="text-sm font-mono text-dracula-fg mb-1">Knowledge Graph</p>
        <p className="text-xs text-dracula-comment max-w-sm">
          图谱浏览与实体检索功能即将上线
        </p>
        <p className="text-[10px] text-dracula-comment/70 mt-2 font-mono">
          可在 Settings 中预先配置 KG 相关选项
        </p>
      </div>
    </div>
  );
}
