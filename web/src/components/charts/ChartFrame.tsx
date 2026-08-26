"use client";

import { useState, type ReactNode } from "react";

import { Button } from "../ui";

/**
 * Wraps a chart with the pieces every chart here needs: a title, a legend, and
 * a table view.
 *
 * The table is not decoration. Some series colours sit below 3:1 against the
 * light surface, and the relief rule for that is a readable alternative — so
 * the numbers behind every chart are always one click away, which also serves
 * screen readers and anyone who just wants the figure.
 */
export function ChartFrame({
  title,
  subtitle,
  legend,
  table,
  children,
  height = 260,
}: {
  title: string;
  subtitle?: string;
  legend?: { label: string; color: string }[];
  table?: ReactNode;
  children: ReactNode;
  height?: number;
}) {
  const [showTable, setShowTable] = useState(false);

  return (
    <section className="rounded-card border border-hairline bg-surface p-5">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-3">
          {legend && legend.length > 1 && (
            <ul className="flex flex-wrap items-center gap-3">
              {legend.map((entry) => (
                <li
                  key={entry.label}
                  className="flex items-center gap-1.5 text-xs text-ink-secondary"
                >
                  <span
                    aria-hidden
                    className="h-2 w-2 rounded-full"
                    style={{ background: entry.color }}
                  />
                  {entry.label}
                </li>
              ))}
            </ul>
          )}
          {table && (
            <Button
              variant="ghost"
              className="px-2 py-1 text-xs"
              aria-pressed={showTable}
              onClick={() => setShowTable((current) => !current)}
            >
              {showTable ? "Chart" : "Table"}
            </Button>
          )}
        </div>
      </header>

      {showTable && table ? (
        <div className="max-h-[320px] overflow-auto scrollbar-thin">{table}</div>
      ) : (
        <div style={{ height }}>{children}</div>
      )}
    </section>
  );
}

/** Shared tooltip so every chart reads the same and follows the theme. */
export function ChartTooltip({
  active,
  label,
  rows,
}: {
  active?: boolean;
  label?: ReactNode;
  rows: { name: string; value: ReactNode; color?: string }[];
}) {
  if (!active) return null;
  return (
    <div className="rounded-md border border-hairline bg-surface-raised px-3 py-2 text-xs shadow-sm">
      {label && <p className="mb-1 font-medium text-ink">{label}</p>}
      <ul className="space-y-0.5">
        {rows.map((row) => (
          <li key={row.name} className="flex items-center gap-2 text-ink-secondary">
            {row.color && (
              <span
                aria-hidden
                className="h-2 w-2 rounded-full"
                style={{ background: row.color }}
              />
            )}
            <span>{row.name}</span>
            <span className="tabular ml-auto font-medium text-ink">{row.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
