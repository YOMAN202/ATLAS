"use client";

import { useMemo, useState } from "react";
import type { EChartsOption } from "@/components/chart";

import { Chart } from "@/components/chart";
import { DashboardError, DashboardLoading } from "@/components/dashboard-status";
import { KpiCard } from "@/components/kpi-card";
import { api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import type { ScenarioSummary } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { formatNumber } from "@/lib/utils";

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

function deltaColor(delta: number, higherIsBad: boolean): string {
  if (delta === 0) return "text-slate-500 dark:text-slate-400";
  const isBad = higherIsBad ? delta > 0 : delta < 0;
  return isBad ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400";
}

function formatDelta(delta: number, digits = 4): string {
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta.toFixed(digits)}`;
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
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: {
        type: "value",
        name: "Inventory Investment ($)",
        axisLabel: { formatter: (v: number) => `$${(v / 1_000_000).toFixed(1)}M` },
      },
      series: [
        {
          name: "Scenario Inventory Investment",
          type: "bar",
          data: rows.map((r) => r.scenario_inventory_investment),
          itemStyle: { borderRadius: [4, 4, 0, 0] },
        },
      ],
    };
  }, [list]);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">Planning — Scenario Simulation</h1>
      <p className="text-xs text-slate-400">
        A curated library of precomputed what-if scenarios, each recomputing Modules A/C/D/B&apos;s
        own frozen formulas over perturbed (never persisted) inputs — see
        docs/phase7-2-architecture.md. Select up to 5 scenarios below for a side-by-side What-if
        Comparison.
      </p>

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

          <div>
            <h2 className="mb-2 text-sm font-medium text-slate-500">
              Inventory Impact — projected inventory investment by scenario
            </h2>
            {investmentChartOption && <Chart option={investmentChartOption} height={320} />}
          </div>

          <div>
            <h2 className="mb-2 text-sm font-medium text-slate-500">Scenario Planner</h2>
            <div className="overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 dark:bg-slate-800/50">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium text-slate-500">Compare</th>
                    <th className="px-3 py-2 text-left font-medium text-slate-500">Type</th>
                    <th className="px-3 py-2 text-left font-medium text-slate-500">Scenario</th>
                    <th className="px-3 py-2 text-left font-medium text-slate-500">Stockout Δ</th>
                    <th className="px-3 py-2 text-left font-medium text-slate-500">
                      Service Level Δ
                    </th>
                    <th className="px-3 py-2 text-left font-medium text-slate-500">Investment Δ</th>
                    <th className="px-3 py-2 text-left font-medium text-slate-500">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.map((row: ScenarioSummary) => (
                    <tr key={row.id} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(row.id)}
                          onChange={() => toggleSelected(row.id)}
                        />
                      </td>
                      <td className="px-3 py-2">
                        {SCENARIO_TYPE_LABEL[row.scenario_type] ?? row.scenario_type}
                      </td>
                      <td className="px-3 py-2">
                        <div className="font-medium">{row.scenario_name}</div>
                        <div className="text-xs text-slate-400">{row.description}</div>
                      </td>
                      <td
                        className={`px-3 py-2 tabular-nums ${deltaColor(row.stockout_probability_delta, true)}`}
                      >
                        {formatDelta(row.stockout_probability_delta)}
                      </td>
                      <td
                        className={`px-3 py-2 tabular-nums ${deltaColor(row.service_level_delta, false)}`}
                      >
                        {formatDelta(row.service_level_delta)}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {row.investment_delta >= 0 ? "+" : ""}${formatNumber(row.investment_delta)}
                      </td>
                      <td className="px-3 py-2">{row.confidence}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {selectedIds.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-medium text-slate-500">
            What-if Comparison — Inventory &amp; Supplier Impact
          </h2>
          {compare.status === "loading" && <DashboardLoading />}
          {compare.status === "error" && <DashboardError error={compare.error} />}
          {compare.status === "ready" && (
            <div className="overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 dark:bg-slate-800/50">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium text-slate-500">Metric</th>
                    <th className="px-3 py-2 text-left font-medium text-slate-500">Baseline</th>
                    {compare.data.map((s) => (
                      <th key={s.id} className="px-3 py-2 text-left font-medium text-slate-500">
                        {s.scenario_name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  <tr className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-3 py-2 text-slate-500">Avg. Stockout Probability</td>
                    <td className="px-3 py-2">
                      {compare.data[0]?.baseline_avg_stockout_probability.toFixed(4) ?? "—"}
                    </td>
                    {compare.data.map((s) => (
                      <td key={s.id} className="px-3 py-2">
                        {s.scenario_avg_stockout_probability.toFixed(4)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-3 py-2 text-slate-500">High Stockout-Risk Pairs</td>
                    <td className="px-3 py-2">
                      {compare.data[0]?.baseline_n_high_stockout_risk ?? "—"}
                    </td>
                    {compare.data.map((s) => (
                      <td key={s.id} className="px-3 py-2">
                        {s.scenario_n_high_stockout_risk}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-3 py-2 text-slate-500">Avg. Backorder Probability</td>
                    <td className="px-3 py-2">
                      {compare.data[0]?.baseline_avg_backorder_probability.toFixed(4) ?? "—"}
                    </td>
                    {compare.data.map((s) => (
                      <td key={s.id} className="px-3 py-2">
                        {s.scenario_avg_backorder_probability.toFixed(4)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-3 py-2 text-slate-500">Inventory Investment</td>
                    <td className="px-3 py-2">
                      $
                      {compare.data[0]
                        ? formatNumber(compare.data[0].baseline_inventory_investment)
                        : "—"}
                    </td>
                    {compare.data.map((s) => (
                      <td key={s.id} className="px-3 py-2">
                        ${formatNumber(s.scenario_inventory_investment)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-3 py-2 text-slate-500">Avg. Service Level</td>
                    <td className="px-3 py-2">
                      {compare.data[0]
                        ? `${(compare.data[0].baseline_avg_service_level * 100).toFixed(1)}%`
                        : "—"}
                    </td>
                    {compare.data.map((s) => (
                      <td key={s.id} className="px-3 py-2">
                        {(s.scenario_avg_service_level * 100).toFixed(1)}%
                      </td>
                    ))}
                  </tr>
                  <tr className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-3 py-2 text-slate-500">Procurement Volume</td>
                    <td className="px-3 py-2">
                      {compare.data[0]
                        ? formatNumber(compare.data[0].baseline_procurement_volume)
                        : "—"}
                    </td>
                    {compare.data.map((s) => (
                      <td key={s.id} className="px-3 py-2">
                        {formatNumber(s.scenario_procurement_volume)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-3 py-2 text-slate-500">Suppliers Utilized</td>
                    <td className="px-3 py-2">
                      {compare.data[0]?.baseline_n_suppliers_utilized ?? "—"}
                    </td>
                    {compare.data.map((s) => (
                      <td key={s.id} className="px-3 py-2">
                        {s.scenario_n_suppliers_utilized}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
              <div className="border-t border-slate-100 p-3 text-xs text-slate-400 dark:border-slate-800">
                {compare.data.map((s) => (
                  <div key={s.id} className="mb-1">
                    <span className="font-medium">{s.scenario_name}:</span>{" "}
                    {s.key_drivers.join("; ")} (affects: {s.affected_modules.join(", ")})
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
