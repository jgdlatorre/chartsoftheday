"""
CandleEye · analyze_sessions.py

Quick aggregate over every session CSV in sessions/. Useful to see if your
eye has measurable edge after a handful of games.

Usage:
    python analyze_sessions.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SESSIONS_DIR = Path(__file__).parent / "sessions"


def main():
    files = sorted(SESSIONS_DIR.glob("*.csv"))
    if not files:
        print("no sessions yet in sessions/. play a game first.")
        return

    dfs = []
    for f in files:
        df = pd.read_csv(f)
        df["session"] = f.stem
        dfs.append(df)
    all_rounds = pd.concat(dfs, ignore_index=True)

    n_sessions = all_rounds["session"].nunique()
    n_rounds = len(all_rounds)

    hits = int(all_rounds["hit"].sum())
    miss = int(((~all_rounds["hit"].astype(bool)) & (~all_rounds["timeout"].astype(bool))).sum())
    timeouts = int(all_rounds["timeout"].sum())

    wr = hits / n_rounds * 100

    print(f"\nsessions:    {n_sessions}")
    print(f"rounds:      {n_rounds}")
    print(f"hits:        {hits} ({wr:.1f}%)")
    print(f"misses:      {miss}")
    print(f"timeouts:    {timeouts}")
    print(f"avg decide:  {all_rounds['ms_to_decide'].mean():.0f} ms")

    print("\nby direction:")
    for direction in ["long", "short"]:
        sub = all_rounds[all_rounds["decision"] == direction]
        if len(sub) == 0:
            continue
        h = int(sub["hit"].sum())
        wr_d = h / len(sub) * 100
        print(f"  {direction:5} · n={len(sub):3}  wr={wr_d:5.1f}%")

    print("\nmonkey benchmark:")
    mh = int(all_rounds["monkey_hit"].sum())
    print(f"  monkey wr:   {mh / n_rounds * 100:.1f}%")
    print(f"  diff (pp):   {wr - mh / n_rounds * 100:+.1f}")

    print("\nby asset (top 10 by count):")
    by_asset = all_rounds.groupby("symbol").agg(
        n=("hit", "size"), hits=("hit", "sum")
    ).sort_values("n", ascending=False).head(10)
    by_asset["wr"] = (by_asset["hits"] / by_asset["n"] * 100).round(1)
    print(by_asset.to_string())

    # Sanity: binomial check — probability of beating 50% by chance given n trials
    if n_rounds >= 30:
        from math import sqrt
        z = (wr / 100 - 0.5) / sqrt(0.25 / n_rounds)
        print(f"\nbinomial z vs 50/50: {z:+.2f}  (|z|>2 suggests real signal)")


if __name__ == "__main__":
    main()
