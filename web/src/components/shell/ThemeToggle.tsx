"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";

function Icon({ name }: { name: "sun" | "moon" | "system" }) {
  const common = "h-4 w-4";
  if (name === "moon")
    return (
      <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M21 14.5A8.5 8.5 0 0 1 9.5 3a7 7 0 1 0 11.5 11.5Z" />
      </svg>
    );
  if (name === "sun")
    return (
      <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12Z" />
        <path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5 5l1.5 1.5M18.5 18.5 20 20M19 5l-1.5 1.5M6.5 18.5 5 20" />
      </svg>
    );
  return (
    <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M4 6h16M7 12h10M10 18h4" />
    </svg>
  );
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const current = mounted ? theme : "system";

  const cycle = () => {
    if (current === "light") return setTheme("dark");
    if (current === "dark") return setTheme("system");
    return setTheme("light");
  };

  const label = current === "light" ? "浅" : current === "dark" ? "深" : "随";
  const icon = current === "light" ? "sun" : current === "dark" ? "moon" : "system";

  return (
    <button type="button" onClick={cycle} className={cn("pp-btn pp-btn-ghost gap-2")} aria-label="切换主题">
      <Icon name={icon as any} />
      <span className="pp-mono text-[12px]">{label}</span>
    </button>
  );
}

