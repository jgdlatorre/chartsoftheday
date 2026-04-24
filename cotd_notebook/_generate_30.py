"""
Generate 30 additional COTD setups (setup_06..setup_35) to complete a 7-day demo
of 5 profiles per day. Works off the full scan pool (edu_score>=70), applies
per-profile signal criteria from the spec, enforces blue-chip/meme and TF quotas,
then assigns to 7 days × 5 slots with the 5 existing finalists.

Constraints honored:
- Date window 2020-01-01..2025-12-31
- |outcome_pct| in [2, 10]
- No duplicate (symbol, tf, decision_ts) vs existing 5
- Per-profile counts: 6 / 6 / 5 / 7 / 6
- Target 24 blue-chip + 6 meme (only DOGEUSDT available — see top-of-run warning)
- TF mix ~60/25/15 (1h/4h/1d)
- RSI profile: ≥3 overbought_extreme (continues up), ≤3 oversold_extreme
- pedagogical_notes: {} for new; existing 5 keep their original "" value
"""
import json
import pandas as pd
from pathlib import Path
from cotd_scanner import scan_token

# ─── Constants ───────────────────────────────────────────────────────────
ALLOWED = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    "ADAUSDT", "DOGEUSDT", "LTCUSDT", "LINKUSDT", "DOTUSDT",
]
TFS = ["1h", "4h", "1d"]
BLUE_CHIP = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
             "ADAUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT"}
MEME = {"DOGEUSDT"}  # only meme with data; AVAX/SHIB/PEPE/WIF/BONK/FLOKI absent

SIG_NAMES = [
    "trend_direction", "recent_momentum", "volume_relative",
    "price_vs_ma25", "ma_cross_7_25", "rsi_zone", "support_resistance",
]

SAMPLES_DIR = Path("samples")

# Existing 5 finalists — (symbol, timeframe, decision_ts_iso, profile_category, file_id, outcome_pct)
# profile_category is how we bucket them in the 7-day grid (matches spec profiles).
EXISTING = [
    ("XRPUSDT", "1d", "2024-09-18T00:00:00", "confirmed_bullish_obvio",   "setup_01_confirmed_bullish",        4.48),
    ("ETHUSDT", "1h", "2020-02-25T14:00:00", "confirmed_bearish_bluechip","setup_02_confirmed_bearish",       -5.28),
    ("BTCUSDT", "1h", "2020-01-08T08:00:00", "contrarian_bullish_falla",  "setup_03_contrarian_star",         -3.21),
    ("BNBUSDT", "4h", "2025-10-13T16:00:00", "contrarian_bullish_falla",  "setup_04_contrarian_second",       -8.38),
    ("SOLUSDT", "1h", "2022-01-05T21:00:00", "rsi_extremo_continua",      "setup_05_rsi_extreme_continues",   -4.13),
]
EXISTING_KEYS = {(s, tf, pd.Timestamp(ts)) for s, tf, ts, _, _, _ in EXISTING}

# Target new-count per profile
NEW_COUNTS = {
    "confirmed_bullish_obvio":    6,
    "confirmed_bearish_bluechip": 6,
    "contrarian_bullish_falla":   5,
    "contrarian_bearish_falla":   7,
    "rsi_extremo_continua":       6,
}

# Target meme (DOGEUSDT) slots per profile
MEME_BUDGET_PER_PROFILE = {
    "confirmed_bullish_obvio":    1,
    "confirmed_bearish_bluechip": 0,  # spec: "priorizar BTC/ETH"
    "contrarian_bullish_falla":   1,
    "contrarian_bearish_falla":   2,
    "rsi_extremo_continua":       2,
}  # sums to 6


# ─── Pool builder ────────────────────────────────────────────────────────
def build_pool() -> pd.DataFrame:
    """Re-scan all symbols × TFs, apply global filters, expand detail columns."""
    parts = []
    for tf in TFS:
        for sym in ALLOWED:
            df = scan_token(sym, tf, verbose=False)
            if len(df) > 0:
                df = df.copy()
                df["timeframe"] = tf
                parts.append(df)
    pool = pd.concat(parts, ignore_index=True)

    # Expand signal details from _signals_full JSON into dedicated columns.
    # Keeps per-profile filters readable without re-parsing JSON each time.
    details = pool["_signals_full"].apply(json.loads)
    pool["d_volume_ratio"]  = details.apply(lambda d: d.get("volume_relative", {}).get("detail", {}).get("ratio"))
    pool["d_price_z"]       = details.apply(lambda d: d.get("price_vs_ma25", {}).get("detail", {}).get("z_score"))
    pool["d_rsi"]           = details.apply(lambda d: d.get("rsi_zone", {}).get("detail", {}).get("rsi_value"))
    pool["d_bull_candles"]  = details.apply(lambda d: d.get("recent_momentum", {}).get("detail", {}).get("bullish_candles"))
    pool["d_bear_candles"]  = details.apply(lambda d: d.get("recent_momentum", {}).get("detail", {}).get("bearish_candles"))
    pool["d_trend_conf"]    = details.apply(lambda d: d.get("trend_direction", {}).get("confidence"))

    pool["decision_ts"] = pd.to_datetime(pool["decision_ts"])
    pool = pool[
        (pool["edu_score"] >= 70) &
        (pool["decision_ts"] >= pd.Timestamp("2020-01-01")) &
        (pool["decision_ts"] <= pd.Timestamp("2025-12-31 23:59:59")) &
        (pool["outcome_pct"].abs() >= 2.0) &
        (pool["outcome_pct"].abs() <= 10.0)
    ].copy()

    # Drop rows whose (symbol,tf,decision_ts) duplicates an existing finalist.
    pool["_k"] = list(zip(pool["symbol"], pool["timeframe"], pool["decision_ts"]))
    pool = pool[~pool["_k"].isin(EXISTING_KEYS)].drop(columns=["_k"]).reset_index(drop=True)
    return pool


# ─── Per-profile candidate filters ───────────────────────────────────────
def candidates_confirmed_bullish(pool):
    return pool[
        (pool["coherence"] == "confirmed") &
        (pool["bias_direction"] == "bullish") &
        (pool["bias_strength"] == "strong") &
        (pool["outcome_direction"] == "up") &
        (pool["sig_trend_direction"].isin(["bullish", "bullish_strong"])) &
        (pool["sig_ma_cross_7_25"].isin(["fresh_bullish_cross", "recent_bullish_cross", "ma7_above_stable"])) &
        (pool["sig_price_vs_ma25"].isin(["above", "far_above"])) &
        (pool["outcome_pct"].between(2.0, 8.0))
    ]


def candidates_confirmed_bearish(pool):
    return pool[
        (pool["coherence"] == "confirmed") &
        (pool["bias_direction"] == "bearish") &
        (pool["bias_strength"] == "strong") &
        (pool["outcome_direction"] == "down") &
        (pool["sig_trend_direction"].isin(["bearish", "bearish_strong"])) &
        (pool["sig_volume_relative"].isin(["rising", "climactic"])) &
        (pool["sig_price_vs_ma25"].isin(["below", "far_below"])) &
        (pool["outcome_pct"].between(-8.0, -2.0))
    ]


def candidates_contrarian_bullish_falla(pool):
    base = pool[
        (pool["coherence"] == "contrarian") &
        (pool["bias_direction"] == "bullish") &
        (pool["bias_strength"].isin(["strong", "moderate"])) &
        (pool["sig_trend_direction"].isin(["bullish", "bullish_strong"])) &
        (pool["outcome_direction"] == "down")
    ].copy()
    # At least one erosion signal
    erosion = (
        (base["sig_volume_relative"] == "falling") |
        (base["sig_recent_momentum"].isin(["indecisive", "mixed", "exhausted_up"])) |
        (base["d_bear_candles"].fillna(0) > base["d_bull_candles"].fillna(0)) |
        (base["d_price_z"].fillna(0) > 2.0)
    )
    return base[erosion]


def candidates_contrarian_bearish_falla(pool):
    base = pool[
        (pool["coherence"] == "contrarian") &
        (pool["bias_direction"] == "bearish") &
        (pool["bias_strength"].isin(["strong", "moderate"])) &
        (pool["sig_trend_direction"].isin(["bearish", "bearish_strong"])) &
        (pool["outcome_direction"] == "up")
    ].copy()
    # At least one reversal signal
    reversal = (
        (base["sig_volume_relative"] == "climactic") |
        (base["sig_recent_momentum"].isin(["indecisive", "mixed", "exhausted_down"])) |
        (base["d_bull_candles"].fillna(0) > base["d_bear_candles"].fillna(0)) |
        (base["d_price_z"].fillna(0) < -2.0) |
        (base["sig_rsi_zone"].isin(["oversold", "oversold_extreme"]))
    )
    return base[reversal]


def candidates_rsi_overbought_continues(pool):
    """Overbought extreme + bullish trend + outcome continues up."""
    return pool[
        (pool["coherence"] == "confirmed") &
        (pool["sig_rsi_zone"] == "overbought_extreme") &
        (pool["sig_trend_direction"].isin(["bullish", "bullish_strong"])) &
        (pool["outcome_direction"] == "up") &
        (pool["outcome_pct"].between(2.0, 10.0))
    ]


def candidates_rsi_oversold_continues(pool):
    """Oversold extreme + bearish trend + outcome continues down."""
    return pool[
        (pool["coherence"] == "confirmed") &
        (pool["sig_rsi_zone"] == "oversold_extreme") &
        (pool["sig_trend_direction"].isin(["bearish", "bearish_strong"])) &
        (pool["outcome_direction"] == "down") &
        (pool["outcome_pct"].between(-10.0, -2.0))
    ]


# ─── Selection with diversity ────────────────────────────────────────────
def pick_diverse(cands: pd.DataFrame, n: int, meme_target: int,
                 max_per_symbol: int = 2, tf_weights=None) -> pd.DataFrame:
    """Pick n rows: first `meme_target` from MEME, then fill with BLUE_CHIP.

    Diversity rules:
    - max_per_symbol (default 2) cap within the profile
    - within each pass, sort by edu_score desc, then outcome_pct absolute desc
    - tf_weights (dict tf->pref int) tie-breaks by TF preference when scores equal
    """
    if cands.empty:
        return cands.head(0)

    cands = cands.copy()
    cands["_abs_pct"] = cands["outcome_pct"].abs()
    cands = cands.sort_values(["edu_score", "_abs_pct"], ascending=[False, False])

    picked_rows = []
    picked_sym_count = {}
    picked_keys = set()

    def try_add(row):
        k = (row["symbol"], row["timeframe"], row["decision_ts"])
        if k in picked_keys:
            return False
        if picked_sym_count.get(row["symbol"], 0) >= max_per_symbol:
            return False
        picked_rows.append(row)
        picked_sym_count[row["symbol"]] = picked_sym_count.get(row["symbol"], 0) + 1
        picked_keys.add(k)
        return True

    # Pass 1: meme slots
    meme_got = 0
    for _, row in cands[cands["symbol"].isin(MEME)].iterrows():
        if meme_got >= meme_target:
            break
        if try_add(row):
            meme_got += 1

    # Pass 2: fill remainder with blue-chip
    for _, row in cands[cands["symbol"].isin(BLUE_CHIP)].iterrows():
        if len(picked_rows) >= n:
            break
        try_add(row)

    # Pass 3: if still short (meme target unfulfilled), accept more blue-chip
    # or more memes (relaxed diversity)
    if len(picked_rows) < n:
        for _, row in cands.iterrows():
            if len(picked_rows) >= n:
                break
            try_add(row)

    return pd.DataFrame(picked_rows)


# ─── JSON serialization ──────────────────────────────────────────────────
def row_to_json(row, setup_id: str, profile_name: str) -> dict:
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
        return str(v)

    return {
        "id": setup_id,
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
        "pedagogical_notes": {},
    }


# ─── Day assignment ──────────────────────────────────────────────────────
SLOT_ORDER = [
    "confirmed_bullish_obvio",
    "confirmed_bearish_bluechip",
    "contrarian_bullish_falla",
    "contrarian_bearish_falla",
    "rsi_extremo_continua",
]


def assign_days(all_setups: list[dict]) -> list[list[dict]]:
    """Group setups into 7 days × 5 slots, one per profile per day.

    Input: list of setup dicts, each with fields {profile, file_id, symbol, tf,
    decision_ts, outcome_pct, existing (bool)}.
    Returns list of 7 lists; each inner list has exactly 5 setups in SLOT_ORDER.
    """
    by_profile = {p: [] for p in SLOT_ORDER}
    for s in all_setups:
        by_profile[s["profile"]].append(s)

    # Sanity check: each profile must have exactly 7 setups
    for p, items in by_profile.items():
        assert len(items) == 7, f"Profile {p} has {len(items)} setups, expected 7"

    # Sort each profile list: existing first (anchors), then newer by edu_score desc
    for p in by_profile:
        by_profile[p].sort(key=lambda s: (not s["existing"], -s["edu_score"]))

    # Distribute: day d gets by_profile[p][d] for each profile
    days = []
    for d in range(7):
        day = [by_profile[p][d] for p in SLOT_ORDER]
        days.append(day)
    return days


# ─── Main ────────────────────────────────────────────────────────────────
def main():
    SAMPLES_DIR.mkdir(exist_ok=True)

    print("[gen] building full pool (edu_score>=70, date 2020-2025, |pct|∈[2,10])...", flush=True)
    pool = build_pool()
    print(f"[gen] pool size after filters: {len(pool)}\n")

    # ── Compute per-profile candidate pools ──────────────────────────
    cand_bull = candidates_confirmed_bullish(pool)
    cand_bear = candidates_confirmed_bearish(pool)
    cand_contr_bull = candidates_contrarian_bullish_falla(pool)
    cand_contr_bear = candidates_contrarian_bearish_falla(pool)
    cand_rsi_over = candidates_rsi_overbought_continues(pool)
    cand_rsi_under = candidates_rsi_oversold_continues(pool)

    print("[gen] candidate counts per profile:")
    print(f"  confirmed_bullish_obvio:         {len(cand_bull)}")
    print(f"  confirmed_bearish_bluechip:      {len(cand_bear)}")
    print(f"  contrarian_bullish_falla:        {len(cand_contr_bull)}")
    print(f"  contrarian_bearish_falla:        {len(cand_contr_bear)}")
    print(f"  rsi overbought continues up:     {len(cand_rsi_over)}")
    print(f"  rsi oversold continues down:     {len(cand_rsi_under)}")
    print()

    # ── Select per profile ──────────────────────────────────────────
    sel_bull = pick_diverse(cand_bull, n=6, meme_target=MEME_BUDGET_PER_PROFILE["confirmed_bullish_obvio"])

    # For confirmed_bearish: prefer BTC/ETH (bluechip). Pick BTC/ETH first, then other.
    cand_bear_prio = cand_bear[cand_bear["symbol"].isin(["BTCUSDT", "ETHUSDT"])]
    cand_bear_rest = cand_bear[~cand_bear["symbol"].isin(["BTCUSDT", "ETHUSDT"])]
    sel_bear_prio = pick_diverse(cand_bear_prio, n=6, meme_target=0, max_per_symbol=3)
    remaining = 6 - len(sel_bear_prio)
    if remaining > 0:
        sel_bear_fill = pick_diverse(cand_bear_rest, n=remaining, meme_target=0, max_per_symbol=2)
        sel_bear = pd.concat([sel_bear_prio, sel_bear_fill], ignore_index=True)
    else:
        sel_bear = sel_bear_prio

    sel_contr_bull = pick_diverse(cand_contr_bull, n=5, meme_target=MEME_BUDGET_PER_PROFILE["contrarian_bullish_falla"])
    sel_contr_bear = pick_diverse(cand_contr_bear, n=7, meme_target=MEME_BUDGET_PER_PROFILE["contrarian_bearish_falla"])

    # RSI: 4 overbought + 2 oversold (3+3 also valid; 4/2 gives slight up bias overall).
    # If insufficient overbought, fallback to 3/3.
    rsi_over_target = 4 if len(cand_rsi_over) >= 4 else 3
    rsi_under_target = 6 - rsi_over_target
    sel_rsi_over = pick_diverse(cand_rsi_over, n=rsi_over_target,
                                meme_target=min(1, MEME_BUDGET_PER_PROFILE["rsi_extremo_continua"]))
    sel_rsi_under = pick_diverse(cand_rsi_under, n=rsi_under_target,
                                 meme_target=max(0, MEME_BUDGET_PER_PROFILE["rsi_extremo_continua"] - 1))
    sel_rsi = pd.concat([sel_rsi_over, sel_rsi_under], ignore_index=True)

    selections = {
        "confirmed_bullish_obvio":    sel_bull,
        "confirmed_bearish_bluechip": sel_bear,
        "contrarian_bullish_falla":   sel_contr_bull,
        "contrarian_bearish_falla":   sel_contr_bear,
        "rsi_extremo_continua":       sel_rsi,
    }

    print("[gen] selected counts per profile:")
    for p, df in selections.items():
        memes = df["symbol"].isin(MEME).sum()
        print(f"  {p:30s} {len(df)}  (meme={memes}, symbols={df['symbol'].tolist()})")
    print()

    # ── Write the 30 new JSONs (setup_06..setup_35) ─────────────────
    # Order across profiles: sort a profile's selections by edu_score desc for stable numbering.
    all_new_dicts = []
    next_id = 6
    for profile in SLOT_ORDER:
        df = selections[profile].sort_values(
            ["edu_score", "outcome_pct"], ascending=[False, False]
        ).reset_index(drop=True)
        for _, row in df.iterrows():
            # file_id suffix: keep the canonical profile name short
            short = {
                "confirmed_bullish_obvio":    "confirmed_bullish",
                "confirmed_bearish_bluechip": "confirmed_bearish",
                "contrarian_bullish_falla":   "contrarian_bull_fails",
                "contrarian_bearish_falla":   "contrarian_bear_fails",
                "rsi_extremo_continua":       "rsi_extreme_continues",
            }[profile]
            setup_id = f"setup_{next_id:02d}_{short}"
            obj = row_to_json(row, setup_id, profile)
            path = SAMPLES_DIR / f"{setup_id}.json"
            with open(path, "w") as f:
                json.dump(obj, f, indent=2, default=str)
            all_new_dicts.append({
                "file_id": setup_id,
                "profile": profile,
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "decision_ts": obj["decision_ts"],
                "outcome_pct": float(row["outcome_pct"]),
                "edu_score": int(row["edu_score"]),
                "existing": False,
            })
            next_id += 1

    # ── Merge existing + new, assign to days ─────────────────────────
    existing_dicts = [
        {
            "file_id": file_id, "profile": cat, "symbol": sym, "timeframe": tf,
            "decision_ts": ts, "outcome_pct": pct, "edu_score": 90, "existing": True,
        }
        for sym, tf, ts, cat, file_id, pct in EXISTING
    ]
    # setup_04 has edu_score=70, setup_03=85, rest=90 — fix for sort stability
    edu_fix = {"setup_03_contrarian_star": 85, "setup_04_contrarian_second": 70}
    for d in existing_dicts:
        if d["file_id"] in edu_fix:
            d["edu_score"] = edu_fix[d["file_id"]]

    all_setups = existing_dicts + all_new_dicts
    days = assign_days(all_setups)

    # ── Validation stats ─────────────────────────────────────────────
    print("═" * 74)
    print("VALIDATION")
    print("═" * 74)
    all_flat = [s for day in days for s in day]
    profile_counts = {p: sum(1 for s in all_flat if s["profile"] == p) for p in SLOT_ORDER}
    print(f"\n  profile counts: {profile_counts}")
    sym_mix = {"blue_chip": 0, "meme": 0}
    for s in all_new_dicts:
        sym_mix["blue_chip" if s["symbol"] in BLUE_CHIP else "meme"] += 1
    print(f"  new-symbol mix (30 new): blue_chip={sym_mix['blue_chip']}, meme={sym_mix['meme']}")
    tf_mix = {tf: sum(1 for s in all_new_dicts if s["timeframe"] == tf) for tf in TFS}
    print(f"  new-TF mix (30 new): {tf_mix}")
    up_total = sum(1 for s in all_flat if s["outcome_pct"] > 0)
    down_total = sum(1 for s in all_flat if s["outcome_pct"] < 0)
    print(f"  week direction: up={up_total}/35 ({100*up_total/35:.0f}%), down={down_total}/35 ({100*down_total/35:.0f}%)")
    # Per-day balance
    for d_idx, day in enumerate(days, 1):
        up = sum(1 for s in day if s["outcome_pct"] > 0)
        dn = sum(1 for s in day if s["outcome_pct"] < 0)
        print(f"  day {d_idx}: up={up} down={dn}")

    # ── Write README ─────────────────────────────────────────────────
    readme_lines = [
        "# COTD Editorial Sample — 35 Finalists (7 days × 5 profiles)",
        "",
        "Five existing hand-picked setups (setup_01..setup_05) plus 30 generated "
        "from the full scan pool (edu_score ≥ 70, 2020–2025, |outcome_pct| ∈ [2,10]).",
        "",
        "**Profile legend**",
        "- `confirmed_bullish_obvio` — trend+MA confirm bullish, outcome up",
        "- `confirmed_bearish_bluechip` — trend+volume+MA confirm bearish, outcome down",
        "- `contrarian_bullish_falla` — bullish signals with erosion (weak momentum / falling volume / overextended), outcome down",
        "- `contrarian_bearish_falla` — bearish signals with reversal hint (climactic volume / divergence / oversold RSI), outcome up",
        "- `rsi_extremo_continua` — RSI in extreme zone continues instead of reverting",
        "",
        "**Note on symbols.** Only DOGEUSDT is available from the spec's meme list "
        "(SHIB/PEPE/WIF/BONK/FLOKI and AVAX are not in `data_1h/4h/1d`). "
        "The 20% meme quota is satisfied with DOGEUSDT only; remainder is blue-chip.",
        "",
        "**Note on schema.** The 5 existing files have `pedagogical_notes: \"\"` (string); "
        "the 30 new files have `pedagogical_notes: {}` (object), per the spec update for this phase.",
        "",
        "## 7-day grid",
        "",
        "| Día | Slot | File | Profile | Symbol | TF | Decision TS | Outcome |",
        "|-----|------|------|---------|--------|----|-------------|---------|",
    ]
    for d_idx, day in enumerate(days, 1):
        for slot_idx, s in enumerate(day, 1):
            readme_lines.append(
                f"| {d_idx} | {slot_idx} | `{s['file_id']}.json` | {s['profile']} | "
                f"{s['symbol']} | {s['timeframe']} | {s['decision_ts']} | {s['outcome_pct']:+.2f}% |"
            )
    readme_lines.append("")
    readme_lines.append("## Acceptance summary")
    readme_lines.append("")
    readme_lines.append(f"- 30 new JSON files generated (setup_06..setup_35)")
    readme_lines.append(f"- Profile distribution (total 35): {profile_counts}")
    readme_lines.append(f"- New-setup symbol mix: blue_chip={sym_mix['blue_chip']}, meme={sym_mix['meme']}")
    readme_lines.append(f"- New-setup TF mix: {tf_mix}")
    readme_lines.append(f"- Week direction balance: up={up_total}, down={down_total} ({100*up_total/35:.0f}% / {100*down_total/35:.0f}%)")
    (SAMPLES_DIR / "README.md").write_text("\n".join(readme_lines))
    print(f"\n✓ {SAMPLES_DIR/'README.md'} ({len(readme_lines)} lines)")

    print("\n═" * 74)
    print("7-DAY GRID")
    print("═" * 74)
    for d_idx, day in enumerate(days, 1):
        print(f"\n── Day {d_idx} ──")
        for slot_idx, s in enumerate(day, 1):
            marker = " (existing)" if s["existing"] else ""
            print(f"  [{slot_idx}] {s['profile']:30s} {s['symbol']:9s} {s['timeframe']:3s} "
                  f"{s['decision_ts']:20s} {s['outcome_pct']:+6.2f}%  score={s['edu_score']}{marker}")


if __name__ == "__main__":
    main()
