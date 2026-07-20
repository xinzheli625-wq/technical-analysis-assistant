"""Trend Dimension - 趋势维度计算

包含：
- 均线系统 (SMA, EMA, WMA)
- 趋势强度 (ADX, ADXR)
- 趋势持续性 (价格vs均线偏离度)
- 动量趋势 (Price ROC, TRIX)
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from .registry import IndicatorRegistry, IndicatorMeta


class TrendCalculator:
    """趋势维度计算器"""

    def __init__(self):
        self.registry = IndicatorRegistry()
        self._register_builtin()

    def _register_builtin(self):
        """注册内置趋势指标"""
        indicators = [
            IndicatorMeta('sma', '简单移动平均线', 'trend',
                         'n周期收盘价的简单平均',
                         'SMA = sum(close, n) / n',
                         ['close'], ['sma'],
                         {'period': 20}, 'builtin', ''),
            IndicatorMeta('ema', '指数移动平均线', 'trend',
                         '加权平均，近期价格权重更高',
                         'EMA_t = alpha * close_t + (1-alpha) * EMA_t-1, alpha=2/(n+1)',
                         ['close'], ['ema'],
                         {'period': 20}, 'builtin', ''),
            IndicatorMeta('wma', '加权移动平均线', 'trend',
                         '线性加权平均',
                         'WMA = sum(close_i * i) / sum(i)',
                         ['close'], ['wma'],
                         {'period': 20}, 'builtin', ''),
            IndicatorMeta('adx', '平均趋向指数', 'trend',
                         '衡量趋势强度，0-100',
                         'ADX = SMA(DX, n), DX = abs(+DI - -DI) / (+DI + -DI) * 100',
                         ['high', 'low', 'close'], ['adx', 'plus_di', 'minus_di'],
                         {'period': 14}, 'builtin', ''),
            IndicatorMeta('price_roc', '价格变动率', 'trend',
                         '当前价格与n周期前价格的百分比变化',
                         'ROC = (close_t - close_t-n) / close_t-n * 100',
                         ['close'], ['roc'],
                         {'period': 12}, 'builtin', ''),
            IndicatorMeta('trix', '三重指数平滑均线', 'trend',
                         '三重EMA的百分比变化',
                         'TRIX = (EMA3_t - EMA3_t-1) / EMA3_t-1 * 100',
                         ['close'], ['trix'],
                         {'period': 15}, 'builtin', ''),
            IndicatorMeta('parabolic_sar', '抛物线转向', 'trend',
                         '跟踪止损和趋势反转指标',
                         'SAR_t = SAR_t-1 + AF * (EP - SAR_t-1)',
                         ['high', 'low'], ['sar'],
                         {'af': 0.02, 'max_af': 0.2}, 'builtin', ''),
            IndicatorMeta('supertrend', '超级趋势', 'trend',
                         '基于ATR的趋势跟踪指标',
                         'Upper = (H+L)/2 + multiplier*ATR, Lower = (H+L)/2 - multiplier*ATR',
                         ['high', 'low', 'close'], ['supertrend', 'direction', 'upper', 'lower'],
                         {'period': 10, 'multiplier': 3.0}, 'builtin', ''),
            IndicatorMeta('ichimoku', '一目均衡表', 'trend',
                         '多时间框架趋势分析系统',
                         'Tenkan=(9H+9L)/2, Kijun=(26H+26L)/2, Senkou=(Tenkan+Kijun)/2',
                         ['high', 'low', 'close'], ['tenkan_sen', 'kijun_sen', 'senkou_span_a', 'senkou_span_b', 'chikou_span'],
                         {}, 'builtin', ''),
            IndicatorMeta('linear_reg', '线性回归通道', 'trend',
                         '最小二乘拟合的趋势通道',
                         'y = ax + b, 标准误差构建通道',
                         ['close'], ['reg_line', 'upper', 'lower', 'slope'],
                         {'period': 20}, 'builtin', ''),
            IndicatorMeta('ma_envelope', '均线包络线', 'trend',
                         '基于百分比的均线通道',
                         'Upper = MA*(1+pct%), Lower = MA*(1-pct%)',
                         ['close'], ['middle', 'upper', 'lower', 'width_pct'],
                         {'period': 20, 'pct': 2.5}, 'builtin', ''),
            IndicatorMeta('heikin_ashi', '平均K线', 'trend',
                         '平滑价格数据，更易识别趋势',
                         'HA_Close=(O+H+L+C)/4, HA_Open=(HA_Open_prev+HA_Close_prev)/2',
                         ['open', 'high', 'low', 'close'], ['ha_open', 'ha_high', 'ha_low', 'ha_close'],
                         {}, 'builtin', ''),
        ]

        for meta in indicators:
            calc_fn = getattr(self, f'calc_{meta.name}', None)
            if calc_fn:
                self.registry.register(meta, calc_fn)

    # ===== 计算实现 =====

    def calc_sma(self, df: pd.DataFrame, period: int = 20, **kwargs) -> pd.Series:
        """简单移动平均线"""
        return df['close'].rolling(window=period).mean()

    def calc_ema(self, df: pd.DataFrame, period: int = 20, **kwargs) -> pd.Series:
        """指数移动平均线"""
        return df['close'].ewm(span=period, adjust=False).mean()

    def calc_wma(self, df: pd.DataFrame, period: int = 20, **kwargs) -> pd.Series:
        """加权移动平均线"""
        weights = np.arange(1, period + 1)
        return df['close'].rolling(window=period).apply(
            lambda x: np.dot(x, weights) / weights.sum(), raw=True
        )

    def calc_adx(self, df: pd.DataFrame, period: int = 14, **kwargs) -> pd.DataFrame:
        """平均趋向指数 (ADX, +DI, -DI)"""
        high = df['high']
        low = df['low']
        close = df['close']

        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # +DM, -DM
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        plus_dm[plus_dm <= minus_dm] = 0
        minus_dm[minus_dm <= plus_dm] = 0

        # Smooth
        atr = tr.ewm(alpha=1/period, adjust=False).mean()
        plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr
        minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.ewm(alpha=1/period, adjust=False).mean()

        return pd.DataFrame({
            'adx': adx,
            'plus_di': plus_di,
            'minus_di': minus_di
        })

    def calc_price_roc(self, df: pd.DataFrame, period: int = 12, **kwargs) -> pd.Series:
        """价格变动率"""
        return (df['close'] - df['close'].shift(period)) / df['close'].shift(period) * 100

    def calc_trix(self, df: pd.DataFrame, period: int = 15, **kwargs) -> pd.Series:
        """三重指数平滑均线"""
        ema1 = df['close'].ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        ema3 = ema2.ewm(span=period, adjust=False).mean()
        return (ema3 - ema3.shift(1)) / ema3.shift(1) * 100

    def calc_parabolic_sar(self, df: pd.DataFrame, af: float = 0.02,
                           max_af: float = 0.2, **kwargs) -> pd.Series:
        """抛物线转向指标 (Parabolic SAR)"""
        high = df['high']
        low = df['low']
        close = df['close']

        sar = pd.Series(index=df.index, dtype=float)
        trend = pd.Series(index=df.index, dtype=int)  # 1=up, -1=down

        # 初始化
        sar.iloc[0] = low.iloc[0]
        trend.iloc[0] = 1
        ep = high.iloc[0]  # 极值点
        current_af = af

        for i in range(1, len(df)):
            if trend.iloc[i-1] == 1:  # 上升趋势
                sar.iloc[i] = sar.iloc[i-1] + current_af * (ep - sar.iloc[i-1])
                # 限制SAR不超过前两个周期的最低值
                if i >= 2:
                    sar.iloc[i] = min(sar.iloc[i], low.iloc[i-1], low.iloc[i-2])

                if low.iloc[i] < sar.iloc[i]:  # 趋势反转
                    trend.iloc[i] = -1
                    sar.iloc[i] = ep
                    ep = low.iloc[i]
                    current_af = af
                else:
                    trend.iloc[i] = 1
                    if high.iloc[i] > ep:
                        ep = high.iloc[i]
                        current_af = min(current_af + af, max_af)
            else:  # 下降趋势
                sar.iloc[i] = sar.iloc[i-1] + current_af * (ep - sar.iloc[i-1])
                if i >= 2:
                    sar.iloc[i] = max(sar.iloc[i], high.iloc[i-1], high.iloc[i-2])

                if high.iloc[i] > sar.iloc[i]:  # 趋势反转
                    trend.iloc[i] = 1
                    sar.iloc[i] = ep
                    ep = high.iloc[i]
                    current_af = af
                else:
                    trend.iloc[i] = -1
                    if low.iloc[i] < ep:
                        ep = low.iloc[i]
                        current_af = min(current_af + af, max_af)

        return sar

    def calc_supertrend(self, df: pd.DataFrame, period: int = 10,
                        multiplier: float = 3.0, **kwargs) -> pd.DataFrame:
        """超级趋势指标 (SuperTrend)"""
        high = df['high']
        low = df['low']
        close = df['close']

        # 本地计算ATR（避免跨类依赖）
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        upper_band = (high + low) / 2 + multiplier * atr
        lower_band = (high + low) / 2 - multiplier * atr

        supertrend = pd.Series(index=df.index, dtype=float)
        direction = pd.Series(index=df.index, dtype=int)  # 1=多头, -1=空头

        for i in range(len(df)):
            if i == 0:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = 1
                continue

            if close.iloc[i] > supertrend.iloc[i-1]:
                direction.iloc[i] = 1
            else:
                direction.iloc[i] = -1

            if direction.iloc[i] == 1:
                supertrend.iloc[i] = max(lower_band.iloc[i], supertrend.iloc[i-1])
            else:
                supertrend.iloc[i] = min(upper_band.iloc[i], supertrend.iloc[i-1])

        return pd.DataFrame({
            'supertrend': supertrend,
            'direction': direction,
            'upper_band': upper_band,
            'lower_band': lower_band
        })

    def calc_ichimoku(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """一目均衡表 (Ichimoku Cloud)"""
        high = df['high']
        low = df['low']
        close = df['close']

        # 转换线 (Tenkan-sen): (9周期最高+最低)/2
        tenkan_sen = (high.rolling(window=9).max() + low.rolling(window=9).min()) / 2

        # 基准线 (Kijun-sen): (26周期最高+最低)/2
        kijun_sen = (high.rolling(window=26).max() + low.rolling(window=26).min()) / 2

        # 先行带1 (Senkou Span A): (转换线+基准线)/2, 前移26周期
        senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(26)

        # 先行带2 (Senkou Span B): (52周期最高+最低)/2, 前移26周期
        senkou_b = ((high.rolling(window=52).max() + low.rolling(window=52).min()) / 2).shift(26)

        # 延迟线 (Chikou Span): 收盘价后移26周期
        chikou = close.shift(-26)

        return pd.DataFrame({
            'tenkan_sen': tenkan_sen,
            'kijun_sen': kijun_sen,
            'senkou_span_a': senkou_a,
            'senkou_span_b': senkou_b,
            'chikou_span': chikou
        })

    def calc_linear_reg(self, df: pd.DataFrame, period: int = 20, **kwargs) -> pd.DataFrame:
        """线性回归通道"""
        close = df['close']

        x = np.arange(period)
        slope = close.rolling(window=period).apply(
            lambda y: np.polyfit(x[-len(y):], y, 1)[0], raw=True
        )
        intercept = close.rolling(window=period).apply(
            lambda y: np.polyfit(x[-len(y):], y, 1)[1], raw=True
        )

        # 回归线
        reg_line = intercept + slope * (period - 1)

        # 计算标准误差
        def std_error(y):
            if len(y) < 2:
                return 0
            p = np.polyfit(x[-len(y):], y, 1)
            fitted = np.polyval(p, x[-len(y):])
            return np.std(y - fitted)

        std_err = close.rolling(window=period).apply(std_error, raw=True)

        upper = reg_line + 2 * std_err
        lower = reg_line - 2 * std_err

        return pd.DataFrame({
            'reg_line': reg_line,
            'upper': upper,
            'lower': lower,
            'slope': slope
        })

    def calc_ma_envelope(self, df: pd.DataFrame, period: int = 20,
                         pct: float = 2.5, **kwargs) -> pd.DataFrame:
        """均线包络线"""
        ma = df['close'].rolling(window=period).mean()
        upper = ma * (1 + pct / 100)
        lower = ma * (1 - pct / 100)

        return pd.DataFrame({
            'middle': ma,
            'upper': upper,
            'lower': lower,
            'width_pct': (upper - lower) / ma * 100
        })

    def calc_heikin_ashi(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """平均K线 (Heikin-Ashi)"""
        open_price = df['open']
        high = df['high']
        low = df['low']
        close = df['close']

        ha_close = (open_price + high + low + close) / 4
        ha_open = pd.Series(index=df.index, dtype=float)
        ha_open.iloc[0] = (open_price.iloc[0] + close.iloc[0]) / 2

        for i in range(1, len(df)):
            ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2

        ha_high = pd.concat([high, ha_open, ha_close], axis=1).max(axis=1)
        ha_low = pd.concat([low, ha_open, ha_close], axis=1).min(axis=1)

        return pd.DataFrame({
            'ha_open': ha_open,
            'ha_high': ha_high,
            'ha_low': ha_low,
            'ha_close': ha_close
        })

    # ===== 综合分析 =====

    def analyze_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """综合分析趋势状态"""
        close = df['close']

        # 计算多条均线
        ma20 = self.calc_sma(df, 20)
        ma50 = self.calc_sma(df, 50)
        ma200 = self.calc_sma(df, 200)

        latest = {
            'price': close.iloc[-1],
            'ma20': ma20.iloc[-1] if not pd.isna(ma20.iloc[-1]) else None,
            'ma50': ma50.iloc[-1] if not pd.isna(ma50.iloc[-1]) else None,
            'ma200': ma200.iloc[-1] if not pd.isna(ma200.iloc[-1]) else None,
        }

        # 判断MA排列
        ma_aligned = False
        if all(v is not None for v in [latest['price'], latest['ma20'], latest['ma50'], latest['ma200']]):
            ma_aligned = (latest['price'] > latest['ma20'] > latest['ma50'] > latest['ma200'])

        # ADX趋势强度
        adx_df = self.calc_adx(df) if all(c in df.columns for c in ['high', 'low', 'close']) else None
        adx_value = adx_df['adx'].iloc[-1] if adx_df is not None and not pd.isna(adx_df['adx'].iloc[-1]) else None

        trend_strength = 'unknown'
        if adx_value is not None:
            if adx_value > 25:
                trend_strength = 'strong'
            elif adx_value > 20:
                trend_strength = 'moderate'
            else:
                trend_strength = 'weak'

        # 200MA斜率
        ma200_slope = 'flat'
        if len(ma200.dropna()) >= 20:
            recent = ma200.dropna().iloc[-20:]
            if recent.iloc[-1] > recent.iloc[0] * 1.02:
                ma200_slope = 'rising'
            elif recent.iloc[-1] < recent.iloc[0] * 0.98:
                ma200_slope = 'falling'

        return {
            'latest_values': latest,
            'ma_aligned': ma_aligned,
            'trend_strength': trend_strength,
            'adx': adx_value,
            'ma200_slope': ma200_slope,
            'price_vs_ma20_pct': round((latest['price'] / latest['ma20'] - 1) * 100, 2) if latest['ma20'] else None
        }
