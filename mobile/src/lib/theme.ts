/**
 * Shared visual tokens, mirroring the dashboard's palette so the two apps read
 * as one product. Both light and dark are defined; the app follows the system
 * setting.
 */
export const light = {
  page: "#f9f9f7",
  surface: "#fcfcfb",
  surfaceRaised: "#ffffff",
  ink: "#0b0b0b",
  inkSecondary: "#52514e",
  inkMuted: "#898781",
  border: "rgba(11,11,11,0.12)",
  accent: "#2a78d6",
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
  onAccent: "#ffffff",
};

export const dark: typeof light = {
  page: "#0d0d0d",
  surface: "#1a1a19",
  surfaceRaised: "#212120",
  ink: "#ffffff",
  inkSecondary: "#c3c2b7",
  inkMuted: "#898781",
  border: "rgba(255,255,255,0.14)",
  accent: "#3987e5",
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
  onAccent: "#ffffff",
};

export type Theme = typeof light;

export const STATUS_LABEL: Record<string, string> = {
  offline: "Offline",
  available: "Available",
  on_call: "On call",
  wrap_up: "Wrap-up",
  break: "On break",
};

export function statusColor(status: string, theme: Theme): string {
  switch (status) {
    case "on_call":
      return theme.accent;
    case "available":
      return theme.good;
    case "wrap_up":
      return theme.warning;
    case "break":
      return theme.serious;
    default:
      return theme.inkMuted;
  }
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${String(rest).padStart(2, "0")}s`;
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

export function clock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  return `${String(minutes).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

/** Reasons written for the agent holding the phone, not for a developer. */
export const POLICY_REASONS: Record<string, string> = {
  policy_enabled: "Recording is on for your number",
  no_policy_configured: "Your number is not set up for recording",
  recording_disabled_for_number: "Recording is switched off for your number",
  customer_opted_out: "This customer has opted out of recording",
  inbound_calls_not_recorded: "Inbound calls are not recorded",
  outbound_calls_not_recorded: "Outbound calls are not recorded",
};

export function policyReason(reason: string): string {
  return POLICY_REASONS[reason] ?? reason.replace(/_/g, " ");
}
