"use client";

import { useRef } from "react";
import { Loader2 } from "lucide-react";
import type { EditorTab, PreviewData } from "../../lib/types";
import TabBar from "./TabBar";
import EmptyEditorPane from "../editor/EmptyEditorPane";
import KgComingSoonPane from "../editor/KgComingSoonPane";
import SettingsPane from "../editor/SettingsPane";
import PdfEditorPane from "../editor/PdfEditorPane";
import VideoEditorPane, { type VideoEditorHandle } from "../editor/VideoEditorPane";
import AudioEditorPane from "../editor/AudioEditorPane";

interface EditorAreaProps {
  tabs: EditorTab[];
  activeTabId: string | null;
  preview: PreviewData | null;
  previewLoading?: boolean;
  pdfPage: number;
  pdfHighlightPage?: number;
  pdfBbox?: string;
  pdfNavNonce?: number;
  videoAnchor?: number;
  videoMarkers?: number[];
  onSelectTab: (assetId: string) => void;
  onCloseTab: (assetId: string) => void;
  onPdfPageChange: (page: number) => void;
  onSettingsSaved?: () => void;
  videoRef?: React.RefObject<VideoEditorHandle>;
}

export default function EditorArea({
  tabs,
  activeTabId,
  preview,
  previewLoading,
  pdfPage,
  pdfHighlightPage,
  pdfBbox,
  pdfNavNonce,
  videoAnchor,
  videoMarkers,
  onSelectTab,
  onCloseTab,
  onPdfPageChange,
  onSettingsSaved,
  videoRef,
}: EditorAreaProps) {
  const localVideoRef = useRef<VideoEditorHandle>(null);
  const vRef = videoRef ?? localVideoRef;

  const activeTab = tabs.find((t) => t.assetId === activeTabId);
  const previewReady = preview && preview.assetId === activeTabId;

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 bg-[var(--wb-editor-bg)]">
      <TabBar tabs={tabs} activeTabId={activeTabId} onSelect={onSelectTab} onClose={onCloseTab} />
      <div className="flex-1 min-h-0 overflow-hidden">
        {!activeTab ? (
          <EmptyEditorPane />
        ) : activeTab.kind === "kg" ? (
          <KgComingSoonPane />
        ) : activeTab.kind === "settings" ? (
          <SettingsPane active={activeTabId === activeTab.assetId} onSaved={onSettingsSaved} />
        ) : previewLoading || !previewReady ? (
          <div className="flex items-center justify-center h-full text-dracula-comment">
            <Loader2 className="animate-spin mr-2" size={20} /> Loading preview...
          </div>
        ) : preview.modality === "pdf" ? (
          <PdfEditorPane
            url={preview.url}
            page={pdfPage}
            highlightPage={pdfHighlightPage}
            bbox={pdfBbox}
            navNonce={pdfNavNonce}
            onPageChange={onPdfPageChange}
          />
        ) : preview.modality === "video" ? (
          <VideoEditorPane ref={vRef} url={preview.url} anchor={videoAnchor} markers={videoMarkers} />
        ) : (
          <AudioEditorPane ref={vRef} url={preview.url} anchor={videoAnchor} markers={videoMarkers} />
        )}
      </div>
    </div>
  );
}
