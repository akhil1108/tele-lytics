"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Shell } from "@/components/Shell";
import {
  Badge,
  Button,
  EmptyState,
  ErrorNote,
  Input,
  Select,
  Spinner,
} from "@/components/ui";
import { api, type CallFilters } from "@/lib/api";
import { BUCKET_COLOR, scoreColor, sentimentBucket } from "@/lib/charts";
import {
  PROCESSING_LABELS,
  SENTIMENT_LABELS,
  count,
  dateTime,
  decimal,
  directionLabel,
  duration,
} from "@/lib/format";
import type { CallListItem, ProcessingStatus } from "@/lib/types";

const PAGE_SIZE = 25;

const RANGES = [
  { value: "1", label: "Last 24 hours" },
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];
const DIRECTIONS = [
  { value: "", label: "Any direction" },
  { value: "inbound", label: "Inbound" },
  { value: "outbound", label: "Outbound" },
  { value: "unknown", label: "Direction unknown" },
];
const SENTIMENTS = [
  { value: "", label: "Any sentiment" },
  { value: "very_negative", label: "Very negative" },
  { value: "negative", label: "Negative" },
  { value: "neutral", label: "Neutral" },
  { value: "positive", label: "Positive" },
  { value: "very_positive", label: "Very positive" },
];
const RECORDED = [
  { value: "", label: "All calls" },
  { value: "true", label: "With recording" },
  { value: "false", label: "Without recording" },
];

/** Processing state reads as words first; colour only reinforces it. */
function ProcessingBadge({ status }: { status: ProcessingStatus }) {
  const color = {
    complete: "var(--status-good)",
    analysing: "var(--series-1)",
    transcribing: "var(--series-2)",
    no_recording: "var(--text-muted)",
    failed: "var(--status-critical)",
  }[status];
  return <Badge color={color}>{PROCESSING_LABELS[status]}</Badge>;
}

export default function CallsPage() {
  const [range, setRange] = useState("7");
  const [direction, setDirection] = useState("");
  const [sentiment, setSentiment] = useState("");
  const [recorded, setRecorded] = useState("");
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [offset, setOffset] = useState(0);

  const filters: CallFilters = {
    days: Number(range),
    direction: direction || undefined,
    sentiment: sentiment || undefined,
    has_recording: recorded === "" ? undefined : recorded === "true",
    search: search || undefined,
    limit: PAGE_SIZE,
    offset,
  };

  const calls = useQuery({
    queryKey: ["calls", filters],
    queryFn: () => api.calls(filters),
    placeholderData: keepPreviousData,
  });

  function resetTo(setter: (value: string) => void) {
    return (value: string) => {
      setter(value);
      setOffset(0); // a changed filter invalidates the current page
    };
  }

  const page = calls.data;
  const showing = page ? page.offset + page.items.length : 0;

  return (
    <Shell>
      <header className="mb-5">
        <h1 className="text-xl font-semibold text-ink">Calls</h1>
        <p className="mt-0.5 text-sm text-ink-muted">
          Every logged call, with its transcript and insight.
        </p>
      </header>

      {/* Filters sit in one row above the table. */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <form
          className="flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setSearch(draft.trim());
            setOffset(0);
          }}
        >
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Number or customer name"
            className="w-56"
            aria-label="Search calls"
          />
          <Button type="submit">Search</Button>
          {search && (
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setDraft("");
                setSearch("");
                setOffset(0);
              }}
            >
              Clear
            </Button>
          )}
        </form>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Select value={range} onChange={resetTo(setRange)} options={RANGES} />
          <Select value={direction} onChange={resetTo(setDirection)} options={DIRECTIONS} />
          <Select value={sentiment} onChange={resetTo(setSentiment)} options={SENTIMENTS} />
          <Select value={recorded} onChange={resetTo(setRecorded)} options={RECORDED} />
        </div>
      </div>

      {calls.isError && <ErrorNote error={calls.error} />}
      {calls.isLoading && <Spinner label="Loading calls" />}

      {page && page.items.length === 0 && (
        <EmptyState
          title="No calls match these filters"
          hint="Widen the date range, or clear the search to see everything in this period."
        />
      )}

      {page && page.items.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-card border border-hairline bg-surface">
            <table className="w-full min-w-[880px] text-left text-sm">
              <thead className="border-b border-hairline text-xs text-ink-muted">
                <tr>
                  <th className="px-4 py-2.5 font-medium">When</th>
                  <th className="px-4 py-2.5 font-medium">Agent</th>
                  <th className="px-4 py-2.5 font-medium">Customer</th>
                  <th className="px-4 py-2.5 text-right font-medium">Duration</th>
                  <th className="px-4 py-2.5 font-medium">Sentiment</th>
                  <th className="px-4 py-2.5 font-medium">Satisfied</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 text-right font-medium">Tasks</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((call: CallListItem) => (
                  <tr
                    key={call.id}
                    className="border-b border-hairline last:border-0 hover:bg-surface-raised"
                  >
                    <td className="px-4 py-2.5">
                      <Link
                        href={`/calls/${call.id}`}
                        className="text-ink underline-offset-2 hover:underline"
                      >
                        {dateTime(call.started_at)}
                      </Link>
                      <span className="ml-2 text-xs text-ink-muted">
                        {directionLabel(call.direction)}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-ink-secondary">
                      {call.agent_name ?? "—"}
                    </td>
                    <td className="px-4 py-2.5 text-ink-secondary">
                      <span className="tabular">{call.customer_number}</span>
                      {call.customer_name && (
                        <span className="ml-1.5 text-xs text-ink-muted">
                          {call.customer_name}
                        </span>
                      )}
                    </td>
                    <td className="tabular px-4 py-2.5 text-right text-ink-secondary">
                      {duration(call.duration_seconds)}
                    </td>
                    <td className="px-4 py-2.5">
                      {call.sentiment_overall ? (
                        <span className="flex items-center gap-1.5 text-ink-secondary">
                          <span
                            aria-hidden
                            className="h-2 w-2 rounded-full"
                            style={{
                              background:
                                BUCKET_COLOR[sentimentBucket(call.sentiment_overall)],
                            }}
                          />
                          {SENTIMENT_LABELS[call.sentiment_overall]}
                          <span
                            className="tabular text-xs"
                            style={{ color: scoreColor(call.sentiment_score) }}
                          >
                            {decimal(call.sentiment_score)}
                          </span>
                        </span>
                      ) : (
                        <span className="text-ink-muted">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-ink-secondary">
                      {call.customer_satisfied === null
                        ? "Unclear"
                        : call.customer_satisfied
                          ? "Yes"
                          : "No"}
                      {call.csat_score !== null && (
                        <span className="tabular ml-1.5 text-xs text-ink-muted">
                          {call.csat_score}/5
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <ProcessingBadge status={call.processing_status} />
                    </td>
                    <td className="tabular px-4 py-2.5 text-right text-ink-secondary">
                      {call.open_tasks || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <nav className="mt-3 flex items-center justify-between text-xs text-ink-muted">
            <span className="tabular">
              Showing {page.offset + 1}–{showing} of {count(page.total)}
            </span>
            <div className="flex gap-2">
              <Button
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                disabled={showing >= page.total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          </nav>
        </>
      )}
    </Shell>
  );
}
