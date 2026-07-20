# Multi-Dimensional Scoring Framework

## Dimensions

Each dimension scored -5 to +5.

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Trend | 20% | MA alignment, stage, slope |
| Pattern | 20% | Best pattern confidence and type |
| Indicator | 15% | RSI, MACD, KDJ confluence |
| Volume-Price | 20% | VSA signal strength |
| Support/Resistance | 15% | Position relative to key levels |
| Behavior | 10% | Capital flow inference |

## Score Interpretation

| Composite | Rating | Action |
|-----------|--------|--------|
| +4 to +5 | Strong bullish | Full position candidate |
| +2 to +3 | Bullish | Reduce size, set tight stop |
| -1 to +1 | Neutral | No position, watch |
| -2 to -3 | Bearish | Avoid or short |
| -4 to -5 | Strong bearish | Strong avoid/short |

## Minimum Thresholds

For a "buy" consideration:
- Composite >= +2
- Trend score >= +2 (must be in favorable trend)
- Volume-Price score >= 0 (no distribution)
- Pattern confidence >= 60% (if pattern is primary signal)

## Confidence Adjustment

Reduce overall confidence when:
- Data quality is poor (< 200 days)
- Screenshot input (visual only)
- Earnings within 5 days
- Market in correction (> 10% decline in index)
