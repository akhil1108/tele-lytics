"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART } from "@/lib/charts";
import { dayLabel, decimal } from "@/lib/format";
import type { TimeseriesPoint } from "@/lib/types";

import { ChartFrame, ChartTooltip } from "./ChartFrame";

/**
 * Average customer sentiment over time.
 *
 * A single series on one axis — never paired with call volume on a second
 * y-scale, which would invite reading a relationship the data does not show.
 * The zero line is drawn because it is the meaningful threshold here.
 */
export function SentimentTrendChart({
  data,
  bucket,
}: {
  data: TimeseriesPoint[];
  bucket: "hour" | "day" | "week";
}) {
  const points = data.filter((point) => point.avg_sentiment !== null);

  return (
    <ChartFrame
      title="Sentiment trend"
      subtitle="Average customer sentiment, −1 to +1"
      table={
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-surface text-ink-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">Period</th>
              <th className="py-1.5 pr-3 text-right font-medium">Sentiment</th>
              <th className="py-1.5 text-right font-medium">Analysed</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.bucket} className="border-t border-hairline text-ink-secondary">
                <td className="py-1.5 pr-3">{dayLabel(point.bucket, bucket)}</td>
                <td className="tabular py-1.5 pr-3 text-right">
                  {decimal(point.avg_sentiment)}
                </td>
                <td className="tabular py-1.5 text-right">{point.analysed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      {points.length === 0 ? (
        <p className="flex h-full items-center justify-center text-sm text-ink-muted">
          No analysed calls in this range yet
        </p>
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis
              dataKey="bucket"
              tickFormatter={(value: string) => dayLabel(value, bucket)}
              tick={{ fill: CHART.tick, fontSize: 11 }}
              axisLine={{ stroke: CHART.axis }}
              tickLine={false}
              minTickGap={24}
            />
            <YAxis
              domain={[-1, 1]}
              ticks={[-1, -0.5, 0, 0.5, 1]}
              // Formatted explicitly with a true minus sign: a hyphen at this
              // size is easy to lose, and "0.5" where "−0.5" belongs inverts
              // the reading of the chart.
              tickFormatter={(value: number) =>
                value < 0 ? `\u2212${Math.abs(value)}` : String(value)
              }
              tick={{ fill: CHART.tick, fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={48}
            />
            <ReferenceLine y={0} stroke={CHART.axis} strokeWidth={1} />
            <Tooltip
              cursor={{ stroke: CHART.axis, strokeWidth: 1 }}
              content={({ active, payload, label }) => (
                <ChartTooltip
                  active={active}
                  label={typeof label === "string" ? dayLabel(label, bucket) : label}
                  rows={[
                    {
                      name: "Avg sentiment",
                      value: decimal(payload?.[0]?.value as number),
                      color: CHART.series1,
                    },
                  ]}
                />
              )}
            />
            <Line
              type="monotone"
              dataKey="avg_sentiment"
              stroke={CHART.series1}
              strokeWidth={2}
              dot={{ r: 3, strokeWidth: 0, fill: CHART.series1 }}
              activeDot={{ r: 5, strokeWidth: 2, stroke: CHART.surface }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </ChartFrame>
  );
}
