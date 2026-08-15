import { AlertTriangle, ShieldAlert } from "lucide-react";

import { ApiError } from "@/lib/api-client";

export function DashboardLoading() {
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="skeleton h-28 rounded-lg" />
      ))}
    </div>
  );
}

export function DashboardError({ error }: { error: Error }) {
  if (error instanceof ApiError && error.status === 403) {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-status-warning/25 bg-status-warning/10 p-4 text-sm text-status-warning">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
        Your current role doesn&apos;t have access to this dashboard. Switch roles above.
      </div>
    );
  }
  if (error instanceof ApiError && error.status === 503) {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-hairline bg-surface p-4 text-sm text-ink-secondary">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" />
        No successful ETL run found yet — the warehouse hasn&apos;t been loaded.
      </div>
    );
  }
  return (
    <div className="flex items-start gap-3 rounded-lg border border-status-critical/25 bg-status-critical/10 p-4 text-sm text-status-critical">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      {error.message}
    </div>
  );
}
