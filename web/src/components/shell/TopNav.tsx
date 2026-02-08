"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";

import { ThemeToggle } from "./ThemeToggle";

const links: Array<{ href: string; label: string }> = [
  { href: "/", label: "概览" },
  { href: "/assets", label: "资产" },
  { href: "/ledger", label: "记账" },
  { href: "/settings", label: "设置" }
];

export function TopNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-ink/10 bg-paper/70 backdrop-blur">
      <div className="mx-auto flex w-full max-w-[1120px] items-center justify-between gap-4 px-3 py-2">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="grid h-8 w-8 place-items-center rounded-xl border border-ink/15 bg-paper shadow-sm">
              <span className="pp-title text-sm font-black tracking-wider">PP</span>
            </div>
          </div>
          <div className="hidden sm:block">
            <div className="pp-title text-sm font-extrabold">永久投资组合</div>
            <div className="text-[11px] text-ink/55">纸感 UI · 同源代理 · 功能等价</div>
          </div>
        </div>

        <nav className="flex items-center gap-1">
          {links.map((l) => {
            const active = pathname === l.href;
            return (
              <Link
                key={l.href}
                href={l.href}
                className={cn(
                  "rounded-lg px-2.5 py-1.5 text-[12px] font-medium transition",
                  active ? "bg-ink text-paper shadow-sm" : "text-ink/75 hover:bg-ink/5"
                )}
              >
                {l.label}
              </Link>
            );
          })}
          <div className="ml-2">
            <ThemeToggle />
          </div>
        </nav>
      </div>
    </header>
  );
}
