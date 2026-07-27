"use client";

import { Upload, RefreshCw } from "lucide-react";
import type { Asset } from "../../lib/types";
import AssetCard from "../AssetCard";
import { uploadAsset } from "../../lib/api/assets";
import PanelHeader from "../workbench/PanelHeader";

interface ExplorerViewProps {
  assets: Asset[];
  loading: boolean;
  selectedAssetId: string | null;
  onSelectAsset: (id: string) => void;
  onUploaded: (assetId: string) => void;
  onRefresh: () => void;
  setUploading: (v: boolean) => void;
  onDeleteAsset: (id: string) => void;
}

export default function ExplorerView({
  assets,
  loading,
  selectedAssetId,
  onSelectAsset,
  onUploaded,
  onRefresh,
  setUploading,
  onDeleteAsset,
}: ExplorerViewProps) {
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const res = await uploadAsset(file);
      onUploaded(res.asset_id);
      onRefresh();
    } catch (err) {
      console.error("upload failed", err);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Explorer"
        actions={
          <>
            <button
              type="button"
              onClick={onRefresh}
              className="p-1 text-dracula-comment hover:text-dracula-fg"
              title="Refresh"
            >
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
            <label
              className="p-1 text-dracula-comment hover:text-dracula-cyan cursor-pointer"
              title="Upload"
            >
              <Upload size={14} />
              <input
                type="file"
                className="hidden"
                accept=".pdf,.mp4,.mov,.avi,.mkv,.mp3,.wav,.m4a"
                onChange={handleUpload}
              />
            </label>
          </>
        }
      />
      <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
        {assets.length === 0 && !loading && (
          <p className="text-xs text-dracula-comment font-mono text-center py-8">
            No assets yet — upload a file
          </p>
        )}
        {assets.map((asset) => (
          <AssetCard
            key={asset.id}
            asset={asset}
            isSelected={selectedAssetId === asset.id}
            onSelect={onSelectAsset}
            onDelete={onDeleteAsset}
          />
        ))}
      </div>
    </div>
  );
}
