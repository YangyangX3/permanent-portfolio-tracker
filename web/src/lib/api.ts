export type ApiError = {
  status: number;
  message: string;
  body?: unknown;
};

function withTimeout(signal: AbortSignal | null | undefined, timeoutMs: number) {
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  signal?.addEventListener("abort", onAbort, { once: true });
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
    }
  };
}

async function parseJsonSafe(res: Response) {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function apiFetch<T>(
  input: RequestInfo | URL,
  init?: RequestInit & { timeoutMs?: number }
): Promise<T> {
  const timeoutMs = init?.timeoutMs ?? 15000;
  const { signal, cleanup } = withTimeout(init?.signal, timeoutMs);
  try {
    const res = await fetch(input, {
      ...init,
      signal,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {})
      }
    });
    if (!res.ok) {
      const body = await parseJsonSafe(res);
      const message =
        typeof body === "string"
          ? body
          : (body && typeof body === "object" && "error" in (body as any) && String((body as any).error)) ||
            res.statusText ||
            "Request failed";
      throw { status: res.status, message, body } satisfies ApiError;
    }
    const data = (await parseJsonSafe(res)) as T;
    return data;
  } finally {
    cleanup();
  }
}

export const api = {
  get: <T>(url: string, init?: RequestInit & { timeoutMs?: number }) => apiFetch<T>(url, { ...init, method: "GET" }),
  post: <T>(url: string, body?: unknown, init?: RequestInit & { timeoutMs?: number }) =>
    apiFetch<T>(url, { ...init, method: "POST", body: body == null ? undefined : JSON.stringify(body) }),
  patch: <T>(url: string, body?: unknown, init?: RequestInit & { timeoutMs?: number }) =>
    apiFetch<T>(url, { ...init, method: "PATCH", body: body == null ? undefined : JSON.stringify(body) }),
  del: <T>(url: string, init?: RequestInit & { timeoutMs?: number }) => apiFetch<T>(url, { ...init, method: "DELETE" })
};
