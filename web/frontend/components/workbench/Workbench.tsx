"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ActivityView, EditorTab, JumpTarget } from "../../lib/types";
import { KG_TAB_ID, SETTINGS_TAB_ID } from "../../lib/types";
import { useAssets } from "../../lib/hooks/useAssets";
import { useChatSession } from "../../lib/hooks/useChatSession";
import { usePreview } from "../../lib/hooks/usePreview";
import { deleteAsset } from "../../lib/api/assets";
import ActivityBar from "./ActivityBar";
import SideBar from "./SideBar";
import EditorArea from "./EditorArea";
import ChatPanel from "./ChatPanel";
import ChatToggleHint from "./ChatToggleHint";
import StatusBar from "./StatusBar";
import ResizableWorkbenchLayout from "./ResizableWorkbenchLayout";
import type { VideoEditorHandle } from "../editor/VideoEditorPane";

export default function Workbench() {
  const [chatOpen, setChatOpen] = useState(true);
  const [activeActivity, setActiveActivity] = useState<ActivityView>("explorer");
  const [healthRefresh, setHealthRefresh] = useState(0);
  const [tabs, setTabs] = useState<EditorTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfHighlightPage, setPdfHighlightPage] = useState<number | undefined>();
  const [pdfBbox, setPdfBbox] = useState<string | undefined>();
  const [pdfNavNonce, setPdfNavNonce] = useState(0);
  const [videoAnchor, setVideoAnchor] = useState<number | undefined>();
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);

  const videoRef = useRef<VideoEditorHandle>(null);
  const assetsHook = useAssets();
  const chatHook = useChatSession();
  const previewHook = usePreview();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "l") {
        e.preventDefault();
        setChatOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const openKgTab = useCallback(() => {
    setActiveActivity("kg");
    setTabs((prev) => {
      if (prev.some((t) => t.assetId === KG_TAB_ID)) return prev;
      return [
        ...prev,
        { assetId: KG_TAB_ID, name: "Knowledge Graph", kind: "kg" as const },
      ];
    });
    setActiveTabId(KG_TAB_ID);
  }, []);

  const openSettingsTab = useCallback(() => {
    setActiveActivity("settings");
    setTabs((prev) => {
      if (prev.some((t) => t.assetId === SETTINGS_TAB_ID)) return prev;
      return [
        ...prev,
        { assetId: SETTINGS_TAB_ID, name: "Settings", kind: "settings" as const },
      ];
    });
    setActiveTabId(SETTINGS_TAB_ID);
  }, []);

  const handleSelectActivity = useCallback(
    (view: ActivityView) => {
      if (view === "kg") {
        openKgTab();
        return;
      }
      if (view === "settings") {
        openSettingsTab();
        return;
      }
      setActiveActivity("explorer");
    },
    [openKgTab, openSettingsTab],
  );

  const selectTab = useCallback(
    async (assetId: string) => {
      if (assetId === KG_TAB_ID) {
        setActiveTabId(KG_TAB_ID);
        setActiveActivity("kg");
        return;
      }
      if (assetId === SETTINGS_TAB_ID) {
        setActiveTabId(SETTINGS_TAB_ID);
        setActiveActivity("settings");
        return;
      }
      const asset = assetsHook.assets.find((a) => a.id === assetId);
      if (!asset) return;
      setActiveTabId(assetId);
      setSelectedAssetId(assetId);
      setActiveActivity("explorer");
      await previewHook.loadPreview(assetId, asset.modality);
      await previewHook.loadOutline(assetId);
    },
    [assetsHook.assets, previewHook],
  );

  const openAssetTab = useCallback(
    async (
      assetId: string,
      jump?: {
        pdfPage?: number;
        pdfHighlightPage?: number;
        pdfBbox?: string;
        videoAnchor?: number;
      },
    ) => {
      const asset = assetsHook.assets.find((a) => a.id === assetId);
      if (!asset || asset.status !== "ready") return;

      const alreadyOpen =
        activeTabId === assetId && previewHook.preview?.assetId === assetId;

      setPdfPage(jump?.pdfPage ?? (alreadyOpen ? pdfPage : 1));
      setPdfHighlightPage(jump?.pdfHighlightPage);
      setPdfBbox(jump?.pdfBbox);
      setVideoAnchor(jump?.videoAnchor);
      if (jump?.pdfPage != null || jump?.pdfHighlightPage != null || jump?.pdfBbox) {
        setPdfNavNonce((n) => n + 1);
      }

      setTabs((prev) => {
        if (prev.some((t) => t.assetId === assetId)) return prev;
        return [
          ...prev,
          { assetId, name: asset.name, kind: "asset" as const, modality: asset.modality },
        ];
      });

      setActiveActivity("explorer");

      if (!alreadyOpen) {
        await selectTab(assetId);
        // Preview remount — bump nonce again so scroll retries after pages exist.
        if (jump?.pdfPage != null || jump?.pdfHighlightPage != null) {
          setPdfNavNonce((n) => n + 1);
        }
      }

      if (jump?.videoAnchor != null && (asset.modality === "video" || asset.modality === "audio")) {
        window.setTimeout(() => videoRef.current?.seek(jump.videoAnchor!), 150);
      }
    },
    [activeTabId, assetsHook.assets, pdfPage, previewHook.preview?.assetId, selectTab],
  );

  const resolveAsset = useCallback(
    (target: JumpTarget) => {
      const byId = target.assetId
        ? assetsHook.assets.find((a) => a.id === target.assetId)
        : undefined;
      if (byId) return byId;
      const name = target.assetName?.trim();
      if (!name) return undefined;
      return (
        assetsHook.assets.find((a) => a.name === name) ||
        assetsHook.assets.find(
          (a) => a.name.includes(name) || name.includes(a.name),
        )
      );
    },
    [assetsHook.assets],
  );

  const handleJump = useCallback(
    (target: JumpTarget) => {
      const asset = resolveAsset(target);
      if (!asset) {
        console.warn("evidence jump: asset not found", target);
        return;
      }

      if (asset.modality === "pdf") {
        const page = Math.max(1, Math.round(target.anchor || 1));
        void openAssetTab(asset.id, {
          pdfPage: page,
          pdfHighlightPage: page,
          pdfBbox: target.bbox,
        });
      } else if (asset.modality === "video" || asset.modality === "audio") {
        void openAssetTab(asset.id, { videoAnchor: target.anchor });
      } else {
        void openAssetTab(asset.id);
      }
    },
    [openAssetTab, resolveAsset],
  );

  const handleOutlineJump = useCallback(
    (anchor: number) => {
      if (!activeTabId) return;
      const tab = tabs.find((t) => t.assetId === activeTabId);
      if (!tab) return;
      if (tab.modality === "pdf") {
        setPdfPage(Math.max(1, Math.round(anchor)));
        setPdfHighlightPage(undefined);
        setPdfBbox(undefined);
        setPdfNavNonce((n) => n + 1);
      } else {
        setVideoAnchor(anchor);
        videoRef.current?.seek(anchor);
      }
    },
    [activeTabId, tabs],
  );

  const closeTab = useCallback(
    (assetId: string) => {
      setTabs((prev) => {
        const remaining = prev.filter((t) => t.assetId !== assetId);
        if (activeTabId === assetId) {
          const next = remaining[remaining.length - 1]?.assetId ?? null;
          setActiveTabId(next);
          if (assetId === KG_TAB_ID || assetId === SETTINGS_TAB_ID) {
            setActiveActivity("explorer");
          }
          if (next) {
            void selectTab(next);
          } else {
            previewHook.clear();
          }
        }
        return remaining;
      });
    },
    [activeTabId, previewHook, selectTab],
  );

  const handleDeleteAsset = useCallback(
    async (assetId: string) => {
      if (!confirm("Delete this asset from the database and disk?")) return;
      try {
        await deleteAsset(assetId, true);
        closeTab(assetId);
        await assetsHook.refresh();
      } catch (e) {
        console.error("delete asset failed", e);
        alert(e instanceof Error ? e.message : "Delete failed");
      }
    },
    [assetsHook, closeTab],
  );

  const handleDeleteSession = useCallback(
    (sessionId: string) => {
      if (!confirm("Delete this chat session and all its messages?")) return;
      chatHook.deleteSessionById(sessionId);
    },
    [chatHook],
  );

  const activeAsset = assetsHook.assets.find((a) => a.id === activeTabId);
  const outlineForTab =
    previewHook.outlineAssetId === activeTabId ? previewHook.outline : [];
  const videoMarkers = outlineForTab.map((o) => o.anchor);

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <div className="flex-1 flex min-h-0 relative">
        <ActivityBar
          activeActivity={activeActivity}
          onSelectActivity={handleSelectActivity}
          onOpenSettings={openSettingsTab}
        />
        <ResizableWorkbenchLayout
          chatOpen={chatOpen}
          sidebar={
            <SideBar
              explorer={{
                assets: assetsHook.assets,
                loading: assetsHook.loading,
                selectedAssetId,
                onSelectAsset: (id) => void openAssetTab(id),
                onUploaded: (id) => assetsHook.watchAsset(id),
                onRefresh: () => void assetsHook.refresh(),
                setUploading: assetsHook.setUploading,
                onDeleteAsset: (id) => void handleDeleteAsset(id),
              }}
              outline={{
                items: outlineForTab,
                loading: previewHook.loadingOutline && previewHook.outlineAssetId === activeTabId,
                modality: activeAsset?.modality ?? "pdf",
                assetName: activeAsset?.name ?? null,
                onJump: handleOutlineJump,
              }}
            />
          }
          editor={
            <div className="relative h-full min-h-0 flex flex-col">
              <EditorArea
                tabs={tabs}
                activeTabId={activeTabId}
                preview={previewHook.preview}
                previewLoading={previewHook.loadingPreview}
                pdfPage={pdfPage}
                pdfHighlightPage={pdfHighlightPage}
                pdfBbox={pdfBbox}
                pdfNavNonce={pdfNavNonce}
                videoAnchor={videoAnchor}
                videoMarkers={videoMarkers}
                onSelectTab={(id) => void selectTab(id)}
                onCloseTab={closeTab}
                onPdfPageChange={setPdfPage}
                onSettingsSaved={() => setHealthRefresh((n) => n + 1)}
                videoRef={videoRef}
              />
              {!chatOpen && <ChatToggleHint />}
            </div>
          }
          chat={
            <ChatPanel
              {...chatHook}
              onEvidenceJump={(assetId, anchor, bbox, assetName) =>
                handleJump({ assetId, anchor, bbox, assetName })
              }
              onDeleteSession={(id) => void handleDeleteSession(id)}
            />
          }
        />
      </div>
      <StatusBar
        key={healthRefresh}
        turnStatus={chatHook.turnStatus}
        pipelineStep={activeAsset?.current_step}
      />
    </div>
  );
}
