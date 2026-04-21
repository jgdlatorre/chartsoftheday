"""
CandleEye · data_prep.py

One-time script: reads 1-min parquets from Binance dataset, resamples to
multiple timeframes (1h, 4h, 1d), and writes one CSV per asset per timeframe
into ./data_1h/, ./data_4h/, ./data_1d/.

Usage:
    python data_prep.py

Run from the candleeye/ project root.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

PARQUET_DIR = Path("/Users/vandetoren/Documents/Vandetoren/data/binance_1min_data/USDT")
ROOT = Path(__file__).parent

TIMEFRAMES = {
    "1h": {"rule": "1h", "out": ROOT / "data_1h", "min_bars": 400},
    "4h": {"rule": "4h", "out": ROOT / "data_4h", "min_bars": 400},
    "1d": {"rule": "1D", "out": ROOT / "data_1d", "min_bars": 350},
}
for tf in TIMEFRAMES.values():
    tf["out"].mkdir(exist_ok=True)

TOP10 = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    "ADAUSDT", "DOGEUSDT", "LTCUSDT", "LINKUSDT", "DOTUSDT",
]


def _standardize(df: pd.DataFrame) -> pd.DataFrame:
    """Return df with DatetimeIndex named 'timestamp' and OHLCV columns."""
    if not isinstance(df.index, pd.DatetimeIndex):
        for cand in ("timestamp", "open_time", "date", "time"):
            if cand in df.columns:
                df = df.set_index(cand)
                break
    df.index = (
        pd.to_datetime(df.index, utc=True).tz_convert(None)
        if getattr(df.index, "tz", None)
        else pd.to_datetime(df.index)
    )
    df.index.name = "timestamp"

    rename_map = {}
    for c in df.columns:
        lc = c.lower()
        if lc in ("open", "o"): rename_map[c] = "open"
        elif lc in ("high", "h"): rename_map[c] = "high"
        elif lc in ("low", "l"): rename_map[c] = "low"
        elif lc in ("close", "c"): rename_map[c] = "close"
        elif lc in ("volume", "v", "vol"): rename_map[c] = "volume"
    df = df.rename(columns=rename_map)

    needed = ["open", "high", "low", "close", "volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}. Got: {list(df.columns)}")

    return df[needed].sort_index()


def resample(df_1min: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    return df_1min.resample(rule).agg(agg).dropna()


def process_one(symbol: str) -> tuple[int, list[str]]:
    path = PARQUET_DIR / f"{symbol}.parquet"
    if not path.exists():
        return 0, [f"not found: {path.name}"]
    try:
        df_1m = _standardize(pd.read_parquet(path))
    except Exception as e:
        return 0, [f"error loading: {e.__class__.__name__}: {e}"]

    msgs = []
    ok = 0
    for tf_name, conf in TIMEFRAMES.items():
        t0 = time.time()
        try:
            df = resample(df_1m, conf["rule"])
            if len(df) < conf["min_bars"]:
                msgs.append(f"{tf_name}: only {len(df)} bars (<{conf['min_bars']})")
                continue
            out = conf["out"] / f"{symbol}.csv"
            df.to_csv(out, index=True, float_format="%.8g")
            dt = time.time() - t0
            msgs.append(f"{tf_name}: {len(df):>6} bars · {dt:4.1f}s")
            ok += 1
        except Exception as e:
            msgs.append(f"{tf_name}: {e.__class__.__name__}: {e}")
    return ok, msgs


def main():
    if not PARQUET_DIR.exists():
        print(f"ERROR: parquet dir does not exist: {PARQUET_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"source: {PARQUET_DIR}")
    print(f"outputs: {', '.join(str(t['out'].name) for t in TIMEFRAMES.values())}")
    print(f"processing {len(TOP10)} symbols × {len(TIMEFRAMES)} timeframes\n")

    total_ok = 0
    for sym in TOP10:
        ok, msgs = process_one(sym)
        print(f"  {sym:10}  " + "  ".join(msgs))
        total_ok += ok

    print(f"\ndone: {total_ok} CSVs written across {len(TIMEFRAMES)} timeframes")
    if total_ok == 0:
        print("nothing written. check parquet path and column names.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
