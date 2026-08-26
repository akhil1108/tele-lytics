"use client";

import { scoreColor } from "@/lib/charts";
import { decimal, stamp } from "@/lib/format";
import type { SentimentPoint } from "@/lib/types";

/**
 * Where sentiment moved during one call.
 *
 * Plotted against call time so a supervisor can jump straight to the moment
 * something turned. Each point is labelled with its timestamp — colour is
 * corroboration, never the only channel.
 */
export function SentimentTimeline({
  points,
  durationSeconds,
  onSeek,
}: {
  points: SentimentPoint[];
  durationSeconds: number | null;
  onSeek?: (ms: number) => void;
}) {
  if (points.length === 0) {
    return (
      <p className="text-sm text-ink-muted">
        Sentiment held steady across this call — no turning points were recorded.
      </p>
    );
  }

  const span = Math.max(
    (durationSeconds ?? 0) * 1000,
    ...points.map((point) => point.at_ms),
    1,
  );

  return (
    <div>
      {/* Inset by a mark radius on each side: a point at 0% or 100% is centred
          on the edge, so without this the first and last marks are clipped. */}
      <div className="relative mx-2 h-20">
        {/* Neutral baseline: the threshold the marks are read against. */}
        <div className="absolute inset-x-0 top-1/2 h-px bg-baseline" />
        {points.map((point, index) => {
          const left = `${(point.at_ms / span) * 100}%`;
          // Score −1..+1 maps to the full height, 0 at the baseline.
          const top = `${((1 - point.score) / 2) * 100}%`;
          return (
            <button
              key={`${point.at_ms}-${index}`}
              type="button"
              onClick={() => onSeek?.(point.at_ms)}
              className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full p-1"
              style={{ left, top }}
              title={`${stamp(point.at_ms)} · ${decimal(point.score)}${point.note ? ` · ${point.note}` : ""}`}
              aria-label={`Sentiment ${decimal(point.score)} at ${stamp(point.at_ms)}`}
            >
              <span
                className="block h-2.5 w-2.5 rounded-full ring-2"
                style={{
                  background: scoreColor(point.score),
                  // A surface-coloured ring keeps overlapping marks separable.
                  boxShadow: "0 0 0 2px var(--surface-1)",
                }}
              />
            </button>
          );
        })}
      </div>

      <ol className="mt-3 space-y-1.5 text-xs">
        {points.map((point, index) => (
          <li key={`${point.at_ms}-note-${index}`} className="flex gap-2">
            <button
              type="button"
              onClick={() => onSeek?.(point.at_ms)}
              className="tabular shrink-0 font-medium text-ink-secondary underline-offset-2 hover:underline"
            >
              {stamp(point.at_ms)}
            </button>
            <span
              aria-hidden
              className="mt-1.5 h-2 w-2 shrink-0 rounded-full"
              style={{ background: scoreColor(point.score) }}
            />
            <span className="text-ink-secondary">
              {point.note ?? `Sentiment moved to ${decimal(point.score)}`}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
