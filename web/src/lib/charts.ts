/**
 * Chart tokens.
 *
 * Series colours are read from the CSS custom properties defined in
 * `globals.css` so charts follow the theme exactly like the rest of the UI, and
 * one palette change lands everywhere.
 *
 * The palettes in use were checked with the data-viz validator:
 *
 *   two-series categorical  (blue, orange)          — passes light and dark
 *   three-series categorical (blue, orange, aqua)   — passes all-pairs; aqua
 *       sits below 3:1 on the light surface, so those charts always ship a
 *       legend, direct labels and a table view (the relief rule)
 *   sentiment poles         (red, blue)             — passes light and dark
 *
 * Sentiment is polarity, not identity, so it uses a diverging pair with a
 * neutral grey midpoint rather than categorical slots — and it is reduced to
 * three buckets in charts, because two distinct steps per arm cannot fit the
 * lightness band the palette holds every series to. The five-level detail
 * stays in tables and tooltips, where labels carry it instead of colour.
 */

import type { Sentiment } from "./types";

export const CHART = {
  series1: "var(--series-1)",
  series2: "var(--series-2)",
  series3: "var(--series-3)",
  grid: "var(--gridline)",
  axis: "var(--baseline)",
  tick: "var(--text-muted)",
  surface: "var(--surface-1)",
  ink: "var(--text-primary)",
  inkSecondary: "var(--text-secondary)",
  negative: "var(--sentiment-negative)",
  neutral: "var(--sentiment-neutral)",
  positive: "var(--sentiment-positive)",
} as const;

export type SentimentBucket = "negative" | "neutral" | "positive";

export function sentimentBucket(label: Sentiment): SentimentBucket {
  if (label === "very_negative" || label === "negative") return "negative";
  if (label === "very_positive" || label === "positive") return "positive";
  return "neutral";
}

export const BUCKET_COLOR: Record<SentimentBucket, string> = {
  negative: CHART.negative,
  neutral: CHART.neutral,
  positive: CHART.positive,
};

export const BUCKET_LABEL: Record<SentimentBucket, string> = {
  negative: "Negative",
  neutral: "Neutral",
  positive: "Positive",
};

/** Colour for a sentiment score in −1…+1, used for score chips and marks. */
export function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return CHART.neutral;
  if (score <= -0.2) return CHART.negative;
  if (score >= 0.2) return CHART.positive;
  return CHART.neutral;
}

/** Status colours are reserved: they never double as a series colour, and they
 *  always ship beside a written label. */
export const STATUS_COLOR = {
  good: "var(--status-good)",
  warning: "var(--status-warning)",
  serious: "var(--status-serious)",
  critical: "var(--status-critical)",
} as const;

export function severityColor(severity: string): string {
  if (severity === "urgent") return STATUS_COLOR.critical;
  if (severity === "high") return STATUS_COLOR.serious;
  if (severity === "medium") return STATUS_COLOR.warning;
  return STATUS_COLOR.good;
}
