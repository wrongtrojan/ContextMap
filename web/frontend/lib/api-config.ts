// web/frontend/lib/api-config.ts
export const BASE_URL = "http://localhost:8001"; 

export const API_ENDPOINTS = {
  UPLOAD: `${BASE_URL}/api/v1/ingest/upload`,
  // 后端通常需要资产 ID 来获取状态：/status?id=xxx
  STATUS: `${BASE_URL}/api/v1/ingest/status`,
  SYNC: `${BASE_URL}/api/v1/ingest/sync`,
  ASSET_MAP: '/api/v1/asset/map',
};