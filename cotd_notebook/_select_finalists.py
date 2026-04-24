"""
Part 2: select 5 editorial finalists from the full pool (all TFs) with edu_score >= 70,
write individual JSON files into samples/, and a samples/README.md with the summary.

Uses scan_token() directly (ignoring rank_setups) because several educational
profiles — contrarian, whipsaw, RSI-extreme — often fall outside the ranked top-N
even though their edu_score is high.

Preference rules (per user):
- #3 contrarian star: prefer BTCUSDT 1h 2020-01-08 08:00. Otherwise best
  contrarian_down_from_bullish with direction-strong signals + context-weak.
- #4 second contrarian: prefer ETHUSDT 4h 2025-09-15 or BNBUSDT 4h 2025-10-13
  (pick higher edu_score). Otherwise best contrarian not from same symbol as #3.
- #5 RSI extreme continues: prefer SOLUSDT 1h 2022-01-05 21:00. Otherwise best
  confirmed with rsi_zone in {overbought_extreme, oversold_extreme}.

If any preferred candidate is NOT in pool, the script will print a loud
warning — per user instruction, don't silently fall back.
"""
import json
import pandas as pd
from pathlib import Path

from cotd_scanner import scan_token

ALLOWED = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    "ADAUSDT", "DOGEUSDT", "LTCUSDT", "LINKUSDT", "DOTUSDT",
]
TFS = ["1h", "4h", "1d"]
MIN_SCORE = 70

SIG_NAMES = [
    "trend_direction", "recent_momentum", "volume_relative",
    "price_vs_ma25", "ma_cross_7_25", "rsi_zone", "support_resistance",
]

SAMPLES_DIR = Path("samples")


def build_full_pool() -> pd.DataFrame:
    """Re-scan everything and concatenate. Filter by edu_score >= 70."""
    parts = []
    for tf in TFS:
        for sym in ALLOWED:
            df = scan_token(sym, tf, verbose=False)
            if len(df) > 0:
                df = df.copy()
                df["timeframe"] = tf
                parts.append(df)
    pool = pd.concat(parts, ignore_index=True)
    pool = pool[pool["edu_score"] >= MIN_SCORE].reset_index(drop=True)
    return pool


def find_exact(pool: pd.DataFrame, symbol: str, tf: str, ts_str: str):
    """Return the row matching (symbol, tf, decision_ts) or None."""
    target_ts = pd.Timestamp(ts_str)
    sub = pool[(pool["symbol"] == symbol) & (pool["timeframe"] == tf)]
    # decision_ts can be Timestamp or string depending on how scan_token left it
    sub = sub[pd.to_datetime(sub["decision_ts"]) == target_ts]
    if len(sub) == 0:
        return None
    return sub.iloc[0]


def row_to_json(row, profile_id: str, profile_name: str) -> dict:
    """Convert a scan_token row into the sample JSON structure."""
    # Unpack the _signals_full JSON blob that scan_token stores per row.
    signals_full = json.loads(row["_signals_full"])
    signals_out = {}
    for name in SIG_NAMES:
        sig = signals_full.get(name, {})
        signals_out[name] = {
            "state": sig.get("state"),
            "confidence": sig.get("confidence"),
            "detail": sig.get("detail"),
        }

    def iso(v):
        if v is None:
            return None
        if hasattr(v, "isoformat"):
            return v.isoformat()
        # If it's already a string (read from CSV path) just stringify
        return str(v)

    return {
        "id": profile_id,
        "profile": profile_name,
        "symbol": row["symbol"],
        "timeframe": row["timeframe"],
        "decision_ts": iso(row["decision_ts"]),
        "exit_ts": iso(row["exit_ts"]),
        "entry_price": float(row["entry_price"]),
        "exit_price": float(row["exit_price"]) if pd.notna(row.get("exit_price")) else None,
        "outcome_pct": float(row["outcome_pct"]),
        "signals": signals_out,
        "bias": {
            # scan_token row doesn't store bias_score directly — reconstruct
            # from the individual columns we DO have.
            "direction": row["bias_direction"],
            "strength": row["bias_strength"],
        },
        "outcome": {
            "direction": row["outcome_direction"],
            "pct_change": float(row["outcome_pct"]),
            "whipsaw": bool(row["outcome_whipsaw"]),
        },
        "edu_score": int(row["edu_score"]),
        "coherence": row["coherence"],
        "pedagogical_notes": "",
    }


def print_candidate(label: str, row):
    print(f"\n── {label} ──")
    print(f"  symbol={row['symbol']}  timeframe={row['timeframe']}")
    print(f"  decision_ts={row['decision_ts']}   exit_ts={row['exit_ts']}")
    print(f"  señales:")
    for n in SIG_NAMES:
        col = f"sig_{n}"
        print(f"    {n:22s} → {row[col]}")
    print(f"  bias: {row['bias_direction']} / {row['bias_strength']}")
    print(f"  outcome: {row['outcome_direction']}, {row['outcome_pct']}%, whipsaw={row['outcome_whipsaw']}")
    print(f"  edu_score={row['edu_score']}  coherence={row['coherence']}")


def main():
    SAMPLES_DIR.mkdir(exist_ok=True)
    print("[select] building full pool (edu_score>=70) across all TFs...", flush=True)
    pool = build_full_pool()
    print(f"[select] pool size: {len(pool)} rows\n")

    # ─── Preferred candidates presence check ────────────────────────────
    preferred_checks = {
        "BTC 1h 2020-01-08 08:00": ("BTCUSDT", "1h", "2020-01-08 08:00:00"),
        "SOL 1h 2022-01-05 21:00": ("SOLUSDT", "1h", "2022-01-05 21:00:00"),
        "ETH 4h 2025-09-15":       ("ETHUSDT", "4h", "2025-09-15"),
        "BNB 4h 2025-10-13":       ("BNBUSDT", "4h", "2025-10-13"),
    }
    # Note: 4h decision_ts could be any of the 4h-aligned hours of that day.
    # Search by date-only for the 4h preferred and pick the matching row if unique.
    print("═" * 70)
    print("Preferred candidate presence check (edu_score>=70 pool)")
    print("═" * 70)
    preferred_resolved = {}
    for label, (sym, tf, ts_str) in preferred_checks.items():
        if tf == "4h" and len(ts_str) == 10:
            # date-only match: any 4h bar on that date, pick best edu_score
            sub = pool[(pool["symbol"] == sym) & (pool["timeframe"] == tf)]
            sub = sub[pd.to_datetime(sub["decision_ts"]).dt.date == pd.Timestamp(ts_str).date()]
            if len(sub):
                row = sub.sort_values("edu_score", ascending=False).iloc[0]
                preferred_resolved[label] = row
                print(f"  ✓ {label}: found ({len(sub)} match(es), best @ {row['decision_ts']} score={row['edu_score']})")
            else:
                preferred_resolved[label] = None
                print(f"  ✗ {label}: NOT in pool")
        else:
            row = find_exact(pool, sym, tf, ts_str)
            preferred_resolved[label] = row
            if row is not None:
                print(f"  ✓ {label}: found (edu_score={row['edu_score']}, coherence={row['coherence']})")
            else:
                print(f"  ✗ {label}: NOT in pool")
    print()

    # ═══════════════════════════════════════════════════════════════════
    # FINALIST SELECTION
    # ═══════════════════════════════════════════════════════════════════
    finalists = {}

    # ─── #1: confirmed_bullish obvio, mov 2-5%, preferible XRPUSDT ─────
    # Criterios: coherence=confirmed, bias=bullish, outcome=up, 2<=pct<=5.
    c1_pool = pool[
        (pool["coherence"] == "confirmed") &
        (pool["bias_direction"] == "bullish") &
        (pool["outcome_direction"] == "up") &
        (pool["outcome_pct"].between(2.0, 5.0))
    ]
    xrp = c1_pool[c1_pool["symbol"] == "XRPUSDT"]
    if len(xrp) > 0:
        c1 = xrp.sort_values("edu_score", ascending=False).iloc[0]
        c1_src = "XRPUSDT preferred"
    else:
        c1 = c1_pool.sort_values("edu_score", ascending=False).iloc[0]
        c1_src = "fallback (any altcoin)"
    finalists["setup_01_confirmed_bullish"] = ("confirmed_bullish_obvio", c1, c1_src)

    # ─── #2: confirmed_bearish en blue-chip (BTC/ETH) ──────────────────
    c2_pool = pool[
        (pool["coherence"] == "confirmed") &
        (pool["bias_direction"] == "bearish") &
        (pool["outcome_direction"] == "down") &
        (pool["symbol"].isin(["BTCUSDT", "ETHUSDT"]))
    ]
    c2 = c2_pool.sort_values("edu_score", ascending=False).iloc[0]
    finalists["setup_02_confirmed_bearish"] = ("confirmed_bearish_bluechip", c2, f"best {c2['symbol']}")

    # ─── #3: contrarian pedagogical star (prefer BTCUSDT 1h 2020-01-08 08:00) ─
    btc_star = preferred_resolved["BTC 1h 2020-01-08 08:00"]
    if btc_star is not None:
        c3 = btc_star
        c3_src = "BTC 2020-01-08 08:00 preferred star"
    else:
        # Fallback: best contrarian_down_from_bullish with direction-strong + context-weak signals
        c3_pool = pool[
            (pool["coherence"] == "contrarian") &
            (pool["bias_direction"] == "bullish") &
            (pool["outcome_direction"] == "down") &
            (pool["sig_recent_momentum"].isin(["indecisive", "exhausted_up"])) &
            (pool["sig_volume_relative"].isin(["falling", "dry"]))
        ]
        if len(c3_pool) == 0:
            # Relax momentum/volume constraints
            c3_pool = pool[
                (pool["coherence"] == "contrarian") &
                (pool["bias_direction"] == "bullish") &
                (pool["outcome_direction"] == "down")
            ]
        c3 = c3_pool.sort_values("edu_score", ascending=False).iloc[0]
        c3_src = "fallback (best bullish-signals → down outcome)"
    finalists["setup_03_contrarian_star"] = ("contrarian_pedagogico_estrella", c3, c3_src)

    # ─── #4: second contrarian, different symbol from #3 ──────────────
    # Preference: ETHUSDT 4h 2025-09-15 OR BNBUSDT 4h 2025-10-13 — pick higher score.
    # Both should be contrarian_down_from_bullish.
    pref_c4_candidates = []
    for label in ["ETH 4h 2025-09-15", "BNB 4h 2025-10-13"]:
        row = preferred_resolved[label]
        if row is not None and row["coherence"] == "contrarian":
            pref_c4_candidates.append((label, row))

    c3_symbol = c3["symbol"]
    if pref_c4_candidates:
        # Pick highest edu_score, must differ from c3's symbol (both prefs are ETH/BNB ≠ BTC, so OK if c3=BTC)
        eligible = [(l, r) for (l, r) in pref_c4_candidates if r["symbol"] != c3_symbol]
        if eligible:
            c4_label, c4 = max(eligible, key=lambda x: x[1]["edu_score"])
            c4_src = f"{c4_label} preferred"
        else:
            c4_label, c4 = None, None
    else:
        c4_label, c4 = None, None

    if c4 is None:
        # Fallback: next best contrarian with symbol != c3_symbol and != BTCUSDT
        c4_pool = pool[
            (pool["coherence"] == "contrarian") &
            (pool["symbol"] != c3_symbol) &
            (pool["symbol"] != "BTCUSDT")  # user: "que no sea BTCUSDT" in fallback
        ]
        if len(c4_pool) == 0:
            c4_pool = pool[(pool["coherence"] == "contrarian") & (pool["symbol"] != c3_symbol)]
        c4 = c4_pool.sort_values("edu_score", ascending=False).iloc[0]
        c4_src = "fallback (best contrarian, diff symbol, not BTC)"
    finalists["setup_04_contrarian_second"] = ("contrarian_segundo_directo", c4, c4_src)

    # ─── #5: RSI extreme that continues (confirmed + oversold_extreme/overbought_extreme) ─
    sol_star = preferred_resolved["SOL 1h 2022-01-05 21:00"]
    if sol_star is not None and sol_star["coherence"] == "confirmed":
        c5 = sol_star
        c5_src = "SOL 2022-01-05 21:00 preferred"
    else:
        c5_pool = pool[
            (pool["coherence"] == "confirmed") &
            (pool["sig_rsi_zone"].isin(["overbought_extreme", "oversold_extreme"]))
        ]
        c5 = c5_pool.sort_values("edu_score", ascending=False).iloc[0]
        c5_src = "fallback (best confirmed + RSI extreme)"
    finalists["setup_05_rsi_extreme_continues"] = ("rsi_extremo_continua", c5, c5_src)

    # ═══════════════════════════════════════════════════════════════════
    # WRITE JSON + README + PRINT
    # ═══════════════════════════════════════════════════════════════════
    print("═" * 70)
    print("Finalistas seleccionados")
    print("═" * 70)

    readme_rows = []
    for file_id, (profile_name, row, source) in finalists.items():
        obj = row_to_json(row, file_id, profile_name)
        path = SAMPLES_DIR / f"{file_id}.json"
        with open(path, "w") as f:
            json.dump(obj, f, indent=2, default=str)
        print(f"\n✓ {path.name}  (source: {source})")
        print_candidate(f"{file_id} — {profile_name}", row)
        readme_rows.append({
            "file": path.name,
            "profile": profile_name,
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "decision_ts": obj["decision_ts"],
            "coherence": row["coherence"],
            "edu_score": int(row["edu_score"]),
            "outcome_pct": float(row["outcome_pct"]),
            "source": source,
        })

    # ─── samples/README.md ──────────────────────────────────────────────
    readme = ["# COTD Editorial Sample — 5 Finalists",
              "",
              "Pre-selected setups from the full scan pool (edu_score ≥ 70 across all TFs).",
              "`pedagogical_notes` fields in each JSON are left empty for editorial fill-in.",
              "",
              "| # | File | Profile | Symbol | TF | Decision TS | Coherence | edu_score | outcome_pct | Source |",
              "|---|------|---------|--------|----|-------------|-----------|-----------|-------------|--------|"]
    for i, r in enumerate(readme_rows, 1):
        readme.append(
            f"| {i} | `{r['file']}` | {r['profile']} | {r['symbol']} | {r['timeframe']} "
            f"| {r['decision_ts']} | {r['coherence']} | {r['edu_score']} | {r['outcome_pct']:+.2f}% | {r['source']} |"
        )
    readme.append("")
    readme.append("## Pedagogical intent per profile")
    readme.append("")
    readme.append("1. **confirmed_bullish_obvio** — teaches that trend + MA-cross + above-MA25 often works on clean altcoin setups with modest 2-5% moves.")
    readme.append("2. **confirmed_bearish_bluechip** — same logic on a blue-chip (BTC/ETH) so the user knows reading works across market caps.")
    readme.append("3. **contrarian_pedagogico_estrella** — directional signals (trend, MA) said bullish but context (momentum, volume) was weak. Outcome down. The teaching: strong trend ≠ strong setup when context is eroding.")
    readme.append("4. **contrarian_segundo_directo** — similar humility lesson on a different symbol; blue-chip preferred so users don't dismiss it as 'just meme-coin chaos'.")
    readme.append("5. **rsi_extremo_continua** — RSI in oversold/overbought extreme CONTINUED in the same direction instead of reverting. Counters the common retail belief that 'RSI > 80 = short'.")
    readme.append("")
    (SAMPLES_DIR / "README.md").write_text("\n".join(readme))
    print(f"\n✓ {SAMPLES_DIR / 'README.md'}")


if __name__ == "__main__":
    main()
