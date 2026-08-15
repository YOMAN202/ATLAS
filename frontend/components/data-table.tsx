"use client";

import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

declare module "@tanstack/react-table" {
  interface ColumnMeta<TData, TValue> {
    /** Overrides the cell's default whitespace-nowrap -- for long free-text columns. */
    wrap?: boolean;
  }
}

interface DataTableProps<T> {
  columns: ColumnDef<T, unknown>[];
  data: T[];
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

export function DataTable<T>({
  columns,
  data,
  page,
  pageSize,
  total,
  onPageChange,
}: DataTableProps<T>) {
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });
  const lastPage = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div>
      <div className="overflow-x-auto rounded-lg border border-hairline bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-inset">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="whitespace-nowrap px-4 py-2.5 text-left text-2xs font-medium uppercase tracking-wide text-ink-muted"
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className="border-t border-hairline transition-colors hover:bg-surface-2/60"
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className={cn(
                      "px-4 py-2.5 tabular-nums",
                      cell.column.columnDef.meta?.wrap
                        ? "max-w-md whitespace-normal"
                        : "whitespace-nowrap",
                    )}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {data.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-4 py-8 text-center text-ink-muted">
                  No rows for the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-ink-muted">
        <span>
          {total.toLocaleString()} rows — page {page} of {lastPage}
        </span>
        <div className="flex gap-2">
          <button
            className="inline-flex items-center gap-1 rounded-md border border-hairline px-2.5 py-1.5 text-ink-secondary transition-colors hover:border-hairline-strong hover:text-ink-primary disabled:pointer-events-none disabled:opacity-40"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            <ChevronLeft className="h-3.5 w-3.5" /> Previous
          </button>
          <button
            className="inline-flex items-center gap-1 rounded-md border border-hairline px-2.5 py-1.5 text-ink-secondary transition-colors hover:border-hairline-strong hover:text-ink-primary disabled:pointer-events-none disabled:opacity-40"
            disabled={page >= lastPage}
            onClick={() => onPageChange(page + 1)}
          >
            Next <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
