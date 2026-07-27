"use client";

import { useCallback, useState } from "react";
import type { OutlineItem, PreviewData } from "../types";
import { fetchPreview, fetchStructure } from "../api/assets";
import { encodeMediaUrl } from "../mediaUrl";

function parseOutline(data: { outline?: { outline?: OutlineItem[] }; title?: string } | undefined): OutlineItem[] {
  if (!data) return [];
  return data.outline?.outline ?? [];
}

export function usePreview() {
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [outline, setOutline] = useState<OutlineItem[]>([]);
  const [outlineAssetId, setOutlineAssetId] = useState<string | null>(null);
  const [loadingOutline, setLoadingOutline] = useState(false);

  const loadPreview = useCallback(async (assetId: string, modality: PreviewData["modality"]) => {
    setLoadingPreview(true);
    try {
      const data = await fetchPreview(assetId);
      setPreview({
        url: encodeMediaUrl(data.raw_path),
        modality: data.type || modality,
        assetId,
      });
    } catch (e) {
      console.error("preview failed", e);
      setPreview(null);
    } finally {
      setLoadingPreview(false);
    }
  }, []);

  const loadOutline = useCallback(async (assetId: string) => {
    setLoadingOutline(true);
    setOutline([]);
    setOutlineAssetId(assetId);
    try {
      const res = await fetchStructure(assetId);
      if (res.status === "success") {
        setOutline(parseOutline(res.data));
        setOutlineAssetId(assetId);
      } else {
        setOutline([]);
      }
    } catch (e) {
      console.error("structure failed", e);
      setOutline([]);
    } finally {
      setLoadingOutline(false);
    }
  }, []);

  const clear = useCallback(() => {
    setPreview(null);
    setOutline([]);
    setOutlineAssetId(null);
  }, []);

  return {
    preview,
    loadingPreview,
    outline,
    outlineAssetId,
    loadingOutline,
    loadPreview,
    loadOutline,
    clear,
  };
}
