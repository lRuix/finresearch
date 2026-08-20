"""Open-source data providers with a deterministic mock fallback."""

from __future__ import annotations

import json
import math
import random
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.error import URLError
from urllib.request import Request, urlopen


CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, list[dict], str]] = {}
_cache_lock = threading.Lock()
_dead_providers: dict[str, float] = {}
_dead_lock = threading.Lock()

BASE_PRICE = {
    "600519": 1420.0,
    "000001": 11.2,
    "300750": 182.0,
    "601318": 46.5,
    "600036": 34.8,
    "110022": 2.86,
    "161725": 0.82,
    "510300": 3.62,
    "159915": 1.86,
    "AAPL": 232.0,
    "NVDA": 126.5,
    "MSFT": 425.0,
    "TSLA": 248.0,
    "SPY": 585.0,
    "005930.KS": 80500.0,
    "000660.KS": 182000.0,
    "035420.KS": 218000.0,
    "373220.KS": 402000.0,
    "0700.HK": 382.0,
    "9988.HK": 86.5,
    "3690.HK": 112.0,
    "1810.HK": 17.8,
    "USDCNY=X": 7.18,
    "EURUSD=X": 1.086,
    "USDJPY=X": 154.8,
    "GBPUSD=X": 1.272,
    "BTCUSDT": 64800.0,
    "ETHUSDT": 3420.0,
    "SOLUSDT": 168.0,
    "BNBUSDT": 596.0,
}

VOLATILITY = {
    "a-share": 0.016,
    "fund": 0.011,
    "us": 0.015,
    "kr": 0.018,
    "hk": 0.017,
    "fx": 0.005,
    "crypto": 0.035,
}


def _cache_get(key: str) -> tuple[list[dict], str] | None:
    with _cache_lock:
        hit = _cache.get(key)
    if hit is None:
        return None
    expires_at, payload, source = hit
    if time.time() > expires_at:
        return None
    return payload, source


def _cache_set(
    key: str,
    payload: list[dict],
    source: str,
    ttl: int = CACHE_TTL_SECONDS,
) -> None:
    with _cache_lock:
        _cache[key] = (time.time() + ttl, payload, source)


def _mark_dead(key: str) -> None:
    with _dead_lock:
        _dead_providers[key] = time.time() + 120


def _is_dead(key: str) -> bool:
    with _dead_lock:
        expires_at = _dead_providers.get(key)
    return expires_at is not None and time.time() < expires_at


def _get_json(
    url: str,
    timeout: int = 5,
    headers: dict[str, str] | None = None,
) -> object:
    request_headers = {"User-Agent": "finresearch-terminal/0.1"}
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_text(
    url: str,
    encoding: str = "utf-8",
    timeout: int = 5,
    headers: dict[str, str] | None = None,
) -> str:
    request_headers = {"User-Agent": "finresearch-terminal/0.1"}
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode(encoding, errors="replace")


def _try_provider(name: str, key: str, function, *args):
    if _is_dead(f"{name}:{key}"):
        return []
    try:
        rows = function(*args)
        if rows:
            return rows
    except Exception:
        _mark_dead(f"{name}:{key}")
    return []


def _aggregate_weekly(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[int, int], list[dict]] = {}
    for row in rows:
        timestamp = row["time"].replace("Z", "+00:00")
        try:
            day = datetime.fromisoformat(timestamp).date()
        except ValueError:
            continue
        groups.setdefault((day.isocalendar().year, day.isocalendar().week), []).append(row)

    weekly: list[dict] = []
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


def binance_klines(symbol: str, interval: str, limit: int) -> list[dict]:
    interval_map = {"h": "1h", "d": "1d", "w": "1w"}
    url = (
        "https://api.binance.com/api/v3/klines"
        f"?symbol={symbol}&interval={interval_map[interval]}&limit={limit}"
    )
    payload = _get_json(url)
    rows = []
    for item in payload:
        ts = datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc)
        rows.append(
            {
                "time": ts.isoformat(),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            }
        )
    if not rows:
        raise ValueError("binance returned no rows")
    return rows


def _tencent_symbol(symbol: str, market: str) -> str:
    code = symbol.split(".")[0]
    if market == "a-share":
        prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
        return f"{prefix}{code}"
    if market == "fund":
        prefix = "sh" if code.startswith("5") else "sz"
        return f"{prefix}{code}"
    if market == "us":
        return f"us{code}.OQ"
    if market == "hk":
        return f"hk{code.zfill(5)}"
    raise ValueError(f"tencent does not support market {market}")


def tencent_klines(
    market: str,
    symbol: str,
    interval: str,
    limit: int,
) -> list[dict]:
    t_symbol = _tencent_symbol(symbol, market)
    period = {"h": "m60", "d": "day", "w": "week"}[interval]
    adjust = "qfq" if market in ("a-share", "fund") else ""
    params = urlencode({"param": f"{t_symbol},{period},,,{limit},{adjust}"})
    payload = _get_json(
        f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?{params}",
        timeout=6,
        headers={"Referer": "https://gu.qq.com/"},
    )
    node = (payload or {}).get("data", {}).get(t_symbol, {})
    raw_rows = node.get(f"qfq{period}") or node.get(period) or []
    if not raw_rows:
        raise ValueError(f"tencent returned no rows for {t_symbol}")

    rows = []
    for item in raw_rows:
        if len(item) < 5:
            continue
        timestamp = str(item[0])
        if interval == "h" and " " in timestamp:
            timestamp = timestamp.replace(" ", "T") + ":00"
        rows.append(
            {
                "time": timestamp,
                "open": float(item[1]),
                "close": float(item[2]),
                "high": float(item[3]),
                "low": float(item[4]),
                "volume": float(item[5]) if len(item) > 5 else 0.0,
            }
        )
    if interval == "h" and len(rows) < 2:
        raise ValueError("tencent returned insufficient hourly rows")
    return rows[-limit:]


def naver_klines(symbol: str, interval: str, limit: int) -> list[dict]:
    if interval == "h":
        raise ValueError("naver does not provide hourly klines")
    timeframe = {"d": "day", "w": "week"}[interval]
    code = symbol.split(".")[0]
    text = _get_text(
        f"https://fchart.stock.naver.com/sise.nhn?symbol={code}"
        f"&timeframe={timeframe}&count={limit}&requestType=0",
        encoding="euc-kr",
        timeout=8,
    )
    root = ET.fromstring(text)
    rows = []
    for item in root.iter("item"):
        values = item.attrib.get("data", "").split("|")
        if len(values) < 5:
            continue
        raw_date = values[0]
        normalized_date = (
            f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
            if len(raw_date) == 8
            else raw_date
        )
        rows.append(
            {
                "time": normalized_date,
                "open": float(values[1]),
                "high": float(values[2]),
                "low": float(values[3]),
                "close": float(values[4]),
                "volume": float(values[5]) if len(values) > 5 else 0.0,
            }
        )
    if not rows:
        raise ValueError(f"naver returned no rows for {symbol}")
    return rows[-limit:]


def gate_klines(symbol: str, interval: str, limit: int) -> list[dict]:
    pair = f"{symbol[:-4]}_{symbol[-4:]}"
    interval_map = {"h": "1h", "d": "1d", "w": "1w"}
    params = urlencode(
        {
            "currency_pair": pair,
            "interval": interval_map[interval],
            "limit": limit,
        }
    )
    payload = _get_json(
        f"https://api.gateio.ws/api/v4/spot/candlesticks?{params}",
        timeout=8,
    )
    if not payload:
        raise ValueError(f"gate returned no rows for {symbol}")

    rows = []
    for item in payload:
        rows.append(
            {
                "time": datetime.fromtimestamp(int(item[0]), tz=timezone.utc).isoformat(),
                "open": float(item[5]),
                "high": float(item[3]),
                "low": float(item[4]),
                "close": float(item[2]),
                "volume": float(item[6]) if len(item) > 6 else 0.0,
            }
        )
    return rows[-limit:]


def frankfurter_klines(symbol: str, interval: str, limit: int) -> list[dict]:
    if interval == "h":
        raise ValueError("frankfurter does not provide hourly fx rates")
    code = symbol.split("=")[0]
    if code in ("EURUSD", "GBPUSD"):
        inverse = True
        target = code[:3]
    else:
        inverse = False
        target = code[3:]

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=min(max(limit * 2, 30), 360))
    payload = _get_json(
        f"https://api.frankfurter.dev/v1/{start.isoformat()}..{end.isoformat()}"
        f"?base=USD&symbols={target}",
        timeout=8,
    )
    rates = (payload or {}).get("rates", {})
    rows = []
    previous = None
    for day in sorted(rates.keys()):
        value = float(rates[day][target])
        close = 1 / value if inverse else value
        open_price = previous if previous is not None else close
        rows.append(
            {
                "time": day,
                "open": open_price,
                "high": max(open_price, close),
                "low": min(open_price, close),
                "close": close,
                "volume": 0.0,
            }
        )
        previous = close
    if not rows:
        raise ValueError(f"frankfurter returned no rows for {symbol}")
    if interval == "w":
        rows = _aggregate_weekly(rows)
    return rows[-limit:]


def eastmoney_fund_klines(symbol: str, interval: str, limit: int) -> list[dict]:
    if interval == "h":
        raise ValueError("fund nav does not provide hourly data")
    params = urlencode(
        {
            "fundCode": symbol,
            "pageIndex": 1,
            "pageSize": min(limit, 200),
        }
    )
    payload = _get_json(
        f"https://api.fund.eastmoney.com/f10/lsjz?{params}",
        timeout=8,
        headers={
            "Referer": "https://fundf10.eastmoney.com/",
            "User-Agent": "Mozilla/5.0",
        },
    )
    items = (payload or {}).get("Data", {}).get("LSJZList", [])
    rows = []
    for item in items:
        close = float(item.get("DWJZ", 0))
        rows.append(
            {
                "time": item.get("FSRQ", ""),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 0.0,
            }
        )
    rows = list(reversed(rows))
    if not rows:
        raise ValueError(f"eastmoney returned no rows for {symbol}")
    if interval == "w":
        rows = _aggregate_weekly(rows)
    return rows[-limit:]


def yfinance_klines(ticker: str, interval: str, limit: int) -> list[dict]:
    import yfinance as yf

    period_map = {
        "h": "3mo" if limit <= 500 else "6mo",
        "d": "3mo" if limit <= 90 else "6mo" if limit <= 180 else "1y",
        "w": "2y",
    }
    interval_map = {"h": "60m", "d": "1d", "w": "1wk"}
    frame = yf.Ticker(ticker).history(
        period=period_map[interval],
        interval=interval_map[interval],
        auto_adjust=False,
        actions=False,
        timeout=8,
    )
    if frame.empty:
        raise ValueError(f"yfinance returned no rows for {ticker}")

    rows = []
    for index, row in frame.iterrows():
        timestamp = index.to_pydatetime()
        if timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        rows.append(
            {
                "time": timestamp.isoformat(),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row.get("Volume", 0) or 0),
            }
        )
    return rows


def akshare_klines(market: str, symbol: str) -> list[dict]:
    import akshare as ak

    if market == "a-share":
        frame = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")
        rows = []
        for _, row in frame.iterrows():
            rows.append(
                {
                    "time": str(row["日期"]),
                    "open": float(row["开盘"]),
                    "high": float(row["最高"]),
                    "low": float(row["最低"]),
                    "close": float(row["收盘"]),
                    "volume": float(row["成交量"]),
                }
            )
        return rows

    if market == "fund":
        if symbol.isdigit() and symbol.startswith(("15", "51")):
            frame = ak.fund_etf_hist_em(symbol=symbol, period="daily", adjust="qfq")
            rows = []
            for _, row in frame.iterrows():
                rows.append(
                    {
                        "time": str(row["日期"]),
                        "open": float(row["开盘"]),
                        "high": float(row["最高"]),
                        "low": float(row["最低"]),
                        "close": float(row["收盘"]),
                        "volume": float(row["成交量"]),
                    }
                )
            return rows

        frame = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势")
        rows = []
        for _, row in frame.iterrows():
            close = float(row["单位净值"])
            rows.append(
                {
                    "time": str(row["净值日期"]),
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": 0.0,
                }
            )
        return rows

    raise ValueError(f"akshare does not support market {market}")


def mock_klines(symbol: str, market: str, interval: str, limit: int) -> list[dict]:
    seed = abs(hash((market, symbol))) % (2**32)
    rng = random.Random(seed)

    base = BASE_PRICE.get(symbol, rng.uniform(20, 300))
    vol = VOLATILITY.get(market, 0.02)
    drift = rng.uniform(-0.0008, 0.0016)
    regime = rng.uniform(-1, 1)
    cycle_phase = rng.uniform(0, math.tau)

    hours = {"h": 1, "d": 24, "w": 168}
    step = hours[interval]
    total = limit + 90
    price = base * rng.uniform(0.82, 1.05)
    rows: list[dict] = []

    if interval == "d":
        day = datetime.now(timezone.utc).date()
        dates: list[datetime] = []
        while len(dates) < total:
            if day.weekday() < 5:
                dates.append(datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(hours=8))
            day -= timedelta(days=1)
        dates.reverse()

    now = datetime.now(timezone.utc)
    for index in range(total):
        if interval == "d":
            t = dates[index]
        else:
            t = now - timedelta(hours=step * (total - index - 1))

        cycle = math.sin(index / 28 + cycle_phase) * 0.0006
        macro_shock = math.sin(index / 63) * regime * 0.0009
        noise = rng.gauss(0, 1)
        shock = 0.0
        if rng.random() < 0.018:
            shock = rng.uniform(-0.055, 0.065) if market in ("crypto", "kr") else rng.uniform(-0.035, 0.04)
        daily_return = drift + cycle + macro_shock + vol * noise + shock

        open_price = price
        close_price = max(open_price * (1 + daily_return), base * 0.05)
        wick = abs(rng.gauss(0, 1)) * vol * 0.9
        high = max(open_price, close_price) * (1 + wick * 0.7)
        low = min(open_price, close_price) * (1 - wick * 0.7)
        volume = abs(daily_return) * 8 + rng.uniform(0.6, 1.6)
        if market in ("fx",):
            volume = volume * 30

        rows.append(
            {
                "time": t.isoformat(),
                "open": round(open_price, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close_price, 4),
                "volume": round(volume, 2),
            }
        )
        price = close_price

    return rows[-limit:]


def get_kline_with_source(
    market: str,
    symbol: str,
    interval: str = "d",
    limit: int = 180,
    prefer_real: bool = True,
) -> tuple[list[dict], str]:
    key = f"{market}:{symbol}:{interval}:{limit}:{int(prefer_real)}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    provider_key = f"{market}:{symbol}:{interval}"
    rows: list[dict] = []
    source = "mock"
    if prefer_real:
        if market == "crypto":
            rows = _try_provider(
                "gate",
                provider_key,
                gate_klines,
                symbol,
                interval,
                limit,
            )
            if not rows:
                rows = _try_provider(
                    "binance",
                    provider_key,
                    binance_klines,
                    symbol,
                    interval,
                    min(limit, 500),
                )
            if not rows:
                rows = _try_provider(
                    "yfinance",
                    provider_key,
                    yfinance_klines,
                    f"{symbol[:-4]}-USD",
                    interval,
                    limit,
                )
        elif market in ("a-share", "fund"):
            is_open_fund = market == "fund" and not symbol.startswith(("15", "51"))
            if is_open_fund:
                rows = _try_provider(
                    "eastmoney-fund",
                    provider_key,
                    eastmoney_fund_klines,
                    symbol,
                    interval,
                    limit,
                )
            else:
                rows = _try_provider(
                    "tencent",
                    provider_key,
                    tencent_klines,
                    market,
                    symbol,
                    interval,
                    limit,
                )
            if not rows:
                rows = _try_provider(
                    "akshare",
                    provider_key,
                    akshare_klines,
                    market,
                    symbol,
                )
        elif market == "kr":
            rows = _try_provider(
                "naver",
                provider_key,
                naver_klines,
                symbol,
                interval,
                limit,
            )
            if not rows:
                rows = _try_provider(
                    "yfinance",
                    provider_key,
                    yfinance_klines,
                    symbol,
                    interval,
                    limit,
                )
        elif market in ("us", "hk"):
            rows = _try_provider(
                "tencent",
                provider_key,
                tencent_klines,
                market,
                symbol,
                interval,
                limit,
            )
            if not rows:
                rows = _try_provider(
                    "yfinance",
                    provider_key,
                    yfinance_klines,
                    symbol,
                    interval,
                    limit,
                )
        elif market == "fx":
            rows = _try_provider(
                "frankfurter",
                provider_key,
                frankfurter_klines,
                symbol,
                interval,
                limit,
            )
            if not rows:
                rows = _try_provider(
                    "yfinance",
                    provider_key,
                    yfinance_klines,
                    symbol,
                    interval,
                    limit,
                )

    if rows:
        source = "live"
    if not rows:
        rows = mock_klines(symbol, market, interval, limit)
        source = "mock"

    _cache_set(key, rows, source)
    return rows, source


def get_kline(
    market: str,
    symbol: str,
    interval: str = "d",
    limit: int = 180,
    prefer_real: bool = True,
) -> list[dict]:
    rows, _ = get_kline_with_source(market, symbol, interval, limit, prefer_real)
    return rows


def get_live_fx_rates() -> dict[str, float] | None:
    """实时拉取 USD 基准汇率，换算为「本币 → RMB」参考汇率。

    数据源：frankfurter（USD 基准）。返回 {currency: 1本币=多少RMB}，
    任何失败（网络异常/无数据）返回 None（调用方回退静态值）。
    失败时标记熔断，120 秒内直接返回 None 不再请求。
    """
    fx_key = "fx:live-rates"
    if _is_dead(fx_key):
        return None
    try:
        payload = _get_json(
            "https://api.frankfurter.dev/v1/latest?base=USD&symbols=CNY,HKD,KRW",
            timeout=6,
        )
    except Exception:
        _mark_dead(fx_key)
        return None
    rates = (payload or {}).get("rates", {})
    if not rates or "CNY" not in rates:
        _mark_dead(fx_key)
        return None
    cny = float(rates["CNY"])          # 1 USD = cny RMB
    hkd = float(rates.get("HKD", 7.84))  # 1 USD = hkd HKD
    krw = float(rates.get("KRW", 1396.0))  # 1 USD = krw KRW
    return {
        "CNY": 1.0,
        "USD": cny,
        "USDT": cny,                   # USDT 按 USD 计价
        "HKD": cny / hkd,
        "KRW": cny / krw,
        "MULTI": 1.0,                  # 外汇对本身是货币对，暂按 1.0
    }
