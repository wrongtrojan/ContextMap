import type { ApiResponse, ChatSessionDetail, ChatSessionSummary } from "../types";
import { API } from "../api-config";
import { apiFetch } from "./client";

export interface CreateSessionResponse {
  status: string;
  session_id: string;
  external_id?: string;
  chat_status: string;
}

export interface StartTurnResponse {
  status: string;
  session_id: string;
  turn_seq: number;
  message: string;
}

export async function createSession(): Promise<CreateSessionResponse> {
  return apiFetch<CreateSessionResponse>(API.chats.sessions, { method: "POST" });
}

export async function startTurn(sessionId: string, message: string): Promise<StartTurnResponse> {
  return apiFetch<StartTurnResponse>(API.chats.turns(sessionId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
}

export async function fetchSessionDetail(sessionId: string): Promise<ChatSessionDetail | null> {
  const q = new URLSearchParams({ session_id: sessionId });
  const res = await apiFetch<ApiResponse<ChatSessionDetail>>(`${API.status.singleChat}?${q}`);
  return res.data ?? null;
}

export async function listSessionSummaries(): Promise<ChatSessionSummary[]> {
  const res = await apiFetch<ApiResponse<Record<string, ChatSessionSummary>>>(API.status.singleChat);
  if (!res.data) return [];
  return Object.values(res.data);
}

export async function deleteSession(
  sessionId: string,
): Promise<{ status: string; session_id: string }> {
  return apiFetch(API.chats.deleteSession(sessionId), { method: "DELETE", timeoutMs: 8_000 });
}
