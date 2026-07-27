"use client";

import { Group, Panel } from "react-resizable-panels";
import ExplorerView from "../sidebar/ExplorerView";
import OutlineView from "../sidebar/OutlineView";
import type { Asset, OutlineItem } from "../../lib/types";
import { ResizeHandle } from "./ResizableWorkbenchLayout";
import PanelHeader from "./PanelHeader";

interface SideBarProps {
  explorer: {
    assets: Asset[];
    loading: boolean;
    selectedAssetId: string | null;
    onSelectAsset: (id: string) => void;
    onUploaded: (assetId: string) => void;
    onRefresh: () => void;
    setUploading: (v: boolean) => void;
    onDeleteAsset: (id: string) => void;
  };
  outline: {
    items: OutlineItem[];
    loading: boolean;
    modality: "pdf" | "video" | "audio";
    assetName: string | null;
    onJump: (anchor: number) => void;
  };
}

const SIDEBAR_LAYOUT = { explorer: 45, outline: 55 };

export default function SideBar({ explorer, outline }: SideBarProps) {
  const outlineTitle = outline.assetName
    ? `Outline · ${outline.assetName}`
    : "Outline";

  return (
    <Group
      id="sidebar-split"
      orientation="vertical"
      className="h-full min-h-0"
      defaultLayout={SIDEBAR_LAYOUT}
      resizeTargetMinimumSize={{ coarse: 24, fine: 12 }}
    >
      <Panel id="explorer" defaultSize="45%" minSize="20%">
        <div className="h-full min-h-0 overflow-hidden flex flex-col">
          <ExplorerView {...explorer} />
        </div>
      </Panel>

      <ResizeHandle direction="vertical" />

      <Panel id="outline" defaultSize="55%" minSize="20%">
        <div className="h-full min-h-0 overflow-hidden flex flex-col">
          <PanelHeader title={outlineTitle} />
          <div className="flex-1 min-h-0 overflow-hidden">
            <OutlineView
              outline={outline.items}
              loading={outline.loading}
              modality={outline.modality}
              onJump={outline.onJump}
            />
          </div>
        </div>
      </Panel>
    </Group>
  );
}
