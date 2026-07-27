import { API } from "../api-config";

export type ChatStreamEventType =
  | "state_change"
  | "step_start"
  | "evaluation"
  | "refetch"
  | "evidence_snapshot"
  | "infer_result"
  | "token"
  | "completed"
  | "error"
  | "ping"
  | "message";

export interface ChatStreamPayload {
  type?: string;
  status?: string;
  step?: string;
  content?: string;
  kind?: string;
  summary?: string;
  recommendation?: string;
  confidence?: number;
  count?: number;
  message?: string;
  [key: string]: unknown;
}

export interface ChatStreamHandlers {
  onEvent?: (type: ChatStreamEventType, payload: ChatStreamPayload) => void;
  onError?: (error: Event) => void;
  onOpen?: () => void;
}

const CHAT_EVENT_TYPES: ChatStreamEventType[] = [
  "state_change",
  "step_start",
  "evaluation",
  "refetch",
  "evidence_snapshot",
  "infer_result",
  "token",
  "completed",
  "error",
  "ping",
  "message",
];

export function openChatStream(
  sessionId: string,
  handlers: ChatStreamHandlers,
): EventSource {
  const q = new URLSearchParams({ session_id: sessionId });
  const es = new EventSource(`${API.chats.stream}?${q}`);

  es.onopen = () => handlers.onOpen?.();

  es.onerror = (ev) => {
    handlers.onError?.(ev);
  };

  for (const eventType of CHAT_EVENT_TYPES) {
    es.addEventListener(eventType, (ev: MessageEvent) => {
      try {
        const payload = JSON.parse(ev.data) as ChatStreamPayload;
        handlers.onEvent?.(eventType, payload);
        if (eventType === "completed" || eventType === "error") {
          es.close();
        }
      } catch {
        handlers.onEvent?.(eventType, { raw: ev.data });
      }
    });
  }

  return es;
}
