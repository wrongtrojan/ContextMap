"use client";

import ChatView from "../sidebar/ChatView";
import type { useChatSession } from "../../lib/hooks/useChatSession";

type ChatHook = ReturnType<typeof useChatSession>;

interface ChatPanelProps extends ChatHook {
  onEvidenceJump: (
    assetId: string,
    anchor: number,
    bbox?: string,
    assetName?: string,
  ) => void;
  onDeleteSession: (sessionId: string) => void;
}

export default function ChatPanel({ onEvidenceJump, onDeleteSession, ...chat }: ChatPanelProps) {
  return (
    <div className="h-full w-full flex flex-col overflow-hidden">
      <ChatView {...chat} onEvidenceJump={onEvidenceJump} onDeleteSession={onDeleteSession} />
    </div>
  );
}
