from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class TokenBalance:
    quantity: float | None
    symbol: str | None
    decimals: int | None
    source: str
    error: str | None = None


@dataclass(frozen=True)
class _CacheEntry:
    ts: float
    ttl: float
    value: object


@dataclass(frozen=True)
class TokenMeta:
    decimals: int | None
    symbol: str | None
    source: str
    error: str | None = None


def _is_evm_address(addr: str) -> bool:
    return bool(re.fullmatch(r"0x[a-fA-F0-9]{40}", (addr or "").strip()))


_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {c: i for i, c in enumerate(_B58_ALPHABET)}


def _b58decode(s: str) -> bytes:
    s = (s or "").strip()
    n = 0
    for ch in s:
        n = n * 58 + _B58_INDEX[ch]
    pad = len(s) - len(s.lstrip("1"))
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return (b"\x00" * pad) + b


def _is_solana_pubkey(addr: str) -> bool:
    a = (addr or "").strip()
    if not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", a):
        return False
    try:
        return len(_b58decode(a)) == 32
    except Exception:
        return False


def _rpc_env_key(chain: str) -> str:
    return f"PP_RPC_{chain.strip().upper()}"


def _get_rpc_url(chain: str) -> str | None:
    return os.environ.get(_rpc_env_key(chain))


def _is_solana_chain(chain: str) -> bool:
    c = (chain or "").strip().lower()
    return c in {"sol", "solana"}


def _get_solana_rpc_url(chain: str) -> str:
    # Primary: PP_RPC_SOLANA (consistent with other chains).
    rpc = _get_rpc_url(chain) or os.environ.get("PP_RPC_SOL") or os.environ.get("PP_SOLANA_RPC") or os.environ.get("SOLANA_RPC_URL")
    return (rpc or "https://api.mainnet-beta.solana.com").strip()


def _pad_address(addr: str) -> str:
    a = addr.lower().replace("0x", "")
    return a.rjust(64, "0")


def _hex_to_int(hex_str: str) -> int:
    return int(hex_str, 16)


def _decode_abi_string(result_hex: str) -> str | None:
    h = (result_hex or "").lower()
    if h.startswith("0x"):
        h = h[2:]
    if not h:
        return None
    data = bytes.fromhex(h)
    if len(data) < 32:
        return None
    # dynamic string: [offset][...][len][bytes...]
    try:
        offset = int.from_bytes(data[0:32], "big")
        if offset + 32 <= len(data):
            ln = int.from_bytes(data[offset : offset + 32], "big")
            start = offset + 32
            end = start + ln
            if end <= len(data):
                s = data[start:end].decode("utf-8", errors="ignore").strip("\x00").strip()
                return s or None
    except Exception:
        pass

    # bytes32 symbol: right-padded
    try:
        s = data[0:32].decode("utf-8", errors="ignore").strip("\x00").strip()
        return s or None
    except Exception:
        return None


class ChainProvider:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_connections=30, max_keepalive_connections=10),
        )
        self._lock = asyncio.Lock()
        self._balance_cache: dict[str, _CacheEntry] = {}
        self._meta_cache: dict[str, _CacheEntry] = {}

        self.balance_ttl_seconds = 30.0
        self.error_ttl_seconds = 10.0
        self.meta_ttl_seconds = 24 * 60 * 60.0

        self.max_concurrency = 8
        self._rpc_sem = asyncio.Semaphore(self.max_concurrency)
        self.request_timeout_seconds = 8.0

    async def close(self) -> None:
        await self._client.aclose()

    def _ttl_for_balance(self, bal: TokenBalance) -> float:
        return self.error_ttl_seconds if bal.error else self.balance_ttl_seconds

    async def _rpc_limited(self, rpc_url: str, method: str, params: list[Any]) -> Any:
        async with self._rpc_sem:
            return await _rpc(self._client, rpc_url, method, params)

    async def _get_token_meta(self, *, rpc_url: str, chain: str, token_address: str) -> TokenMeta:
        key = f"{chain}:{token_address.lower()}"
        now = time.time()
        async with self._lock:
            cached = self._meta_cache.get(key)
            if cached and (now - cached.ts) < cached.ttl:
                return cached.value  # type: ignore[return-value]

        try:
            data_decimals = "0x313ce567"
            data_symbol = "0x95d89b41"
            dec_task = self._rpc_limited(rpc_url, "eth_call", [{"to": token_address, "data": data_decimals}, "latest"])
            sym_task = self._rpc_limited(rpc_url, "eth_call", [{"to": token_address, "data": data_symbol}, "latest"])
            raw_dec, raw_sym = await asyncio.gather(dec_task, sym_task)
            dec = _hex_to_int(raw_dec)
            sym = _decode_abi_string(raw_sym)
            meta = TokenMeta(decimals=dec, symbol=sym, source="chain-meta")
        except Exception as e:
            meta = TokenMeta(decimals=None, symbol=None, source="chain-meta", error=f"{type(e).__name__}: {e}")

        async with self._lock:
            ttl = self.meta_ttl_seconds if not meta.error else self.error_ttl_seconds
            self._meta_cache[key] = _CacheEntry(ts=now, ttl=ttl, value=meta)
        return meta

    async def get_evm_token_balance(self, *, chain: str, wallet: str, token_address: str | None) -> TokenBalance:
        chain = (chain or "").strip().lower()
        wallet = (wallet or "").strip()
        token_address = (token_address or "").strip() or None

        if not chain:
            return TokenBalance(quantity=None, symbol=None, decimals=None, source="chain", error="missing chain")

        # Solana support (wallet is base58 pubkey; token_address is SPL mint pubkey or empty for SOL).
        if _is_solana_chain(chain):
            if not _is_solana_pubkey(wallet):
                return TokenBalance(quantity=None, symbol=None, decimals=None, source="solana", error="invalid wallet address")
            if token_address is not None and not _is_solana_pubkey(token_address):
                return TokenBalance(quantity=None, symbol=None, decimals=None, source="solana", error="invalid token mint address")
            rpc_url = _get_solana_rpc_url(chain)
            cache_key = f"solana:{wallet}:{(token_address or 'native')}"
            now = time.time()
            async with self._lock:
                cached = self._balance_cache.get(cache_key)
                if cached and (now - cached.ts) < cached.ttl:
                    return cached.value  # type: ignore[return-value]

            bal: TokenBalance
            try:
                bal = await asyncio.wait_for(
                    self._fetch_solana_balance(rpc_url=rpc_url, wallet=wallet, token_mint=token_address),
                    timeout=self.request_timeout_seconds,
                )
            except asyncio.TimeoutError:
                bal = TokenBalance(
                    quantity=None,
                    symbol=None,
                    decimals=None,
                    source="solana",
                    error="TimeoutError: rpc timeout",
                )
            except Exception as e:
                bal = TokenBalance(
                    quantity=None,
                    symbol=None,
                    decimals=None,
                    source="solana",
                    error=f"{type(e).__name__}: {e}",
                )

            ttl = self._ttl_for_balance(bal)
            async with self._lock:
                self._balance_cache[cache_key] = _CacheEntry(ts=now, ttl=ttl, value=bal)
            return bal

        # EVM (0x...)
        if not _is_evm_address(wallet):
            return TokenBalance(quantity=None, symbol=None, decimals=None, source="chain", error="invalid wallet address")
        if token_address is not None and not _is_evm_address(token_address):
            return TokenBalance(quantity=None, symbol=None, decimals=None, source="chain", error="invalid token address")

        rpc_url = _get_rpc_url(chain)
        if not rpc_url:
            return TokenBalance(
                quantity=None,
                symbol=None,
                decimals=None,
                source=f"chain:{chain}",
                error=f"missing rpc url env {_rpc_env_key(chain)}",
            )

        cache_key = f"{chain}:{wallet.lower()}:{(token_address or 'native').lower()}"
        now = time.time()
        async with self._lock:
            cached = self._balance_cache.get(cache_key)
            if cached and (now - cached.ts) < cached.ttl:
                return cached.value  # type: ignore[return-value]

        bal: TokenBalance
        try:
            bal = await asyncio.wait_for(
                self._fetch_balance(rpc_url=rpc_url, chain=chain, wallet=wallet, token_address=token_address),
                timeout=self.request_timeout_seconds,
            )
        except asyncio.TimeoutError:
            bal = TokenBalance(quantity=None, symbol=None, decimals=None, source=f"chain:{chain}", error="TimeoutError: rpc timeout")
        except Exception as e:
            bal = TokenBalance(quantity=None, symbol=None, decimals=None, source=f"chain:{chain}", error=f"{type(e).__name__}: {e}")

        ttl = self._ttl_for_balance(bal)
        async with self._lock:
            self._balance_cache[cache_key] = _CacheEntry(ts=now, ttl=ttl, value=bal)
        return bal

    async def _fetch_balance(self, *, rpc_url: str, chain: str, wallet: str, token_address: str | None) -> TokenBalance:
        try:
            if token_address is None:
                raw = await self._rpc_limited(rpc_url, "eth_getBalance", [wallet, "latest"])
                wei = _hex_to_int(raw)
                qty = wei / 1e18
                return TokenBalance(quantity=qty, symbol=None, decimals=18, source="chain-native")

            token_address = token_address.strip()
            if not _is_evm_address(token_address):
                return TokenBalance(
                    quantity=None,
                    symbol=None,
                    decimals=None,
                    source=f"chain:{chain}",
                    error="invalid token address",
                )

            meta = await self._get_token_meta(rpc_url=rpc_url, chain=chain, token_address=token_address)

            data_balance = "0x70a08231" + _pad_address(wallet)
            raw_bal = await self._rpc_limited(rpc_url, "eth_call", [{"to": token_address, "data": data_balance}, "latest"])
            bal_int = _hex_to_int(raw_bal)

            qty = (bal_int / (10 ** meta.decimals)) if meta.decimals is not None else None
            return TokenBalance(
                quantity=qty,
                symbol=meta.symbol,
                decimals=meta.decimals,
                source="chain-erc20",
                error=meta.error,
            )
        except Exception as e:
            return TokenBalance(
                quantity=None,
                symbol=None,
                decimals=None,
                source=f"chain:{chain}",
                error=f"{type(e).__name__}: {e}",
            )

    async def _fetch_solana_balance(self, *, rpc_url: str, wallet: str, token_mint: str | None) -> TokenBalance:
        try:
            if token_mint is None:
                res = await self._rpc_limited(rpc_url, "getBalance", [wallet])
                lamports = int((res or {}).get("value") or 0)
                qty = lamports / 1e9
                return TokenBalance(quantity=qty, symbol="SOL", decimals=9, source="solana-native")

            res = await self._rpc_limited(
                rpc_url,
                "getTokenAccountsByOwner",
                [
                    wallet,
                    {"mint": token_mint},
                    {"encoding": "jsonParsed"},
                ],
            )
            accounts = (res or {}).get("value") or []
            total_amount = 0
            decimals: int | None = None
            for it in accounts:
                try:
                    info = (
                        (((it or {}).get("account") or {}).get("data") or {}).get("parsed") or {}
                    ).get("info") or {}
                    ta = info.get("tokenAmount") or {}
                    amount_str = str(ta.get("amount") or "0").strip()
                    dec = ta.get("decimals")
                    if decimals is None and dec is not None:
                        decimals = int(dec)
                    total_amount += int(amount_str)
                except Exception:
                    continue

            if decimals is None:
                # No accounts or unexpected format => treat as zero balance.
                return TokenBalance(quantity=0.0, symbol=None, decimals=None, source="solana-spl")

            qty = total_amount / (10**decimals)
            return TokenBalance(quantity=qty, symbol=None, decimals=decimals, source="solana-spl")
        except Exception as e:
            return TokenBalance(quantity=None, symbol=None, decimals=None, source="solana", error=f"{type(e).__name__}: {e}")


async def _rpc(client: httpx.AsyncClient, rpc_url: str, method: str, params: list[Any]) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = await client.post(rpc_url, json=payload, headers={"Content-Type": "application/json"})
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    return data.get("result")
