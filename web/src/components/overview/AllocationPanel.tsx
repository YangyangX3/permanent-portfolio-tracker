"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { useToast } from "@/components/toast/ToastProvider";
import { cn } from "@/lib/cn";
import { api, type ApiError } from "@/lib/api";
import { fmtCny, fmtPct, fmtQty } from "@/lib/format";
import type { ContributionSuggestion, SettingsPayload, UiState } from "@/lib/types";

type CryptoPrefill = {
  total: number;
  items: Array<{ name: string; amount: number }>;
  prefillAssets: Record<string, number>;
};

function buildAssetMetaById(state: UiState | null) {
  const out: Record<string, { kind: string; source?: string; name?: string }> = {};
  const view = state?.view;
  if (!view) return out;
  const all = [...(view.unassigned || []), ...view.categories.flatMap((c) => c.assets || [])];
  for (const a of all) out[a.id] = { kind: a.kind, source: a.source, name: a.name };
  return out;
}

function collectCryptoPrefill(sug: ContributionSuggestion | null, metaById: Record<string, { kind: string; source?: string; name?: string }>): CryptoPrefill {
  const items: CryptoPrefill["items"] = [];
  const prefillAssets: Record<string, number> = {};
  let total = 0;
  for (const c of sug?.categories || []) {
    for (const a of c.assets || []) {
      const aid = (a.asset_id || "") as string;
      if (!aid) continue;
      const meta = metaById[aid];
      if (!meta || meta.kind !== "crypto") continue;
      const source = String(meta.source || "");
      if (source.includes("manual-quantity")) continue;
      const amt = Number(a.amount_cny || 0);
      if (!Number.isFinite(amt) || amt <= 0) continue;
      total += amt;
      prefillAssets[aid] = (prefillAssets[aid] || 0) + amt;
      items.push({ name: a.name || meta.name || a.code || "—", amount: amt });
    }
  }
  return { total, items, prefillAssets };
}

function readSlipPct(settings: SettingsPayload | null): number {
  const ov = settings?.override as any;
  if (ov && ov.crypto_slip_pct != null) {
    const n = Number(ov.crypto_slip_pct);
    if (Number.isFinite(n)) return Math.max(0, Math.min(20, n));
  }
  const eff = settings?.effective as any;
  const v = eff?.crypto_slip_pct;
  const n = Number(v);
  if (Number.isFinite(n)) return Math.max(0, Math.min(20, n));
  return 1.0;
}

export function AllocationPanel({
  state,
  onApplied
}: {
  state: UiState | null;
  onApplied?: () => void;
}) {
  const toast = useToast();
  const metaById = useMemo(() => buildAssetMetaById(state), [state]);
  const [contribution, setContribution] = useState<string>("");
  const [suggestion, setSuggestion] = useState<ContributionSuggestion | null>(null);
  const [cryptoBaseline, setCryptoBaseline] = useState<Record<string, number> | null>(null);
  const [expectedCrypto, setExpectedCrypto] = useState<Record<string, number> | null>(null);
  const [prefillAssets, setPrefillAssets] = useState<Record<string, number> | null>(null);
  const [contributionTotal, setContributionTotal] = useState<number | null>(null);
  const [contributionRemaining, setContributionRemaining] = useState<number | null>(null);

  const settingsQ = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<SettingsPayload>("/api/v2/settings"),
    staleTime: 60_000
  });

  const suggestM = useMutation({
    mutationFn: async (amt: number) => {
      const params = new URLSearchParams();
      params.set("contribution", String(amt));
      if (prefillAssets && Object.keys(prefillAssets).length > 0) params.set("prefill", JSON.stringify(prefillAssets));
      const sug = await api.get<ContributionSuggestion>(`/api/v2/allocation/suggest?${params.toString()}`);
      return sug;
    },
    onSuccess: async (sug, amt) => {
      setSuggestion(sug);
      setContributionTotal(amt as any);
      setContributionRemaining(amt as any);
      const cryptoInfo = collectCryptoPrefill(sug, metaById);
      const prefillSum = prefillAssets ? Object.values(prefillAssets).reduce((sum, v) => sum + (Number(v) || 0), 0) : 0;
      if (prefillSum <= 0) setExpectedCrypto(cryptoInfo.total > 0 ? cryptoInfo.prefillAssets : null);

      try {
        const snap = await api.get<{ ok: boolean; assets?: Record<string, number> }>("/api/v2/crypto/snapshot");
        setCryptoBaseline((snap && snap.assets) || {});
      } catch {
        setCryptoBaseline(null);
      }
    },
    onError: () => toast.push("计算建议失败", { tone: "danger" })
  });

  const confirmCryptoM = useMutation({
    mutationFn: async () => {
      const baseAmount = Number(contributionTotal ?? contribution ?? 0);
      if (!Number.isFinite(baseAmount) || baseAmount <= 0) throw new Error("invalid amount");
      if (!cryptoBaseline) throw new Error("missing baseline");
      if (!expectedCrypto || Object.keys(expectedCrypto).length === 0) throw new Error("missing expected");
      const baselineParam = encodeURIComponent(JSON.stringify(cryptoBaseline || {}));
      const expectedParam = encodeURIComponent(JSON.stringify(expectedCrypto || {}));
      const slipPct = readSlipPct(settingsQ.data ?? null);
      return api.get<ContributionSuggestion>(
        `/api/v2/allocation/suggest-after-crypto?contribution=${encodeURIComponent(String(baseAmount))}&baseline=${baselineParam}&expected=${expectedParam}&slip_pct=${encodeURIComponent(String(slipPct))}`
      );
    },
    onSuccess: (sug) => {
      const pa = (sug && (sug as any).prefill_assets) || {};
      const remaining = Number((sug as any).contribution_remaining);
      setSuggestion(sug);
      setPrefillAssets(pa && Object.keys(pa).length ? pa : null);
      setContributionRemaining(Number.isFinite(remaining) ? remaining : contributionRemaining);
    },
    onError: (e: any) => {
      const msg = e?.message || "链上确认失败";
      toast.push("链上确认失败", { tone: "danger", detail: msg });
    }
  });

  const applyM = useMutation({
    mutationFn: async () => {
      const amt = Number(contributionRemaining ?? contributionTotal ?? contribution ?? 0);
      if (!Number.isFinite(amt) || amt <= 0) throw new Error("请输入新增资金");
      const payload: any = { contribution: amt };
      if (prefillAssets && Object.keys(prefillAssets).length > 0) payload.prefill_assets = prefillAssets;
      return api.post<any>("/api/v2/allocation/apply", payload);
    },
    onSuccess: (r) => {
      const a = (r && r.applied) || {};
      toast.push("已应用到持仓", {
        tone: "ok",
        detail: `cn=${a.cn || 0} cash=${a.cash || 0} crypto(手动)=${a.crypto_manual || 0} crypto(钱包)=${a.crypto_ledger || 0} skipped=${a.skipped || 0}`
      });
      setSuggestion(null);
      setContribution("");
      setContributionTotal(null);
      setContributionRemaining(null);
      setPrefillAssets(null);
      setCryptoBaseline(null);
      setExpectedCrypto(null);
      onApplied?.();
    },
    onError: (e: any) => {
      const detail = (e as ApiError)?.message || String(e?.message || "");
      toast.push("应用失败", { tone: "danger", detail });
    }
  });

  const cryptoInfo = useMemo(() => collectCryptoPrefill(suggestion, metaById), [suggestion, metaById]);
  const prefillSum = prefillAssets ? Object.values(prefillAssets).reduce((sum, v) => sum + (Number(v) || 0), 0) : 0;

  const showSuggest = () => {
    const amt = Number(contribution || 0);
    if (!Number.isFinite(amt) || amt <= 0) {
      toast.push("请输入新增资金", { tone: "warn" });
      return;
    }
    suggestM.mutate(amt);
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
        <label className="block">
          <div className="mb-2 text-[12px] text-ink/65">新增资金（CNY）</div>
          <input className="pp-input pp-mono" inputMode="decimal" value={contribution} onChange={(e) => setContribution(e.target.value)} placeholder="例如 10000" />
        </label>
        <div className="flex gap-2">
          <button type="button" className={cn("pp-btn pp-btn-primary", suggestM.isPending && "opacity-70")} onClick={showSuggest} disabled={suggestM.isPending}>
            {suggestM.isPending ? "计算中…" : "计算建议"}
          </button>
          <button
            type="button"
            className="pp-btn pp-btn-ghost"
            onClick={() => {
              setContribution("");
              setSuggestion(null);
              setContributionTotal(null);
              setContributionRemaining(null);
              setPrefillAssets(null);
              setCryptoBaseline(null);
              setExpectedCrypto(null);
            }}
          >
            清空
          </button>
        </div>
      </div>

      {suggestion ? (
        <div className="space-y-3">
          {prefillSum > 0 ? (
            <div className="rounded-2xl border border-ink/10 bg-wash/50 px-4 py-3 text-[13px] text-ink/70">
              已扣除链上资产 <span className="pp-mono">¥ {fmtCny(prefillSum, 2)}</span>，按剩余金额{" "}
              <span className="pp-mono">¥ {fmtCny(contributionRemaining, 2)}</span> 建议分配其他资产。
            </div>
          ) : cryptoInfo.total > 0 ? (
            <div className="rounded-2xl border border-stamp/35 bg-stamp/5 px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="pp-title text-[13px] font-extrabold text-stamp">
                    链上资产建议分配：<span className="pp-mono">¥ {fmtCny(cryptoInfo.total, 2)}</span>
                  </div>
                  <div className="mt-1 text-[12px] text-ink/65">
                    明细：{cryptoInfo.items.map((i) => `${i.name} ¥${fmtCny(i.amount, 2)}`).join("；")}
                  </div>
                </div>
                <button
                  type="button"
                  className={cn("pp-btn", confirmCryptoM.isPending && "opacity-70")}
                  onClick={() => confirmCryptoM.mutate()}
                  disabled={confirmCryptoM.isPending}
                  title={cryptoBaseline ? "将读取链上余额变化并重新计算" : "缺少链上快照，需先计算建议"}
                >
                  {confirmCryptoM.isPending ? "重新计算中…" : "我已完成链上分配，按剩余金额重算"}
                </button>
              </div>
              <div className="mt-2 text-[11px] text-ink/55">
                滑点容忍：<span className="pp-mono">{fmtPct(readSlipPct(settingsQ.data ?? null), 2)}</span>（可在设置中调整）
              </div>
            </div>
          ) : null}

          {suggestion.note ? <div className="text-[12px] text-ink/65">{suggestion.note}</div> : null}

          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] uppercase tracking-widest text-ink/45">建议分配（按四类桶）</div>
            <button type="button" className={cn("pp-btn pp-btn-primary", applyM.isPending && "opacity-70")} disabled={applyM.isPending} onClick={() => applyM.mutate()}>
              {applyM.isPending ? "应用中…" : "一键应用到持仓"}
            </button>
          </div>

          <div className="overflow-x-auto rounded-xl border border-ink/10 bg-paper/60">
            <div className="min-w-[860px]">
              <div className="grid grid-cols-[1.2fr_.45fr_.55fr_.55fr_.55fr] gap-2 border-b border-ink/10 px-3 py-1.5 text-[11px] uppercase tracking-widest text-ink/45">
                <div>资产桶</div>
                <div className="text-right">当前占比</div>
                <div className="text-right">建议投入</div>
                <div className="text-right">投入后占比</div>
                <div className="text-right">投入后目标值</div>
              </div>
              <div className="divide-y divide-ink/10">
                {suggestion.categories.map((c) => (
                  <div key={c.category_id} className="grid grid-cols-[1.2fr_.45fr_.55fr_.55fr_.55fr] gap-2 px-3 py-2">
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium">{c.name || c.category_id}</div>
                      {c.assets && c.assets.length > 0 ? (
                        <div className="mt-1 truncate text-[11px] text-ink/60">
                          建议：
                          {c.assets
                            .map(
                              (a) =>
                                `${a.name || a.code || "—"} ¥${fmtCny(a.amount_cny, 2)}${
                                  a.est_quantity == null ? "" : `（≈${fmtQty(a.est_quantity)})`
                                }`
                            )
                            .join("；")}
                        </div>
                      ) : null}
                    </div>
                    <div className="pp-mono text-right text-[13px]">{fmtPct((Number(c.current_weight) || 0) * 100, 1)}</div>
                    <div className="pp-mono text-right text-[13px]">¥ {fmtCny(c.allocate_amount, 2)}</div>
                    <div className="pp-mono text-right text-[13px]">{fmtPct((Number(c.weight_after) || 0) * 100, 1)}</div>
                    <div className="pp-mono text-right text-[13px]">¥ {fmtCny(c.target_value_after, 2)}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
