"""Volatility Dimension - 波动维度计算"""

from typing import Any, Dict

import numpy as np
import pandas as pd

from .registry import IndicatorMeta, IndicatorRegistry


class VolatilityCalculator:
    """波动维度计算器"""

    def __init__(self):
        self.registry = IndicatorRegistry()
        self._register_builtin()

    def _register_builtin(self):
        indicators = [
            IndicatorMeta('atr', '真实波幅', 'volatility',
                         '衡量价格波动幅度',
                         'TR = max(high-low, |high-close_prev|, |low-close_prev|), ATR = SMA(TR, n)',
                         ['high', 'low', 'close'], ['atr'],
                         {'period': 14}, 'builtin', ''),
            IndicatorMeta('bollinger', '布林带', 'volatility',
                         '基于标准差的波动区间',
                         'Middle=SMA(close,20), Upper=Middle+2*std, Lower=Middle-2*std',
                         ['close'], ['upper', 'middle', 'lower', 'bandwidth', 'percent_b'],
                         {'period': 20, 'std': 2}, 'builtin', ''),
            IndicatorMeta('hist_vol', '历史波动率', 'volatility',
                         '对数收益率的年化标准差',
                         'HV = std(ln(close_t/close_t-1)) * sqrt(252)',
                         ['close'], ['hist_vol'],
                         {'period': 20}, 'builtin', ''),
            IndicatorMeta('keltner', '凯尔特纳通道', 'volatility',
                         '基于ATR的波动通道',
                         'Middle=EMA(typical_price), Upper=Middle+mult*ATR',
                         ['high', 'low', 'close'], ['upper', 'middle', 'lower'],
                         {'period': 20, 'atr_period': 10, 'multiplier': 2.0}, 'builtin', ''),
            IndicatorMeta('donchian', '唐奇安通道', 'volatility',
                         '基于n周期高低点的通道',
                         'Upper=max(high,n), Lower=min(low,n)',
                         ['high', 'low'], ['upper', 'middle', 'lower'],
                         {'period': 20}, 'builtin', ''),
            IndicatorMeta('std_dev', '标准差', 'volatility',
                         '收盘价的滚动标准差',
                         'StdDev = std(close, n)',
                         ['close'], ['std_dev'],
                         {'period': 20}, 'builtin', ''),
            IndicatorMeta('ulcer_index', '溃疡指数', 'volatility',
                         '衡量下行波动风险',
                         'UI = sqrt(mean((drawdown)^2))',
                         ['close'], ['ulcer_index'],
                         {'period': 14}, 'builtin', ''),
            IndicatorMeta('chaikin_volatility', '蔡金波动率', 'volatility',
                         '高低差EMA的变化率',
                         'Chaikin Vol = (EMA(H-L) - EMA(H-L)_prev) / EMA(H-L)_prev',
                         ['high', 'low'], ['chaikin_vol'],
                         {'ema_period': 10, 'roc_period': 10}, 'builtin', ''),
        ]
        for meta in indicators:
            calc_fn = getattr(self, f'calc_{meta.name}', None)
            if calc_fn:
                self.registry.register(meta, calc_fn)

    def calc_atr(self, df: pd.DataFrame, period: int = 14, **kwargs) -> pd.Series:
        """ATR计算"""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        return tr.rolling(window=period).mean()

    def calc_bollinger(self, df: pd.DataFrame, period: int = 20, std: int = 2, **kwargs) -> pd.DataFrame:
        """布林带计算"""
        close = df['close']
        middle = close.rolling(window=period).mean()
        rolling_std = close.rolling(window=period).std()
        upper = middle + rolling_std * std
        lower = middle - rolling_std * std

        bandwidth = (upper - lower) / middle * 100
        percent_b = (close - lower) / (upper - lower)

        return pd.DataFrame({
            'upper': upper,
            'middle': middle,
            'lower': lower,
            'bandwidth': bandwidth,
            'percent_b': percent_b
        })

    def calc_hist_vol(self, df: pd.DataFrame, period: int = 20, **kwargs) -> pd.Series:
        """历史波动率（年化）"""
        log_returns = np.log(df['close'] / df['close'].shift(1))
        return log_returns.rolling(window=period).std() * np.sqrt(252) * 100

    def calc_keltner(self, df: pd.DataFrame, period: int = 20,
                     atr_period: int = 10, multiplier: float = 2.0, **kwargs) -> pd.DataFrame:
        """凯尔特纳通道 (Keltner Channels)"""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        middle = typical_price.ewm(span=period, adjust=False).mean()
        atr = self.calc_atr(df, period=atr_period)
        upper = middle + multiplier * atr
        lower = middle - multiplier * atr

        return pd.DataFrame({
            'upper': upper,
            'middle': middle,
            'lower': lower
        })

    def calc_donchian(self, df: pd.DataFrame, period: int = 20, **kwargs) -> pd.DataFrame:
        """唐奇安通道 (Donchian Channels)"""
        upper = df['high'].rolling(window=period).max()
        lower = df['low'].rolling(window=period).min()
        middle = (upper + lower) / 2

        return pd.DataFrame({
            'upper': upper,
            'middle': middle,
            'lower': lower
        })

    def calc_std_dev(self, df: pd.DataFrame, period: int = 20, **kwargs) -> pd.Series:
        """收盘价标准差"""
        return df['close'].rolling(window=period).std()

    def calc_ulcer_index(self, df: pd.DataFrame, period: int = 14, **kwargs) -> pd.Series:
        """溃疡指数 (Ulcer Index)"""
        close = df['close']
        max_close = close.rolling(window=period).max()
        pct_drawdown = (close - max_close) / max_close * 100
        squared = pct_drawdown ** 2
        return np.sqrt(squared.rolling(window=period).mean())

    def calc_chaikin_volatility(self, df: pd.DataFrame,
                                 ema_period: int = 10,
                                 roc_period: int = 10, **kwargs) -> pd.Series:
        """蔡金波动率 (Chaikin Volatility)"""
        high_low = df['high'] - df['low']
        ema_hl = high_low.ewm(span=ema_period, adjust=False).mean()
        return (ema_hl - ema_hl.shift(roc_period)) / ema_hl.shift(roc_period) * 100

    def analyze_volatility(self, df: pd.DataFrame) -> Dict[str, Any]:
        """综合分析波动状态"""
        bb = self.calc_bollinger(df)
        atr = self.calc_atr(df)
        hist_vol = self.calc_hist_vol(df)

        latest_close = df['close'].iloc[-1]
        bb_pct = bb['percent_b'].iloc[-1]

        bb_position = 'middle'
        if bb_pct > 0.95:
            bb_position = 'upper_band'
        elif bb_pct < 0.05:
            bb_position = 'lower_band'
        elif bb_pct > 0.8:
            bb_position = 'upper_half'
        elif bb_pct < 0.2:
            bb_position = 'lower_half'

        atr_pct = atr.iloc[-1] / latest_close * 100 if not pd.isna(atr.iloc[-1]) else None

        return {
            'bollinger': {
                'upper': round(bb['upper'].iloc[-1], 2),
                'middle': round(bb['middle'].iloc[-1], 2),
                'lower': round(bb['lower'].iloc[-1], 2),
                'position': bb_position,
                'bandwidth': round(bb['bandwidth'].iloc[-1], 2) if not pd.isna(bb['bandwidth'].iloc[-1]) else None
            },
            'atr': {
                'value': round(atr.iloc[-1], 2) if not pd.isna(atr.iloc[-1]) else None,
                'pct_of_price': round(atr_pct, 2) if atr_pct else None
            },
            'hist_volatility': round(hist_vol.iloc[-1], 1) if not pd.isna(hist_vol.iloc[-1]) else None
        }
