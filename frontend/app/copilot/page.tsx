"use client";

import { useEffect, useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import type { CopilotAnswer, CopilotStatus } from "@/lib/types";
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

function CitationList({ answer }: { answer: CopilotAnswer }) {
  if (answer.sources.length === 0) return null;
  return (
    <div className="mt-3 flex flex-col gap-1.5 border-t border-slate-100 pt-2 dark:border-slate-800">
      <span className="text-xs font-medium text-slate-400">Sources</span>
      {answer.sources.map((c) => (
        <div key={c.citation_id} className="text-xs text-slate-500 dark:text-slate-400">
          <span className="font-mono text-slate-400">[{c.citation_id}]</span>{" "}
          <span className="font-mono">{c.endpoint}</span>
          {" — "}
          {c.source_tables.join(", ")}
          {c.model_name && <> · model {c.model_name}</>}
          {c.etl_run_id != null && <> · ETL run #{c.etl_run_id}</>}
          {c.generated_at && <> · generated {c.generated_at}</>}
        </div>
      ))}
    </div>
  );
}

function AnswerBubble({ turn }: { turn: ChatTurn }) {
  if (turn.status === "loading") {
    return <div className="text-sm text-slate-400">Thinking…</div>;
  }

  if (turn.status === "error") {
    return (
      <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
        {turn.errorMessage}
      </div>
    );
  }

  const answer = turn.answer!;

  if (answer.status === "refused") {
    return (
      <div className="rounded-md border border-amber-300 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-amber-200 px-2 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-800 dark:text-amber-100">
            Refused
          </span>
          <span className="text-xs font-medium text-amber-800 dark:text-amber-200">
            {REASON_CODE_LABELS[answer.reason_code ?? ""] ?? answer.reason_code}
          </span>
        </div>
        <p className="mt-2 text-sm text-amber-900 dark:text-amber-100">{answer.explanation}</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center gap-2">
        <span className="flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
          ✓ Verified
        </span>
        <span className="text-xs text-slate-400">
          {answer.claim_count} claim{answer.claim_count === 1 ? "" : "s"} · {answer.provider}
        </span>
      </div>
      <p className="mt-2 text-sm text-slate-800 dark:text-slate-100">
        {answer.answer || "No verifiable claims could be produced for this question."}
      </p>
      <CitationList answer={answer} />
    </div>
  );
}

function ProviderStatusBadge({ status }: { status: CopilotStatus | "loading" | "error" }) {
  if (status === "loading") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
        <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
        Checking…
      </span>
    );
  }
  if (status === "error" || !status.configured) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-red-100 px-2.5 py-1 text-xs font-medium text-red-800 dark:bg-red-950 dark:text-red-300">
        <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
        {status === "error" ? "Status unavailable" : "Not configured"}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
      {status.provider} ready ({status.model})
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

  const busy = turns.some((t) => t.status === "loading");

  // Passive "is Gemini up" indicator -- checked on load and re-checked
  // periodically, so a viewer can tell the copilot is configured
  // before asking a question and hitting a 503, not just after.
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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const question = input.trim();
    if (!question || busy) return;

    const id = nextId;
    setNextId(id + 1);
    setInput("");
    setTurns((prev) => [...prev, { id, question, status: "loading" }]);

    try {
      const answer = await api.copilot.ask(role, question);
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, status: "done", answer } : t)));
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.status === 403
            ? "Your current role doesn't have access to the copilot. Switch roles above."
            : err.status === 503
              ? "The copilot isn't configured yet (no LLM provider credential set on the backend)."
              : err.detail
          : err instanceof Error
            ? err.message
            : "Unknown error.";
      setTurns((prev) =>
        prev.map((t) => (t.id === id ? { ...t, status: "error", errorMessage: message } : t)),
      );
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Analytics Copilot</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Ask about KPIs, forecasts, supplier risk, inventory recommendations, service level, or
            scenario comparisons. Every answer is retrieved from the same read-only dashboard API
            and independently verified before it&apos;s shown — no unverified number is ever
            rendered.
          </p>
        </div>
        <ProviderStatusBadge status={providerStatus} />
      </div>

      <Card>
        <CardContent className="flex flex-col gap-4 pt-4">
          {turns.length === 0 && (
            <p className="text-sm text-slate-400">
              Try: &quot;What is the average supplier risk score?&quot; or &quot;What&apos;s our
              current fulfillment rate?&quot;
            </p>
          )}

          <div className="flex flex-col gap-4">
            {turns.map((turn) => (
              <div key={turn.id} className="flex flex-col gap-2">
                <div className="self-end rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-800 dark:bg-slate-800 dark:text-slate-100">
                  {turn.question}
                </div>
                <AnswerBubble turn={turn} />
              </div>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask a question about ATLAS's data…"
              disabled={busy}
              className="flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className={cn(
                "rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900",
              )}
            >
              {busy ? "Asking…" : "Ask"}
            </button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
