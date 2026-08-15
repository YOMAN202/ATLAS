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
import type { SupplierRiskRow } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { formatNumber } from "@/lib/utils";

const CLASSIFICATION_OPTIONS = [
  { value: "", label: "All" },
  { value: "High", label: "High" },
  { value: "Medium", label: "Medium" },
  { value: "Low", label: "Low" },
] as const;

const CLASSIFICATION_COLOR: Record<string, string> = {
  High: "text-status-critical",
  Medium: "text-status-warning",
  Low: "text-status-good",
};

const detailColumns: ColumnDef<SupplierRiskRow, unknown>[] = [
  { accessorKey: "supplier_key", header: "Supplier Key" },
  {
    accessorKey: "risk_score",
    header: "Risk Score",
    cell: (c) => c.getValue() as number,
  },
  {
    accessorKey: "risk_classification",
    header: "Classification",
    cell: (c) => {
      const v = c.getValue() as string;
      return <span className={CLASSIFICATION_COLOR[v]}>{v}</span>;
    },
  },
  {
    accessorKey: "on_time_rate",
    header: "On-Time Rate",
    cell: (c) => `${((c.getValue() as number) * 100).toFixed(1)}%`,
  },
  {
    accessorKey: "quality_rejection_rate",
    header: "Quality Rejection",
    cell: (c) => `${((c.getValue() as number) * 100).toFixed(2)}%`,
  },
  {
    accessorKey: "lead_time_stddev_days",
    header: "Lead-Time StdDev (d)",
    cell: (c) => (c.getValue() as number).toFixed(2),
  },
  { accessorKey: "trend_direction", header: "Trend" },
  {
    accessorKey: "total_spend",
    header: "Total Spend",
    cell: (c) => formatNumber(c.getValue() as number),
  },
  {
    accessorKey: "triggering_metrics",
    header: "Triggering Metrics",
    meta: { wrap: true },
    cell: (c) => {
      const metrics = c.getValue() as string[];
      return metrics.length === 0 ? "—" : metrics.join("; ");
    },
  },
];

export default function SupplierRiskDashboardPage() {
  const { role } = useRole();
  const [classification, setClassification] = useState<"" | "Low" | "Medium" | "High">("");
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const summary = useApi(() => api.supplierRisk.summary(role), [role]);
  const detail = useApi(
    () =>
      api.supplierRisk.detail(role, {
        risk_classification: classification || undefined,
        page,
        page_size: pageSize,
      }),
    [role, classification, page],
  );

  const chartOption = useMemo<EChartsOption | null>(() => {
    if (summary.status !== "ready") return null;
    const { low, medium, high } = summary.data.classification_breakdown;
    return {
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [
        {
          type: "pie",
          radius: ["45%", "70%"],
          data: [
            { name: "Low", value: low, itemStyle: { color: "#10b981" } },
            { name: "Medium", value: medium, itemStyle: { color: "#f59e0b" } },
            { name: "High", value: high, itemStyle: { color: "#ef4444" } },
          ],
        },
      ],
    };
  }, [summary]);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-headline font-semibold text-ink-primary">Planning — Supplier Risk</h1>

      {summary.status === "loading" && <DashboardLoading />}
      {summary.status === "error" && <DashboardError error={summary.error} />}
      {summary.status === "ready" && (
        <>
          <p className="text-xs text-ink-muted">
            As of ETL run #{summary.data.etl_run_id} — scores generated{" "}
            {summary.data.generated_at ?? "—"}
          </p>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard
              label="Scoring Model"
              value={summary.data.model_name ?? "—"}
              note={
                summary.data.scoring_weights
                  ? Object.entries(summary.data.scoring_weights)
                      .map(([k, v]) => `${k} ${(v * 100).toFixed(0)}%`)
                      .join(" · ")
                  : "No model has been run yet."
              }
            />
            <KpiCard label="Suppliers Scored" value={formatNumber(summary.data.n_suppliers)} />
            <KpiCard
              label="Average Risk Score"
              value={
                summary.data.avg_risk_score !== null ? summary.data.avg_risk_score.toFixed(1) : "—"
              }
            />
            <KpiCard
              label="High Risk Suppliers"
              value={formatNumber(summary.data.classification_breakdown.high)}
              note={`${summary.data.classification_breakdown.medium} medium, ${summary.data.classification_breakdown.low} low`}
            />
          </div>

          {chartOption && (
            <div>
              <h2 className="mb-2 text-sm font-medium text-ink-secondary">
                Risk Classification Breakdown
              </h2>
              <Chart option={chartOption} height={280} />
            </div>
          )}
        </>
      )}

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-ink-secondary">Supplier Risk Detail</h2>
          <select
            value={classification}
            onChange={(e) => {
              setClassification(e.target.value as typeof classification);
              setPage(1);
            }}
            className="rounded-md border border-hairline bg-surface-inset px-2.5 py-1.5 text-sm text-ink-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {CLASSIFICATION_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
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
