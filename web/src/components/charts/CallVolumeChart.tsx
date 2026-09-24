"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART } from "@/lib/charts";
import { count, dayLabel } from "@/lib/format";
import type { TimeseriesPoint } from "@/lib/types";

import { ChartFrame, ChartTooltip } from "./ChartFrame";

export function CallVolumeChart({
  data,
  bucket,
}: {
  data: TimeseriesPoint[];
  bucket: "hour" | "day" | "week";
}) {
  const legend = [
    { label: "Calls", color: CHART.series1 },
    { label: "Recorded", color: CHART.series2 },
  ];

  return (
    <ChartFrame
      title="Call volume"
      subtitle="Calls handled, and how many produced a recording"
      legend={legend}
      table={
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-surface text-ink-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">Period</th>
              <th className="py-1.5 pr-3 text-right font-medium">Calls</th>
              <th className="py-1.5 pr-3 text-right font-medium">Recorded</th>
              <th className="py-1.5 text-right font-medium">Analysed</th>
            </tr>
          </thead>
          <tbody>
            {data.map((point) => (
              <tr key={point.bucket} className="border-t border-hairline text-ink-secondary">
                <td className="py-1.5 pr-3">{dayLabel(point.bucket, bucket)}</td>
                <td className="tabular py-1.5 pr-3 text-right">{count(point.calls)}</td>
                <td className="tabular py-1.5 pr-3 text-right">{count(point.recorded)}</td>
                <td className="tabular py-1.5 text-right">{count(point.analysed)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
          <defs>
            <linearGradient id="callsFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART.series1} stopOpacity={0.22} />
              <stop offset="100%" stopColor={CHART.series1} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          {/* Horizontal rules only: vertical ones add ink without adding meaning. */}
          <CartesianGrid stroke={CHART.grid} strokeDasharray="0" vertical={false} />
          <XAxis
            dataKey="bucket"
            tickFormatter={(value: string) => dayLabel(value, bucket)}
            tick={{ fill: CHART.tick, fontSize: 11 }}
            axisLine={{ stroke: CHART.axis }}
            tickLine={false}
            minTickGap={24}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fill: CHART.tick, fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={44}
          />
          <Tooltip
            cursor={{ stroke: CHART.axis, strokeWidth: 1 }}
            content={({ active, payload, label }) => (
              <ChartTooltip
                active={active}
                label={typeof label === "string" ? dayLabel(label, bucket) : label}
                rows={(payload ?? []).map((entry) => ({
                  name: entry.name === "calls" ? "Calls" : "Recorded",
                  value: count(entry.value as number),
                  color: entry.color,
                }))}
              />
            )}
          />
          <Area
            type="monotone"
            dataKey="calls"
            stroke={CHART.series1}
            strokeWidth={2}
            fill="url(#callsFill)"
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: CHART.surface }}
          />
          <Area
            type="monotone"
            dataKey="recorded"
            stroke={CHART.series2}
            strokeWidth={2}
            fill="transparent"
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: CHART.surface }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
