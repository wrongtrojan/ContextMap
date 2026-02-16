// lib/types.ts
export interface OutlineSubPoint {
  heading: string;
  anchor: number;
  summary: string;
}

export interface OutlineItem {
  heading: string;
  anchor: number;
  summary: string;
  sub_points: OutlineSubPoint[];
}

export interface Asset {
  id: string; 
  name: string;
  type: 'pdf' | 'video';
  status: 'idle' | 'syncing' | 'ready';
  progress: number;
  outline?: OutlineItem[]; 
  raw_url?: string;
  preview_url?: string;
}