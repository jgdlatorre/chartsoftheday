"""
Build edu_pool.json from the 35 curated setup JSONs.

Input:
    --notes-dir <path>   directory with setup_01_*.json..setup_35_*.json
                         each file must have top-level:
                           symbol, timeframe (anchor TF), decision_ts,
                           pedagogical_notes: {tooltip:{es,en,zh}, holistic:{es,en,zh}}

For each setup (in numeric order 01..35):
  - Load CSVs for all three TFs of that symbol
  - Anchor at the setup's (timeframe, decision_ts)
  - For the anchor TF: locate the exact row
  - For the other two TFs: searchsorted(decision_ts) to find the equivalent bar
  - Slice WARMUP+CONTEXT behind (inclusive) and FUTURE ahead
  - Compute entry_price / exit_price / truth per TF
  - Emit a section with the same schema as sections_pool.json entries, plus
    pedagogical_notes and anchor_tf

Output:
    candleeye/edu_pool.json  (committed to repo; server reads at boot)

Usage:
    python build_edu_pool.py --notes-dir cotd_notebook/samples_with_notes/
    python build_edu_pool.py --notes-dir <path> --out edu_pool.json --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
DATA_DIRS = {
    "1h": ROOT / "data_1h",
    "4h": ROOT / "data_4h",
    "1d": ROOT / "data_1d",
}

# Must match server.py
WARMUP_BARS = 200
CONTEXT_BARS = 80
FUTURE_BARS = 48
MIN_WINDOW = WARMUP_BARS + CONTEXT_BARS + FUTURE_BARS  # 328
# Floor for adaptive warmup when CSV history before decision_ts is short.
# MA(7)/MA(25) fully defined after 25 bars; MA(99) stabilizes after 99 bars.
# Setting floor at 50 keeps curve/RSI meaningful while allowing early-history setups.
MIN_WARMUP_BARS = 50

SETUP_FILE_RE = re.compile(r"^setup_(\d{2})_.*\.json$")


def compact_bar(row) -> dict:
    """Match the on-disk section bar format used by sections_pool.json."""
    return {
        "ts": row.timestamp.isoformat() if hasattr(row.timestamp, "isoformat") else str(row.timestamp),
        "o": round(float(row.open), 8),
        "h": round(float(row.high), 8),
        "l": round(float(row.low), 8),
        "c": round(float(row.close), 8),
        "v": round(float(row.volume), 4),
    }


def load_tf_df(symbol: str, tf: str) -> pd.DataFrame:
    f = DATA_DIRS[tf] / f"{symbol}.csv"
    if not f.exists():
        raise FileNotFoundError(f"missing CSV for {symbol} {tf}: {f}")
    df = pd.read_csv(f, parse_dates=["timestamp"])
    return df.sort_values("timestamp").reset_index(drop=True)


def slice_tf(df: pd.DataFrame, decision_ts: pd.Timestamp, tf_name: str) -> dict:
    """Slice a WARMUP+CONTEXT+FUTURE window around decision_ts on this TF.
    Returns a dict with the same shape the server expects per-TF section entry:
      {bars: [...], warmup_count, context_count, entry_price, exit_price, truth,
       decision_ts, exit_ts}.
    """
    ts = df["timestamp"]
    pos = int(ts.searchsorted(decision_ts, side="right")) - 1
    if pos < 0:
        raise ValueError(f"{tf_name}: decision_ts {decision_ts} before first bar")
    future_end = pos + FUTURE_BARS
    if future_end >= len(df):
        raise ValueError(f"{tf_name}: not enough future bars after {decision_ts}")

    # Adaptive warmup: use full WARMUP_BARS when history allows, otherwise shrink
    # down to MIN_WARMUP_BARS. If even the floor can't fit + CONTEXT, give up.
    bars_before = pos + 1  # including the decision bar
    available_warmup = bars_before - CONTEXT_BARS
    if available_warmup < MIN_WARMUP_BARS:
        raise ValueError(
            f"{tf_name}: only {available_warmup} warmup bars available before "
            f"{decision_ts} (need >= {MIN_WARMUP_BARS})"
        )
    effective_warmup = min(WARMUP_BARS, available_warmup)
    desired_start = pos - (effective_warmup + CONTEXT_BARS) + 1

    bars_df = df.iloc[desired_start : future_end + 1]
    bars = [compact_bar(r) for r in bars_df.itertuples(index=False)]

    entry_price = float(df["close"].iat[pos])
    exit_price = float(df["close"].iat[future_end])
    truth = "long" if exit_price > entry_price else "short"

    return {
        "bars": bars,
        "warmup_count": effective_warmup,
        "context_count": CONTEXT_BARS,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "truth": truth,
        "decision_ts": df["timestamp"].iat[pos].isoformat(),
        "exit_ts": df["timestamp"].iat[future_end].isoformat(),
    }


def build_section(setup: dict) -> dict:
    symbol = setup["symbol"]
    anchor_tf = setup["timeframe"]
    decision_ts = pd.Timestamp(setup["decision_ts"])
    notes = setup.get("pedagogical_notes", {}) or {}

    tfs_out: dict[str, dict] = {}
    for tf_name in DATA_DIRS.keys():
        df = load_tf_df(symbol, tf_name)
        tfs_out[tf_name] = slice_tf(df, decision_ts, tf_name)

    # The canonical "decision_ts_1h" in sections_pool.json is the 1h-TF decision ts.
    # We preserve that for compatibility with build_round_from_section.
    decision_ts_1h = tfs_out["1h"]["decision_ts"]

    return {
        "symbol": symbol,
        "decision_ts_1h": decision_ts_1h,
        "anchor_tf": anchor_tf,
        "pedagogical_notes": notes,
        "tfs": tfs_out,
    }


def iter_setups(notes_dir: Path):
    """Yield (ordinal, path) in numeric order setup_01..setup_35."""
    files = []
    for p in notes_dir.iterdir():
        m = SETUP_FILE_RE.match(p.name)
        if m:
            files.append((int(m.group(1)), p))
    files.sort()
    return files


def validate_notes(pn) -> list[str]:
    """Return list of problems; empty means OK."""
    problems = []
    if not isinstance(pn, dict) or not pn:
        problems.append("pedagogical_notes missing or empty")
        return problems
    for key in ("tooltip", "holistic"):
        block = pn.get(key)
        if not isinstance(block, dict):
            problems.append(f"missing pedagogical_notes.{key}")
            continue
        for lang in ("es", "en", "zh"):
            v = block.get(lang)
            # Threshold ≥4 covers dense Chinese (e.g. "趋势持续下跌。" = 7 chars is a full sentence)
            # while still rejecting empty strings and trivial values like "ok".
            if not isinstance(v, str) or len(v.strip()) < 4:
                problems.append(f"pedagogical_notes.{key}.{lang} empty")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notes-dir", required=True, help="directory with populated setup_NN_*.json")
    ap.add_argument("--out", default=str(ROOT / "edu_pool.json"), help="output path")
    ap.add_argument("--dry-run", action="store_true", help="don't write the file")
    ap.add_argument("--strict-notes", action="store_true",
                    help="fail if any pedagogical_notes is empty or missing a language")
    args = ap.parse_args()

    notes_dir = Path(args.notes_dir)
    if not notes_dir.is_dir():
        print(f"ERROR: {notes_dir} is not a directory", file=sys.stderr)
        sys.exit(2)

    setups = iter_setups(notes_dir)
    if len(setups) != 35:
        print(f"WARNING: expected 35 setups, found {len(setups)}", file=sys.stderr)

    sections = []
    errors = []
    for ordinal, path in setups:
        with open(path) as f:
            setup = json.load(f)
        notes_problems = validate_notes(setup.get("pedagogical_notes"))
        if notes_problems:
            for p in notes_problems:
                errors.append(f"  [{path.name}] {p}")
            if args.strict_notes:
                continue
        try:
            section = build_section(setup)
            sections.append(section)
            # Per-TF effective warmup (may be < WARMUP_BARS for short-history setups)
            wmp = {tf: section["tfs"][tf]["warmup_count"] for tf in DATA_DIRS}
            anchor = setup["timeframe"]
            short = [tf for tf, w in wmp.items() if w < WARMUP_BARS]
            tag = ""
            if short:
                parts = [f"{tf}={wmp[tf]}{'*' if tf==anchor else ''}" for tf in ("1h","4h","1d")]
                tag = "  warmup[" + " ".join(parts) + "]"
            print(f"  ok  setup_{ordinal:02d}  {setup['symbol']} {setup['timeframe']} {setup['decision_ts']}{tag}")
        except Exception as e:
            errors.append(f"  [{path.name}] build failed: {e}")

    if errors:
        print("\nPROBLEMS:")
        for e in errors:
            print(e)
        if args.strict_notes and errors:
            print("\nstrict mode: aborting without writing", file=sys.stderr)
            sys.exit(3)

    payload = {
        "version": 1,
        "count": len(sections),
        "epoch": "2026-04-01",
        "sections": sections,
    }
    if args.dry_run:
        print(f"\ndry-run: would write {args.out} with {len(sections)} sections")
        return

    with open(args.out, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"\nwrote {args.out} with {len(sections)} sections")


if __name__ == "__main__":
    main()
