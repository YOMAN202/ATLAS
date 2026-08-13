"use client";

import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { DashboardError, DashboardLoading } from "@/components/dashboard-status";
import { DataTable } from "@/components/data-table";
import { KpiCard } from "@/components/kpi-card";
import { api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import type { InventoryRow } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";

const columns: ColumnDef<InventoryRow, unknown>[] = [
  { accessorKey: "snapshot_date", header: "Date" },
  { accessorKey: "product_key", header: "Product Key" },
  { accessorKey: "warehouse_key", header: "Warehouse Key" },
  { accessorKey: "quantity_on_hand", header: "On Hand" },
  { accessorKey: "quantity_available", header: "Available" },
  { accessorKey: "inventory_value", header: "Value", cell: (c) => formatCurrency(c.getValue() as number) },
  { accessorKey: "is_stockout", header: "Stockout", cell: (c) => ((c.getValue() as boolean) ? "Yes" : "No") },
];

export default function InventoryDashboardPage() {
  const { role } = useRole();
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const summary = useApi(() => api.inventory.summary(role), [role]);
  const detail = useApi(() => api.inventory.detail(role, { page, page_size: pageSize }), [role, page]);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">Inventory</h1>

      {summary.status === "loading" && <DashboardLoading />}
      {summary.status === "error" && <DashboardError error={summary.error} />}
      {summary.status === "ready" && (
        <>
          <p className="text-xs text-slate-400">As of {summary.data.latest_snapshot_date ?? "—"}</p>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <KpiCard label="On Hand (units)" value={formatNumber(summary.data.total_quantity_on_hand)} />
            <KpiCard label="Inventory Value" value={formatCurrency(summary.data.total_inventory_value)} />
            <KpiCard label="Stockout Rate" value={formatPercent(summary.data.stockout_rate)} />
            <KpiCard label="Turnover" value={summary.data.inventory_turnover?.toFixed(2) ?? "—"} />
            <KpiCard label="Days of Supply" value={summary.data.days_of_supply?.toFixed(1) ?? "—"} />
          </div>
          <KpiCard label="Overstock Value" value="—" note={summary.data.overstock_value_note} className="md:w-1/3" />
        </>
      )}

      <div>
        <h2 className="mb-2 text-sm font-medium text-slate-500">Snapshot Detail (most recent first)</h2>
        {detail.status === "loading" && <DashboardLoading />}
        {detail.status === "error" && <DashboardError error={detail.error} />}
        {detail.status === "ready" && (
          <DataTable
            columns={columns}
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
