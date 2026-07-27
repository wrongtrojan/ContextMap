"use client";

import { useCallback, useEffect, useImperativeHandle, useRef, useState, forwardRef } from "react";
import { Pause, Play, SkipBack } from "lucide-react";
import { cn, formatAnchor } from "../../lib/utils";
import ZoomControls, { clampScale, handleZoomWheel } from "./ZoomControls";
import { encodeMediaUrl } from "../../lib/mediaUrl";

export interface VideoEditorHandle {
  seek: (seconds: number) => void;
}

interface VideoEditorPaneProps {
  url: string;
  anchor?: number;
  markers?: number[];
}

const VideoEditorPane = forwardRef<VideoEditorHandle, VideoEditorPaneProps>(
  function VideoEditorPane({ url, anchor, markers = [] }, ref) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const [playing, setPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [error, setError] = useState<string | null>(null);
    const [scale, setScale] = useState(1);

    const mediaUrl = encodeMediaUrl(url);

    useImperativeHandle(ref, () => ({
      seek: (seconds: number) => {
        if (videoRef.current) {
          videoRef.current.currentTime = seconds;
          setCurrentTime(seconds);
        }
      },
    }));

    useEffect(() => {
      setError(null);
      setPlaying(false);
      setCurrentTime(0);
      setDuration(0);
      const v = videoRef.current;
      if (!v) return;
      v.load();
      if (anchor != null) {
        const onMeta = () => {
          v.currentTime = anchor;
          setCurrentTime(anchor);
        };
        if (v.readyState >= 1) onMeta();
        else v.addEventListener("loadedmetadata", onMeta, { once: true });
      }
    }, [anchor, mediaUrl]);

    const togglePlay = useCallback(() => {
      const v = videoRef.current;
      if (!v) return;
      if (v.paused) {
        void v.play().catch(() => setError("Playback blocked — click play again"));
        setPlaying(true);
      } else {
        v.pause();
        setPlaying(false);
      }
    }, []);

    const seekTo = useCallback((t: number) => {
      if (videoRef.current) {
        videoRef.current.currentTime = t;
        setCurrentTime(t);
      }
    }, []);

    const onWheel = useCallback(
      (e: React.WheelEvent) => handleZoomWheel(e, scale, (s) => setScale(clampScale(s))),
      [scale],
    );

    const pct = duration > 0 ? (currentTime / duration) * 100 : 0;

    return (
      <div className="relative flex flex-col h-full min-h-0 bg-dracula-bg">
        <ZoomControls scale={scale} onScaleChange={(s) => setScale(clampScale(s))} />

        <div
          className="flex-1 min-h-0 overflow-auto flex items-center justify-center p-4 custom-scrollbar"
          onWheel={onWheel}
        >
          {/* Scale via width %, not CSS transform — transform often blanks <video> */}
          <video
            key={mediaUrl}
            ref={videoRef}
            src={mediaUrl}
            preload="metadata"
            playsInline
            controls={false}
            className="rounded shadow-lg bg-black"
            style={{
              width: `${Math.round(scale * 100)}%`,
              maxWidth: "100%",
              height: "auto",
              maxHeight: "100%",
            }}
            onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
            onLoadedMetadata={(e) => {
              setDuration(e.currentTarget.duration);
              setError(null);
            }}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onError={() => {
              const err = videoRef.current?.error;
              const code = err?.code;
              setError(
                code === 4
                  ? "Video format not supported or URL invalid"
                  : `Failed to load video (media error ${code ?? "?"})`,
              );
            }}
          />
        </div>

        {error && (
          <p className="absolute top-14 left-0 right-0 text-center text-dracula-red text-xs font-mono px-4 z-30">
            {error}
          </p>
        )}

        <div className="border-t border-dracula-comment/30 bg-dracula-current/50 p-4 space-y-3 shrink-0">
          <div
            className="relative h-2 bg-dracula-bg rounded-full cursor-pointer group"
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const ratio = (e.clientX - rect.left) / rect.width;
              seekTo(ratio * duration);
            }}
          >
            <div className="absolute inset-y-0 left-0 bg-dracula-purple/60 rounded-full" style={{ width: `${pct}%` }} />
            {markers.map((m, i) => (
              <div
                key={i}
                className="absolute top-1/2 -translate-y-1/2 w-1.5 h-3 bg-dracula-cyan rounded-sm opacity-80"
                style={{ left: `${duration > 0 ? (m / duration) * 100 : 0}%` }}
                title={formatAnchor(m, "video")}
              />
            ))}
            <div
              className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-dracula-pink rounded-full shadow-md -ml-1.5"
              style={{ left: `${pct}%` }}
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => seekTo(0)} className="p-2 text-dracula-comment hover:text-dracula-fg">
                <SkipBack size={16} />
              </button>
              <button
                type="button"
                onClick={togglePlay}
                className={cn(
                  "p-2 rounded-full border border-dracula-purple/50 text-dracula-purple hover:bg-dracula-purple/20",
                )}
              >
                {playing ? <Pause size={18} /> : <Play size={18} />}
              </button>
            </div>
            <span className="text-[11px] font-mono text-dracula-comment">
              {formatAnchor(currentTime, "video")} / {formatAnchor(duration, "video")}
            </span>
          </div>
        </div>
      </div>
    );
  },
);

export default VideoEditorPane;
