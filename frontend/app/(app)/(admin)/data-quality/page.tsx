"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { Chart, type EChartsOption } from "@/components/chart";
import { DashboardError, DashboardLoading } from "@/components/dashboard-status";
import { DataTable } from "@/components/data-table";
import { KpiCard } from "@/components/kpi-card";
import { api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import type { QuarantineRow, TableQualityRow } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { formatNumber, formatPercent } from "@/lib/utils";

const tableColumns: ColumnDef<TableQualityRow, unknown>[] = [
  { accessorKey: "source_table", header: "Table" },
  { accessorKey: "extracted_count", header: "Extracted" },
  { accessorKey: "quarantined_count", header: "Quarantined" },
  { accessorKey: "rejected_count", header: "Rejected" },
  {
    accessorKey: "dq_score",
    header: "DQ Score",
    cell: (c) => formatPercent(c.getValue() as number | null),
  },
];

const quarantineColumns: ColumnDef<QuarantineRow, unknown>[] = [
  { accessorKey: "etl_run_id", header: "Run" },
  { accessorKey: "source_table", header: "Table" },
  { accessorKey: "source_id", header: "Source ID" },
  { accessorKey: "rule_violated", header: "Rule" },
  { accessorKey: "rule_detail", header: "Detail" },
];

export default function DataQualityDashboardPage() {
  const { role } = useRole();
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const summary = useApi(() => api.dataQuality.summary(role), [role]);
  const quarantine = useApi(
    () => api.dataQuality.quarantine(role, { page, page_size: pageSize }),
    [role, page],
  );

  const runTrendOption = useMemo<EChartsOption | null>(() => {
    if (summary.status !== "ready" || summary.data.run_trend.length === 0) return null;
    return {
      tooltip: { trigger: "axis" },
      grid: { left: 60, right: 20, top: 20, bottom: 30 },
      xAxis: {
        type: "category",
        data: summary.data.run_trend.map((r) => `#${r.etl_run_id}`),
      },
      yAxis: { type: "value", min: 0, max: 1, axisLabel: { formatter: "{value}" } },
      series: [
        {
          name: "DQ Score",
          type: "bar",
          data: summary.data.run_trend.map((r) => r.overall_dq_score),
        },
      ],
    };
  }, [summary]);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-headline font-semibold text-ink-primary">Data Quality</h1>

      {summary.status === "loading" && <DashboardLoading />}
      {summary.status === "error" && <DashboardError error={summary.error} />}
      {summary.status === "ready" && (
        <>
          <p className="text-xs text-ink-muted">ETL run #{summary.data.etl_run_id}</p>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard
              label="Overall DQ Score"
              value={formatPercent(summary.data.overall_dq_score)}
            />
            <KpiCard label="Quarantine Rate" value={formatPercent(summary.data.quarantine_rate)} />
            <KpiCard
              label="Referential Integrity Failure Rate"
              value={formatPercent(summary.data.referential_integrity_failure_rate)}
            />
            <KpiCard
              label="Run Duration"
              value={`${formatNumber(Math.round(summary.data.duration_seconds))}s`}
            />
          </div>

          {runTrendOption && <Chart option={runTrendOption} height={220} />}

          <div>
            <h2 className="mb-2 text-sm font-medium text-ink-secondary">
              Per-Table Breakdown (current run)
            </h2>
            <DataTable
              columns={tableColumns}
              data={summary.data.per_table}
              page={1}
              pageSize={summary.data.per_table.length || 1}
              total={summary.data.per_table.length}
              onPageChange={() => {}}
            />
          </div>
        </>
      )}

      <div>
        <h2 className="mb-2 text-sm font-medium text-ink-secondary">Quarantine Detail</h2>
        {quarantine.status === "loading" && <DashboardLoading />}
        {quarantine.status === "error" && <DashboardError error={quarantine.error} />}
        {quarantine.status === "ready" && (
          <DataTable
            columns={quarantineColumns}
            data={quarantine.data.data}
            page={quarantine.data.page}
            pageSize={quarantine.data.page_size}
            total={quarantine.data.total}
            onPageChange={setPage}
          />
        )}
      </div>
    </div>
  );
}
