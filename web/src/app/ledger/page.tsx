"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { useToast } from "@/components/toast/ToastProvider";
import { Panel } from "@/components/ui/Panel";
import { Separator } from "@/components/ui/Separator";
import { api, type ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { fmtCny, fmtPct, fmtSignedCny } from "@/lib/format";
import type { LedgerDaysPayload, LedgerMetricsPayload, UiState } from "@/lib/types";

function fmtDateInput(d: Date) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export default function LedgerPage() {
  const toast = useToast();
  const [manage, setManage] = useState(false);

  const stateQ = useQuery({
    queryKey: ["state"],
    queryFn: () => api.get<UiState>("/api/v2/state"),
    refetchInterval: 30_000
  });

  const metricsQ = useQuery({
    queryKey: ["ledger-metrics"],
    queryFn: () => api.get<LedgerMetricsPayload>("/api/v2/ledger/metrics"),
    refetchInterval: 30_000
  });

  const daysQ = useQuery({
    queryKey: ["ledger-days", manage ? 1 : 0],
    queryFn: () => api.get<LedgerDaysPayload>(`/api/ui/ledger-days?manage=${manage ? "1" : "0"}`),
    staleTime: 3_000
  });

  const addM = useMutation({
    mutationFn: async (payload: any) => api.post("/api/v2/ledger", payload),
    onSuccess: () => {
      toast.push("已新增记录", { tone: "ok" });
      metricsQ.refetch();
      daysQ.refetch();
    },
    onError: (e: any) => toast.push("新增失败", { tone: "danger", detail: (e as ApiError)?.message || "" })
  });

  const delM = useMutation({
    mutationFn: async (entryId: string) => api.del(`/api/v2/ledger/${encodeURIComponent(entryId)}`),
    onSuccess: () => {
      toast.push("已删除", { tone: "ok" });
      metricsQ.refetch();
      daysQ.refetch();
    },
    onError: (e: any) => toast.push("删除失败", { tone: "danger", detail: (e as ApiError)?.message || "" })
  });

  const total = metricsQ.data?.total ?? null;
  const profit = total?.profit == null ? null : Number(total.profit);
  const xirr = total?.xirr_annual == null ? null : Number(total.xirr_annual) * 100;
  const showProfit =
    total != null &&
    (xirr != null || Number(total.principal ?? 0) !== 0 || Number(total.current_value ?? 0) !== 0 || Number(total.profit ?? 0) !== 0);

  const assetOptions = useMemo(() => {
    const p = stateQ.data?.portfolio;
    if (!p) return [];
    const map = new Map<string, string>();
    for (const a of p.assets) {
      const name = (a.name || a.code || a.coingecko_id || a.id).trim();
      map.set(a.id, name);
    }
    return Array.from(map.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((x, y) => x.name.localeCompare(y.name, "zh-CN"));
  }, [stateQ.data?.portfolio]);

  const today = fmtDateInput(new Date());

  return (
    <div className="space-y-4">
      <section className="grid gap-3 lg:grid-cols-[1.4fr_.9fr]">
        <div className="pp-card px-4 py-4">
          <div className="text-[12px] uppercase tracking-[0.22em] text-ink/45">组合收益（估算）</div>
          <div className="mt-2 flex flex-wrap items-baseline gap-3">
            <div className="pp-title text-3xl font-black">
              ¥ <span className="pp-mono">{fmtCny(total?.current_value, 2)}</span>
            </div>
            <div
              className={cn(
                "pp-mono text-sm font-semibold",
                showProfit && profit != null && profit > 0 && "text-ok",
                showProfit && profit != null && profit < 0 && "text-danger",
                !showProfit && "text-ink/45"
              )}
            >
              {showProfit ? fmtSignedCny(profit, 2) : "—"}
              {showProfit && xirr != null ? <span className="ml-2 text-ink/55">({fmtPct(xirr, 2)})</span> : null}
            </div>
          </div>
          <div className="mt-2 text-[12px] text-ink/60">
            本金：¥ <span className="pp-mono">{fmtCny(total?.principal, 2)}</span>
            <span className="mx-2 text-ink/35">·</span>
            年化口径：按现金流估算（XIRR）
          </div>
        </div>

        <div className="pp-card px-4 py-4">
          <div className="pp-title text-base font-extrabold">快速记一笔</div>
          <div className="mt-2 text-[12px] text-ink/65">建议：每次投入/取出都记录，年化更接近真实。</div>
          <div className="mt-4 flex flex-wrap gap-2">
            <a className="pp-btn" href="#ledger-add">
              新增记录
            </a>
            <button type="button" className="pp-btn pp-btn-ghost" onClick={() => setManage((v) => !v)}>
              {manage ? "关闭管理" : "开启管理"}
            </button>
          </div>
        </div>
      </section>

      <Panel title="新增本金记录" hint="金额为 CNY；“投入”为正，“取出”为负（用于收益/年化计算）。" className="scroll-mt-24" >
        <form
          id="ledger-add"
          className="grid gap-3 md:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            const fd = new FormData(e.currentTarget);
            const payload = {
              date: String(fd.get("date") || ""),
              direction: String(fd.get("direction") || "deposit"),
              amount_cny: Number(fd.get("amount_cny") || 0),
              asset_id: String(fd.get("asset_id") || "") || null,
              note: String(fd.get("note") || "") || null
            };
            addM.mutate(payload);
            e.currentTarget.reset();
          }}
        >
          <label className="block">
            <div className="mb-2 text-[12px] text-ink/65">日期</div>
            <input className="pp-input pp-mono" name="date" type="date" defaultValue={today} />
          </label>
          <label className="block">
            <div className="mb-2 text-[12px] text-ink/65">方向</div>
            <select className="pp-select" name="direction" defaultValue="deposit">
              <option value="deposit">投入本金</option>
              <option value="withdraw">取出资金</option>
            </select>
          </label>
          <label className="block">
            <div className="mb-2 text-[12px] text-ink/65">金额（CNY）</div>
            <input className="pp-input pp-mono" name="amount_cny" type="number" step="0.01" defaultValue={0} />
          </label>
          <label className="block">
            <div className="mb-2 text-[12px] text-ink/65">归属资产（可空=组合层）</div>
            <select className="pp-select" name="asset_id" defaultValue="">
              <option value="">（组合层）</option>
              {assetOptions.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block md:col-span-2">
            <div className="mb-2 text-[12px] text-ink/65">备注（可空）</div>
            <input className="pp-input" name="note" placeholder="例如：定投/加仓" />
          </label>
          <div className="flex items-center gap-2 md:col-span-2">
            <button type="submit" className={cn("pp-btn pp-btn-primary", addM.isPending && "opacity-70")} disabled={addM.isPending}>
              {addM.isPending ? "提交中…" : "新增记录"}
            </button>
            <button type="button" className="pp-btn pp-btn-ghost" onClick={() => {
              metricsQ.refetch();
              daysQ.refetch();
            }}>
              刷新
            </button>
          </div>
        </form>
      </Panel>

      <Panel title="单资产收益" hint="若年化显示为 “—”，通常是本金为 0 或缺少现金流。">
        <div className="overflow-x-auto">
          <div className="min-w-[820px]">
            <div className="grid grid-cols-[1.3fr_.55fr_.55fr_.55fr_.45fr] gap-2 border-b border-ink/10 pb-2 text-[11px] uppercase tracking-widest text-ink/45">
              <div>资产</div>
              <div className="text-right">本金</div>
              <div className="text-right">当前市值</div>
              <div className="text-right">收益</div>
              <div className="text-right">年化</div>
            </div>
            <div className="divide-y divide-ink/10">
              {(metricsQ.data?.per_asset || []).map((a) => {
                const p = Number(a.profit || 0);
                const x = a.xirr_annual == null ? null : Number(a.xirr_annual) * 100;
                return (
                  <div key={a.id} className="grid grid-cols-[1.3fr_.55fr_.55fr_.55fr_.45fr] gap-2 py-2">
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium">{a.name}</div>
                      <div className="truncate text-[11px] text-ink/55">
                        <span className="pp-mono">{a.kind}</span>
                        <span className="mx-2 text-ink/35">·</span>
                        <span className="pp-mono">{a.code}</span>
                      </div>
                    </div>
                    <div className="pp-mono text-right text-[13px]">¥ {fmtCny(a.principal, 2)}</div>
                    <div className="pp-mono text-right text-[13px]">¥ {fmtCny(a.current_value, 2)}</div>
                    <div className={cn("pp-mono text-right text-[13px]", p > 0 && "text-ok", p < 0 && "text-danger")}>
                      ¥ {fmtSignedCny(p, 2)}
                    </div>
                    <div className="pp-mono text-right text-[13px]">{x == null ? "—" : fmtPct(x, 2)}</div>
                  </div>
                );
              })}
              {(metricsQ.data?.per_asset || []).length === 0 ? (
                <div className="py-3 text-[13px] text-ink/60">暂无资产。</div>
              ) : null}
            </div>
          </div>
        </div>
      </Panel>

      <Panel
        title="本金记录（按日汇总）"
        hint={
          <>
            以“日期”为卡片汇总；{manage ? "管理模式已开启，可删除明细。" : "可开启管理模式查看/删除明细。"}
          </>
        }
        right={
          <button type="button" className="pp-btn" onClick={() => setManage((v) => !v)}>
            {manage ? "关闭管理" : "开启管理"}
          </button>
        }
      >
        {daysQ.data?.days?.length ? (
          <div className="grid gap-3">
            {daysQ.data.days.map((d) => (
              <details key={d.date} className="rounded-xl border border-ink/10 bg-paper/60">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2.5">
                  <div className="min-w-0">
                    <div className="pp-mono text-[13px] font-semibold">{d.date}</div>
                    <div className="mt-0.5 text-[11px] text-ink/55">
                      投入：¥ <span className="pp-mono">{fmtCny(d.deposit_total, 2)}</span>
                      <span className="mx-2 text-ink/35">·</span>
                      取出：¥ <span className="pp-mono">{fmtCny(d.withdraw_total, 2)}</span>
                      <span className="mx-2 text-ink/35">·</span>
                      本金累计：¥ <span className="pp-mono">{fmtCny(d.running_principal_end, 2)}</span>
                    </div>
                  </div>
                  <div className={cn("pp-mono text-[13px] font-semibold", d.net_total > 0 && "text-danger", d.net_total < 0 && "text-ok")}>
                    ¥ {fmtSignedCny(d.net_total, 2)}
                  </div>
                </summary>
                <div className="border-t border-ink/10 px-3 py-3">
                  <div className="grid gap-2">
                    <div className="grid grid-cols-[1fr_.35fr_.35fr_.35fr] gap-2 border-b border-ink/10 pb-2 text-[11px] uppercase tracking-widest text-ink/45">
                      <div>资金桶</div>
                      <div className="text-right">投入</div>
                      <div className="text-right">取出</div>
                      <div className="text-right">净投入</div>
                    </div>
                    {[...d.buckets, { id: "other", name: "未归属（组合层/未分配）", ...d.other } as any].map((b: any) => (
                      <div key={b.id} className="grid grid-cols-[1fr_.35fr_.35fr_.35fr] gap-3 py-2">
                        <div className="text-[13px]">{b.name}</div>
                        <div className="pp-mono text-right text-[13px]">¥ {fmtCny(b.deposit, 2)}</div>
                        <div className="pp-mono text-right text-[13px]">¥ {fmtCny(b.withdraw, 2)}</div>
                        <div className={cn("pp-mono text-right text-[13px]", b.net > 0 && "text-danger", b.net < 0 && "text-ok")}>
                          ¥ {fmtSignedCny(b.net, 2)}
                        </div>
                      </div>
                    ))}
                  </div>

                  {manage && d.entries?.length ? (
                    <>
                      <Separator />
                      <div className="text-[11px] uppercase tracking-widest text-ink/45">明细</div>
                      <div className="mt-2 grid gap-2">
                        {d.entries.map((e) => (
                          <div key={e.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-ink/10 bg-paper/70 px-3 py-2">
                            <div className="min-w-0">
                              <div className="text-[13px]">
                                <span className="pp-mono">{e.direction}</span>
                                <span className="mx-2 text-ink/35">·</span>
                                <span className="pp-mono">¥ {fmtCny(e.amount_cny, 2)}</span>
                                <span className="mx-2 text-ink/35">·</span>
                                <span className="text-ink/75">{e.asset_name}</span>
                              </div>
                              {e.note ? <div className="mt-0.5 text-[11px] text-ink/55">{e.note}</div> : null}
                            </div>
                            <button
                              type="button"
                              className="pp-btn"
                              onClick={() => {
                                if (!confirm("确定删除该记录？")) return;
                                delM.mutate(e.id);
                              }}
                            >
                              删除
                            </button>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : null}
                </div>
              </details>
            ))}
          </div>
        ) : (
          <div className="text-[13px] text-ink/60">暂无记录。</div>
        )}
      </Panel>
    </div>
  );
}
