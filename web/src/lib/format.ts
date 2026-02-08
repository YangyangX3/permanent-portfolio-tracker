export function fmtNum(value: unknown, decimals = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n
    .toLocaleString("zh-CN", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    })
    .replace(/(\.\d*?)0+$/, "$1")
    .replace(/\.$/, "");
}

export function fmtCny(value: unknown, decimals = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return fmtNum(n, decimals);
}

export function fmtSignedCny(value: unknown, decimals = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : n < 0 ? "−" : "";
  return `${sign}${fmtNum(Math.abs(n), decimals)}`;
}

export function fmtPct(value: unknown, decimals = 1) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${fmtNum(n, decimals)}%`;
}

export function fmtPrice(value: unknown, kind?: "cn" | "crypto" | "cash") {
  if (kind === "cn") return fmtNum(value, 4);
  if (kind === "crypto") return fmtNum(value, 8);
  if (kind === "cash") return fmtNum(value, 2);
  return fmtNum(value, 6);
}

export function fmtQty(value: unknown, kind?: "cn" | "crypto" | "cash") {
  if (kind === "cn") return fmtNum(value, 4);
  if (kind === "crypto") return fmtNum(value, 8);
  if (kind === "cash") return fmtNum(value, 2);
  return fmtNum(value, 6);
}

export function fmtTimeHms(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (!Number.isFinite(d.getTime())) return iso;
  return d.toLocaleTimeString("zh-CN", { hour12: false });
}
