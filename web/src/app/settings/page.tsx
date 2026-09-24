"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { Shell } from "@/components/Shell";
import { Button, Card, EmptyState, ErrorNote, Input, Spinner, Toggle } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { CallCategory, RatingParameter } from "@/lib/types";

/**
 * The org's stage-2 taxonomy: what every call is scored and classified
 * against. Read by the pipeline on each analysis run — see
 * `app/services/pipeline.py` on the backend — so a change here only affects
 * calls analysed after it, not history already on the books.
 */
export default function SettingsPage() {
  const { canConfigure } = useAuth();

  return (
    <Shell>
      <header className="mb-5">
        <h1 className="text-xl font-semibold text-ink">Settings</h1>
        <p className="mt-0.5 text-sm text-ink-muted">
          Custom rating criteria and call categories the insight model scores every
          call against.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <RatingParametersCard canConfigure={canConfigure} />
        <CallCategoriesCard canConfigure={canConfigure} />
      </div>
    </Shell>
  );
}

function RatingParametersCard({ canConfigure }: { canConfigure: boolean }) {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const parameters = useQuery({
    queryKey: ["rating-parameters", true],
    queryFn: () => api.ratingParameters(true),
  });

  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.createRatingParameter(body),
    onSuccess: () => {
      setShowForm(false);
      queryClient.invalidateQueries({ queryKey: ["rating-parameters"] });
    },
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.updateRatingParameter(id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rating-parameters"] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteRatingParameter(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rating-parameters"] }),
  });

  function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    create.mutate({
      name: form.get("name"),
      description: form.get("description") || null,
      scale_min: Number(form.get("scale_min") || 1),
      scale_max: Number(form.get("scale_max") || 5),
    });
  }

  return (
    <Card
      title="Rating parameters"
      subtitle="Scored on every call, e.g. Politeness or Product Knowledge"
      actions={
        canConfigure && (
          <Button variant="primary" onClick={() => setShowForm((open) => !open)}>
            {showForm ? "Cancel" : "Add"}
          </Button>
        )
      }
    >
      {showForm && (
        <form onSubmit={onCreate} className="mb-4 grid gap-2 rounded-card border border-hairline p-3">
          <Input name="name" required placeholder="Name, e.g. Empathy" />
          <Input name="description" placeholder="What this measures" />
          <div className="flex items-center gap-2">
            <Input name="scale_min" type="number" defaultValue={1} className="w-20" aria-label="Scale minimum" />
            <span className="text-xs text-ink-muted">to</span>
            <Input name="scale_max" type="number" defaultValue={5} className="w-20" aria-label="Scale maximum" />
          </div>
          {create.isError && <ErrorNote error={create.error} />}
          <Button type="submit" variant="primary" disabled={create.isPending}>
            {create.isPending ? "Saving…" : "Add parameter"}
          </Button>
        </form>
      )}

      {parameters.isLoading && <Spinner label="Loading parameters" />}
      {parameters.isError && <ErrorNote error={parameters.error} />}
      {parameters.data?.length === 0 && (
        <EmptyState
          title="No rating parameters yet"
          hint="Add one and every call analysed after that will be scored against it."
        />
      )}

      {parameters.data && parameters.data.length > 0 && (
        <ul className="divide-y divide-hairline">
          {parameters.data.map((parameter: RatingParameter) => (
            <li key={parameter.id} className="flex items-start justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <p className="text-sm text-ink">
                  {parameter.name}
                  <span className="ml-1.5 text-xs text-ink-muted">
                    {parameter.scale_min}–{parameter.scale_max}
                  </span>
                </p>
                {parameter.description && (
                  <p className="mt-0.5 text-xs text-ink-muted">{parameter.description}</p>
                )}
              </div>
              {canConfigure && (
                <div className="flex shrink-0 items-center gap-2">
                  <Toggle
                    checked={parameter.is_active}
                    label={`Active — ${parameter.name}`}
                    disabled={update.isPending}
                    onChange={(next) =>
                      update.mutate({ id: parameter.id, body: { is_active: next } })
                    }
                  />
                  <Button
                    variant="danger"
                    className="px-2 py-1 text-xs"
                    onClick={() => {
                      if (window.confirm(`Remove '${parameter.name}'? Past scores are kept.`)) {
                        remove.mutate(parameter.id);
                      }
                    }}
                  >
                    Remove
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function CallCategoriesCard({ canConfigure }: { canConfigure: boolean }) {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const categories = useQuery({
    queryKey: ["call-categories", true],
    queryFn: () => api.callCategories(true),
  });

  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.createCallCategory(body),
    onSuccess: () => {
      setShowForm(false);
      queryClient.invalidateQueries({ queryKey: ["call-categories"] });
    },
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.updateCallCategory(id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["call-categories"] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteCallCategory(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["call-categories"] }),
  });

  function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    create.mutate({ name: form.get("name"), description: form.get("description") || null });
  }

  return (
    <Card
      title="Call categories"
      subtitle="What every call is classified as, e.g. Sales Enquiry or Vendor Call"
      actions={
        canConfigure && (
          <Button variant="primary" onClick={() => setShowForm((open) => !open)}>
            {showForm ? "Cancel" : "Add"}
          </Button>
        )
      }
    >
      {showForm && (
        <form onSubmit={onCreate} className="mb-4 grid gap-2 rounded-card border border-hairline p-3">
          <Input name="name" required placeholder="Name, e.g. Billing Enquiry" />
          <Input name="description" placeholder="What kind of call this covers" />
          {create.isError && <ErrorNote error={create.error} />}
          <Button type="submit" variant="primary" disabled={create.isPending}>
            {create.isPending ? "Saving…" : "Add category"}
          </Button>
        </form>
      )}

      {categories.isLoading && <Spinner label="Loading categories" />}
      {categories.isError && <ErrorNote error={categories.error} />}

      {categories.data && categories.data.length > 0 && (
        <ul className="divide-y divide-hairline">
          {categories.data.map((category: CallCategory) => (
            <li key={category.id} className="flex items-start justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <p className="text-sm text-ink">
                  {category.name}
                  {category.is_default && (
                    <span className="ml-1.5 text-xs text-ink-muted">default fallback</span>
                  )}
                </p>
                {category.description && (
                  <p className="mt-0.5 text-xs text-ink-muted">{category.description}</p>
                )}
              </div>
              {canConfigure && (
                <div className="flex shrink-0 items-center gap-2">
                  <Toggle
                    checked={category.is_active}
                    label={`Active — ${category.name}`}
                    disabled={update.isPending || category.is_default}
                    onChange={(next) =>
                      update.mutate({ id: category.id, body: { is_active: next } })
                    }
                  />
                  <Button
                    variant="danger"
                    className="px-2 py-1 text-xs"
                    disabled={category.is_default}
                    title={
                      category.is_default
                        ? "The default fallback category cannot be removed"
                        : undefined
                    }
                    onClick={() => {
                      if (window.confirm(`Remove '${category.name}'? Past calls keep it.`)) {
                        remove.mutate(category.id);
                      }
                    }}
                  >
                    Remove
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
