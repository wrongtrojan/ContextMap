export const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

export const API = {
  upload: `${BASE_URL}/api/v1/upload/file`,
  assets: {
    preview: `${BASE_URL}/api/v1/assets/preview`,
    structure: `${BASE_URL}/api/v1/assets/structure`,
    stream: `${BASE_URL}/api/v1/assets/stream`,
    retry: (assetId: string) => `${BASE_URL}/api/v1/assets/${assetId}/retry`,
    delete: (assetId: string) => `${BASE_URL}/api/v1/assets/${assetId}`,
  },
  chats: {
    sessions: `${BASE_URL}/api/v1/chats/sessions`,
    turns: (sessionId: string) => `${BASE_URL}/api/v1/chats/sessions/${sessionId}/turns`,
    deleteSession: (sessionId: string) => `${BASE_URL}/api/v1/chats/sessions/${sessionId}`,
    stream: `${BASE_URL}/api/v1/chats/stream`,
  },
  status: {
    singleAsset: `${BASE_URL}/api/v1/status/single_asset`,
    globalAssets: `${BASE_URL}/api/v1/status/global_assets`,
    singleChat: `${BASE_URL}/api/v1/status/single_chat`,
    globalChats: `${BASE_URL}/api/v1/status/global_chats`,
  },
  settings: {
    get: `${BASE_URL}/api/v1/settings`,
    save: `${BASE_URL}/api/v1/settings/save`,
  },
  root: `${BASE_URL}/`,
} as const;
