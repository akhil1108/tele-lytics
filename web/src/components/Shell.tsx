"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/lib/auth";
import { useRealtime } from "@/lib/realtime";
import { Spinner } from "./ui";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/calls", label: "Calls" },
  { href: "/agents", label: "Agents" },
  { href: "/numbers", label: "Recording" },
  { href: "/tasks", label: "Tasks" },
  { href: "/leads", label: "Leads" },
  { href: "/settings", label: "Settings" },
];

export function Shell({ children }: { children: ReactNode }) {
  const { user, organization, loading, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const { presence, connected } = useRealtime();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Signing you in" />
      </div>
    );
  }
  if (!user) return null;

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-hairline bg-surface px-3 py-5 md:flex">
        <div className="px-2">
          <p className="text-sm font-semibold text-ink">Call Analytics</p>
          <p className="mt-0.5 truncate text-xs text-ink-muted">{organization}</p>
        </div>

        <nav className="mt-6 flex-1 space-y-0.5" aria-label="Main">
          {NAV.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={clsx(
                  "block rounded-md px-2 py-1.5 text-sm transition",
                  active
                    ? "bg-surface-raised font-medium text-ink"
                    : "text-ink-secondary hover:text-ink",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Live agent counts: the figure a floor supervisor watches all day. */}
        <div className="rounded-card border border-hairline px-3 py-2.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-ink-muted">Live now</span>
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{
                background: connected
                  ? "var(--status-good)"
                  : "var(--text-muted)",
              }}
              title={connected ? "Realtime connected" : "Realtime reconnecting"}
              aria-label={connected ? "Realtime connected" : "Realtime reconnecting"}
            />
          </div>
          <dl className="mt-2 space-y-1 text-xs">
            <div className="flex justify-between">
              <dt className="text-ink-secondary">On call</dt>
              <dd className="tabular font-semibold text-ink">{presence?.on_call ?? "—"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-ink-secondary">Available</dt>
              <dd className="tabular text-ink">{presence?.available ?? "—"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-ink-secondary">Offline</dt>
              <dd className="tabular text-ink">{presence?.offline ?? "—"}</dd>
            </div>
          </dl>
        </div>

        <div className="mt-4 border-t border-hairline pt-3">
          <p className="truncate px-2 text-xs font-medium text-ink">{user.full_name}</p>
          <p className="truncate px-2 text-xs capitalize text-ink-muted">{user.role}</p>
          <button
            onClick={signOut}
            className="mt-2 w-full rounded-md px-2 py-1.5 text-left text-xs text-ink-secondary hover:text-ink"
          >
            Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 overflow-x-auto border-b border-hairline bg-surface px-4 py-2 md:hidden">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="whitespace-nowrap text-sm text-ink-secondary"
            >
              {item.label}
            </Link>
          ))}
          <button
            onClick={signOut}
            className="ml-auto shrink-0 whitespace-nowrap text-sm text-ink-muted"
          >
            Sign out
          </button>
        </header>

        <main className="min-w-0 flex-1 px-4 py-6 md:px-8">{children}</main>
      </div>
    </div>
  );
}
