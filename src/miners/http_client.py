"""Camada HTTP resiliente com exponential backoff, rate-limiting por domínio e cache TTL em disco."""

from __future__ import annotations

import base64
import hashlib
import json
import random
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from ..config import USER_AGENT, atomic_write_json, get_cache_dir, get_logger

logger = get_logger(__name__)

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

DEFAULT_DOMAIN_INTERVALS: dict[str, float] = {
    "api.github.com": 0.4,
    "boards-api.greenhouse.io": 0.25,
    "api.ashbyhq.com": 0.25,
    "api.lever.co": 0.25,
    "hn.algolia.com": 0.25,
    "remotive.com": 0.3,
    "jobicy.com": 0.3,
    "weworkremotely.com": 0.3,
}


class DiskHTTPCache:
    """Cache local em disco indexado por SHA-256 com expiração por TTL."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._explicit_dir = cache_dir
        self._now_fn = now_fn or time.time

    @property
    def cache_dir(self) -> Path:
        return self._explicit_dir if self._explicit_dir is not None else get_cache_dir()

    @staticmethod
    def build_key(url: str, params: dict[str, Any] | None = None) -> str:
        canonical = str(httpx.URL(url, params=params))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _entry_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str, ttl_seconds: int) -> bytes | None:
        if ttl_seconds <= 0:
            return None
        entry_path = self._entry_path(key)
        if not entry_path.exists():
            return None

        try:
            with open(entry_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            fetched_at = float(payload["fetched_at"])
            if self._now_fn() - fetched_at > ttl_seconds:
                return None
            return base64.b64decode(payload["body_b64"].encode("ascii"))
        except Exception:
            return None

    def set(self, key: str, url: str, body: bytes) -> None:
        payload = {
            "url": url,
            "fetched_at": self._now_fn(),
            "body_b64": base64.b64encode(body).decode("ascii"),
        }
        try:
            atomic_write_json(self._entry_path(key), payload)
        except Exception as exc:
            logger.warning("Falha ao gravar cache HTTP para %s: %s", url, exc)


class DomainRateLimiter:
    """Controlador de cadência thread-safe por domínio (host)."""

    def __init__(
        self,
        default_interval: float = 0.25,
        per_domain: dict[str, float] | None = None,
        clock_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self.default_interval = max(0.0, default_interval)
        self.per_domain = (
            dict(DEFAULT_DOMAIN_INTERVALS)
            if per_domain is None
            else dict(per_domain)
        )
        self._clock_fn = clock_fn or time.monotonic
        self._sleep_fn = sleep_fn or time.sleep
        self._lock = threading.Lock()
        self._next_allowed: dict[str, float] = {}

    def acquire(self, url: str) -> float:
        """Aguarda o intervalo mínimo configurado para o host da URL e retorna o tempo aguardado."""
        host = urlparse(url).netloc.lower()
        interval = self.per_domain.get(host, self.default_interval)
        if interval <= 0:
            return 0.0

        with self._lock:
            now = self._clock_fn()
            earliest = self._next_allowed.get(host, now)
            wait_seconds = max(0.0, earliest - now)
            scheduled_at = max(now, earliest)
            self._next_allowed[host] = scheduled_at + interval

        if wait_seconds > 0:
            self._sleep_fn(wait_seconds)
        return wait_seconds


class ResilientHTTPClient:
    """Cliente HTTP baseado em httpx com retries, exponential backoff, rate-limit e cache."""

    def __init__(
        self,
        timeout: float = 15.0,
        max_retries: int = 3,
        base_backoff: float = 0.5,
        max_backoff: float = 10.0,
        cache_ttl_seconds: int = 2700,
        use_cache: bool = True,
        cache: DiskHTTPCache | None = None,
        rate_limiter: DomainRateLimiter | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        jitter_fn: Callable[[float, float], float] | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self.cache_ttl_seconds = cache_ttl_seconds
        self.use_cache = use_cache
        self.cache = cache if cache is not None else DiskHTTPCache()
        self.rate_limiter = (
            rate_limiter if rate_limiter is not None else DomainRateLimiter()
        )
        self._sleep_fn = sleep_fn or time.sleep
        self._jitter_fn = jitter_fn or random.uniform
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, application/xml, text/xml, */*",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ResilientHTTPClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _compute_backoff(self, attempt: int, response: httpx.Response | None = None) -> float:
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    parsed = float(retry_after.strip())
                    return min(self.max_backoff, max(0.0, parsed))
                except ValueError:
                    pass
        exp_delay = min(self.max_backoff, self.base_backoff * (2**attempt))
        jitter = max(0.0, self._jitter_fn(0.0, 0.25))
        return min(self.max_backoff, exp_delay + jitter)

    def get_bytes(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool | None = None,
    ) -> bytes | None:
        cache_enabled = self.use_cache if use_cache is None else use_cache
        cache_key = DiskHTTPCache.build_key(url, params)
        if cache_enabled:
            cached = self.cache.get(cache_key, self.cache_ttl_seconds)
            if cached is not None:
                return cached

        for attempt in range(self.max_retries + 1):
            self.rate_limiter.acquire(url)
            response: httpx.Response | None = None
            try:
                response = self._client.get(url, params=params, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
                logger.warning(
                    "Erro de rede (%s) em %s (tentativa %d/%d): %s",
                    type(exc).__name__,
                    url,
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
                if attempt < self.max_retries:
                    self._sleep_fn(self._compute_backoff(attempt))
                    continue
                return None

            if 200 <= response.status_code < 300:
                body = response.content
                if cache_enabled:
                    self.cache.set(cache_key, str(response.url), body)
                return body

            if response.status_code in RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                delay = self._compute_backoff(attempt, response=response)
                logger.warning(
                    "HTTP %d em %s — aguardando %.2fs antes de retry (%d/%d)",
                    response.status_code,
                    url,
                    delay,
                    attempt + 1,
                    self.max_retries + 1,
                )
                self._sleep_fn(delay)
                continue

            logger.warning("HTTP %d não recuperável em %s", response.status_code, url)
            return None

        return None

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool | None = None,
    ) -> Any | None:
        raw = self.get_bytes(url, params=params, headers=headers, use_cache=use_cache)
        if raw is None:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            logger.warning("JSON inválido recebido de %s: %s", url, exc)
            return None
