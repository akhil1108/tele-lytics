"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

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
  Toggle,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { policyReason, titleCase } from "@/lib/format";
import type { PolicyDecision, RecordingPolicy } from "@/lib/types";

const FILTERS = [
  { value: "", label: "All numbers" },
  { value: "true", label: "Recording on" },
  { value: "false", label: "Recording off" },
];

/**
 * Per-number recording configuration.
 *
 * This page is the answer to "is recording set for this number?" — and it also
 * runs the *same* resolver the handset uses, so an operator can confirm what a
 * given number will actually do before trusting it.
 */
export default function NumbersPage() {
  const { canConfigure } = useAuth();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [lookupNumber, setLookupNumber] = useState("");
  const [decision, setDecision] = useState<PolicyDecision | null>(null);

  const policies = useQuery({
    queryKey: ["policies", filter],
    queryFn: () =>
      api.policies({
        recording_enabled: filter === "" ? undefined : filter === "true",
        limit: 100,
      }),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.updatePolicy(id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["policies"] }),
  });

  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.createPolicy(body),
    onSuccess: () => {
      setShowForm(false);
      queryClient.invalidateQueries({ queryKey: ["policies"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deletePolicy(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["policies"] }),
  });

  const lookup = useMutation({
    mutationFn: (value: string) => api.lookupPolicy(value),
    onSuccess: setDecision,
  });

  function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    create.mutate({
      e164: form.get("e164"),
      label: form.get("label") || null,
      kind: form.get("kind") || "agent",
      recording_enabled: form.get("recording_enabled") === "on",
      consent_required: form.get("consent_required") === "on",
      retention_days: form.get("retention_days")
        ? Number(form.get("retention_days"))
        : null,
      notes: form.get("notes") || null,
    });
  }

  return (
    <Shell>
      <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">Recording policy</h1>
          <p className="mt-0.5 text-sm text-ink-muted">
            Recording is off unless a number says otherwise, and a customer opt-out
            always wins.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={filter} onChange={setFilter} options={FILTERS} />
          {canConfigure && (
            <Button variant="primary" onClick={() => setShowForm((open) => !open)}>
              {showForm ? "Cancel" : "Add number"}
            </Button>
          )}
        </div>
      </header>

      <Card
        className="mb-4"
        title="Check a number"
        subtitle="Runs the same decision the handset makes before a call"
      >
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (lookupNumber.trim()) lookup.mutate(lookupNumber.trim());
          }}
        >
          <Input
            value={lookupNumber}
            onChange={(event) => setLookupNumber(event.target.value)}
            placeholder="+91 98765 43210"
            className="w-56"
            aria-label="Number to check"
          />
          <Button type="submit" disabled={lookup.isPending}>
            Check
          </Button>
        </form>

        {decision && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            <Badge
              color={
                decision.should_record ? "var(--status-good)" : "var(--text-muted)"
              }
            >
              {decision.should_record ? "Will record" : "Will not record"}
            </Badge>
            <span className="text-ink-secondary">{policyReason(decision.reason)}</span>
            {decision.consent_required && (
              <span className="text-xs text-ink-muted">consent required</span>
            )}
          </div>
        )}
        {lookup.isError && (
          <div className="mt-3">
            <ErrorNote error={lookup.error} />
          </div>
        )}
      </Card>

      {showForm && (
        <Card className="mb-4" title="Add a number">
          <form onSubmit={onCreate} className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs text-ink-secondary">Number</span>
              <Input name="e164" required placeholder="+91 98765 43210" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-secondary">Label</span>
              <Input name="label" placeholder="Priya — support line" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-secondary">Kind</span>
              <select
                name="kind"
                defaultValue="agent"
                className="w-full rounded-md border border-hairline bg-surface px-3 py-1.5 text-sm text-ink"
              >
                <option value="agent">Agent line</option>
                <option value="customer">Customer number</option>
                <option value="did">Inbound DID</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-secondary">
                Keep recordings for (days)
              </span>
              <Input name="retention_days" type="number" min={0} placeholder="90" />
            </label>
            <label className="flex items-center gap-2 text-sm text-ink-secondary">
              <input type="checkbox" name="recording_enabled" /> Record calls on this
              number
            </label>
            <label className="flex items-center gap-2 text-sm text-ink-secondary">
              <input type="checkbox" name="consent_required" defaultChecked /> Announce
              consent before recording
            </label>
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-xs text-ink-secondary">Notes</span>
              <Input name="notes" placeholder="Why this setting was chosen" />
            </label>
            <div className="sm:col-span-2">
              {create.isError && <ErrorNote error={create.error} />}
              <Button
                type="submit"
                variant="primary"
                className="mt-2"
                disabled={create.isPending}
              >
                {create.isPending ? "Saving…" : "Add number"}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {policies.isLoading && <Spinner label="Loading numbers" />}
      {policies.isError && <ErrorNote error={policies.error} />}
      {policies.data?.items.length === 0 && (
        <EmptyState
          title="No numbers configured"
          hint="Until a number is added here, calls on it are not recorded."
        />
      )}

      {policies.data && policies.data.items.length > 0 && (
        <div className="overflow-x-auto rounded-card border border-hairline bg-surface">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="border-b border-hairline text-xs text-ink-muted">
              <tr>
                <th className="px-4 py-2.5 font-medium">Number</th>
                <th className="px-4 py-2.5 font-medium">Kind</th>
                <th className="px-4 py-2.5 font-medium">Recording</th>
                <th className="px-4 py-2.5 font-medium">Inbound</th>
                <th className="px-4 py-2.5 font-medium">Outbound</th>
                <th className="px-4 py-2.5 font-medium">Consent</th>
                <th className="px-4 py-2.5 text-right font-medium">Retention</th>
                {canConfigure && <th className="px-4 py-2.5" />}
              </tr>
            </thead>
            <tbody>
              {policies.data.items.map((policy: RecordingPolicy) => (
                <tr key={policy.id} className="border-b border-hairline last:border-0">
                  <td className="px-4 py-2.5">
                    <span className="tabular text-ink">{policy.e164}</span>
                    {policy.label && (
                      <p className="text-xs text-ink-muted">{policy.label}</p>
                    )}
                    {policy.notes && (
                      <p className="mt-0.5 text-xs italic text-ink-muted">{policy.notes}</p>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-ink-secondary">
                    {titleCase(policy.kind)}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <Toggle
                        checked={policy.recording_enabled}
                        disabled={!canConfigure || update.isPending}
                        label={`Recording for ${policy.e164}`}
                        onChange={(next) =>
                          update.mutate({
                            id: policy.id,
                            body: { recording_enabled: next },
                          })
                        }
                      />
                      {/* The state is always written out, not just coloured. */}
                      <span className="text-xs text-ink-secondary">
                        {policy.recording_enabled ? "On" : "Off"}
                      </span>
                    </div>
                  </td>
                  <DirectionCell
                    policy={policy}
                    field="record_inbound"
                    canConfigure={canConfigure}
                    onChange={(body) => update.mutate({ id: policy.id, body })}
                  />
                  <DirectionCell
                    policy={policy}
                    field="record_outbound"
                    canConfigure={canConfigure}
                    onChange={(body) => update.mutate({ id: policy.id, body })}
                  />
                  <td className="px-4 py-2.5 text-ink-secondary">
                    {policy.consent_required ? "Required" : "Not required"}
                  </td>
                  <td className="tabular px-4 py-2.5 text-right text-ink-secondary">
                    {policy.retention_days === null
                      ? "Org default"
                      : policy.retention_days === 0
                        ? "Keep"
                        : `${policy.retention_days}d`}
                  </td>
                  {canConfigure && (
                    <td className="px-4 py-2.5 text-right">
                      <Button
                        variant="danger"
                        className="px-2 py-1 text-xs"
                        onClick={() => {
                          if (
                            window.confirm(
                              `Remove the policy for ${policy.e164}? Calls on this number will stop being recorded.`,
                            )
                          ) {
                            remove.mutate(policy.id);
                          }
                        }}
                      >
                        Remove
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {update.isError && (
        <div className="mt-3">
          <ErrorNote error={update.error} />
        </div>
      )}
    </Shell>
  );
}

function DirectionCell({
  policy,
  field,
  canConfigure,
  onChange,
}: {
  policy: RecordingPolicy;
  field: "record_inbound" | "record_outbound";
  canConfigure: boolean;
  onChange: (body: Record<string, unknown>) => void;
}) {
  const enabled = policy[field];
  return (
    <td className="px-4 py-2.5">
      <label className="flex items-center gap-2 text-xs text-ink-secondary">
        <input
          type="checkbox"
          checked={enabled}
          disabled={!canConfigure || !policy.recording_enabled}
          onChange={(event) => onChange({ [field]: event.target.checked })}
          className="h-3.5 w-3.5"
        />
        {enabled ? "Yes" : "No"}
      </label>
    </td>
  );
}
