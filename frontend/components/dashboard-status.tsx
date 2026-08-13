import { ApiError } from "@/lib/api-client";

export function DashboardLoading() {
  return <div className="p-8 text-center text-sm text-slate-400">Loading…</div>;
}

export function DashboardError({ error }: { error: Error }) {
  if (error instanceof ApiError && error.status === 403) {
    return (
      <div className="rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
        Your current role doesn&apos;t have access to this dashboard. Switch roles above.
      </div>
    );
  }
  if (error instanceof ApiError && error.status === 503) {
    return (
      <div className="rounded-md border border-slate-300 bg-slate-50 p-4 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
        No successful ETL run found yet — the warehouse hasn&apos;t been loaded.
      </div>
    );
  }
  return (
    <div className="rounded-md border border-red-300 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
      {error.message}
    </div>
  );
}
