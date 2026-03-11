import numpy as np


def ema(values: np.ndarray, period: int) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if period <= 1:
        return values.copy()
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(values)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    close = np.asarray(close, dtype=float)
    if len(close) < 2:
        return np.zeros_like(close)
    delta = np.diff(close, prepend=close[0])
    gains = np.maximum(delta, 0.0)
    losses = np.maximum(-delta, 0.0)

    # Wilder smoothing
    avg_gain = np.zeros_like(close)
    avg_loss = np.zeros_like(close)
    avg_gain[0] = gains[0]
    avg_loss[0] = losses[0]
    for i in range(1, len(close)):
        avg_gain[i] = (avg_gain[i-1] * (period - 1) + gains[i]) / period
        avg_loss[i] = (avg_loss[i-1] * (period - 1) + losses[i]) / period

    rs = np.divide(avg_gain, avg_loss, out=np.zeros_like(avg_gain), where=avg_loss != 0)
    r = 100.0 - (100.0 / (1.0 + rs))
    return r
