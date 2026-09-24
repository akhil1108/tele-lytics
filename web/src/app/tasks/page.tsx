"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Shell } from "@/components/Shell";
import {
  Badge,
  Button,
  EmptyState,
  ErrorNote,
  Select,
  Spinner,
} from "@/components/ui";
import { api } from "@/lib/api";
import { severityColor } from "@/lib/charts";
import { count, dateTime, titleCase } from "@/lib/format";
import type { ActionItem } from "@/lib/types";

const PAGE_SIZE = 25;

const KINDS = [
  { value: "", label: "Tasks and actions" },
  { value: "task", label: "Committed on calls" },
  { value: "action", label: "Recommended steps" },
];
const PRIORITIES = [
  { value: "", label: "Any priority" },
  { value: "urgent", label: "Urgent" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];
const VIEWS = [
  { value: "open", label: "Open" },
  { value: "overdue", label: "Overdue" },
  { value: "done", label: "Completed" },
];

export default function TasksPage() {
  const queryClient = useQueryClient();
  const [view, setView] = useState("open");
  const [kind, setKind] = useState("");
  const [priority, setPriority] = useState("");
  const [offset, setOffset] = useState(0);

  const params: Record<string, unknown> = {
    kind: kind || undefined,
    priority: priority || undefined,
    status: view === "done" ? "done" : undefined,
    overdue_only: view === "overdue" ? true : undefined,
    limit: PAGE_SIZE,
    offset,
  };

  const tasks = useQuery({
    queryKey: ["tasks", params],
    queryFn: () => api.tasks(params),
    placeholderData: keepPreviousData,
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.updateTask(id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tasks"] }),
  });

  const page = tasks.data;
  const isOverdue = (item: ActionItem) =>
    item.due_at !== null && new Date(item.due_at) < new Date() && item.status !== "done";

  return (
    <Shell>
      <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">Tasks</h1>
          <p className="mt-0.5 text-sm text-ink-muted">
            What was promised on calls, and what the model recommends doing next.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={view}
            onChange={(value) => {
              setView(value);
              setOffset(0);
            }}
            options={VIEWS}
          />
          <Select
            value={kind}
            onChange={(value) => {
              setKind(value);
              setOffset(0);
            }}
            options={KINDS}
          />
          <Select
            value={priority}
            onChange={(value) => {
              setPriority(value);
              setOffset(0);
            }}
            options={PRIORITIES}
          />
        </div>
      </header>

      {tasks.isLoading && <Spinner label="Loading tasks" />}
      {tasks.isError && <ErrorNote error={tasks.error} />}
      {page?.items.length === 0 && (
        <EmptyState
          title={view === "done" ? "Nothing completed yet" : "Nothing outstanding"}
          hint="Tasks appear here automatically as calls are analysed."
        />
      )}

      {page && page.items.length > 0 && (
        <>
          <ul className="space-y-2">
            {page.items.map((item) => (
              <li
                key={item.id}
                className="rounded-card border border-hairline bg-surface px-4 py-3"
              >
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 shrink-0"
                    checked={item.status === "done"}
                    aria-label={`Mark "${item.title}" ${item.status === "done" ? "open" : "done"}`}
                    onChange={() =>
                      update.mutate({
                        id: item.id,
                        body: { status: item.status === "done" ? "open" : "done" },
                      })
                    }
                  />
                  <div className="min-w-0 flex-1">
                    <p
                      className={
                        item.status === "done"
                          ? "text-sm text-ink-muted line-through"
                          : "text-sm text-ink"
                      }
                    >
                      {item.title}
                    </p>
                    {item.description && (
                      <p className="mt-0.5 text-xs text-ink-secondary">
                        {item.description}
                      </p>
                    )}

                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                      <Badge color={severityColor(item.priority)}>
                        {titleCase(item.priority)}
                      </Badge>
                      <Badge>{item.kind === "task" ? "Committed" : "Recommended"}</Badge>
                      {item.agent_name && (
                        <span className="text-ink-muted">{item.agent_name}</span>
                      )}
                      {item.customer_number && (
                        <span className="tabular text-ink-muted">
                          {item.customer_number}
                        </span>
                      )}
                      {item.due_at && (
                        <span
                          style={
                            isOverdue(item)
                              ? { color: "var(--status-critical)" }
                              : undefined
                          }
                        >
                          {isOverdue(item) ? "Overdue " : "Due "}
                          {dateTime(item.due_at)}
                        </span>
                      )}
                      {!item.due_at && item.due_hint && (
                        <span className="text-ink-muted">due: {item.due_hint}</span>
                      )}
                      <Link
                        href={`/calls/${item.call_id}`}
                        className="ml-auto text-ink-secondary underline-offset-2 hover:underline"
                      >
                        Open call
                      </Link>
                    </div>

                    {item.source_quote && (
                      <blockquote className="mt-2 border-l-2 border-hairline pl-2.5 text-xs italic text-ink-muted">
                        “{item.source_quote}”
                      </blockquote>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>

          <nav className="mt-3 flex items-center justify-between text-xs text-ink-muted">
            <span className="tabular">
              {page.offset + 1}–{page.offset + page.items.length} of {count(page.total)}
            </span>
            <div className="flex gap-2">
              <Button
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                disabled={page.offset + page.items.length >= page.total}
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
