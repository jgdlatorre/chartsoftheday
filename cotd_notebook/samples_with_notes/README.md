# COTD Editorial Sample — 35 Finalists (7 days × 5 profiles)

Five existing hand-picked setups (setup_01..setup_05) plus 30 generated from the full scan pool (edu_score ≥ 70, 2020–2025, |outcome_pct| ∈ [2,10]).

**Profile legend**
- `confirmed_bullish_obvio` — trend+MA confirm bullish, outcome up
- `confirmed_bearish_bluechip` — trend+volume+MA confirm bearish, outcome down
- `contrarian_bullish_falla` — bullish signals with erosion (weak momentum / falling volume / overextended), outcome down
- `contrarian_bearish_falla` — bearish signals with reversal hint (climactic volume / divergence / oversold RSI), outcome up
- `rsi_extremo_continua` — RSI in extreme zone continues instead of reverting

**Note on symbols.** Only DOGEUSDT is available from the spec's meme list (SHIB/PEPE/WIF/BONK/FLOKI and AVAX are not in `data_1h/4h/1d`). The 20% meme quota is satisfied with DOGEUSDT only; remainder is blue-chip.

**Note on schema.** The 5 existing files have `pedagogical_notes: ""` (string); the 30 new files have `pedagogical_notes: {}` (object), per the spec update for this phase.

## 7-day grid

| Día | Slot | File | Profile | Symbol | TF | Decision TS | Outcome |
|-----|------|------|---------|--------|----|-------------|---------|
| 1 | 1 | `setup_01_confirmed_bullish.json` | confirmed_bullish_obvio | XRPUSDT | 1d | 2024-09-18T00:00:00 | +4.48% |
| 1 | 2 | `setup_02_confirmed_bearish.json` | confirmed_bearish_bluechip | ETHUSDT | 1h | 2020-02-25T14:00:00 | -5.28% |
| 1 | 3 | `setup_03_contrarian_star.json` | contrarian_bullish_falla | BTCUSDT | 1h | 2020-01-08T08:00:00 | -3.21% |
| 1 | 4 | `setup_23_contrarian_bear_fails.json` | contrarian_bearish_falla | XRPUSDT | 1h | 2022-06-15T16:00:00 | +9.99% |
| 1 | 5 | `setup_05_rsi_extreme_continues.json` | rsi_extremo_continua | SOLUSDT | 1h | 2022-01-05T21:00:00 | -4.13% |
| 2 | 1 | `setup_06_confirmed_bullish.json` | confirmed_bullish_obvio | XRPUSDT | 1h | 2022-02-07T10:00:00 | +8.00% |
| 2 | 2 | `setup_12_confirmed_bearish.json` | confirmed_bearish_bluechip | BTCUSDT | 4h | 2021-11-17T08:00:00 | -6.17% |
| 2 | 3 | `setup_04_contrarian_second.json` | contrarian_bullish_falla | BNBUSDT | 4h | 2025-10-13T16:00:00 | -8.38% |
| 2 | 4 | `setup_24_contrarian_bear_fails.json` | contrarian_bearish_falla | BNBUSDT | 1h | 2022-06-15T16:00:00 | +9.98% |
| 2 | 5 | `setup_30_rsi_extreme_continues.json` | rsi_extremo_continua | BNBUSDT | 1h | 2021-03-30T10:00:00 | +4.88% |
| 3 | 1 | `setup_07_confirmed_bullish.json` | confirmed_bullish_obvio | DOGEUSDT | 1h | 2025-07-10T11:00:00 | +7.99% |
| 3 | 2 | `setup_13_confirmed_bearish.json` | confirmed_bearish_bluechip | BTCUSDT | 1h | 2022-06-18T08:00:00 | -6.31% |
| 3 | 3 | `setup_18_contrarian_bull_fails.json` | contrarian_bullish_falla | DOGEUSDT | 4h | 2025-07-21T16:00:00 | -9.88% |
| 3 | 4 | `setup_25_contrarian_bear_fails.json` | contrarian_bearish_falla | DOTUSDT | 1h | 2021-12-15T15:00:00 | +9.98% |
| 3 | 5 | `setup_31_rsi_extreme_continues.json` | rsi_extremo_continua | LTCUSDT | 1h | 2023-06-10T04:00:00 | -4.24% |
| 4 | 1 | `setup_08_confirmed_bullish.json` | confirmed_bullish_obvio | SOLUSDT | 4h | 2021-09-08T12:00:00 | +7.94% |
| 4 | 2 | `setup_14_confirmed_bearish.json` | confirmed_bearish_bluechip | ETHUSDT | 1h | 2021-06-25T20:00:00 | -7.17% |
| 4 | 3 | `setup_19_contrarian_bull_fails.json` | contrarian_bullish_falla | LTCUSDT | 4h | 2020-02-23T16:00:00 | -9.91% |
| 4 | 4 | `setup_26_contrarian_bear_fails.json` | contrarian_bearish_falla | BNBUSDT | 4h | 2020-03-16T16:00:00 | +9.98% |
| 4 | 5 | `setup_32_rsi_extreme_continues.json` | rsi_extremo_continua | SOLUSDT | 1h | 2023-04-11T03:00:00 | +9.61% |
| 5 | 1 | `setup_09_confirmed_bullish.json` | confirmed_bullish_obvio | LINKUSDT | 4h | 2025-04-22T16:00:00 | +7.94% |
| 5 | 2 | `setup_15_confirmed_bearish.json` | confirmed_bearish_bluechip | ETHUSDT | 1h | 2020-09-05T14:00:00 | -7.36% |
| 5 | 3 | `setup_20_contrarian_bull_fails.json` | contrarian_bullish_falla | LINKUSDT | 4h | 2022-03-02T16:00:00 | -9.94% |
| 5 | 4 | `setup_27_contrarian_bear_fails.json` | contrarian_bearish_falla | DOTUSDT | 4h | 2025-05-06T12:00:00 | +9.98% |
| 5 | 5 | `setup_33_rsi_extreme_continues.json` | rsi_extremo_continua | LINKUSDT | 1h | 2020-08-08T16:00:00 | +9.16% |
| 6 | 1 | `setup_10_confirmed_bullish.json` | confirmed_bullish_obvio | LINKUSDT | 4h | 2024-02-03T16:00:00 | +7.93% |
| 6 | 2 | `setup_16_confirmed_bearish.json` | confirmed_bearish_bluechip | ETHUSDT | 1h | 2024-03-18T20:00:00 | -7.67% |
| 6 | 3 | `setup_21_contrarian_bull_fails.json` | contrarian_bullish_falla | LINKUSDT | 1h | 2021-09-12T22:00:00 | -9.97% |
| 6 | 4 | `setup_28_contrarian_bear_fails.json` | contrarian_bearish_falla | DOGEUSDT | 1d | 2024-02-04T00:00:00 | +9.80% |
| 6 | 5 | `setup_34_rsi_extreme_continues.json` | rsi_extremo_continua | DOGEUSDT | 1h | 2022-10-25T17:00:00 | +3.56% |
| 7 | 1 | `setup_11_confirmed_bullish.json` | confirmed_bullish_obvio | SOLUSDT | 1h | 2021-03-27T15:00:00 | +7.90% |
| 7 | 2 | `setup_17_confirmed_bearish.json` | confirmed_bearish_bluechip | BTCUSDT | 1h | 2021-01-10T14:00:00 | -7.76% |
| 7 | 3 | `setup_22_contrarian_bull_fails.json` | contrarian_bullish_falla | ETHUSDT | 4h | 2021-02-20T08:00:00 | -10.00% |
| 7 | 4 | `setup_29_contrarian_bear_fails.json` | contrarian_bearish_falla | DOGEUSDT | 1h | 2022-01-22T17:00:00 | +9.44% |
| 7 | 5 | `setup_35_rsi_extreme_continues.json` | rsi_extremo_continua | DOGEUSDT | 4h | 2023-08-16T16:00:00 | -8.91% |

## Acceptance summary

- 30 new JSON files generated (setup_06..setup_35)
- Profile distribution (total 35): {'confirmed_bullish_obvio': 7, 'confirmed_bearish_bluechip': 7, 'contrarian_bullish_falla': 7, 'contrarian_bearish_falla': 7, 'rsi_extremo_continua': 7}
- New-setup symbol mix: blue_chip=24, meme=6
- New-setup TF mix: {'1h': 18, '4h': 11, '1d': 1}
- Week direction balance: up=18, down=17 (51% / 49%)