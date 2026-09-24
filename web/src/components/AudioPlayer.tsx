"use client";

import { useEffect, useRef, useState } from "react";

import { fetchAudioUrl } from "@/lib/api";
import { duration, stamp } from "@/lib/format";

/**
 * Recording playback.
 *
 * The audio endpoint checks tenancy on every request, so the file is fetched
 * with the bearer token and played from an object URL rather than pointed at
 * directly. The URL is revoked on unmount so the blob is not retained.
 */
export function AudioPlayer({
  callId,
  onTimeUpdate,
  seekToMs,
}: {
  callId: string;
  onTimeUpdate?: (ms: number) => void;
  seekToMs?: number | null;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [position, setPosition] = useState(0);
  const [length, setLength] = useState(0);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    fetchAudioUrl(callId)
      .then((created) => {
        if (cancelled) {
          URL.revokeObjectURL(created);
          return;
        }
        objectUrl = created;
        setUrl(created);
      })
      .catch((caught: unknown) =>
        setError(caught instanceof Error ? caught.message : "Could not load audio"),
      );

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [callId]);

  useEffect(() => {
    if (seekToMs === null || seekToMs === undefined || !audioRef.current) return;
    audioRef.current.currentTime = seekToMs / 1000;
    void audioRef.current.play().catch(() => {
      /* autoplay may be blocked; the control still moved */
    });
  }, [seekToMs]);

  if (error) {
    return (
      <p className="text-sm" style={{ color: "var(--status-critical)" }}>
        {error}
      </p>
    );
  }
  if (!url) return <p className="text-sm text-ink-muted">Loading audio…</p>;

  return (
    <div>
      <audio
        ref={audioRef}
        src={url}
        controls
        className="w-full"
        onLoadedMetadata={(event) => setLength(event.currentTarget.duration)}
        onTimeUpdate={(event) => {
          const seconds = event.currentTarget.currentTime;
          setPosition(seconds);
          onTimeUpdate?.(seconds * 1000);
        }}
      />
      <p className="tabular mt-1.5 text-xs text-ink-muted">
        {stamp(position * 1000)} / {duration(length || null)}
      </p>
    </div>
  );
}
