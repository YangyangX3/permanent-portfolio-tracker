"use client";

import { cn } from "@/lib/cn";
import type { TotalHistoryPoint } from "@/lib/types";

function clamp(n: number, a: number, b: number) {
  return Math.max(a, Math.min(b, n));
}

function pathFromPoints(points: Array<{ x: number; y: number }>) {
  if (points.length <= 0) return "";
  const d: string[] = [];
  d.push(`M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`);
  for (let i = 1; i < points.length; i++) d.push(`L ${points[i].x.toFixed(2)} ${points[i].y.toFixed(2)}`);
  return d.join(" ");
}

export function Sparkline({
  points,
  className,
  tone
}: {
  points: TotalHistoryPoint[];
  className?: string;
  tone?: "accent" | "stamp";
}) {
  const w = 560;
  const h = 120;
  const pad = 8;
  const xs = points.map((p) => Number(p.t));
  const ys = points.map((p) => Number(p.v));
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;

  const plot = points.map((p) => {
    const x = pad + ((p.t - minX) / spanX) * (w - pad * 2);
    const y = pad + (1 - (p.v - minY) / spanY) * (h - pad * 2);
    return { x: clamp(x, pad, w - pad), y: clamp(y, pad, h - pad) };
  });

  const line = pathFromPoints(plot);
  const area = line ? `${line} L ${plot[plot.length - 1].x.toFixed(2)} ${(h - pad).toFixed(2)} L ${plot[0].x.toFixed(2)} ${(h - pad).toFixed(2)} Z` : "";

  const stroke = tone === "stamp" ? "hsl(var(--stamp))" : "hsl(var(--accent))";

  return (
    <svg
      className={cn("h-[120px] w-full", className)}
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="pp-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={stroke} stopOpacity="0.28" />
          <stop offset="1" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#pp-area)" />
      <path d={line} fill="none" stroke={stroke} strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

