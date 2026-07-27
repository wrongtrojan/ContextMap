"use client";

import { useRef, useEffect, useMemo } from "react";
import type { ChatMessage, Evidence } from "../../lib/types";
import MarkdownRenderer from "../MarkdownRenderer";
import EvidencePanel from "./EvidencePanel";
import { Loader2 } from "lucide-react";

interface MessageListProps {
  messages: ChatMessage[];
  evidences?: Evidence[];
  onEvidenceJump?: (
    assetId: string,
    anchor: number,
    bbox?: string,
    assetName?: string,
  ) => void;
}

type TimelineItem =
  | { kind: "message"; message: ChatMessage; key: string }
  | { kind: "evidence"; evidences: Evidence[]; key: string };

/**
 * Stable order per turn: User → Evidence → Assistant.
 * While the assistant bubble is still streaming (no id yet), attach orphan /
 * unmatched evidences to that open turn so they don't jump from below the
 * answer to above it after the turn completes.
 */
function buildTimeline(messages: ChatMessage[], evidences: Evidence[]): TimelineItem[] {
  const byAssistant = new Map<string, Evidence[]>();
  const orphans: Evidence[] = [];

  for (const ev of evidences) {
    if (ev.message_id) {
      const list = byAssistant.get(ev.message_id) ?? [];
      list.push(ev);
      byAssistant.set(ev.message_id, list);
    } else {
      orphans.push(ev);
    }
  }

  const usedAssistants = new Set<string>();
  const usedOrphans = new Set<Evidence>();
  const items: TimelineItem[] = [];

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    items.push({
      kind: "message",
      message: msg,
      key: msg.id ?? `msg-${i}`,
    });

    if (msg.role !== "user") continue;

    const next = messages[i + 1];
    if (next?.role !== "assistant") continue;

    let turnEvs: Evidence[] | undefined;
    if (next.id) {
      turnEvs = byAssistant.get(next.id);
      if (turnEvs?.length) usedAssistants.add(next.id);
    }

    // Open / streaming turn: pin unmatched evidences under this question.
    if ((!turnEvs || turnEvs.length === 0) && (next.streaming || !next.id)) {
      const openTurnEvs = [
        ...orphans,
        ...[...byAssistant.entries()]
          .filter(([id]) => !usedAssistants.has(id))
          .flatMap(([, list]) => list),
      ];
      if (openTurnEvs.length) {
        turnEvs = openTurnEvs;
        for (const ev of orphans) usedOrphans.add(ev);
        for (const [id] of byAssistant) {
          if (!usedAssistants.has(id)) usedAssistants.add(id);
        }
      }
    }

    if (turnEvs?.length) {
      items.push({
        kind: "evidence",
        evidences: turnEvs,
        key: `ev-${next.id ?? `turn-${i}`}`,
      });
    }
  }

  const leftover = [
    ...orphans.filter((ev) => !usedOrphans.has(ev)),
    ...[...byAssistant.entries()]
      .filter(([id]) => !usedAssistants.has(id))
      .flatMap(([, list]) => list),
  ];
  if (leftover.length > 0) {
    items.push({ kind: "evidence", evidences: leftover, key: "ev-orphan" });
  }

  return items;
}

function StreamingText({ content }: { content: string }) {
  return (
    <div className="whitespace-pre-wrap break-words text-sm leading-relaxed text-dracula-fg">
      {content}
      <span className="inline-block w-1.5 h-3.5 ml-0.5 align-middle bg-dracula-purple/80 animate-pulse" />
    </div>
  );
}

export default function MessageList({
  messages,
  evidences = [],
  onEvidenceJump,
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

  const timeline = useMemo(
    () => buildTimeline(messages, evidences),
    [messages, evidences],
  );

  const streaming = messages.some((m) => m.streaming);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onScroll = () => {
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      stickToBottomRef.current = distance < 80;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!stickToBottomRef.current) return;
    endRef.current?.scrollIntoView({
      behavior: streaming ? "auto" : "smooth",
      block: "end",
    });
  }, [timeline, streaming]);

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
      {timeline.map((item) => {
        if (item.kind === "evidence") {
          if (!onEvidenceJump) return null;
          return (
            <EvidencePanel
              key={item.key}
              evidences={item.evidences}
              onJump={onEvidenceJump}
            />
          );
        }

        const msg = item.message;
        return (
          <div
            key={item.key}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === "user"
                  ? "bg-dracula-purple/20 border border-dracula-purple/40 text-dracula-fg"
                  : "bg-dracula-current/50 border border-dracula-comment/20"
              }`}
            >
              {msg.role === "assistant" && msg.streaming && !msg.content ? (
                <Loader2 size={16} className="animate-spin text-dracula-purple" />
              ) : msg.role === "assistant" && msg.streaming ? (
                <StreamingText content={msg.content} />
              ) : (
                <MarkdownRenderer content={msg.content} />
              )}
            </div>
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
