import type { LucideIcon } from "lucide-react";
import { Minus, TrendingDown, TrendingUp } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface DeltaProps {
  value: string;
  direction: "up" | "down" | "flat";
  /** Whether "up" is the good direction for this metric (default true).
   * Set false for metrics like backorder rate, where down is good. */
  positiveIsUp?: boolean;
}

interface KpiCardProps {
  label: string;
  value: string;
  note?: string | null;
  delta?: DeltaProps;
  icon?: LucideIcon;
  className?: string;
}

function Delta({ value, direction, positiveIsUp = true }: DeltaProps) {
  const isGood = direction === "flat" ? null : direction === "up" ? positiveIsUp : !positiveIsUp;
  const Icon = direction === "up" ? TrendingUp : direction === "down" ? TrendingDown : Minus;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs font-medium tabular-nums",
        isGood === null && "text-ink-muted",
        isGood === true && "text-status-good",
        isGood === false && "text-status-critical",
      )}
    >
      <Icon className="h-3.5 w-3.5" strokeWidth={2.5} />
      {value}
    </span>
  );
}

export function KpiCard({ label, value, note, delta, icon: Icon, className }: KpiCardProps) {
  const unavailable = value === "—";
  return (
    <Card className={cn("group hover:border-hairline-strong", className)}>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>{label}</CardTitle>
        {Icon && <Icon className="h-4 w-4 text-ink-muted" strokeWidth={1.75} />}
      </CardHeader>
      <CardContent>
        <div className="flex items-baseline gap-3">
          <div
            className={cn(
              "min-w-0 break-words text-display font-semibold tabular-nums transition-all duration-300",
              unavailable && "text-ink-muted",
            )}
          >
            {value}
          </div>
          {delta && !unavailable && <Delta {...delta} />}
        </div>
        {note && <p className="mt-1.5 break-words text-xs text-ink-muted">{note}</p>}
      </CardContent>
    </Card>
  );
}
