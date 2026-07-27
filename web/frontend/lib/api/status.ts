import { API } from "../api-config";
import { apiFetch } from "./client";

export interface GlobalAssetsStatus {
  assets_number: number;
  active_pipelines: number;
  queue_length: number;
}

export interface GlobalChatsStatus {
  chats_number: number;
  chats_status: string;
  active_turns: number;
}

export interface ApiHealth {
  message: string;
  llm_configured?: boolean;
}

export async function pingApi(): Promise<boolean> {
  try {
    const res = await fetch(API.root);
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchApiHealth(): Promise<ApiHealth | null> {
  try {
    const res = await fetch(API.root);
    if (!res.ok) return null;
    return (await res.json()) as ApiHealth;
  } catch {
    return null;
  }
}

export async function fetchGlobalAssets(): Promise<GlobalAssetsStatus | null> {
  const res = await apiFetch<{ status: string; data?: GlobalAssetsStatus }>(API.status.globalAssets);
  return res.data ?? null;
}

export async function fetchGlobalChats(): Promise<GlobalChatsStatus | null> {
  const res = await apiFetch<{ status: string; data?: GlobalChatsStatus }>(API.status.globalChats);
  return res.data ?? null;
}
