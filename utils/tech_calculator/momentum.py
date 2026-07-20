"""Momentum Dimension - 动量维度计算

包含：
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- KDJ (Stochastic Oscillator)
- CCI (Commodity Channel Index)
- Stochastic Oscillator
- Williams %R
- Momentum
"""

from typing import Any, Dict

import numpy as np
import pandas as pd

from .registry import IndicatorMeta, IndicatorRegistry


class MomentumCalculator:
    """动量维度计算器"""

    def __init__(self):
        self.registry = IndicatorRegistry()
        self._register_builtin()

    def _register_builtin(self):
        indicators = [
            IndicatorMeta('rsi', '相对强弱指数', 'momentum',
                         '衡量价格变动速度和幅度',
                         'RSI = 100 - 100 / (1 + RS), RS = avg_gain / avg_loss',
                         ['close'], ['rsi'],
                         {'period': 14}, 'builtin', ''),
            IndicatorMeta('macd', '指数平滑异同平均线', 'momentum',
                         '趋势跟踪动量指标',
                         'MACD = EMA(12) - EMA(26), Signal = EMA(MACD, 9)',
                         ['close'], ['macd', 'signal', 'histogram'],
                         {'fast': 12, 'slow': 26, 'signal': 9}, 'builtin', ''),
            IndicatorMeta('kdj', '随机指标', 'momentum',
                         '比较收盘价与价格区间',
                         'K = SMA(RSV, 3), D = SMA(K, 3), J = 3K - 2D',
                         ['high', 'low', 'close'], ['k', 'd', 'j'],
                         {'n': 9, 'm1': 3, 'm2': 3}, 'builtin', ''),
            IndicatorMeta('cci', '商品通道指数', 'momentum',
                         '衡量价格与平均价格的偏离',
                         'CCI = (TP - SMA(TP, n)) / (0.015 * mean_deviation)',
                         ['high', 'low', 'close'], ['cci'],
                         {'period': 20}, 'builtin', ''),
            IndicatorMeta('stoch', '随机震荡器', 'momentum',
                         'KDJ的简化版',
                         '%K = (close - low_n) / (high_n - low_n) * 100',
                         ['high', 'low', 'close'], ['stoch_k', 'stoch_d'],
                         {'k_period': 14, 'd_period': 3}, 'builtin', ''),
            IndicatorMeta('williams_r', '威廉指标', 'momentum',
                         '衡量超买超卖',
                         '%R = (high_n - close) / (high_n - low_n) * -100',
                         ['high', 'low', 'close'], ['williams_r'],
                         {'period': 14}, 'builtin', ''),
            IndicatorMeta('momentum', '动量指标', 'momentum',
                         '当前价格与n周期前价格的差',
                         'MOM = close_t - close_t-n',
                         ['close'], ['momentum'],
                         {'period': 10}, 'builtin', ''),
            IndicatorMeta('tsi', '真实强弱指数', 'momentum',
                         '双重平滑的动量指标',
                         'TSI = 100 * PC_EMA / |PC|_EMA',
                         ['close'], ['tsi'],
                         {'long_period': 25, 'short_period': 13}, 'builtin', ''),
            IndicatorMeta('awesome_oscillator', '动量震荡器', 'momentum',
                         '5期和34期中位数价格差的动量指标',
                         'AO = SMA(median_price,5) - SMA(median_price,34)',
                         ['high', 'low'], ['ao'],
                         {}, 'builtin', ''),
            IndicatorMeta('ultimate_oscillator', '终极震荡器', 'momentum',
                         '多时间框架加权动量指标',
                         'UO = 100*(4*Avg7 + 2*Avg14 + Avg28)/7',
                         ['high', 'low', 'close'], ['uo'],
                         {'period1': 7, 'period2': 14, 'period3': 28}, 'builtin', ''),
            IndicatorMeta('ppo', '百分比价格震荡器', 'momentum',
                         'MACD的百分比版本',
                         'PPO = (EMA_fast - EMA_slow)/EMA_slow * 100',
                         ['close'], ['ppo', 'signal', 'histogram'],
                         {'fast': 12, 'slow': 26, 'signal': 9}, 'builtin', ''),
            IndicatorMeta('dpo', '去趋势价格震荡器', 'momentum',
                         '去除趋势后的价格震荡',
                         'DPO = Close - SMA(Close shifted)',
                         ['close'], ['dpo'],
                         {'period': 20}, 'builtin', ''),
            IndicatorMeta('stoch_rsi', '随机RSI', 'momentum',
                         'RSI的随机化处理',
                         'StochRSI = (RSI - RSI_low) / (RSI_high - RSI_low)',
                         ['close'], ['stoch_rsi', 'k', 'd'],
                         {'rsi_period': 14, 'stoch_period': 14, 'k_period': 3, 'd_period': 3}, 'builtin', ''),
            IndicatorMeta('elder_ray', '艾尔德射线', 'momentum',
                         '衡量买卖双方力量对比',
                         'Bull Power = High - EMA, Bear Power = Low - EMA',
                         ['high', 'low', 'close'], ['bull_power', 'bear_power', 'ema'],
                         {'period': 13}, 'builtin', ''),
        ]
        for meta in indicators:
            calc_fn = getattr(self, f'calc_{meta.name}', None)
            if calc_fn:
                self.registry.register(meta, calc_fn)

    def calc_rsi(self, df: pd.DataFrame, period: int = 14, **kwargs) -> pd.Series:
        """RSI计算 (Wilder方法)"""
        close = df['close']
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calc_macd(self, df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9, **kwargs) -> pd.DataFrame:
        """MACD计算"""
        close = df['close']
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        return pd.DataFrame({
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        })

    def calc_kdj(self, df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3, **kwargs) -> pd.DataFrame:
        """KDJ计算"""
        low_list = df['low'].rolling(window=n, min_periods=n).min()
        high_list = df['high'].rolling(window=n, min_periods=n).max()
        # 窗口内 high==low（停牌/无波动）时 RSV 无定义，置 NaN 而非除零
        rsv = (df['close'] - low_list) / (high_list - low_list).replace(0, np.nan) * 100

        k = rsv.ewm(com=m1 - 1, adjust=False).mean()
        d = k.ewm(com=m2 - 1, adjust=False).mean()
        j = 3 * k - 2 * d

        return pd.DataFrame({'k': k, 'd': d, 'j': j})

    def calc_cci(self, df: pd.DataFrame, period: int = 20, **kwargs) -> pd.Series:
        """CCI计算"""
        tp = (df['high'] + df['low'] + df['close']) / 3
        sma_tp = tp.rolling(window=period).mean()
        mean_dev = tp.rolling(window=period).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
        cci = (tp - sma_tp) / (0.015 * mean_dev)
        return cci

    def calc_stoch(self, df: pd.DataFrame, k_period: int = 14, d_period: int = 3, **kwargs) -> pd.DataFrame:
        """Stochastic Oscillator"""
        low_min = df['low'].rolling(window=k_period).min()
        high_max = df['high'].rolling(window=k_period).max()
        k = 100 * (df['close'] - low_min) / (high_max - low_min).replace(0, np.nan)
        d = k.rolling(window=d_period).mean()
        return pd.DataFrame({'stoch_k': k, 'stoch_d': d})

    def calc_williams_r(self, df: pd.DataFrame, period: int = 14, **kwargs) -> pd.Series:
        """Williams %R"""
        high_max = df['high'].rolling(window=period).max()
        low_min = df['low'].rolling(window=period).min()
        return -100 * (high_max - df['close']) / (high_max - low_min).replace(0, np.nan)

    def calc_momentum(self, df: pd.DataFrame, period: int = 10, **kwargs) -> pd.Series:
        """Momentum"""
        return df['close'] - df['close'].shift(period)

    def calc_tsi(self, df: pd.DataFrame, long_period: int = 25,
                 short_period: int = 13, **kwargs) -> pd.Series:
        """真实强弱指标 (True Strength Index)"""
        close = df['close']
        pc = close - close.shift(1)

        double_smoothed_pc = pc.ewm(span=long_period, adjust=False).mean().ewm(span=short_period, adjust=False).mean()
        double_smoothed_abs = abs(pc).ewm(span=long_period, adjust=False).mean().ewm(span=short_period, adjust=False).mean()

        return 100 * double_smoothed_pc / (double_smoothed_abs + 1e-10)

    def calc_awesome_oscillator(self, df: pd.DataFrame, **kwargs) -> pd.Series:
        """动量震荡指标 (Awesome Oscillator)"""
        median_price = (df['high'] + df['low']) / 2
        sma5 = median_price.rolling(window=5).mean()
        sma34 = median_price.rolling(window=34).mean()
        return sma5 - sma34

    def calc_ultimate_oscillator(self, df: pd.DataFrame,
                                  period1: int = 7, period2: int = 14,
                                  period3: int = 28, **kwargs) -> pd.Series:
        """终极震荡指标 (Ultimate Oscillator)"""
        close = df['close']
        low = df['low']
        high = df['high']

        bp = close - pd.concat([low, close.shift(1)], axis=1).min(axis=1)
        tr = pd.concat([
            high - low,
            abs(high - close.shift(1)),
            abs(low - close.shift(1))
        ], axis=1).max(axis=1)

        avg1 = bp.rolling(window=period1).sum() / tr.rolling(window=period1).sum()
        avg2 = bp.rolling(window=period2).sum() / tr.rolling(window=period2).sum()
        avg3 = bp.rolling(window=period3).sum() / tr.rolling(window=period3).sum()

        return 100 * (4 * avg1 + 2 * avg2 + avg3) / 7

    def calc_ppo(self, df: pd.DataFrame, fast: int = 12, slow: int = 26,
                 signal: int = 9, **kwargs) -> pd.DataFrame:
        """百分比价格震荡器 (Percentage Price Oscillator)"""
        close = df['close']
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        ppo = (ema_fast - ema_slow) / ema_slow * 100
        ppo_signal = ppo.ewm(span=signal, adjust=False).mean()
        histogram = ppo - ppo_signal

        return pd.DataFrame({
            'ppo': ppo,
            'signal': ppo_signal,
            'histogram': histogram
        })

    def calc_dpo(self, df: pd.DataFrame, period: int = 20, **kwargs) -> pd.Series:
        """去趋势价格震荡器 (Detrended Price Oscillator)"""
        close = df['close']
        # 移位的移动平均线
        shifted_ma = close.rolling(window=period).mean().shift(int(period / 2) + 1)
        return close - shifted_ma

    def calc_stoch_rsi(self, df: pd.DataFrame, rsi_period: int = 14,
                       stoch_period: int = 14, k_period: int = 3,
                       d_period: int = 3, **kwargs) -> pd.DataFrame:
        """随机RSI (Stochastic RSI)"""
        rsi = self.calc_rsi(df, period=rsi_period)
        rsi_min = rsi.rolling(window=stoch_period).min()
        rsi_max = rsi.rolling(window=stoch_period).max()

        stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan)
        k = stoch_rsi.rolling(window=k_period).mean()
        d = k.rolling(window=d_period).mean()

        return pd.DataFrame({
            'stoch_rsi': stoch_rsi,
            'k': k,
            'd': d
        })

    def calc_elder_ray(self, df: pd.DataFrame, period: int = 13, **kwargs) -> pd.DataFrame:
        """艾尔德射线指标 (Elder Ray Index)"""
        ema = df['close'].ewm(span=period, adjust=False).mean()
        bull_power = df['high'] - ema
        bear_power = df['low'] - ema

        return pd.DataFrame({
            'bull_power': bull_power,
            'bear_power': bear_power,
            'ema': ema
        })

    def analyze_momentum(self, df: pd.DataFrame) -> Dict[str, Any]:
        """综合分析动量状态"""
        df['close']

        # RSI
        rsi = self.calc_rsi(df)
        rsi_val = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else None
        rsi_signal = 'neutral'
        if rsi_val is not None:
            if rsi_val > 70:
                rsi_signal = 'overbought'
            elif rsi_val < 30:
                rsi_signal = 'oversold'
            elif rsi_val > 50:
                rsi_signal = 'bullish_momentum'
            else:
                rsi_signal = 'bearish_momentum'

        # MACD
        macd_df = self.calc_macd(df)
        macd_val = macd_df['macd'].iloc[-1] if not pd.isna(macd_df['macd'].iloc[-1]) else None
        signal_val = macd_df['signal'].iloc[-1] if not pd.isna(macd_df['signal'].iloc[-1]) else None
        hist_val = macd_df['histogram'].iloc[-1] if not pd.isna(macd_df['histogram'].iloc[-1]) else None

        macd_signal = 'neutral'
        if macd_val is not None and signal_val is not None:
            if macd_val > signal_val and macd_df['macd'].iloc[-2] <= macd_df['signal'].iloc[-2]:
                macd_signal = 'bullish_crossover'
            elif macd_val < signal_val and macd_df['macd'].iloc[-2] >= macd_df['signal'].iloc[-2]:
                macd_signal = 'bearish_crossover'
            elif hist_val > 0:
                macd_signal = 'bullish'
            else:
                macd_signal = 'bearish'

        # KDJ
        kdj_df = self.calc_kdj(df) if all(c in df.columns for c in ['high', 'low']) else None
        kdj_signal = 'neutral'
        if kdj_df is not None:
            k = kdj_df['k'].iloc[-1]
            d = kdj_df['d'].iloc[-1]
            if k > 80 and d > 80:
                kdj_signal = 'overbought'
            elif k < 20 and d < 20:
                kdj_signal = 'oversold'
            elif k > d and kdj_df['k'].iloc[-2] <= kdj_df['d'].iloc[-2]:
                kdj_signal = 'golden_cross'
            elif k < d and kdj_df['k'].iloc[-2] >= kdj_df['d'].iloc[-2]:
                kdj_signal = 'death_cross'

        return {
            'rsi': {'value': round(rsi_val, 2) if rsi_val else None, 'signal': rsi_signal},
            'macd': {
                'value': round(macd_val, 3) if macd_val else None,
                'signal': macd_signal,
                'histogram': round(hist_val, 3) if hist_val else None
            },
            'kdj': {'signal': kdj_signal} if kdj_df is not None else {'signal': 'no_data'}
        }
