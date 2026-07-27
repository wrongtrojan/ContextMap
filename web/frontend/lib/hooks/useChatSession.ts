"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatSessionDetail, ChatSessionSummary, ChatStatus } from "../types";
import {
  createSession,
  fetchSessionDetail,
  listSessionSummaries,
  startTurn,
} from "../api/chats";
import { openChatStream, type ChatStreamPayload } from "../sse/chatStream";
import { sessionDeleteQueue } from "../sessionDeleteQueue";

export function useChatSession() {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ChatSessionDetail | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [turnStatus, setTurnStatus] = useState<ChatStatus>("idle");
  const [currentStep, setCurrentStep] = useState<string | null>(null);
  const [inferResults, setInferResults] = useState<Array<{ kind: string; summary: string }>>([]);
  const [lastError, setLastError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamRef = useRef<EventSource | null>(null);
  const pendingDeletesRef = useRef(new Set<string>());
  const streamingRef = useRef(false);

  useEffect(() => {
    streamingRef.current = streaming;
  }, [streaming]);

  const loadSessions = useCallback(async () => {
    try {
      const list = await listSessionSummaries();
      const pending = pendingDeletesRef.current;
      const filtered = list.filter((s) => !pending.has(s.session_id));
      setSessions(filtered);
      if (filtered.length > 0 && !activeSessionId) {
        setActiveSessionId(filtered[0].session_id);
      }
    } catch (e) {
      console.error("load sessions failed", e);
    }
  }, [activeSessionId]);

  const loadDetail = useCallback(async (sessionId: string) => {
    try {
      const d = await fetchSessionDetail(sessionId);
      if (!d) return;

      // While tokens are streaming, never replace the live assistant bubble.
      // Still merge evidence + assign message ids so timeline stays stable.
      if (streamingRef.current) {
        setTurnStatus(d.status);
        setCurrentStep(d.current_step ?? null);
        setDetail((prev) => {
          if (!prev) return d;
          const serverMsgs = d.messages ?? [];
          const merged = prev.messages.map((local, idx) => {
            if (local.id) return local;
            // Match by role + order: fill ids from server without touching streamed content.
            const candidates = serverMsgs.filter((s) => s.role === local.role);
            const sameRoleIndex = prev.messages
              .slice(0, idx + 1)
              .filter((m) => m.role === local.role).length - 1;
            const server = candidates[sameRoleIndex];
            if (server?.id && !local.streaming) {
              return { ...local, id: server.id };
            }
            if (server?.id && local.streaming) {
              return { ...local, id: server.id };
            }
            return local;
          });
          return {
            ...prev,
            messages: merged,
            evidences: d.evidences,
            events: d.events,
            status: d.status,
            current_step: d.current_step,
          };
        });
        return;
      }

      setDetail(d);
      setTurnStatus(d.status);
      setCurrentStep(d.current_step ?? null);
      if (d.status === "failed") {
        const errEvt = [...(d.events ?? [])].reverse().find((e) => e.type === "error");
        const msg = (errEvt?.detail as { message?: string } | undefined)?.message;
        if (msg) setLastError(msg);
      }
    } catch (e) {
      console.error("load detail failed", e);
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (sessionId: string) => {
      stopPolling();
      pollRef.current = setInterval(() => void loadDetail(sessionId), 2000);
    },
    [loadDetail, stopPolling],
  );

  const closeStream = useCallback(() => {
    streamRef.current?.close();
    streamRef.current = null;
  }, []);

  const appendStreamChunk = useCallback((chunk: string) => {
    setDetail((prev) => {
      if (!prev) return prev;
      const msgs = [...prev.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === "assistant" && last.streaming) {
        msgs[msgs.length - 1] = { ...last, content: (last.content || "") + chunk };
      }
      return { ...prev, messages: msgs };
    });
  }, []);

  const handleStreamEvent = useCallback(
    (type: string, payload: ChatStreamPayload) => {
      if (type === "state_change" && payload.status) {
        setTurnStatus(payload.status as ChatStatus);
      }
      if (type === "step_start") {
        if (payload.step) setCurrentStep(String(payload.step));
        if (payload.status) setTurnStatus(payload.status as ChatStatus);
      }
      if (type === "token" && payload.content) {
        appendStreamChunk(String(payload.content));
      }
      if (type === "error" && payload.message) {
        setLastError(String(payload.message));
      }
      if (type === "infer_result" && payload.kind) {
        setInferResults((prev) => [
          ...prev,
          { kind: String(payload.kind), summary: String(payload.summary ?? "") },
        ]);
      }
      if (type === "completed" || type === "error") {
        setStreaming(false);
        setInferResults([]);
        stopPolling();
        closeStream();
        setDetail((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            messages: prev.messages.map((m) =>
              m.streaming ? { ...m, streaming: false } : m,
            ),
          };
        });
        if (activeSessionId) void loadDetail(activeSessionId);
      }
    },
    [activeSessionId, appendStreamChunk, closeStream, loadDetail, stopPolling],
  );

  const newSession = useCallback(async () => {
    const res = await createSession();
    const summary: ChatSessionSummary = {
      session_id: res.session_id,
      external_id: res.external_id,
      chat_name: `Chat ${res.session_id.slice(-4)}`,
      status: (res.chat_status as ChatStatus) || "idle",
    };
    setSessions((prev) => [summary, ...prev]);
    setActiveSessionId(res.session_id);
    setDetail({
      ...summary,
      messages: [],
      evidences: [],
      events: [],
    });
    return res.session_id;
  }, []);

  const removeSession = useCallback((sessionId: string) => {
    setSessions((prev) => {
      const remaining = prev.filter((s) => s.session_id !== sessionId);
      if (activeSessionId === sessionId) {
        const next = remaining[0]?.session_id ?? null;
        setActiveSessionId(next);
        if (!next) setDetail(null);
      }
      return remaining;
    });
  }, [activeSessionId]);

  const deleteSessionById = useCallback(
    (sessionId: string) => {
      if (sessionDeleteQueue.has(sessionId)) return;

      if (activeSessionId === sessionId) {
        closeStream();
        stopPolling();
        setStreaming(false);
        setInferResults([]);
        setLastError(null);
        setTurnStatus("idle");
        setCurrentStep(null);
      }

      pendingDeletesRef.current.add(sessionId);
      removeSession(sessionId);
      sessionDeleteQueue.enqueue(sessionId);
    },
    [activeSessionId, closeStream, stopPolling, removeSession],
  );

  const sendMessage = useCallback(
    async (message: string) => {
      if (!activeSessionId || streaming) return;
      const sessionId = activeSessionId;
      setStreaming(true);
      setInferResults([]);
      setLastError(null);
      setTurnStatus("preparing");

      setDetail((prev) =>
        prev
          ? {
              ...prev,
              messages: [
                ...prev.messages,
                { role: "user", content: message },
                { role: "assistant", content: "", streaming: true },
              ],
            }
          : prev,
      );

      closeStream();
      streamRef.current = openChatStream(sessionId, {
        onEvent: handleStreamEvent,
        onError: () => {
          setStreaming(false);
          stopPolling();
        },
      });

      startPolling(sessionId);

      try {
        await startTurn(sessionId, message);
      } catch (e) {
        console.error("start turn failed", e);
        setLastError(e instanceof Error ? e.message : "Failed to start turn");
        setStreaming(false);
        stopPolling();
        closeStream();
      }
    },
    [
      activeSessionId,
      streaming,
      closeStream,
      handleStreamEvent,
      startPolling,
      stopPolling,
    ],
  );

  useEffect(() => {
    sessionDeleteQueue.setOnFail((sessionId, error) => {
      pendingDeletesRef.current.delete(sessionId);
      console.error("delete session failed", sessionId, error);
      void loadSessions();
    });
    return () => sessionDeleteQueue.setOnFail(null);
  }, [loadSessions]);

  useEffect(() => {
    void loadSessions();
    return () => {
      stopPolling();
      closeStream();
    };
  }, [loadSessions, stopPolling, closeStream]);

  useEffect(() => {
    if (activeSessionId) {
      void loadDetail(activeSessionId);
    } else {
      setDetail(null);
    }
  }, [activeSessionId, loadDetail]);

  return {
    sessions,
    activeSessionId,
    setActiveSessionId,
    detail,
    streaming,
    turnStatus,
    currentStep,
    inferResults,
    lastError,
    newSession,
    removeSession,
    deleteSessionById,
    sendMessage,
    refreshDetail: () => activeSessionId && loadDetail(activeSessionId),
  };
}
