"""
Smoke test — genera datos sintéticos y corre todos los detectores + scorer.
Valida que no haya errores de sintaxis, tipos o dimensiones.

No valida que las reglas sean correctas — eso lo haces tú viendo los resultados sobre datos reales.
"""

import numpy as np
import pandas as pd
import json

from signal_detectors import detect_all_signals
from setup_scorer import compute_expected_bias, compute_hidden_outcome, compute_educational_score


def make_synthetic_chart(n_bars: int = 150, trend: str = "up", seed: int = 42) -> pd.DataFrame:
    """
    Genera datos OHLCV sintéticos con tendencia controlada.
    
    trend: 'up' / 'down' / 'sideways' / 'volatile'
    """
    rng = np.random.default_rng(seed)
    base_price = 100.0

    if trend == "up":
        drift = 0.003  # +0.3% por vela de media
        vol = 0.008
    elif trend == "down":
        drift = -0.003
        vol = 0.008
    elif trend == "sideways":
        drift = 0.0
        vol = 0.005
    elif trend == "volatile":
        drift = 0.001
        vol = 0.025
    else:
        drift, vol = 0.0, 0.005

    # Random walk con drift
    returns = rng.normal(drift, vol, n_bars)
    closes = base_price * np.exp(np.cumsum(returns))

    # Generar OHLCV a partir de los closes
    opens = np.roll(closes, 1)
    opens[0] = base_price
    # Highs y lows con rango random
    ranges = np.abs(rng.normal(0, 0.006, n_bars)) * closes
    highs = np.maximum(opens, closes) + ranges * 0.5
    lows = np.minimum(opens, closes) - ranges * 0.5
    volumes = rng.uniform(1000, 5000, n_bars) * (1 + 0.3 * rng.standard_normal(n_bars))
    volumes = np.clip(volumes, 100, None)

    df = pd.DataFrame({
        "ts": pd.date_range("2024-01-01", periods=n_bars, freq="h"),
        "o": opens, "h": highs, "l": lows, "c": closes, "v": volumes,
    })
    return df


def run_test(trend_name: str, n_visible: int = 147, n_hidden: int = 12):
    print(f"\n{'═' * 60}")
    print(f"  Trend: {trend_name.upper()}")
    print(f"{'═' * 60}")

    full = make_synthetic_chart(n_bars=n_visible + n_hidden, trend=trend_name)
    df_visible = full.iloc[:n_visible]
    df_hidden = full.iloc[n_visible:]

    signals = detect_all_signals(df_visible)
    print("\nSeñales detectadas:")
    for name, data in signals.items():
        print(f"  {name:22s} → {data['state']:30s} [{data.get('confidence', '?')}]")

    bias = compute_expected_bias(signals)
    print(f"\nBias: score={bias['score']:+d}, direction={bias['direction']}, strength={bias['strength']}")

    entry_price = df_visible["c"].iloc[-1]
    outcome = compute_hidden_outcome(df_hidden, entry_price)
    print(f"\nOutcome: direction={outcome['direction']}, pct_change={outcome['pct_change']}%, whipsaw={outcome.get('whipsaw')}")

    edu = compute_educational_score(bias, outcome)
    print(f"\nEducational score: {edu['score']}/100 (coherence: {edu['coherence']})")
    print(f"  Breakdown: {edu['breakdown']}")


if __name__ == "__main__":
    print("═══ COTD Detectors Smoke Test ═══\n")
    print("Objetivo: validar que los detectores corren sin errores en datos sintéticos.")
    print("No valida que las reglas sean 'correctas' — eso lo harás viendo resultados reales.")

    for trend in ["up", "down", "sideways", "volatile"]:
        run_test(trend)

    print("\n═══ Smoke test completado ═══")
