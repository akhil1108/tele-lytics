"use client";

import { CHART } from "@/lib/charts";
import { count } from "@/lib/format";
import type { TermCount } from "@/lib/types";

import { ChartFrame } from "./ChartFrame";

/**
 * Most-used filler words across the range.
 *
 * One series, so no legend — the title names it. Bar length carries magnitude
 * and every bar is directly labelled, which is what makes this readable
 * without leaning on colour at all.
 */
export function FillerChart({ data }: { data: TermCount[] }) {
  const rows = data.slice(0, 10);
  const max = Math.max(1, ...rows.map((row) => row.count));

  return (
    <ChartFrame
      title="Filler words used by agents"
      subtitle="Padding that carries no content — a coaching signal, not a defect"
      height={rows.length ? rows.length * 30 + 12 : 120}
      table={
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-surface text-ink-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">Term</th>
              <th className="py-1.5 text-right font-medium">Uses</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.term} className="border-t border-hairline text-ink-secondary">
                <td className="py-1.5 pr-3">{row.term}</td>
                <td className="tabular py-1.5 text-right">{count(row.count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      {rows.length === 0 ? (
        <p className="flex h-full items-center justify-center text-sm text-ink-muted">
          Nothing to show yet — filler counts appear once calls are analysed
        </p>
      ) : (
        <ul className="flex h-full flex-col justify-start gap-2">
          {rows.map((row) => (
            <li key={row.term} className="flex items-center gap-3 text-xs">
              <span className="w-24 shrink-0 truncate text-ink-secondary" title={row.term}>
                {row.term}
              </span>
              <span className="h-4 flex-1">
                <span
                  className="block h-full rounded-r-[4px]"
                  style={{
                    width: `${(row.count / max) * 100}%`,
                    background: CHART.series1,
                  }}
                />
              </span>
              <span className="tabular w-10 shrink-0 text-right font-medium text-ink">
                {count(row.count)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </ChartFrame>
  );
}
