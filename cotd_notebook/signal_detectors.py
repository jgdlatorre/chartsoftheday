"""
COTD Signal Detectors · Rule-based, auditable, zero ML.

Cada detector recibe un DataFrame OHLCV con las columnas estándar:
    ts (datetime), o (open), h (high), l (low), c (close), v (volume)

Y retorna un dict con:
    - state: valor categórico (ej. "bullish" / "bearish" / "sideways")
    - detail: información adicional opcional (ej. magnitud, índice de la vela clave)
    - confidence: 'strong' / 'moderate' / 'weak' — cuán clara es la señal

Las reglas están documentadas en cada función para que compliance/editorial
puedan auditarlas sin leer código.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any


# ════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════

def _sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=period, min_periods=period).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI (Wilder's smoothing) — same formula as the client."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(avg_loss > 0, 100)  # if no losses, RSI = 100
    return rsi


def _linear_slope(series: pd.Series) -> float:
    """Pendiente normalizada (% sobre el valor medio) de una regresión lineal.

    Útil para medir dirección de tendencia sin depender de la escala del precio.
    """
    y = series.dropna().values
    if len(y) < 3:
        return 0.0
    x = np.arange(len(y))
    slope, _ = np.polyfit(x, y, 1)
    mean_val = y.mean()
    if mean_val == 0:
        return 0.0
    # Normalizar: ¿qué % del valor medio representa la pendiente por vela?
    return (slope / mean_val) * 100


# ════════════════════════════════════════════════════════════════════
# 1. TREND DIRECTION — Tendencia direccional
# ════════════════════════════════════════════════════════════════════

def detect_trend_direction(df: pd.DataFrame, lookback: int = 20) -> Dict[str, Any]:
    """
    Dirección de tendencia reciente medida por pendiente de regresión lineal
    sobre los últimos `lookback` cierres.

    Umbrales (en % de pendiente por vela respecto a la media):
        slope > +0.15%     → bullish_strong
        +0.05% < s ≤ 0.15% → bullish
        -0.05% ≤ s ≤ 0.05% → sideways
        -0.15% ≤ s < -0.05%→ bearish
        slope < -0.15%     → bearish_strong

    Estos umbrales son arbitrarios pero defendibles. Se ajustan tras ver muestras reales.
    """
    if len(df) < lookback:
        return {"state": "unknown", "detail": None, "confidence": "weak"}

    closes = df["c"].iloc[-lookback:]
    slope_pct = _linear_slope(closes)

    if slope_pct > 0.15:
        state = "bullish_strong"
    elif slope_pct > 0.05:
        state = "bullish"
    elif slope_pct >= -0.05:
        state = "sideways"
    elif slope_pct >= -0.15:
        state = "bearish"
    else:
        state = "bearish_strong"

    confidence = "strong" if abs(slope_pct) > 0.15 else ("moderate" if abs(slope_pct) > 0.05 else "weak")

    return {
        "state": state,
        "detail": {"slope_pct_per_candle": round(slope_pct, 4), "lookback": lookback},
        "confidence": confidence,
    }


# ════════════════════════════════════════════════════════════════════
# 2. RECENT MOMENTUM — Momentum del precio reciente
# ════════════════════════════════════════════════════════════════════

def detect_recent_momentum(df: pd.DataFrame, window: int = 5) -> Dict[str, Any]:
    """
    Momentum de las últimas `window` velas.

    Medido combinando:
    - Ratio de velas alcistas vs bajistas
    - Rango medio (cuerpo) de las velas comparado con el histórico

    Estados:
        accelerating_up   → 4/5+ velas alcistas con cuerpo creciente
        accelerating_down → 4/5+ velas bajistas con cuerpo creciente
        mixed             → ~50/50, cuerpos normales
        indecisive        → cuerpos muy pequeños comparados con histórico (dojis)
        exhausted_up      → alcistas pero cuerpos decrecientes
        exhausted_down    → bajistas pero cuerpos decrecientes
    """
    if len(df) < window + 20:
        return {"state": "unknown", "detail": None, "confidence": "weak"}

    recent = df.iloc[-window:]
    bodies = (recent["c"] - recent["o"]).abs()
    bullish_count = ((recent["c"] > recent["o"]).sum())
    bearish_count = ((recent["c"] < recent["o"]).sum())

    # Cuerpo medio reciente vs cuerpo medio histórico (20 velas previas a las recientes)
    hist_bodies = (df["c"].iloc[-window-20:-window] - df["o"].iloc[-window-20:-window]).abs()
    avg_recent_body = bodies.mean()
    avg_hist_body = hist_bodies.mean() if len(hist_bodies) > 0 else avg_recent_body
    body_ratio = avg_recent_body / avg_hist_body if avg_hist_body > 0 else 1.0

    # Dirección dominante
    if bullish_count >= window - 1:
        direction = "up"
    elif bearish_count >= window - 1:
        direction = "down"
    else:
        direction = "mixed"

    # Tendencia de cuerpos (crecientes o decrecientes)
    first_half_avg = bodies.iloc[:window//2].mean()
    second_half_avg = bodies.iloc[window//2:].mean()
    body_trend = "rising" if second_half_avg > first_half_avg * 1.15 else (
        "falling" if second_half_avg < first_half_avg * 0.85 else "flat"
    )

    # Clasificación
    if body_ratio < 0.4:
        state = "indecisive"  # velas muy pequeñas
    elif direction == "up" and body_trend == "rising":
        state = "accelerating_up"
    elif direction == "down" and body_trend == "rising":
        state = "accelerating_down"
    elif direction == "up" and body_trend == "falling":
        state = "exhausted_up"
    elif direction == "down" and body_trend == "falling":
        state = "exhausted_down"
    else:
        state = "mixed"

    return {
        "state": state,
        "detail": {
            "bullish_candles": int(bullish_count),
            "bearish_candles": int(bearish_count),
            "body_ratio_vs_hist": round(body_ratio, 2),
            "body_trend": body_trend,
        },
        "confidence": "strong" if state in ("accelerating_up", "accelerating_down", "indecisive") else "moderate",
    }


# ════════════════════════════════════════════════════════════════════
# 3. VOLUME RELATIVE — Volumen relativo
# ════════════════════════════════════════════════════════════════════

def detect_volume_relative(df: pd.DataFrame, recent: int = 5, hist: int = 20) -> Dict[str, Any]:
    """
    Volumen reciente comparado con volumen histórico.

    Estados:
        climactic  → volumen reciente > 2.5x del histórico (pico extremo)
        rising     → volumen reciente > 1.3x del histórico
        normal     → entre 0.7x y 1.3x
        falling    → volumen reciente < 0.7x del histórico
        dry        → volumen reciente < 0.4x del histórico (mercado seco)
    """
    if len(df) < recent + hist:
        return {"state": "unknown", "detail": None, "confidence": "weak"}

    recent_vol = df["v"].iloc[-recent:].mean()
    hist_vol = df["v"].iloc[-recent-hist:-recent].mean()

    if hist_vol == 0:
        return {"state": "unknown", "detail": None, "confidence": "weak"}

    ratio = recent_vol / hist_vol

    if ratio > 2.5:
        state = "climactic"
    elif ratio > 1.3:
        state = "rising"
    elif ratio >= 0.7:
        state = "normal"
    elif ratio >= 0.4:
        state = "falling"
    else:
        state = "dry"

    confidence = "strong" if ratio > 2.0 or ratio < 0.5 else "moderate"

    return {
        "state": state,
        "detail": {"ratio": round(ratio, 2), "recent_avg": float(recent_vol), "hist_avg": float(hist_vol)},
        "confidence": confidence,
    }


# ════════════════════════════════════════════════════════════════════
# 4. PRICE VS MA25 — Precio respecto a la media móvil 25
# ════════════════════════════════════════════════════════════════════

def detect_price_vs_ma25(df: pd.DataFrame, period: int = 25) -> Dict[str, Any]:
    """
    Posición del último precio respecto a MA25, medida como distancia % estandarizada.

    Estados:
        far_above    → precio > MA25 + 1.5 desviaciones
        above        → precio > MA25 (distancia normal)
        touching     → precio dentro de ±0.3 desv de MA25
        below        → precio < MA25
        far_below    → precio < MA25 - 1.5 desviaciones
    """
    if len(df) < period + 10:
        return {"state": "unknown", "detail": None, "confidence": "weak"}

    ma25 = _sma(df["c"], period)
    last_price = df["c"].iloc[-1]
    last_ma = ma25.iloc[-1]

    if pd.isna(last_ma) or last_ma == 0:
        return {"state": "unknown", "detail": None, "confidence": "weak"}

    # Calculamos la desviación típica de la distancia precio-MA25 en las últimas N velas,
    # para normalizar la distancia actual.
    recent_distances = (df["c"] - ma25).iloc[-30:].dropna()
    std_distance = recent_distances.std()
    if std_distance == 0 or pd.isna(std_distance):
        std_distance = last_ma * 0.01  # fallback: 1% del precio

    distance = last_price - last_ma
    z_score = distance / std_distance

    if z_score > 1.5:
        state = "far_above"
    elif z_score > 0.3:
        state = "above"
    elif z_score >= -0.3:
        state = "touching"
    elif z_score >= -1.5:
        state = "below"
    else:
        state = "far_below"

    pct_distance = (distance / last_ma) * 100

    return {
        "state": state,
        "detail": {"z_score": round(z_score, 2), "pct_distance": round(pct_distance, 2)},
        "confidence": "strong" if abs(z_score) > 1.0 else "moderate",
    }


# ════════════════════════════════════════════════════════════════════
# 5. MA CROSS 7/25 — Cruce entre MA(7) y MA(25)
# ════════════════════════════════════════════════════════════════════

def detect_ma_cross_7_25(df: pd.DataFrame, lookback: int = 10) -> Dict[str, Any]:
    """
    Cruce reciente de MA(7) sobre/bajo MA(25).

    Mira las últimas `lookback` velas buscando un cambio de signo en (MA7 - MA25).

    Estados:
        fresh_bullish_cross   → cruce alcista en las últimas 3 velas
        recent_bullish_cross  → cruce alcista en las últimas `lookback` velas
        fresh_bearish_cross   → cruce bajista en las últimas 3 velas
        recent_bearish_cross  → cruce bajista en las últimas `lookback` velas
        ma7_above_stable      → sin cruce, MA7 por encima de MA25
        ma7_below_stable      → sin cruce, MA7 por debajo de MA25
    """
    if len(df) < 25 + lookback:
        return {"state": "unknown", "detail": None, "confidence": "weak"}

    ma7 = _sma(df["c"], 7)
    ma25 = _sma(df["c"], 25)
    diff = (ma7 - ma25).iloc[-lookback:]

    if diff.isna().any():
        return {"state": "unknown", "detail": None, "confidence": "weak"}

    # Buscar cambios de signo
    signs = np.sign(diff.values)
    sign_changes = np.where(np.diff(signs) != 0)[0]  # índices donde cambia el signo

    last_sign = signs[-1]

    if len(sign_changes) == 0:
        state = "ma7_above_stable" if last_sign > 0 else "ma7_below_stable"
        bars_since_cross = None
    else:
        last_cross_idx = sign_changes[-1] + 1  # +1 porque np.diff reduce en 1
        bars_since_cross = len(signs) - 1 - last_cross_idx

        if last_sign > 0:  # MA7 ahora por encima → fue cruce alcista
            state = "fresh_bullish_cross" if bars_since_cross <= 3 else "recent_bullish_cross"
        else:
            state = "fresh_bearish_cross" if bars_since_cross <= 3 else "recent_bearish_cross"

    return {
        "state": state,
        "detail": {"bars_since_cross": bars_since_cross, "lookback": lookback},
        "confidence": "strong" if state.startswith("fresh") else "moderate",
    }


# ════════════════════════════════════════════════════════════════════
# 6. RSI ZONE — Zonas extremas del RSI
# ════════════════════════════════════════════════════════════════════

def detect_rsi_zone(df: pd.DataFrame, period: int = 14) -> Dict[str, Any]:
    """
    Zona actual del RSI(14).

    Estados:
        overbought_extreme → RSI > 80
        overbought        → RSI 70-80
        neutral_high      → RSI 55-70
        neutral           → RSI 45-55
        neutral_low       → RSI 30-45
        oversold          → RSI 20-30
        oversold_extreme  → RSI < 20
    """
    if len(df) < period + 5:
        return {"state": "unknown", "detail": None, "confidence": "weak"}

    rsi_series = _rsi(df["c"], period)
    last_rsi = rsi_series.iloc[-1]

    if pd.isna(last_rsi):
        return {"state": "unknown", "detail": None, "confidence": "weak"}

    if last_rsi > 80:
        state = "overbought_extreme"
    elif last_rsi >= 70:
        state = "overbought"
    elif last_rsi >= 55:
        state = "neutral_high"
    elif last_rsi >= 45:
        state = "neutral"
    elif last_rsi >= 30:
        state = "neutral_low"
    elif last_rsi >= 20:
        state = "oversold"
    else:
        state = "oversold_extreme"

    confidence = "strong" if last_rsi > 75 or last_rsi < 25 else (
        "moderate" if last_rsi > 65 or last_rsi < 35 else "weak"
    )

    return {
        "state": state,
        "detail": {"rsi_value": round(float(last_rsi), 1)},
        "confidence": confidence,
    }


# ════════════════════════════════════════════════════════════════════
# 7. SUPPORT / RESISTANCE — Niveles locales
# ════════════════════════════════════════════════════════════════════

def detect_support_resistance(df: pd.DataFrame, lookback: int = 50, touch_pct: float = 1.0) -> Dict[str, Any]:
    """
    Posición del último precio respecto a máximos/mínimos locales.

    NOTA METODOLÓGICA: hay múltiples definiciones de soporte/resistencia.
    Aquí usamos una SIMPLIFICACIÓN: el mínimo y máximo de las últimas `lookback` velas.
    Es una regla auditable pero limitada. Documentado explícitamente para compliance.

    Estados:
        breaking_resistance → precio hace nuevo máximo del periodo
        near_resistance     → precio dentro de `touch_pct` % del máximo
        mid_range           → precio en la parte media del rango
        near_support        → precio dentro de `touch_pct` % del mínimo
        breaking_support    → precio hace nuevo mínimo del periodo
    """
    if len(df) < lookback:
        return {"state": "unknown", "detail": None, "confidence": "weak"}

    window = df.iloc[-lookback:]
    high = window["h"].max()
    low = window["l"].min()
    last_price = df["c"].iloc[-1]

    if high == low:
        return {"state": "mid_range", "detail": None, "confidence": "weak"}

    # Posición relativa (0 = low, 1 = high)
    pos = (last_price - low) / (high - low)

    # ¿Está rompiendo? Comparamos con las primeras velas para saber si el high/low es realmente reciente
    if last_price > high * (1 - 0.001):  # dentro del 0.1% del máximo o rompiendo
        state = "breaking_resistance"
    elif last_price < low * (1 + 0.001):  # dentro del 0.1% del mínimo
        state = "breaking_support"
    elif last_price >= high * (1 - touch_pct / 100):
        state = "near_resistance"
    elif last_price <= low * (1 + touch_pct / 100):
        state = "near_support"
    else:
        state = "mid_range"

    confidence = "strong" if state in ("breaking_resistance", "breaking_support") else (
        "moderate" if state in ("near_resistance", "near_support") else "weak"
    )

    return {
        "state": state,
        "detail": {"high": float(high), "low": float(low), "position": round(pos, 2)},
        "confidence": confidence,
    }


# ════════════════════════════════════════════════════════════════════
# ORCHESTRATOR — detecta las 7 señales de una ventana
# ════════════════════════════════════════════════════════════════════

def detect_all_signals(df_visible: pd.DataFrame) -> Dict[str, Any]:
    """
    Ejecuta los 7 detectores sobre una ventana visible de un chart.

    Input: DataFrame con las velas que el usuario vería en COTD (zona visible).
    Output: dict con las 7 señales detectadas, cada una con su estado + detalles + confidence.
    """
    return {
        "trend_direction":    detect_trend_direction(df_visible),
        "recent_momentum":    detect_recent_momentum(df_visible),
        "volume_relative":    detect_volume_relative(df_visible),
        "price_vs_ma25":      detect_price_vs_ma25(df_visible),
        "ma_cross_7_25":      detect_ma_cross_7_25(df_visible),
        "rsi_zone":           detect_rsi_zone(df_visible),
        "support_resistance": detect_support_resistance(df_visible),
    }
