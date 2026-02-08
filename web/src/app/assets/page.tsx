"use client";

import {
  type CollisionDetection,
  DndContext,
  DragOverlay,
  type Modifier,
  PointerSensor,
  closestCenter,
  pointerWithin,
  useSensor,
  useSensors
} from "@dnd-kit/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { getEventCoordinates } from "@dnd-kit/utilities";

import { AssetChip } from "@/components/assets/AssetChip";
import { AssetDragCursor } from "@/components/assets/AssetDragCursor";
import { BucketDrop } from "@/components/assets/BucketDrop";
import { UnassignedDrop } from "@/components/assets/UnassignedDrop";
import { useToast } from "@/components/toast/ToastProvider";
import { Panel } from "@/components/ui/Panel";
import { api, type ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { Category, PortfolioAsset, UiState } from "@/lib/types";

const EMPTY_CATEGORIES: Category[] = [];
const EMPTY_ASSETS: PortfolioAsset[] = [];

function labelOf(a: PortfolioAsset) {
  return (a.name || a.code || a.coingecko_id || (a.kind === "cash" ? "现金" : a.id)).trim();
}

export default function AssetsPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const [manage, setManage] = useState(false);
  const [dirtyById, setDirtyById] = useState<Record<string, Partial<PortfolioAsset>>>({});
  const [activeAssetId, setActiveAssetId] = useState<string | null>(null);

  const stateQ = useQuery({
    queryKey: ["state"],
    queryFn: () => api.get<UiState>("/api/v2/state"),
    refetchInterval: 20_000
  });

  const portfolio = stateQ.data?.portfolio;
  const categories = portfolio?.categories ?? EMPTY_CATEGORIES;
  const assets = portfolio?.assets ?? EMPTY_ASSETS;

  const byCategory = useMemo(() => {
    const map: Record<string, PortfolioAsset[]> = {};
    for (const c of categories) map[c.id] = [];
    const unassigned: PortfolioAsset[] = [];
    for (const a of assets) {
      const cid = (a.category_id || "").trim();
      if (cid && map[cid]) map[cid].push(a);
      else unassigned.push(a);
    }
    for (const k of Object.keys(map)) map[k].sort((x, y) => labelOf(x).localeCompare(labelOf(y), "zh-CN"));
    unassigned.sort((x, y) => labelOf(x).localeCompare(labelOf(y), "zh-CN"));
    return { map, unassigned };
  }, [assets, categories]);

  const moveM = useMutation({
    mutationFn: async (vars: { assetId: string; categoryId: string | null; targetName?: string }) => {
      const { assetId, categoryId } = vars;
      return api.post("/api/v2/assets/" + encodeURIComponent(assetId) + "/move", { category_id: categoryId });
    },
    onSuccess: (_r, vars) => {
      stateQ.refetch();
      const target = String(vars.targetName || "").trim();
      toast.push(target ? `已移动到 ${target}` : "已保存分配", { tone: "ok" });
    },
    onError: (e: any) => {
      toast.push("保存失败", { tone: "danger", detail: (e as ApiError)?.message || "" });
      stateQ.refetch();
    }
  });

  const createM = useMutation({
    mutationFn: async (payload: any) => api.post<{ ok: boolean; asset: PortfolioAsset }>("/api/v2/assets", payload),
    onSuccess: () => {
      toast.push("已添加", { tone: "ok" });
      stateQ.refetch();
    },
    onError: (e: any) => toast.push("添加失败", { tone: "danger", detail: (e as ApiError)?.message || "" })
  });

  const deleteM = useMutation({
    mutationFn: async (assetId: string) => api.del(`/api/v2/assets/${encodeURIComponent(assetId)}`),
    onSuccess: () => {
      toast.push("已删除", { tone: "ok" });
      stateQ.refetch();
    },
    onError: (e: any) => toast.push("删除失败", { tone: "danger", detail: (e as ApiError)?.message || "" })
  });

  const saveAllM = useMutation({
    mutationFn: async () => {
      const items = Object.entries(dirtyById).map(([asset_id, patch]) => ({ asset_id, ...patch }));
      if (items.length <= 0) return { ok: true, updated: [] as string[] };
      return api.post<{ ok: boolean; updated: string[]; not_found: string[] }>("/api/v2/assets/batch", items);
    },
    onSuccess: (r) => {
      const n = (r && (r as any).updated && (r as any).updated.length) || 0;
      toast.push(n > 0 ? `已保存 ${n} 项` : "没有需要保存的修改", { tone: "ok" });
      setDirtyById({});
      stateQ.refetch();
    },
    onError: (e: any) => toast.push("保存失败", { tone: "danger", detail: (e as ApiError)?.message || "" })
  });

  const onDragEnd = (ev: any) => {
    const overId = ev?.over?.id as string | undefined;
    const activeId = ev?.active?.id as string | undefined;
    setActiveAssetId(null);
    if (!overId || !activeId) return;
    const assetId = String(activeId);
    const categoryId = overId === "unassigned" ? null : String(overId);

    const cur = assets.find((a) => a.id === assetId);
    const curCat = (cur?.category_id || "").trim() || null;
    if (curCat === categoryId) return;

    const targetName =
      categoryId == null ? "未分配" : categories.find((c) => String(c.id) === String(categoryId))?.name || String(categoryId);

    // Optimistic update (portfolio only).
    qc.setQueryData(["state"], (prev: any) => {
      if (!prev || !prev.portfolio || !Array.isArray(prev.portfolio.assets)) return prev;
      const next = structuredClone(prev);
      for (const a of next.portfolio.assets) {
        if (a.id === assetId) a.category_id = categoryId;
      }
      return next;
    });
    moveM.mutate({ assetId, categoryId, targetName });
  };

  const collisionDetection: CollisionDetection = (args) => {
    const byPointer = pointerWithin(args);
    if (byPointer.length) return byPointer;
    return closestCenter(args);
  };

  const snapOverlayCenterToCursor: Modifier = ({ activatorEvent, draggingNodeRect, overlayNodeRect, transform }) => {
    if (!draggingNodeRect || !overlayNodeRect || !activatorEvent) return transform;
    const coords = getEventCoordinates(activatorEvent);
    if (!coords) return transform;

    const offsetX = coords.x - draggingNodeRect.left;
    const offsetY = coords.y - draggingNodeRect.top;

    return {
      ...transform,
      x: transform.x + offsetX - overlayNodeRect.width / 2,
      y: transform.y + offsetY - overlayNodeRect.height / 2
    };
  };

  const cursorAvoidOffset: Modifier = ({ transform, draggingNodeRect, overlayNodeRect, windowRect }) => {
    if (!draggingNodeRect || !windowRect) return transform;

    const halfW = (overlayNodeRect?.width ?? 36) / 2;
    const halfH = (overlayNodeRect?.height ?? 36) / 2;

    // After `snapOverlayCenterToCursor`, overlay center is at cursor + transform.
    const cursorX = draggingNodeRect.left + transform.x + halfW;
    const cursorY = draggingNodeRect.top + transform.y + halfH;

    const pad = 10;
    const base = 12;

    let dx = base + halfW * 0.2;
    let dy = base + halfH * 0.2;

    const leftBound = windowRect.left + pad + halfW;
    const rightBound = windowRect.left + windowRect.width - pad - halfW;
    const topBound = windowRect.top + pad + halfH;
    const bottomBound = windowRect.top + windowRect.height - pad - halfH;

    if (cursorX + dx > rightBound) dx = -dx;
    if (cursorX + dx < leftBound) dx = Math.abs(dx);
    if (cursorY + dy > bottomBound) dy = -dy;
    if (cursorY + dy < topBound) dy = Math.abs(dy);

    return { ...transform, x: transform.x + dx, y: transform.y + dy };
  };

  const activeAsset = useMemo(() => {
    if (!activeAssetId) return null;
    return assets.find((a) => a.id === activeAssetId) || null;
  }, [activeAssetId, assets]);

  const activeLabel = activeAsset ? labelOf(activeAsset) : "";
  const activeKind = activeAsset ? activeAsset.kind : "cn";

  const dirtyCount = Object.keys(dirtyById).length;
  const dragging = activeAssetId != null;

  return (
    <div className="space-y-4">
      <Panel
        title="拖动分配（四类资产桶）"
        hint="把资产拖到对应桶里即可；该操作会立即保存（调用 /api/v2/assets/{id}/move）。"
        right={
          <>
            <button type="button" className="pp-btn pp-btn-ghost" onClick={() => stateQ.refetch()}>
              刷新
            </button>
            <button type="button" className="pp-btn" onClick={() => setManage((v) => !v)}>
              {manage ? "关闭管理" : "开启管理"}
            </button>
          </>
        }
      >
        {!portfolio ? (
          <div className="text-[13px] text-ink/60">加载中…</div>
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={collisionDetection}
            onDragStart={(ev) => setActiveAssetId(String(ev?.active?.id || "") || null)}
            onDragCancel={() => setActiveAssetId(null)}
            onDragEnd={onDragEnd}
          >
            <div className="grid gap-2 lg:grid-cols-2">
              {categories.map((c) => (
                <BucketDrop
                  key={c.id}
                  category={c as Category}
                  count={(byCategory.map[c.id] || []).length}
                  dragging={dragging}
                >
                  {(byCategory.map[c.id] || []).length ? (
                    (byCategory.map[c.id] || []).map((a) => <AssetChip key={a.id} asset={a} />)
                  ) : (
                    <div className="rounded-lg border border-ink/10 bg-paper/60 px-2.5 py-1.5 text-[11.5px] text-ink/55">
                      拖动资产到这里
                    </div>
                  )}
                </BucketDrop>
              ))}
            </div>
            <div className="mt-2.5">
              <UnassignedDrop count={byCategory.unassigned.length} dragging={dragging}>
                {byCategory.unassigned.length ? (
                  byCategory.unassigned.map((a) => <AssetChip key={a.id} asset={a} />)
                ) : (
                  <div className="rounded-lg border border-ink/10 bg-paper/60 px-2.5 py-1.5 text-[11.5px] text-ink/55">
                    当前没有未分配资产
                  </div>
                )}
              </UnassignedDrop>
            </div>

            <DragOverlay dropAnimation={null} modifiers={[snapOverlayCenterToCursor, cursorAvoidOffset]}>
              {activeAsset ? <AssetDragCursor label={activeLabel} kind={activeKind} /> : null}
            </DragOverlay>
          </DndContext>
        )}
      </Panel>

      <Panel title="新增资产" hint="支持中国标的 / 链上资产 / 现金。创建后可再拖动分配到四类桶。">
        <div className="grid gap-3 lg:grid-cols-3">
          <div className="rounded-xl border border-ink/10 bg-paper/60 p-3">
            <div className="pp-title text-sm font-extrabold">中国 ETF/股票</div>
            <form
              className="mt-3 grid gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                createM.mutate({
                  kind: "cn",
                  code: String(fd.get("code") || "").trim(),
                  name: String(fd.get("name") || "").trim(),
                  quantity: Number(fd.get("quantity") || 0),
                  category_id: String(fd.get("category_id") || "") || null,
                  bucket_weight: String(fd.get("bucket_weight") || "").trim() || null
                });
                e.currentTarget.reset();
              }}
            >
              <input className="pp-input" name="code" placeholder="510300 / 600519 / 161725" required />
              <input className="pp-input" name="name" placeholder="名称（可空）" />
              <input className="pp-input pp-mono" name="quantity" type="number" step="0.0001" defaultValue={0} />
              <select className="pp-select" name="category_id" defaultValue="">
                <option value="">未分配</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <input className="pp-input" name="bucket_weight" placeholder="桶内占比（0~100，可空）" />
              <button type="submit" className={cn("pp-btn pp-btn-primary", createM.isPending && "opacity-70")} disabled={createM.isPending}>
                {createM.isPending ? "添加中…" : "添加"}
              </button>
            </form>
          </div>

          <div className="rounded-xl border border-ink/10 bg-paper/60 p-3">
            <div className="pp-title text-sm font-extrabold">链上/加密资产</div>
            <form
              className="mt-3 grid gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                createM.mutate({
                  kind: "crypto",
                  name: String(fd.get("name") || "").trim(),
                  chain: String(fd.get("chain") || "").trim().toLowerCase(),
                  wallet: String(fd.get("wallet") || "").trim() || null,
                  token_address: String(fd.get("token_address") || "").trim() || null,
                  manual_quantity: String(fd.get("manual_quantity") || "").trim() || null,
                  coingecko_id: String(fd.get("coingecko_id") || "").trim().toLowerCase(),
                  category_id: String(fd.get("category_id") || "") || null,
                  bucket_weight: String(fd.get("bucket_weight") || "").trim() || null
                });
                e.currentTarget.reset();
              }}
            >
              <input className="pp-input" name="name" placeholder="名称（可空）" />
              <input className="pp-input" name="chain" placeholder="链（eth / solana / bsc ...）" required />
              <input className="pp-input" name="wallet" placeholder="钱包地址（可空；留空=手动数量）" />
              <input className="pp-input" name="token_address" placeholder="代币地址（可空=原生币）" />
              <input className="pp-input pp-mono" name="manual_quantity" placeholder="手动数量（可空）" />
              <input className="pp-input" name="coingecko_id" placeholder="coingecko_id（ethereum / tether ...）" required />
              <select className="pp-select" name="category_id" defaultValue="">
                <option value="">未分配</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <input className="pp-input" name="bucket_weight" placeholder="桶内占比（0~100，可空）" />
              <button type="submit" className={cn("pp-btn pp-btn-primary", createM.isPending && "opacity-70")} disabled={createM.isPending}>
                {createM.isPending ? "添加中…" : "添加"}
              </button>
            </form>
          </div>

          <div className="rounded-xl border border-ink/10 bg-paper/60 p-3">
            <div className="pp-title text-sm font-extrabold">现金</div>
            <form
              className="mt-3 grid gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                createM.mutate({
                  kind: "cash",
                  name: String(fd.get("name") || "现金").trim() || "现金",
                  cash_amount_cny: Number(fd.get("cash_amount_cny") || 0),
                  category_id: String(fd.get("category_id") || "cash") || "cash",
                  bucket_weight: String(fd.get("bucket_weight") || "").trim() || null
                });
                e.currentTarget.reset();
              }}
            >
              <input className="pp-input" name="name" defaultValue="现金" />
              <input className="pp-input pp-mono" name="cash_amount_cny" type="number" step="0.01" defaultValue={0} />
              <select className="pp-select" name="category_id" defaultValue="cash">
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <input className="pp-input" name="bucket_weight" placeholder="桶内占比（0~100，可空）" />
              <button type="submit" className={cn("pp-btn pp-btn-primary", createM.isPending && "opacity-70")} disabled={createM.isPending}>
                {createM.isPending ? "添加中…" : "添加"}
              </button>
            </form>
          </div>
        </div>
      </Panel>

      {manage ? (
        <Panel
          title="管理：编辑 / 删除"
          hint="修改会先进入“待保存”队列；点击“保存全部修改”批量写入（/api/v2/assets/batch）。"
          right={
            <>
              <span className="pp-badge">待保存：{dirtyCount} 项</span>
              <button type="button" className={cn("pp-btn pp-btn-primary", saveAllM.isPending && "opacity-70")} onClick={() => saveAllM.mutate()} disabled={saveAllM.isPending}>
                {saveAllM.isPending ? "保存中…" : "保存全部修改"}
              </button>
            </>
          }
        >
          <div className="grid gap-3">
            {assets.length ? (
              assets
                .slice()
                .sort((a, b) => labelOf(a).localeCompare(labelOf(b), "zh-CN"))
                .map((a) => {
                  const dirty = dirtyById[a.id] || {};
                  const merged = { ...a, ...dirty };
                  const setField = (patch: Partial<PortfolioAsset>) =>
                    setDirtyById((prev) => ({ ...prev, [a.id]: { ...(prev[a.id] || {}), ...patch } }));
                  const changed = Object.keys(dirty).length > 0;
                  const title = labelOf(a);

                  return (
                    <details key={a.id} className={cn("rounded-xl border border-ink/10 bg-paper/60", changed && "border-ring/25")}>
                      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2.5">
                        <div className="min-w-0">
                          <div className="truncate text-[13px] font-medium">{title}</div>
                          <div className="mt-0.5 truncate text-[11px] text-ink/55">
                            <span className="pp-mono">{a.kind}</span>
                            <span className="mx-2 text-ink/35">·</span>
                            分配：<span className="pp-mono">{(merged.category_id as any) || "未分配"}</span>
                            {merged.bucket_weight != null ? (
                              <>
                                <span className="mx-2 text-ink/35">·</span>
                                桶内：<span className="pp-mono">{Number(merged.bucket_weight) > 1 ? merged.bucket_weight : Number(merged.bucket_weight) * 100}%</span>
                              </>
                            ) : null}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {changed ? <span className="pp-stamp">待保存</span> : <span className="pp-badge">已同步</span>}
                          <span className="pp-badge">编辑</span>
                        </div>
                      </summary>
                      <div className="border-t border-ink/10 px-3 py-3">
                        <div className="grid gap-3 md:grid-cols-2">
                          <label className="block">
                            <div className="mb-2 text-[12px] text-ink/65">名称</div>
                            <input className="pp-input" value={String((merged as any).name || "")} onChange={(e) => setField({ name: e.target.value })} />
                          </label>

                          <label className="block">
                            <div className="mb-2 text-[12px] text-ink/65">分配到</div>
                            <select className="pp-select" value={String(merged.category_id || "")} onChange={(e) => setField({ category_id: e.target.value || null })}>
                              <option value="">未分配</option>
                              {categories.map((c) => (
                                <option key={c.id} value={c.id}>
                                  {c.name}
                                </option>
                              ))}
                            </select>
                          </label>

                          <label className="block">
                            <div className="mb-2 text-[12px] text-ink/65">桶内占比（0~100，可空）</div>
                            <input
                              className="pp-input pp-mono"
                              value={merged.bucket_weight == null ? "" : String(Number(merged.bucket_weight) > 1 ? merged.bucket_weight : Number(merged.bucket_weight) * 100)}
                              onChange={(e) => setField({ bucket_weight: e.target.value ? Number(e.target.value) : null })}
                              placeholder="例如 60"
                            />
                          </label>

                          {a.kind === "cn" ? (
                            <>
                              <label className="block">
                                <div className="mb-2 text-[12px] text-ink/65">代码</div>
                                <input className="pp-input pp-mono" value={String((merged as any).code || "")} onChange={(e) => setField({ code: e.target.value })} />
                              </label>
                              <label className="block">
                                <div className="mb-2 text-[12px] text-ink/65">数量</div>
                                <input
                                  className="pp-input pp-mono"
                                  type="number"
                                  step="0.0001"
                                  value={Number((merged as any).quantity || 0)}
                                  onChange={(e) => setField({ quantity: Number(e.target.value || 0) })}
                                />
                              </label>
                            </>
                          ) : null}

                          {a.kind === "crypto" ? (
                            <>
                              <label className="block">
                                <div className="mb-2 text-[12px] text-ink/65">链</div>
                                <input className="pp-input pp-mono" value={String((merged as any).chain || "")} onChange={(e) => setField({ chain: e.target.value })} />
                              </label>
                              <label className="block">
                                <div className="mb-2 text-[12px] text-ink/65">钱包地址</div>
                                <input className="pp-input pp-mono" value={String((merged as any).wallet || "")} onChange={(e) => setField({ wallet: e.target.value || null })} />
                              </label>
                              <label className="block">
                                <div className="mb-2 text-[12px] text-ink/65">代币地址</div>
                                <input
                                  className="pp-input pp-mono"
                                  value={String((merged as any).token_address || "")}
                                  onChange={(e) => setField({ token_address: e.target.value || null })}
                                />
                              </label>
                              <label className="block">
                                <div className="mb-2 text-[12px] text-ink/65">CoinGecko ID</div>
                                <input
                                  className="pp-input pp-mono"
                                  value={String((merged as any).coingecko_id || "")}
                                  onChange={(e) => setField({ coingecko_id: e.target.value })}
                                />
                              </label>
                              <label className="block md:col-span-2">
                                <div className="mb-2 text-[12px] text-ink/65">手动数量（留空=读取钱包余额）</div>
                                <input
                                  className="pp-input pp-mono"
                                  value={(merged as any).manual_quantity == null ? "" : String((merged as any).manual_quantity)}
                                  onChange={(e) => setField({ manual_quantity: e.target.value ? Number(e.target.value) : null })}
                                  placeholder="可空"
                                />
                              </label>
                            </>
                          ) : null}

                          {a.kind === "cash" ? (
                            <label className="block md:col-span-2">
                              <div className="mb-2 text-[12px] text-ink/65">现金金额（CNY）</div>
                              <input
                                className="pp-input pp-mono"
                                type="number"
                                step="0.01"
                                value={Number((merged as any).cash_amount_cny || 0)}
                                onChange={(e) => setField({ cash_amount_cny: Number(e.target.value || 0) })}
                              />
                            </label>
                          ) : null}
                        </div>

                        <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
                          <button
                            type="button"
                            className="pp-btn pp-btn-ghost"
                            onClick={() => setDirtyById((prev) => {
                              const next = { ...prev };
                              delete next[a.id];
                              return next;
                            })}
                            disabled={!changed}
                          >
                            放弃修改
                          </button>
                          <button
                            type="button"
                            className="pp-btn"
                            onClick={() => {
                              if (!confirm("确定删除该资产？")) return;
                              deleteM.mutate(a.id);
                            }}
                          >
                            删除
                          </button>
                        </div>
                      </div>
                    </details>
                  );
                })
            ) : (
              <div className="text-[13px] text-ink/60">暂无资产。</div>
            )}
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
