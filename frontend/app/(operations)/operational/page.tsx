"use client";

import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { DashboardError, DashboardLoading } from "@/components/dashboard-status";
import { DataTable } from "@/components/data-table";
import { KpiCard } from "@/components/kpi-card";
import { api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import type { ShipmentRow, WarehouseCapacityRow } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";

const shipmentColumns: ColumnDef<ShipmentRow, unknown>[] = [
  { accessorKey: "shipment_number", header: "Shipment" },
  { accessorKey: "status_code", header: "Status" },
  { accessorKey: "carrier_key", header: "Carrier Key" },
  { accessorKey: "origin_warehouse_key", header: "Origin Warehouse Key" },
  { accessorKey: "distance_miles", header: "Miles" },
  {
    accessorKey: "shipping_cost",
    header: "Cost",
    cell: (c) => formatCurrency(c.getValue() as number | null),
  },
  { accessorKey: "transit_days", header: "Transit Days" },
];

const capacityColumns: ColumnDef<WarehouseCapacityRow, unknown>[] = [
  { accessorKey: "warehouse_name", header: "Warehouse" },
  { accessorKey: "quantity_on_hand", header: "On Hand" },
  { accessorKey: "total_capacity_units", header: "Capacity" },
  {
    accessorKey: "capacity_utilization",
    header: "Utilization",
    cell: (c) => formatPercent(c.getValue() as number | null),
  },
];

export default function OperationalDashboardPage() {
  const { role } = useRole();
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const summary = useApi(() => api.operational.summary(role), [role]);
  const detail = useApi(
    () => api.operational.detail(role, { page, page_size: pageSize }),
    [role, page],
  );

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">Operational</h1>

      {summary.status === "loading" && <DashboardLoading />}
      {summary.status === "error" && <DashboardError error={summary.error} />}
      {summary.status === "ready" && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard label="Shipments" value={formatNumber(summary.data.total_shipments)} />
            <KpiCard
              label="On-Time Delivery Rate"
              value={formatPercent(summary.data.on_time_delivery_rate)}
              note={summary.data.on_time_delivery_rate_note}
            />
            <KpiCard
              label="Avg Cost / Mile"
              value={formatCurrency(summary.data.average_cost_per_mile)}
            />
            <KpiCard
              label="Avg Transit Days"
              value={summary.data.average_transit_days?.toFixed(1) ?? "—"}
            />
          </div>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard label="Pick Accuracy" value="—" note={summary.data.pick_accuracy_note} />
            <KpiCard label="Zone Throughput" value="—" note={summary.data.zone_throughput_note} />
          </div>

          <div>
            <h2 className="mb-2 text-sm font-medium text-slate-500">
              Warehouse Capacity (latest snapshot)
            </h2>
            <DataTable
              columns={capacityColumns}
              data={summary.data.warehouse_capacity}
              page={1}
              pageSize={summary.data.warehouse_capacity.length || 1}
              total={summary.data.warehouse_capacity.length}
              onPageChange={() => {}}
            />
          </div>
        </>
      )}

      <div>
        <h2 className="mb-2 text-sm font-medium text-slate-500">Shipment Detail</h2>
        {detail.status === "loading" && <DashboardLoading />}
        {detail.status === "error" && <DashboardError error={detail.error} />}
        {detail.status === "ready" && (
          <DataTable
            columns={shipmentColumns}
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
