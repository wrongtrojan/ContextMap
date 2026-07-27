"use client";

import { Plus, ChevronDown, Trash2 } from "lucide-react";
import { useState } from "react";
import type { ChatSessionSummary } from "../../lib/types";
import MessageList from "../chat/MessageList";
import ChatInput from "../chat/ChatInput";
import TurnProgress from "../chat/TurnProgress";
import ChatErrorBanner from "../chat/ChatErrorBanner";
import PanelHeader from "../workbench/PanelHeader";
import type { useChatSession } from "../../lib/hooks/useChatSession";

type ChatHook = ReturnType<typeof useChatSession>;

interface ChatViewProps extends ChatHook {
  onEvidenceJump: (
    assetId: string,
    anchor: number,
    bbox?: string,
    assetName?: string,
  ) => void;
  onDeleteSession: (sessionId: string) => void;
}

export default function ChatView({
  sessions,
  activeSessionId,
  setActiveSessionId,
  detail,
  streaming,
  turnStatus,
  currentStep,
  lastError,
  newSession,
  sendMessage,
  onEvidenceJump,
  onDeleteSession,
}: ChatViewProps) {
  const [listOpen, setListOpen] = useState(false);
  const activeName = sessions.find((s) => s.session_id === activeSessionId)?.chat_name ?? "Chat";

  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title={activeName}
        className="bg-[var(--wb-chatpanel-bg)]"
        actions={
          <>
            {activeSessionId && (
              <button
                type="button"
                onClick={() => onDeleteSession(activeSessionId)}
                className="p-1 text-dracula-comment hover:text-dracula-red"
                title="Delete current session"
              >
                <Trash2 size={14} />
              </button>
            )}
            <button
              type="button"
              onClick={() => void newSession()}
              className="p-1 text-dracula-comment hover:text-dracula-green"
              title="New session"
            >
              <Plus size={14} />
            </button>
          </>
        }
      >
        <button
          type="button"
          className="flex items-center gap-1 text-xs font-mono text-dracula-fg hover:text-dracula-purple truncate"
          onClick={() => setListOpen(!listOpen)}
        >
          <ChevronDown size={12} className={listOpen ? "" : "-rotate-90"} />
          <span className="truncate max-w-[140px]">{activeName}</span>
        </button>
      </PanelHeader>

      {listOpen && (
        <div className="border-b border-dracula-comment/20 max-h-32 overflow-y-auto custom-scrollbar">
          {sessions.map((s) => (
            <SessionRow
              key={s.session_id}
              session={s}
              active={s.session_id === activeSessionId}
              onSelect={() => {
                setActiveSessionId(s.session_id);
                setListOpen(false);
              }}
              onDelete={() => onDeleteSession(s.session_id)}
            />
          ))}
        </div>
      )}

      <ChatErrorBanner message={lastError ?? (turnStatus === "failed" ? "Turn failed" : null)} />
      <TurnProgress status={turnStatus} currentStep={currentStep} />

      <MessageList
        messages={detail?.messages ?? []}
        evidences={detail?.evidences ?? []}
        onEvidenceJump={onEvidenceJump}
      />
      <ChatInput onSend={(msg) => void sendMessage(msg)} disabled={streaming || !activeSessionId} />
    </div>
  );
}

function SessionRow({
  session,
  active,
  onSelect,
  onDelete,
}: {
  session: ChatSessionSummary;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={`group flex items-center w-full px-3 py-1.5 text-xs font-mono hover:bg-dracula-current/50 ${
        active ? "text-dracula-purple bg-dracula-current/30" : "text-dracula-comment"
      }`}
    >
      <button type="button" onClick={onSelect} className="flex-1 truncate text-left">
        {session.chat_name}
      </button>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="p-1 text-dracula-comment hover:text-dracula-red shrink-0"
        title="Delete session"
      >
        <Trash2 size={12} />
      </button>
    </div>
  );
}
