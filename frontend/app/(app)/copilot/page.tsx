"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Database, FileSearch, ShieldCheck, ShieldX, Sparkles } from "lucide-react";

import { ApiError, api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import type { CopilotAnswer, CopilotCitation, CopilotStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ChatTurn {
  id: number;
  question: string;
  status: "loading" | "done" | "error";
  answer?: CopilotAnswer;
  errorMessage?: string;
}

// Kept in sync with backend/app/copilot/refusal.py's ReasonCode literal.
const REASON_CODE_LABELS: Record<string, string> = {
  no_matching_tool: "No matching capability",
  entity_not_found: "Entity not found",
  out_of_scope: "Out of scope",
  insufficient_verified_evidence: "Insufficient verified evidence",
  data_unavailable: "Data unavailable",
};

const EXAMPLE_PROMPTS = [
  "What is the average supplier risk score?",
  "What's our current fulfillment rate?",
  "Compare scenario 1 and scenario 2 — what's the difference in inventory investment?",
  "What is the service level for a high-risk product?",
];

function EvidenceCard({ citation }: { citation: CopilotCitation }) {
  const lineage = [
    citation.source_forecast_model_id && `forecast v${citation.source_forecast_model_id}`,
    citation.source_supplier_model_id && `supplier v${citation.source_supplier_model_id}`,
    citation.source_service_level_model_id &&
      `service-level v${citation.source_service_level_model_id}`,
    citation.source_inventory_policy_model_id &&
      `inventory v${citation.source_inventory_policy_model_id}`,
  ].filter(Boolean);

  return (
    <div className="rounded-md border border-hairline bg-surface-inset p-3">
      <div className="flex items-center gap-1.5 font-mono text-2xs text-accent">
        <Database className="h-3 w-3" />[{citation.citation_id}] {citation.endpoint}
      </div>
      <div className="mt-1.5 text-2xs text-ink-secondary">{citation.source_tables.join(", ")}</div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {citation.model_name && (
          <span className="rounded bg-surface-2 px-1.5 py-0.5 text-2xs text-ink-secondary">
            {citation.model_name}
          </span>
        )}
        {citation.etl_run_id != null && (
          <span className="rounded bg-surface-2 px-1.5 py-0.5 text-2xs text-ink-secondary">
            ETL run #{citation.etl_run_id}
          </span>
        )}
        {lineage.map((l) => (
          <span key={l} className="rounded bg-accent-subtle px-1.5 py-0.5 text-2xs text-accent">
            {l}
          </span>
        ))}
      </div>
      {citation.generated_at && (
        <div className="mt-1.5 text-2xs text-ink-muted">generated {citation.generated_at}</div>
      )}
    </div>
  );
}

function AnswerCard({ turn }: { turn: ChatTurn }) {
  if (turn.status === "loading") {
    return (
      <div className="flex items-center gap-2.5 rounded-lg border border-hairline bg-surface p-4 text-sm text-ink-muted">
        <span className="flex h-5 w-5 items-center justify-center">
          <span className="h-2 w-2 animate-ping rounded-full bg-accent" />
        </span>
        Retrieving, drafting, and verifying claims…
      </div>
    );
  }

  if (turn.status === "error") {
    return (
      <div className="rounded-lg border border-status-critical/25 bg-status-critical/10 p-4 text-sm text-status-critical">
        {turn.errorMessage}
      </div>
    );
  }

  const answer = turn.answer!;

  if (answer.status === "refused") {
    return (
      <div className="rounded-lg border border-status-warning/25 bg-surface p-4">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-status-warning/15 px-2.5 py-1 text-2xs font-semibold text-status-warning">
            <ShieldX className="h-3.5 w-3.5" />
            Refused — not verifiable
          </span>
          <span className="text-2xs text-ink-muted">
            {REASON_CODE_LABELS[answer.reason_code ?? ""] ?? answer.reason_code}
          </span>
        </div>
        <p className="mt-2.5 text-sm text-ink-secondary">{answer.explanation}</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-status-good/20 bg-surface p-4 shadow-[0_0_0_1px_rgba(12,163,12,0.06)]">
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-status-good/15 px-2.5 py-1 text-2xs font-semibold text-status-good">
          <ShieldCheck className="h-3.5 w-3.5" />
          Verified
        </span>
        <span className="text-2xs text-ink-muted">
          {answer.claim_count} claim{answer.claim_count === 1 ? "" : "s"} · {answer.provider}
        </span>
      </div>
      <p className="mt-3 text-base text-ink-primary">
        {answer.answer || "No verifiable claims could be produced for this question."}
      </p>
      {answer.sources.length > 0 && (
        <div className="mt-4 border-t border-hairline pt-3">
          <div className="mb-2 flex items-center gap-1.5 text-2xs font-medium uppercase tracking-wide text-ink-muted">
            <FileSearch className="h-3 w-3" /> Evidence
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {answer.sources.map((c) => (
              <EvidenceCard key={c.citation_id} citation={c} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ProviderStatusBadge({
  status,
  degradedUntil,
}: {
  status: CopilotStatus | "loading" | "error";
  /** Epoch ms until which the badge shows "rate limited" regardless of the
   * passive /status check -- set from a live 502 on the last ask(), since
   * "a key is configured" and "the last real call actually succeeded" are
   * different facts, and the badge should reflect the second one when it's
   * fresher. Cleared automatically once this time passes. */
  degradedUntil: number | null;
}) {
  if (degradedUntil && degradedUntil > Date.now()) {
    const retrySeconds = Math.max(0, Math.ceil((degradedUntil - Date.now()) / 1000));
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-status-critical/25 bg-status-critical/10 px-2.5 py-1 text-2xs font-medium text-status-critical">
        <span className="h-1.5 w-1.5 rounded-full bg-status-critical" />
        Rate limited · retry in {retrySeconds}s
      </span>
    );
  }
  if (status === "loading") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-1 text-2xs font-medium text-ink-muted">
        <span className="h-1.5 w-1.5 rounded-full bg-ink-muted" />
        Checking…
      </span>
    );
  }
  if (status === "error" || !status.configured) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-status-critical/25 bg-status-critical/10 px-2.5 py-1 text-2xs font-medium text-status-critical">
        <span className="h-1.5 w-1.5 rounded-full bg-status-critical" />
        {status === "error" ? "Status unavailable" : "Not configured"}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-status-good/25 bg-status-good/10 px-2.5 py-1 text-2xs font-medium text-status-good">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-status-good" />
      {status.provider} ready · {status.model}
    </span>
  );
}

export default function CopilotPage() {
  const { role } = useRole();
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [nextId, setNextId] = useState(1);
  const [providerStatus, setProviderStatus] = useState<CopilotStatus | "loading" | "error">(
    "loading",
  );
  const [degradedUntil, setDegradedUntil] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const busy = turns.some((t) => t.status === "loading");

  // Passive "is Gemini up" indicator -- checked on load and re-checked
  // periodically, so a viewer can tell the copilot is configured before
  // asking a question and hitting a 503, not just after.
  useEffect(() => {
    let cancelled = false;
    async function checkStatus() {
      try {
        const status = await api.copilot.status(role);
        if (!cancelled) setProviderStatus(status);
      } catch {
        if (!cancelled) setProviderStatus("error");
      }
    }
    checkStatus();
    const interval = setInterval(checkStatus, 30_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [role]);

  // Ticks a re-render every second so the "retry in Ns" badge counts down
  // instead of freezing at the value from when the error first landed.
  const [, forceTick] = useState(0);
  useEffect(() => {
    if (!degradedUntil) return;
    const id = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [degradedUntil]);

  async function ask(question: string) {
    if (!question || busy) return;
    const id = nextId;
    setNextId(id + 1);
    setInput("");
    setTurns((prev) => [{ id, question, status: "loading" }, ...prev]);

    try {
      const answer = await api.copilot.ask(role, question);
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, status: "done", answer } : t)));
      setDegradedUntil(null);
    } catch (err) {
      let message: string;
      if (err instanceof ApiError) {
        if (err.status === 403) {
          message = "Your current role doesn't have access to the copilot. Switch roles above.";
        } else if (err.status === 503) {
          message =
            "The copilot isn't configured yet (no LLM provider credential set on the backend).";
        } else if (err.status === 502) {
          // The backend passes through the real Gemini error text (see
          // app/api/v1/copilot.py's APIError handler) -- a provider-side
          // rate limit is the common case on a free-tier key, so it gets
          // its own friendly message instead of the raw error dump.
          const retryMatch = err.detail.match(/retry in ([\d.]+)s/i);
          const retrySeconds = retryMatch ? Math.ceil(parseFloat(retryMatch[1])) : null;
          const isRateLimit = /quota|rate.?limit|429/i.test(err.detail);
          if (isRateLimit) {
            setDegradedUntil(Date.now() + (retrySeconds ?? 30) * 1000);
            message = retrySeconds
              ? `Gemini's free-tier rate limit was hit — try again in about ${retrySeconds}s.`
              : "Gemini's free-tier rate limit was hit — try again in a moment.";
          } else {
            setDegradedUntil(Date.now() + 15_000);
            message = "Gemini is temporarily unavailable. Try again shortly.";
          }
        } else {
          message = err.detail;
        }
      } else {
        message = err instanceof Error ? err.message : "Unknown error.";
      }
      setTurns((prev) =>
        prev.map((t) => (t.id === id ? { ...t, status: "error", errorMessage: message } : t)),
      );
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <Sparkles className="h-5 w-5 text-accent" strokeWidth={1.75} />
          <div>
            <h1 className="text-headline font-semibold text-ink-primary">
              Verified Analytics Workspace
            </h1>
            <p className="mt-0.5 text-xs text-ink-muted">
              Every answer is retrieved, then independently verified before render — no unverified
              number ever ships.
            </p>
          </div>
        </div>
        <ProviderStatusBadge status={providerStatus} degradedUntil={degradedUntil} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(input.trim());
        }}
        className="rounded-lg border border-hairline-strong bg-surface p-2 focus-within:ring-2 focus-within:ring-accent"
      >
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask ATLAS anything about its verified data…"
            disabled={busy}
            className="flex-1 bg-transparent px-3 py-3 text-base text-ink-primary placeholder:text-ink-muted focus:outline-none disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-md bg-accent text-white transition-colors hover:bg-accent-hover disabled:opacity-30",
            )}
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        </div>
      </form>

      {turns.length === 0 && (
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_PROMPTS.map((p) => (
            <button
              key={p}
              onClick={() => ask(p)}
              className="rounded-full border border-hairline px-3 py-1.5 text-xs text-ink-secondary transition-colors hover:border-accent hover:text-accent"
            >
              {p}
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-4">
        {turns.map((turn) => (
          <div key={turn.id} className="flex flex-col gap-2">
            <div className="text-sm font-medium text-ink-secondary">{turn.question}</div>
            <AnswerCard turn={turn} />
          </div>
        ))}
      </div>
    </div>
  );
}
