"use client";

import { BUCKET_COLOR, BUCKET_LABEL, sentimentBucket, type SentimentBucket } from "@/lib/charts";
import { SENTIMENT_LABELS, count, percent } from "@/lib/format";
import type { SentimentBreakdown } from "@/lib/types";

import { ChartFrame } from "./ChartFrame";

const ORDER: SentimentBucket[] = ["negative", "neutral", "positive"];

/**
 * Customer sentiment as a single stacked bar.
 *
 * Three buckets, not five: sentiment is polarity, so it takes a diverging
 * scale, and two distinct steps per arm cannot fit the lightness band every
 * series here is held to. The five-level detail is in the table view and the
 * per-segment labels, where words carry it instead of colour.
 */
export function SentimentChart({ data }: { data: SentimentBreakdown[] }) {
  const buckets = ORDER.map((bucket) => ({
    bucket,
    count: data
      .filter((row) => sentimentBucket(row.label) === bucket)
      .reduce((total, row) => total + row.count, 0),
  }));
  const total = buckets.reduce((sum, entry) => sum + entry.count, 0);

  return (
    <ChartFrame
      title="Customer sentiment"
      subtitle={total ? `${count(total)} analysed calls` : undefined}
      legend={ORDER.map((bucket) => ({
        label: BUCKET_LABEL[bucket],
        color: BUCKET_COLOR[bucket],
      }))}
      height={200}
      table={
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-surface text-ink-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">Sentiment</th>
              <th className="py-1.5 pr-3 text-right font-medium">Calls</th>
              <th className="py-1.5 text-right font-medium">Share</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.label} className="border-t border-hairline text-ink-secondary">
                <td className="py-1.5 pr-3">{SENTIMENT_LABELS[row.label]}</td>
                <td className="tabular py-1.5 pr-3 text-right">{count(row.count)}</td>
                <td className="tabular py-1.5 text-right">{percent(row.share, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      {total === 0 ? (
        <p className="flex h-full items-center justify-center text-sm text-ink-muted">
          No analysed calls in this range yet
        </p>
      ) : (
        <div className="flex h-full flex-col justify-center gap-6">
          {/* 2px gaps between segments so adjacent fills never touch. */}
          <div className="flex h-9 w-full gap-[2px] overflow-hidden rounded-md">
            {buckets
              .filter((entry) => entry.count > 0)
              .map((entry) => (
                <div
                  key={entry.bucket}
                  className="flex items-center justify-center"
                  style={{
                    width: `${(entry.count / total) * 100}%`,
                    background: BUCKET_COLOR[entry.bucket],
                  }}
                  title={`${BUCKET_LABEL[entry.bucket]}: ${entry.count}`}
                />
              ))}
          </div>

          <dl className="grid grid-cols-3 gap-4">
            {buckets.map((entry) => (
              <div key={entry.bucket}>
                <dt className="flex items-center gap-1.5 text-xs text-ink-secondary">
                  <span
                    aria-hidden
                    className="h-2 w-2 rounded-full"
                    style={{ background: BUCKET_COLOR[entry.bucket] }}
                  />
                  {BUCKET_LABEL[entry.bucket]}
                </dt>
                <dd className="mt-1 text-lg font-semibold text-ink">
                  {count(entry.count)}
                  <span className="ml-1.5 text-xs font-normal text-ink-muted">
                    {percent(entry.count / total)}
                  </span>
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </ChartFrame>
  );
}
