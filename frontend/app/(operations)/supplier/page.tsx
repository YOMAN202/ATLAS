"use client";

import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { DashboardError, DashboardLoading } from "@/components/dashboard-status";
import { DataTable } from "@/components/data-table";
import { KpiCard } from "@/components/kpi-card";
import { api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import type { SupplierDeliveryRow } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { formatNumber, formatPercent } from "@/lib/utils";

const columns: ColumnDef<SupplierDeliveryRow, unknown>[] = [
  { accessorKey: "po_number", header: "PO Number" },
  { accessorKey: "supplier_key", header: "Supplier Key" },
  { accessorKey: "product_key", header: "Product Key" },
  { accessorKey: "received_quantity", header: "Received" },
  { accessorKey: "quality_rejected_quantity", header: "Rejected" },
  { accessorKey: "is_on_time", header: "On Time", cell: (c) => ((c.getValue() as boolean) ? "Yes" : "No") },
  { accessorKey: "lead_time_variance_days", header: "Lead Time Variance (days)" },
];

export default function SupplierDashboardPage() {
  const { role } = useRole();
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const summary = useApi(() => api.supplier.summary(role), [role]);
  const detail = useApi(() => api.supplier.detail(role, { page, page_size: pageSize }), [role, page]);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">Supplier</h1>

      {summary.status === "loading" && <DashboardLoading />}
      {summary.status === "error" && <DashboardError error={summary.error} />}
      {summary.status === "ready" && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard label="Deliveries" value={formatNumber(summary.data.total_deliveries)} />
            <KpiCard label="On-Time Delivery Rate" value={formatPercent(summary.data.on_time_delivery_rate)} />
            <KpiCard
              label="Avg Lead Time Variance"
              value={summary.data.average_lead_time_variance_days?.toFixed(1) ?? "—"}
            />
            <KpiCard label="Quality Rejection Rate" value={formatPercent(summary.data.quality_rejection_rate)} />
          </div>
          <KpiCard label="Risk Score" value="—" note={summary.data.risk_score_note} className="md:w-1/3" />
        </>
      )}

      <div>
        <h2 className="mb-2 text-sm font-medium text-slate-500">Delivery Detail</h2>
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
