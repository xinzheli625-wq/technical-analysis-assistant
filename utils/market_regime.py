"""Market Regime Detection - 市场状态检测

基于技术指标自动判断当前市场状态，用于动态选择相关Skill。
"""

from dataclasses import dataclass
from typing import Any, Dict, List

import pandas as pd


@dataclass
class MarketRegime:
    """市场状态"""
    primary: str           # 主要状态: trending_up/trending_down/ranging/breakout/volatile
    secondary: str         # 次要状态: early/mature/late
    confidence: float      # 置信度 0-1
    indicators: Dict[str, Any]  # 用于判断的关键指标值


class MarketRegimeDetector:
    """市场状态检测器

    基于多维度技术指标综合判断当前市场状态。
    """

    def __init__(self):
        from utils.tech_calculator import MomentumCalculator, TrendCalculator, VolatilityCalculator
        self.trend = TrendCalculator()
        self.momentum = MomentumCalculator()
        self.volatility = VolatilityCalculator()

    def detect(self, df: pd.DataFrame) -> MarketRegime:
        """检测当前市场状态

        Returns:
            MarketRegime 对象
        """
        close = df['close']
        latest = close.iloc[-1]

        # 1. 趋势强度 (ADX)
        adx_df = self.trend.calc_adx(df) if all(c in df.columns for c in ['high', 'low', 'close']) else None
        adx = adx_df['adx'].iloc[-1] if adx_df is not None else 0

        # 2. 均线排列
        sma20 = self.trend.calc_sma(df, 20)
        sma50 = self.trend.calc_sma(df, 50)
        self.trend.calc_ema(df, 20)

        ma_aligned_up = (latest > sma20.iloc[-1] > sma50.iloc[-1]) if not pd.isna(sma50.iloc[-1]) else False
        ma_aligned_down = (latest < sma20.iloc[-1] < sma50.iloc[-1]) if not pd.isna(sma50.iloc[-1]) else False

        # 3. 波动率状态
        atr = self.volatility.calc_atr(df) if all(c in df.columns for c in ['high', 'low']) else None
        atr_pct = atr.iloc[-1] / latest * 100 if atr is not None else 0

        bb = self.volatility.calc_bollinger(df)
        bb_width = bb['bandwidth'].iloc[-1]

        # 4. 动量状态
        rsi = self.momentum.calc_rsi(df)
        rsi_val = rsi.iloc[-1]

        macd_df = self.momentum.calc_macd(df)
        macd_hist = macd_df['histogram'].iloc[-1]

        # 5. 近期价格行为
        returns_5d = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100 if len(close) > 5 else 0
        returns_20d = (close.iloc[-1] - close.iloc[-21]) / close.iloc[-21] * 100 if len(close) > 20 else 0

        # 综合判断
        regime, secondary, confidence = self._classify(
            adx=adx,
            ma_aligned_up=ma_aligned_up,
            ma_aligned_down=ma_aligned_down,
            atr_pct=atr_pct,
            bb_width=bb_width,
            rsi=rsi_val,
            macd_hist=macd_hist,
            returns_5d=returns_5d,
            returns_20d=returns_20d,
            price=latest,
            sma20=sma20.iloc[-1],
            sma50=sma50.iloc[-1]
        )

        return MarketRegime(
            primary=regime,
            secondary=secondary,
            confidence=round(confidence, 2),
            indicators={
                'adx': round(adx, 1),
                'rsi': round(rsi_val, 1),
                'atr_pct': round(atr_pct, 2),
                'bb_width': round(bb_width, 2),
                'macd_hist': round(macd_hist, 3),
                'returns_5d': round(returns_5d, 2),
                'returns_20d': round(returns_20d, 2),
                'ma_aligned_up': ma_aligned_up,
                'ma_aligned_down': ma_aligned_down,
            }
        )

    def _classify(self, adx, ma_aligned_up, ma_aligned_down,
                  atr_pct, bb_width, rsi, macd_hist,
                  returns_5d, returns_20d, price, sma20, sma50) -> tuple:
        """分类市场状态

        Returns:
            (primary_state, secondary_state, confidence)
        """
        # 强趋势判断
        if adx > 30:
            if ma_aligned_up and rsi > 50:
                if returns_20d > 15:
                    return 'trending_up', 'late', 0.85
                elif returns_5d > 5:
                    return 'trending_up', 'mature', 0.80
                else:
                    return 'trending_up', 'early', 0.75
            elif ma_aligned_down and rsi < 50:
                if returns_20d < -15:
                    return 'trending_down', 'late', 0.85
                elif returns_5d < -5:
                    return 'trending_down', 'mature', 0.80
                else:
                    return 'trending_down', 'early', 0.75
            else:
                # ADX高但均线不整齐 → 可能即将 breakout
                return 'volatile', 'transition', 0.60

        # 中等趋势
        elif adx > 20:
            if price > sma20 and macd_hist > 0:
                return 'trending_up', 'early', 0.65
            elif price < sma20 and macd_hist < 0:
                return 'trending_down', 'early', 0.65
            else:
                return 'ranging', 'moderate', 0.60

        # 低ADX → 震荡或整理
        else:
            if bb_width < 5 and atr_pct < 1.5:
                # 低波动 + 窄布林带 → 极度整理，可能即将突破
                return 'ranging', 'tight', 0.70
            elif bb_width > 10 and atr_pct > 3:
                # 高波动但无方向 → 波动市
                return 'volatile', 'expansion', 0.65
            elif abs(returns_5d) > 5 and adx < 20:
                # 短期大幅波动但ADX低 → 假突破/快速反转
                return 'volatile', 'false_breakout', 0.55
            else:
                return 'ranging', 'normal', 0.60

    def get_applicable_categories(self, regime: MarketRegime) -> List[str]:
        """根据市场状态返回适用的Skill类别

        用于动态选择注入LLM的Skill上下文。
        """
        primary = regime.primary
        secondary = regime.secondary

        # 基础类别（所有市场都适用）
        base = ['indicators', 'scoring']

        regime_map = {
            'trending_up': {
                'early': ['trend', 'volume_price', 'behavior'],
                'mature': ['trend', 'volume_price', 'behavior', 'events'],
                'late': ['trend', 'patterns', 'behavior', 'events'],
            },
            'trending_down': {
                'early': ['trend', 'volume_price', 'behavior'],
                'mature': ['trend', 'volume_price', 'behavior', 'events'],
                'late': ['trend', 'patterns', 'behavior', 'events'],
            },
            'ranging': {
                'tight': ['patterns', 'levels', 'volume_price'],
                'normal': ['patterns', 'levels', 'volume_price', 'behavior'],
                'moderate': ['patterns', 'levels', 'trend'],
            },
            'volatile': {
                'transition': ['trend', 'events', 'behavior'],
                'expansion': ['volatility', 'behavior', 'events'],
                'false_breakout': ['patterns', 'behavior', 'levels'],
            },
        }

        specific = regime_map.get(primary, {}).get(secondary, [])
        return list(dict.fromkeys(base + specific))  # 去重保持顺序

    def describe(self, regime: MarketRegime) -> str:
        """生成人类可读的市场状态描述"""
        primary_names = {
            'trending_up': '上升趋势',
            'trending_down': '下降趋势',
            'ranging': '区间震荡',
            'volatile': '高波动',
        }
        secondary_names = {
            'early': '初期',
            'mature': '中期',
            'late': '末期',
            'tight': '窄幅整理',
            'normal': '正常震荡',
            'moderate': '中度震荡',
            'transition': '转换期',
            'expansion': '波动扩张',
            'false_breakout': '假突破',
        }

        return f"{primary_names.get(regime.primary, regime.primary)}-{secondary_names.get(regime.secondary, regime.secondary)} (置信度{regime.confidence*100:.0f}%)"
