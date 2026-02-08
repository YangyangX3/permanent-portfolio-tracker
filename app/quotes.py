from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class Quote:
    code: str
    name: str
    price: float | None
    change_pct: float | None
    as_of: str | None
    source: str
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class _CacheEntry:
    ts: float
    ttl: float
    quote: Quote


class QuoteProvider:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(8.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        self._lock = asyncio.Lock()
        self._cache: dict[str, _CacheEntry] = {}
        self._cg_cache: dict[str, _CacheEntry] = {}

        # TTLs (seconds): keep requests off the critical path; background refresh reads cache.
        self.cn_realtime_ttl_seconds = 4.0  # A股/ETF (Tencent)
        self.cn_fund_ttl_seconds = 45.0  # 基金口径（净值/估值）
        self.coingecko_ttl_seconds = 45.0
        self.error_ttl_seconds = 10.0

    async def close(self) -> None:
        await self._client.aclose()

    def _ttl_for_quote(self, q: Quote) -> float:
        src = (q.source or "").lower()
        if src.endswith("invalid") or src == "unavailable":
            return self.error_ttl_seconds
        if q.price is None and q.change_pct is None:
            return self.error_ttl_seconds
        if src.startswith("tencent"):
            return self.cn_realtime_ttl_seconds
        if src.startswith("eastmoney"):
            return self.cn_fund_ttl_seconds
        if src.startswith("coingecko"):
            return self.coingecko_ttl_seconds
        return self.cn_fund_ttl_seconds

    async def get_quote(self, code: str) -> Quote:
        code = code.strip()
        if not code:
            return Quote(code=code, name="", price=None, change_pct=None, as_of=None, source="invalid")

        now = time.time()
        async with self._lock:
            cached = self._cache.get(code)
            if cached and (now - cached.ts) < cached.ttl:
                return cached.quote

        quote = await self._fetch_quote(code)
        ttl = self._ttl_for_quote(quote)
        async with self._lock:
            self._cache[code] = _CacheEntry(ts=now, ttl=ttl, quote=quote)
        return quote

    async def get_coingecko_market(self, coingecko_id: str) -> Quote:
        coingecko_id = (coingecko_id or "").strip().lower()
        if not coingecko_id:
            return Quote(code=coingecko_id, name="", price=None, change_pct=None, as_of=None, source="coingecko-invalid")

        now = time.time()
        async with self._lock:
            cached = self._cg_cache.get(coingecko_id)
            if cached and (now - cached.ts) < cached.ttl:
                return cached.quote

        q = await _fetch_coingecko_market(self._client, coingecko_id)
        async with self._lock:
            self._cg_cache[coingecko_id] = _CacheEntry(ts=now, ttl=self._ttl_for_quote(q), quote=q)
        return q

    async def get_coingecko_markets_bulk(self, ids: list[str]) -> dict[str, Quote]:
        cleaned = [i.strip().lower() for i in ids if i and i.strip()]
        if not cleaned:
            return {}

        now = time.time()
        out: dict[str, Quote] = {}
        missing: list[str] = []
        async with self._lock:
            for cid in cleaned:
                cached = self._cg_cache.get(cid)
                if cached and (now - cached.ts) < cached.ttl:
                    out[cid] = cached.quote
                else:
                    missing.append(cid)

        # CoinGecko supports comma-separated ids
        if missing:
            fetched = await _fetch_coingecko_markets_bulk(self._client, missing)
            async with self._lock:
                for cid, q in fetched.items():
                    self._cg_cache[cid] = _CacheEntry(ts=now, ttl=self._ttl_for_quote(q), quote=q)
            out.update(fetched)

        # Ensure all requested keys exist
        for cid in cleaned:
            out.setdefault(cid, Quote(code=cid, name="", price=None, change_pct=None, as_of=None, source="coingecko"))
        return out

    async def get_quotes_bulk(self, codes: list[str]) -> dict[str, Quote]:
        cleaned = [c.strip() for c in codes if c and c.strip()]
        if not cleaned:
            return {}
        now = time.time()

        out: dict[str, Quote] = {}
        missing: list[str] = []
        async with self._lock:
            for code in cleaned:
                cached = self._cache.get(code)
                if cached and (now - cached.ts) < cached.ttl:
                    out[code] = cached.quote
                else:
                    missing.append(code)

        # Bulk fetch Tencent for those supported
        sym_map: dict[str, str] = {}
        others: list[str] = []
        for code in missing:
            normalized = code.strip().lower()
            if re.fullmatch(r"(sh|sz|bj)\d{6}", normalized):
                sym_map[normalized] = code
                continue
            sym = _tencent_symbol(code)
            if sym:
                sym_map[sym] = code
            else:
                others.append(code)

        if sym_map:
            fetched_cn = await _fetch_tencent_cn_quotes_bulk(self._client, sym_map)
            out.update(fetched_cn)
            async with self._lock:
                for code, q in fetched_cn.items():
                    self._cache[code] = _CacheEntry(ts=now, ttl=self._ttl_for_quote(q), quote=q)

        # Fallback for remaining codes (fund endpoints, etc.)
        for code in others:
            q = await self._fetch_quote(code)
            out[code] = q
            async with self._lock:
                self._cache[code] = _CacheEntry(ts=now, ttl=self._ttl_for_quote(q), quote=q)

        # If Tencent bulk didn't return (or returned without price), fallback to _fetch_quote
        tencent_missed = [code for code in missing if code not in out or out[code].price is None]
        for code in tencent_missed:
            q = await self._fetch_quote(code)
            out[code] = q
            async with self._lock:
                self._cache[code] = _CacheEntry(ts=now, ttl=self._ttl_for_quote(q), quote=q)

        for code in cleaned:
            out.setdefault(code, Quote(code=code, name="", price=None, change_pct=None, as_of=None, source="unavailable"))
        return out

    async def _fetch_quote(self, code: str) -> Quote:
        normalized = code.strip().lower()
        # 如果用户显式带市场前缀（sh/sz/bj），强制按交易所标的处理，避免“000001”这类冲突代码误判成基金。
        if re.fullmatch(r"(sh|sz|bj)\d{6}", normalized):
            q = await _fetch_tencent_cn_quote(self._client, normalized)
            if q:
                return q
            return Quote(code=code, name="", price=None, change_pct=None, as_of=None, source="unavailable")

        # 6 位数字（无前缀）：优先按交易所行情（ETF/股票更贴近“你看到的实时价格”），失败再按基金口径
        if re.fullmatch(r"\d{6}", code):
            q = await _fetch_tencent_cn_quote(self._client, code)
            if q and q.price is not None:
                return q
            q = await _fetch_eastmoney_fund_estimate(self._client, code)
            if q:
                return q
            q = await _fetch_eastmoney_fund_nav_lsjz(self._client, code)
            if q:
                return q

        q = await _fetch_tencent_cn_quote(self._client, code)
        if q and q.price is not None:
            return q
        return Quote(code=code, name="", price=None, change_pct=None, as_of=None, source="unavailable")


async def _fetch_eastmoney_fund_estimate(client: httpx.AsyncClient, code: str) -> Quote | None:
    # https://fundgz.1234567.com.cn/js/161725.js -> jsonpgz({...});
    url = f"https://fundgz.1234567.com.cn/js/{code}.js"
    try:
        r = await client.get(url)
        if r.status_code != 200:
            return None
        return _parse_eastmoney_fundgz(text=r.text, code=code)
    except Exception:
        return None


def _tencent_symbol(code: str) -> str | None:
    code = code.strip().lower()
    if re.fullmatch(r"(sh|sz|bj)\d{6}", code):
        return code
    if not re.fullmatch(r"\d{6}", code):
        return None
    # 上交所：A 股 6xxxxx；ETF/基金 5xxxxx
    if code.startswith(("6", "5")):
        return f"sh{code}"
    # 深交所：A 股 0/3xxxxx；ETF/LOF 1xxxxx
    if code.startswith(("0", "1", "3")):
        return f"sz{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return None


async def _fetch_tencent_cn_quote(client: httpx.AsyncClient, code: str) -> Quote | None:
    sym = _tencent_symbol(code)
    if not sym:
        return None

    # 非官方：qt.gtimg.cn，返回格式类似：
    # v_sh600519="1~贵州茅台~600519~...~现价~昨收~...~涨跌~涨跌%~...~时间~";
    url = f"https://qt.gtimg.cn/q={sym}"
    try:
        r = await client.get(url)
        if r.status_code != 200:
            return None
        return _parse_tencent_qt(text=r.text, requested_code=code)
    except Exception:
        return None


def _parse_eastmoney_fundgz(text: str, code: str) -> Quote | None:
    text = text.strip()
    m = re.search(r"jsonpgz\((\{.*\})\);?", text)
    if not m:
        return None
    raw_json = m.group(1)
    try:
        data = json.loads(raw_json)
    except Exception:
        return None
    name = str(data.get("name") or "")
    price = _to_float(data.get("gsz"))
    change_pct = _to_float(data.get("gszzl"))
    as_of = str(data.get("gztime") or "")
    # 以 gsz 是否存在作为有效性判断，避免误把异常响应当作行情
    if price is None and change_pct is None:
        return None
    return Quote(
        code=code,
        name=name,
        price=price,
        change_pct=change_pct,
        as_of=as_of,
        source="eastmoney-fundgz",
        raw={"fundgz": data},
    )


async def _fetch_eastmoney_fund_nav_lsjz(client: httpx.AsyncClient, code: str) -> Quote | None:
    # 公募基金历史净值接口（取最新一条）。对 fundgz 返回空的代码（如 018064）很有用。
    url = "https://api.fund.eastmoney.com/f10/lsjz"
    try:
        r = await client.get(
            url,
            params={"fundCode": code, "pageIndex": "1", "pageSize": "1"},
            headers={"Referer": f"https://fund.eastmoney.com/{code}.html"},
        )
        if r.status_code != 200:
            return None
        data = r.json()
        err_code = data.get("ErrCode") or data.get("ErrCod")
        if err_code not in (0, "0", None):
            return None
        payload = data.get("Data") or {}
        items = payload.get("LSJZList") or []
        if not items:
            return None
        it = items[0]
        name = ""
        price = _to_float(it.get("DWJZ"))
        change_pct = _to_float(it.get("JZZZL"))
        as_of = str(it.get("FSRQ") or "")
        if price is None and change_pct is None:
            return None
        return Quote(
            code=code,
            name=name,
            price=price,
            change_pct=change_pct,
            as_of=as_of,
            source="eastmoney-lsjz",
            raw={"lsjz": it},
        )
    except Exception:
        return None


def _parse_tencent_qt(text: str, requested_code: str) -> Quote | None:
    m = re.search(r'v_\w+=\"(.*)\";', text)
    if not m:
        return None
    parts = m.group(1).split("~")
    if len(parts) < 6:
        return None
    name = parts[1]
    price = _to_float(parts[3])
    prev_close = _to_float(parts[4])
    change_pct = _to_float(parts[32]) if len(parts) > 32 else None
    if change_pct is None and price is not None and prev_close not in (None, 0):
        change_pct = (price / prev_close - 1.0) * 100.0
    as_of = parts[30] if len(parts) > 30 and parts[30] else None
    return Quote(
        code=requested_code,
        name=name,
        price=price,
        change_pct=change_pct,
        as_of=as_of,
        source="tencent-qt",
    )


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        s = str(value).strip()
        if s == "" or s.lower() == "nan":
            return None
        return float(s)
    except Exception:
        return None


async def _fetch_coingecko_market(client: httpx.AsyncClient, coingecko_id: str) -> Quote:
    # https://www.coingecko.com/en/api/documentation (public, rate-limited)
    url = "https://api.coingecko.com/api/v3/coins/markets"
    try:
        r = await client.get(
            url,
            params={
                "vs_currency": "cny",
                "ids": coingecko_id,
                "price_change_percentage": "24h",
            },
        )
        if r.status_code != 200:
            return Quote(code=coingecko_id, name="", price=None, change_pct=None, as_of=None, source="coingecko")
        data = r.json()
        if not isinstance(data, list) or not data:
            return Quote(code=coingecko_id, name="", price=None, change_pct=None, as_of=None, source="coingecko")
        it = data[0]
        price = _to_float(it.get("current_price"))
        change_pct = _to_float(it.get("price_change_percentage_24h"))
        name = str(it.get("name") or "")
        return Quote(code=coingecko_id, name=name, price=price, change_pct=change_pct, as_of=None, source="coingecko", raw={"coingecko": it})
    except Exception:
        return Quote(code=coingecko_id, name="", price=None, change_pct=None, as_of=None, source="coingecko")


async def _fetch_coingecko_markets_bulk(client: httpx.AsyncClient, ids: list[str]) -> dict[str, Quote]:
    out: dict[str, Quote] = {}
    # keep request size sane
    chunks: list[list[str]] = []
    chunk: list[str] = []
    for cid in ids:
        chunk.append(cid)
        if len(chunk) >= 120:
            chunks.append(chunk)
            chunk = []
    if chunk:
        chunks.append(chunk)

    for ch in chunks:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        try:
            r = await client.get(
                url,
                params={
                    "vs_currency": "cny",
                    "ids": ",".join(ch),
                    "price_change_percentage": "24h",
                },
            )
            if r.status_code != 200:
                continue
            data = r.json()
            if not isinstance(data, list):
                continue
            for it in data:
                cid = str(it.get("id") or "").strip().lower()
                if not cid:
                    continue
                out[cid] = Quote(
                    code=cid,
                    name=str(it.get("name") or ""),
                    price=_to_float(it.get("current_price")),
                    change_pct=_to_float(it.get("price_change_percentage_24h")),
                    as_of=None,
                    source="coingecko",
                    raw={"coingecko": it},
                )
        except Exception:
            continue
    return out


async def _fetch_tencent_cn_quotes_bulk(client: httpx.AsyncClient, sym_to_requested: dict[str, str]) -> dict[str, Quote]:
    syms = list(sym_to_requested.keys())
    out: dict[str, Quote] = {}

    chunks: list[list[str]] = []
    chunk: list[str] = []
    for s in syms:
        chunk.append(s)
        if len(chunk) >= 60:
            chunks.append(chunk)
            chunk = []
    if chunk:
        chunks.append(chunk)

    for ch in chunks:
        url = f"https://qt.gtimg.cn/q={','.join(ch)}"
        try:
            r = await client.get(url)
            if r.status_code != 200:
                continue
            for m in re.finditer(r'(v_\w+=\"[^\"]*\");', r.text):
                line = m.group(0)
                var = line.split("=", 1)[0].strip()
                sym = var.replace("v_", "", 1)
                requested = sym_to_requested.get(sym)
                if not requested:
                    continue
                q = _parse_tencent_qt(text=line, requested_code=requested)
                if q:
                    out[requested] = q
        except Exception:
            continue
    return out
