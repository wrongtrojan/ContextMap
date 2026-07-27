import type { SettingsData } from "../api/settings";

export interface SettingsFormState {
  llmModel: string;
  llmApiUrl: string;
  llmTimeout: string;
  deepseekApiKey: string;
  maxConcurrentParse: string;
  maxConcurrentWhisper: string;
  maxConcurrentOutline: string;
  maxConcurrentIngest: string;
  maxConcurrentKg: string;
  autoStartOnUpload: boolean;
  kgEnabled: boolean;
  kgFailOpen: boolean;
  kgChunkMaxTokens: string;
  retrievalTopK: string;
  retrievalGraphEnabled: boolean;
  chatMaxRetries: string;
  sseBatchMs: string;
  sseBatchChars: string;
}

export function settingsDataToForm(data: SettingsData): SettingsFormState {
  return {
    llmModel: String(data.llm.model ?? ""),
    llmApiUrl: String(data.llm.api_url ?? ""),
    llmTimeout: String(data.llm.timeout_sec ?? ""),
    deepseekApiKey: "",
    maxConcurrentParse: String(data.pipeline.max_concurrent_parse ?? ""),
    maxConcurrentWhisper: String(data.pipeline.max_concurrent_whisper ?? ""),
    maxConcurrentOutline: String(data.pipeline.max_concurrent_outline ?? ""),
    maxConcurrentIngest: String(data.pipeline.max_concurrent_ingest ?? ""),
    maxConcurrentKg: String(data.pipeline.max_concurrent_kg ?? ""),
    autoStartOnUpload: Boolean(data.pipeline.auto_start_on_upload),
    kgEnabled: Boolean(data.kg.enabled),
    kgFailOpen: Boolean(data.kg.fail_open),
    kgChunkMaxTokens: String(data.kg.chunk_max_tokens ?? ""),
    retrievalTopK: String(data.retrieval.top_k_default ?? ""),
    retrievalGraphEnabled: Boolean(data.retrieval.graph_enabled),
    chatMaxRetries: String(data.chat.max_retries ?? ""),
    sseBatchMs: String(data.chat.streaming?.sse_token_batch_ms ?? ""),
    sseBatchChars: String(data.chat.streaming?.sse_token_batch_chars ?? ""),
  };
}

export function formToSettingsChanges(
  form: SettingsFormState,
  baseline: SettingsFormState,
): Record<string, unknown> {
  const changes: Record<string, unknown> = {};
  const map: Array<[keyof SettingsFormState, string]> = [
    ["llmModel", "outline.llm.model"],
    ["llmApiUrl", "outline.llm.api_url"],
    ["llmTimeout", "outline.llm.timeout_sec"],
    ["maxConcurrentParse", "pipeline.max_concurrent_parse"],
    ["maxConcurrentWhisper", "pipeline.max_concurrent_whisper"],
    ["maxConcurrentOutline", "pipeline.max_concurrent_outline"],
    ["maxConcurrentIngest", "pipeline.max_concurrent_ingest"],
    ["maxConcurrentKg", "pipeline.max_concurrent_kg"],
    ["kgChunkMaxTokens", "kg.chunk_max_tokens"],
    ["retrievalTopK", "retrieval.top_k_default"],
    ["chatMaxRetries", "chat.research.max_retries"],
    ["sseBatchMs", "chat.streaming.sse_token_batch_ms"],
    ["sseBatchChars", "chat.streaming.sse_token_batch_chars"],
  ];
  for (const [formKey, path] of map) {
    if (form[formKey] !== baseline[formKey]) {
      const raw = form[formKey];
      if (
        path.includes("timeout") ||
        path.includes("max_concurrent") ||
        path.includes("tokens") ||
        path.includes("top_k") ||
        path.includes("retries") ||
        path.includes("batch")
      ) {
        changes[path] = Number(raw);
      } else {
        changes[path] = raw;
      }
    }
  }
  if (form.autoStartOnUpload !== baseline.autoStartOnUpload) {
    changes["pipeline.auto_start_on_upload"] = form.autoStartOnUpload;
  }
  if (form.kgEnabled !== baseline.kgEnabled) {
    changes["kg.enabled"] = form.kgEnabled;
  }
  if (form.kgFailOpen !== baseline.kgFailOpen) {
    changes["kg.fail_open"] = form.kgFailOpen;
  }
  if (form.retrievalGraphEnabled !== baseline.retrievalGraphEnabled) {
    changes["retrieval.channels.graph.enabled"] = form.retrievalGraphEnabled;
  }
  return changes;
}

export const settingsInputClass =
  "w-full px-2 py-1.5 text-xs font-mono bg-dracula-background border border-dracula-comment/30 rounded text-dracula-fg focus:outline-none focus:border-dracula-purple/60";
