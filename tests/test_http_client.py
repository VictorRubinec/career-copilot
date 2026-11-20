from pathlib import Path

import httpx

from src.miners.http_client import DiskHTTPCache, DomainRateLimiter, ResilientHTTPClient


def test_http_client_retries_503_with_exponential_backoff(tmp_path: Path):
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json={"ok": True})

    cache = DiskHTTPCache(cache_dir=tmp_path / "cache")
    limiter = DomainRateLimiter(default_interval=0.0, per_domain={})
    with ResilientHTTPClient(
        max_retries=3,
        base_backoff=0.5,
        max_backoff=5.0,
        cache=cache,
        rate_limiter=limiter,
        transport=httpx.MockTransport(handler),
        sleep_fn=sleeps.append,
        jitter_fn=lambda a, b: 0.0,
    ) as client:
        data = client.get_json("https://api.exemplo.com/jobs")

    assert data == {"ok": True}
    assert attempts == 3
    assert sleeps == [0.5, 1.0]


def test_http_client_respects_429_retry_after_header(tmp_path: Path):
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json={"jobs": [1]})

    cache = DiskHTTPCache(cache_dir=tmp_path / "cache")
    limiter = DomainRateLimiter(default_interval=0.0, per_domain={})
    with ResilientHTTPClient(
        max_retries=2,
        max_backoff=10.0,
        cache=cache,
        rate_limiter=limiter,
        transport=httpx.MockTransport(handler),
        sleep_fn=sleeps.append,
        jitter_fn=lambda a, b: 0.0,
    ) as client:
        data = client.get_json("https://api.exemplo.com/rate")

    assert data == {"jobs": [1]}
    assert sleeps == [3.0]


def test_http_client_timeout_exhaustion_and_non_retryable_404(tmp_path: Path):
    timeout_calls = 0
    not_found_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal timeout_calls, not_found_calls
        if "timeout" in str(request.url):
            timeout_calls += 1
            raise httpx.ReadTimeout("timed out", request=request)
        not_found_calls += 1
        return httpx.Response(404, text="not found")

    cache = DiskHTTPCache(cache_dir=tmp_path / "cache")
    limiter = DomainRateLimiter(default_interval=0.0, per_domain={})
    with ResilientHTTPClient(
        max_retries=2,
        base_backoff=0.1,
        cache=cache,
        rate_limiter=limiter,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _: None,
        jitter_fn=lambda a, b: 0.0,
    ) as client:
        assert client.get_bytes("https://api.exemplo.com/timeout") is None
        assert client.get_bytes("https://api.exemplo.com/missing") is None

    assert timeout_calls == 3
    assert not_found_calls == 1


def test_disk_http_cache_hit_ttl_expiry_and_bypass(tmp_path: Path):
    clock = [1000.0]
    network_hits = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal network_hits
        network_hits += 1
        return httpx.Response(200, json={"hit": network_hits})

    cache = DiskHTTPCache(cache_dir=tmp_path / "cache", now_fn=lambda: clock[0])
    limiter = DomainRateLimiter(default_interval=0.0, per_domain={})
    with ResilientHTTPClient(
        cache_ttl_seconds=60,
        cache=cache,
        rate_limiter=limiter,
        transport=httpx.MockTransport(handler),
    ) as client:
        url = "https://api.exemplo.com/items"
        assert client.get_json(url) == {"hit": 1}
        assert client.get_json(url) == {"hit": 1}
        assert network_hits == 1

        # Bypass explícito de cache
        assert client.get_json(url, use_cache=False) == {"hit": 2}
        assert network_hits == 2

        # Expiração do TTL
        clock[0] += 120.0
        assert client.get_json(url) == {"hit": 3}
        assert network_hits == 3


def test_domain_rate_limiter_spaces_requests_per_host():
    now = [10.0]
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(round(seconds, 3))
        now[0] += seconds

    limiter = DomainRateLimiter(
        default_interval=0.5,
        per_domain={"boards-api.greenhouse.io": 1.0},
        clock_fn=lambda: now[0],
        sleep_fn=fake_sleep,
    )

    assert limiter.acquire("https://boards-api.greenhouse.io/v1/boards/gitlab/jobs") == 0.0
    wait_second = limiter.acquire("https://boards-api.greenhouse.io/v1/boards/stripe/jobs")
    assert wait_second == 1.0
    assert sleeps == [1.0]
    # Outro domínio não sofre bloqueio pelo anterior
    assert limiter.acquire("https://api.lever.co/v0/postings/toptal") == 0.0
