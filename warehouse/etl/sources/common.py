"""Shared HTTP, parsing, caching and circuit-breaking helpers."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen


CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, list[dict], str]] = {}
_cache_lock = threading.Lock()
_dead_providers: dict[str, float] = {}
_dead_lock = threading.Lock()


def get_json(url, timeout=8, headers=None):
    request_headers = {"User-Agent": "finresearch-warehouse/1.0"}
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_text(url, encoding="utf-8", timeout=8, headers=None):
    request_headers = {"User-Agent": "finresearch-warehouse/1.0"}
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode(encoding, errors="replace")


def parse_ts(value):
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def aggregate_weekly(rows):
    groups: dict[tuple[int, int], list[dict]] = {}
    for row in rows:
        try:
            day = parse_ts(row["time"]).date()
        except (TypeError, ValueError):
            continue
        groups.setdefault((day.isocalendar().year, day.isocalendar().week), []).append(row)
    weekly = []
    for _, group in groups.items():
        group.sort(key=lambda item: item["time"])
        weekly.append(
            {
                "time": group[-1]["time"],
                "open": group[0]["open"],
                "high": max(item["high"] for item in group),
                "low": min(item["low"] for item in group),
                "close": group[-1]["close"],
                "volume": sum(item["volume"] for item in group),
            }
        )
    weekly.sort(key=lambda item: item["time"])
    return weekly


def cache_get(key):
    with _cache_lock:
        hit = _cache.get(key)
    if hit is None:
        return None
    expires_at, payload, source = hit
    if time.time() > expires_at:
        return None
    return payload, source


def cache_set(key, payload, source, ttl=CACHE_TTL_SECONDS):
    with _cache_lock:
        _cache[key] = (time.time() + ttl, payload, source)


def mark_dead(key):
    with _dead_lock:
        _dead_providers[key] = time.time() + 120


def is_dead(key):
    with _dead_lock:
        expires_at = _dead_providers.get(key)
    return expires_at is not None and time.time() < expires_at


def try_provider(name, key, function, *args):
    if is_dead(f"{name}:{key}"):
        return []
    try:
        rows = function(*args)
        if rows:
            return rows
    except Exception:
        mark_dead(f"{name}:{key}")
    return []
