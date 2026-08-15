"use client";

import { useMemo, useState } from "react";
import type { EChartsOption } from "@/components/chart";
import { ArrowRight, CheckCircle2 } from "lucide-react";

import { Chart } from "@/components/chart";
import { DashboardError, DashboardLoading } from "@/components/dashboard-status";
import { KpiCard } from "@/components/kpi-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import type { ScenarioResultDetail, ScenarioSummary } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn, formatNumber } from "@/lib/utils";

const SCENARIO_TYPE_LABEL: Record<string, string> = {
  demand_surge: "Demand Surge",
  demand_decline: "Demand Decline",
  supplier_disruption: "Supplier Disruption",
  lead_time_inflation: "Lead-Time Inflation",
  warehouse_outage: "Warehouse Outage",
  inventory_policy_change: "Inventory Policy Change",
  service_level_target_change: "Service-Level Target Change",
  combined: "Combined",
};

function deltaTone(delta: number, higherIsBad: boolean): "good" | "critical" | "neutral" {
  if (delta === 0) return "neutral";
  const isBad = higherIsBad ? delta > 0 : delta < 0;
  return isBad ? "critical" : "good";
}

function formatDelta(delta: number, digits = 4): string {
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta.toFixed(digits)}`;
}

function DeltaBadge({ delta, higherIsBad, digits = 4 }: { delta: number; higherIsBad: boolean; digits?: number }) {
  const tone = deltaTone(delta, higherIsBad);
  return (
    <span
      className={cn(
        "rounded px-1.5 py-0.5 text-2xs font-medium tabular-nums",
        tone === "good" && "bg-status-good/15 text-status-good",
        tone === "critical" && "bg-status-critical/15 text-status-critical",
        tone === "neutral" && "bg-surface-2 text-ink-muted",
      )}
    >
      {formatDelta(delta, digits)}
    </span>
  );
}

function ImpactRow({
  label,
  baseline,
  scenario,
  format,
  higherIsBad,
}: {
  label: string;
  baseline: number;
  scenario: number;
  format: (v: number) => string;
  higherIsBad: boolean;
}) {
  const delta = scenario - baseline;
  return (
    <div className="flex items-center justify-between border-t border-hairline py-2 text-sm first:border-t-0">
      <span className="text-ink-muted">{label}</span>
      <div className="flex items-center gap-2 tabular-nums">
        <span className="text-ink-secondary">{format(baseline)}</span>
        <ArrowRight className="h-3 w-3 text-ink-muted" />
        <span className="font-medium text-ink-primary">{format(scenario)}</span>
        <DeltaBadge delta={delta} higherIsBad={higherIsBad} digits={Math.abs(delta) < 1 ? 4 : 0} />
      </div>
    </div>
  );
}

function ComparisonCard({ s }: { s: ScenarioResultDetail }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle className="normal-case tracking-normal text-ink-primary">
            {s.scenario_name}
          </CardTitle>
          <p className="mt-0.5 text-2xs text-ink-muted">
            {SCENARIO_TYPE_LABEL[s.scenario_type] ?? s.scenario_type} · {s.n_pairs_evaluated.toLocaleString()} pairs evaluated
          </p>
        </div>
        <span className="rounded-full bg-accent-subtle px-2.5 py-0.5 text-2xs font-medium text-accent">
          {s.confidence} confidence
        </span>
      </CardHeader>
      <CardContent className="flex flex-col">
        <ImpactRow
          label="Avg. stockout probability"
          baseline={s.baseline_avg_stockout_probability}
          scenario={s.scenario_avg_stockout_probability}
          format={(v) => v.toFixed(4)}
          higherIsBad
        />
        <ImpactRow
          label="High stockout-risk pairs"
          baseline={s.baseline_n_high_stockout_risk}
          scenario={s.scenario_n_high_stockout_risk}
          format={(v) => v.toString()}
          higherIsBad
        />
        <ImpactRow
          label="Avg. backorder probability"
          baseline={s.baseline_avg_backorder_probability}
          scenario={s.scenario_avg_backorder_probability}
          format={(v) => v.toFixed(4)}
          higherIsBad
        />
        <ImpactRow
          label="Inventory investment"
          baseline={s.baseline_inventory_investment}
          scenario={s.scenario_inventory_investment}
          format={(v) => `$${formatNumber(v)}`}
          higherIsBad
        />
        <ImpactRow
          label="Avg. service level"
          baseline={s.baseline_avg_service_level}
          scenario={s.scenario_avg_service_level}
          format={(v) => `${(v * 100).toFixed(1)}%`}
          higherIsBad={false}
        />
        <ImpactRow
          label="Procurement volume"
          baseline={s.baseline_procurement_volume}
          scenario={s.scenario_procurement_volume}
          format={(v) => formatNumber(v)}
          higherIsBad={false}
        />
        <ImpactRow
          label="Suppliers utilized"
          baseline={s.baseline_n_suppliers_utilized}
          scenario={s.scenario_n_suppliers_utilized}
          format={(v) => v.toString()}
          higherIsBad={false}
        />

        <div className="mt-4 rounded-md bg-surface-inset p-3">
          <div className="text-2xs font-medium uppercase tracking-wide text-ink-muted">
            Key drivers
          </div>
          <p className="mt-1 text-xs text-ink-secondary">{s.key_drivers.join("; ")}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {s.affected_modules.map((m) => (
              <span key={m} className="rounded bg-surface-2 px-1.5 py-0.5 text-2xs text-ink-muted">
                {m}
              </span>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ScenarioPlannerPage() {
  const { role } = useRole();
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  const list = useApi(() => api.scenarios.list(role), [role]);
  const compare = useApi(
    () => (selectedIds.length > 0 ? api.scenarios.compare(role, selectedIds) : Promise.resolve([])),
    [role, selectedIds.join(",")],
  );

  const toggleSelected = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 5 ? [...prev, id] : prev,
    );
  };

  const investmentChartOption = useMemo<EChartsOption | null>(() => {
    if (list.status !== "ready" || list.data.length === 0) return null;
    const rows = list.data;
    return {
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 90, right: 30, top: 20, bottom: 90 },
      xAxis: {
        type: "category",
        data: rows.map((r) => r.scenario_name),
        axisLabel: { rotate: 45, fontSize: 10, color: "#898781" },
        axisLine: { lineStyle: { color: "#383835" } },
      },
      yAxis: {
        type: "value",
        name: "Inventory Investment ($)",
        axisLabel: { formatter: (v: number) => `$${(v / 1_000_000).toFixed(1)}M`, color: "#898781" },
        splitLine: { lineStyle: { color: "#2c2c2a" } },
      },
      series: [
        {
          name: "Scenario Inventory Investment",
          type: "bar",
          data: rows.map((r) => r.scenario_inventory_investment),
          itemStyle: { borderRadius: [4, 4, 0, 0], color: "#3987e5" },
        },
      ],
    };
  }, [list]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-headline font-semibold text-ink-primary">Scenario Simulation</h1>
        <p className="mt-1 text-xs text-ink-muted">
          A curated library of precomputed what-if scenarios, each recomputing Modules A/C/D/B&apos;s
          own frozen formulas over perturbed, never-persisted inputs. Select up to 5 for a
          side-by-side impact comparison.
        </p>
      </div>

      {list.status === "loading" && <DashboardLoading />}
      {list.status === "error" && <DashboardError error={list.error} />}
      {list.status === "ready" && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard label="Scenarios Available" value={formatNumber(list.data.length)} />
            <KpiCard
              label="Widest Investment Swing"
              value={`$${formatNumber(
                Math.max(...list.data.map((r) => Math.abs(r.investment_delta))),
              )}`}
            />
            <KpiCard
              label="Max Stockout-Risk Delta"
              value={formatDelta(
                Math.max(...list.data.map((r) => r.stockout_probability_delta)),
                4,
              )}
            />
            <KpiCard
              label="Min Service-Level Delta"
              value={formatDelta(Math.min(...list.data.map((r) => r.service_level_delta)), 4)}
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Inventory Impact by Scenario</CardTitle>
            </CardHeader>
            <CardContent>
              {investmentChartOption && <Chart option={investmentChartOption} height={300} />}
            </CardContent>
          </Card>

          <div>
            <h2 className="mb-3 text-sm font-medium text-ink-secondary">Scenario Library</h2>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {list.data.map((row: ScenarioSummary) => {
                const selected = selectedIds.includes(row.id);
                return (
                  <button
                    key={row.id}
                    onClick={() => toggleSelected(row.id)}
                    className={cn(
                      "flex animate-rise-in flex-col gap-2.5 rounded-lg border p-4 text-left transition-colors",
                      selected
                        ? "border-accent bg-accent-subtle"
                        : "border-hairline bg-surface hover:border-hairline-strong",
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="rounded-full bg-surface-2 px-2 py-0.5 text-2xs font-medium text-ink-secondary">
                        {SCENARIO_TYPE_LABEL[row.scenario_type] ?? row.scenario_type}
                      </span>
                      {selected && <CheckCircle2 className="h-4 w-4 text-accent" />}
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-ink-primary">
                        {row.scenario_name}
                      </div>
                      <div className="mt-0.5 text-xs text-ink-muted">{row.description}</div>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      <DeltaBadge delta={row.stockout_probability_delta} higherIsBad />
                      <DeltaBadge delta={row.service_level_delta} higherIsBad={false} />
                      <span className="rounded bg-surface-2 px-1.5 py-0.5 text-2xs tabular-nums text-ink-muted">
                        {row.investment_delta >= 0 ? "+" : ""}${formatNumber(row.investment_delta)}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}

      {selectedIds.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-medium text-ink-secondary">
            Impact Comparison — Baseline vs. Selected Scenarios
          </h2>
          {compare.status === "loading" && <DashboardLoading />}
          {compare.status === "error" && <DashboardError error={compare.error} />}
          {compare.status === "ready" && (
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {compare.data.map((s) => (
                <ComparisonCard key={s.id} s={s} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
