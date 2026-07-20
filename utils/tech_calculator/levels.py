"""Levels Dimension - 支撑阻力维度计算

包含：
- Pivot Points
- Fibonacci Retracement
- Support/Resistance via clustering
- Price channels
"""

import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN
from typing import Dict, List, Any
from .registry import IndicatorRegistry, IndicatorMeta


class LevelCalculator:
    """支撑阻力计算器"""

    def __init__(self):
        self.registry = IndicatorRegistry()
        self._register_builtin()

    def _register_builtin(self):
        indicators = [
            IndicatorMeta('pivot_points', '枢轴点', 'levels',
                         '基于前一日高低收计算关键价位',
                         'PP=(H+L+C)/3, R1=2*PP-L, S1=2*PP-H',
                         ['high', 'low', 'close'], ['pp', 'r1', 's1', 'r2', 's2'],
                         {}, 'builtin', ''),
            IndicatorMeta('fibonacci', '斐波那契回撤', 'levels',
                         '基于波段高低点计算回撤位',
                         'levels = high - (high-low) * [0.236, 0.382, 0.5, 0.618, 0.786]',
                         ['high', 'low'], ['fib_236', 'fib_382', 'fib_500', 'fib_618', 'fib_786'],
                         {}, 'builtin', ''),
            IndicatorMeta('clusters', '聚类支撑阻力', 'levels',
                         '基于历史极值点的聚类分析',
                         'DBSCAN clustering on swing highs/lows',
                         ['high', 'low'], ['support_clusters', 'resistance_clusters'],
                         {'eps_pct': 0.02}, 'builtin', ''),
        ]
        for meta in indicators:
            calc_fn = getattr(self, f'calc_{meta.name}', None)
            if calc_fn:
                self.registry.register(meta, calc_fn)

    def calc_pivot_points(self, df: pd.DataFrame, **kwargs) -> Dict[str, float]:
        """计算枢轴点（基于最近一个完整周期）"""
        high = df['high'].iloc[-1]
        low = df['low'].iloc[-1]
        close = df['close'].iloc[-1]

        pp = (high + low + close) / 3
        r1 = 2 * pp - low
        s1 = 2 * pp - high
        r2 = pp + (high - low)
        s2 = pp - (high - low)

        return {
            'pp': round(pp, 2),
            'r1': round(r1, 2),
            's1': round(s1, 2),
            'r2': round(r2, 2),
            's2': round(s2, 2)
        }

    def calc_fibonacci(self, df: pd.DataFrame, lookback: int = 60, **kwargs) -> Dict[str, float]:
        """计算斐波那契回撤位（基于最近一个波段）"""
        recent = df.tail(lookback)
        swing_high = recent['high'].max()
        swing_low = recent['low'].min()
        diff = swing_high - swing_low

        levels = [0.236, 0.382, 0.5, 0.618, 0.786]
        result = {}
        for level in levels:
            key = f'fib_{int(level*1000)}'
            result[key] = round(swing_high - diff * level, 2)

        result['swing_high'] = round(swing_high, 2)
        result['swing_low'] = round(swing_low, 2)
        return result

    def calc_clusters(self, df: pd.DataFrame, eps_pct: float = 0.02, **kwargs) -> Dict[str, List[float]]:
        """使用DBSCAN聚类检测支撑阻力位"""
        from .pattern import PatternDetector

        detector = PatternDetector()
        highs = df['high']
        lows = df['low']

        peaks, troughs = detector.find_swing_points(highs, lows)

        if len(peaks) < 3 or len(troughs) < 3:
            return {'support_clusters': [], 'resistance_clusters': []}

        # 阻力位聚类（peaks）
        peak_prices = highs.iloc[peaks].values.reshape(-1, 1)
        eps = highs.mean() * eps_pct

        if len(peak_prices) >= 2:
            clustering_r = DBSCAN(eps=eps, min_samples=2).fit(peak_prices)
            resistance_clusters = []
            for label in set(clustering_r.labels_):
                if label == -1:
                    continue
                cluster_prices = peak_prices[clustering_r.labels_ == label].flatten()
                resistance_clusters.append(round(np.mean(cluster_prices), 2))
        else:
            resistance_clusters = []

        # 支撑位聚类（troughs）
        trough_prices = lows.iloc[troughs].values.reshape(-1, 1)
        if len(trough_prices) >= 2:
            clustering_s = DBSCAN(eps=eps, min_samples=2).fit(trough_prices)
            support_clusters = []
            for label in set(clustering_s.labels_):
                if label == -1:
                    continue
                cluster_prices = trough_prices[clustering_s.labels_ == label].flatten()
                support_clusters.append(round(np.mean(cluster_prices), 2))
        else:
            support_clusters = []

        return {
            'support_clusters': sorted(support_clusters),
            'resistance_clusters': sorted(resistance_clusters)
        }

    def analyze_levels(self, df: pd.DataFrame) -> Dict[str, Any]:
        """综合分析支撑阻力"""
        pivot = self.calc_pivot_points(df)
        fib = self.calc_fibonacci(df)
        clusters = self.calc_clusters(df)

        current_price = df['close'].iloc[-1]

        # 找出最近的支撑和阻力
        all_supports = clusters['support_clusters'] + [pivot['s1'], pivot['s2']]
        all_resistances = clusters['resistance_clusters'] + [pivot['r1'], pivot['r2']]

        below_supports = [s for s in all_supports if s < current_price]
        above_resistances = [r for r in all_resistances if r > current_price]

        nearest_support = max(below_supports) if below_supports else fib.get('swing_low')
        nearest_resistance = min(above_resistances) if above_resistances else fib.get('swing_high')

        return {
            'pivot_points': pivot,
            'fibonacci': fib,
            'clusters': clusters,
            'current_price': round(current_price, 2),
            'nearest_support': round(nearest_support, 2) if nearest_support else None,
            'nearest_resistance': round(nearest_resistance, 2) if nearest_resistance else None,
            'support_distance_pct': round((current_price - nearest_support) / current_price * 100, 2) if nearest_support else None,
            'resistance_distance_pct': round((nearest_resistance - current_price) / current_price * 100, 2) if nearest_resistance else None
        }
