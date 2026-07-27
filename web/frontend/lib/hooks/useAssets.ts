"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Asset, AssetStatusPayload } from "../types";
import { listAssets } from "../api/assets";
import { openAssetStream } from "../sse/assetStream";

function toAsset(row: AssetStatusPayload): Asset {
  return {
    id: row.asset_id,
    name: row.name,
    modality: row.modality,
    status: row.status,
    kg_status: row.kg_status,
    triple_count: row.triple_count,
    raw_path: row.raw_path,
    processed_path: row.processed_path,
    error_message: row.error_message,
    retry_count: row.retry_count,
    current_step: row.current_step,
  };
}

export function useAssets() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const streamsRef = useRef<Map<string, EventSource>>(new Map());

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await listAssets();
      setAssets(rows.map(toAsset));
    } catch (e) {
      console.error("refresh assets failed", e);
    } finally {
      setLoading(false);
    }
  }, []);

  const updateAsset = useCallback((assetId: string, patch: Partial<Asset>) => {
    setAssets((prev) =>
      prev.map((a) => (a.id === assetId ? { ...a, ...patch } : a)),
    );
  }, []);

  const watchAsset = useCallback(
    (assetId: string) => {
      if (streamsRef.current.has(assetId)) return;
      const es = openAssetStream(assetId, {
        onEvent: (type, payload) => {
          if (payload.status) {
            updateAsset(assetId, { status: payload.status as Asset["status"] });
          }
          if (type === "completed" || type === "error") {
            streamsRef.current.get(assetId)?.close();
            streamsRef.current.delete(assetId);
            void refresh();
          }
        },
        onError: () => {
          streamsRef.current.get(assetId)?.close();
          streamsRef.current.delete(assetId);
        },
      });
      streamsRef.current.set(assetId, es);
    },
    [refresh, updateAsset],
  );

  useEffect(() => {
    void refresh();
    return () => {
      streamsRef.current.forEach((es) => es.close());
      streamsRef.current.clear();
    };
  }, [refresh]);

  useEffect(() => {
    const active = assets.filter(
      (a) => !["ready", "failed", "raw"].includes(a.status),
    );
    for (const asset of active) {
      watchAsset(asset.id);
    }
  }, [assets, watchAsset]);

  return {
    assets,
    loading,
    uploading,
    setUploading,
    refresh,
    updateAsset,
    watchAsset,
  };
}
