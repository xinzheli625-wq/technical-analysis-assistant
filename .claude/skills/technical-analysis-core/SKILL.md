---
name: technical-analysis-core
description: >
  Perform comprehensive multi-school technical analysis on stocks using any input format
  (screenshot, Excel/CSV data, or live API). Analyzes trends, chart patterns (Western + Japanese
  candlestick), technical indicators (RSI, MACD, KDJ, Bollinger, OBV), volume-price relationships,
  capital flow behavior, and infers potential fundamental events from technical signals.
  Use whenever the user asks to analyze a stock chart, technical setup, price action,
  candlestick pattern, volume analysis, or wants a technical opinion on a ticker.
  Also triggers when user uploads a stock chart image, shares price data, or asks
  "should I buy this stock" from a technical perspective.
---

# Technical Analysis Core

Perform multi-dimensional technical analysis combining Western classical patterns,
Japanese candlestick analysis, volume-price analysis (VSA), and capital flow interpretation.

> **Disclaimer:** This analysis is for educational purposes only. It does not constitute
> investment advice. Never execute trades based solely on this analysis.

---

## Step 1: Receive and Normalize Input

Accept any input format and convert to standard analysis structure.

| Input Type | How to Handle |
|-----------|--------------|
| Screenshot/image | Use vision to identify visible patterns, key levels, timeframe. Note precision limitations. |
| Excel/CSV | Parse OHLCV columns (auto-detect Chinese/English headers). Calculate derived fields. |
| API/ticker symbol | Fetch data via yfinance or funda-data skill. Use 200+ days of daily data. |

**Minimum data:** 30 days for basic analysis, 200+ days for full trend/stage analysis.

---

## Step 2: Trend Analysis

Read `references/trend-analysis.md` for detailed methodology.

Determine:
1. **Wyckoff Stage** (1-4): Only Stage 2 is buyable
2. **MA Alignment**: Bullish staircase (Price > 50MA > 150MA > 200MA)
3. **200MA Slope**: Rising for ≥1 month (ideally 4-5 months)
4. **Base Count**: Within Stage 2, how many consolidation-breakout cycles

**Gate:** If Stage 4, reduce to "avoid." If Stage 1, note "watchlist only."

---

## Step 3: Pattern Recognition

Read `references/chart-patterns.md` for complete pattern catalog.

Check for:
- **Reversal patterns:** H&S, Double Top/Bottom, Triple patterns, Rounding
- **Continuation patterns:** Cup with Handle, Flag, Pennant, Triangles
- **Japanese candlestick:** Doji, Hammer, Engulfing, Morning/Evening Star, Marubozu

**Scoring:** Each pattern gets confidence 0-100 based on:
- Volume confirmation (required for > 70 confidence)
- Pattern completeness (all required touches/swings)
- Preceding trend alignment

---

## Step 4: Indicator Analysis

Read `references/indicators.md` for detailed indicator rules.

Analyze:
| Indicator | Signal | Strength |
|-----------|--------|----------|
| RSI(14) | >70 overbought, <30 oversold, divergence warning | Moderate |
| MACD | Crossover direction, histogram, zero-line position | Strong |
| KDJ | K/D cross, overbought/oversold levels | Short-term |
| Bollinger | Squeeze (expansion imminent), band walk | Moderate |
| OBV | Divergence from price = early warning | Strong when clear |

---

## Step 5: Volume-Price Analysis (VSA)

Read `references/volume-price-analysis.md` for VSA rules.

Key checks:
1. Breakout on volume > 2x average? (Required for high confidence)
2. Pullback on declining volume? (Healthy)
3. Distribution signals (up on low vol, down on high vol)?
4. Volume ratio to 20-day average

---

## Step 6: Capital Flow & Sentiment

Read `references/market-behavior.md` for interpretation framework.

Combine all prior signals to infer:
- What institutions are likely doing (accumulating/distributing)
- Overall market sentiment
- Likely follow-through probability

---

## Step 7: Fundamental Event Inference

Read `references/event-inference.md` for inference rules.

Based on combined technical signature, guess what type of event may be occurring:
- Sudden gap + volume = earnings/M&A/major news
- Gradual build = positioning ahead of catalyst
- Capitulation = potential bottom

**Note:** This is inference, not fact. State confidence level clearly.

---

## Step 8: Multi-Dimensional Scoring

Read `references/scoring-framework.md` for scoring details.

| Dimension | Weight | Score |
|-----------|--------|-------|
| Trend | 20% | -5 to +5 |
| Pattern | 20% | -5 to +5 |
| Indicator | 15% | -5 to +5 |
| Volume-Price | 20% | -5 to +5 |
| Support/Resistance | 15% | -5 to +5 |
| Behavior | 10% | -5 to +5 |

**Composite:** Weighted sum. Verdict: Strong Bullish (+4/+5), Bullish (+2/+3),
Neutral (-1/+1), Bearish (-2/-3), Strong Bearish (-4/-5).

---

## Step 9: Output Report

Structure the output as:

```
## Technical Analysis Report: [SYMBOL] ([Date])

### 1. Trend Assessment
- Stage: [X - Name]
- MA Alignment: [description]
- Moving Averages: [50MA/150MA/200MA values]

### 2. Pattern Recognition
[Table of patterns with type, confidence, notes]
- Support: [levels]
- Resistance: [levels]

### 3. Technical Indicators
[RSI, MACD, KDJ, Bollinger summary]

### 4. Volume-Price Analysis
[Volume ratio, interpretation]

### 5. Capital Flow Interpretation
[What smart money is likely doing]

### 6. Inferred Events
[What events may be driving this]

### 7. Composite Score: [X.X] / 5 ([Verdict])
[Dimension score table]

### 8. Key Levels & Risk
| Level | Price | Significance |

### 9. Disclaimer
```

Include confidence level and key caveats. If screenshot input, note precision limitations.
