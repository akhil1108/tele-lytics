import type { Config } from "tailwindcss";

/**
 * Colours are declared as CSS custom properties in `globals.css` and referenced
 * here by role, so light and dark swap in exactly one place and components are
 * written against roles rather than raw hex.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        page: "var(--page)",
        surface: "var(--surface-1)",
        "surface-raised": "var(--surface-2)",
        ink: "var(--text-primary)",
        "ink-secondary": "var(--text-secondary)",
        "ink-muted": "var(--text-muted)",
        hairline: "var(--border)",
        grid: "var(--gridline)",
        baseline: "var(--baseline)",
        accent: "var(--series-1)",
        good: "var(--status-good)",
        warning: "var(--status-warning)",
        serious: "var(--status-serious)",
        critical: "var(--status-critical)",
        "series-1": "var(--series-1)",
        "series-2": "var(--series-2)",
        "series-3": "var(--series-3)",
        "sentiment-negative": "var(--sentiment-negative)",
        "sentiment-neutral": "var(--sentiment-neutral)",
        "sentiment-positive": "var(--sentiment-positive)",
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      borderRadius: { card: "10px" },
    },
  },
  plugins: [],
};

export default config;
