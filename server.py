"""
CandleEye · server.py (v0.5)

Each timeframe (1h / 4h / 1d) is its own game:
  - 80 visible context bars
  - 48 future bars horizon
  - TF-specific LONG_BIAS calibrated on each TF's drift
  - Ground truth = close[48 future] > close[decision] on the TF where the user decided

Usage:
    python server.py
"""

from __future__ import annotations

import csv
import json
import os
import random
import secrets
import sys
import time
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from threading import Lock

import pandas as pd
from flask import Flask, Response, jsonify, make_response, request, send_from_directory

ROOT = Path(__file__).parent
DATA_DIRS = {
    "1h": ROOT / "data_1h",
    "4h": ROOT / "data_4h",
    "1d": ROOT / "data_1d",
}
SECTIONS_POOL_FILE = ROOT / "sections_pool.json"
EDU_POOL_FILE = ROOT / "edu_pool.json"
SESSIONS_DIR = ROOT / "sessions"
STATIC_DIR = ROOT / "static"
SESSIONS_DIR.mkdir(exist_ok=True)

# Same dimensions for all TFs — simpler and visually consistent.
CONTEXT_BARS = 80
FUTURE_BARS = 48
WARMUP_BARS = 200
MIN_WINDOW = WARMUP_BARS + CONTEXT_BARS + FUTURE_BARS  # 328 bars needed per TF

# Allowed TOP10 assets (long history).
ALLOWED = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    "ADAUSDT", "DOGEUSDT", "LTCUSDT", "LINKUSDT", "DOTUSDT",
}

DATASETS: dict[str, dict[str, pd.DataFrame]] = {}

# Sections pool: pre-extracted rounds for lightweight deploys.
# If the file exists at boot, the server uses it instead of the raw CSVs.
SECTIONS_POOL: list | None = None

# Edu pool: 35 curated setups with pedagogical_notes (tooltip + holistic) in ES/EN/ZH.
# Rotates cyclically through 7 days of 5 setups each, deterministic by UTC date.
EDU_POOL: list | None = None
EDU_EPOCH = date(2026, 4, 1)  # day 0 of the rotation cycle

# Access token (env var). If set, requests require ?k=<token> or a valid cookie.
# Leave unset locally to skip auth.
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "").strip()
AUTH_COOKIE_NAME = "ce_auth"


def load_all_csvs() -> None:
    primary = DATA_DIRS["1h"]
    if not primary.exists():
        print(f"ERROR: {primary} does not exist. Run data_prep.py first.", file=sys.stderr)
        sys.exit(1)
    symbols = sorted(f.stem for f in primary.glob("*.csv") if f.stem in ALLOWED)
    if not symbols:
        print(f"ERROR: no allowed CSVs in {primary}.", file=sys.stderr)
        sys.exit(1)

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
        if skip:
            print(f"  skip {symbol}: insufficient data on some TF")
            continue
        DATASETS[symbol] = tf_dfs
    print(f"loaded {len(DATASETS)} assets: {', '.join(DATASETS.keys())}")


# ──────────────────────────────────────────────────────────────────────────────
# TF-specific monkey baselines
# ──────────────────────────────────────────────────────────────────────────────

LONG_BIAS_BY_TF: dict[str, float] = {"1h": 0.5, "4h": 0.5, "1d": 0.5}


def historical_long_bias_tf(tf_name: str) -> float:
    """% of windows where close at end-of-future > close at decision, on this TF."""
    ups = 0
    total = 0
    sample_per_asset = 500
    for tfs in DATASETS.values():
        df = tfs[tf_name]
        n = len(df)
        max_start = n - MIN_WINDOW - 1
        if max_start <= 0:
            continue
        for _ in range(sample_per_asset):
            s = random.randint(0, max_start)
            decision_idx = s + WARMUP_BARS + CONTEXT_BARS - 1
            exit_idx = s + WARMUP_BARS + CONTEXT_BARS + FUTURE_BARS - 1
            if df["close"].iat[exit_idx] > df["close"].iat[decision_idx]:
                ups += 1
            total += 1
    return ups / total if total else 0.5


# ──────────────────────────────────────────────────────────────────────────────
# Round cache
# ──────────────────────────────────────────────────────────────────────────────

ROUND_CACHE: dict[str, dict] = {}
CACHE_LOCK = Lock()


def bars_to_list(df: pd.DataFrame) -> list[list]:
    """Compact format: array of [o,h,l,c,v] arrays instead of dicts.
    Saves ~40% payload vs dicts with named keys. Floats rounded to 8 sig digits."""
    out = []
    for r in df.itertuples(index=False):
        out.append([
            round(float(r.open), 8),
            round(float(r.high), 8),
            round(float(r.low), 8),
            round(float(r.close), 8),
            round(float(r.volume), 4),
        ])
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Sections pool loader — lightweight alternative to CSV loading
# ──────────────────────────────────────────────────────────────────────────────

def load_sections_pool() -> bool:
    """Load pre-extracted sections pool if the file exists.
    Returns True if loaded successfully, False to indicate CSV fallback."""
    global SECTIONS_POOL
    if not SECTIONS_POOL_FILE.exists():
        return False
    try:
        with open(SECTIONS_POOL_FILE) as f:
            payload = json.load(f)
        SECTIONS_POOL = payload.get("sections", [])
        print(f"Loaded {len(SECTIONS_POOL)} sections from {SECTIONS_POOL_FILE.name}")
        return True
    except Exception as e:
        print(f"WARNING: failed to load sections pool: {e}", file=sys.stderr)
        return False


def load_edu_pool() -> bool:
    """Load the curated Edu pool (35 setups with pedagogical_notes)."""
    global EDU_POOL
    if not EDU_POOL_FILE.exists():
        print(f"edu pool not found ({EDU_POOL_FILE.name}) — /daily?edu=1 will 503")
        return False
    try:
        with open(EDU_POOL_FILE) as f:
            payload = json.load(f)
        EDU_POOL = payload.get("sections", [])
        print(f"Loaded {len(EDU_POOL)} edu sections from {EDU_POOL_FILE.name}")
        return True
    except Exception as e:
        print(f"WARNING: failed to load edu pool: {e}", file=sys.stderr)
        return False


def edu_section_for_today(chart_index: int, day_offset: int = 0) -> dict | None:
    """Pick the edu section for today's N-th round using a 7-day cyclic rotation.
    Day 0 of the cycle serves setups 1..5, day 1 serves 6..10, ..., day 6 serves 31..35.
    `day_offset` lets the dev "Next day" button preview future days without changing the clock.
    """
    if not EDU_POOL:
        return None
    simulated_date = datetime.utcnow().date() + timedelta(days=day_offset)
    days_since = (simulated_date - EDU_EPOCH).days
    day_in_cycle = days_since % 7
    start = day_in_cycle * 5
    idx = start + (chart_index - 1)
    if idx < 0 or idx >= len(EDU_POOL):
        return None
    return EDU_POOL[idx]


def build_round_from_section(section: dict, rng: random.Random) -> dict:
    """Convert a pool section into the round payload format the client expects.
    Computes bots votes fresh per call (they're cheap and need variance).

    Output bar format: arrays [o,h,l,c,v] (same as bars_to_list) — the client's
    hydrateBars() expects Array.isArray(bars[0]) to be true.
    """
    tf_payloads = {}
    tf_cache = {}

    for tf_name, tfs in section["tfs"].items():
        bars_full = tfs["bars"]
        warmup = tfs["warmup_count"]
        ctx_count = tfs["context_count"]

        # Context slice = warmup + context bars (first warmup+context bars of "bars")
        context_bars = bars_full[: warmup + ctx_count]
        future_bars = bars_full[warmup + ctx_count : warmup + ctx_count + FUTURE_BARS]

        bias = LONG_BIAS_BY_TF.get(tf_name, 0.5)
        monkey_votes = [rng.random() < bias for _ in range(100)]
        monkey_long = sum(monkey_votes)

        tf_cache[tf_name] = {
            "entry_price": tfs["entry_price"],
            "exit_price": tfs["exit_price"],
            "truth": tfs["truth"],
            "decision_ts": tfs["decision_ts"],
            "exit_ts": tfs["exit_ts"],
            "future_bars": [_bar_compact_to_array(b) for b in future_bars],
            "monkey_votes": monkey_votes,
            "monkey_long_count": monkey_long,
        }

        tf_payloads[tf_name] = {
            "bars": [_bar_compact_to_array(b) for b in context_bars],
            "warmup_count": int(warmup),
            "future_count": FUTURE_BARS,
            "monkey_sentiment_long_pct": monkey_long,
            "decision_ts": tfs["decision_ts"],
            "exit_ts": tfs["exit_ts"],
        }

    round_id = secrets.token_hex(8)
    with CACHE_LOCK:
        ROUND_CACHE[round_id] = {
            "symbol": section["symbol"],
            "decision_ts_1h": section.get("decision_ts_1h"),
            "tfs": tf_cache,
            "created_at": time.time(),
            "is_edu": bool(section.get("pedagogical_notes")),
        }
        now = time.time()
        stale = [k for k, v in ROUND_CACHE.items() if now - v["created_at"] > 600]
        for k in stale:
            del ROUND_CACHE[k]

    payload = {
        "round_id": round_id,
        "symbol": section["symbol"],
        "warmup_bars": WARMUP_BARS,
        "future_bars": FUTURE_BARS,
        "context_bars": CONTEXT_BARS,
        "timeframes": tf_payloads,
    }
    if section.get("pedagogical_notes"):
        payload["pedagogical_notes"] = section["pedagogical_notes"]
    if section.get("anchor_tf"):
        payload["anchor_tf"] = section["anchor_tf"]
    return payload


def _bar_compact_to_array(b: dict) -> list:
    """Compact dict {ts,o,h,l,c,v} → [o,h,l,c,v] array (matches bars_to_list output)."""
    return [b["o"], b["h"], b["l"], b["c"], b["v"]]


# ──────────────────────────────────────────────────────────────────────────────
# Flask
# ──────────────────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder=None)


# ──────────────────────────────────────────────────────────────────────────────
# Access token middleware — gates the app behind a single shared password.
# If ACCESS_TOKEN env var is empty (local dev), auth is disabled entirely.
# If set (production), requests need either:
#   - ?k=<token> query param, OR
#   - a valid auth cookie (set automatically after first valid ?k)
# Invalid requests get a tiny password form at /.
# ──────────────────────────────────────────────────────────────────────────────

def is_authed(req) -> bool:
    """Check if the request is authenticated."""
    if not ACCESS_TOKEN:
        return True
    # Query param grants auth immediately
    if req.args.get("k", "") == ACCESS_TOKEN:
        return True
    # Cookie grants auth for subsequent requests
    if req.cookies.get(AUTH_COOKIE_NAME, "") == ACCESS_TOKEN:
        return True
    return False


LOGIN_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Access</title>
<style>
  html,body{height:100%;margin:0;background:#0B0E11;color:#EAECEF;
    font-family:system-ui,sans-serif;-webkit-font-smoothing:antialiased;}
  .box{max-width:320px;margin:18vh auto;padding:24px;background:#1E2026;
    border:1px solid #2B3139;border-radius:14px;}
  h1{font-size:18px;margin:0 0 14px;font-weight:700;}
  input{width:100%;padding:14px;border:1px solid #2B3139;border-radius:8px;
    background:#0B0E11;color:#EAECEF;font-size:15px;box-sizing:border-box;}
  button{width:100%;margin-top:10px;padding:14px;border:none;border-radius:8px;
    background:#F0B90B;color:#0B0E11;font-weight:700;font-size:15px;cursor:pointer;}
  .err{color:#F6465D;font-size:12px;margin-top:10px;min-height:16px;}
</style>
</head><body>
<form class="box" method="POST" action="/auth">
  <h1>Access code</h1>
  <input type="password" name="k" placeholder="code" autofocus required/>
  <button type="submit">Enter</button>
  <div class="err">__ERR__</div>
</form>
</body></html>
"""


@app.before_request
def auth_gate():
    # Let the login POST and static CSS/fonts through
    if request.path == "/auth":
        return None
    if is_authed(request):
        # If auth came from query param, stash it in a cookie for subsequent requests
        if request.args.get("k", "") == ACCESS_TOKEN and ACCESS_TOKEN:
            resp = make_response()
            resp.set_cookie(AUTH_COOKIE_NAME, ACCESS_TOKEN, max_age=60*60*24*30, httponly=False, samesite="Lax")
            # We don't short-circuit here — let the request continue;
            # the cookie will be set on this response by merging below.
            request._set_auth_cookie = True  # flag for after_request
        return None
    # Not authed: serve login page (HTML for GET, 401 JSON for API-ish paths)
    if request.path.startswith("/round") or request.path.startswith("/daily") or \
       request.path.startswith("/decide") or request.path.startswith("/session") or \
       request.path.startswith("/meta"):
        return jsonify({"error": "unauthorized"}), 401
    return Response(LOGIN_HTML.replace("__ERR__", ""), mimetype="text/html")


@app.after_request
def maybe_set_cookie(resp):
    if getattr(request, "_set_auth_cookie", False):
        resp.set_cookie(AUTH_COOKIE_NAME, ACCESS_TOKEN, max_age=60*60*24*30, httponly=False, samesite="Lax")
    return resp


@app.route("/auth", methods=["POST"])
def auth_post():
    submitted = request.form.get("k", "").strip()
    if ACCESS_TOKEN and submitted == ACCESS_TOKEN:
        resp = make_response(Response(
            '<meta http-equiv="refresh" content="0; url=/"/>Redirecting...',
            mimetype="text/html"))
        resp.set_cookie(AUTH_COOKIE_NAME, ACCESS_TOKEN, max_age=60*60*24*30, httponly=False, samesite="Lax")
        return resp
    return Response(LOGIN_HTML.replace("__ERR__", "Wrong code"), mimetype="text/html", status=401)


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/round", methods=["GET"])
def get_round():
    """
    Pick a random (symbol, tf-window) independently for each TF.
    Used for free-play mode.
    """
    return _build_round(rng=random)


def _build_round(rng):
    """Generate a round payload using the provided random source.
    Used by both /round (random) and /daily (deterministic by date)."""
    symbol = rng.choice(list(DATASETS.keys()))
    tfs = DATASETS[symbol]

    # Anchor on 1h for the decision moment
    df_1h = tfs["1h"]
    max_start_1h = len(df_1h) - MIN_WINDOW - 1
    start_1h = rng.randint(0, max_start_1h)
    decision_idx_1h = start_1h + WARMUP_BARS + CONTEXT_BARS - 1
    decision_ts = df_1h["timestamp"].iat[decision_idx_1h]

    tf_payloads = {}
    tf_cache = {}

    for tf_name, tf_df in tfs.items():
        ts = tf_df["timestamp"]
        pos = int(ts.searchsorted(decision_ts, side="right")) - 1
        if pos < 0:
            continue
        future_end = pos + FUTURE_BARS
        if future_end >= len(tf_df):
            return _build_round(rng)

        desired_start = pos - (WARMUP_BARS + CONTEXT_BARS) + 1
        if desired_start < 0:
            return _build_round(rng)
        context_start = desired_start
        actual_warmup = WARMUP_BARS

        context_df = tf_df.iloc[context_start : pos + 1]
        future_df = tf_df.iloc[pos + 1 : future_end + 1]

        entry_price = float(tf_df["close"].iat[pos])
        exit_price = float(tf_df["close"].iat[future_end])
        truth = "long" if exit_price > entry_price else "short"

        bias = LONG_BIAS_BY_TF.get(tf_name, 0.5)
        monkey_votes = [rng.random() < bias for _ in range(100)]
        monkey_long = sum(monkey_votes)

        tf_cache[tf_name] = {
            "entry_price": entry_price,
            "exit_price": exit_price,
            "truth": truth,
            "decision_ts": tf_df["timestamp"].iat[pos].isoformat(),
            "exit_ts": tf_df["timestamp"].iat[future_end].isoformat(),
            "future_bars": bars_to_list(future_df),
            "monkey_votes": monkey_votes,
            "monkey_long_count": monkey_long,
        }

        tf_payloads[tf_name] = {
            "bars": bars_to_list(context_df),
            "warmup_count": int(actual_warmup),
            "future_count": FUTURE_BARS,
            "monkey_sentiment_long_pct": monkey_long,
            "decision_ts": tf_df["timestamp"].iat[pos].isoformat(),
            "exit_ts": tf_df["timestamp"].iat[future_end].isoformat(),
        }

    if not tf_payloads:
        return _build_round(rng)

    round_id = secrets.token_hex(8)
    with CACHE_LOCK:
        ROUND_CACHE[round_id] = {
            "symbol": symbol,
            "decision_ts_1h": decision_ts.isoformat(),
            "tfs": tf_cache,
            "created_at": time.time(),
        }
        now = time.time()
        stale = [k for k, v in ROUND_CACHE.items() if now - v["created_at"] > 600]
        for k in stale:
            del ROUND_CACHE[k]

    return jsonify({
        "round_id": round_id,
        "symbol": symbol,
        "warmup_bars": WARMUP_BARS,
        "future_bars": FUTURE_BARS,
        "context_bars": CONTEXT_BARS,
        "timeframes": tf_payloads,
    })


@app.route("/daily/<int:chart_index>", methods=["GET"])
def get_daily(chart_index):
    """
    Charts of the Day: round N (1..5) for today.
    Everyone who plays today gets the same 5 sections, in the same order —
    the per-day picks are seeded by the UTC date.
    With the sections pool loaded: picks 5 random sections from the pool.
    Without the pool (local dev): builds rounds from CSVs using the same seed.
    """
    if chart_index < 1 or chart_index > 5:
        return jsonify({"error": "chart_index must be 1-5"}), 400

    # Optional dev-only day_offset: shifts the simulated UTC date forward by N days
    # so the "Next day" dev button can preview future rotations without touching the clock.
    try:
        day_offset = int(request.args.get("day_offset", "0"))
    except ValueError:
        day_offset = 0

    # Edu branch: curated pool with pedagogical notes.
    if request.args.get("edu", "") == "1":
        if not EDU_POOL:
            return jsonify({"error": "edu pool not loaded"}), 503
        section = edu_section_for_today(chart_index, day_offset=day_offset)
        if section is None:
            return jsonify({"error": "no edu section for this slot"}), 500
        resp = jsonify(build_round_from_section(section, random.Random()))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    simulated_date = datetime.utcnow().date() + timedelta(days=day_offset)
    today = simulated_date.strftime("%Y-%m-%d")

    if SECTIONS_POOL:
        # Pool mode: sample 5 sections for today, deterministically
        day_rng = random.Random(f"candleeye:day:{today}")
        indices = day_rng.sample(range(len(SECTIONS_POOL)), min(5, len(SECTIONS_POOL)))
        section_idx = indices[chart_index - 1]
        section = SECTIONS_POOL[section_idx]
        # Per-round RNG for bots (fresh each call, not deterministic — bots have variance)
        bot_rng = random.Random()
        resp = jsonify(build_round_from_section(section, bot_rng))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # CSV fallback mode (legacy, local dev only)
    seed = f"candleeye:{today}:{chart_index}"
    daily_rng = random.Random(seed)
    resp = _build_round(daily_rng)
    if hasattr(resp, "headers"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/decide", methods=["POST"])
def decide():
    data = request.get_json(force=True)
    round_id = data.get("round_id")
    decision = data.get("decision")
    tf_used = data.get("tf_used", "1h")

    with CACHE_LOCK:
        cached = ROUND_CACHE.pop(round_id, None)
    if cached is None:
        return jsonify({"error": "round expired or unknown"}), 404

    tf_info = cached["tfs"].get(tf_used)
    if tf_info is None:
        return jsonify({"error": f"tf {tf_used} not in round"}), 400

    is_timeout = decision is None
    hit = (not is_timeout) and (decision == tf_info["truth"])

    monkey_votes = tf_info["monkey_votes"]
    monkeys_long = sum(monkey_votes)
    monkeys_short = 100 - monkeys_long
    monkey_decision = "long" if monkeys_long > monkeys_short else "short"
    monkey_hit = monkey_decision == tf_info["truth"]
    monkey_hits_individual = monkeys_long if tf_info["truth"] == "long" else monkeys_short

    pct_change = (tf_info["exit_price"] - tf_info["entry_price"]) / tf_info["entry_price"] * 100

    # Return future bars for ALL TFs so UI can still let user click through,
    # but the canonical result is on tf_used.
    futures = {tf_name: info["future_bars"] for tf_name, info in cached["tfs"].items()}

    return jsonify({
        "round_id": round_id,
        "truth": tf_info["truth"],
        "hit": hit,
        "timeout": is_timeout,
        "decision": decision,
        "tf_used": tf_used,
        "symbol": cached["symbol"],
        "decision_ts": tf_info["decision_ts"],
        "exit_ts": tf_info["exit_ts"],
        "entry_price": tf_info["entry_price"],
        "exit_price": tf_info["exit_price"],
        "pct_change": pct_change,
        "future_bars_by_tf": futures,
        "monkey_decision": monkey_decision,
        "monkey_hit": monkey_hit,
        "monkey_sentiment_long_pct": tf_info["monkey_long_count"],
        "monkey_hits_individual": monkey_hits_individual,
        "edu": bool(cached.get("is_edu")),
    })


@app.route("/session", methods=["POST"])
def save_session():
    data = request.get_json(force=True)
    rounds = data.get("rounds", [])
    if not rounds:
        return jsonify({"error": "no rounds"}), 400
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = SESSIONS_DIR / f"{stamp}.csv"
    fieldnames = [
        "round_idx", "symbol", "decision_ts", "exit_ts",
        "entry_price", "exit_price", "pct_change",
        "decision", "truth", "hit", "timeout", "tf_used",
        "ms_to_decide", "points", "streak_after", "score_after",
        "monkey_decision", "monkey_hit",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rounds:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return jsonify({"saved": str(path.name), "rounds": len(rounds)})


@app.route("/meta", methods=["GET"])
def meta():
    return jsonify({
        "assets": list(DATASETS.keys()) if DATASETS else [],
        "long_bias_by_tf": LONG_BIAS_BY_TF,
        "context_bars": CONTEXT_BARS,
        "future_bars": FUTURE_BARS,
        "warmup_bars": WARMUP_BARS,
        "timeframes": list(DATA_DIRS.keys()),
        "mode": "pool" if SECTIONS_POOL else "csv",
    })


# ──────────────────────────────────────────────────────────────────────────────
# Bootstrap — runs both under `python server.py` and under gunicorn/Railway.
# Priority: pool file > CSVs. Pool mode is deploy-friendly (~1-2MB vs ~150MB).
# ──────────────────────────────────────────────────────────────────────────────

def _bootstrap():
    # Default sensible biases so the app boots even if we skip CSV loading entirely.
    # These are historical cripto long-bias values (~54% on the TFs we care about).
    LONG_BIAS_BY_TF.setdefault("1h", 0.5381)
    LONG_BIAS_BY_TF.setdefault("4h", 0.5402)
    LONG_BIAS_BY_TF.setdefault("1d", 0.5614)

    if load_sections_pool():
        print("mode: SECTIONS POOL (deploy-ready, no CSVs needed)")
        load_edu_pool()
        return

    # Fallback: legacy CSV mode
    print("mode: CSV (legacy / local dev)")
    load_all_csvs()
    print("computing TF-specific historical long bias...")
    for tf_name in DATA_DIRS.keys():
        bias = historical_long_bias_tf(tf_name)
        LONG_BIAS_BY_TF[tf_name] = round(bias, 4)
        print(f"  {tf_name}: {bias:.4f}")
    load_edu_pool()


# Boot on import (works with gunicorn: `gunicorn server:app`)
_bootstrap()


if __name__ == "__main__":
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = None

    port = int(os.environ.get("PORT", "5050"))
    print("\nserver ready:")
    print(f"  on this mac:   http://localhost:{port}")
    if local_ip:
        print(f"  on iphone:     http://{local_ip}:{port}   (same wifi)")
    if ACCESS_TOKEN:
        print(f"  access token:  set via ACCESS_TOKEN env var")
    else:
        print(f"  access token:  (none — auth disabled)")
    print()
    app.run(host="0.0.0.0", port=port, debug=False)
