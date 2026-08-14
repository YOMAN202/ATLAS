import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface KpiCardProps {
  label: string;
  value: string;
  note?: string | null;
  className?: string;
}

export function KpiCard({ label, value, note, className }: KpiCardProps) {
  const unavailable = value === "—";
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div
          className={cn(
            "text-2xl font-semibold tabular-nums",
            unavailable && "text-slate-400 dark:text-slate-600",
          )}
        >
          {value}
        </div>
        {note && <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">{note}</p>}
      </CardContent>
    </Card>
  );
}
