import { API } from "../api-config";

export type AssetStreamEventType = "state_change" | "completed" | "error" | "message" | string;

export interface AssetStreamPayload {
  type?: string;
  status?: string;
  message?: string;
  [key: string]: unknown;
}

export interface AssetStreamHandlers {
  onEvent?: (type: AssetStreamEventType, payload: AssetStreamPayload) => void;
  onError?: (error: Event) => void;
}

export function openAssetStream(
  assetId: string,
  handlers: AssetStreamHandlers,
): EventSource {
  const q = new URLSearchParams({ asset_id: assetId });
  const es = new EventSource(`${API.assets.stream}?${q}`);

  es.onerror = (ev) => handlers.onError?.(ev);

  const dispatch = (eventType: string, data: string) => {
    try {
      const payload = JSON.parse(data) as AssetStreamPayload;
      handlers.onEvent?.(eventType, payload);
    } catch {
      handlers.onEvent?.(eventType, { raw: data });
    }
  };

  es.onmessage = (ev) => dispatch("message", ev.data);
  es.addEventListener("state_change", (ev) => dispatch("state_change", (ev as MessageEvent).data));
  es.addEventListener("completed", (ev) => {
    dispatch("completed", (ev as MessageEvent).data);
    es.close();
  });
  es.addEventListener("error", (ev) => {
    dispatch("error", (ev as MessageEvent).data);
    es.close();
  });

  return es;
}
