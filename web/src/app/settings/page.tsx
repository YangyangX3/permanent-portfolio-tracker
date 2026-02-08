"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { useToast } from "@/components/toast/ToastProvider";
import { Panel } from "@/components/ui/Panel";
import { Separator } from "@/components/ui/Separator";
import { api, type ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { fmtPct } from "@/lib/format";
import type { SettingsPayload } from "@/lib/types";

function joinMailTo(v: string[] | null | undefined) {
  if (!v || !Array.isArray(v)) return "";
  return v.join(", ");
}

export default function SettingsPage() {
  const toast = useToast();
  const qc = useQueryClient();

  const settingsQ = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<SettingsPayload>("/api/v2/settings"),
    staleTime: 30_000
  });

  const ov = settingsQ.data?.override;

  const [form, setForm] = useState(() => ({
    email_enabled: false,
    mail_from: "",
    mail_to: "",
    timezone: "",
    daily_job_time: "",
    notify_cooldown_minutes: 360,
    crypto_slip_pct: 1.0,
    smtp_host: "",
    smtp_port: 587,
    smtp_username: "",
    smtp_password: "",
    smtp_use_starttls: true
  }));

  useEffect(() => {
    if (!ov) return;
    setForm((prev) => ({
      ...prev,
      email_enabled: Boolean(ov.email_enabled ?? prev.email_enabled),
      mail_from: String(ov.mail_from ?? ""),
      mail_to: joinMailTo(ov.mail_to),
      timezone: String(ov.timezone ?? ""),
      daily_job_time: String(ov.daily_job_time ?? ""),
      notify_cooldown_minutes: Number(ov.notify_cooldown_minutes ?? prev.notify_cooldown_minutes),
      crypto_slip_pct: Number(ov.crypto_slip_pct ?? prev.crypto_slip_pct),
      smtp_host: String(ov.smtp_host ?? ""),
      smtp_port: Number(ov.smtp_port ?? prev.smtp_port),
      smtp_username: String(ov.smtp_username ?? ""),
      smtp_password: "",
      smtp_use_starttls: Boolean(ov.smtp_use_starttls ?? prev.smtp_use_starttls)
    }));
  }, [ov]);

  const saveM = useMutation({
    mutationFn: async () =>
      api.post<SettingsPayload>("/api/v2/settings", {
        email_enabled: form.email_enabled,
        mail_from: form.mail_from,
        mail_to: form.mail_to,
        timezone: form.timezone,
        daily_job_time: form.daily_job_time,
        notify_cooldown_minutes: Number(form.notify_cooldown_minutes || 1),
        crypto_slip_pct: Number(form.crypto_slip_pct || 0),
        smtp_host: form.smtp_host,
        smtp_port: Number(form.smtp_port || 587),
        smtp_username: form.smtp_username,
        smtp_password: form.smtp_password,
        smtp_use_starttls: form.smtp_use_starttls
      }),
    onSuccess: (payload) => {
      toast.push("已保存设置", { tone: "ok" });
      qc.setQueryData(["settings"], payload);
      setForm((prev) => ({ ...prev, smtp_password: "" }));
    },
    onError: (e: any) => toast.push("保存失败", { tone: "danger", detail: (e as ApiError)?.message || "" })
  });

  const testM = useMutation({
    mutationFn: async () => api.post<{ ok: boolean; sent_any: boolean } | { ok: boolean; error: string }>("/api/v2/settings/test-email", {}),
    onSuccess: (r: any) => {
      if (r && r.ok) {
        toast.push(r.sent_any ? "已发送邮件（至少一封）" : "本次未发送（未到触发条件/冷却中）", { tone: "ok" });
      } else {
        toast.push("发送失败", { tone: "danger", detail: String(r?.error || "") });
      }
    },
    onError: (e: any) => toast.push("发送失败", { tone: "danger", detail: (e as ApiError)?.message || "" })
  });

  const effectiveJson = useMemo(() => {
    const eff = settingsQ.data?.effective;
    try {
      return JSON.stringify(eff || {}, null, 2);
    } catch {
      return String(eff || "");
    }
  }, [settingsQ.data?.effective]);

  return (
    <div className="space-y-4">
      <Panel
        title="邮件提醒"
        hint={
          <>
            SMTP 密码会加密保存到本地文件（`data/app_settings.json` + `data/secret.key`）。任何 API 响应都不会返回明文密码。
          </>
        }
        right={
          <button type="button" className="pp-btn pp-btn-ghost" onClick={() => settingsQ.refetch()}>
            刷新
          </button>
        }
      >
        <form
          className="grid gap-3 md:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            saveM.mutate();
          }}
        >
          <label className="block">
            <div className="mb-2 text-[12px] text-ink/65">开启邮件</div>
            <select className="pp-select" value={form.email_enabled ? "true" : "false"} onChange={(e) => setForm((p) => ({ ...p, email_enabled: e.target.value === "true" }))}>
              <option value="false">false</option>
              <option value="true">true</option>
            </select>
          </label>
          <label className="block">
            <div className="mb-2 text-[12px] text-ink/65">发件人地址（可空）</div>
            <input className="pp-input" value={form.mail_from} onChange={(e) => setForm((p) => ({ ...p, mail_from: e.target.value }))} placeholder="you@example.com" />
          </label>
          <label className="block md:col-span-2">
            <div className="mb-2 text-[12px] text-ink/65">收件人（逗号分隔）</div>
            <input className="pp-input" value={form.mail_to} onChange={(e) => setForm((p) => ({ ...p, mail_to: e.target.value }))} placeholder="a@example.com, b@example.com" />
          </label>

          <label className="block">
            <div className="mb-2 text-[12px] text-ink/65">SMTP 主机</div>
            <input className="pp-input" value={form.smtp_host} onChange={(e) => setForm((p) => ({ ...p, smtp_host: e.target.value }))} placeholder="smtp.qq.com / smtp.gmail.com" />
          </label>
          <label className="block">
            <div className="mb-2 text-[12px] text-ink/65">SMTP 端口</div>
            <input className="pp-input pp-mono" type="number" value={form.smtp_port} onChange={(e) => setForm((p) => ({ ...p, smtp_port: Number(e.target.value || 0) }))} />
          </label>
          <label className="block">
            <div className="mb-2 text-[12px] text-ink/65">SMTP 用户名</div>
            <input className="pp-input" value={form.smtp_username} onChange={(e) => setForm((p) => ({ ...p, smtp_username: e.target.value }))} />
          </label>
          <label className="block">
            <div className="mb-2 text-[12px] text-ink/65">STARTTLS</div>
            <select className="pp-select" value={form.smtp_use_starttls ? "true" : "false"} onChange={(e) => setForm((p) => ({ ...p, smtp_use_starttls: e.target.value === "true" }))}>
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </label>
          <label className="block md:col-span-2">
            <div className="mb-2 flex items-center justify-between gap-2 text-[12px] text-ink/65">
              <span>SMTP 密码/授权码（留空=不修改）</span>
              <span className="pp-badge">已保存：{settingsQ.data?.override?.smtp_password_set ? "是" : "否"}</span>
            </div>
            <input className="pp-input" type="password" value={form.smtp_password} onChange={(e) => setForm((p) => ({ ...p, smtp_password: e.target.value }))} placeholder="留空不修改" />
          </label>

          <Separator />

          <label className="block">
            <div className="mb-2 text-[12px] text-ink/65">时区</div>
            <input className="pp-input pp-mono" value={form.timezone} onChange={(e) => setForm((p) => ({ ...p, timezone: e.target.value }))} placeholder="Asia/Shanghai" />
          </label>
          <label className="block">
            <div className="mb-2 text-[12px] text-ink/65">每天检查时间（HH:MM）</div>
            <input className="pp-input pp-mono" value={form.daily_job_time} onChange={(e) => setForm((p) => ({ ...p, daily_job_time: e.target.value }))} placeholder="09:05" />
          </label>
          <label className="block">
            <div className="mb-2 text-[12px] text-ink/65">阈值邮件冷却（分钟）</div>
            <input className="pp-input pp-mono" type="number" value={form.notify_cooldown_minutes} onChange={(e) => setForm((p) => ({ ...p, notify_cooldown_minutes: Number(e.target.value || 0) }))} />
          </label>
          <label className="block">
            <div className="mb-2 text-[12px] text-ink/65">链上滑点容忍（%）</div>
            <input className="pp-input pp-mono" type="number" step="0.1" value={form.crypto_slip_pct} onChange={(e) => setForm((p) => ({ ...p, crypto_slip_pct: Number(e.target.value || 0) }))} />
            <div className="mt-1 text-[11px] text-ink/55">
              当前值：<span className="pp-mono">{fmtPct(form.crypto_slip_pct, 2)}</span>
            </div>
          </label>

          <div className="flex flex-wrap items-center gap-2 md:col-span-2">
            <button type="submit" className={cn("pp-btn pp-btn-primary", saveM.isPending && "opacity-70")} disabled={saveM.isPending}>
              {saveM.isPending ? "保存中…" : "保存设置"}
            </button>
            <button type="button" className={cn("pp-btn", testM.isPending && "opacity-70")} disabled={testM.isPending} onClick={() => testM.mutate()}>
              {testM.isPending ? "执行中…" : "执行一次检查（可能发邮件）"}
            </button>
          </div>
        </form>
      </Panel>

      <Panel title="当前生效配置（隐藏密码）" hint="用于排查“为什么没发邮件”。">
        <pre className="overflow-x-auto rounded-xl border border-ink/10 bg-paper/60 p-3 text-[12px] text-ink/75">
          <code>{effectiveJson}</code>
        </pre>
      </Panel>
    </div>
  );
}
