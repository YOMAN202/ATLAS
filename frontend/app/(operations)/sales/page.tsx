"use client";

import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { DashboardError, DashboardLoading } from "@/components/dashboard-status";
import { DataTable } from "@/components/data-table";
import { KpiCard } from "@/components/kpi-card";
import { api } from "@/lib/api-client";
import { useRole } from "@/lib/role-context";
import type { OrderLineRow } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";

const columns: ColumnDef<OrderLineRow, unknown>[] = [
  { accessorKey: "order_number", header: "Order" },
  { accessorKey: "order_line_number", header: "Line" },
  { accessorKey: "product_key", header: "Product Key" },
  { accessorKey: "customer_key", header: "Customer Key" },
  { accessorKey: "ordered_quantity", header: "Ordered" },
  { accessorKey: "allocated_quantity", header: "Allocated" },
  { accessorKey: "backordered_quantity", header: "Backordered" },
  {
    accessorKey: "extended_revenue",
    header: "Revenue",
    cell: (c) => formatCurrency(c.getValue() as number),
  },
  {
    accessorKey: "gross_margin",
    header: "Margin",
    cell: (c) => formatCurrency(c.getValue() as number),
  },
];

export default function SalesDashboardPage() {
  const { role } = useRole();
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const summary = useApi(() => api.sales.summary(role), [role]);
  const detail = useApi(() => api.sales.detail(role, { page, page_size: pageSize }), [role, page]);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">Sales</h1>

      {summary.status === "loading" && <DashboardLoading />}
      {summary.status === "error" && <DashboardError error={summary.error} />}
      {summary.status === "ready" && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <KpiCard label="Order Lines" value={formatNumber(summary.data.total_order_lines)} />
          <KpiCard label="Distinct Orders" value={formatNumber(summary.data.distinct_orders)} />
          <KpiCard label="Fulfillment Rate" value={formatPercent(summary.data.fulfillment_rate)} />
          <KpiCard
            label="Avg Order Value"
            value={formatCurrency(summary.data.average_order_value)}
          />
        </div>
      )}

      <div>
        <h2 className="mb-2 text-sm font-medium text-slate-500">Order Line Detail</h2>
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
