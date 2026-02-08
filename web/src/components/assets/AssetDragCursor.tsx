"use client";

import { cn } from "@/lib/cn";

function firstGlyph(text: string) {
  const s = String(text || "").trim();
  if (!s) return "?";
  return Array.from(s)[0] || "?";
}

export function AssetDragCursor({
  label,
  kind,
  className
}: {
  label: string;
  kind: "cn" | "crypto" | "cash" | string;
  className?: string;
}) {
  const glyph = firstGlyph(label);
  const kindTag = kind === "crypto" ? "CR" : kind === "cash" ? "CA" : "CN";

  return (
    <div
      className={cn(
        "pointer-events-none grid h-9 w-9 place-items-center rounded-full border border-ink/25 bg-paper/92 shadow-lifted",
        "ring-1 ring-ink/10",
        className
      )}
    >
      <div className="relative grid h-full w-full place-items-center">
        <div className="pp-title text-[14px] font-black leading-none">{glyph}</div>
        <div className="absolute -bottom-1 -right-1 grid h-4 w-4 place-items-center rounded-full border border-ink/20 bg-paper text-[9px] font-semibold text-ink/70">
          {kindTag}
        </div>
      </div>
    </div>
  );
}

