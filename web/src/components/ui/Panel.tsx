import { type ReactNode } from "react";

import { cn } from "@/lib/cn";

export function Panel({
  title,
  hint,
  right,
  children,
  className
}: {
  title: string;
  hint?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("pp-card", className)}>
      <div className="flex flex-wrap items-end justify-between gap-2 border-b border-ink/10 px-3 py-2.5">
        <div className="min-w-0">
          <div className="pp-title text-base font-extrabold">{title}</div>
          {hint ? <div className="mt-0.5 text-[12px] text-ink/60">{hint}</div> : null}
        </div>
        {right ? <div className="flex items-center gap-2">{right}</div> : null}
      </div>
      <div className="px-3 py-2.5">{children}</div>
    </section>
  );
}
