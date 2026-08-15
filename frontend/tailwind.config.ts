import type { Config } from "tailwindcss";

// ATLAS v2 design system tokens. Values reference CSS custom properties
// defined in app/globals.css (:root) so the palette lives in one place —
// this file only names the roles as Tailwind utilities (bg-surface,
// text-primary, border-hairline, ...). See docs/ATLAS-v2-design-system.md
// for the full rationale and the dataviz skill's validated dark
// categorical/status/sequential palette this draws from.
const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        page: "rgb(var(--bg-page) / <alpha-value>)",
        surface: "rgb(var(--bg-surface) / <alpha-value>)",
        "surface-2": "rgb(var(--bg-surface-2) / <alpha-value>)",
        "surface-inset": "rgb(var(--bg-surface-inset) / <alpha-value>)",
        ink: {
          primary: "rgb(var(--text-primary) / <alpha-value>)",
          secondary: "rgb(var(--text-secondary) / <alpha-value>)",
          muted: "rgb(var(--text-muted) / <alpha-value>)",
        },
        hairline: "var(--border-hairline)",
        "hairline-strong": "var(--border-hairline-strong)",
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          hover: "rgb(var(--accent-hover) / <alpha-value>)",
          subtle: "var(--accent-subtle)",
        },
        status: {
          good: "rgb(var(--status-good) / <alpha-value>)",
          warning: "rgb(var(--status-warning) / <alpha-value>)",
          serious: "rgb(var(--status-serious) / <alpha-value>)",
          critical: "rgb(var(--status-critical) / <alpha-value>)",
        },
        series: {
          1: "rgb(var(--series-1) / <alpha-value>)",
          2: "rgb(var(--series-2) / <alpha-value>)",
          3: "rgb(var(--series-3) / <alpha-value>)",
          4: "rgb(var(--series-4) / <alpha-value>)",
          5: "rgb(var(--series-5) / <alpha-value>)",
          6: "rgb(var(--series-6) / <alpha-value>)",
          7: "rgb(var(--series-7) / <alpha-value>)",
          8: "rgb(var(--series-8) / <alpha-value>)",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      fontSize: {
        // Enterprise-command-center scale: a wider spread than the
        // Tailwind default, biased toward large headline/hero figures
        // and a small, calm base body size (data density needs a
        // restrained body size to fit; hierarchy comes from a big jump
        // to headline/hero, not a crowded middle).
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
        hero: ["3.5rem", { lineHeight: "1.05", letterSpacing: "-0.02em" }],
        display: ["2.25rem", { lineHeight: "1.1", letterSpacing: "-0.015em" }],
        headline: ["1.5rem", { lineHeight: "1.2", letterSpacing: "-0.01em" }],
      },
      borderRadius: {
        sm: "6px",
        DEFAULT: "10px",
        lg: "14px",
        xl: "20px",
      },
      boxShadow: {
        // Dark-surface elevation doesn't read from drop-shadow the way
        // it does on light surfaces (see dataviz skill) -- these are
        // used sparingly, only for true overlays (modals, popovers),
        // never for ordinary card elevation (which uses a lighter
        // surface step + hairline border instead).
        overlay: "0 24px 48px -12px rgb(0 0 0 / 0.6), 0 0 0 1px rgb(255 255 255 / 0.06)",
        glow: "0 0 0 1px rgb(var(--accent) / 0.4), 0 0 24px -4px rgb(var(--accent) / 0.35)",
      },
      maxWidth: {
        grid: "1600px",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "rise-in": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.3s ease-out",
        "rise-in": "rise-in 0.35s cubic-bezier(0.16, 1, 0.3, 1)",
        shimmer: "shimmer 1.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
