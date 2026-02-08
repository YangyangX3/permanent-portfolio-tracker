"use client";

import { useDroppable } from "@dnd-kit/core";

import { cn } from "@/lib/cn";
import type { Category } from "@/lib/types";

export function BucketDrop({
  category,
  count,
  dragging,
  children
}: {
  category: Category;
  count: number;
  dragging: boolean;
  children: React.ReactNode;
}) {
  const { isOver, setNodeRef } = useDroppable({ id: category.id });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        "pp-card min-h-[132px] px-3 py-2.5 transition",
        isOver && "border-ring/45 bg-wash/70 shadow-lifted ring-2 ring-ring/15"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="pp-title text-[13px] font-extrabold">{category.name}</div>
          <div className="mt-0.5 text-[10.5px] text-ink/55">
            目标 <span className="pp-mono">{Math.round((category.target_weight || 0) * 100)}%</span> · 阈值{" "}
            <span className="pp-mono">
              {Math.round((category.min_weight || 0) * 100)}~{Math.round((category.max_weight || 0) * 100)}%
            </span>
          </div>
        </div>
        <span className="pp-badge">{dragging && isOver ? "放下" : `${count} 项`}</span>
      </div>
      <div className="mt-2 grid gap-1">{children}</div>
    </div>
  );
}
