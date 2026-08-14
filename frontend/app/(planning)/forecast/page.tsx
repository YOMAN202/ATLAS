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
import type { ExperimentRow, ForecastRow } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { formatNumber } from "@/lib/utils";

const detailColumns: ColumnDef<ForecastRow, unknown>[] = [
  { accessorKey: "forecast_date", header: "Date" },
  { accessorKey: "product_key", header: "Product Key" },
  { accessorKey: "warehouse_key", header: "Warehouse Key" },
  { accessorKey: "category", header: "Category" },
  { accessorKey: "region_key", header: "Region Key" },
  {
    accessorKey: "predicted_quantity",
    header: "Predicted Demand",
    cell: (c) => formatNumber(c.getValue() as number),
  },
  {
    accessorKey: "confidence_interval_low",
    header: "CI Low",
    cell: (c) => formatNumber(c.getValue() as number | null),
  },
  {
    accessorKey: "confidence_interval_high",
    header: "CI High",
    cell: (c) => formatNumber(c.getValue() as number | null),
  },
];

const experimentColumns: ColumnDef<ExperimentRow, unknown>[] = [
  { accessorKey: "model_name", header: "Model" },
  { accessorKey: "series_scope", header: "Series" },
  {
    accessorKey: "metric_value",
    header: "MAPE",
    cell: (c) => {
      const v = c.getValue() as number | null;
      return v === null ? "—" : `${v.toFixed(1)}%`;
    },
  },
  {
    accessorKey: "baseline_metric_value",
    header: "Baseline MAPE",
    cell: (c) => {
      const v = c.getValue() as number | null;
      return v === null ? "—" : `${v.toFixed(1)}%`;
    },
  },
  { accessorKey: "n_observations", header: "Test Days" },
];

const GRAIN_OPTIONS = [
  { value: "region", label: "Region" },
  { value: "category", label: "Category" },
  { value: "sku_warehouse", label: "SKU / Warehouse" },
] as const;

export default function ForecastDashboardPage() {
  const { role } = useRole();
  const [grainType, setGrainType] = useState<"region" | "category" | "sku_warehouse">("region");
  const [page, setPage] = useState(1);
  const [experimentsPage, setExperimentsPage] = useState(1);
  const pageSize = 25;
  const experimentsPageSize = 20;

  const summary = useApi(() => api.planning.summary(role), [role]);
  const detail = useApi(
    () => api.planning.detail(role, { grain_type: grainType, page, page_size: pageSize }),
    [role, grainType, page],
  );
  const chartData = useApi(
    () => api.planning.detail(role, { grain_type: "region", page: 1, page_size: 200 }),
    [role],
  );
  const experiments = useApi(() => api.planning.experiments(role), [role]);

  const chartOption = useMemo<EChartsOption | null>(() => {
    if (chartData.status !== "ready") return null;
    const byRegion = new Map<number, { date: string; value: number }[]>();
    for (const row of chartData.data.data) {
      if (row.region_key === null) continue;
      const series = byRegion.get(row.region_key) ?? [];
      series.push({ date: row.forecast_date, value: row.predicted_quantity });
      byRegion.set(row.region_key, series);
    }
    const regionKeys = [...byRegion.keys()].sort((a, b) => a - b);
    const dates = [...new Set(chartData.data.data.map((r) => r.forecast_date))].sort();

    return {
      tooltip: { trigger: "axis" },
      legend: { data: regionKeys.map((r) => `Region ${r}`) },
      grid: { left: 60, right: 20, top: 40, bottom: 30 },
      xAxis: { type: "category", data: dates },
      yAxis: { type: "value" },
      series: regionKeys.map((r) => {
        const points = new Map((byRegion.get(r) ?? []).map((p) => [p.date, p.value]));
        return {
          name: `Region ${r}`,
          type: "line" as const,
          smooth: true,
          data: dates.map((d) => points.get(d) ?? null),
        };
      }),
    };
  }, [chartData]);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">Planning — Demand Forecast</h1>

      {summary.status === "loading" && <DashboardLoading />}
      {summary.status === "error" && <DashboardError error={summary.error} />}
      {summary.status === "ready" && (
        <>
          <p className="text-xs text-slate-400">
            As of ETL run #{summary.data.etl_run_id} — forecast generated{" "}
            {summary.data.forecast_generated_at ?? "—"}
          </p>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard
              label="Active Model"
              value={summary.data.active_model?.model_name ?? "—"}
              note={
                summary.data.active_model
                  ? `params: ${JSON.stringify(summary.data.active_model.parameters)}`
                  : "No model has been promoted yet."
              }
            />
            <KpiCard
              label="Model MAPE (vs. Baseline)"
              value={
                summary.data.active_model?.weighted_avg_mape !== null &&
                summary.data.active_model?.weighted_avg_mape !== undefined
                  ? `${summary.data.active_model.weighted_avg_mape.toFixed(1)}%`
                  : "—"
              }
              note={
                summary.data.active_model?.baseline_mape != null
                  ? `seasonal-naive baseline: ${summary.data.active_model.baseline_mape.toFixed(1)}%`
                  : undefined
              }
            />
            <KpiCard
              label="Predicted Demand (next 30d, all regions)"
              value={formatNumber(summary.data.total_predicted_demand_next_30d)}
            />
            <KpiCard
              label="Forecast Series"
              value={`${formatNumber(summary.data.n_sku_warehouse_series)} SKU · ${formatNumber(
                summary.data.n_category_series,
              )} category · ${formatNumber(summary.data.n_region_series)} region`}
            />
          </div>

          {chartOption && (
            <div>
              <h2 className="mb-2 text-sm font-medium text-slate-500">
                Region-Level Demand Forecast (next 30 days)
              </h2>
              <Chart option={chartOption} height={320} />
            </div>
          )}
        </>
      )}

      <div>
        <h2 className="mb-2 text-sm font-medium text-slate-500">
          Model Comparison — why the active model was selected
        </h2>
        {experiments.status === "loading" && <DashboardLoading />}
        {experiments.status === "error" && <DashboardError error={experiments.error} />}
        {experiments.status === "ready" && (
          <DataTable
            columns={experimentColumns}
            data={experiments.data.slice(
              (experimentsPage - 1) * experimentsPageSize,
              experimentsPage * experimentsPageSize,
            )}
            page={experimentsPage}
            pageSize={experimentsPageSize}
            total={experiments.data.length}
            onPageChange={setExperimentsPage}
          />
        )}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-500">Forecast Detail</h2>
          <select
            value={grainType}
            onChange={(e) => {
              setGrainType(e.target.value as typeof grainType);
              setPage(1);
            }}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
          >
            {GRAIN_OPTIONS.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
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
