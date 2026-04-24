"""
One-off: consolidate cotd_all_{1h,4h,1d}.csv, produce cotd_candidates_consolidated.csv
and print the A/B/C analysis to stdout.

Does NOT re-scan. Reads the CSVs + re-runs scan_token for counts of total windows
analyzed (which are not in the output CSVs — only the top-N are).
"""
import json
import pandas as pd
from pathlib import Path

TFS = ["1h", "4h", "1d"]
ALLOWED = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    "ADAUSDT", "DOGEUSDT", "LTCUSDT", "LINKUSDT", "DOTUSDT",
]

SIG_COLS = [
    "sig_trend_direction", "sig_recent_momentum", "sig_volume_relative",
    "sig_price_vs_ma25", "sig_ma_cross_7_25", "sig_rsi_zone", "sig_support_resistance",
]


def tag_row(row) -> str:
    bd, od = row["bias_direction"], row["outcome_direction"]
    if bd == "bullish" and od == "up":
        return "confirmed_bullish"
    if bd == "bearish" and od == "down":
        return "confirmed_bearish"
    if bd == "bearish" and od == "up":
        return "contrarian_up_from_bearish"
    if bd == "bullish" and od == "down":
        return "contrarian_down_from_bullish"
    if bd == "neutral" and od != "flat":
        return "surprise"
    return "other"


def print_candidate(label: str, row):
    if row is None:
        print(f"\n── {label}: (no encontrado) ──")
        return
    print(f"\n── {label} ──")
    print(f"  symbol={row['symbol']}  timeframe={row['timeframe']}")
    print(f"  decision_ts={row['decision_ts']}   exit_ts={row['exit_ts']}")
    print(f"  señales:")
    for c in SIG_COLS:
        name = c.replace("sig_", "")
        print(f"    {name:22s} → {row[c]}")
    print(f"  bias: direction={row['bias_direction']}, strength={row['bias_strength']}")
    print(f"  outcome: direction={row['outcome_direction']}, pct={row['outcome_pct']}%, whipsaw={row['outcome_whipsaw']}")
    print(f"  edu_score={row['edu_score']}  coherence={row['coherence']}  tag={row['diversity_tag']}")


def main():
    # ── Re-compute total window counts per timeframe (fast: read raw CSV + divide).
    from cotd_scanner import TOTAL_WINDOW, STRIDE, load_token_data
    totals_windows = {}
    for tf in TFS:
        total = 0
        for sym in ALLOWED:
            df = load_token_data(sym, tf)
            if df is None or len(df) < TOTAL_WINDOW:
                continue
            total += (len(df) - TOTAL_WINDOW) // STRIDE + 1
        totals_windows[tf] = total

    # ── Also re-scan to get FULL per-TF result sets (for coherence distribution + count>=50).
    # Cheaper: read the intermediate CSVs would miss non-top rows.
    # Trade-off acknowledged: we re-run the full scan once per TF (already done in the main runs,
    # but those CSVs only contain top-N). To avoid re-scanning, we use the per-TF top-N CSVs
    # AND reconstruct full-set stats from /tmp logs.
    # Instead we'll just run scan_token again here per TF — it's deterministic and cached I/O.
    from cotd_scanner import scan_token
    per_tf_full = {}
    for tf in TFS:
        print(f"[consolidate] recomputing full scan for {tf} to collect stats...", flush=True)
        parts = []
        for sym in ALLOWED:
            df = scan_token(sym, tf, verbose=False)
            if len(df) > 0:
                parts.append(df)
        if parts:
            per_tf_full[tf] = pd.concat(parts, ignore_index=True)
        else:
            per_tf_full[tf] = pd.DataFrame()

    # ── Load the top-N CSVs (the canonical ranked candidate set per TF)
    top_frames = []
    for tf in TFS:
        path = Path(f"cotd_all_{tf}.csv")
        if not path.exists():
            print(f"WARNING: {path} missing, skipping")
            continue
        df = pd.read_csv(path)
        df["timeframe"] = tf
        df = df.sort_values("edu_score", ascending=False).reset_index(drop=True)
        df["rank_in_tf"] = df.index + 1
        top_frames.append(df)

    combined = pd.concat(top_frames, ignore_index=True)
    combined["diversity_tag"] = combined.apply(tag_row, axis=1)
    combined = combined.sort_values("edu_score", ascending=False).reset_index(drop=True)

    # ── Write consolidated CSV (drop the noisy _signals_full JSON column)
    out_cols = [c for c in combined.columns if c != "_signals_full"]
    combined[out_cols].to_csv("cotd_candidates_consolidated.csv", index=False)
    print("\n✓ Exportado cotd_candidates_consolidated.csv "
          f"({len(combined)} filas, columnas principales: symbol, timeframe, decision_ts, "
          f"rank_in_tf, edu_score, coherence, diversity_tag)\n")

    # ══════════════════════════════════════════════════════════════
    # A) PER-TIMEFRAME STATS
    # ══════════════════════════════════════════════════════════════
    print("═" * 70)
    print("A) Resumen por timeframe")
    print("═" * 70)
    for tf in TFS:
        full = per_tf_full[tf]
        top = combined[combined["timeframe"] == tf]
        n_total = totals_windows[tf]
        n_50 = int((full["edu_score"] >= 50).sum()) if len(full) else 0
        print(f"\n── {tf} ──")
        print(f"  ventanas totales analizadas (derivado, sin filtrar): ~{n_total}")
        print(f"  ventanas efectivas evaluadas (full scan):            {len(full)}")
        print(f"  candidatos con edu_score >= 50:                      {n_50} "
              f"({100*n_50/max(1,len(full)):.1f}%)")
        print(f"  distribución de coherence (todas las ventanas):")
        if len(full):
            coh = full["coherence"].value_counts().to_dict()
            for k in ["confirmed", "contrarian", "surprise_from_neutral",
                      "signal_ignored", "both_neutral"]:
                print(f"    {k:25s} {coh.get(k, 0):7d}")
        print(f"  símbolos en el top-{len(top)}:")
        sym_dist = top["symbol"].value_counts().to_dict()
        missing_syms = [s for s in ALLOWED if s not in sym_dist]
        for s, c in sym_dist.items():
            print(f"    {s:10s} {c}")
        if missing_syms:
            print(f"    (ausentes del top: {', '.join(missing_syms)})")

    # ══════════════════════════════════════════════════════════════
    # B) GLOBAL DIVERSITY TAG DISTRIBUTION
    # ══════════════════════════════════════════════════════════════
    print("\n" + "═" * 70)
    print("B) Distribución global por diversity_tag (consolidado)")
    print("═" * 70)
    tag_dist = combined["diversity_tag"].value_counts()
    for tag, c in tag_dist.items():
        print(f"  {tag:30s} {c}")

    # ══════════════════════════════════════════════════════════════
    # C) 5 CANDIDATOS PRE-SELECCIONADOS
    # ══════════════════════════════════════════════════════════════
    # Build FULL pool (all windows, all TFs) with tags — needed to find
    # contrarian / whipsaw / rsi-extreme candidates that are filtered OUT
    # by rank_setups (which top-N only keeps coherence=confirmed at score 90).
    print("\n" + "═" * 70)
    print("C) 5 candidatos pre-seleccionados")
    print("═" * 70)

    full_parts = []
    for tf, df in per_tf_full.items():
        if len(df) == 0:
            continue
        df = df.copy()
        df["timeframe"] = tf
        full_parts.append(df)
    full_pool = pd.concat(full_parts, ignore_index=True)
    full_pool["diversity_tag"] = full_pool.apply(tag_row, axis=1)
    full_pool = full_pool[full_pool["edu_score"] >= 50]

    def best_by_tag(tag, pool):
        sub = pool[pool["diversity_tag"] == tag]
        if len(sub) == 0:
            return None
        return sub.sort_values("edu_score", ascending=False).iloc[0]

    c1 = best_by_tag("confirmed_bullish", combined)
    c2 = best_by_tag("confirmed_bearish", combined)

    contr_all = full_pool[full_pool["diversity_tag"].isin(
        ["contrarian_up_from_bearish", "contrarian_down_from_bullish"]
    )]
    c3 = contr_all.sort_values("edu_score", ascending=False).iloc[0] if len(contr_all) else None

    whips = full_pool[full_pool["outcome_whipsaw"] == True]
    c4 = whips.sort_values("edu_score", ascending=False).iloc[0] if len(whips) else None

    rsi_extreme = full_pool[
        (full_pool["sig_rsi_zone"].isin(["overbought_extreme", "oversold_extreme"])) &
        (full_pool["coherence"] == "confirmed")
    ]
    c5 = rsi_extreme.sort_values("edu_score", ascending=False).iloc[0] if len(rsi_extreme) else None

    # Also print full-pool tag distribution as context (the top-N is confirmed-only by design)
    print("\n[contexto] Distribución tag en FULL pool (edu_score>=50, pre-filtro top-N):")
    for tag, c in full_pool["diversity_tag"].value_counts().items():
        print(f"  {tag:30s} {c}")

    print_candidate("1. Mejor CONFIRMED_BULLISH (señales alcistas → outcome up)", c1)
    print_candidate("2. Mejor CONFIRMED_BEARISH (señales bajistas → outcome down)", c2)
    print_candidate("3. Mejor CONTRARIAN (señales decían una cosa, pasó la otra)", c3)
    print_candidate("4. WHIPSAW que pasó filtro (setup difícil de narrar)", c4)
    print_candidate("5. RSI extremo en setup CONFIRMED (extremos que CONTINÚAN, no revierten)", c5)


if __name__ == "__main__":
    main()
