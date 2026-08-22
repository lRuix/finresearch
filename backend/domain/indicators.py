"""Technical indicators and composite scoring."""

from __future__ import annotations

import math


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal_period: int = 9):
    if len(closes) < slow + signal_period:
        return {"macd": None, "signal": None, "histogram": None}
    ema_fast = ema_series(closes, fast)
    ema_slow = ema_series(closes, slow)
    dif = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal = ema_series(dif, signal_period)
    histogram = [d - s for d, s in zip(dif, signal)]
    return {
        "macd": dif[-1],
        "signal": signal[-1],
        "histogram": histogram[-1],
        "histogram_series": histogram[-40:],
    }


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, len(closes)):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for index in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[index]) / period
        avg_loss = (avg_loss * (period - 1) + losses[index]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def bollinger(closes: list[float], period: int = 20, width: float = 2.0):
    if len(closes) < period:
        return {"upper": None, "middle": None, "lower": None, "bandwidth": None}
    middle = sma(closes, period)
    window = closes[-period:]
    variance = sum((value - middle) ** 2 for value in window) / period
    deviation = math.sqrt(variance)
    upper = middle + width * deviation
    lower = middle - width * deviation
    bandwidth = (upper - lower) / middle if middle else 0
    return {
        "upper": round(upper, 4),
        "middle": round(middle, 4),
        "lower": round(lower, 4),
        "bandwidth": round(bandwidth, 4),
    }


def atr(klines: list[dict], period: int = 14) -> float | None:
    if len(klines) < period + 1:
        return None
    true_ranges: list[float] = []
    for index in range(1, len(klines)):
        high = klines[index]["high"]
        low = klines[index]["low"]
        previous_close = klines[index - 1]["close"]
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return sum(true_ranges[-period:]) / period


def annualized_volatility(closes: list[float], period: int = 20) -> float | None:
    if len(closes) < period + 1:
        return None
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - period, len(closes))]
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252)


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def analyze(klines: list[dict], meta: dict | None = None) -> dict:
    meta = meta or {}
    closes = [row["close"] for row in klines]
    if len(closes) < 2:
        return {"error": "insufficient kline data"}

    sma5 = sma(closes, 5)
    sma10 = sma(closes, 10)
    sma20 = sma(closes, 20)
    sma60 = sma(closes, 60)
    macd_values = macd(closes)
    rsi14 = rsi(closes, 14)
    bands = bollinger(closes)
    atr14 = atr(klines, 14)
    price = closes[-1]
    previous = closes[-2]

    change_1d = (price / previous - 1) * 100 if previous else 0
    change_5d = (price / closes[-6] - 1) * 100 if len(closes) >= 6 and closes[-6] else 0
    change_20d = (price / closes[-21] - 1) * 100 if len(closes) >= 21 and closes[-21] else 0
    change_60d = (price / closes[-61] - 1) * 100 if len(closes) >= 61 and closes[-61] else 0
    vol20 = annualized_volatility(closes, 20)
    atr_pct = (atr14 / price * 100) if atr14 and price else 0

    trend_points = 0
    if sma5 and sma10 and sma20:
        trend_points += int(sma5 > sma10) + int(sma10 > sma20) + int(price > sma20)
        if sma20 and sma60:
            trend_points += int(sma20 > sma60)
        if macd_values["histogram"] is not None and macd_values["histogram"] > 0:
            trend_points += 1
    trend_score = round(trend_points / 5 * 100, 1)

    if rsi14 is None:
        momentum_score = 50.0
    elif 48 <= rsi14 <= 62:
        momentum_score = 82.0
    elif 42 <= rsi14 <= 70:
        momentum_score = 68.0
    elif rsi14 < 30 or rsi14 > 80:
        momentum_score = 32.0
    else:
        momentum_score = 50.0
    if change_20d > 5:
        momentum_score = _clamp(momentum_score + 12)
    elif change_20d < -5:
        momentum_score = _clamp(momentum_score - 10)

    vol_target = {"fx": 0.06, "fund": 0.14, "a-share": 0.22}
    target = vol_target.get(meta.get("market", ""), 0.28)
    if vol20 is None:
        volatility_score = 50.0
    elif vol20 <= target * 0.8:
        volatility_score = 72.0
    elif vol20 <= target * 1.15:
        volatility_score = 86.0
    elif vol20 <= target * 1.6:
        volatility_score = 58.0
    else:
        volatility_score = 34.0

    risk = meta.get("base_risk", 0.65)
    risk_score = round((1 - risk) * 100, 1)

    macro_score = float(meta.get("macro_score", 55))
    total = round(
        trend_score * 0.30
        + momentum_score * 0.25
        + volatility_score * 0.15
        + risk_score * 0.15
        + macro_score * 0.15,
        1,
    )

    signals: list[str] = []
    if sma5 and sma20 and sma5 > sma20:
        signals.append("短期均线占优")
    if macd_values["histogram"] is not None and macd_values["histogram"] > 0:
        signals.append("MACD 动能转强")
    if rsi14 is not None and 45 <= rsi14 <= 65:
        signals.append("RSI 处于强势区")
    if change_20d > 3:
        signals.append("20 日动量为正")
    if bands["bandwidth"] is not None and bands["bandwidth"] < 0.08:
        signals.append("波动收窄待突破")
    if atr_pct and atr_pct < 1.8 and meta.get("market") not in ("crypto",):
        signals.append("波动率偏低")
    if macro_score >= 70:
        signals.append("宏观因子偏多")
    elif macro_score <= 40:
        signals.append("宏观因子偏空")

    return {
        "price": round(price, 4),
        "change_1d": round(change_1d, 2),
        "change_5d": round(change_5d, 2),
        "change_20d": round(change_20d, 2),
        "change_60d": round(change_60d, 2),
        "sma5": round(sma5, 4) if sma5 is not None else None,
        "sma10": round(sma10, 4) if sma10 is not None else None,
        "sma20": round(sma20, 4) if sma20 is not None else None,
        "sma60": round(sma60, 4) if sma60 is not None else None,
        "macd": round(macd_values["macd"], 4) if macd_values["macd"] is not None else None,
        "macd_signal": round(macd_values["signal"], 4) if macd_values["signal"] is not None else None,
        "macd_hist": round(macd_values["histogram"], 4) if macd_values["histogram"] is not None else None,
        "rsi14": rsi14,
        "boll": bands,
        "atr14": round(atr14, 4) if atr14 is not None else None,
        "atr_pct": round(atr_pct, 2),
        "volatility20": round(vol20, 4) if vol20 is not None else None,
        "trend_score": trend_score,
        "momentum_score": round(momentum_score, 1),
        "volatility_score": volatility_score,
        "risk_score": risk_score,
        "macro_score": macro_score,
        "total_score": total,
        "signals": signals,
    }

