"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { AudioPlayer } from "@/components/AudioPlayer";
import { SentimentTimeline } from "@/components/charts/SentimentTimeline";
import {
  CustomRatingsPanel,
  LanguagePanel,
  RiskPanel,
  TasksPanel,
  VerdictPanel,
} from "@/components/InsightPanels";
import { Shell } from "@/components/Shell";
import { ToneSummary, TranscriptView } from "@/components/TranscriptView";
import { Badge, Button, Card, EmptyState, ErrorNote, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  dateTime,
  directionLabel,
  duration,
  isMetadataOnly,
  policyReason,
  titleCase,
} from "@/lib/format";
import type { ActionItem, Lead } from "@/lib/types";

export default function CallDetailPage() {
  const params = useParams<{ id: string }>();
  const callId = params.id;
  const queryClient = useQueryClient();
  const { canConfigure } = useAuth();

  const [seekToMs, setSeekToMs] = useState<number | null>(null);
  const [playheadMs, setPlayheadMs] = useState(0);

  const call = useQuery({
    queryKey: ["call", callId],
    queryFn: () => api.call(callId),
    // While a call is still moving through the pipeline, poll so the page
    // fills in as each stage lands.
    refetchInterval: (query) =>
      query.state.data?.analysis ? false : 5_000,
  });

  const reprocess = useMutation({
    mutationFn: (stage: "transcribe" | "analyze") => api.reprocess(callId, stage),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["call", callId] }),
  });

  const toggleTask = useMutation({
    mutationFn: (item: ActionItem) =>
      api.updateTask(item.id, { status: item.status === "done" ? "open" : "done" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["call", callId] }),
  });

  const lead = useQuery({
    queryKey: ["lead-for-call", callId],
    queryFn: () => api.leads({ call_id: callId, limit: 1 }),
    enabled: Boolean(call.data?.analysis),
  });
  const leadUpdate = useMutation({
    mutationFn: (status: string) => api.updateLead(lead.data!.items[0].id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["lead-for-call", callId] }),
  });

  if (call.isLoading) {
    return (
      <Shell>
        <Spinner label="Loading call" />
      </Shell>
    );
  }
  if (call.isError) {
    return (
      <Shell>
        <ErrorNote error={call.error} />
      </Shell>
    );
  }

  const data = call.data!;
  const failedJob = data.jobs.find((job) => job.status === "failed");

  return (
    <Shell>
      <nav className="mb-4 text-xs text-ink-muted">
        <Link href="/calls" className="underline-offset-2 hover:underline">
          Calls
        </Link>
        <span className="mx-1.5">/</span>
        <span>{dateTime(data.started_at)}</span>
      </nav>

      <header className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink">
            {data.customer_name ?? data.customer_number}
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-muted">
            <span>
              {data.direction === "unknown"
                ? "Direction unknown"
                : `${directionLabel(data.direction)} call`}
            </span>
            <span className="tabular">{data.customer_number}</span>
            <span>·</span>
            <span>{data.agent_name}</span>
            {data.agent_team && <span className="text-xs">{data.agent_team}</span>}
            <span>·</span>
            <span>{duration(data.duration_seconds)}</span>
          </p>
        </div>
        {canConfigure && (
          <div className="flex gap-2">
            <Button
              onClick={() => reprocess.mutate("transcribe")}
              disabled={!data.has_recording || reprocess.isPending}
            >
              Re-transcribe
            </Button>
            <Button
              onClick={() => reprocess.mutate("analyze")}
              disabled={!data.transcript || reprocess.isPending}
            >
              Re-analyse
            </Button>
          </div>
        )}
      </header>

      {reprocess.isSuccess && (
        <p className="mb-4 text-sm text-ink-secondary">{reprocess.data.message}</p>
      )}
      {reprocess.isError && <ErrorNote error={reprocess.error} />}

      {failedJob && (
        <div
          role="alert"
          className="mb-4 rounded-card border border-hairline px-4 py-3 text-sm"
        >
          <p className="font-medium" style={{ color: "var(--status-critical)" }}>
            {titleCase(failedJob.stage)} failed after {failedJob.attempts} attempts
          </p>
          {failedJob.last_error && (
            <p className="mt-1 text-xs text-ink-secondary">{failedJob.last_error}</p>
          )}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-4">
          {data.analysis && <VerdictPanel analysis={data.analysis} />}

          {data.transcript ? (
            <Card
              title="Transcript"
              subtitle={
                `${data.transcript.provider}` +
                (data.transcript.language ? ` · ${data.transcript.language}` : "") +
                ` · ${data.transcript.word_count} words`
              }
            >
              <TranscriptView
                transcript={data.transcript}
                onSeek={setSeekToMs}
                activeMs={playheadMs}
              />
            </Card>
          ) : (
            <Card title="Transcript">
              <EmptyState
                title={
                  data.has_recording
                    ? "Transcription is still running"
                    : "This call has no recording"
                }
                hint={
                  data.has_recording
                    ? "The page refreshes on its own as each stage completes."
                    : data.recording_skipped_reason
                      ? policyReason(data.recording_skipped_reason)
                      : "No audio was uploaded for this call."
                }
              />
            </Card>
          )}

          {data.analysis && (
            <TasksPanel
              items={data.action_items}
              onToggle={(item) => toggleTask.mutate(item)}
            />
          )}
          {data.analysis && <CustomRatingsPanel analysis={data.analysis} />}
          {data.analysis && <LanguagePanel analysis={data.analysis} />}
          {data.analysis && <RiskPanel analysis={data.analysis} />}
        </div>

        <aside className="space-y-4">
          <Card title="Recording">
            {data.recording?.status === "stored" ? (
              <>
                <AudioPlayer
                  callId={callId}
                  seekToMs={seekToMs}
                  onTimeUpdate={setPlayheadMs}
                />
                <dl className="mt-3 space-y-1 text-xs">
                  <Row label="Source" value={sourceLabel(data.call_metadata?.source)} />
                  <Row
                    label="Consent captured"
                    value={data.recording.consent_captured ? "Yes" : "No"}
                  />
                  <Row label="Uploaded" value={dateTime(data.recording.uploaded_at)} />
                  <Row
                    label="Deleted after"
                    value={
                      data.recording.purge_after
                        ? dateTime(data.recording.purge_after)
                        : "Kept indefinitely"
                    }
                  />
                </dl>

                {isDiallerRecording(data.call_metadata?.source) && (
                  <p className="mt-3 text-xs text-ink-muted">
                    {/* Without this, "consent captured: No" reads as a compliance
                        failure rather than a fact about how the file arrived. */}
                    This recording came from the handset&apos;s own dialler, which
                    carries no record of a consent announcement. Recording was still
                    checked against this number&apos;s policy before it was accepted.
                  </p>
                )}
              </>
            ) : data.recording?.status === "purged" ? (
              <p className="text-sm text-ink-muted">
                The audio was deleted under the retention policy on{" "}
                {dateTime(data.recording.purged_at)}. The transcript and analysis are kept.
              </p>
            ) : (
              <>
                <p className="text-sm text-ink-muted">
                  {data.recording_skipped_reason
                    ? policyReason(data.recording_skipped_reason)
                    : "No recording was uploaded for this call."}
                </p>
                {isMetadataOnly(data.recording_skipped_reason) && (
                  <p className="mt-2 text-xs text-ink-muted">
                    {/* Otherwise an empty player reads as a failure rather than
                        as a call that was only ever going to have metadata. */}
                    This call was reported from the handset&apos;s call log, so its
                    number, direction and duration are exact — there is simply no audio
                    to transcribe.
                  </p>
                )}
              </>
            )}
          </Card>

          {lead.data?.items[0] && (
            <LeadCard
              lead={lead.data.items[0]}
              onStatusChange={(status) => leadUpdate.mutate(status)}
              updating={leadUpdate.isPending}
            />
          )}

          {data.analysis && (
            <Card title="Sentiment through the call">
              <SentimentTimeline
                points={data.analysis.sentiment_timeline}
                durationSeconds={data.duration_seconds}
                onSeek={setSeekToMs}
              />
            </Card>
          )}

          {data.analysis && Object.keys(data.analysis.tone_summary).length > 0 && (
            <Card title="Tone">
              <ToneSummary tone={data.analysis.tone_summary} />
            </Card>
          )}

          <Card title="Processing">
            <ul className="space-y-2 text-xs">
              {data.jobs.map((job) => (
                <li key={job.id} className="flex items-center justify-between gap-2">
                  <span className="text-ink-secondary">{titleCase(job.stage)}</span>
                  <Badge
                    color={
                      job.status === "succeeded"
                        ? "var(--status-good)"
                        : job.status === "failed"
                          ? "var(--status-critical)"
                          : "var(--series-1)"
                    }
                  >
                    {titleCase(job.status)}
                  </Badge>
                </li>
              ))}
              {data.jobs.length === 0 && (
                <li className="text-ink-muted">Nothing queued for this call.</li>
              )}
            </ul>
          </Card>
        </aside>
      </div>
    </Shell>
  );
}

/** How the call reached the platform, in words a supervisor can act on. */
function sourceLabel(source: unknown): string {
  switch (source) {
    case "call_log_with_recording":
      return "Handset call log + dialler recording";
    case "call_log_only":
      return "Handset call log";
    case "device_recording_import":
      return "Imported from handset";
    default:
      return "Recorded in app";
  }
}

function isDiallerRecording(source: unknown): boolean {
  return source === "device_recording_import" || source === "call_log_with_recording";
}

function LeadCard({
  lead,
  onStatusChange,
  updating,
}: {
  lead: Lead;
  onStatusChange: (status: string) => void;
  updating: boolean;
}) {
  return (
    <Card
      title="Lead"
      subtitle={lead.category === "lead" ? "Judged a genuine lead" : "Not judged a lead"}
      actions={
        <Badge color={lead.category === "lead" ? "var(--series-1)" : "var(--text-muted)"}>
          {titleCase(lead.category)}
        </Badge>
      }
    >
      {lead.category === "lead" ? (
        <dl className="space-y-1.5 text-xs">
          <Row label="Name" value={lead.lead_name ?? "—"} />
          <Row label="Email" value={lead.lead_email ?? "—"} />
          <Row label="Purpose" value={lead.purpose ?? "—"} />
          <Row label="Intent" value={lead.intent ?? "—"} />
        </dl>
      ) : (
        <p className="text-sm text-ink-muted">{lead.reason ?? "No lead signal on this call."}</p>
      )}

      <label className="mt-3 flex items-center justify-between gap-2 text-xs">
        <span className="text-ink-muted">Status</span>
        <select
          value={lead.status}
          disabled={updating}
          onChange={(event) => onStatusChange(event.target.value)}
          className="rounded-md border border-hairline bg-surface px-2 py-1 text-xs text-ink"
        >
          <option value="new">New</option>
          <option value="contacted">Contacted</option>
          <option value="dismissed">Dismissed</option>
        </select>
      </label>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="text-ink-secondary">{value}</dd>
    </div>
  );
}
