"use client";

import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { DashboardError, DashboardLoading } from "@/components/dashboard-status";
import { DataTable } from "@/components/data-table";
import { KpiCard } from "@/components/kpi-card";
import { api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import type { ProcurementRow } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";

const columns: ColumnDef<ProcurementRow, unknown>[] = [
  { accessorKey: "po_number", header: "PO Number" },
  { accessorKey: "po_status_code", header: "Status" },
  { accessorKey: "supplier_key", header: "Supplier Key" },
  { accessorKey: "product_key", header: "Product Key" },
  { accessorKey: "ordered_quantity", header: "Ordered" },
  { accessorKey: "received_quantity", header: "Received" },
  { accessorKey: "quality_rejected_quantity", header: "Rejected" },
  {
    accessorKey: "extended_cost",
    header: "Cost",
    cell: (c) => formatCurrency(c.getValue() as number),
  },
];

export default function ProcurementDashboardPage() {
  const { role } = useRole();
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const summary = useApi(() => api.procurement.summary(role), [role]);
  const detail = useApi(
    () => api.procurement.detail(role, { page, page_size: pageSize }),
    [role, page],
  );

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">Procurement</h1>

      {summary.status === "loading" && <DashboardLoading />}
      {summary.status === "error" && <DashboardError error={summary.error} />}
      {summary.status === "ready" && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <KpiCard label="PO Lines" value={formatNumber(summary.data.total_po_lines)} />
          <KpiCard label="Total Spend" value={formatCurrency(summary.data.total_spend)} />
          <KpiCard label="Receipt Rate" value={formatPercent(summary.data.receipt_rate)} />
          <KpiCard
            label="Quality Rejection Rate"
            value={formatPercent(summary.data.quality_rejection_rate)}
          />
        </div>
      )}

      <div>
        <h2 className="mb-2 text-sm font-medium text-slate-500">PO Line Detail</h2>
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
