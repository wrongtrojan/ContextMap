import { API } from "../api-config";
import { apiFetch } from "./client";

export interface SettingsLlm {
  model?: string;
  api_url?: string;
  timeout_sec?: number;
  api_key_env?: string;
  configured?: boolean;
  hint?: string | null;
}

export interface SettingsData {
  llm: SettingsLlm;
  pipeline: {
    max_concurrent_parse?: number;
    max_concurrent_whisper?: number;
    max_concurrent_outline?: number;
    max_concurrent_ingest?: number;
    max_concurrent_kg?: number;
    auto_start_on_upload?: boolean;
  };
  kg: {
    enabled?: boolean;
    fail_open?: boolean;
    chunk_max_tokens?: number;
  };
  retrieval: {
    top_k_default?: number;
    graph_enabled?: boolean;
  };
  chat: {
    max_retries?: number;
    streaming?: {
      sse_token_batch_ms?: number;
      sse_token_batch_chars?: number;
    };
  };
  editable_paths?: string[];
}

export interface SettingsGetResponse {
  status: string;
  data: SettingsData;
}

export interface SettingsSavePayload {
  changes: Record<string, unknown>;
  deepseek_api_key?: string;
}

export interface SettingsSaveResponse {
  status: string;
  saved_files: string[];
  saved_at: string;
  data: SettingsData;
}

export async function fetchSettings(): Promise<SettingsData> {
  const res = await apiFetch<SettingsGetResponse>(API.settings.get);
  return res.data;
}

export async function saveSettings(payload: SettingsSavePayload): Promise<SettingsSaveResponse> {
  return apiFetch<SettingsSaveResponse>(API.settings.save, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
