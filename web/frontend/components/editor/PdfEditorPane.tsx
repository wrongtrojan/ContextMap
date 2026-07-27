"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { Loader2 } from "lucide-react";
import ZoomControls, { clampScale, handleZoomWheel } from "./ZoomControls";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.js`;

interface PdfEditorPaneProps {
  url: string;
  /** Currently viewed page (1-based) — updated by scroll observer only. */
  page: number;
  /** Page the bbox belongs to — must NOT follow scroll. */
  highlightPage?: number;
  bbox?: string;
  /** Bumped only on intentional jumps (evidence / outline). */
  navNonce?: number;
  onPageChange?: (page: number) => void;
}

function parseBbox(bbox?: string): [number, number, number, number] | null {
  if (!bbox) return null;
  try {
    const coords = JSON.parse(bbox) as number[];
    if (Array.isArray(coords) && coords.length >= 4) {
      return [Number(coords[0]), Number(coords[1]), Number(coords[2]), Number(coords[3])];
    }
  } catch {
    /* ignore */
  }
  return null;
}

function computeHighlight(
  bbox: string | undefined,
  highlightPage: number | undefined,
  pageNum: number,
  viewport: { width: number; height: number } | undefined,
  pageWidth: number,
) {
  if (!highlightPage || pageNum !== highlightPage || !viewport || viewport.width <= 0) {
    return null;
  }
  const coords = parseBbox(bbox);
  if (!coords) return null;
  const scale = pageWidth / viewport.width;
  const [xmin, ymin, xmax, ymax] = coords;
  const left = Math.min(xmin, xmax) * scale;
  const top = Math.min(ymin, ymax) * scale;
  const width = Math.abs(xmax - xmin) * scale;
  const height = Math.abs(ymax - ymin) * scale;
  if (width < 1 || height < 1) return null;
  return { left, top, width, height };
}

export default function PdfEditorPane({
  url,
  page,
  highlightPage,
  bbox,
  navNonce = 0,
  onPageChange,
}: PdfEditorPaneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<(HTMLDivElement | null)[]>([]);
  const scrollingProgrammatically = useRef(false);
  const pageFromObserver = useRef(page);
  const lastNavNonce = useRef(0);
  /** One-shot scroll target from an intentional jump; cleared after success. */
  const pendingScrollPage = useRef<number | null>(null);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [numPages, setNumPages] = useState(0);
  const [scale, setScale] = useState(1);
  const [containerWidth, setContainerWidth] = useState(0);
  const [pageViewports, setPageViewports] = useState<Record<number, { width: number; height: number }>>({});

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(() => {
      if (containerRef.current) setContainerWidth(containerRef.current.clientWidth);
    });
    ro.observe(containerRef.current);
    setContainerWidth(containerRef.current.clientWidth);
    return () => ro.disconnect();
  }, []);

  const baseWidth = Math.max(containerWidth - 48, 200);
  const pageWidth = baseWidth * scale;

  const clearRetry = useCallback(() => {
    if (retryTimer.current) {
      clearTimeout(retryTimer.current);
      retryTimer.current = null;
    }
  }, []);

  const tryPendingScroll = useCallback(() => {
    const target = pendingScrollPage.current;
    if (target == null || target < 1) return;

    const el = pageRefs.current[target - 1];
    if (!el) {
      // Page not mounted yet — retry briefly, then give up (do NOT loop forever).
      clearRetry();
      retryTimer.current = setTimeout(() => {
        if (pendingScrollPage.current === target) {
          const again = pageRefs.current[target - 1];
          if (!again) {
            // Give up so we never lock the user later.
            pendingScrollPage.current = null;
            return;
          }
          pendingScrollPage.current = null;
          scrollingProgrammatically.current = true;
          again.scrollIntoView({ behavior: "smooth", block: "start" });
          pageFromObserver.current = target;
          window.setTimeout(() => {
            scrollingProgrammatically.current = false;
          }, 500);
        }
      }, 80);
      return;
    }

    clearRetry();
    pendingScrollPage.current = null;
    scrollingProgrammatically.current = true;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    pageFromObserver.current = target;
    window.setTimeout(() => {
      scrollingProgrammatically.current = false;
    }, 500);
  }, [clearRetry]);

  // ONLY react to navNonce bumps (evidence / outline). Never to `page` from user scroll.
  useEffect(() => {
    if (!navNonce || navNonce === lastNavNonce.current) return;
    lastNavNonce.current = navNonce;
    const target = highlightPage || page;
    if (target > 0) {
      pendingScrollPage.current = target;
      tryPendingScroll();
    }
    // Intentionally omit `page` / `highlightPage` as ongoing deps for re-scroll.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navNonce, tryPendingScroll]);

  // When pages first become available, complete a pending jump once.
  useEffect(() => {
    if (numPages === 0) return;
    if (pendingScrollPage.current != null) {
      tryPendingScroll();
    }
  }, [numPages, tryPendingScroll]);

  useEffect(() => () => clearRetry(), [clearRetry]);

  useEffect(() => {
    const root = containerRef.current;
    if (!root || numPages === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (scrollingProgrammatically.current) return;
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        const top = visible[0];
        if (!top?.target) return;
        const pageNum = Number((top.target as HTMLElement).dataset.page);
        if (pageNum > 0 && pageNum !== pageFromObserver.current) {
          pageFromObserver.current = pageNum;
          onPageChange?.(pageNum);
        }
      },
      { root, threshold: [0.35, 0.5, 0.65] },
    );

    pageRefs.current.forEach((el) => {
      if (el) observer.observe(el);
    });

    return () => observer.disconnect();
  }, [numPages, pageWidth, onPageChange]);

  const onPageLoadSuccess = useCallback(
    (pageNum: number, p: { originalWidth: number; originalHeight: number }) => {
      setPageViewports((prev) => ({
        ...prev,
        [pageNum]: { width: p.originalWidth, height: p.originalHeight },
      }));
    },
    [],
  );

  const onWheel = useCallback(
    (e: React.WheelEvent) => handleZoomWheel(e, scale, (s) => setScale(clampScale(s))),
    [scale],
  );

  return (
    <div className="relative w-full h-full flex flex-col bg-dracula-bg overflow-hidden">
      <ZoomControls scale={scale} onScaleChange={(s) => setScale(clampScale(s))} />
      <div className="absolute top-3 left-3 z-40 text-[11px] font-mono text-dracula-pink bg-dracula-bg/90 border border-dracula-comment/40 rounded-md px-2 py-1">
        {page} / {numPages || "?"}
      </div>
      <div
        ref={containerRef}
        className="flex-1 overflow-auto custom-scrollbar"
        onWheel={onWheel}
      >
        <Document
          file={url}
          loading={
            <div className="flex items-center justify-center py-20">
              <Loader2 className="text-dracula-purple animate-spin" size={32} />
            </div>
          }
          onLoadSuccess={({ numPages: n }) => {
            setNumPages(n);
            pageRefs.current = new Array(n).fill(null);
            setPageViewports({});
          }}
          className="flex flex-col items-center py-8 px-6 gap-6"
        >
          {Array.from({ length: numPages }, (_, i) => {
            const pageNum = i + 1;
            const highlightStyle = computeHighlight(
              bbox,
              highlightPage,
              pageNum,
              pageViewports[pageNum],
              pageWidth,
            );

            return (
              <div
                key={pageNum}
                ref={(el) => {
                  pageRefs.current[i] = el;
                }}
                data-page={pageNum}
                className="flex justify-center w-full"
              >
                <div className="relative shadow-[0_20px_60px_rgba(0,0,0,0.4)] bg-white">
                  <Page
                    pageNumber={pageNum}
                    width={pageWidth}
                    onLoadSuccess={(p) => onPageLoadSuccess(pageNum, p)}
                    renderTextLayer={false}
                    renderAnnotationLayer={false}
                  />
                  {highlightStyle && (
                    <div
                      className="absolute pointer-events-none z-20 rounded-sm border-2 border-dracula-pink bg-dracula-pink/30 shadow-[0_0_18px_rgba(255,121,198,0.35)]"
                      style={highlightStyle}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </Document>
      </div>
    </div>
  );
}
