"use client";

import clsx from "clsx";
import { useState } from "react";

import { BUCKET_COLOR, sentimentBucket } from "@/lib/charts";
import { SENTIMENT_LABELS, stamp, titleCase } from "@/lib/format";
import type { Segment, Transcript } from "@/lib/types";

import { Badge, Button } from "./ui";

/**
 * The call transcript, turn by turn.
 *
 * Each utterance carries the tone the speech model heard and — where the
 * insight model marked a turning point — the sentiment at that moment. Both
 * are written as words with a colour beside them, never colour alone.
 */
export function TranscriptView({
  transcript,
  onSeek,
  activeMs,
}: {
  transcript: Transcript;
  onSeek?: (ms: number) => void;
  activeMs?: number;
}) {
  const [speaker, setSpeaker] = useState<"all" | "agent" | "customer">("all");
  const [query, setQuery] = useState("");

  const segments = transcript.segments.filter((segment) => {
    if (speaker !== "all" && segment.speaker !== speaker) return false;
    if (query && !segment.text.toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  });

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border border-hairline p-0.5">
          {(["all", "agent", "customer"] as const).map((option) => (
            <button
              key={option}
              onClick={() => setSpeaker(option)}
              aria-pressed={speaker === option}
              className={clsx(
                "rounded px-2.5 py-1 text-xs capitalize transition",
                speaker === option
                  ? "bg-surface-raised font-medium text-ink"
                  : "text-ink-secondary hover:text-ink",
              )}
            >
              {option}
            </button>
          ))}
        </div>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Find in transcript"
          aria-label="Find in transcript"
          className="ml-auto w-48 rounded-md border border-hairline bg-surface px-2.5 py-1 text-xs text-ink placeholder:text-ink-muted"
        />
        <span className="tabular text-xs text-ink-muted">
          {segments.length}/{transcript.segments.length}
        </span>
      </div>

      <ol className="max-h-[520px] space-y-2.5 overflow-y-auto pr-1 scrollbar-thin">
        {segments.map((segment) => (
          <SegmentRow
            key={segment.id}
            segment={segment}
            onSeek={onSeek}
            active={
              activeMs !== undefined &&
              activeMs >= segment.start_ms &&
              activeMs < (segment.end_ms || segment.start_ms + 1)
            }
          />
        ))}
        {segments.length === 0 && (
          <li className="py-6 text-center text-sm text-ink-muted">
            Nothing in this transcript matches that filter.
          </li>
        )}
      </ol>
    </div>
  );
}

function SegmentRow({
  segment,
  onSeek,
  active,
}: {
  segment: Segment;
  onSeek?: (ms: number) => void;
  active: boolean;
}) {
  const isAgent = segment.speaker === "agent";

  return (
    <li
      className={clsx(
        "rounded-md border px-3 py-2.5 transition",
        active ? "border-[color:var(--series-1)]" : "border-hairline",
      )}
    >
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => onSeek?.(segment.start_ms)}
          className="tabular text-xs font-medium text-ink-secondary underline-offset-2 hover:underline"
          aria-label={`Play from ${stamp(segment.start_ms)}`}
        >
          {stamp(segment.start_ms)}
        </button>
        <span
          className={clsx(
            "text-xs font-semibold",
            isAgent ? "text-ink" : "text-ink-secondary",
          )}
        >
          {isAgent ? "Agent" : segment.speaker === "customer" ? "Customer" : "Unknown"}
        </span>
        {segment.tone_label && (
          <Badge className="border-none px-0 text-ink-muted">
            tone: {segment.tone_label}
          </Badge>
        )}
        {segment.sentiment && (
          <Badge color={BUCKET_COLOR[sentimentBucket(segment.sentiment)]}>
            {SENTIMENT_LABELS[segment.sentiment]}
          </Badge>
        )}
      </div>
      <p className="text-sm leading-relaxed text-ink">{segment.text}</p>
    </li>
  );
}

/** Compact tone rollup shown beside the transcript. */
export function ToneSummary({ tone }: { tone: Record<string, string> }) {
  const entries = Object.entries(tone).filter(([, value]) => value && value !== "unknown");
  if (entries.length === 0) return null;

  return (
    <dl className="grid grid-cols-2 gap-3">
      {entries.map(([who, value]) => (
        <div key={who}>
          <dt className="text-xs text-ink-muted">{titleCase(who)} tone</dt>
          <dd className="mt-0.5 text-sm capitalize text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
