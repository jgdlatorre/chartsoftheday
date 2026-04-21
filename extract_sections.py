"""
extract_sections.py — Pre-extract 100 self-contained round sections from the
full CSVs into a single sections_pool.json file (~1-2MB).

This lets us deploy to a tiny hosting tier (Railway free, Fly.io free) without
shipping 100-200MB of OHLCV CSVs. The server reads sections_pool.json at boot
and serves rounds from it. No further CSV access needed in production.

Usage:
    python extract_sections.py             # 100 sections (default)
    python extract_sections.py --n 200     # more sections

Output: sections_pool.json in the project root.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
DATA_DIRS = {
    "1h": ROOT / "data_1h",
    "4h": ROOT / "data_4h",
    "1d": ROOT / "data_1d",
}
OUTPUT = ROOT / "sections_pool.json"

CONTEXT_BARS = 80
FUTURE_BARS = 48
WARMUP_BARS = 200
MIN_WINDOW = WARMUP_BARS + CONTEXT_BARS + FUTURE_BARS

ALLOWED = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    "ADAUSDT", "DOGEUSDT", "LTCUSDT", "LINKUSDT", "DOTUSDT",
}


def load_csvs():
    primary = DATA_DIRS["1h"]
    if not primary.exists():
        print(f"ERROR: {primary} missing. Run data_prep.py first.", file=sys.stderr)
        sys.exit(1)
    datasets = {}
    symbols = sorted(f.stem for f in primary.glob("*.csv") if f.stem in ALLOWED)
    for symbol in symbols:
        tf_dfs = {}
        skip = False
        for tf_name, tf_dir in DATA_DIRS.items():
            f = tf_dir / f"{symbol}.csv"
            if not f.exists():
                skip = True
                break
            df = pd.read_csv(f, parse_dates=["timestamp"])
            df = df.sort_values("timestamp").reset_index(drop=True)
            if len(df) < MIN_WINDOW + 10:
                skip = True
                break
            tf_dfs[tf_name] = df
        if not skip:
            datasets[symbol] = tf_dfs
            print(f"  loaded {symbol}: "
                  f"{len(tf_dfs['1h'])} 1h, {len(tf_dfs['4h'])} 4h, {len(tf_dfs['1d'])} 1d bars")
    return datasets


def bars_to_list(df):
    """Serialize OHLCV dataframe window to list of compact dicts."""
    out = []
    for _, r in df.iterrows():
        out.append({
            "ts": r["timestamp"].isoformat(),
            "o": float(r["open"]),
            "h": float(r["high"]),
            "l": float(r["low"]),
            "c": float(r["close"]),
            "v": float(r["volume"]),
        })
    return out


def extract_one_section(symbol, tfs, rng):
    """Pick a single (symbol, decision_ts) and serialize all 3 TFs + future."""
    df_1h = tfs["1h"]
    max_start_1h = len(df_1h) - MIN_WINDOW - 1
    if max_start_1h <= 0:
        return None
    start_1h = rng.randint(0, max_start_1h)
    decision_idx_1h = start_1h + WARMUP_BARS + CONTEXT_BARS - 1
    decision_ts = df_1h["timestamp"].iat[decision_idx_1h]

    tfs_out = {}
    for tf_name, tf_df in tfs.items():
        ts = tf_df["timestamp"]
        pos = int(ts.searchsorted(decision_ts, side="right")) - 1
        if pos < 0:
            return None
        future_end = pos + FUTURE_BARS
        if future_end >= len(tf_df):
            return None
        desired_start = pos - (WARMUP_BARS + CONTEXT_BARS) + 1
        if desired_start < 0:
            # Not enough warmup for SMA 200 from the first context bar
            return None
        # Full context including warmup, plus future (for reveal phase)
        full_df = tf_df.iloc[desired_start : future_end + 1]
        entry_price = float(tf_df["close"].iat[pos])
        exit_price = float(tf_df["close"].iat[future_end])
        truth = "long" if exit_price > entry_price else "short"

        tfs_out[tf_name] = {
            "bars": bars_to_list(full_df),
            "warmup_count": WARMUP_BARS,
            "context_count": CONTEXT_BARS,
            "future_count": FUTURE_BARS,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "truth": truth,
            "decision_ts": tf_df["timestamp"].iat[pos].isoformat(),
            "exit_ts": tf_df["timestamp"].iat[future_end].isoformat(),
        }

    return {
        "symbol": symbol,
        "decision_ts_1h": decision_ts.isoformat(),
        "tfs": tfs_out,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100, help="number of sections to extract")
    ap.add_argument("--seed", type=int, default=None, help="RNG seed (default random)")
    args = ap.parse_args()

    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    datasets = load_csvs()
    if not datasets:
        print("ERROR: no datasets loaded.", file=sys.stderr)
        sys.exit(1)

    print(f"\nExtracting {args.n} sections...")
    sections = []
    attempts = 0
    max_attempts = args.n * 10
    while len(sections) < args.n and attempts < max_attempts:
        attempts += 1
        symbol = rng.choice(list(datasets.keys()))
        section = extract_one_section(symbol, datasets[symbol], rng)
        if section is not None:
            sections.append(section)
            if len(sections) % 10 == 0:
                print(f"  ...{len(sections)}/{args.n}")

    if len(sections) < args.n:
        print(f"WARNING: only extracted {len(sections)}/{args.n} sections after {attempts} attempts")

    payload = {
        "version": 1,
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "count": len(sections),
        "sections": sections,
    }
    with open(OUTPUT, "w") as f:
        json.dump(payload, f, separators=(',', ':'))

    size_kb = OUTPUT.stat().st_size / 1024
    print(f"\nWrote {OUTPUT} — {size_kb:.1f} KB, {len(sections)} sections")


if __name__ == "__main__":
    main()
