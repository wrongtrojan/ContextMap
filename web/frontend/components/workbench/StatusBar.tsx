"use client";

import { useEffect, useState } from "react";
import { fetchApiHealth, fetchGlobalAssets, fetchGlobalChats } from "../../lib/api/status";
import type { ChatStatus } from "../../lib/types";

interface StatusBarProps {
  turnStatus?: ChatStatus;
  pipelineStep?: string | null;
}

export default function StatusBar({ turnStatus, pipelineStep }: StatusBarProps) {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [llmConfigured, setLlmConfigured] = useState<boolean | null>(null);
  const [assets, setAssets] = useState<{ active: number; queue: number } | null>(null);
  const [chats, setChats] = useState<{ activeTurns: number } | null>(null);

  useEffect(() => {
    const poll = async () => {
      const health = await fetchApiHealth();
      setConnected(health !== null);
      setLlmConfigured(health?.llm_configured ?? null);
      const ga = await fetchGlobalAssets().catch(() => null);
      const gc = await fetchGlobalChats().catch(() => null);
      if (ga) setAssets({ active: ga.active_pipelines, queue: ga.queue_length });
      if (gc) setChats({ activeTurns: gc.active_turns });
    };
    void poll();
    const id = setInterval(() => void poll(), 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="h-6 flex items-center justify-between px-3 text-[10px] font-mono bg-[var(--wb-statusbar-bg)] border-t border-dracula-comment/20 shrink-0">
      <div className="flex items-center gap-2">
        <span
          className={
            connected === null
              ? "text-dracula-comment"
              : connected
                ? "text-dracula-green"
                : "text-dracula-red"
          }
        >
          {connected === null ? "..." : connected ? "API connected" : "API offline"}
        </span>
        {connected && llmConfigured === false && (
          <span className="text-dracula-orange">LLM not configured</span>
        )}
      </div>
      <div className="text-dracula-comment truncate max-w-[40%]">
        {pipelineStep ? `Pipeline: ${pipelineStep}` : assets ? `Pipelines: ${assets.active} active, ${assets.queue} queued` : ""}
      </div>
      <div className="text-dracula-comment">
        {turnStatus && turnStatus !== "idle" && <span className="text-dracula-purple mr-2">{turnStatus}</span>}
        {chats && <span>Turns: {chats.activeTurns}</span>}
      </div>
    </div>
  );
}
