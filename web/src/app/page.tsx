"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useCallback, useState } from "react";

import { CallVolumeChart } from "@/components/charts/CallVolumeChart";
import { FillerChart } from "@/components/charts/FillerChart";
import { SentimentChart } from "@/components/charts/SentimentChart";
import { SentimentTrendChart } from "@/components/charts/SentimentTrendChart";
import { Shell } from "@/components/Shell";
import { Badge, Card, ErrorNote, MiniBar, Select, Spinner, StatTile } from "@/components/ui";
import { api } from "@/lib/api";
import { CHART, scoreColor, severityColor } from "@/lib/charts";
import { count, decimal, duration, percent, titleCase } from "@/lib/format";
import { useRealtime } from "@/lib/realtime";

const RANGES = [
  { value: "1", label: "Last 24 hours" },
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];

function bucketFor(days: number): "hour" | "day" | "week" {
  if (days <= 2) return "hour";
  if (days <= 90) return "day";
  return "week";
}

export default function DashboardPage() {
  const [range, setRange] = useState("7");
  const days = Number(range);
  const bucket = bucketFor(days);
  const queryClient = useQueryClient();

  // A finished call changes almost every figure here, so the whole page is
  // refreshed rather than trying to patch individual counters.
  const onRealtime = useCallback(
    (event: { event: string }) => {
      if (event.event === "call.logged" || event.event === "recording.uploaded") {
        queryClient.invalidateQueries();
      }
    },
    [queryClient],
  );
  const { presence } = useRealtime(onRealtime);

  const overview = useQuery({
    queryKey: ["overview", days],
    queryFn: () => api.overview(days),
    refetchInterval: 60_000,
  });
  const series = useQuery({
    queryKey: ["timeseries", days, bucket],
    queryFn: () => api.timeseries(days, bucket),
  });
  const sentiment = useQuery({
    queryKey: ["sentiment", days],
    queryFn: () => api.sentimentBreakdown(days),
  });
  const leaderboard = useQuery({
    queryKey: ["leaderboard", days],
    queryFn: () => api.leaderboard(days, 8),
  });
  const fillers = useQuery({
    queryKey: ["fillers", days],
    queryFn: () => api.fillers(days),
  });
  const risks = useQuery({ queryKey: ["risks", days], queryFn: () => api.risks(days) });
  const coverage = useQuery({
    queryKey: ["coverage", days],
    queryFn: () => api.recordingCoverage(days),
  });

  const metrics = overview.data;
  const onCall = presence?.on_call ?? metrics?.agents_on_call ?? 0;

  return (
    <Shell>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">Dashboard</h1>
          <p className="mt-0.5 text-sm text-ink-muted">
            Live floor status and call insight across your organisation.
          </p>
        </div>
        <Select value={range} onChange={setRange} options={RANGES} label="Range" />
      </header>

      {overview.isError && <ErrorNote error={overview.error} />}
      {overview.isLoading && <Spinner label="Loading dashboard" />}

      {metrics && (
        <>
          <section
            aria-label="Live floor"
            className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4"
          >
            <StatTile
              label="Agents on call"
              value={count(onCall)}
              hint={`${count(metrics.agents_online)} of ${count(metrics.agents_total)} online`}
            />
            <StatTile
              label="Calls handled"
              value={count(metrics.calls_total)}
              hint={`${count(metrics.calls_inbound)} in · ${count(metrics.calls_outbound)} out`}
            />
            <StatTile
              label="Talk time"
              value={duration(metrics.total_talk_seconds)}
              hint={`avg ${duration(metrics.avg_duration_seconds)} per call`}
            />
            <StatTile
              label="Open tasks"
              value={count(metrics.open_tasks)}
              tone={metrics.overdue_tasks > 0 ? "warning" : "default"}
              hint={
                metrics.overdue_tasks > 0
                  ? `${count(metrics.overdue_tasks)} overdue`
                  : "nothing overdue"
              }
            />
          </section>

          <section
            aria-label="Insight"
            className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4"
          >
            <StatTile
              label="Avg sentiment"
              value={
                <span style={{ color: scoreColor(metrics.avg_sentiment) }}>
                  {decimal(metrics.avg_sentiment)}
                </span>
              }
              hint={`${count(metrics.calls_analysed)} calls analysed`}
            />
            <StatTile
              label="Customers satisfied"
              value={percent(metrics.satisfaction_rate)}
              tone={
                metrics.satisfaction_rate !== null && metrics.satisfaction_rate < 0.6
                  ? "warning"
                  : "default"
              }
              hint={
                /* Abstentions are shown, not folded into the rate — a call the
                   model could not judge is not a dissatisfied customer. */
                `${count(metrics.satisfied_count)} yes · ${count(metrics.unsatisfied_count)} no · ${count(metrics.unknown_satisfaction_count)} unclear`
              }
            />
            <StatTile
              label="Recording coverage"
              value={percent(metrics.recording_coverage)}
              tone={
                metrics.recording_coverage !== null && metrics.recording_coverage < 0.9
                  ? "warning"
                  : "default"
              }
              hint={`${count(metrics.numbers_with_recording_enabled)} of ${count(metrics.numbers_total)} numbers set to record`}
            />
            <StatTile
              label="Agent filler rate"
              value={
                metrics.avg_filler_rate === null
                  ? "—"
                  : `${decimal(metrics.avg_filler_rate, 1)}`
              }
              hint="filler words per 100 spoken"
            />
          </section>

          {(metrics.pipeline_failed > 0 || metrics.pipeline_queued > 0) && (
            <div className="mb-6 flex flex-wrap items-center gap-3 rounded-card border border-hairline bg-surface px-4 py-3 text-sm">
              <span className="font-medium text-ink">Processing</span>
              <Badge color={CHART.series1}>{count(metrics.pipeline_queued)} queued</Badge>
              <Badge color={CHART.series2}>{count(metrics.pipeline_running)} running</Badge>
              {metrics.pipeline_failed > 0 && (
                <Badge color={severityColor("urgent")}>
                  {count(metrics.pipeline_failed)} failed
                </Badge>
              )}
              <Link
                href="/calls?status=failed"
                className="ml-auto text-xs text-ink-secondary underline-offset-2 hover:underline"
              >
                Review
              </Link>
            </div>
          )}

          <div className="mb-4 grid gap-4 lg:grid-cols-2">
            {series.data && <CallVolumeChart data={series.data} bucket={bucket} />}
            {sentiment.data && <SentimentChart data={sentiment.data} />}
          </div>

          <div className="mb-4 grid items-start gap-4 lg:grid-cols-2">
            {series.data && <SentimentTrendChart data={series.data} bucket={bucket} />}
            {fillers.data && <FillerChart data={fillers.data} />}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card
              title="Agents"
              subtitle="Busiest agents in this range"
              actions={
                <Link href="/agents" className="text-xs text-ink-secondary hover:text-ink">
                  All agents
                </Link>
              }
            >
              {leaderboard.data?.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs text-ink-muted">
                      <tr>
                        <th className="pb-2 pr-3 font-medium">Agent</th>
                        <th className="pb-2 pr-3 text-right font-medium">Calls</th>
                        <th className="pb-2 pr-3 text-right font-medium">Sentiment</th>
                        <th className="pb-2 text-right font-medium">Satisfied</th>
                      </tr>
                    </thead>
                    <tbody>
                      {leaderboard.data.map((row) => (
                        <tr key={row.agent_id} className="border-t border-hairline">
                          <td className="py-2 pr-3">
                            <span className="text-ink">{row.agent_name}</span>
                            {row.team && (
                              <span className="ml-1.5 text-xs text-ink-muted">{row.team}</span>
                            )}
                          </td>
                          <td className="tabular py-2 pr-3 text-right text-ink-secondary">
                            {count(row.calls)}
                          </td>
                          <td
                            className="tabular py-2 pr-3 text-right font-medium"
                            style={{ color: scoreColor(row.avg_sentiment) }}
                          >
                            {decimal(row.avg_sentiment)}
                          </td>
                          <td className="tabular py-2 text-right text-ink-secondary">
                            {percent(row.satisfaction_rate)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-ink-muted">No calls in this range yet.</p>
              )}
            </Card>

            <Card
              title="Recording coverage by number"
              subtitle="Configuration next to what actually happened"
              actions={
                <Link href="/numbers" className="text-xs text-ink-secondary hover:text-ink">
                  Manage
                </Link>
              }
            >
              {coverage.data?.length ? (
                <ul className="space-y-3">
                  {coverage.data.slice(0, 6).map((row) => (
                    <li key={row.number}>
                      <div className="flex items-baseline justify-between gap-3 text-sm">
                        <span className="truncate text-ink">
                          {row.label ?? row.number}
                        </span>
                        <span className="tabular shrink-0 text-xs text-ink-muted">
                          {count(row.recorded)}/{count(row.calls)} recorded
                        </span>
                      </div>
                      <div className="mt-1.5 flex items-center gap-2">
                        <MiniBar
                          value={row.recorded}
                          max={row.calls}
                          color={row.recording_enabled ? CHART.series1 : CHART.neutral}
                          title={`${percent(row.coverage)} coverage`}
                        />
                        {/* A colour never carries this alone — the words do. */}
                        <span className="shrink-0 text-xs text-ink-muted">
                          {row.recording_enabled ? "Recording on" : "Recording off"}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-ink-muted">No calls in this range yet.</p>
              )}
            </Card>
          </div>

          {risks.data && risks.data.length > 0 && (
            <Card className="mt-4" title="Risk flags" subtitle="Raised by the insight model">
              <ul className="flex flex-wrap gap-2">
                {risks.data.map((risk) => (
                  <li key={risk.kind}>
                    <Badge color={severityColor(risk.severity_high > 0 ? "high" : "medium")}>
                      {titleCase(risk.kind)} · {count(risk.count)}
                      {risk.severity_high > 0 && ` (${risk.severity_high} high)`}
                    </Badge>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </Shell>
  );
}
