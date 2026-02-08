"use client";

import { useDraggable } from "@dnd-kit/core";

import { cn } from "@/lib/cn";
import type { PortfolioAsset } from "@/lib/types";

export function AssetChip({ asset }: { asset: PortfolioAsset }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: asset.id,
    data: { assetId: asset.id }
  });

  const style = transform
    ? {
        transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`
      }
    : undefined;

  const label = (asset.name || asset.code || asset.coingecko_id || (asset.kind === "cash" ? "现金" : asset.id)).trim();
  const sub =
    asset.kind === "cn"
      ? asset.code || "CN"
      : asset.kind === "crypto"
        ? asset.coingecko_id || "crypto"
        : "CASH";

  return (
    <div
      ref={setNodeRef}
      style={isDragging ? undefined : style}
      {...listeners}
      {...attributes}
      className={cn(
        "cursor-grab select-none rounded-lg border border-ink/12 bg-paper/70 px-2 py-1 shadow-sm transition",
        "hover:border-ink/25 hover:shadow-md active:cursor-grabbing",
        isDragging && "pointer-events-none opacity-0 ring-2 ring-ring/15 scale-[0.92] transition-[opacity,transform] duration-150 ease-out"
      )}
      title="拖动分配到资产桶"
    >
      <div className="truncate text-[11.5px] font-medium">{label}</div>
      <div className="mt-0.5 truncate text-[10px] text-ink/55">
        <span className="pp-mono">{sub}</span>
      </div>
    </div>
  );
}
