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
import type { ServiceLevelRow } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { formatNumber } from "@/lib/utils";

const PREDICTION_TYPE_LABELS: Record<string, string> = {
  stockout: "Stockout",
  backorder: "Backorder",
  fulfillment_delay: "Fulfillment Delay",
};

function formatPct(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(1)}%`;
}

const detailColumns: ColumnDef<ServiceLevelRow, unknown>[] = [
  { accessorKey: "product_key", header: "Product Key" },
  { accessorKey: "warehouse_key", header: "Warehouse Key" },
  {
    accessorKey: "stockout_probability",
    header: "Stockout Prob.",
    cell: (c) => formatPct(c.getValue() as number),
  },
  {
    accessorKey: "backorder_probability",
    header: "Backorder Prob.",
    cell: (c) => formatPct(c.getValue() as number),
  },
  {
    accessorKey: "fulfillment_delay_probability",
    header: "Delay Prob.",
    cell: (c) => formatPct(c.getValue() as number | null),
  },
  { accessorKey: "primary_supplier_key", header: "Primary Supplier" },
];

export default function ServiceLevelDashboardPage() {
  const { role } = useRole();
  const [page, setPage] = useState(1);
  const [minStockout, setMinStockout] = useState<number | undefined>(undefined);
  const [calibrationType, setCalibrationType] = useState("stockout");
  const pageSize = 25;

  const summary = useApi(() => api.serviceLevel.summary(role), [role]);
  const calibration = useApi(() => api.serviceLevel.calibration(role), [role]);
  const detail = useApi(
    () => api.serviceLevel.detail(role, { min_stockout: minStockout, page, page_size: pageSize }),
    [role, minStockout, page],
  );

  const activeCalibration = useMemo(() => {
    if (calibration.status !== "ready") return null;
    return calibration.data.find((c) => c.prediction_type === calibrationType) ?? null;
  }, [calibration, calibrationType]);

  const calibrationChartOption = useMemo<EChartsOption | null>(() => {
    if (!activeCalibration) return null;
    const buckets = activeCalibration.buckets;
    return {
      tooltip: { trigger: "axis" },
      legend: { data: ["Predicted", "Actual"], bottom: 0 },
      grid: { left: 60, right: 20, top: 40, bottom: 50 },
      xAxis: {
        type: "category",
        name: "Bucket (low to high predicted risk)",
        data: buckets.map((b) => `${b.bucket_index + 1}`),
      },
      yAxis: {
        type: "value",
        name: "Rate",
        axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` },
      },
      series: [
        {
          name: "Predicted",
          type: "line",
          smooth: false,
          lineStyle: { width: 2, type: "dashed" },
          data: buckets.map((b) => b.predicted_probability_mean),
        },
        {
          name: "Actual",
          type: "line",
          smooth: false,
          lineStyle: { width: 2 },
          data: buckets.map((b) => b.actual_outcome_rate),
        },
      ],
    };
  }, [activeCalibration]);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">Planning — Service-Level Prediction</h1>

      {summary.status === "loading" && <DashboardLoading />}
      {summary.status === "error" && <DashboardError error={summary.error} />}
      {summary.status === "ready" && (
        <>
          <p className="text-xs text-slate-400">
            As of ETL run #{summary.data.etl_run_id} — predictions generated{" "}
            {summary.data.generated_at ?? "—"} — source forecast model #
            {summary.data.source_forecast_model_id ?? "—"}, source supplier model #
            {summary.data.source_supplier_model_id ?? "—"}
          </p>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard
              label="Predictions"
              value={formatNumber(summary.data.n_predictions)}
              note={`${formatNumber(summary.data.n_with_delay_prediction)} with a delay prediction`}
            />
            <KpiCard
              label="Avg. Stockout Probability"
              value={formatPct(summary.data.avg_stockout_probability)}
            />
            <KpiCard
              label="Avg. Backorder Probability"
              value={formatPct(summary.data.avg_backorder_probability)}
            />
            <KpiCard
              label="High Stockout-Risk Pairs"
              value={formatNumber(summary.data.n_high_stockout_risk)}
              note="stockout probability > 50%"
            />
          </div>
        </>
      )}

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-500">
            Calibration Analysis — predicted vs. actual outcome rate by risk decile
          </h2>
          <select
            value={calibrationType}
            onChange={(e) => setCalibrationType(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
          >
            {Object.entries(PREDICTION_TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        {calibration.status === "loading" && <DashboardLoading />}
        {calibration.status === "error" && <DashboardError error={calibration.error} />}
        {calibration.status === "ready" && activeCalibration && calibrationChartOption && (
          <>
            <p className="mb-2 text-xs text-slate-400">
              Brier score {activeCalibration.brier_score.toFixed(4)} vs. naive baseline{" "}
              {activeCalibration.baseline_brier_score.toFixed(4)} (lower is better) — walk-forward
              validated {activeCalibration.test_start_date} to {activeCalibration.test_end_date},{" "}
              {formatNumber(activeCalibration.n_observations)} observations.
            </p>
            <Chart option={calibrationChartOption} height={280} />
          </>
        )}
        {calibration.status === "ready" && !activeCalibration && (
          <p className="text-sm text-slate-400">No calibration data for this prediction type.</p>
        )}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-500">Service-Level Detail</h2>
          <label className="flex items-center gap-2 text-sm text-slate-500">
            Min. stockout probability
            <select
              value={minStockout ?? ""}
              onChange={(e) => {
                setMinStockout(e.target.value ? Number(e.target.value) : undefined);
                setPage(1);
              }}
              className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="">All</option>
              <option value="0.25">≥ 25%</option>
              <option value="0.5">≥ 50%</option>
              <option value="0.75">≥ 75%</option>
            </select>
          </label>
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
