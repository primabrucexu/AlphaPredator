from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MacdPoint:
    ema8: float
    ema17: float
    dif: float
    dea: float
    hist: float


def compute_ema_series(values: list[float], span: int) -> list[float]:
    alpha = 2.0 / (span + 1)
    result = [0.0] * len(values)
    if not values:
        return result
    result[0] = values[0]
    for idx in range(1, len(values)):
        result[idx] = alpha * values[idx] + (1 - alpha) * result[idx - 1]
    return result


def compute_macd_points(closes: list[float]) -> list[MacdPoint]:
    if not closes:
        return []
    ema8 = compute_ema_series(closes, 8)
    ema17 = compute_ema_series(closes, 17)
    dif = [ema8[idx] - ema17[idx] for idx in range(len(closes))]
    dea = compute_ema_series(dif, 6)
    return [
        MacdPoint(
            ema8=ema8[idx],
            ema17=ema17[idx],
            dif=dif[idx],
            dea=dea[idx],
            hist=(dif[idx] - dea[idx]) * 2,
        )
        for idx in range(len(closes))
    ]
