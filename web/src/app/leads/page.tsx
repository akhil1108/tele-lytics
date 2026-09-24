"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Shell } from "@/components/Shell";
import { Badge, Button, EmptyState, ErrorNote, Input, Select, Spinner } from "@/components/ui";
import { api, type LeadFilters } from "@/lib/api";
import { count, dateTime, titleCase } from "@/lib/format";
import type { Lead } from "@/lib/types";

const PAGE_SIZE = 25;

const RANGES = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];
const CATEGORIES = [
  { value: "lead", label: "Leads only" },
  { value: "other", label: "Not leads" },
  { value: "", label: "All calls" },
];
const STATUSES = [
  { value: "", label: "Any status" },
  { value: "new", label: "New" },
  { value: "contacted", label: "Contacted" },
  { value: "dismissed", label: "Dismissed" },
];
const STATUS_OPTIONS = [
  { value: "new", label: "New" },
  { value: "contacted", label: "Contacted" },
  { value: "dismissed", label: "Dismissed" },
];

const STATUS_COLOR: Record<string, string> = {
  new: "var(--series-2)",
  contacted: "var(--status-good)",
  dismissed: "var(--text-muted)",
};

/**
 * The pipeline's per-call lead verdict — every analysed call gets a row here,
 * tagged `lead` or `other`, so a supervisor can both work real leads and audit
 * what got filtered out. See `app/services/pipeline.py::_upsert_lead`.
 */
export default function LeadsPage() {
  const queryClient = useQueryClient();
  const [range, setRange] = useState("30");
  const [category, setCategory] = useState("lead");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [offset, setOffset] = useState(0);

  const filters: LeadFilters = {
    days: Number(range),
    category: category || undefined,
    status: status || undefined,
    search: search || undefined,
    limit: PAGE_SIZE,
    offset,
  };

  const leads = useQuery({
    queryKey: ["leads", filters],
    queryFn: () => api.leads(filters),
    placeholderData: keepPreviousData,
  });

  const updateStatus = useMutation({
    mutationFn: ({ id, status: next }: { id: string; status: string }) =>
      api.updateLead(id, next),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["leads"] }),
  });

  function resetTo(setter: (value: string) => void) {
    return (value: string) => {
      setter(value);
      setOffset(0);
    };
  }

  const page = leads.data;
  const showing = page ? page.offset + page.items.length : 0;

  return (
    <Shell>
      <header className="mb-5">
        <h1 className="text-xl font-semibold text-ink">Leads</h1>
        <p className="mt-0.5 text-sm text-ink-muted">
          Contact and intent captured from calls, with the model&apos;s lead-or-other
          verdict.
        </p>
      </header>

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
            placeholder="Name, email, or number"
            className="w-64"
            aria-label="Search leads"
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
          <Select value={category} onChange={resetTo(setCategory)} options={CATEGORIES} />
          <Select value={status} onChange={resetTo(setStatus)} options={STATUSES} />
        </div>
      </div>

      {leads.isError && <ErrorNote error={leads.error} />}
      {leads.isLoading && <Spinner label="Loading leads" />}

      {page && page.items.length === 0 && (
        <EmptyState
          title="No leads match these filters"
          hint="Widen the date range, or clear the search to see everything in this period."
        />
      )}

      {page && page.items.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-card border border-hairline bg-surface">
            <table className="w-full min-w-[960px] text-left text-sm">
              <thead className="border-b border-hairline text-xs text-ink-muted">
                <tr>
                  <th className="px-4 py-2.5 font-medium">When</th>
                  <th className="px-4 py-2.5 font-medium">Customer</th>
                  <th className="px-4 py-2.5 font-medium">Contact</th>
                  <th className="px-4 py-2.5 font-medium">Purpose</th>
                  <th className="px-4 py-2.5 font-medium">Intent</th>
                  <th className="px-4 py-2.5 font-medium">Category</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((lead: Lead) => (
                  <tr
                    key={lead.id}
                    className="border-b border-hairline last:border-0 hover:bg-surface-raised"
                  >
                    <td className="px-4 py-2.5">
                      <Link
                        href={`/calls/${lead.call_id}`}
                        className="text-ink underline-offset-2 hover:underline"
                      >
                        {dateTime(lead.call_started_at ?? lead.created_at)}
                      </Link>
                    </td>
                    <td className="px-4 py-2.5 text-ink-secondary">
                      <span className="tabular">{lead.customer_number}</span>
                      {lead.customer_name && (
                        <span className="ml-1.5 text-xs text-ink-muted">
                          {lead.customer_name}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-ink-secondary">
                      {lead.lead_name && <p>{lead.lead_name}</p>}
                      {lead.lead_email && (
                        <p className="text-xs text-ink-muted">{lead.lead_email}</p>
                      )}
                      {!lead.lead_name && !lead.lead_email && (
                        <span className="text-ink-muted">—</span>
                      )}
                    </td>
                    <td className="max-w-[220px] truncate px-4 py-2.5 text-ink-secondary">
                      {lead.purpose ?? "—"}
                    </td>
                    <td className="max-w-[200px] truncate px-4 py-2.5 text-ink-secondary">
                      {lead.intent ?? "—"}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge
                        color={
                          lead.category === "lead"
                            ? "var(--series-1)"
                            : "var(--text-muted)"
                        }
                        title={lead.reason ?? undefined}
                      >
                        {titleCase(lead.category)}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      <label className="sr-only" htmlFor={`status-${lead.id}`}>
                        Status for {lead.customer_number}
                      </label>
                      <select
                        id={`status-${lead.id}`}
                        value={lead.status}
                        disabled={updateStatus.isPending}
                        onChange={(event) =>
                          updateStatus.mutate({ id: lead.id, status: event.target.value })
                        }
                        className="rounded-md border border-hairline bg-surface px-2 py-1 text-xs text-ink"
                        style={{ color: STATUS_COLOR[lead.status] }}
                      >
                        {STATUS_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
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
