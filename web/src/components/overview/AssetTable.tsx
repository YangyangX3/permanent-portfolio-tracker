import { Fragment } from "react";

import { cn } from "@/lib/cn";
import { fmtCny, fmtPrice, fmtQty, fmtPct } from "@/lib/format";
import type { AssetView } from "@/lib/types";

export function AssetTable({ assets }: { assets: AssetView[] }) {
  if (!assets || assets.length === 0) return <div className="text-[13px] text-ink/60">暂无资产。</div>;

  const cols = [
    "grid-cols-[minmax(0,240px)_repeat(4,minmax(56px,1fr))]",
    "md:grid-cols-[minmax(0,280px)_repeat(4,minmax(64px,1fr))]",
    "lg:grid-cols-[minmax(0,320px)_repeat(4,minmax(72px,1fr))]"
  ].join(" ");

  return (
    <div className={cn("grid items-start gap-x-2", cols)}>
      <div className="py-1.5 text-[10.5px] uppercase tracking-widest text-ink/45">资产</div>
      <div className="min-w-0 py-1.5 text-center text-[10.5px] uppercase tracking-widest text-ink/45 whitespace-nowrap">现价</div>
      <div className="min-w-0 py-1.5 text-center text-[10.5px] uppercase tracking-widest text-ink/45 whitespace-nowrap">涨跌</div>
      <div className="min-w-0 py-1.5 text-center text-[10.5px] uppercase tracking-widest text-ink/45 whitespace-nowrap">数量/金额</div>
      <div className="min-w-0 py-1.5 text-center text-[10.5px] uppercase tracking-widest text-ink/45 whitespace-nowrap">市值</div>

      <div className="col-span-5 h-px bg-ink/10" />

      {assets.map((a, idx) => {
        const changePct = a.change_pct == null ? null : Number(a.change_pct);
        return (
          <Fragment key={a.id}>
            <div className="min-w-0 py-2">
              <div className="truncate text-[12px] font-medium">{a.name || a.code || "—"}</div>
              <div className="truncate text-[10px] text-ink/55">
                <span className="pp-mono">{a.code || "—"}</span>
                {a.source ? <span className="ml-2 text-ink/40">{a.source}</span> : null}
                {a.status === "error" ? <span className="ml-2 text-danger/90">异常</span> : null}
              </div>
            </div>
            <div className="min-w-0 py-2 text-center text-[12px] pp-mono whitespace-nowrap">{fmtPrice(a.price, a.kind as any)}</div>
            <div
              className={cn(
                "min-w-0 py-2 text-center text-[12px] pp-mono whitespace-nowrap",
                changePct != null && changePct > 0 && "text-ok",
                changePct != null && changePct < 0 && "text-danger"
              )}
            >
              {changePct == null ? "—" : fmtPct(changePct, 2)}
            </div>
            <div className="min-w-0 py-2 text-center text-[12px] pp-mono whitespace-nowrap">
              {a.kind === "cash" ? `¥ ${fmtCny(a.value, 2)}` : fmtQty(a.quantity, a.kind as any)}
            </div>
            <div className="min-w-0 py-2 text-center text-[12px] pp-mono whitespace-nowrap">¥ {fmtCny(a.value, 2)}</div>

            {idx < assets.length - 1 ? <div className="col-span-5 h-px bg-ink/10" /> : null}
          </Fragment>
        );
      })}
    </div>
  );
}
