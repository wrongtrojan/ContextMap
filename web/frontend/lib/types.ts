export type AssetModality = "pdf" | "video" | "audio";

export type AssetStatus =
  | "uploading"
  | "raw"
  | "recognizing"
  | "embedding"
  | "structuring"
  | "kg_extracting"
  | "ingesting"
  | "ready"
  | "failed";

export type ChatStatus =
  | "idle"
  | "preparing"
  | "researching"
  | "evaluating"
  | "strengthening"
  | "finalizing"
  | "failed";

export type MessageRole = "user" | "assistant" | "system";

export interface OutlineSubPoint {
  heading: string;
  anchor: number;
  summary: string;
}

export interface OutlineItem {
  heading: string;
  anchor: number;
  summary: string;
  sub_points?: OutlineSubPoint[];
}

export interface Asset {
  id: string;
  name: string;
  modality: AssetModality;
  status: AssetStatus;
  kg_status?: string;
  triple_count?: number;
  raw_path?: string;
  processed_path?: string;
  error_message?: string;
  retry_count?: number;
  current_step?: string | null;
}

export interface ChatMessage {
  id?: string;
  role: MessageRole;
  content: string;
  seq?: number;
  created_at?: string;
  streaming?: boolean;
}

export interface Evidence {
  id?: string;
  message_id?: string | null;
  content: string;
  score?: number;
  rank?: number;
  metadata: {
    asset_id?: string;
    asset_name?: string;
    modality?: AssetModality;
    type?: string;
    page_label?: number;
    timestamp?: number;
    bbox?: string | number[];
    image_filename?: string;
    processed_path?: string;
  };
}

export interface TurnEvent {
  type: string;
  step?: string | null;
  turn_seq?: number;
  detail?: Record<string, unknown>;
  created_at?: string;
}

export interface ChatSessionSummary {
  session_id: string;
  external_id?: string;
  chat_name: string;
  status: ChatStatus;
  updated_at?: string;
}

export interface ChatSessionDetail extends ChatSessionSummary {
  retry_count?: number;
  current_step?: string | null;
  messages: ChatMessage[];
  evidences: Evidence[];
  events: TurnEvent[];
}

export interface PreviewData {
  url: string;
  modality: AssetModality;
  assetId: string;
}

export type ActivityView = "explorer" | "kg" | "settings";

export type EditorTabKind = "asset" | "kg" | "settings";

export const KG_TAB_ID = "__kg__";
export const SETTINGS_TAB_ID = "__settings__";

export interface EditorTab {
  assetId: string;
  name: string;
  kind: EditorTabKind;
  modality?: AssetModality;
}

export interface JumpTarget {
  assetId: string;
  anchor: number;
  bbox?: string;
  assetName?: string;
}

export type SidebarView = "explorer" | "outline" | "chat";

export interface ApiResponse<T> {
  status: "success" | "error" | "processing";
  data?: T;
  message?: string;
  current_step?: string;
}

export interface AssetStatusPayload {
  asset_id: string;
  name: string;
  modality: AssetModality;
  status: AssetStatus;
  kg_status?: string;
  triple_count?: number;
  raw_path?: string;
  processed_path?: string;
  error_message?: string;
  retry_count?: number;
  current_step?: string | null;
}
