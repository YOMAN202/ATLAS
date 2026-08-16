"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, PackageX, ShieldAlert, TrendingDown } from "lucide-react";

import { Chart, type EChartsOption } from "@/components/chart";
import { DashboardError, DashboardLoading } from "@/components/dashboard-status";
import { KpiCard } from "@/components/kpi-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import { useApi } from "@/lib/use-api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";

export default function ExecutiveDashboardPage() {
  const { role } = useRole();
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const summary = useApi(
    () =>
      api.executive.summary(role, {
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      }),
    [role, dateFrom, dateTo],
  );
  const inventory = useApi(() => api.inventory.summary(role), [role]);
  const forecast = useApi(() => api.planning.summary(role), [role]);
  const supplierRisk = useApi(() => api.supplierRisk.summary(role), [role]);
  const serviceLevel = useApi(() => api.serviceLevel.summary(role), [role]);
  const inventoryPolicy = useApi(() => api.inventoryPolicy.summary(role), [role]);

  const trendOption = useMemo<EChartsOption | null>(() => {
    if (summary.status !== "ready") return null;
    return {
      tooltip: { trigger: "axis" },
      legend: { data: ["Revenue", "Gross Margin"], textStyle: { color: "#c3c2b7" } },
      grid: { left: 64, right: 20, top: 40, bottom: 30 },
      xAxis: {
        type: "category",
        data: summary.data.daily_trend.map((p) => p.full_date),
        axisLine: { lineStyle: { color: "#383835" } },
        axisLabel: { color: "#898781" },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#2c2c2a" } },
        axisLabel: { color: "#898781" },
      },
      series: [
        {
          name: "Revenue",
          type: "line",
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2, color: "#3987e5" },
          areaStyle: { color: "rgba(57,135,229,0.08)" },
          data: summary.data.daily_trend.map((p) => p.total_revenue),
        },
        {
          name: "Gross Margin",
          type: "line",
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2, color: "#199e70" },
          data: summary.data.daily_trend.map((p) => p.total_gross_margin),
        },
      ],
    };
  }, [summary]);

  // Alerts derived directly from already-fetched summary counts -- no
  // new computation, just surfacing thresholds the underlying modules
  // already flag (High supplier risk, high stockout risk, reorder-now).
  const alerts = useMemo(() => {
    const items: { icon: typeof AlertTriangle; label: string; tone: "warning" | "critical" }[] = [];
    if (supplierRisk.status === "ready" && supplierRisk.data.classification_breakdown.high > 0) {
      items.push({
        icon: ShieldAlert,
        label: `${supplierRisk.data.classification_breakdown.high} supplier${supplierRisk.data.classification_breakdown.high === 1 ? "" : "s"} flagged High risk`,
        tone: "critical",
      });
    }
    if (serviceLevel.status === "ready" && serviceLevel.data.n_high_stockout_risk > 0) {
      items.push({
        icon: PackageX,
        label: `${serviceLevel.data.n_high_stockout_risk} product/warehouse pairs at high stockout risk`,
        tone: "critical",
      });
    }
    if (
      inventoryPolicy.status === "ready" &&
      inventoryPolicy.data.balancing_breakdown.reorder_now > 0
    ) {
      items.push({
        icon: TrendingDown,
        label: `${inventoryPolicy.data.balancing_breakdown.reorder_now} SKU/warehouse pairs need reordering now`,
        tone: "warning",
      });
    }
    return items;
  }, [supplierRisk, serviceLevel, inventoryPolicy]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-headline font-semibold text-ink-primary">Executive Command Center</h1>
          <p className="mt-0.5 text-xs text-ink-muted">Monitor · Predict · Decide</p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="rounded-md border border-hairline bg-surface-inset px-2.5 py-1.5 text-ink-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          />
          <span className="text-ink-muted">to</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="rounded-md border border-hairline bg-surface-inset px-2.5 py-1.5 text-ink-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          />
        </div>
      </div>

      {summary.status === "loading" && <DashboardLoading />}
      {summary.status === "error" && <DashboardError error={summary.error} />}
      {summary.status === "ready" && (
        <>
          <p className="text-2xs text-ink-muted">As of ETL run #{summary.data.as_of.etl_run_id}</p>

          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard label="Revenue" value={formatCurrency(summary.data.total_revenue)} />
            <KpiCard label="Gross Margin" value={formatCurrency(summary.data.total_gross_margin)} />
            <KpiCard
              label="Fulfillment Rate"
              value={formatPercent(summary.data.order_fulfillment_rate)}
            />
            <KpiCard
              label="Inventory Value"
              value={
                inventory.status === "ready"
                  ? formatCurrency(inventory.data.total_inventory_value)
                  : "—"
              }
            />
          </div>

          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard
              label="Forecast Accuracy (MAPE)"
              value={
                forecast.status === "ready" && forecast.data.active_model?.weighted_avg_mape != null
                  ? formatPercent(forecast.data.active_model.weighted_avg_mape)
                  : "—"
              }
              note={
                forecast.status === "ready" ? forecast.data.active_model?.model_name : undefined
              }
            />
            <KpiCard
              label="Avg Supplier Risk"
              value={
                supplierRisk.status === "ready" && supplierRisk.data.avg_risk_score != null
                  ? formatNumber(supplierRisk.data.avg_risk_score) + " / 100"
                  : "—"
              }
              note={
                supplierRisk.status === "ready"
                  ? `${supplierRisk.data.classification_breakdown.high} High · ${supplierRisk.data.classification_breakdown.medium} Medium`
                  : undefined
              }
            />
            <KpiCard
              label="Stockout Risk (predicted)"
              value={
                serviceLevel.status === "ready" &&
                serviceLevel.data.avg_stockout_probability != null
                  ? formatPercent(serviceLevel.data.avg_stockout_probability)
                  : "—"
              }
            />
            <KpiCard
              label="Backorder Risk (predicted)"
              value={
                serviceLevel.status === "ready" &&
                serviceLevel.data.avg_backorder_probability != null
                  ? formatPercent(serviceLevel.data.avg_backorder_probability)
                  : "—"
              }
            />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Revenue &amp; Margin Trend</CardTitle>
              </CardHeader>
              <CardContent>
                {trendOption && <Chart option={trendOption} height={320} />}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Operational Alerts</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2.5">
                {alerts.length === 0 && (
                  <p className="text-sm text-ink-muted">No thresholds currently breached.</p>
                )}
                {alerts.map((alert, i) => (
                  <div
                    key={i}
                    className={`flex items-start gap-2.5 rounded-md border p-3 text-sm ${
                      alert.tone === "critical"
                        ? "border-status-critical/25 bg-status-critical/10 text-status-critical"
                        : "border-status-warning/25 bg-status-warning/10 text-status-warning"
                    }`}
                  >
                    <alert.icon className="mt-0.5 h-4 w-4 shrink-0" />
                    {alert.label}
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
