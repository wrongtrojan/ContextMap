"use client";

import { useEffect, type ReactNode } from "react";
import {
  Group,
  Panel,
  Separator,
  usePanelRef,
} from "react-resizable-panels";
import { cn } from "../../lib/utils";

function ResizeHandle({ direction }: { direction: "horizontal" | "vertical" }) {
  return (
    <Separator
      className={cn(
        "panel-resize-handle",
        direction === "horizontal" ? "panel-resize-handle-h" : "panel-resize-handle-v",
      )}
    />
  );
}

interface ResizableWorkbenchLayoutProps {
  chatOpen: boolean;
  sidebar: ReactNode;
  editor: ReactNode;
  chat: ReactNode;
}

/** VS Code-ish defaults: ~20% sidebar, ~55% editor, ~25% chat */
const WORKBENCH_LAYOUT = {
  sidebar: 20,
  editor: 55,
  chat: 25,
};

export default function ResizableWorkbenchLayout({
  chatOpen,
  sidebar,
  editor,
  chat,
}: ResizableWorkbenchLayoutProps) {
  const chatPanelRef = usePanelRef();

  useEffect(() => {
    const panel = chatPanelRef.current;
    if (!panel) return;
    if (chatOpen) {
      if (panel.isCollapsed()) panel.expand();
    } else {
      if (!panel.isCollapsed()) panel.collapse();
    }
  }, [chatOpen, chatPanelRef]);

  return (
    <Group
      id="workbench"
      orientation="horizontal"
      className="flex-1 min-w-0 min-h-0"
      defaultLayout={WORKBENCH_LAYOUT}
      resizeTargetMinimumSize={{ coarse: 24, fine: 12 }}
    >
      <Panel id="sidebar" defaultSize="20%" minSize="12%" maxSize="40%">
        <div className="h-full flex flex-col min-h-0 overflow-hidden bg-[var(--wb-sidebar-bg)] border-r border-dracula-comment/20">
          {sidebar}
        </div>
      </Panel>

      <ResizeHandle direction="horizontal" />

      <Panel id="editor" defaultSize="55%" minSize="30%">
        <div className="h-full min-h-0 overflow-hidden">{editor}</div>
      </Panel>

      <ResizeHandle direction="horizontal" />

      <Panel
        id="chat"
        panelRef={chatPanelRef}
        defaultSize="25%"
        minSize="18%"
        maxSize="45%"
        collapsible
        collapsedSize="0%"
      >
        <div className="h-full flex flex-col min-h-0 overflow-hidden bg-[var(--wb-chatpanel-bg)] border-l border-dracula-comment/20">
          {chat}
        </div>
      </Panel>
    </Group>
  );
}

export { Group, Panel, Separator, ResizeHandle };
