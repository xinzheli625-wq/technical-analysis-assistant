"""Volume Dimension - 量能维度计算

包含：
- OBV (On-Balance Volume)
- Volume MA / Ratio
- VWAP (Volume Weighted Average Price)
- Money Flow Index
- Accumulation/Distribution Line
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from .registry import IndicatorRegistry, IndicatorMeta


class VolumeCalculator:
    """量能维度计算器"""

    def __init__(self):
        self.registry = IndicatorRegistry()
        self._register_builtin()

    def _register_builtin(self):
        indicators = [
            IndicatorMeta('obv', '能量潮', 'volume',
                         '累积成交量指标',
                         'OBV_t = OBV_t-1 + volume (if close>close_prev) - volume (if close<close_prev)',
                         ['close', 'volume'], ['obv'],
                         {}, 'builtin', ''),
            IndicatorMeta('volume_ma', '成交量均线', 'volume',
                         '成交量的简单移动平均',
                         'VMA = SMA(volume, n)',
                         ['volume'], ['volume_ma'],
                         {'period': 20}, 'builtin', ''),
            IndicatorMeta('volume_ratio', '量比', 'volume',
                         '当前成交量与历史平均的比值',
                         'Ratio = volume_t / SMA(volume, n)',
                         ['volume'], ['volume_ratio'],
                         {'period': 20}, 'builtin', ''),
            IndicatorMeta('vwap', '成交量加权均价', 'volume',
                         '按成交量加权的平均价格',
                         'VWAP = sum(typical_price * volume) / sum(volume)',
                         ['high', 'low', 'close', 'volume'], ['vwap'],
                         {}, 'builtin', ''),
            IndicatorMeta('mfi', '资金流量指标', 'volume',
                         '量价结合的超买超卖指标',
                         'MFI = 100 - 100/(1 + money_flow_ratio)',
                         ['high', 'low', 'close', 'volume'], ['mfi'],
                         {'period': 14}, 'builtin', ''),
            IndicatorMeta('ad_line', '累积派发线', 'volume',
                         '累积资金流入流出',
                         'AD = AD_prev + ((close-low) - (high-close)) / (high-low) * volume',
                         ['high', 'low', 'close', 'volume'], ['ad_line'],
                         {}, 'builtin', ''),
            IndicatorMeta('chaikin_oscillator', '蔡金震荡器', 'volume',
                         'AD线的快EMA减慢EMA',
                         'CO = EMA(AD,3) - EMA(AD,10)',
                         ['high', 'low', 'close', 'volume'], ['chaikin_osc'],
                         {'fast': 3, 'slow': 10}, 'builtin', ''),
            IndicatorMeta('ease_of_movement', '简易波动指标', 'volume',
                         '衡量价格移动难易度',
                         'EOM = ((H+L)/2 - (H+L)_prev/2) / (Volume/(H-L))',
                         ['high', 'low', 'volume'], ['eom'],
                         {'period': 14}, 'builtin', ''),
            IndicatorMeta('force_index', '力量指数', 'volume',
                         '价格变化乘以成交量',
                         'Force = (Close - Close_prev) * Volume',
                         ['close', 'volume'], ['force_index'],
                         {'period': 13}, 'builtin', ''),
            IndicatorMeta('nvi', '负成交量指标', 'volume',
                         '成交量减少日的价格累积',
                         'NVI = NVI_prev + ROC(if Volume < Volume_prev)',
                         ['close', 'volume'], ['nvi'],
                         {}, 'builtin', ''),
            IndicatorMeta('pvi', '正成交量指标', 'volume',
                         '成交量增加日的价格累积',
                         'PVI = PVI_prev + ROC(if Volume > Volume_prev)',
                         ['close', 'volume'], ['pvi'],
                         {}, 'builtin', ''),
        ]
        for meta in indicators:
            calc_fn = getattr(self, f'calc_{meta.name}', None)
            if calc_fn:
                self.registry.register(meta, calc_fn)

    def calc_obv(self, df: pd.DataFrame, **kwargs) -> pd.Series:
        """OBV计算"""
        close = df['close']
        volume = df['volume']
        obv = pd.Series(index=close.index, dtype=float)
        obv.iloc[0] = volume.iloc[0]

        for i in range(1, len(close)):
            if close.iloc[i] > close.iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
            elif close.iloc[i] < close.iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]
        return obv

    def calc_volume_ma(self, df: pd.DataFrame, period: int = 20, **kwargs) -> pd.Series:
        """成交量MA"""
        return df['volume'].rolling(window=period).mean()

    def calc_volume_ratio(self, df: pd.DataFrame, period: int = 20, **kwargs) -> pd.Series:
        """量比"""
        return df['volume'] / df['volume'].rolling(window=period).mean()

    def calc_vwap(self, df: pd.DataFrame, **kwargs) -> pd.Series:
        """VWAP"""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        cumulative_tp_vol = (typical_price * df['volume']).cumsum()
        cumulative_vol = df['volume'].cumsum()
        return cumulative_tp_vol / cumulative_vol

    def calc_mfi(self, df: pd.DataFrame, period: int = 14, **kwargs) -> pd.Series:
        """MFI计算"""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        raw_money_flow = typical_price * df['volume']

        money_flow_sign = np.where(typical_price > typical_price.shift(1), 1, -1)
        signed_money_flow = raw_money_flow * money_flow_sign

        positive_flow = pd.Series(np.where(signed_money_flow > 0, signed_money_flow, 0), index=df.index)
        negative_flow = pd.Series(np.where(signed_money_flow < 0, -signed_money_flow, 0), index=df.index)

        positive_sum = positive_flow.rolling(window=period).sum()
        negative_sum = negative_flow.rolling(window=period).sum()

        money_flow_ratio = positive_sum / negative_sum
        mfi = 100 - (100 / (1 + money_flow_ratio))
        return mfi

    def calc_ad_line(self, df: pd.DataFrame, **kwargs) -> pd.Series:
        """Accumulation/Distribution Line"""
        high = df['high']
        low = df['low']
        close = df['close']
        volume = df['volume']

        money_flow_multiplier = ((close - low) - (high - close)) / (high - low)
        money_flow_volume = money_flow_multiplier * volume

        return money_flow_volume.cumsum()

    def calc_chaikin_oscillator(self, df: pd.DataFrame, fast: int = 3,
                                 slow: int = 10, **kwargs) -> pd.Series:
        """蔡金震荡器 (Chaikin Oscillator)"""
        ad_line = self.calc_ad_line(df)
        return ad_line.ewm(span=fast, adjust=False).mean() - ad_line.ewm(span=slow, adjust=False).mean()

    def calc_ease_of_movement(self, df: pd.DataFrame, period: int = 14, **kwargs) -> pd.Series:
        """简易波动指标 (Ease of Movement)"""
        high = df['high']
        low = df['low']
        volume = df['volume']

        distance_moved = ((high + low) / 2) - ((high.shift(1) + low.shift(1)) / 2)
        box_ratio = volume / 100000000 / (high - low)
        eom = distance_moved / box_ratio

        return eom.rolling(window=period).mean()

    def calc_force_index(self, df: pd.DataFrame, period: int = 13, **kwargs) -> pd.Series:
        """力量指数 (Force Index)"""
        close = df['close']
        volume = df['volume']
        force = (close - close.shift(1)) * volume
        return force.ewm(span=period, adjust=False).mean()

    def calc_nvi(self, df: pd.DataFrame, **kwargs) -> pd.Series:
        """负成交量指标 (Negative Volume Index)"""
        close = df['close']
        volume = df['volume']

        nvi = pd.Series(index=df.index, dtype=float)
        nvi.iloc[0] = 1000

        for i in range(1, len(df)):
            if volume.iloc[i] < volume.iloc[i-1]:
                nvi.iloc[i] = nvi.iloc[i-1] + (close.iloc[i] - close.iloc[i-1]) / close.iloc[i-1] * nvi.iloc[i-1]
            else:
                nvi.iloc[i] = nvi.iloc[i-1]

        return nvi

    def calc_pvi(self, df: pd.DataFrame, **kwargs) -> pd.Series:
        """正成交量指标 (Positive Volume Index)"""
        close = df['close']
        volume = df['volume']

        pvi = pd.Series(index=df.index, dtype=float)
        pvi.iloc[0] = 1000

        for i in range(1, len(df)):
            if volume.iloc[i] > volume.iloc[i-1]:
                pvi.iloc[i] = pvi.iloc[i-1] + (close.iloc[i] - close.iloc[i-1]) / close.iloc[i-1] * pvi.iloc[i-1]
            else:
                pvi.iloc[i] = pvi.iloc[i-1]

        return pvi

    def analyze_volume(self, df: pd.DataFrame) -> Dict[str, Any]:
        """综合分析量能状态"""
        volume = df['volume']
        close = df['close']

        # 量比
        vol_ratio = self.calc_volume_ratio(df)
        vr = vol_ratio.iloc[-1] if not pd.isna(vol_ratio.iloc[-1]) else None

        volume_signal = 'normal'
        if vr is not None:
            if vr > 2.0:
                volume_signal = 'strong_surge'
            elif vr > 1.5:
                volume_signal = 'above_average'
            elif vr < 0.5:
                volume_signal = 'low_interest'
            elif vr < 0.7:
                volume_signal = 'below_average'

        # 价格变动 vs 量比
        price_change = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] if len(close) > 1 else 0

        vpa_signal = 'normal'
        if abs(price_change) > 0.03 and vr > 1.5:
            vpa_signal = 'strong_move_confirmed'
        elif abs(price_change) > 0.03 and vr < 0.8:
            vpa_signal = 'weak_move_suspect'
        elif abs(price_change) < 0.01 and vr > 1.5:
            vpa_signal = 'battle'

        return {
            'volume_ratio': round(vr, 2) if vr else None,
            'volume_signal': volume_signal,
            'vpa_signal': vpa_signal,
            'avg_volume': round(volume.rolling(20).mean().iloc[-1], 0) if len(volume) >= 20 else None,
            'latest_volume': int(volume.iloc[-1]) if not pd.isna(volume.iloc[-1]) else None
        }
