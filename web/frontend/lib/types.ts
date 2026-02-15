export type Asset = {
  id: string;
  name: string;
  type: 'pdf' | 'video';
  status: 'idle' | 'syncing' | 'ready' | 'failed';
  progress: number;
};