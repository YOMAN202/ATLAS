"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import type { EChartsOption } from "echarts";

import { Chart } from "@/components/chart";
import { DashboardError, DashboardLoading } from "@/components/dashboard-status";
import { DataTable } from "@/components/data-table";
import { KpiCard } from "@/components/kpi-card";
import { api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import type { InventoryPolicyRow } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { formatNumber } from "@/lib/utils";

const BALANCING_LABEL: Record<string, string> = {
  reorder_now: "Reorder Now",
  adequate: "Adequate",
  excess_inventory: "Excess Inventory",
};

const BALANCING_COLOR: Record<string, string> = {
  reorder_now: "text-red-600 dark:text-red-400",
  adequate: "text-emerald-600 dark:text-emerald-400",
  excess_inventory: "text-amber-600 dark:text-amber-400",
};

const detailColumns: ColumnDef<InventoryPolicyRow, unknown>[] = [
  { accessorKey: "product_key", header: "Product Key" },
  { accessorKey: "warehouse_key", header: "Warehouse Key" },
  {
    accessorKey: "current_available_quantity",
    header: "Available",
    cell: (c) => formatNumber(c.getValue() as number),
  },
  {
    accessorKey: "reorder_point",
    header: "Reorder Point",
    cell: (c) => formatNumber(c.getValue() as number),
  },
  {
    accessorKey: "safety_stock",
    header: "Safety Stock",
    cell: (c) => formatNumber(c.getValue() as number),
  },
  {
    accessorKey: "balancing_recommendation",
    header: "Recommendation",
    cell: (c) => {
      const v = c.getValue() as string;
      return <span className={BALANCING_COLOR[v]}>{BALANCING_LABEL[v] ?? v}</span>;
    },
  },
  { accessorKey: "primary_supplier_key", header: "Primary Supplier" },
];

export default function InventoryPolicyDashboardPage() {
  const { role } = useRole();
  const [page, setPage] = useState(1);
  const [balancing, setBalancing] = useState<
    "" | "reorder_now" | "adequate" | "excess_inventory"
  >("");
  const pageSize = 25;

  const summary = useApi(() => api.inventoryPolicy.summary(role), [role]);
  const sensitivity = useApi(() => api.inventoryPolicy.sensitivity(role), [role]);
  const detail = useApi(
    () =>
      api.inventoryPolicy.detail(role, {
        balancing_recommendation: balancing || undefined,
        page,
        page_size: pageSize,
      }),
    [role, balancing, page]
  );

  const sensitivityChartOption = useMemo<EChartsOption | null>(() => {
    if (sensitivity.status !== "ready" || sensitivity.data.length === 0) return null;
    const scenarios = [...sensitivity.data].sort(
      (a, b) => a.target_service_level - b.target_service_level
    );
    return {
      tooltip: { trigger: "axis" },
      legend: { data: ["Target Service Level", "Achieved Service Level"], bottom: 0 },
      grid: { left: 60, right: 20, top: 40, bottom: 50 },
      xAxis: {
        type: "category",
        name: "Scenario",
        data: scenarios.map((s) => `${(s.target_service_level * 100).toFixed(0)}%`),
      },
      yAxis: {
        type: "value",
        min: 0.8,
        max: 1.0,
        axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` },
      },
      series: [
        {
          name: "Target Service Level",
          type: "line",
          lineStyle: { width: 2, type: "dashed" },
          data: scenarios.map((s) => s.target_service_level),
        },
        {
          name: "Achieved Service Level",
          type: "line",
          lineStyle: { width: 2 },
          data: scenarios.map((s) => s.achieved_service_level),
        },
      ],
    };
  }, [sensitivity]);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">Planning — Inventory Optimization</h1>

      {summary.status === "loading" && <DashboardLoading />}
      {summary.status === "error" && <DashboardError error={summary.error} />}
      {summary.status === "ready" && (
        <>
          <p className="text-xs text-slate-400">
            As of ETL run #{summary.data.etl_run_id} — recommendations generated{" "}
            {summary.data.generated_at ?? "—"} — forecast model #
            {summary.data.source_forecast_model_id ?? "—"}, supplier model #
            {summary.data.source_supplier_model_id ?? "—"}, service-level model #
            {summary.data.source_service_level_model_id ?? "—"}
          </p>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard
              label="Recommendations"
              value={formatNumber(summary.data.n_recommendations)}
            />
            <KpiCard
              label="Reorder Now"
              value={formatNumber(summary.data.balancing_breakdown.reorder_now)}
              note={`${formatNumber(summary.data.balancing_breakdown.adequate)} adequate, ${formatNumber(summary.data.balancing_breakdown.excess_inventory)} excess`}
            />
            <KpiCard
              label="Avg. Safety Stock"
              value={
                summary.data.avg_safety_stock !== null
                  ? formatNumber(summary.data.avg_safety_stock)
                  : "—"
              }
            />
            <KpiCard
              label="Avg. Reorder Point"
              value={
                summary.data.avg_reorder_point !== null
                  ? formatNumber(summary.data.avg_reorder_point)
                  : "—"
              }
            />
          </div>
        </>
      )}

      <div>
        <h2 className="mb-2 text-sm font-medium text-slate-500">
          Policy Sensitivity Analysis — target vs. achieved service level by scenario
        </h2>
        {sensitivity.status === "loading" && <DashboardLoading />}
        {sensitivity.status === "error" && <DashboardError error={sensitivity.error} />}
        {sensitivity.status === "ready" && sensitivityChartOption && (
          <>
            <Chart option={sensitivityChartOption} height={280} />
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 dark:bg-slate-800/50">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium text-slate-500">Target</th>
                    <th className="px-3 py-2 text-left font-medium text-slate-500">Achieved</th>
                    <th className="px-3 py-2 text-left font-medium text-slate-500">
                      Avg. Safety Stock
                    </th>
                    <th className="px-3 py-2 text-left font-medium text-slate-500">
                      Inventory Investment
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {[...sensitivity.data]
                    .sort((a, b) => a.target_service_level - b.target_service_level)
                    .map((s) => (
                      <tr
                        key={s.target_service_level}
                        className="border-t border-slate-100 dark:border-slate-800"
                      >
                        <td className="px-3 py-2 tabular-nums">
                          {(s.target_service_level * 100).toFixed(0)}%
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {(s.achieved_service_level * 100).toFixed(1)}%
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {formatNumber(s.avg_safety_stock)}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          ${formatNumber(s.total_inventory_investment)}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-500">Inventory Policy Detail</h2>
          <select
            value={balancing}
            onChange={(e) => {
              setBalancing(e.target.value as typeof balancing);
              setPage(1);
            }}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="">All</option>
            <option value="reorder_now">Reorder Now</option>
            <option value="adequate">Adequate</option>
            <option value="excess_inventory">Excess Inventory</option>
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
