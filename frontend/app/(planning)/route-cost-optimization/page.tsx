"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import type { EChartsOption } from "@/components/chart";

import { Chart } from "@/components/chart";
import { DashboardError, DashboardLoading } from "@/components/dashboard-status";
import { DataTable } from "@/components/data-table";
import { KpiCard } from "@/components/kpi-card";
import { api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import type { OptimizationRecommendationRow } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { formatNumber } from "@/lib/utils";

const TYPE_LABEL: Record<string, string> = {
  right_sizing: "Vehicle Right-Sizing",
  consolidation: "Shipment Consolidation",
};

const detailColumns: ColumnDef<OptimizationRecommendationRow, unknown>[] = [
  {
    accessorKey: "recommendation_type",
    header: "Type",
    cell: (c) => TYPE_LABEL[c.getValue() as string] ?? (c.getValue() as string),
  },
  { accessorKey: "origin_warehouse_key", header: "Warehouse" },
  { accessorKey: "shipment_date", header: "Date" },
  {
    accessorKey: "total_quantity",
    header: "Quantity",
    cell: (c) => formatNumber(c.getValue() as number),
  },
  { accessorKey: "current_vehicle_type_code", header: "Current Vehicle" },
  { accessorKey: "recommended_vehicle_type_code", header: "Recommended Vehicle" },
  {
    accessorKey: "estimated_savings",
    header: "Est. Savings",
    cell: (c) => `$${formatNumber(c.getValue() as number)}`,
  },
  { accessorKey: "confidence", header: "Confidence" },
];

export default function RouteCostOptimizationDashboardPage() {
  const { role } = useRole();
  const [page, setPage] = useState(1);
  const [recommendationType, setRecommendationType] = useState<
    "" | "right_sizing" | "consolidation"
  >("");
  const pageSize = 25;

  const summary = useApi(() => api.routeCostOptimization.summary(role), [role]);
  const warehouseImpact = useApi(() => api.routeCostOptimization.warehouseImpact(role), [role]);
  const detail = useApi(
    () =>
      api.routeCostOptimization.detail(role, {
        recommendation_type: recommendationType || undefined,
        page,
        page_size: pageSize,
      }),
    [role, recommendationType, page],
  );

  const warehouseChartOption = useMemo<EChartsOption | null>(() => {
    if (warehouseImpact.status !== "ready" || warehouseImpact.data.length === 0) return null;
    const rows = warehouseImpact.data;
    return {
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { data: ["Right-Sizing", "Consolidation"], bottom: 0 },
      grid: { left: 90, right: 30, top: 20, bottom: 60 },
      xAxis: { type: "category", data: rows.map((r) => `WH ${r.origin_warehouse_key}`) },
      yAxis: {
        type: "value",
        name: "Estimated Savings ($)",
        axisLabel: { formatter: (v: number) => `$${(v / 1_000_000).toFixed(1)}M` },
      },
      series: [
        {
          name: "Right-Sizing",
          type: "bar",
          stack: "savings",
          data: rows.map(
            (r) =>
              r.total_estimated_savings *
              (r.n_right_sizing_recommendations /
                Math.max(1, r.n_right_sizing_recommendations + r.n_consolidation_recommendations)),
          ),
        },
        {
          name: "Consolidation",
          type: "bar",
          stack: "savings",
          data: rows.map(
            (r) =>
              r.total_estimated_savings *
              (r.n_consolidation_recommendations /
                Math.max(1, r.n_right_sizing_recommendations + r.n_consolidation_recommendations)),
          ),
        },
      ],
    };
  }, [warehouseImpact]);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">Planning — Route &amp; Cost Optimization</h1>
      <p className="text-xs text-slate-400">
        Deterministic vehicle right-sizing and shipment-consolidation heuristics over real carrier
        and shipment data — no external optimization engine. Right-sizing has provable zero
        service-level impact (transit time does not vary by vehicle type in this dataset).
      </p>

      {summary.status === "loading" && <DashboardLoading />}
      {summary.status === "error" && <DashboardError error={summary.error} />}
      {summary.status === "ready" && (
        <>
          <p className="text-xs text-slate-400">
            As of ETL run #{summary.data.etl_run_id} — analysis window{" "}
            {summary.data.analysis_window_start ?? "—"} to {summary.data.analysis_window_end ?? "—"}{" "}
            — generated {summary.data.generated_at ?? "—"}
          </p>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard
              label="Total Estimated Savings"
              value={`$${formatNumber(summary.data.total_estimated_savings)}`}
            />
            <KpiCard
              label="Right-Sizing Opportunities"
              value={formatNumber(summary.data.n_right_sizing_recommendations)}
              note={`$${formatNumber(summary.data.right_sizing_estimated_savings)} savings`}
            />
            <KpiCard
              label="Consolidation Opportunities"
              value={formatNumber(summary.data.n_consolidation_recommendations)}
              note={`$${formatNumber(summary.data.consolidation_estimated_savings)} savings`}
            />
            <KpiCard
              label="Service-Level Impact"
              value="None"
              note="Transit time is invariant to vehicle type"
            />
          </div>
        </>
      )}

      <div>
        <h2 className="mb-2 text-sm font-medium text-slate-500">
          Transportation Impact — estimated savings by warehouse
        </h2>
        {warehouseImpact.status === "loading" && <DashboardLoading />}
        {warehouseImpact.status === "error" && <DashboardError error={warehouseImpact.error} />}
        {warehouseChartOption && <Chart option={warehouseChartOption} height={320} />}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-500">Optimization Recommendations</h2>
          <select
            value={recommendationType}
            onChange={(e) => {
              setRecommendationType(e.target.value as typeof recommendationType);
              setPage(1);
            }}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="">All</option>
            <option value="right_sizing">Vehicle Right-Sizing</option>
            <option value="consolidation">Shipment Consolidation</option>
          </select>
        </div>
        {detail.status === "loading" && <DashboardLoading />}
        {detail.status === "error" && <DashboardError error={detail.error} />}
        {detail.status === "ready" && (
          <DataTable
            columns={detailColumns}
            data={detail.data.data}
            page={detail.data.page}
            pageSize={detail.data.page_size}
            total={detail.data.total}
            onPageChange={setPage}
          />
        )}
      </div>
    </div>
  );
}
