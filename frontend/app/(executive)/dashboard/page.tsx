"use client";

import { useState } from "react";

import { Chart } from "@/components/chart";
import { DashboardError, DashboardLoading } from "@/components/dashboard-status";
import { KpiCard } from "@/components/kpi-card";
import { api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import { useApi } from "@/lib/use-api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";

export default function ExecutiveDashboardPage() {
  const { role } = useRole();
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const query = useApi(
    () =>
      api.executive.summary(role, {
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      }),
    [role, dateFrom, dateTo],
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Executive Overview</h1>
        <div className="flex items-center gap-2 text-sm">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
          />
          <span className="text-slate-400">to</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
      </div>

      {query.status === "loading" && <DashboardLoading />}
      {query.status === "error" && <DashboardError error={query.error} />}
      {query.status === "ready" && (
        <>
          <p className="text-xs text-slate-400">As of ETL run #{query.data.as_of.etl_run_id}</p>

          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <KpiCard label="Revenue" value={formatCurrency(query.data.total_revenue)} />
            <KpiCard label="Gross Margin" value={formatCurrency(query.data.total_gross_margin)} />
            <KpiCard label="Orders" value={formatNumber(query.data.total_orders)} />
            <KpiCard label="Order Lines" value={formatNumber(query.data.total_order_lines)} />
            <KpiCard
              label="Fulfillment Rate"
              value={formatPercent(query.data.order_fulfillment_rate)}
            />
          </div>

          <KpiCard
            label="Cost to Serve"
            value="—"
            note={query.data.cost_to_serve_note}
            className="md:w-1/3"
          />

          <Chart
            option={{
              tooltip: { trigger: "axis" },
              legend: { data: ["Revenue", "Gross Margin"] },
              grid: { left: 60, right: 20, top: 40, bottom: 30 },
              xAxis: { type: "category", data: query.data.daily_trend.map((p) => p.full_date) },
              yAxis: { type: "value" },
              series: [
                {
                  name: "Revenue",
                  type: "line",
                  smooth: true,
                  data: query.data.daily_trend.map((p) => p.total_revenue),
                },
                {
                  name: "Gross Margin",
                  type: "line",
                  smooth: true,
                  data: query.data.daily_trend.map((p) => p.total_gross_margin),
                },
              ],
            }}
          />
        </>
      )}
    </div>
  );
}
