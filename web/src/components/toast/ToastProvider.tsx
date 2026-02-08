"use client";

import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";

import { cn } from "@/lib/cn";

type ToastTone = "info" | "ok" | "warn" | "danger";
type ToastItem = { id: string; tone: ToastTone; title: string; detail?: string; createdAt: number };

type ToastCtx = {
  push: (title: string, opts?: { tone?: ToastTone; detail?: string; ttlMs?: number }) => void;
};

const ToastContext = createContext<ToastCtx | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const push = useCallback((title: string, opts?: { tone?: ToastTone; detail?: string; ttlMs?: number }) => {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const tone = opts?.tone ?? "info";
    const detail = opts?.detail;
    const ttlMs = opts?.ttlMs ?? 2600;
    const toast: ToastItem = { id, tone, title, detail, createdAt: Date.now() };
    setItems((prev) => [toast, ...prev].slice(0, 4));
    window.setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, ttlMs);
  }, []);

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-[min(420px,calc(100vw-2rem))] flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto rounded-2xl border px-4 py-3 shadow-lifted backdrop-blur",
              "bg-paper/85 border-ink/10 text-ink",
              t.tone === "ok" && "border-ok/30",
              t.tone === "warn" && "border-stamp/35",
              t.tone === "danger" && "border-danger/35"
            )}
          >
            <div className="flex items-start gap-3">
              <div
                className={cn(
                  "mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full",
                  t.tone === "info" && "bg-accent",
                  t.tone === "ok" && "bg-ok",
                  t.tone === "warn" && "bg-stamp",
                  t.tone === "danger" && "bg-danger"
                )}
              />
              <div className="min-w-0">
                <div className="text-[13px] font-medium tracking-wide">{t.title}</div>
                {t.detail ? <div className="mt-0.5 text-xs text-ink/70">{t.detail}</div> : null}
              </div>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

