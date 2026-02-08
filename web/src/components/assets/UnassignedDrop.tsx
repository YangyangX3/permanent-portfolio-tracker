"use client";

import { useDroppable } from "@dnd-kit/core";

import { cn } from "@/lib/cn";

export function UnassignedDrop({
  count,
  dragging,
  children
}: {
  count: number;
  dragging: boolean;
  children: React.ReactNode;
}) {
  const { isOver, setNodeRef } = useDroppable({ id: "unassigned" });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        "pp-card border-dashed px-3 py-2.5 transition",
        isOver && "border-ring/45 bg-wash/70 shadow-lifted ring-2 ring-ring/15"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="pp-title text-[13px] font-extrabold">未分配</div>
          <div className="mt-0.5 text-[10.5px] text-ink/55">拖回这里可取消分配（不计入四类桶权重）。</div>
        </div>
        <span className="pp-badge">{dragging && isOver ? "放下" : `${count} 项`}</span>
      </div>
      <div className="mt-2 grid gap-1 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
    </div>
  );
}
