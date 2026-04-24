"""
COTD Setup Scorer — evalúa cuán "educativo" es un setup midiendo la coherencia
entre las señales visibles y el outcome oculto.

Filosofía:
- Un setup "perfecto" (correlación 100%) es aburrido: si leyendo las señales siempre aciertas, no hay juego
- Un setup "aleatorio" (correlación 0%) es injusto: las señales no sirven
- El sweet spot educativo está entre 55-75% de coherencia: el experto acierta más que el novato,
  pero no siempre, lo que refuerza el mensaje "rentabilidades pasadas no garantizan futuras"

Este scorer calcula:
1. Bias esperado por las señales visibles (sesgo alcista/bajista)
2. Outcome real en la zona oculta
3. Coherencia entre ambos
4. Score educativo final
"""

import pandas as pd
import numpy as np
from typing import Dict, Any


# ════════════════════════════════════════════════════════════════════
# 1. BIAS ESPERADO a partir de las señales visibles
# ════════════════════════════════════════════════════════════════════

# Cada estado contribuye un voto direccional:
#   +2 = fuerte alcista, +1 = leve alcista, 0 = neutral, -1 = leve bajista, -2 = fuerte bajista
# NOTA: estos pesos son heurísticos y editoriales. No son "verdad" técnica,
# representan la lectura convencional de análisis técnico.

SIGNAL_BIAS_WEIGHTS = {
    "trend_direction": {
        "bullish_strong": +2, "bullish": +1, "sideways": 0,
        "bearish": -1, "bearish_strong": -2, "unknown": 0,
    },
    "recent_momentum": {
        "accelerating_up": +2, "exhausted_up": -1,
        "accelerating_down": -2, "exhausted_down": +1,
        "mixed": 0, "indecisive": 0, "unknown": 0,
    },
    "volume_relative": {
        # El volumen no es direccional por sí mismo — modula otras señales.
        # Aquí lo tratamos como neutral en el bias.
        "climactic": 0, "rising": 0, "normal": 0, "falling": 0, "dry": 0, "unknown": 0,
    },
    "price_vs_ma25": {
        "far_above": +1, "above": +1, "touching": 0,
        "below": -1, "far_below": -1, "unknown": 0,
    },
    "ma_cross_7_25": {
        "fresh_bullish_cross": +2, "recent_bullish_cross": +1, "ma7_above_stable": +1,
        "fresh_bearish_cross": -2, "recent_bearish_cross": -1, "ma7_below_stable": -1,
        "unknown": 0,
    },
    "rsi_zone": {
        # RSI es contrarian en extremos: overbought sugiere posible reversión a la baja
        "overbought_extreme": -2, "overbought": -1,
        "neutral_high": +1, "neutral": 0, "neutral_low": -1,
        "oversold": +1, "oversold_extreme": +2,
        "unknown": 0,
    },
    "support_resistance": {
        "breaking_resistance": +2, "near_resistance": -1,  # cerca suele rebotar a la baja
        "mid_range": 0,
        "near_support": +1, "breaking_support": -2,
        "unknown": 0,
    },
}


def compute_expected_bias(signals: Dict[str, Any]) -> Dict[str, Any]:
    """
    Suma ponderada de los votos direccionales de cada señal.

    Output:
        - score: suma total (típicamente entre -10 y +10)
        - direction: 'bullish' / 'bearish' / 'neutral'
        - strength: 'weak' / 'moderate' / 'strong'
    """
    total = 0
    contributions = {}

    for signal_name, signal_data in signals.items():
        state = signal_data.get("state", "unknown")
        weight = SIGNAL_BIAS_WEIGHTS.get(signal_name, {}).get(state, 0)
        total += weight
        contributions[signal_name] = weight

    if total > 2:
        direction = "bullish"
    elif total < -2:
        direction = "bearish"
    else:
        direction = "neutral"

    abs_total = abs(total)
    if abs_total >= 5:
        strength = "strong"
    elif abs_total >= 3:
        strength = "moderate"
    else:
        strength = "weak"

    return {
        "score": total,
        "direction": direction,
        "strength": strength,
        "contributions": contributions,
    }


# ════════════════════════════════════════════════════════════════════
# 2. OUTCOME REAL en la zona oculta
# ════════════════════════════════════════════════════════════════════

def compute_hidden_outcome(df_hidden: pd.DataFrame, entry_price: float) -> Dict[str, Any]:
    """
    Calcula qué ocurrió en la zona oculta del chart.

    Input:
        df_hidden: DataFrame con las velas ocultas (el "futuro" que el usuario no ve)
        entry_price: precio de cierre de la última vela visible (punto de decisión)

    Output:
        - direction: 'up' / 'down' / 'flat'
        - pct_change: cambio % entry → exit (último precio oculto)
        - max_drawdown_pct: máxima caída desde entry durante la zona oculta
        - max_runup_pct: máxima subida desde entry durante la zona oculta
        - whipsaw: True si hubo tanto subida como bajada significativa
    """
    if len(df_hidden) == 0:
        return {"direction": "unknown", "pct_change": 0, "whipsaw": False}

    exit_price = df_hidden["c"].iloc[-1]
    highs = df_hidden["h"]
    lows = df_hidden["l"]

    pct_change = ((exit_price - entry_price) / entry_price) * 100
    max_runup_pct = ((highs.max() - entry_price) / entry_price) * 100
    max_drawdown_pct = ((lows.min() - entry_price) / entry_price) * 100

    # Umbrales para considerar "flat": movimiento final < 1%
    if pct_change > 1.0:
        direction = "up"
    elif pct_change < -1.0:
        direction = "down"
    else:
        direction = "flat"

    # Whipsaw: subió >3% Y bajó >3% en algún momento
    whipsaw = max_runup_pct > 3.0 and max_drawdown_pct < -3.0

    return {
        "direction": direction,
        "pct_change": round(pct_change, 2),
        "max_runup_pct": round(max_runup_pct, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "whipsaw": whipsaw,
    }


# ════════════════════════════════════════════════════════════════════
# 3. SCORE EDUCATIVO del setup
# ════════════════════════════════════════════════════════════════════

def compute_educational_score(bias: Dict[str, Any], outcome: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calcula el score educativo de un setup.

    Criterios:

    A) COHERENCIA DIRECCIONAL: ¿el outcome fue en la dirección esperada por las señales?
        - Alta coherencia (señales bullish + outcome up): pedagógico, enseña que leer funciona
        - Baja coherencia (señales bullish + outcome down): pedagógico, enseña humildad
        - Neutral + flat: poco interesante educativamente

    B) MAGNITUD DEL MOVIMIENTO: muy pequeño es aburrido, muy grande es outlier
        - Ideal: |pct_change| entre 2% y 15%

    C) FUERZA DE LAS SEÑALES: señales débiles dan poca materia para explicar
        - Ideal: bias strength 'moderate' o 'strong'

    D) AUSENCIA DE WHIPSAW EXTREMO: setups con whipsaw son difíciles de narrar
        - Penalización si whipsaw

    Score final: 0-100 (mayor = mejor para dataset educativo)
    """

    # Coherencia direccional
    bias_dir = bias["direction"]
    outcome_dir = outcome["direction"]
    pct = abs(outcome.get("pct_change", 0))

    # Normalizar vocabulario para comparación:
    # bias usa bullish/bearish/neutral, outcome usa up/down/flat → los unificamos
    _DIR_MAP = {"bullish": "up", "bearish": "down", "neutral": "flat",
                "up": "up", "down": "down", "flat": "flat"}
    bias_norm = _DIR_MAP.get(bias_dir, "flat")
    outcome_norm = _DIR_MAP.get(outcome_dir, "flat")

    # Mapa de coherencia
    if bias_norm == outcome_norm and bias_norm != "flat":
        coherence = "confirmed"
        coherence_score = 30
    elif bias_norm != "flat" and outcome_norm != "flat" and bias_norm != outcome_norm:
        coherence = "contrarian"
        coherence_score = 25  # ligeramente menos que confirmed, pero aún valioso pedagógicamente
    elif bias_norm == "flat" and outcome_norm == "flat":
        coherence = "both_neutral"
        coherence_score = 5  # aburrido
    elif bias_norm == "flat":
        coherence = "surprise_from_neutral"
        coherence_score = 15  # señales no claras pero algo pasó
    else:  # bias direccional, outcome flat
        coherence = "signal_ignored"
        coherence_score = 10  # las señales "fallaron"

    # Magnitud
    if 2.0 <= pct <= 15.0:
        magnitude_score = 25
    elif 1.0 <= pct < 2.0 or 15.0 < pct <= 25.0:
        magnitude_score = 15
    elif pct > 25.0:
        magnitude_score = 5  # outlier, poco educativo
    else:
        magnitude_score = 0  # movimiento despreciable

    # Fuerza de señales
    strength = bias["strength"]
    strength_score = {"strong": 25, "moderate": 20, "weak": 8}.get(strength, 0)

    # Whipsaw penalización
    whipsaw_penalty = -10 if outcome.get("whipsaw", False) else 0

    # Bonus por outcome informativo (no flat)
    direction_bonus = 10 if outcome_dir != "flat" else 0

    total = coherence_score + magnitude_score + strength_score + direction_bonus + whipsaw_penalty
    total = max(0, min(100, total))

    return {
        "score": total,
        "coherence": coherence,
        "breakdown": {
            "coherence_score": coherence_score,
            "magnitude_score": magnitude_score,
            "strength_score": strength_score,
            "direction_bonus": direction_bonus,
            "whipsaw_penalty": whipsaw_penalty,
        },
    }
