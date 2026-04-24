# COTD Setup Scanner

Pipeline de Python que analiza datos históricos OHLCV para encontrar setups
educativamente valiosos para Charts of the Day.

## Archivos

- `signal_detectors.py` — los 7 detectores de señales (reglas puras, sin ML)
- `setup_scorer.py` — calcula bias esperado, outcome real, score educativo
- `cotd_scanner.py` — notebook principal que procesa los tokens y rankea
- `smoke_test.py` — test de sanidad con datos sintéticos

## Las 7 señales detectadas

1. **trend_direction** — pendiente lineal sobre 20 velas: bullish_strong / bullish / sideways / bearish / bearish_strong
2. **recent_momentum** — ratio alcistas vs bajistas + tendencia de cuerpos: accelerating_up/down, exhausted_up/down, mixed, indecisive
3. **volume_relative** — volumen reciente vs histórico: climactic, rising, normal, falling, dry
4. **price_vs_ma25** — z-score del precio respecto a MA25: far_above, above, touching, below, far_below
5. **ma_cross_7_25** — cruces en las últimas 10 velas: fresh_bullish_cross, recent_bullish_cross, ma7_above_stable, (y bajistas equivalentes)
6. **rsi_zone** — RSI(14): overbought_extreme, overbought, neutral_high, neutral, neutral_low, oversold, oversold_extreme
7. **support_resistance** — posición respecto a máx/mín local de últimas 50 velas: breaking_resistance, near_resistance, mid_range, near_support, breaking_support

## Uso básico

```bash
# Instalar dependencias
pip install pandas numpy

# Test de sanidad (datos sintéticos)
python smoke_test.py

# Escanear un token concreto
python cotd_scanner.py --token BTCUSDT --timeframe 1h --top 20

# Escanear todos los tokens ALLOWED y sacar top 30
python cotd_scanner.py --timeframe 1h --top 30 --output candidates_1h.csv

# Con más verbosidad
python cotd_scanner.py --token ETHUSDT -v
```

## Output

- `cotd_candidates.csv` — tabla ranked con top setups
- `cotd_candidates.json` — mismo contenido + señales completas con detalles

## Score educativo (0-100)

Un setup vale más si:
- Las señales visibles apuntan claramente a una dirección Y el outcome fue en esa dirección (coherence: confirmed, +30)
- O las señales apuntaban a una dirección Y el outcome fue en la contraria (coherence: contrarian, +25) — enseña humildad
- El movimiento es de magnitud razonable (2-15%)
- Las señales son fuertes (no ambiguas)
- No hay whipsaw extremo

## Siguientes pasos después de correr el notebook

1. Abre `cotd_candidates.csv` y revisa los top 30-50 candidatos
2. Para cada uno, abre el chart real en TradingView / Binance y valida visualmente:
   - ¿Son señales claras a ojo?
   - ¿El setup es interesante para aprender?
   - ¿Se ve coherente?
3. Marca los 5 mejores candidatos para la muestra editorial
4. Escribe las frases de explicación (usando el catálogo de frases traducidas)
5. Prepáralos para la demo del lunes

## Notas de diseño

- **No hay ML.** Todo son reglas auditables documentadas en el código.
- **Los detectores son deterministas.** Mismo input → mismo output.
- **Los pesos de bias son editoriales, no verdad técnica.** Representan la lectura convencional del análisis técnico y pueden ajustarse tras validación.
- **Compliance-ready**: el output es estructurado, no texto libre. Las frases que ve el usuario vienen de un diccionario pre-aprobado.
