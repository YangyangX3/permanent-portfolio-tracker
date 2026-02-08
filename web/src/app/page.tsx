"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { Sparkline } from "@/components/chart/Sparkline";
import { AllocationPanel } from "@/components/overview/AllocationPanel";
import { BucketCard } from "@/components/overview/BucketCard";
import { useToast } from "@/components/toast/ToastProvider";
import { Panel } from "@/components/ui/Panel";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { fmtCny, fmtPct, fmtSignedCny, fmtTimeHms } from "@/lib/format";
import type { TotalHistoryPayload, UiState } from "@/lib/types";

function pickTone(changeValue: number) {
  if (!Number.isFinite(changeValue)) return "accent";
  return changeValue >= 0 ? "accent" : "stamp";
}

export default function OverviewPage() {
  const toast = useToast();
  const [chartOpen, setChartOpen] = useState(false);
  const [historyWindow, setHistoryWindow] = useState<"24h" | "7d" | "30d">("24h");

  const stateQ = useQuery({
    queryKey: ["state"],
    queryFn: () => api.get<UiState>("/api/v2/state"),
    refetchInterval: 15_000
  });

  const view = stateQ.data?.view || null;
  const cache = stateQ.data?.cache || null;

  const balanceNeededQ = useQuery({
    queryKey: ["balance-needed"],
    queryFn: () => api.get<{ balance_needed_cny: number }>("/api/v2/rebalance/balance-needed"),
    staleTime: 8_000
  });

  const historyQ = useQuery({
    queryKey: ["total-history", historyWindow],
    queryFn: () =>
      api.get<TotalHistoryPayload>(`/api/total-history?window=${encodeURIComponent(historyWindow)}&max_points=240`),
    enabled: chartOpen,
    staleTime: 10_000
  });

  const hasHistory = chartOpen && !!historyQ.data;
  const changeValue = hasHistory ? historyQ.data!.change_value : null;
  const changePct = hasHistory ? historyQ.data!.change_pct : null;
  const tone = pickTone(Number(changeValue ?? 0));

  const warnings = useMemo(() => (view?.warnings || []).filter(Boolean), [view]);

  return (
    <div className="space-y-3">
      <section className="grid items-start justify-items-stretch gap-2 lg:grid-cols-2 lg:items-stretch">
        <div className="pp-card w-full h-full flex flex-col px-3 py-3">
          <div className="text-[15px] uppercase tracking-[0.22em] text-ink/45">组合总市值（估算）</div>

            <div className="flex flex-1 items-center py-3">
              <div className="flex w-full flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
                <button
                  type="button"
                  className="flex items-baseline gap-2 text-left"
                  onClick={() => setChartOpen((v) => !v)}
                  title="点击展开/收起总资产走势"
                >
                  <div className="pp-title text-4xl font-black leading-none">
                    ¥ <span className="pp-mono">{fmtCny(view?.total_value, 2)}</span>
                  </div>
                </button>
                <div
                  className={cn(
                    "pp-mono text-sm font-semibold whitespace-nowrap",
                    changeValue != null && changeValue > 0 && "text-ok",
                    changeValue != null && changeValue < 0 && "text-danger",
                    changeValue == null && "text-ink/45"
                  )}
                >
                  {chartOpen ? (historyQ.isFetching ? "…" : fmtSignedCny(changeValue, 2)) : "—"}
                  {changePct == null ? null : <span className="ml-2 text-ink/55">({fmtPct(changePct, 2)})</span>}
                </div>
              </div>
            </div>

          <div className="pt-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-ink/60">
              <span>数据时间：{view?.as_of || "—"}</span>
              <span className="text-ink/35">·</span>
              {cache?.updated_at ? (
                <span className="pp-mono text-ink/45">
                  缓存更新：{fmtTimeHms(cache.updated_at)}
                  {cache.last_duration_ms != null ? `（${Math.round(cache.last_duration_ms)}ms）` : ""}
                </span>
              ) : (
                <span>缓存未就绪</span>
              )}
            </div>
            {cache?.last_error ? (
              <div className="mt-3 rounded-xl border border-danger/35 bg-danger/10 px-3 py-2.5 text-[12px] text-danger">
                缓存错误：{cache.last_error}
              </div>
            ) : null}

            {chartOpen ? (
              <div className="mt-3 rounded-xl border border-ink/10 bg-paper/60 p-2.5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-[12px] text-ink/65">
                    窗口：<span className="pp-mono">{historyWindow}</span>
                  </div>
                  <div className="flex gap-2">
                    {(["24h", "7d", "30d"] as const).map((w) => (
                      <button
                        key={w}
                        type="button"
                        className={cn("pp-btn pp-btn-ghost", w === historyWindow && "border-ink/35")}
                        onClick={() => setHistoryWindow(w)}
                      >
                        {w}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="mt-2 text-[11px] text-ink/55">
                  {historyQ.isFetching
                    ? "加载中…"
                    : historyQ.data?.points?.length
                      ? `基准：¥ ${fmtCny(historyQ.data.baseline_value, 2)} → 当前：¥ ${fmtCny(historyQ.data.current_value, 2)}`
                      : "暂无快照数据（snapshots.jsonl）"}
                </div>
                {historyQ.data?.points?.length ? (
                  <Sparkline points={historyQ.data.points} tone={tone as any} className="mt-3" />
                ) : null}
              </div>
            ) : null}
          </div>
        </div>

        <div className="pp-card w-full h-full flex flex-col px-3 py-3">
          <div className="pp-title text-base font-extrabold">再平衡提醒</div>
          <div className="mt-2 text-[12px] text-ink/65">
            规则：每桶目标 25%，默认阈值 15%~35%。
          </div>
          <div className="mt-3 rounded-xl border border-ink/10 bg-paper/60 px-3 py-2.5">
            {warnings.length > 0 ? (
              <ul className="list-disc space-y-1 pl-4 text-[12.5px] text-ink/75">
                {warnings.map((w, i) => (
                  <li key={`${i}-${w}`}>{w}</li>
                ))}
              </ul>
            ) : (
              <div className="text-[13px] text-ok">当前未触发阈值提醒。</div>
            )}
          </div>
          <div className="mt-auto flex flex-wrap gap-2 pt-3">
            <a className="pp-btn" href="/assets">
              去调整资产
            </a>
            <button
              type="button"
              className="pp-btn pp-btn-ghost"
              onClick={() => {
                stateQ.refetch().catch(() => toast.push("刷新失败", { tone: "danger" }));
              }}
            >
              刷新追踪
            </button>
          </div>
        </div>
      </section>

      <Panel
        title="新增资金自动分配"
        hint="输入新增资金（CNY），系统按 4×25% 目标给出“建议分配到四类桶金额”；可一键应用到持仓（并自动记账已应用部分）。"
        right={
          <span className="pp-badge">
            完全平衡所需新增资金：<span className="pp-mono">¥ {fmtCny(balanceNeededQ.data?.balance_needed_cny, 2)}</span>
          </span>
        }
      >
        <AllocationPanel
          state={stateQ.data ?? null}
          onApplied={() => {
            stateQ.refetch();
            balanceNeededQ.refetch();
          }}
        />
      </Panel>

      <Panel
        title="四类资产桶"
        hint={
          <span>
            每桶目标 25%，阈值区间来自配置（`portfolio.json`）。状态为 “超出阈值” 时建议再平衡。
          </span>
        }
      >
        {!view ? (
          <div className="text-[13px] text-ink/60">行情缓存尚未就绪，稍后刷新即可。</div>
        ) : (
          <div className="grid gap-2 lg:grid-cols-2">
            {view.categories.map((c) => (
              <BucketCard key={c.id} c={c} />
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
