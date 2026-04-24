"""
generate_notes.py — Produce 210 pedagogical_notes (35 setups × 2 variants × 3 langs)

Consumes metadata_35.json (real signals per setup).
Emits notes_35.json: {setups: [{setup_num, pedagogical_notes: {tooltip, holistic}}]}

Design principles:
- Consistent vocabulary across languages (same concept → same phrasing rule)
- Descriptive, never categorical. No "es fiable", no "seguro subirá".
- No questions (bias the player), no imperatives ("mira", "look").
- Tooltip: one idea, ≤70 chars ES/EN, ~15-25 chars ZH equivalent.
- Holistic: context + outcome with real pct, ≤100 chars ES/EN.
- Holistic explains why outcome happened (reconciles signals with direction).
"""

import json
from pathlib import Path


# ────────────────────────────────────────────────────────────────────
# Trilingual vocabulary building blocks
# ────────────────────────────────────────────────────────────────────

# Contextual phrases by signal state.
# Each entry: (es, en, zh). Used compositionally.

TREND = {
    'bullish_strong':  ("tendencia alcista firme", "strong uptrend", "趋势强势上涨"),
    'bullish':         ("tendencia alcista",       "uptrend",        "趋势上涨"),
    'bearish_strong':  ("tendencia bajista firme", "strong downtrend","趋势强势下跌"),
    'bearish':         ("tendencia bajista",       "downtrend",      "趋势下跌"),
    'sideways':        ("lateralidad",             "sideways",       "横盘"),
}

VOLUME = {
    'rising':     ("volumen creciente",   "volume rising",     "成交量上升"),
    'falling':    ("volumen cae",         "volume fading",     "成交量萎缩"),
    'climactic':  ("volumen climático",   "volume climax",     "成交量高潮"),
    'normal':     ("volumen normal",      "volume normal",     "成交量正常"),
}

MOMENTUM = {
    'accelerating_up':   ("momentum acelera",    "momentum accelerating", "动量加速"),
    'accelerating_down': ("momentum se acelera abajo", "momentum accelerating down", "动量下跌加速"),
    'mixed':             ("momentum mixto",      "mixed momentum",        "动量混杂"),
    'indecisive':        ("momentum duda",       "momentum hesitates",    "动量犹豫"),
}

RSI = {
    'overbought_extreme': ("RSI en extremo alto",   "RSI extreme overbought", "RSI 极度超买"),
    'overbought':         ("RSI sobrecomprado",     "RSI overbought",         "RSI 超买"),
    'neutral_high':       ("RSI neutro alto",       "RSI high-neutral",       "RSI 中性偏高"),
    'neutral':            ("RSI neutro",            "RSI neutral",            "RSI 中性"),
    'neutral_low':        ("RSI neutro bajo",       "RSI low-neutral",        "RSI 中性偏低"),
    'oversold':           ("RSI sobrevendido",      "RSI oversold",           "RSI 超卖"),
    'oversold_extreme':   ("RSI en extremo bajo",   "RSI extreme oversold",   "RSI 极度超卖"),
}

MA_CROSS = {
    'fresh_bullish_cross':   ("cruce alcista fresco de medias",   "fresh bullish MA cross",   "均线金叉新鲜"),
    'recent_bullish_cross':  ("cruce alcista reciente",            "recent bullish cross",    "均线金叉"),
    'ma7_above_stable':      ("media 7 estable arriba",            "MA7 stable above",        "MA7 稳定于上方"),
    'fresh_bearish_cross':   ("cruce bajista fresco",              "fresh bearish cross",     "均线死叉新鲜"),
    'recent_bearish_cross':  ("cruce bajista reciente",            "recent bearish cross",    "均线死叉"),
    'ma7_below_stable':      ("media 7 estable abajo",             "MA7 stable below",        "MA7 稳定于下方"),
}

PVMA = {
    'far_above':  ("precio lejos sobre MA25",  "price far above MA25",  "价格远高于 MA25"),
    'above':      ("precio sobre MA25",        "price above MA25",       "价格高于 MA25"),
    'below':      ("precio bajo MA25",         "price below MA25",       "价格低于 MA25"),
    'far_below':  ("precio lejos bajo MA25",   "price far below MA25",   "价格远低于 MA25"),
}

SR = {
    'near_support':     ("cerca de soporte",      "near support",      "接近支撑"),
    'near_resistance':  ("cerca de resistencia",  "near resistance",   "接近阻力"),
    'breaking_support': ("rompiendo soporte",     "breaking support",  "跌破支撑"),
    'mid_range':        ("en zona media",         "mid-range",         "处于区间中段"),
}


# ────────────────────────────────────────────────────────────────────
# Templates per profile
# ────────────────────────────────────────────────────────────────────

# Each profile returns (tooltip_es, tooltip_en, tooltip_zh, holistic_es, holistic_en, holistic_zh)
# given the setup's signals + outcome.

def fmt_pct(pct):
    """Signed percentage string like '+4.48%' or '-3.21%'."""
    sign = '+' if pct >= 0 else ''
    return f"{sign}{pct:.2f}%"


def pick(vocab, state, default=None):
    """Safe pick from vocab dict; returns tuple (es, en, zh)."""
    if state in vocab:
        return vocab[state]
    return default


def build_confirmed_bullish_notes(s):
    """Setup is bullish and outcome is up. Signals align, reading is clean."""
    pct = s['outcome_pct']
    vol = s['signals']['volume_relative']['state']
    mom = s['signals']['recent_momentum']['state']
    cross = s['signals']['ma_cross_7_25']['state']
    rsi = s['signals']['rsi_zone']['state']
    pvma = s['signals']['price_vs_ma25']['state']
    
    # Tooltip candidates
    candidates = []
    if vol == 'rising':
        candidates.append(("Tendencia alcista clara, volumen acompaña.",
                          "Clean uptrend, volume confirms.",
                          "趋势明确上涨,成交量支持。"))
    if cross in ('fresh_bullish_cross', 'recent_bullish_cross'):
        candidates.append(("Tendencia alcista con cruce reciente de medias.",
                          "Uptrend with recent MA bullish cross.",
                          "趋势上涨,均线金叉。"))
    if mom == 'accelerating_up':
        candidates.append(("Tendencia alcista y momentum acelerando.",
                          "Uptrend with accelerating momentum.",
                          "趋势上涨,动量加速。"))
    if pvma == 'far_above':
        candidates.append(("Precio muy por encima de MA25, tendencia firme.",
                          "Price far above MA25, trend firm.",
                          "价格远高于 MA25,趋势稳固。"))
    if pvma == 'above' and cross == 'ma7_above_stable':
        candidates.append(("Precio y medias alineados al alza.",
                          "Price and MAs aligned upward.",
                          "价格与均线向上对齐。"))
    if rsi == 'neutral_high':
        candidates.append(("Tendencia alcista sin sobrecompra aún.",
                          "Uptrend not yet overbought.",
                          "趋势上涨,尚未超买。"))
    candidates.append(("Tendencia alcista, estructura sostenida.",
                      "Uptrend, structure sustained.",
                      "趋势上涨,结构稳固。"))
    
    idx = (s['setup_num'] - 1) % len(candidates)
    t_es, t_en, t_zh = candidates[idx]
    
    # Holistic variants — rotate by setup_num
    holistic_variants = [
        (f"Señal alcista limpia y contexto a favor. El precio subió {fmt_pct(pct)}.",
         f"Clean bullish signal with context aligned. Price rose {fmt_pct(pct)}.",
         f"看涨信号清晰,背景支持。价格上涨 {fmt_pct(pct)}。"),
        (f"Contexto alcista coherente con la acción del precio. El precio subió {fmt_pct(pct)}.",
         f"Bullish context coherent with price action. Price rose {fmt_pct(pct)}.",
         f"看涨背景与价格一致。价格上涨 {fmt_pct(pct)}。"),
        (f"Dirección alcista sostenida por el contexto. El precio subió {fmt_pct(pct)}.",
         f"Bullish direction sustained by context. Price rose {fmt_pct(pct)}.",
         f"背景支撑看涨方向。价格上涨 {fmt_pct(pct)}。"),
    ]
    h_es, h_en, h_zh = holistic_variants[(s['setup_num'] - 1) % len(holistic_variants)]
    
    return (t_es, t_en, t_zh, h_es, h_en, h_zh)


def build_confirmed_bearish_notes(s):
    """Bearish bias with clear context, outcome down."""
    pct = s['outcome_pct']
    vol = s['signals']['volume_relative']['state']
    mom = s['signals']['recent_momentum']['state']
    cross = s['signals']['ma_cross_7_25']['state']
    pvma = s['signals']['price_vs_ma25']['state']
    rsi = s['signals']['rsi_zone']['state']
    
    candidates = []
    if vol == 'rising':
        candidates.append(("Tendencia bajista con volumen al alza.",
                          "Downtrend with rising volume.",
                          "趋势下跌,成交量上升。"))
    if cross in ('fresh_bearish_cross', 'recent_bearish_cross'):
        candidates.append(("Tendencia bajista tras cruce de medias.",
                          "Downtrend after MA bearish cross.",
                          "均线死叉后趋势下跌。"))
    if mom == 'accelerating_down':
        candidates.append(("Tendencia bajista y momentum se acelera abajo.",
                          "Downtrend with momentum accelerating down.",
                          "趋势下跌,动量加速下行。"))
    if pvma == 'far_below':
        candidates.append(("Precio muy por debajo de MA25, presión firme.",
                          "Price far below MA25, pressure firm.",
                          "价格远低于 MA25,压力稳固。"))
    if pvma == 'below' and cross == 'ma7_below_stable':
        candidates.append(("Precio y medias alineados a la baja.",
                          "Price and MAs aligned downward.",
                          "价格与均线向下对齐。"))
    if rsi == 'neutral_low':
        candidates.append(("Tendencia bajista sin sobreventa aún.",
                          "Downtrend not yet oversold.",
                          "趋势下跌,尚未超卖。"))
    candidates.append(("Tendencia bajista sostenida.",
                      "Sustained downtrend.",
                      "趋势持续下跌。"))
    
    idx = (s['setup_num'] - 1) % len(candidates)
    t_es, t_en, t_zh = candidates[idx]
    
    holistic_variants = [
        (f"Señal bajista firme y contexto coherente. El precio cayó {fmt_pct(pct)}.",
         f"Firm bearish signal with coherent context. Price fell {fmt_pct(pct)}.",
         f"看跌信号稳固,背景一致。价格下跌 {fmt_pct(pct)}。"),
        (f"Contexto bajista consistente con la caída. El precio cayó {fmt_pct(pct)}.",
         f"Bearish context consistent with drop. Price fell {fmt_pct(pct)}.",
         f"看跌背景与跌幅一致。价格下跌 {fmt_pct(pct)}。"),
        (f"Dirección bajista confirmada por el contexto. El precio cayó {fmt_pct(pct)}.",
         f"Bearish direction confirmed by context. Price fell {fmt_pct(pct)}.",
         f"背景确认看跌方向。价格下跌 {fmt_pct(pct)}。"),
    ]
    h_es, h_en, h_zh = holistic_variants[(s['setup_num'] - 1) % len(holistic_variants)]
    
    return (t_es, t_en, t_zh, h_es, h_en, h_zh)


def build_contrarian_bullish_falla_notes(s):
    """Bullish signals but outcome DOWN."""
    pct = s['outcome_pct']
    vol = s['signals']['volume_relative']['state']
    mom = s['signals']['recent_momentum']['state']
    rsi = s['signals']['rsi_zone']['state']
    pvma = s['signals']['price_vs_ma25']['state']
    
    candidates = []
    if vol == 'falling' and mom in ('mixed', 'indecisive'):
        candidates.append(("Tendencia alcista, pero volumen cae y momentum duda.",
                          "Uptrend, but volume fades and momentum hesitates.",
                          "趋势上涨,但成交量萎缩、动量犹豫。"))
    if vol == 'falling':
        candidates.append(("Tendencia alcista con volumen menguando.",
                          "Uptrend with fading volume.",
                          "趋势上涨,但成交量萎缩。"))
    if mom in ('mixed', 'indecisive'):
        candidates.append(("Tendencia alcista, pero momentum no acompaña.",
                          "Uptrend, but momentum not following.",
                          "趋势上涨,但动量不跟进。"))
    if rsi in ('overbought', 'overbought_extreme'):
        candidates.append(("Tendencia alcista con RSI estirado.",
                          "Uptrend with stretched RSI.",
                          "趋势上涨,但 RSI 过度延伸。"))
    if pvma == 'far_above':
        candidates.append(("Precio muy estirado sobre MA25, alcista frágil.",
                          "Price stretched above MA25, uptrend fragile.",
                          "价格过度高于 MA25,涨势脆弱。"))
    if vol == 'climactic':
        candidates.append(("Tendencia alcista con volumen climático.",
                          "Uptrend with climactic volume.",
                          "趋势上涨,但成交量高潮。"))
    candidates.append(("Tendencia alcista, pero contexto se agota.",
                      "Uptrend, but context wearing thin.",
                      "趋势上涨,但背景正在耗尽。"))
    
    idx = (s['setup_num'] - 1) % len(candidates)
    t_es, t_en, t_zh = candidates[idx]
    
    holistic_variants = [
        (f"Dirección alcista aparente, contexto en contra. El precio cayó {fmt_pct(pct)}.",
         f"Apparent bullish direction, context against. Price fell {fmt_pct(pct)}.",
         f"方向看似上涨,背景相反。价格下跌 {fmt_pct(pct)}。"),
        (f"Señal alcista superficial, el fondo cedió. El precio cayó {fmt_pct(pct)}.",
         f"Surface bullish signal, underlying gave. Price fell {fmt_pct(pct)}.",
         f"表面看涨,但基础让步。价格下跌 {fmt_pct(pct)}。"),
        (f"La tendencia alcista no sostuvo el contexto. El precio cayó {fmt_pct(pct)}.",
         f"Uptrend did not sustain context. Price fell {fmt_pct(pct)}.",
         f"涨势未能维持背景。价格下跌 {fmt_pct(pct)}。"),
    ]
    h_es, h_en, h_zh = holistic_variants[(s['setup_num'] - 1) % len(holistic_variants)]
    
    return (t_es, t_en, t_zh, h_es, h_en, h_zh)


def build_contrarian_bearish_falla_notes(s):
    """Bearish signals but outcome UP."""
    pct = s['outcome_pct']
    vol = s['signals']['volume_relative']['state']
    mom = s['signals']['recent_momentum']['state']
    rsi = s['signals']['rsi_zone']['state']
    pvma = s['signals']['price_vs_ma25']['state']
    sr = s['signals']['support_resistance']['state']
    
    candidates = []
    if vol == 'climactic':
        candidates.append(("Tendencia bajista con volumen climático.",
                          "Downtrend with climactic volume.",
                          "趋势下跌,成交量高潮。"))
    if rsi in ('oversold', 'oversold_extreme'):
        candidates.append(("Tendencia bajista con RSI estirado abajo.",
                          "Downtrend with RSI stretched down.",
                          "趋势下跌,但 RSI 过度超卖。"))
    if vol == 'falling' and mom in ('mixed', 'indecisive'):
        candidates.append(("Tendencia bajista, pero presión vendedora se agota.",
                          "Downtrend, but selling pressure exhausting.",
                          "趋势下跌,但卖压耗尽。"))
    if mom in ('mixed', 'indecisive'):
        candidates.append(("Tendencia bajista, pero momentum no acompaña.",
                          "Downtrend, but momentum not following.",
                          "趋势下跌,但动量不跟进。"))
    if sr == 'near_support':
        candidates.append(("Tendencia bajista cerca de soporte clave.",
                          "Downtrend near key support.",
                          "趋势下跌,接近关键支撑。"))
    if pvma == 'far_below':
        candidates.append(("Precio muy estirado bajo MA25, rebote posible.",
                          "Price stretched below MA25, bounce possible.",
                          "价格过度低于 MA25,可能反弹。"))
    candidates.append(("Tendencia bajista con agotamiento visible.",
                      "Downtrend with visible exhaustion.",
                      "趋势下跌,显现衰竭。"))
    
    idx = (s['setup_num'] - 1) % len(candidates)
    t_es, t_en, t_zh = candidates[idx]
    
    holistic_variants = [
        (f"Dirección bajista aparente, contexto agotado. El precio subió {fmt_pct(pct)}.",
         f"Apparent bearish direction, context exhausted. Price rose {fmt_pct(pct)}.",
         f"方向看似下跌,背景耗尽。价格上涨 {fmt_pct(pct)}。"),
        (f"Señal bajista sin respaldo, rebote técnico. El precio subió {fmt_pct(pct)}.",
         f"Bearish signal without support, technical bounce. Price rose {fmt_pct(pct)}.",
         f"看跌信号无支撑,技术反弹。价格上涨 {fmt_pct(pct)}。"),
        (f"La tendencia bajista se agotó ahí. El precio subió {fmt_pct(pct)}.",
         f"Downtrend exhausted at that point. Price rose {fmt_pct(pct)}.",
         f"跌势在此耗尽。价格上涨 {fmt_pct(pct)}。"),
    ]
    h_es, h_en, h_zh = holistic_variants[(s['setup_num'] - 1) % len(holistic_variants)]
    
    return (t_es, t_en, t_zh, h_es, h_en, h_zh)


def build_rsi_extremo_continua_notes(s):
    """RSI extreme but trend continues."""
    pct = s['outcome_pct']
    rsi_state = s['signals']['rsi_zone']['state']
    direction = s['direction']
    mom = s['signals']['recent_momentum']['state']
    vol = s['signals']['volume_relative']['state']
    
    candidates = []
    
    if rsi_state == 'overbought_extreme':
        candidates.append(("Tendencia alcista con RSI en extremo alto.",
                          "Uptrend with RSI at extreme high.",
                          "趋势上涨,RSI 极度超买。"))
        if mom == 'accelerating_up':
            candidates.append(("RSI extremo alto, momentum alcista persistente.",
                              "Extreme RSI, momentum persists up.",
                              "RSI 极高,动量持续上涨。"))
        if vol == 'rising':
            candidates.append(("RSI alto pero volumen aún al alza.",
                              "High RSI but volume still rising.",
                              "RSI 偏高,但成交量仍在上升。"))
    elif rsi_state == 'overbought':
        candidates.append(("Tendencia alcista con RSI sobrecomprado.",
                          "Uptrend with overbought RSI.",
                          "趋势上涨,RSI 超买。"))
    elif rsi_state == 'oversold_extreme':
        candidates.append(("Tendencia bajista con RSI en extremo bajo.",
                          "Downtrend with RSI at extreme low.",
                          "趋势下跌,RSI 极度超卖。"))
        if mom == 'accelerating_down':
            candidates.append(("RSI extremo bajo, momentum bajista persistente.",
                              "Extreme low RSI, momentum persists down.",
                              "RSI 极低,动量持续下跌。"))
        if vol == 'rising':
            candidates.append(("RSI bajo pero volumen aún al alza.",
                              "Low RSI but volume still rising.",
                              "RSI 偏低,但成交量仍在上升。"))
    elif rsi_state == 'oversold':
        candidates.append(("Tendencia bajista con RSI sobrevendido.",
                          "Downtrend with oversold RSI.",
                          "趋势下跌,RSI 超卖。"))
    
    if direction == 'up':
        candidates.append(("Tendencia alcista con RSI estirado, continúa.",
                          "Uptrend with stretched RSI, continues.",
                          "趋势上涨,RSI 延伸,继续。"))
    else:
        candidates.append(("Tendencia bajista con RSI estirado, continúa.",
                          "Downtrend with stretched RSI, continues.",
                          "趋势下跌,RSI 延伸,继续。"))
    
    idx = (s['setup_num'] - 1) % len(candidates)
    t_es, t_en, t_zh = candidates[idx]
    
    if direction == 'up':
        holistic_variants = [
            (f"RSI estirado no revirtió la tendencia. El precio subió {fmt_pct(pct)}.",
             f"Stretched RSI did not flip trend. Price rose {fmt_pct(pct)}.",
             f"RSI 延伸未扭转趋势。价格上涨 {fmt_pct(pct)}。"),
            (f"El extremo de RSI continuó al alza. El precio subió {fmt_pct(pct)}.",
             f"RSI extreme continued higher. Price rose {fmt_pct(pct)}.",
             f"RSI 极值继续上涨。价格上涨 {fmt_pct(pct)}。"),
            (f"Sobrecompra no detuvo la subida. El precio subió {fmt_pct(pct)}.",
             f"Overbought did not stop the rise. Price rose {fmt_pct(pct)}.",
             f"超买未能阻止上涨。价格上涨 {fmt_pct(pct)}。"),
        ]
    else:
        holistic_variants = [
            (f"RSI estirado no revirtió la tendencia. El precio cayó {fmt_pct(pct)}.",
             f"Stretched RSI did not flip trend. Price fell {fmt_pct(pct)}.",
             f"RSI 延伸未扭转趋势。价格下跌 {fmt_pct(pct)}。"),
            (f"El extremo de RSI continuó a la baja. El precio cayó {fmt_pct(pct)}.",
             f"RSI extreme continued lower. Price fell {fmt_pct(pct)}.",
             f"RSI 极值继续下跌。价格下跌 {fmt_pct(pct)}。"),
            (f"Sobreventa no detuvo la caída. El precio cayó {fmt_pct(pct)}.",
             f"Oversold did not stop the fall. Price fell {fmt_pct(pct)}.",
             f"超卖未能阻止下跌。价格下跌 {fmt_pct(pct)}。"),
        ]
    h_es, h_en, h_zh = holistic_variants[(s['setup_num'] - 1) % len(holistic_variants)]
    
    return (t_es, t_en, t_zh, h_es, h_en, h_zh)


def build_contrarian_pedagogico_estrella_notes(s):
    """Special one-off: setup 3, pedagogical star."""
    pct = s['outcome_pct']
    direction = s['direction']
    
    # Highlight the tension between surface and deep signals
    if direction == 'up':
        t_es = "Señal bajista visible, pero lectura profunda sugiere rebote."
        t_en = "Visible bearish signal, deep read hints at bounce."
        t_zh = "表面看跌信号,但深层读法暗示反弹。"
        h_es = f"Señal superficial bajista, contexto profundo alcista. El precio subió {fmt_pct(pct)}."
        h_en = f"Surface bearish, deep context bullish. Price rose {fmt_pct(pct)}."
        h_zh = f"表面看跌,深层背景看涨。价格上涨 {fmt_pct(pct)}。"
    else:
        t_es = "Señal alcista visible, pero lectura profunda advierte."
        t_en = "Visible bullish signal, deep read warns."
        t_zh = "表面看涨信号,但深层读法示警。"
        h_es = f"Señal superficial alcista, contexto profundo bajista. El precio cayó {fmt_pct(pct)}."
        h_en = f"Surface bullish, deep context bearish. Price fell {fmt_pct(pct)}."
        h_zh = f"表面看涨,深层背景看跌。价格下跌 {fmt_pct(pct)}。"
    
    return (t_es, t_en, t_zh, h_es, h_en, h_zh)


def build_contrarian_segundo_directo_notes(s):
    """Setup 4: contrarian where signals converge in the counterintuitive direction."""
    pct = s['outcome_pct']
    direction = s['direction']
    
    if direction == 'up':
        t_es = "Contexto bajista, pero señal de rebote clara."
        t_en = "Bearish context, clear bounce signal."
        t_zh = "背景看跌,但反弹信号清晰。"
        h_es = f"Contexto bajista con rebote técnico. El precio subió {fmt_pct(pct)}."
        h_en = f"Bearish context with technical bounce. Price rose {fmt_pct(pct)}."
        h_zh = f"背景看跌,但技术性反弹。价格上涨 {fmt_pct(pct)}。"
    else:
        t_es = "Contexto alcista, pero señal de retroceso clara."
        t_en = "Bullish context, clear pullback signal."
        t_zh = "背景看涨,但回落信号清晰。"
        h_es = f"Contexto alcista con retroceso técnico. El precio cayó {fmt_pct(pct)}."
        h_en = f"Bullish context with technical pullback. Price fell {fmt_pct(pct)}."
        h_zh = f"背景看涨,但技术性回落。价格下跌 {fmt_pct(pct)}。"
    
    return (t_es, t_en, t_zh, h_es, h_en, h_zh)


# ────────────────────────────────────────────────────────────────────
# Dispatcher
# ────────────────────────────────────────────────────────────────────

PROFILE_BUILDERS = {
    'confirmed_bullish_obvio':          build_confirmed_bullish_notes,
    'confirmed_bearish_bluechip':       build_confirmed_bearish_notes,
    'contrarian_bullish_falla':         build_contrarian_bullish_falla_notes,
    'contrarian_bearish_falla':         build_contrarian_bearish_falla_notes,
    'rsi_extremo_continua':             build_rsi_extremo_continua_notes,
    'contrarian_pedagogico_estrella':   build_contrarian_pedagogico_estrella_notes,
    'contrarian_segundo_directo':       build_contrarian_segundo_directo_notes,
}


def generate_notes(setup):
    builder = PROFILE_BUILDERS.get(setup['profile'])
    if not builder:
        raise ValueError(f"No builder for profile {setup['profile']}")
    t_es, t_en, t_zh, h_es, h_en, h_zh = builder(setup)
    return {
        "tooltip": {"es": t_es, "en": t_en, "zh": t_zh},
        "holistic": {"es": h_es, "en": h_en, "zh": h_zh},
    }


def validate(notes, setup_num):
    """Lint: check lengths, no questions/imperatives/categorical claims."""
    errors = []
    for variant in ('tooltip', 'holistic'):
        for lang in ('es', 'en', 'zh'):
            txt = notes[variant][lang]
            if not txt or not txt.strip():
                errors.append(f"setup {setup_num}: empty {variant}.{lang}")
            if lang in ('es', 'en'):
                limit = 70 if variant == 'tooltip' else 100
                if len(txt) > limit:
                    errors.append(f"setup {setup_num}: {variant}.{lang} len {len(txt)} > {limit}: {txt!r}")
            # No questions
            if '?' in txt or '¿' in txt or '?' in txt:
                errors.append(f"setup {setup_num}: {variant}.{lang} contains question: {txt!r}")
            # No imperatives (ES/EN)
            imperatives = {
                'es': ('Mira ', 'mira el ', 'Observa', 'Fíjate', 'Ten en cuenta'),
                'en': ('Look ', 'look at', 'Watch ', 'Notice ', 'Beware'),
            }
            if lang in imperatives:
                for imp in imperatives[lang]:
                    if imp in txt:
                        errors.append(f"setup {setup_num}: {variant}.{lang} imperative '{imp}': {txt!r}")
            # No categorical claims
            categorical = {
                'es': ('es fiable', 'no falla', 'siempre ', 'nunca '),
                'en': ('is reliable', 'never fails', 'always ', 'never '),
            }
            if lang in categorical:
                for cat in categorical[lang]:
                    if cat in txt.lower():
                        errors.append(f"setup {setup_num}: {variant}.{lang} categorical '{cat}': {txt!r}")
    return errors


# ────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────

def main():
    meta = json.load(open('/home/claude/edu_notes/metadata_35.json'))
    setups = meta['setups']
    
    output = {"generated_at": meta['generated_at'], "setups": []}
    all_errors = []
    
    for s in setups:
        notes = generate_notes(s)
        errors = validate(notes, s['setup_num'])
        all_errors.extend(errors)
        output['setups'].append({
            "setup_num": s['setup_num'],
            "setup_id": s['setup_id'],
            "symbol": s['symbol'],
            "profile": s['profile'],
            "direction": s['direction'],
            "outcome_pct": s['outcome_pct'],
            "pedagogical_notes": notes,
        })
    
    # Report
    print(f"Generated {len(output['setups'])} sets of notes")
    print(f"Total strings: {len(output['setups']) * 6}")
    if all_errors:
        print(f"\n✗ VALIDATION ERRORS ({len(all_errors)}):")
        for e in all_errors:
            print(f"  {e}")
    else:
        print("\n✓ All 210 notes pass validation")
    
    # Sample output
    print("\n=== SAMPLES ===")
    for i in (0, 1, 2, 3, 4, 17, 22, 29):
        s = output['setups'][i]
        print(f"\nSetup {s['setup_num']:02d} · {s['profile']} · {s['symbol']} · {s['outcome_pct']:+.2f}%")
        for variant in ('tooltip', 'holistic'):
            for lang in ('es', 'en', 'zh'):
                print(f"  {variant}.{lang}: {s['pedagogical_notes'][variant][lang]}")
    
    # Save
    out_path = Path('/home/claude/edu_notes/notes_35.json')
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nSaved to {out_path}")

if __name__ == '__main__':
    main()
