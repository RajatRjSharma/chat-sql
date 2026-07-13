import type { LabelHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export function Label({
  className,
  ...props
}: LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]",
        className,
      )}
      {...props}
    />
  );
}
