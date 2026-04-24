"""
COTD Setup Scanner — Notebook principal.

Este script:
1. Carga los datos OHLCV de los tokens permitidos
2. Para cada token, desliza una ventana estilo COTD (visible + oculto) sobre el histórico
3. Aplica los 7 detectores a la zona visible
4. Calcula el outcome real en la zona oculta
5. Puntúa cada setup por su valor educativo
6. Exporta los top candidatos a CSV/JSON para revisión editorial

Uso:
    python cotd_scanner.py --token ETHUSDT --timeframe 1h --top 20
    python cotd_scanner.py --all --top 50

Configuración COTD (debe coincidir con server.py):
    WARMUP_BARS    = 99   (necesarias para MA(99), no se ven)
    CONTEXT_BARS   = 48   (zona visible al usuario — el "70%")
    FUTURE_BARS    = 12   (zona oculta, outcome — el "30%")
"""

import argparse
import json
import pandas as pd
from pathlib import Path
from typing import Optional

from signal_detectors import detect_all_signals
from setup_scorer import compute_expected_bias, compute_hidden_outcome, compute_educational_score


# ════════════════════════════════════════════════════════════════════
# CONSTANTES (deben coincidir con server.py)
# ════════════════════════════════════════════════════════════════════

WARMUP_BARS = 99
CONTEXT_BARS = 48
FUTURE_BARS = 12
TOTAL_WINDOW = WARMUP_BARS + CONTEXT_BARS + FUTURE_BARS  # 159

# Paso entre ventanas (para no procesar cada una, evitar dataset denso)
STRIDE = 6

DATA_DIRS = {
    "1h": Path("../candleeye/data_1h"),
    "4h": Path("../candleeye/data_4h"),
    "1d": Path("../candleeye/data_1d"),
}


# ════════════════════════════════════════════════════════════════════
# LOADER
# ════════════════════════════════════════════════════════════════════

def load_token_data(symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
    """Carga el CSV de un símbolo/timeframe y devuelve un DataFrame con las columnas estándar."""
    data_dir = DATA_DIRS.get(timeframe)
    if data_dir is None:
        print(f"  ERROR: timeframe '{timeframe}' no reconocido")
        return None

    csv_path = data_dir / f"{symbol}.csv"
    if not csv_path.exists():
        print(f"  ERROR: no existe {csv_path}")
        return None

    # Se asume formato Binance estándar exportado por data_prep.py
    # Columnas: ts (unix ms o ISO), o, h, l, c, v
    df = pd.read_csv(csv_path)

    # Normalizar nombres de columnas (por si hay variaciones)
    col_map = {
        "timestamp": "ts", "time": "ts", "date": "ts", "Date": "ts", "Timestamp": "ts",
        "open": "o", "high": "h", "low": "l", "close": "c", "volume": "v",
        "Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v",
    }
    df = df.rename(columns=col_map)

    required = {"ts", "o", "h", "l", "c", "v"}
    missing = required - set(df.columns)
    if missing:
        print(f"  ERROR: faltan columnas en {csv_path}: {missing}")
        return None

    # Parsear timestamp (acepta ms unix, segundos unix, o ISO string)
    if pd.api.types.is_numeric_dtype(df["ts"]):
        sample = df["ts"].iloc[0]
        unit = "ms" if sample > 1e12 else "s"
        df["ts"] = pd.to_datetime(df["ts"], unit=unit)
    else:
        df["ts"] = pd.to_datetime(df["ts"])

    df = df.sort_values("ts").reset_index(drop=True)
    return df


# ════════════════════════════════════════════════════════════════════
# SCAN
# ════════════════════════════════════════════════════════════════════

def scan_token(symbol: str, timeframe: str, verbose: bool = False) -> pd.DataFrame:
    """
    Desliza una ventana COTD sobre el histórico del token y evalúa cada setup.

    Returns: DataFrame con una fila por setup candidato, incluyendo:
        - symbol, timeframe, start_ts, decision_ts, exit_ts
        - las 7 señales (una columna por señal)
        - bias score/direction/strength
        - outcome pct_change/direction/whipsaw
        - educational_score + coherence
    """
    df = load_token_data(symbol, timeframe)
    if df is None or len(df) < TOTAL_WINDOW:
        print(f"  {symbol} {timeframe}: insuficientes datos")
        return pd.DataFrame()

    rows = []
    total_windows = (len(df) - TOTAL_WINDOW) // STRIDE + 1
    if verbose:
        print(f"  {symbol} {timeframe}: {len(df)} velas, {total_windows} ventanas a analizar")

    for start in range(0, len(df) - TOTAL_WINDOW, STRIDE):
        window = df.iloc[start:start + TOTAL_WINDOW].reset_index(drop=True)

        # La zona visible al usuario es warmup + context (las primeras warmup NO se ven
        # pero sí se usan para calcular MAs y RSI)
        df_visible_full = window.iloc[:WARMUP_BARS + CONTEXT_BARS]  # 147 velas
        df_hidden = window.iloc[WARMUP_BARS + CONTEXT_BARS:]  # 12 velas

        entry_price = df_visible_full["c"].iloc[-1]

        # Detectar señales sobre la ventana visible (detectores usan warmup internamente si lo necesitan)
        signals = detect_all_signals(df_visible_full)

        # Calcular bias esperado
        bias = compute_expected_bias(signals)

        # Calcular outcome real
        outcome = compute_hidden_outcome(df_hidden, entry_price)

        # Score educativo
        edu = compute_educational_score(bias, outcome)

        row = {
            "symbol": symbol,
            "timeframe": timeframe,
            "start_ts": window["ts"].iloc[0],
            "decision_ts": df_visible_full["ts"].iloc[-1],
            "exit_ts": df_hidden["ts"].iloc[-1] if len(df_hidden) > 0 else None,
            "entry_price": float(entry_price),
            "exit_price": float(df_hidden["c"].iloc[-1]) if len(df_hidden) > 0 else None,
            # Señales (solo el state, para tabla legible)
            **{f"sig_{name}": data["state"] for name, data in signals.items()},
            # Bias
            "bias_score": bias["score"],
            "bias_direction": bias["direction"],
            "bias_strength": bias["strength"],
            # Outcome
            "outcome_direction": outcome["direction"],
            "outcome_pct": outcome.get("pct_change", 0),
            "outcome_whipsaw": outcome.get("whipsaw", False),
            # Score educativo
            "edu_score": edu["score"],
            "coherence": edu["coherence"],
        }
        # También guardamos las señales completas (con detail + confidence) en una columna JSON
        row["_signals_full"] = json.dumps({
            name: {"state": d["state"], "detail": d.get("detail"), "confidence": d.get("confidence")}
            for name, d in signals.items()
        }, default=str)

        rows.append(row)

    return pd.DataFrame(rows)


# ════════════════════════════════════════════════════════════════════
# RANKING + FILTROS
# ════════════════════════════════════════════════════════════════════

def rank_setups(df_all: pd.DataFrame, top_n: int = 20, min_score: int = 50) -> pd.DataFrame:
    """
    Ordena los setups y aplica cuotas + balance + diversidad.

    Objetivo pedagógico: el dataset visible debe reflejar que las señales fallan
    ~50% de las veces. Por eso NO ordenamos sólo por edu_score (eso nos daría
    top-N 100% confirmed, ya que confirmed puntúa +30 y contrarian +25).

    Estrategia:
    1) Filtro por min_score.
    2) Cuotas por coherence dentro del top_n:
         - ≥30% failed (contrarian + signal_ignored): las señales no funcionaron
         - ≥30% confirmed: las señales funcionaron
         - ~40% libre: se llena por edu_score sin restricción
       Dentro de cada cuota, balance direccional (up/down).
    3) Diversidad de símbolo: máx max(2, top_n // 5) por símbolo.
    """
    df = df_all[df_all["edu_score"] >= min_score].copy()
    if len(df) == 0:
        return df

    quota_failed = max(1, int(top_n * 0.3))
    quota_confirmed = max(1, int(top_n * 0.3))

    failed_pool = df[df["coherence"].isin(["contrarian", "signal_ignored"])]
    confirmed_pool = df[df["coherence"] == "confirmed"]

    def balanced_top(pool: pd.DataFrame, n: int) -> pd.DataFrame:
        """Top n balanceado direccionalmente (mitad up, mitad down por edu_score)."""
        up = pool[pool["outcome_direction"] == "up"].sort_values("edu_score", ascending=False)
        down = pool[pool["outcome_direction"] == "down"].sort_values("edu_score", ascending=False)
        half = n // 2
        return pd.concat([up.head(half), down.head(n - half)])

    failed_selected = balanced_top(failed_pool, quota_failed)
    confirmed_selected = balanced_top(confirmed_pool, quota_confirmed)

    # El ~40% libre se llena de lo que queda, por edu_score descendente
    already_selected_ids = set(failed_selected.index) | set(confirmed_selected.index)
    remaining_pool = df[~df.index.isin(already_selected_ids)]
    remaining_slots = top_n - len(failed_selected) - len(confirmed_selected)
    free_selected = remaining_pool.sort_values("edu_score", ascending=False).head(remaining_slots)

    combined = pd.concat([failed_selected, confirmed_selected, free_selected])

    # Diversidad de símbolo (aplicado al final sobre la unión)
    max_per_symbol = max(2, top_n // 5)
    diverse = combined.groupby("symbol").head(max_per_symbol).sort_values("edu_score", ascending=False)

    return diverse.head(top_n).reset_index(drop=True)


# ════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════

DEFAULT_TOKENS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    "ADAUSDT", "DOGEUSDT", "LTCUSDT", "LINKUSDT", "DOTUSDT",
]


def main():
    parser = argparse.ArgumentParser(description="COTD Setup Scanner")
    parser.add_argument("--token", help="Símbolo específico (ej. BTCUSDT). Omitir para escanear todos.")
    parser.add_argument("--timeframe", default="1h", choices=["1h", "4h", "1d"])
    parser.add_argument("--all", action="store_true", help="Escanear todos los tokens por defecto")
    parser.add_argument("--top", type=int, default=30, help="Top N candidatos a exportar")
    parser.add_argument("--min-score", type=int, default=50, help="Score mínimo para considerar")
    parser.add_argument("--output", default="cotd_candidates.csv", help="Archivo de salida")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.token:
        tokens = [args.token]
    else:
        tokens = DEFAULT_TOKENS

    print(f"═══ COTD Setup Scanner ═══")
    print(f"  Timeframe: {args.timeframe}")
    print(f"  Tokens: {len(tokens)}")
    print(f"  Ventana: warmup={WARMUP_BARS} + context={CONTEXT_BARS} + future={FUTURE_BARS}")
    print(f"  Stride: {STRIDE} velas entre ventanas")
    print()

    all_results = []
    for symbol in tokens:
        df_results = scan_token(symbol, args.timeframe, verbose=args.verbose)
        if len(df_results) > 0:
            all_results.append(df_results)
            print(f"  ✓ {symbol}: {len(df_results)} ventanas evaluadas, "
                  f"avg edu_score={df_results['edu_score'].mean():.1f}, "
                  f"max={df_results['edu_score'].max()}")

    if not all_results:
        print("\n⚠ No se obtuvieron resultados.")
        return

    df_all = pd.concat(all_results, ignore_index=True)
    print(f"\n═══ Total: {len(df_all)} setups candidatos ═══")

    # Distribución de scores
    print("\nDistribución de edu_score:")
    print(df_all["edu_score"].describe().to_string())

    # Ranking final
    top = rank_setups(df_all, top_n=args.top, min_score=args.min_score)
    print(f"\n═══ Top {len(top)} setups (min_score={args.min_score}) ═══")
    cols_preview = ["symbol", "decision_ts", "outcome_pct", "bias_direction", "coherence", "edu_score"]
    print(top[cols_preview].to_string(index=False))

    # Guardar
    top.to_csv(args.output, index=False)
    print(f"\n✓ Exportado a {args.output}")

    # También un JSON con la info completa para cada top setup
    json_output = args.output.replace(".csv", ".json")
    top_records = top.to_dict(orient="records")
    for r in top_records:
        # Deserializar el JSON interno para que el output final sea legible
        if "_signals_full" in r:
            r["signals_full"] = json.loads(r["_signals_full"])
            del r["_signals_full"]
        # Convertir timestamps a ISO
        for k in ("start_ts", "decision_ts", "exit_ts"):
            if r.get(k) is not None and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()

    with open(json_output, "w") as f:
        json.dump(top_records, f, indent=2, default=str)
    print(f"✓ JSON detallado en {json_output}")


if __name__ == "__main__":
    main()
