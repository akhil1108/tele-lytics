"use client";

import { BUCKET_COLOR, CHART, scoreColor, sentimentBucket, severityColor } from "@/lib/charts";
import {
  SENTIMENT_LABELS,
  count,
  decimal,
  percent,
  titleCase,
} from "@/lib/format";
import type { ActionItem, Analysis } from "@/lib/types";

import { Badge, Card, MiniBar } from "./ui";

export function VerdictPanel({ analysis }: { analysis: Analysis }) {
  const satisfied = analysis.customer_satisfied;
  const bucket = sentimentBucket(analysis.sentiment_overall);

  return (
    <Card title="Verdict" subtitle={`${analysis.provider}${analysis.model ? ` · ${analysis.model}` : ""}`}>
      <p className="text-sm leading-relaxed text-ink">{analysis.summary}</p>

      <dl className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <dt className="text-xs text-ink-muted">Sentiment</dt>
          <dd className="mt-1 flex items-center gap-1.5 text-sm font-medium text-ink">
            <span
              aria-hidden
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: BUCKET_COLOR[bucket] }}
            />
            {SENTIMENT_LABELS[analysis.sentiment_overall]}
            <span
              className="tabular text-xs font-normal"
              style={{ color: scoreColor(analysis.sentiment_score) }}
            >
              {decimal(analysis.sentiment_score)}
            </span>
          </dd>
        </div>

        <div>
          <dt className="text-xs text-ink-muted">Customer satisfied</dt>
          <dd className="mt-1 text-sm font-medium text-ink">
            {satisfied === null ? "Unclear" : satisfied ? "Yes" : "No"}
            {analysis.csat_score !== null && (
              <span className="tabular ml-1.5 text-xs font-normal text-ink-muted">
                {analysis.csat_score}/5
              </span>
            )}
          </dd>
          {analysis.csat_confidence !== null && (
            <p className="mt-0.5 text-xs text-ink-muted">
              {percent(analysis.csat_confidence)} confidence
            </p>
          )}
        </div>

        <div>
          <dt className="text-xs text-ink-muted">Resolution</dt>
          <dd className="mt-1 text-sm font-medium text-ink">
            {analysis.resolution_status ? titleCase(analysis.resolution_status) : "—"}
          </dd>
        </div>

        <div>
          <dt className="text-xs text-ink-muted">Agent talk ratio</dt>
          <dd className="mt-1 text-sm font-medium text-ink">
            {percent(analysis.agent_talk_ratio)}
          </dd>
          {analysis.agent_talk_ratio !== null && (
            <div className="mt-1.5">
              <MiniBar
                value={analysis.agent_talk_ratio}
                max={1}
                color={CHART.series1}
                title="Share of speaking time held by the agent"
              />
            </div>
          )}
        </div>

        {analysis.category_name && (
          <div>
            <dt className="text-xs text-ink-muted">Category</dt>
            <dd className="mt-1 text-sm font-medium text-ink">{analysis.category_name}</dd>
            {analysis.category_confidence !== null && (
              <p className="mt-0.5 text-xs text-ink-muted">
                {percent(analysis.category_confidence)} confidence
              </p>
            )}
          </div>
        )}
      </dl>

      {analysis.csat_evidence && (
        <blockquote className="mt-4 border-l-2 border-hairline pl-3 text-sm italic text-ink-secondary">
          “{analysis.csat_evidence}”
        </blockquote>
      )}

      {analysis.topics.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-1.5">
          {analysis.topics.map((topic) => (
            <li key={topic}>
              <Badge>{topic}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function CustomRatingsPanel({ analysis }: { analysis: Analysis }) {
  if (analysis.custom_ratings.length === 0) return null;

  return (
    <Card title="Custom ratings" subtitle="This org's own criteria, scored for this call">
      <ul className="space-y-3">
        {analysis.custom_ratings.map((rating) => (
          <li key={rating.parameter_id}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="text-ink">{rating.parameter_name}</span>
              <span className="tabular shrink-0 text-xs text-ink-muted">
                {decimal(rating.score, 1)} / {rating.scale_max}
              </span>
            </div>
            <div className="mt-1.5">
              <MiniBar
                value={rating.score - rating.scale_min}
                max={rating.scale_max - rating.scale_min}
                color={CHART.series1}
                title={`${rating.score} of ${rating.scale_min}–${rating.scale_max}`}
              />
            </div>
            {rating.rationale && (
              <p className="mt-1.5 text-xs text-ink-muted">{rating.rationale}</p>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function TasksPanel({
  items,
  onToggle,
}: {
  items: ActionItem[];
  onToggle?: (item: ActionItem) => void;
}) {
  const tasks = items.filter((item) => item.kind === "task");
  const actions = items.filter((item) => item.kind === "action");

  return (
    <Card
      title="Tasks and actions"
      subtitle="Commitments made on the call, and steps the model recommends"
    >
      {items.length === 0 ? (
        <p className="text-sm text-ink-muted">
          Nothing was promised on this call and no follow-up was recommended.
        </p>
      ) : (
        <div className="space-y-5">
          {tasks.length > 0 && (
            <Group title="Committed on the call" items={tasks} onToggle={onToggle} />
          )}
          {actions.length > 0 && (
            <Group title="Recommended next steps" items={actions} onToggle={onToggle} />
          )}
        </div>
      )}
    </Card>
  );
}

function Group({
  title,
  items,
  onToggle,
}: {
  title: string;
  items: ActionItem[];
  onToggle?: (item: ActionItem) => void;
}) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-muted">
        {title}
      </h3>
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.id} className="rounded-md border border-hairline px-3 py-2.5">
            <div className="flex items-start gap-2.5">
              {onToggle && (
                <input
                  type="checkbox"
                  className="mt-1 h-3.5 w-3.5 shrink-0"
                  checked={item.status === "done"}
                  onChange={() => onToggle(item)}
                  aria-label={`Mark "${item.title}" ${item.status === "done" ? "open" : "done"}`}
                />
              )}
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
                  <p className="mt-0.5 text-xs text-ink-secondary">{item.description}</p>
                )}
                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                  <Badge color={severityColor(item.priority)}>
                    {titleCase(item.priority)}
                  </Badge>
                  {item.due_hint && (
                    <span className="text-xs text-ink-muted">
                      {/* The phrase as spoken, not a paraphrase. */}
                      due: {item.due_hint}
                    </span>
                  )}
                  {item.owner_role && (
                    <span className="text-xs text-ink-muted">
                      owner: {titleCase(item.owner_role)}
                    </span>
                  )}
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
    </div>
  );
}

export function LanguagePanel({ analysis }: { analysis: Analysis }) {
  const agent = analysis.stopword_stats?.agent;
  const customer = analysis.stopword_stats?.customer;
  const assessment = analysis.filler_stats?.agent?.assessment;

  if (!agent && !customer) return null;

  return (
    <Card
      title="Language and filler words"
      subtitle="Counts are computed exactly in code; the model only judges them"
    >
      <div className="grid gap-5 sm:grid-cols-2">
        {agent && <SpeakerStats who="Agent" stats={agent} />}
        {customer && <SpeakerStats who="Customer" stats={customer} />}
      </div>
      {assessment && (
        <p className="mt-4 border-t border-hairline pt-3 text-sm text-ink-secondary">
          {assessment}
        </p>
      )}
    </Card>
  );
}

function SpeakerStats({
  who,
  stats,
}: {
  who: string;
  stats: NonNullable<Analysis["stopword_stats"][string]>;
}) {
  return (
    <div>
      <h3 className="text-xs font-medium uppercase tracking-wide text-ink-muted">{who}</h3>
      <dl className="mt-2 space-y-1.5 text-sm">
        <Row label="Words spoken" value={count(stats.word_count)} />
        <Row
          label="Filler words"
          value={`${count(stats.filler_count)} (${decimal(stats.filler_rate_per_100_words, 1)} per 100)`}
        />
        <Row label="Hedges" value={count(stats.hedge_count)} />
        <Row label="Content density" value={percent(stats.content_density)} />
      </dl>
      {stats.top_fillers?.length > 0 && (
        <ul className="mt-2.5 flex flex-wrap gap-1.5">
          {stats.top_fillers.slice(0, 6).map((filler) => (
            <li key={filler.term}>
              <Badge>
                {filler.term} <span className="tabular">×{filler.count}</span>
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-ink-secondary">{label}</dt>
      <dd className="tabular font-medium text-ink">{value}</dd>
    </div>
  );
}

export function RiskPanel({ analysis }: { analysis: Analysis }) {
  const { risk_flags: risks, coaching } = analysis;
  const hasCoaching =
    (coaching.strengths?.length ?? 0) +
      (coaching.improvements?.length ?? 0) +
      (coaching.missed_opportunities?.length ?? 0) >
    0;

  if (risks.length === 0 && !hasCoaching) return null;

  return (
    <Card title="Risks and coaching">
      {risks.length > 0 && (
        <ul className="mb-4 space-y-2">
          {risks.map((risk, index) => (
            <li
              key={`${risk.kind}-${index}`}
              className="rounded-md border border-hairline px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <Badge color={severityColor(risk.severity)}>
                  {titleCase(risk.kind)} · {titleCase(risk.severity)}
                </Badge>
              </div>
              <p className="mt-1.5 text-sm text-ink-secondary">{risk.detail}</p>
              {risk.source_quote && (
                <blockquote className="mt-1.5 border-l-2 border-hairline pl-2.5 text-xs italic text-ink-muted">
                  “{risk.source_quote}”
                </blockquote>
              )}
            </li>
          ))}
        </ul>
      )}

      {hasCoaching && (
        <div className="grid gap-4 sm:grid-cols-3">
          <CoachingList title="Went well" items={coaching.strengths} />
          <CoachingList title="To improve" items={coaching.improvements} />
          <CoachingList title="Missed" items={coaching.missed_opportunities} />
        </div>
      )}
    </Card>
  );
}

function CoachingList({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div>
      <h3 className="text-xs font-medium uppercase tracking-wide text-ink-muted">{title}</h3>
      <ul className="mt-1.5 space-y-1 text-sm text-ink-secondary">
        {items.map((item) => (
          <li key={item} className="leading-snug">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
