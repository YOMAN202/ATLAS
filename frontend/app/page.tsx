import Link from "next/link";
import { ArrowRight, Boxes, Database, Gauge, ShieldCheck, Sparkles, Workflow } from "lucide-react";

const METRICS = [
  { value: "365", label: "days simulated", note: "8 warehouses · 5,000 SKUs · 100 suppliers" },
  { value: "1.8M+", label: "warehouse records", note: "3.3M+ rows loaded end to end" },
  { value: "300", label: "tests passing", note: "zero known failures" },
  { value: "7", label: "live dashboards", note: "role-gated, read-only" },
  { value: "6", label: "decision-intelligence modules", note: "closed-form, no ML framework" },
  {
    value: "100%",
    label: "claims verified pre-render",
    note: "copilot answers, deterministically",
  },
];

const PIPELINE = [
  { icon: Workflow, label: "Simulate", note: "365-day synthetic supply chain" },
  { icon: Database, label: "Warehouse", note: "Kimball star schema, SCD2" },
  { icon: Gauge, label: "Predict", note: "Forecast · risk · service level · policy" },
  { icon: Boxes, label: "Decide", note: "Scenario · route & cost optimization" },
  { icon: Sparkles, label: "Ask", note: "Verified analytics copilot" },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-page">
      <header className="mx-auto flex max-w-grid items-center justify-between px-6 py-6 md:px-8">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-xs font-bold text-white">
            A
          </div>
          <span className="text-sm font-semibold tracking-tight">ATLAS</span>
        </div>
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 rounded-md border border-hairline-strong px-3.5 py-1.5 text-sm font-medium text-ink-primary transition-colors hover:border-accent hover:text-accent"
        >
          Enter platform <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </header>

      <section className="mx-auto max-w-grid px-6 pb-20 pt-16 md:px-8 md:pt-24">
        <div className="mx-auto max-w-3xl text-center">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-hairline bg-surface px-3 py-1 text-2xs font-medium uppercase tracking-wide text-ink-muted">
            <ShieldCheck className="h-3.5 w-3.5 text-status-good" />
            Verification-first analytics
          </div>
          <h1 className="text-hero font-semibold tracking-tight text-ink-primary">
            Monitor. Predict. Decide.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-ink-secondary">
            ATLAS is an enterprise supply chain intelligence platform — a full
            simulation-to-decision pipeline with real-time dashboards, six decision-intelligence
            modules, and an AI copilot that never states a number it hasn&apos;t verified.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 rounded-md bg-accent px-5 py-2.5 text-sm font-semibold text-white shadow-glow transition-colors hover:bg-accent-hover"
            >
              Enter the platform <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/copilot"
              className="inline-flex items-center gap-2 rounded-md border border-hairline-strong px-5 py-2.5 text-sm font-semibold text-ink-primary transition-colors hover:border-accent hover:text-accent"
            >
              Ask the copilot
            </Link>
          </div>
        </div>
      </section>

      <section className="border-y border-hairline bg-surface/50">
        <div className="mx-auto grid max-w-grid grid-cols-2 gap-px overflow-hidden rounded-none px-6 py-10 sm:grid-cols-3 md:grid-cols-6 md:px-8">
          {METRICS.map((m) => (
            <div key={m.label} className="flex flex-col items-center gap-1 px-2 text-center">
              <div className="text-display font-semibold tabular-nums text-ink-primary">
                {m.value}
              </div>
              <div className="text-sm text-ink-secondary">{m.label}</div>
              <div className="text-2xs text-ink-muted">{m.note}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-grid px-6 py-20 md:px-8">
        <div className="mb-10 text-center">
          <h2 className="text-headline font-semibold text-ink-primary">
            One pipeline, five stages, zero unverified answers
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-ink-secondary">
            Every number on every dashboard traces back to this chain — including what the copilot
            tells you.
          </p>
        </div>
        <div className="flex flex-col items-stretch gap-3 md:flex-row md:items-center">
          {PIPELINE.map((stage, i) => (
            <div key={stage.label} className="flex flex-1 items-center gap-3">
              <div className="flex flex-1 flex-col items-center gap-2 rounded-lg border border-hairline bg-surface px-4 py-6 text-center">
                <stage.icon className="h-5 w-5 text-accent" strokeWidth={1.75} />
                <div className="text-sm font-semibold text-ink-primary">{stage.label}</div>
                <div className="text-2xs text-ink-muted">{stage.note}</div>
              </div>
              {i < PIPELINE.length - 1 && (
                <ArrowRight className="hidden h-4 w-4 shrink-0 text-ink-muted md:block" />
              )}
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-hairline px-6 py-8 text-center text-2xs text-ink-muted md:px-8">
        ATLAS v2 — engineering unchanged from the validated v1.0 platform. Full technical report in{" "}
        <code className="rounded bg-surface-2 px-1 py-0.5">docs/ATLAS-v1.0-final-report.md</code>.
      </footer>
    </div>
  );
}
