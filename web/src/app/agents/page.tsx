"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useCallback, useState, type FormEvent } from "react";

import { Shell } from "@/components/Shell";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorNote,
  Input,
  Select,
  Spinner,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { scoreColor } from "@/lib/charts";
import { count, decimal, duration, percent, relative } from "@/lib/format";
import { useRealtime } from "@/lib/realtime";
import type { Agent, AgentStatus } from "@/lib/types";

const STATUS_COLOR: Record<AgentStatus, string> = {
  on_call: "var(--series-1)",
  available: "var(--status-good)",
  wrap_up: "var(--status-warning)",
  break: "var(--status-serious)",
  offline: "var(--text-muted)",
};

const STATUS_LABEL: Record<AgentStatus, string> = {
  on_call: "On call",
  available: "Available",
  wrap_up: "Wrap-up",
  break: "On break",
  offline: "Offline",
};

const RANGES = [
  { value: "1", label: "Today" },
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
];

export default function AgentsPage() {
  const { canConfigure } = useAuth();
  const queryClient = useQueryClient();
  const [range, setRange] = useState("7");
  const [showForm, setShowForm] = useState(false);
  const [pairing, setPairing] = useState<{ name: string; code: string } | null>(null);

  const onRealtime = useCallback(
    (event: { event: string }) => {
      if (event.event === "agent.status") {
        queryClient.invalidateQueries({ queryKey: ["agents"] });
      }
    },
    [queryClient],
  );
  useRealtime(onRealtime);

  const agents = useQuery({
    queryKey: ["agents", range],
    queryFn: () => api.agents(Number(range)),
  });

  const createAgent = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.createAgent(body),
    onSuccess: () => {
      setShowForm(false);
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });

  const pairingCode = useMutation({
    mutationFn: (agent: Agent) =>
      api.pairingCode(agent.id).then((result) => ({ ...result, name: agent.display_name })),
    onSuccess: (result) => setPairing({ name: result.name, code: result.code }),
  });

  function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    createAgent.mutate({
      display_name: form.get("display_name"),
      phone_number: form.get("phone_number"),
      team: form.get("team") || null,
      employee_code: form.get("employee_code") || null,
    });
  }

  return (
    <Shell>
      <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">Agents</h1>
          <p className="mt-0.5 text-sm text-ink-muted">
            Registered numbers, live status and per-agent quality.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={range} onChange={setRange} options={RANGES} label="Range" />
          {canConfigure && (
            <Button variant="primary" onClick={() => setShowForm((open) => !open)}>
              {showForm ? "Cancel" : "Add agent"}
            </Button>
          )}
        </div>
      </header>

      {pairing && (
        <Card
          className="mb-4"
          title={`Pairing code for ${pairing.name}`}
          subtitle="Type this into the mobile app. It works once and expires in 30 minutes."
          actions={
            <Button variant="ghost" onClick={() => setPairing(null)}>
              Dismiss
            </Button>
          }
        >
          <p className="tabular select-all text-2xl font-semibold tracking-[0.2em] text-ink">
            {pairing.code}
          </p>
        </Card>
      )}

      {showForm && (
        <Card className="mb-4" title="Add an agent">
          <form onSubmit={onCreate} className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs text-ink-secondary">Name</span>
              <Input name="display_name" required placeholder="Priya Sharma" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-secondary">
                Phone number
              </span>
              <Input name="phone_number" required placeholder="+91 98765 43210" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-secondary">Team</span>
              <Input name="team" placeholder="Support" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-secondary">
                Employee code
              </span>
              <Input name="employee_code" placeholder="NW-101" />
            </label>
            <div className="sm:col-span-2">
              {createAgent.isError && <ErrorNote error={createAgent.error} />}
              <Button
                type="submit"
                variant="primary"
                className="mt-2"
                disabled={createAgent.isPending}
              >
                {createAgent.isPending ? "Adding…" : "Add agent"}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {agents.isLoading && <Spinner label="Loading agents" />}
      {agents.isError && <ErrorNote error={agents.error} />}
      {agents.data?.length === 0 && (
        <EmptyState
          title="No agents yet"
          hint="Add an agent with the phone number their calls are made from, then pair their handset."
        />
      )}

      {agents.data && agents.data.length > 0 && (
        <div className="overflow-x-auto rounded-card border border-hairline bg-surface">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="border-b border-hairline text-xs text-ink-muted">
              <tr>
                <th className="px-4 py-2.5 font-medium">Agent</th>
                <th className="px-4 py-2.5 font-medium">Number</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 text-right font-medium">Today</th>
                <th className="px-4 py-2.5 text-right font-medium">In range</th>
                <th className="px-4 py-2.5 text-right font-medium">Sentiment</th>
                <th className="px-4 py-2.5 text-right font-medium">Satisfied</th>
                <th className="px-4 py-2.5 text-right font-medium">Avg length</th>
                {canConfigure && <th className="px-4 py-2.5 font-medium">Handset</th>}
              </tr>
            </thead>
            <tbody>
              {agents.data.map((agent) => (
                <tr key={agent.id} className="border-b border-hairline last:border-0">
                  <td className="px-4 py-2.5">
                    <span className="text-ink">{agent.display_name}</span>
                    {agent.team && (
                      <span className="ml-1.5 text-xs text-ink-muted">{agent.team}</span>
                    )}
                    <p className="text-xs text-ink-muted">
                      seen {relative(agent.last_seen_at)}
                    </p>
                  </td>
                  <td className="tabular px-4 py-2.5 text-ink-secondary">
                    {agent.phone_number}
                  </td>
                  <td className="px-4 py-2.5">
                    <Badge color={STATUS_COLOR[agent.status]}>
                      {STATUS_LABEL[agent.status]}
                    </Badge>
                    {agent.status === "on_call" && agent.current_call_id && (
                      <Link
                        href={`/calls/${agent.current_call_id}`}
                        className="ml-1.5 text-xs text-ink-muted underline-offset-2 hover:underline"
                      >
                        view
                      </Link>
                    )}
                  </td>
                  <td className="tabular px-4 py-2.5 text-right text-ink-secondary">
                    {count(agent.calls_today)}
                  </td>
                  <td className="tabular px-4 py-2.5 text-right text-ink-secondary">
                    {count(agent.calls_in_range)}
                  </td>
                  <td
                    className="tabular px-4 py-2.5 text-right font-medium"
                    style={{ color: scoreColor(agent.avg_sentiment) }}
                  >
                    {decimal(agent.avg_sentiment)}
                  </td>
                  <td className="tabular px-4 py-2.5 text-right text-ink-secondary">
                    {percent(agent.satisfied_rate)}
                  </td>
                  <td className="tabular px-4 py-2.5 text-right text-ink-secondary">
                    {duration(agent.avg_duration_seconds)}
                  </td>
                  {canConfigure && (
                    <td className="px-4 py-2.5">
                      <Button
                        className="px-2 py-1 text-xs"
                        onClick={() => pairingCode.mutate(agent)}
                        disabled={pairingCode.isPending}
                      >
                        Pair
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {pairingCode.isError && (
        <div className="mt-3">
          <ErrorNote error={pairingCode.error} />
        </div>
      )}
    </Shell>
  );
}
