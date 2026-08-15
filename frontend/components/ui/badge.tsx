import { cn } from "@/lib/utils";

type BadgeTone = "neutral" | "accent" | "good" | "warning" | "serious" | "critical";

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-surface-2 text-ink-secondary",
  accent: "bg-accent-subtle text-accent",
  good: "bg-status-good/15 text-status-good",
  warning: "bg-status-warning/15 text-status-warning",
  serious: "bg-status-serious/15 text-status-serious",
  critical: "bg-status-critical/15 text-status-critical",
};

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: BadgeTone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-2xs font-medium",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
