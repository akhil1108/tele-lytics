"use client";

import clsx from "clsx";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function Card({
  children,
  className,
  title,
  subtitle,
  actions,
}: {
  children: ReactNode;
  className?: string;
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section
      className={clsx(
        "rounded-card border border-hairline bg-surface p-5",
        className,
      )}
    >
      {(title || actions) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
            {subtitle && (
              <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>
            )}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function StatTile({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "good" | "warning" | "critical";
}) {
  const toneClass = {
    default: "text-ink",
    good: "text-[color:var(--success-text)]",
    warning: "text-[color:var(--status-warning)]",
    critical: "text-[color:var(--status-critical)]",
  }[tone];

  return (
    <div className="rounded-card border border-hairline bg-surface px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
        {label}
      </p>
      {/* Hero figures keep proportional figures; only aligned columns go tabular. */}
      <p className={clsx("mt-1.5 text-2xl font-semibold leading-none", toneClass)}>
        {value}
      </p>
      {hint && <p className="mt-1.5 text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}

export function Badge({
  children,
  color,
  className,
  title,
}: {
  children: ReactNode;
  color?: string;
  className?: string;
  /** Hover explanation — used where a short label needs the full reason behind it. */
  title?: string;
}) {
  return (
    <span
      title={title}
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border border-hairline px-2 py-0.5 text-xs font-medium text-ink-secondary",
        className,
      )}
    >
      {color && (
        <span
          aria-hidden
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ background: color }}
        />
      )}
      {children}
    </span>
  );
}

export function Button({
  children,
  variant = "secondary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
}) {
  const styles = {
    primary: "bg-accent text-white hover:opacity-90",
    secondary: "border border-hairline bg-surface text-ink hover:bg-surface-raised",
    ghost: "text-ink-secondary hover:text-ink",
    danger:
      "border border-hairline text-[color:var(--status-critical)] hover:bg-surface-raised",
  }[variant];

  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        styles,
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function Input({
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={clsx(
        "w-full rounded-md border border-hairline bg-surface px-3 py-1.5 text-sm text-ink placeholder:text-ink-muted",
        className,
      )}
      {...props}
    />
  );
}

export function Select({
  value,
  onChange,
  options,
  label,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  label?: string;
  className?: string;
}) {
  return (
    <label className={clsx("flex items-center gap-2 text-xs text-ink-muted", className)}>
      {label && <span className="whitespace-nowrap">{label}</span>}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-md border border-hairline bg-surface px-2 py-1.5 text-sm text-ink"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx(
        "relative h-5 w-9 shrink-0 rounded-full border transition disabled:opacity-40",
        checked ? "border-transparent bg-accent" : "border-hairline bg-surface-raised",
      )}
    >
      <span
        className={clsx(
          "absolute top-0.5 h-3.5 w-3.5 rounded-full bg-white transition-all",
          checked ? "left-[18px]" : "left-0.5",
        )}
        style={!checked ? { background: "var(--text-muted)" } : undefined}
      />
    </button>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-ink-muted" role="status">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-hairline border-t-[color:var(--series-1)]" />
      {label}…
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-card border border-dashed border-hairline px-6 py-10 text-center">
      <p className="text-sm font-medium text-ink">{title}</p>
      {hint && <p className="max-w-md text-xs text-ink-muted">{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Something went wrong";
  return (
    <div
      role="alert"
      className="rounded-card border border-hairline px-4 py-3 text-sm"
      style={{ color: "var(--status-critical)" }}
    >
      {message}
    </div>
  );
}

/** Small labelled bar used inside tables — magnitude without a whole chart. */
export function MiniBar({
  value,
  max,
  color,
  title,
}: {
  value: number;
  max: number;
  color: string;
  title?: string;
}) {
  const width = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
  return (
    <div className="h-1.5 w-full rounded-full bg-[color:var(--gridline)]" title={title}>
      <div
        className="h-full rounded-full"
        style={{ width: `${width}%`, background: color }}
      />
    </div>
  );
}
