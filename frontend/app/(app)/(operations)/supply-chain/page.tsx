"use client";

import { useMemo } from "react";
import { AlertTriangle, MapPin, Warehouse as WarehouseIcon } from "lucide-react";

import { DashboardError, DashboardLoading } from "@/components/dashboard-status";
import { KpiCard } from "@/components/kpi-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import type { SupplierRiskRow, WarehouseCapacityRow } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn, formatCurrency, formatNumber, formatPercent } from "@/lib/utils";

const RISK_TONE: Record<string, string> = {
  Low: "border-status-good/25 bg-status-good/10 text-status-good",
  Medium: "border-status-warning/25 bg-status-warning/10 text-status-warning",
  High: "border-status-critical/25 bg-status-critical/10 text-status-critical",
};

function CapacityMeter({ value }: { value: number | null }) {
  const pct = value != null ? Math.min(value * 100, 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-500 ease-out"
          style={{ width: `${Math.max(pct, value != null && value > 0 ? 2 : 0)}%` }}
        />
      </div>
      <span className="w-12 shrink-0 text-right text-2xs tabular-nums text-ink-muted">
        {value != null ? `${(value * 100).toFixed(1)}%` : "—"}
      </span>
    </div>
  );
}

function WarehouseCard({ w }: { w: WarehouseCapacityRow }) {
  return (
    <div className="animate-rise-in rounded-lg border border-hairline bg-surface p-3.5 transition-colors hover:border-hairline-strong">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-1.5 text-sm font-medium text-ink-primary">
            <WarehouseIcon className="h-3.5 w-3.5 text-ink-muted" />
            {w.warehouse_name}
          </div>
          {w.city && (
            <div className="mt-0.5 flex items-center gap-1 text-2xs text-ink-muted">
              <MapPin className="h-3 w-3" />
              {w.city}
            </div>
          )}
        </div>
        <span className="shrink-0 text-2xs tabular-nums text-ink-muted">
          {formatNumber(w.quantity_on_hand)} / {formatNumber(w.total_capacity_units)} units
        </span>
      </div>
      <div className="mt-3">
        <CapacityMeter value={w.capacity_utilization} />
      </div>
    </div>
  );
}

function SupplierRiskRowItem({ s }: { s: SupplierRiskRow }) {
  return (
    <div className="flex items-center justify-between gap-3 border-t border-hairline py-2.5 first:border-t-0">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-ink-primary">Supplier #{s.supplier_key}</span>
          <span
            className={cn(
              "rounded-full border px-1.5 py-0.5 text-2xs font-medium",
              RISK_TONE[s.risk_classification] ?? "border-hairline text-ink-muted",
            )}
          >
            {s.risk_classification}
          </span>
        </div>
        <div className="mt-0.5 text-2xs text-ink-muted">
          {formatCurrency(s.total_spend)} spend · {formatPercent(s.share_of_total_spend)} of total ·{" "}
          {s.distinct_warehouses_served} warehouses served
        </div>
      </div>
      <span className="shrink-0 text-sm font-semibold tabular-nums text-ink-primary">
        {s.risk_score.toFixed(0)}
      </span>
    </div>
  );
}

export default function SupplyChainMapPage() {
  const { role } = useRole();

  const operational = useApi(() => api.operational.summary(role), [role]);
  const supplierRisk = useApi(
    () => api.supplierRisk.detail(role, { page: 1, page_size: 8 }),
    [role],
  );

  const byRegion = useMemo(() => {
    if (operational.status !== "ready") return [];
    const groups = new Map<string, WarehouseCapacityRow[]>();
    for (const w of operational.data.warehouse_capacity) {
      const key = w.region_name ?? "Unassigned";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(w);
    }
    return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [operational]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-headline font-semibold text-ink-primary">Supply Chain Map</h1>
        <p className="mt-1 text-xs text-ink-muted">
          Live warehouse network and supplier risk, in one view — real capacity utilization by site
          and the highest-risk suppliers currently feeding it. City/region are actual dim_warehouse
          attributes, not placed on a geographic map (this dataset has no coordinates).
        </p>
      </div>

      {operational.status === "loading" && <DashboardLoading />}
      {operational.status === "error" && <DashboardError error={operational.error} />}
      {operational.status === "ready" && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <KpiCard label="Total Shipments" value={formatNumber(operational.data.total_shipments)} />
          <KpiCard
            label="Avg Cost / Mile"
            value={
              operational.data.average_cost_per_mile != null
                ? formatCurrency(operational.data.average_cost_per_mile)
                : "—"
            }
          />
          <KpiCard
            label="Avg Transit Days"
            value={
              operational.data.average_transit_days != null
                ? operational.data.average_transit_days.toFixed(1)
                : "—"
            }
          />
          <KpiCard
            label="Warehouses Monitored"
            value={formatNumber(operational.data.warehouse_capacity.length)}
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="flex flex-col gap-5 xl:col-span-2">
          {operational.status === "ready" &&
            byRegion.map(([region, warehouses]) => (
              <div key={region}>
                <h2 className="mb-2 text-sm font-medium text-ink-secondary">{region}</h2>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {warehouses.map((w) => (
                    <WarehouseCard key={w.warehouse_key} w={w} />
                  ))}
                </div>
              </div>
            ))}
        </div>

        <Card>
          <CardHeader className="flex-row items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-status-warning" />
            <CardTitle>Supplier Risk Watch</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col">
            {supplierRisk.status === "loading" && <DashboardLoading />}
            {supplierRisk.status === "error" && <DashboardError error={supplierRisk.error} />}
            {supplierRisk.status === "ready" &&
              supplierRisk.data.data.map((s) => <SupplierRiskRowItem key={s.supplier_key} s={s} />)}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
