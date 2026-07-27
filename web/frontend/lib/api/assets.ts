import type { ApiResponse, AssetModality, AssetStatusPayload, OutlineItem } from "../types";
import { API } from "../api-config";
import { apiFetch } from "./client";

export interface UploadResponse {
  status: string;
  asset_id: string;
  current_state: string;
  message: string;
}

export interface PreviewResponse {
  asset_id: string;
  raw_path: string;
  type: AssetModality;
}

export interface StructureResponse {
  status: "success" | "processing" | "error";
  data?: {
    title?: string;
    outline?: { title?: string; outline?: OutlineItem[] };
  };
  current_step?: string;
  message?: string;
}

export async function uploadAsset(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<UploadResponse>(API.upload, { method: "POST", body: formData });
}

export async function fetchPreview(assetId: string): Promise<PreviewResponse> {
  const q = new URLSearchParams({ asset_id: assetId });
  return apiFetch<PreviewResponse>(`${API.assets.preview}?${q}`);
}

export async function fetchStructure(assetId: string): Promise<StructureResponse> {
  const q = new URLSearchParams({ asset_id: assetId });
  return apiFetch<StructureResponse>(`${API.assets.structure}?${q}`);
}

export async function retryAsset(assetId: string): Promise<{ status: string }> {
  return apiFetch(API.assets.retry(assetId), { method: "POST" });
}

export async function listAssets(): Promise<AssetStatusPayload[]> {
  const res = await apiFetch<ApiResponse<Record<string, AssetStatusPayload>>>(API.status.singleAsset);
  if (!res.data) return [];
  return Object.values(res.data);
}

export async function deleteAsset(assetId: string, includeDisk = true): Promise<{ status: string; asset_id: string }> {
  const q = includeDisk ? "?include_disk=true" : "?include_disk=false";
  return apiFetch(`${API.assets.delete(assetId)}${q}`, { method: "DELETE" });
}
