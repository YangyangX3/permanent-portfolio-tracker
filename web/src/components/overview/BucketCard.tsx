import { cn } from "@/lib/cn";
import { fmtCny, fmtPct } from "@/lib/format";
import type { CategoryView } from "@/lib/types";

import { AssetTable } from "./AssetTable";

export function BucketCard({ c }: { c: CategoryView }) {
  const warn = c.status === "warn";
  return (
    <div className={cn("pp-card", warn && "border-stamp/35")}>
      <div className="flex items-start justify-between gap-2 border-b border-ink/10 px-3 py-2.5">
        <div className="min-w-0">
          <div className="pp-title text-sm font-extrabold">{c.name}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11.5px] text-ink/60">
            <span className="pp-badge">
              占比 <span className="pp-mono">{fmtPct((Number(c.weight) || 0) * 100, 1)}</span>
            </span>
            <span className="pp-badge">
              目标 <span className="pp-mono">{fmtPct((Number(c.target_weight) || 0) * 100, 0)}</span>
            </span>
            <span className="pp-badge">
              区间{" "}
              <span className="pp-mono">
                {fmtPct((Number(c.min_weight) || 0) * 100, 0)}~{fmtPct((Number(c.max_weight) || 0) * 100, 0)}
              </span>
            </span>
            {warn ? <span className="pp-stamp">超出阈值</span> : null}
          </div>
          {c.note ? <div className="mt-1.5 text-xs text-stamp">{c.note}</div> : null}
        </div>
        <div className="text-right">
          <div className="pp-mono text-sm font-semibold">¥ {fmtCny(c.value, 2)}</div>
          <div className="mt-1 text-[11px] text-ink/55">桶内市值</div>
        </div>
      </div>
      <div className="px-3 py-2.5">
        <AssetTable assets={c.assets} />
      </div>
    </div>
  );
}
