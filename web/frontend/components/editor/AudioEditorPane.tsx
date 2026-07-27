"use client";

import { useRef, forwardRef, useImperativeHandle, useCallback, useEffect, useState } from "react";
import { Pause, Play, SkipBack } from "lucide-react";
import { cn, formatAnchor } from "../../lib/utils";
import { encodeMediaUrl } from "../../lib/mediaUrl";

export interface MediaEditorHandle {
  seek: (seconds: number) => void;
}

interface AudioEditorPaneProps {
  url: string;
  anchor?: number;
  markers?: number[];
}

const AudioEditorPane = forwardRef<MediaEditorHandle, AudioEditorPaneProps>(
  function AudioEditorPane({ url, anchor, markers = [] }, ref) {
    const audioRef = useRef<HTMLAudioElement>(null);
    const [playing, setPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [error, setError] = useState<string | null>(null);

    const mediaUrl = encodeMediaUrl(url);

    useImperativeHandle(ref, () => ({
      seek: (seconds: number) => {
        if (audioRef.current) {
          audioRef.current.currentTime = seconds;
          setCurrentTime(seconds);
        }
      },
    }));

    useEffect(() => {
      setError(null);
      setPlaying(false);
      setCurrentTime(0);
      setDuration(0);
      const a = audioRef.current;
      if (!a) return;
      a.load();
      if (anchor != null) {
        const onMeta = () => {
          a.currentTime = anchor;
          setCurrentTime(anchor);
        };
        if (a.readyState >= 1) onMeta();
        else a.addEventListener("loadedmetadata", onMeta, { once: true });
      }
    }, [anchor, mediaUrl]);

    const togglePlay = useCallback(() => {
      const a = audioRef.current;
      if (!a) return;
      if (a.paused) {
        void a.play().catch(() => setError("Playback blocked — click play again"));
        setPlaying(true);
      } else {
        a.pause();
        setPlaying(false);
      }
    }, []);

    const seekTo = useCallback((t: number) => {
      if (audioRef.current) {
        audioRef.current.currentTime = t;
        setCurrentTime(t);
      }
    }, []);

    const pct = duration > 0 ? (currentTime / duration) * 100 : 0;

    return (
      <div className="flex flex-col h-full min-h-0 bg-dracula-bg">
        <div className="flex-1 flex flex-col items-center justify-center p-8 gap-4 min-h-0">
          <audio
            key={mediaUrl}
            ref={audioRef}
            src={mediaUrl}
            preload="metadata"
            onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
            onLoadedMetadata={(e) => {
              setDuration(e.currentTarget.duration);
              setError(null);
            }}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onError={() => setError("Failed to load audio")}
          />
          {error && <p className="text-dracula-red text-sm font-mono">{error}</p>}
          {!error && (
            <p className="text-xs font-mono text-dracula-comment">Audio ready — use controls below</p>
          )}
        </div>
        <div className="border-t border-dracula-comment/30 bg-dracula-current/50 p-4 space-y-3 shrink-0">
          <div
            className="relative h-2 bg-dracula-bg rounded-full cursor-pointer"
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              seekTo(((e.clientX - rect.left) / rect.width) * duration);
            }}
          >
            <div className="absolute inset-y-0 left-0 bg-dracula-purple/60 rounded-full" style={{ width: `${pct}%` }} />
            {markers.map((m, i) => (
              <div
                key={i}
                className="absolute top-1/2 -translate-y-1/2 w-1.5 h-3 bg-dracula-cyan rounded-sm"
                style={{ left: `${duration > 0 ? (m / duration) * 100 : 0}%` }}
              />
            ))}
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => seekTo(0)} className="p-2 text-dracula-comment hover:text-dracula-fg">
                <SkipBack size={16} />
              </button>
              <button
                type="button"
                onClick={togglePlay}
                className={cn("p-2 rounded-full border border-dracula-purple/50 text-dracula-purple hover:bg-dracula-purple/20")}
              >
                {playing ? <Pause size={18} /> : <Play size={18} />}
              </button>
            </div>
            <span className="text-[11px] font-mono text-dracula-comment">
              {formatAnchor(currentTime, "audio")} / {formatAnchor(duration, "audio")}
            </span>
          </div>
        </div>
      </div>
    );
  },
);

export default AudioEditorPane;
