"""Feature Extractor - 技术指标统一提取器

将所有技术指标计算结果格式化为结构化数据，供LLM分析使用。
核心设计：
1. 精确计算所有指标（不依赖LLM心算）
2. 提取最新值 + 近期变化趋势
3. 输出标准化JSON，直接注入LLM Prompt
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from utils.tech_calculator import (
    LevelCalculator,
    MomentumCalculator,
    PatternDetector,
    TrendCalculator,
    VolatilityCalculator,
    VolumeCalculator,
)


@dataclass
class IndicatorSnapshot:
    """单个指标的快照"""
    name: str
    value: Any
    signal: str = ''
    prev_value: Any = None
    change_pct: Optional[float] = None


class FeatureExtractor:
    """技术指标特征提取器

    从OHLCV数据提取所有技术指标的最新值，
    格式化为LLM友好的结构化输出。
    """

    def __init__(self):
        self.trend = TrendCalculator()
        self.momentum = MomentumCalculator()
        self.volatility = VolatilityCalculator()
        self.volume = VolumeCalculator()
        self.pattern = PatternDetector()
        self.levels = LevelCalculator()

    def extract_all(self, df: pd.DataFrame) -> Dict[str, Any]:
        """提取所有维度的技术指标

        Returns:
            {
                'trend': {...},
                'momentum': {...},
                'volatility': {...},
                'volume': {...},
                'pattern': {...},
                'levels': {...},
                'divergence': {...},       # NEW: 背离检测
                'trend_stage': {...},       # NEW: 趋势阶段评估
                'volatility_state': {...},  # NEW: 波动率状态变化
                'momentum_accel': {...},    # NEW: 动量加速度
                'multi_timeframe': {...},   # NEW: 多时间框架一致性
                'composite': {...}
            }
        """
        if len(df) < 60:
            raise ValueError(f"Need at least 60 data points, got {len(df)}")

        return {
            'raw': self._extract_raw(df),
            'trend': self._extract_trend(df),
            'momentum': self._extract_momentum(df),
            'volatility': self._extract_volatility(df),
            'volume': self._extract_volume(df),
            'pattern': self._extract_patterns(df),
            'levels': self._extract_levels(df),
            'divergence': self._extract_divergence(df),
            'trend_stage': self._extract_trend_stage(df),
            'volatility_state': self._extract_volatility_state(df),
            'momentum_accel': self._extract_momentum_accel(df),
            'multi_timeframe': self._extract_multi_timeframe(df),
            'composite': self._extract_composite(df),
        }

    def _extract_raw(self, df: pd.DataFrame) -> Dict[str, Any]:
        """最新一根K线的原始 OHLCV（供 Skill 触发条件直接引用 close/open/high/low/volume）"""
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        close = float(latest['close'])
        prev_close = float(prev['close'])
        return {
            'open': round(float(latest['open']), 4),
            'high': round(float(latest['high']), 4),
            'low': round(float(latest['low']), 4),
            'close': round(close, 4),
            'volume': float(latest['volume']),
            'prev_close': round(prev_close, 4),
            'change_pct': round((close / prev_close - 1) * 100, 2) if prev_close else None,
        }

    def _extract_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """提取趋势维度指标"""
        close = df['close']
        latest = close.iloc[-1]

        # 均线系统
        sma20 = self.trend.calc_sma(df, 20)
        sma50 = self.trend.calc_sma(df, 50)
        sma200 = self.trend.calc_sma(df, 200) if len(df) >= 200 else None
        ema12 = self.trend.calc_ema(df, 12)
        ema26 = self.trend.calc_ema(df, 26)

        # 趋势强度
        adx_df = self.trend.calc_adx(df) if all(c in df.columns for c in ['high', 'low']) else None

        # 其他趋势指标
        roc = self.trend.calc_price_roc(df, 12)
        trix = self.trend.calc_trix(df, 15)

        # SuperTrend
        st = self.trend.calc_supertrend(df) if all(c in df.columns for c in ['high', 'low']) else None

        # Ichimoku
        ichi = self.trend.calc_ichimoku(df) if all(c in df.columns for c in ['high', 'low']) else None

        # Parabolic SAR
        psar = self.trend.calc_parabolic_sar(df) if all(c in df.columns for c in ['high', 'low']) else None

        result = {
            'price': round(latest, 2),
            'moving_averages': {
                'sma20': self._safe_latest(sma20),
                'sma50': self._safe_latest(sma50),
                'ema12': self._safe_latest(ema12),
                'ema26': self._safe_latest(ema26),
                'price_vs_sma20_pct': round((latest / self._safe_latest(sma20) - 1) * 100, 2) if self._safe_latest(sma20) else None,
                'sma20_vs_sma50': 'golden_cross' if self._safe_latest(sma20) > self._safe_latest(sma50) else 'death_cross',
            },
            'trend_strength': {
                'adx': round(self._safe_latest(adx_df['adx']), 1) if adx_df is not None else None,
                'adx_signal': self._adx_signal(self._safe_latest(adx_df['adx']) if adx_df is not None else None),
            },
            'momentum': {
                'roc_12': round(self._safe_latest(roc), 2),
                'trix': round(self._safe_latest(trix), 3),
            },
        }

        if sma200 is not None and len(sma200.dropna()) > 0:
            result['moving_averages']['sma200'] = round(sma200.iloc[-1], 2)
            result['moving_averages']['price_vs_sma200_pct'] = round((latest / sma200.iloc[-1] - 1) * 100, 2)

        # 额外周期均线（Skill 触发条件常用，如 sma5/sma9/sma65）
        for period in (3, 4, 5, 9, 10, 13, 21, 40, 65, 90):
            if len(df) >= period:
                sma = self.trend.calc_sma(df, period)
                val = self._safe_latest(sma)
                if val:
                    result['moving_averages'][f'sma{period}'] = round(val, 2)
                    result['moving_averages'][f'price_vs_sma{period}_pct'] = round((latest / val - 1) * 100, 2)

        if st is not None:
            result['supertrend'] = {
                'value': round(st['supertrend'].iloc[-1], 2),
                'direction': 'long' if st['direction'].iloc[-1] == 1 else 'short',
            }

        if ichi is not None:
            result['ichimoku'] = {
                'tenkan_sen': round(self._safe_latest(ichi['tenkan_sen']), 2),
                'kijun_sen': round(self._safe_latest(ichi['kijun_sen']), 2),
                'price_vs_kijun': 'above' if latest > self._safe_latest(ichi['kijun_sen']) else 'below',
            }

        if psar is not None:
            result['parabolic_sar'] = {
                'value': round(psar.iloc[-1], 2),
                'signal': 'bullish' if psar.iloc[-1] < latest else 'bearish',
            }

        return result

    def _extract_momentum(self, df: pd.DataFrame) -> Dict[str, Any]:
        """提取动量维度指标"""
        close = df['close']
        close.iloc[-1]

        # RSI
        rsi = self.momentum.calc_rsi(df, 14)
        rsi_val = self._safe_latest(rsi)

        # MACD
        macd_df = self.momentum.calc_macd(df)

        # KDJ
        kdj_df = self.momentum.calc_kdj(df) if all(c in df.columns for c in ['high', 'low']) else None

        # 其他动量指标
        cci = self.momentum.calc_cci(df, 20)
        williams = self.momentum.calc_williams_r(df, 14)
        stoch = self.momentum.calc_stoch(df) if all(c in df.columns for c in ['high', 'low']) else None
        mom = self.momentum.calc_momentum(df, 10)

        # 新增指标
        tsi = self.momentum.calc_tsi(df)
        ao = self.momentum.calc_awesome_oscillator(df) if all(c in df.columns for c in ['high', 'low']) else None
        uo = self.momentum.calc_ultimate_oscillator(df) if all(c in df.columns for c in ['high', 'low']) else None
        ppo = self.momentum.calc_ppo(df)
        stoch_rsi = self.momentum.calc_stoch_rsi(df)

        result = {
            'rsi': {
                'value': round(rsi_val, 1) if rsi_val else None,
                'signal': self._rsi_signal(rsi_val),
                'prev': round(rsi.iloc[-2], 1) if len(rsi) > 1 and not pd.isna(rsi.iloc[-2]) else None,
            },
            'macd': {
                'line': round(self._safe_latest(macd_df['macd']), 3),
                'signal': round(self._safe_latest(macd_df['signal']), 3),
                'histogram': round(self._safe_latest(macd_df['histogram']), 3),
                'trend': 'expanding' if macd_df['histogram'].iloc[-1] > macd_df['histogram'].iloc[-2] else 'contracting',
            },
            'cci': round(self._safe_latest(cci), 1),
            'williams_r': round(self._safe_latest(williams), 1),
            'momentum': round(self._safe_latest(mom), 2),
        }

        if kdj_df is not None:
            result['kdj'] = {
                'k': round(self._safe_latest(kdj_df['k']), 1),
                'd': round(self._safe_latest(kdj_df['d']), 1),
                'j': round(self._safe_latest(kdj_df['j']), 1),
            }

        if stoch is not None:
            result['stochastic'] = {
                'k': round(self._safe_latest(stoch['stoch_k']), 1),
                'd': round(self._safe_latest(stoch['stoch_d']), 1),
            }

        # 新增指标
        result['tsi'] = round(self._safe_latest(tsi), 2)
        result['awesome_oscillator'] = round(self._safe_latest(ao), 2) if ao is not None else None
        result['ultimate_oscillator'] = round(self._safe_latest(uo), 1) if uo is not None else None
        result['ppo'] = {
            'value': round(self._safe_latest(ppo['ppo']), 2),
            'signal': round(self._safe_latest(ppo['signal']), 2),
            'histogram': round(self._safe_latest(ppo['histogram']), 2),
        }
        result['stoch_rsi'] = {
            'value': round(self._safe_latest(stoch_rsi['stoch_rsi']), 3),
            'k': round(self._safe_latest(stoch_rsi['k']), 3),
            'd': round(self._safe_latest(stoch_rsi['d']), 3),
        }

        return result

    def _extract_volatility(self, df: pd.DataFrame) -> Dict[str, Any]:
        """提取波动率维度指标"""
        close = df['close']

        # ATR
        atr = self.volatility.calc_atr(df) if all(c in df.columns for c in ['high', 'low']) else None
        atr_val = self._safe_latest(atr) if atr is not None else None

        # Bollinger
        bb = self.volatility.calc_bollinger(df)
        latest = close.iloc[-1]
        bb_pct = (latest - bb['lower'].iloc[-1]) / (bb['upper'].iloc[-1] - bb['lower'].iloc[-1])

        # 历史波动率
        hist_vol = self.volatility.calc_hist_vol(df)

        # 新增波动率指标
        keltner = self.volatility.calc_keltner(df) if all(c in df.columns for c in ['high', 'low']) else None
        donchian = self.volatility.calc_donchian(df) if all(c in df.columns for c in ['high', 'low']) else None
        ulcer = self.volatility.calc_ulcer_index(df)
        chaikin_vol = self.volatility.calc_chaikin_volatility(df) if all(c in df.columns for c in ['high', 'low']) else None

        result = {
            'atr': {
                'value': round(atr_val, 2) if atr_val else None,
                'pct_of_price': round(atr_val / latest * 100, 2) if atr_val else None,
            },
            'bollinger': {
                'upper': round(bb['upper'].iloc[-1], 2),
                'middle': round(bb['middle'].iloc[-1], 2),
                'lower': round(bb['lower'].iloc[-1], 2),
                'percent_b': round(bb_pct, 2),
                'bandwidth': round(bb['bandwidth'].iloc[-1], 2),
                'position': self._boll_position(bb_pct),
            },
            'historical_volatility': round(self._safe_latest(hist_vol), 1),
        }

        if keltner is not None:
            result['keltner'] = {
                'upper': round(keltner['upper'].iloc[-1], 2),
                'middle': round(keltner['middle'].iloc[-1], 2),
                'lower': round(keltner['lower'].iloc[-1], 2),
            }

        if donchian is not None:
            result['donchian'] = {
                'upper': round(donchian['upper'].iloc[-1], 2),
                'middle': round(donchian['middle'].iloc[-1], 2),
                'lower': round(donchian['lower'].iloc[-1], 2),
            }

        result['ulcer_index'] = round(self._safe_latest(ulcer), 2)
        result['chaikin_volatility'] = round(self._safe_latest(chaikin_vol), 2) if chaikin_vol is not None else None

        return result

    def _extract_volume(self, df: pd.DataFrame) -> Dict[str, Any]:
        """提取量能维度指标"""
        if 'volume' not in df.columns:
            return {'error': 'No volume data'}

        volume = df['volume']
        close = df['close']

        # OBV
        obv = self.volume.calc_obv(df)

        # Volume Ratio
        vr = self.volume.calc_volume_ratio(df)

        # VWAP
        vwap = self.volume.calc_vwap(df) if all(c in df.columns for c in ['high', 'low']) else None

        # MFI
        mfi = self.volume.calc_mfi(df) if all(c in df.columns for c in ['high', 'low']) else None

        # 新增量能指标
        chaikin_osc = self.volume.calc_chaikin_oscillator(df) if all(c in df.columns for c in ['high', 'low']) else None
        eom = self.volume.calc_ease_of_movement(df) if all(c in df.columns for c in ['high', 'low']) else None
        force = self.volume.calc_force_index(df)
        nvi = self.volume.calc_nvi(df)
        pvi = self.volume.calc_pvi(df)

        # 成交量趋势
        vol_sma20 = volume.rolling(20).mean()
        vol_trend = volume.iloc[-1] / vol_sma20.iloc[-1] if not pd.isna(vol_sma20.iloc[-1]) else None

        result = {
            'latest_volume': int(volume.iloc[-1]),
            'avg_volume_20d': int(vol_sma20.iloc[-1]) if not pd.isna(vol_sma20.iloc[-1]) else None,
            'volume_ratio': round(vr.iloc[-1], 2) if not pd.isna(vr.iloc[-1]) else None,
            'volume_trend': 'above_avg' if vol_trend and vol_trend > 1.5 else 'below_avg' if vol_trend and vol_trend < 0.7 else 'normal',
            'obv': {
                'value': int(obv.iloc[-1]),
                'trend': 'rising' if obv.iloc[-1] > obv.iloc[-5] else 'falling',
            },
        }

        if vwap is not None:
            result['vwap'] = round(vwap.iloc[-1], 2)
            result['price_vs_vwap_pct'] = round((close.iloc[-1] / vwap.iloc[-1] - 1) * 100, 2)

        if mfi is not None:
            result['mfi'] = round(mfi.iloc[-1], 1)

        result['chaikin_oscillator'] = round(chaikin_osc.iloc[-1], 2) if chaikin_osc is not None else None
        result['ease_of_movement'] = round(eom.iloc[-1], 4) if eom is not None else None
        result['force_index'] = round(force.iloc[-1], 0)
        result['nvi'] = round(nvi.iloc[-1], 0)
        result['pvi'] = round(pvi.iloc[-1], 0)

        return result

    def _extract_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """提取形态检测结果（使用analyze_patterns聚合所有形态）"""
        if not all(c in df.columns for c in ['high', 'low']):
            return {'error': 'Need high/low for pattern detection'}

        result = self.pattern.analyze_patterns(df)

        # 统一输出格式（兼容旧代码）
        return {
            'patterns_detected': result.get('patterns', []),
            'pattern_count': result.get('pattern_count', 0),
            'swing_points': {
                'peaks_count': result.get('swing_points', {}).get('peaks', 0),
                'troughs_count': result.get('swing_points', {}).get('troughs', 0),
                'latest_peaks': result.get('resistance_levels', [])[-3:] if result.get('resistance_levels') else [],
                'latest_troughs': result.get('support_levels', [])[-3:] if result.get('support_levels') else [],
            },
            'gaps': result.get('gaps', {}),
            'support_levels': result.get('support_levels', []),
            'resistance_levels': result.get('resistance_levels', []),
        }

    def _extract_levels(self, df: pd.DataFrame) -> Dict[str, Any]:
        """提取支撑阻力维度"""
        if not all(c in df.columns for c in ['high', 'low']):
            return {'error': 'Need high/low for level calculation'}

        levels = self.levels.analyze_levels(df)

        return {
            'pivot_points': levels.get('pivot_points'),
            'fibonacci': levels.get('fibonacci'),
            'nearest_support': levels.get('nearest_support'),
            'nearest_resistance': levels.get('nearest_resistance'),
            'support_distance_pct': levels.get('support_distance_pct'),
            'resistance_distance_pct': levels.get('resistance_distance_pct'),
            'cluster_supports': levels.get('clusters', {}).get('support_clusters', []),
            'cluster_resistances': levels.get('clusters', {}).get('resistance_clusters', []),
        }

    def _extract_divergence(self, df: pd.DataFrame) -> Dict[str, Any]:
        """检测背离信号

        1. 价格-RSI背离
        2. 价格-MACD背离
        3. 价格-OBV背离（量价背离）
        """
        close = df['close']
        high = df['high'] if 'high' in df.columns else close
        low = df['low'] if 'low' in df.columns else close

        # 需要至少40天数据
        if len(df) < 40:
            return {'error': 'Need at least 40 days for divergence detection'}

        # RSI
        rsi = self.momentum.calc_rsi(df, 14)

        # MACD
        macd_df = self.momentum.calc_macd(df)
        macd_line = macd_df['macd']

        # OBV
        obv = self.volume.calc_obv(df) if 'volume' in df.columns else None

        divergences = []

        # 价格-RSI背离检测（使用最近20天内的局部极值）
        window = 5
        recent_prices = close.iloc[-30:].values
        recent_rsi = rsi.iloc[-30:].values
        recent_highs = high.iloc[-30:].values
        recent_lows = low.iloc[-30:].values

        # 找价格的局部高点和RSI的局部高点
        price_peaks = []
        rsi_peaks = []
        price_troughs = []
        rsi_troughs = []

        for i in range(window, len(recent_prices) - window):
            # 价格高点
            if all(recent_highs[i] > recent_highs[i-j] for j in range(1, window+1)) and \
               all(recent_highs[i] > recent_highs[i+j] for j in range(1, window+1)):
                price_peaks.append((i, recent_highs[i]))
            # RSI高点
            if all(recent_rsi[i] > recent_rsi[i-j] for j in range(1, window+1)) and \
               all(recent_rsi[i] > recent_rsi[i+j] for j in range(1, window+1)):
                rsi_peaks.append((i, recent_rsi[i]))
            # 价格低点
            if all(recent_lows[i] < recent_lows[i-j] for j in range(1, window+1)) and \
               all(recent_lows[i] < recent_lows[i+j] for j in range(1, window+1)):
                price_troughs.append((i, recent_lows[i]))
            # RSI低点
            if all(recent_rsi[i] < recent_rsi[i-j] for j in range(1, window+1)) and \
               all(recent_rsi[i] < recent_rsi[i+j] for j in range(1, window+1)):
                rsi_troughs.append((i, recent_rsi[i]))

        # 顶背离：价格新高但RSI未新高
        if len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
            p1, p2 = price_peaks[-2], price_peaks[-1]
            r1, r2 = None, None
            for r in rsi_peaks:
                if abs(r[0] - p1[0]) <= 3:
                    r1 = r
                if abs(r[0] - p2[0]) <= 3:
                    r2 = r

            if r1 and r2 and p2[1] > p1[1] and r2[1] < r1[1]:
                divergences.append({
                    'type': 'bearish_divergence',
                    'indicator': 'RSI',
                    'description': '价格创新高但RSI未创新高',
                    'strength': round((r1[1] - r2[1]) / r1[1] * 100, 1),
                })

        # 底背离：价格新低但RSI未新低
        if len(price_troughs) >= 2 and len(rsi_troughs) >= 2:
            t1, t2 = price_troughs[-2], price_troughs[-1]
            r1, r2 = None, None
            for r in rsi_troughs:
                if abs(r[0] - t1[0]) <= 3:
                    r1 = r
                if abs(r[0] - t2[0]) <= 3:
                    r2 = r

            if r1 and r2 and t2[1] < t1[1] and r2[1] > r1[1]:
                divergences.append({
                    'type': 'bullish_divergence',
                    'indicator': 'RSI',
                    'description': '价格创新低但RSI未创新低',
                    'strength': round((r2[1] - r1[1]) / abs(r1[1]) * 100, 1),
                })

        # 价格-MACD背离
        recent_macd = macd_line.iloc[-30:].values
        macd_peaks = []
        macd_troughs = []
        for i in range(window, len(recent_macd) - window):
            if all(recent_macd[i] > recent_macd[i-j] for j in range(1, window+1)) and \
               all(recent_macd[i] > recent_macd[i+j] for j in range(1, window+1)):
                macd_peaks.append((i, recent_macd[i]))
            if all(recent_macd[i] < recent_macd[i-j] for j in range(1, window+1)) and \
               all(recent_macd[i] < recent_macd[i+j] for j in range(1, window+1)):
                macd_troughs.append((i, recent_macd[i]))

        # MACD顶背离
        if len(price_peaks) >= 2 and len(macd_peaks) >= 2:
            p1, p2 = price_peaks[-2], price_peaks[-1]
            m1, m2 = None, None
            for m in macd_peaks:
                if abs(m[0] - p1[0]) <= 3:
                    m1 = m
                if abs(m[0] - p2[0]) <= 3:
                    m2 = m

            if m1 and m2 and p2[1] > p1[1] and m2[1] < m1[1]:
                divergences.append({
                    'type': 'bearish_divergence',
                    'indicator': 'MACD',
                    'description': '价格创新高但MACD未创新高',
                    'strength': round((m1[1] - m2[1]) / abs(m1[1]) * 100, 1) if m1[1] != 0 else 0,
                })

        # MACD底背离
        if len(price_troughs) >= 2 and len(macd_troughs) >= 2:
            t1, t2 = price_troughs[-2], price_troughs[-1]
            m1, m2 = None, None
            for m in macd_troughs:
                if abs(m[0] - t1[0]) <= 3:
                    m1 = m
                if abs(m[0] - t2[0]) <= 3:
                    m2 = m

            if m1 and m2 and t2[1] < t1[1] and m2[1] > m1[1]:
                divergences.append({
                    'type': 'bullish_divergence',
                    'indicator': 'MACD',
                    'description': '价格创新低但MACD未创新低',
                    'strength': round((m2[1] - m1[1]) / abs(m1[1]) * 100, 1) if m1[1] != 0 else 0,
                })

        # 价格-OBV背离（量价背离）
        if obv is not None:
            recent_obv = obv.iloc[-30:].values
            obv_peaks = []
            obv_troughs = []
            for i in range(window, len(recent_obv) - window):
                if all(recent_obv[i] > recent_obv[i-j] for j in range(1, window+1)) and \
                   all(recent_obv[i] > recent_obv[i+j] for j in range(1, window+1)):
                    obv_peaks.append((i, recent_obv[i]))
                if all(recent_obv[i] < recent_obv[i-j] for j in range(1, window+1)) and \
                   all(recent_obv[i] < recent_obv[i+j] for j in range(1, window+1)):
                    obv_troughs.append((i, recent_obv[i]))

            # 量价顶背离：价格新高但OBV未新高
            if len(price_peaks) >= 2 and len(obv_peaks) >= 2:
                p1, p2 = price_peaks[-2], price_peaks[-1]
                o1, o2 = None, None
                for o in obv_peaks:
                    if abs(o[0] - p1[0]) <= 3:
                        o1 = o
                    if abs(o[0] - p2[0]) <= 3:
                        o2 = o

                if o1 and o2 and p2[1] > p1[1] and o2[1] < o1[1]:
                    divergences.append({
                        'type': 'volume_divergence_bearish',
                        'indicator': 'OBV',
                        'description': '价格创新高但OBV未创新高（量价背离，上涨动能不足）',
                        'strength': round((o1[1] - o2[1]) / abs(o1[1]) * 100, 1) if o1[1] != 0 else 0,
                    })

            # 量价底背离：价格新低但OBV未新低
            if len(price_troughs) >= 2 and len(obv_troughs) >= 2:
                t1, t2 = price_troughs[-2], price_troughs[-1]
                o1, o2 = None, None
                for o in obv_troughs:
                    if abs(o[0] - t1[0]) <= 3:
                        o1 = o
                    if abs(o[0] - t2[0]) <= 3:
                        o2 = o

                if o1 and o2 and t2[1] < t1[1] and o2[1] > o1[1]:
                    divergences.append({
                        'type': 'volume_divergence_bullish',
                        'indicator': 'OBV',
                        'description': '价格创新低但OBV未创新低（量价背离，下跌动能不足）',
                        'strength': round((o2[1] - o1[1]) / abs(o1[1]) * 100, 1) if o1[1] != 0 else 0,
                    })

        # 综合背离信号
        bearish_divs = [d for d in divergences if 'bearish' in d['type']]
        bullish_divs = [d for d in divergences if 'bullish' in d['type']]

        return {
            'divergences': divergences,
            'count': len(divergences),
            'bearish_count': len(bearish_divs),
            'bullish_count': len(bullish_divs),
            'primary_signal': 'bearish' if len(bearish_divs) > len(bullish_divs) else 'bullish' if len(bullish_divs) > len(bearish_divs) else 'none',
            'strength': round(len(divergences) * 20 + sum(d.get('strength', 0) for d in divergences) * 0.5, 1),
        }

    def _extract_trend_stage(self, df: pd.DataFrame) -> Dict[str, Any]:
        """评估趋势阶段

        判断趋势处于：初期(early)、中期(middle)、末期(late)、衰竭(fading)
        """
        close = df['close']
        latest = close.iloc[-1]

        if len(df) < 100:
            return {'error': 'Need at least 100 days for trend stage assessment'}

        # ADX及变化率
        adx_df = self.trend.calc_adx(df) if all(c in df.columns for c in ['high', 'low']) else None
        adx = self._safe_latest(adx_df['adx']) if adx_df is not None else None
        adx_10d_ago = adx_df['adx'].iloc[-10] if adx_df is not None and len(adx_df) > 10 else None
        adx_change = ((adx - adx_10d_ago) / adx_10d_ago * 100) if adx and adx_10d_ago else None

        # 均线偏离度
        sma20 = self.trend.calc_sma(df, 20)
        sma50 = self.trend.calc_sma(df, 50)
        self.trend.calc_sma(df, 200) if len(df) >= 200 else None

        dev_20 = (latest / self._safe_latest(sma20) - 1) * 100 if self._safe_latest(sma20) else None
        dev_50 = (latest / self._safe_latest(sma50) - 1) * 100 if self._safe_latest(sma50) else None

        # 偏离度变化率（过去10天）
        dev_20_10d = (close.iloc[-10] / sma20.iloc[-10] - 1) * 100 if len(sma20) > 10 else None
        dev_20_change = (dev_20 - dev_20_10d) if dev_20 and dev_20_10d else None

        # 近期价格加速度
        returns_5d = (latest / close.iloc[-6] - 1) * 100 if len(close) > 5 else None
        returns_10d = (latest / close.iloc[-11] - 1) * 100 if len(close) > 10 else None
        returns_20d = (latest / close.iloc[-21] - 1) * 100 if len(close) > 20 else None

        # 加速度 = 近期涨速 - 前期涨速
        accel = (returns_5d - (returns_20d - returns_10d)) if all(v is not None for v in [returns_5d, returns_20d, returns_10d]) else None

        # 判断趋势阶段
        stage = 'unknown'
        stage_confidence = 0

        if adx and dev_20 is not None:
            if adx > 40:
                # ADX极强
                if adx_change and adx_change > 5:
                    stage = 'early_acceleration'
                    stage_confidence = 70
                elif adx_change and adx_change < -5:
                    stage = 'fading'
                    stage_confidence = 75
                elif dev_20 > 20:
                    stage = 'late'
                    stage_confidence = 65
                else:
                    stage = 'middle'
                    stage_confidence = 60
            elif adx > 25:
                # ADX强
                if dev_20_change and dev_20_change > 3:
                    stage = 'early'
                    stage_confidence = 60
                elif dev_20_change and dev_20_change < -3:
                    stage = 'fading'
                    stage_confidence = 65
                elif abs(dev_20) < 5:
                    stage = 'early'
                    stage_confidence = 55
                else:
                    stage = 'middle'
                    stage_confidence = 55
            else:
                stage = 'ranging'
                stage_confidence = 60

        # 特殊信号：极端偏离
        extreme_deviation = False
        if dev_20 and abs(dev_20) > 25:
            extreme_deviation = True

        return {
            'stage': stage,
            'stage_confidence': stage_confidence,
            'adx_change_10d_pct': round(adx_change, 1) if adx_change else None,
            'ma_deviation_20': round(dev_20, 1) if dev_20 else None,
            'ma_deviation_50': round(dev_50, 1) if dev_50 else None,
            'ma_deviation_change_10d': round(dev_20_change, 1) if dev_20_change else None,
            'price_acceleration': round(accel, 1) if accel else None,
            'extreme_deviation': extreme_deviation,
            'interpretation': self._trend_stage_interpretation(stage, extreme_deviation),
        }

    def _extract_volatility_state(self, df: pd.DataFrame) -> Dict[str, Any]:
        """检测波动率状态变化

        1. Bollinger Squeeze → Expansion
        2. 波动率收缩/扩张判断
        3. 历史波动率变化
        """
        df['close']

        if len(df) < 40:
            return {'error': 'Need at least 40 days for volatility state'}

        # 布林带
        bb = self.volatility.calc_bollinger(df)
        bandwidth = bb['bandwidth']

        latest_bw = bandwidth.iloc[-1]
        bw_20d_avg = bandwidth.iloc[-20:].mean()
        bw_20d_min = bandwidth.iloc[-20:].min()
        bw_20d_max = bandwidth.iloc[-20:].max()

        # Squeeze: 当前带宽接近20日最低（< 20日平均的50%）
        squeeze = latest_bw < bw_20d_avg * 0.5 and latest_bw < bw_20d_min * 1.2

        # Expansion: 当前带宽接近20日最高（> 20日平均的150%）
        expansion = latest_bw > bw_20d_avg * 1.5 and latest_bw > bw_20d_max * 0.8

        # 带宽趋势
        bw_5d_avg = bandwidth.iloc[-5:].mean()
        bw_10d_avg = bandwidth.iloc[-10:].mean()
        bw_trend = 'expanding' if bw_5d_avg > bw_10d_avg * 1.1 else 'contracting' if bw_5d_avg < bw_10d_avg * 0.9 else 'stable'

        # ATR变化
        atr = self.volatility.calc_atr(df) if all(c in df.columns for c in ['high', 'low']) else None
        if atr is not None:
            atr_change = (atr.iloc[-1] / atr.iloc[-10:].mean() - 1) * 100 if len(atr) > 10 else None
        else:
            atr_change = None

        # 历史波动率变化
        hist_vol = self.volatility.calc_hist_vol(df)
        hv_change = (hist_vol.iloc[-1] / hist_vol.iloc[-10:].mean() - 1) * 100 if len(hist_vol) > 10 else None

        # 波动率状态综合判断
        state = 'normal'
        if squeeze:
            state = 'squeeze'
        elif expansion:
            state = 'expansion'
        elif bw_trend == 'expanding':
            state = 'expanding'
        elif bw_trend == 'contracting':
            state = 'contracting'

        # Squeeze → Expansion 预警
        squeeze_to_expansion_alert = False
        if bw_trend == 'expanding' and bandwidth.iloc[-10:].min() < bw_20d_avg * 0.6:
            squeeze_to_expansion_alert = True

        return {
            'state': state,
            'squeeze': squeeze,
            'expansion': expansion,
            'squeeze_to_expansion_alert': squeeze_to_expansion_alert,
            'bandwidth_latest': round(latest_bw, 2),
            'bandwidth_trend': bw_trend,
            'bandwidth_20d_range': [round(bw_20d_min, 2), round(bw_20d_max, 2)],
            'atr_change_10d_pct': round(atr_change, 1) if atr_change else None,
            'hist_vol_change_10d_pct': round(hv_change, 1) if hv_change else None,
            'volatility_breakout_risk': 'high' if squeeze_to_expansion_alert else 'normal',
        }

    def _extract_momentum_accel(self, df: pd.DataFrame) -> Dict[str, Any]:
        """检测动量加速度/减速度

        1. RSI加速度
        2. MACD histogram加速度
        3. 价格变化加速度
        """
        close = df['close']

        if len(df) < 20:
            return {'error': 'Need at least 20 days for momentum acceleration'}

        # RSI加速度
        rsi = self.momentum.calc_rsi(df, 14)
        rsi_change_1d = rsi.iloc[-1] - rsi.iloc[-2] if len(rsi) > 1 else None
        rsi_change_5d = rsi.iloc[-1] - rsi.iloc[-6] if len(rsi) > 5 else None
        rsi_accel = (rsi_change_1d - (rsi_change_5d / 5)) if rsi_change_1d and rsi_change_5d else None

        # MACD histogram加速度
        macd_df = self.momentum.calc_macd(df)
        hist = macd_df['histogram']
        hist_1d = hist.iloc[-1] - hist.iloc[-2] if len(hist) > 1 else None
        hist_3d = (hist.iloc[-1] - hist.iloc[-4]) / 3 if len(hist) > 3 else None
        hist_accel = (hist_1d - hist_3d) if hist_1d and hist_3d else None

        # 价格加速度（二阶导数近似）
        ret_1d = (close.iloc[-1] / close.iloc[-2] - 1) * 100 if len(close) > 1 else None
        ret_3d = (close.iloc[-1] / close.iloc[-4] - 1) * 100 / 3 if len(close) > 3 else None
        ret_5d = (close.iloc[-1] / close.iloc[-6] - 1) * 100 / 5 if len(close) > 5 else None

        price_accel = None
        if ret_1d and ret_3d and ret_5d:
            # 如果1日涨速 > 3日平均涨速 > 5日平均涨速，说明在加速
            if ret_1d > ret_3d > ret_5d:
                price_accel = 'accelerating'
            elif ret_1d < ret_3d < ret_5d:
                price_accel = 'decelerating'
            else:
                price_accel = 'mixed'

        # 综合动量方向
        momentum_direction = 'neutral'
        if rsi_change_5d:
            if rsi_change_5d > 5 and hist.iloc[-1] > hist.iloc[-6] if len(hist) > 5 else False:
                momentum_direction = 'strengthening'
            elif rsi_change_5d < -5 and hist.iloc[-1] < hist.iloc[-6] if len(hist) > 5 else False:
                momentum_direction = 'weakening'

        return {
            'rsi_change_1d': round(rsi_change_1d, 2) if rsi_change_1d else None,
            'rsi_change_5d': round(rsi_change_5d, 2) if rsi_change_5d else None,
            'rsi_acceleration': round(rsi_accel, 2) if rsi_accel else None,
            'macd_hist_change_1d': round(hist_1d, 3) if hist_1d else None,
            'macd_hist_acceleration': round(hist_accel, 3) if hist_accel else None,
            'price_acceleration': price_accel,
            'momentum_direction': momentum_direction,
            'signal': 'momentum_accelerating' if momentum_direction == 'strengthening' and price_accel == 'accelerating' else
                     'momentum_decelerating' if momentum_direction == 'weakening' or price_accel == 'decelerating' else
                     'momentum_stable',
        }

    def _extract_multi_timeframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        """多时间框架一致性评估

        评估短期(5日)/中期(20日)/长期(50日/200日)趋势是否一致
        """
        close = df['close']
        latest = close.iloc[-1]

        if len(df) < 50:
            return {'error': 'Need at least 50 days for multi-timeframe analysis'}

        # 短期趋势（5日EMA）
        ema5 = close.ewm(span=5).mean()
        short_trend = 'up' if latest > ema5.iloc[-1] else 'down'

        # 中期趋势（20日EMA）
        ema20 = close.ewm(span=20).mean()
        mid_trend = 'up' if latest > ema20.iloc[-1] else 'down'

        # 长期趋势
        ema50 = close.ewm(span=50).mean()
        long_trend = 'up' if latest > ema50.iloc[-1] else 'down'

        # 均线方向（斜率）
        ema5_slope = (ema5.iloc[-1] - ema5.iloc[-5]) / ema5.iloc[-5] * 100 if len(ema5) > 5 else None
        ema20_slope = (ema20.iloc[-1] - ema20.iloc[-10]) / ema20.iloc[-10] * 100 if len(ema20) > 10 else None
        ema50_slope = (ema50.iloc[-1] - ema50.iloc[-20]) / ema50.iloc[-20] * 100 if len(ema50) > 20 else None

        # 一致性判断
        trends = [short_trend, mid_trend, long_trend]
        up_count = trends.count('up')
        down_count = trends.count('down')

        alignment = 'neutral'
        if up_count == 3:
            alignment = 'strongly_bullish'
        elif up_count == 2 and down_count == 1:
            alignment = 'bullish'
        elif down_count == 3:
            alignment = 'strongly_bearish'
        elif down_count == 2 and up_count == 1:
            alignment = 'bearish'
        else:
            alignment = 'mixed'

        # 趋势拐头信号
        short_turning = False
        if ema5_slope and ema20_slope:
            if short_trend == 'up' and ema5_slope < ema20_slope * 0.5:
                short_turning = 'short_weakening'
            elif short_trend == 'down' and ema5_slope > ema20_slope * 0.5:
                short_turning = 'short_strengthening'

        # 长期趋势 intact 判断
        long_intact = False
        if long_trend == 'up' and ema50_slope and ema50_slope > 0:
            long_intact = True
        elif long_trend == 'down' and ema50_slope and ema50_slope < 0:
            long_intact = True

        return {
            'short_trend': short_trend,
            'mid_trend': mid_trend,
            'long_trend': long_trend,
            'alignment': alignment,
            'up_count': up_count,
            'down_count': down_count,
            'short_turning': short_turning,
            'long_trend_intact': long_intact,
            'ema5_slope_5d_pct': round(ema5_slope, 2) if ema5_slope else None,
            'ema20_slope_10d_pct': round(ema20_slope, 2) if ema20_slope else None,
            'ema50_slope_20d_pct': round(ema50_slope, 2) if ema50_slope else None,
        }

    def _extract_composite(self, df: pd.DataFrame) -> Dict[str, Any]:
        """提取综合信号"""
        close = df['close']
        latest = close.iloc[-1]

        # 短期/中期/长期趋势
        sma20 = self.trend.calc_sma(df, 20)
        sma50 = self.trend.calc_sma(df, 50)

        short_trend = 'up' if latest > self._safe_latest(sma20) else 'down'
        mid_trend = 'up' if self._safe_latest(sma20) > self._safe_latest(sma50) else 'down'

        # 价格位置（过去60天）
        recent = df.tail(60)
        price_position = (latest - recent['low'].min()) / (recent['high'].max() - recent['low'].min())

        # 近期涨跌幅
        returns = {
            '1d': round((close.iloc[-1] / close.iloc[-2] - 1) * 100, 2) if len(close) > 1 else None,
            '5d': round((close.iloc[-1] / close.iloc[-6] - 1) * 100, 2) if len(close) > 5 else None,
            '20d': round((close.iloc[-1] / close.iloc[-21] - 1) * 100, 2) if len(close) > 20 else None,
        }

        # 波动状态
        atr = self.volatility.calc_atr(df) if all(c in df.columns for c in ['high', 'low']) else None
        atr_pct = self._safe_latest(atr) / latest * 100 if atr is not None else None

        return {
            'short_trend': short_trend,
            'mid_trend': mid_trend,
            'price_position_60d': round(price_position, 2),
            'returns': returns,
            'volatility_state': 'high' if atr_pct and atr_pct > 3 else 'low' if atr_pct and atr_pct < 1 else 'normal',
        }

    def format_for_llm(self, features: Dict[str, Any]) -> str:
        """将特征格式化为LLM Prompt友好的文本

        输出格式简洁、结构化，方便LLM直接阅读分析。
        """
        lines = ["# 技术指标数据", ""]

        # 综合信息
        comp = features.get('composite', {})
        lines.append("## 综合状态")
        lines.append(f"- 短期趋势: {comp.get('short_trend', 'unknown')}")
        lines.append(f"- 中期趋势: {comp.get('mid_trend', 'unknown')}")
        lines.append(f"- 价格位置(60日): {comp.get('price_position_60d', 'N/A')}")
        lines.append(f"- 涨跌幅: 1日{comp.get('returns', {}).get('1d', 'N/A')}% | 5日{comp.get('returns', {}).get('5d', 'N/A')}% | 20日{comp.get('returns', {}).get('20d', 'N/A')}%")
        lines.append(f"- 波动状态: {comp.get('volatility_state', 'unknown')}")
        lines.append("")

        # 趋势
        trend = features.get('trend', {})
        lines.append("## 趋势指标")
        lines.append(f"- 价格: {trend.get('price')}")
        ma = trend.get('moving_averages', {})
        lines.append(f"- MA: SMA20={ma.get('sma20')} | SMA50={ma.get('sma50')} | EMA12={ma.get('ema12')} | EMA26={ma.get('ema26')}")
        if ma.get('sma200'):
            lines.append(f"- SMA200: {ma.get('sma200')} (偏离{ma.get('price_vs_sma200_pct')}%)")
        ts = trend.get('trend_strength', {})
        lines.append(f"- ADX: {ts.get('adx')} ({ts.get('adx_signal')})")
        if trend.get('supertrend'):
            st = trend['supertrend']
            lines.append(f"- SuperTrend: 方向{st.get('direction')} | 值{st.get('value')}")
        if trend.get('ichimoku'):
            ichi = trend['ichimoku']
            lines.append(f"- Ichimoku: 转换线{ichi.get('tenkan_sen')} | 基准线{ichi.get('kijun_sen')} | 价格{ichi.get('price_vs_kijun')}")
        lines.append("")

        # 动量
        mom = features.get('momentum', {})
        lines.append("## 动量指标")
        rsi = mom.get('rsi', {})
        lines.append(f"- RSI(14): {rsi.get('value')} ({rsi.get('signal')})")
        macd = mom.get('macd', {})
        lines.append(f"- MACD: {macd.get('line')} | Signal: {macd.get('signal')} | Hist: {macd.get('histogram')} ({macd.get('trend')})")
        if mom.get('kdj'):
            kdj = mom['kdj']
            lines.append(f"- KDJ: K={kdj.get('k')} D={kdj.get('d')} J={kdj.get('j')}")
        lines.append(f"- CCI(20): {mom.get('cci')}")
        lines.append(f"- Williams %R: {mom.get('williams_r')}")
        if mom.get('stochastic'):
            stoch = mom['stochastic']
            lines.append(f"- Stochastic: %K={stoch.get('k')} %D={stoch.get('d')}")
        lines.append(f"- TSI: {mom.get('tsi')}")
        lines.append(f"- Awesome Oscillator: {mom.get('awesome_oscillator')}")
        lines.append(f"- Ultimate Oscillator: {mom.get('ultimate_oscillator')}")
        if mom.get('ppo'):
            ppo = mom['ppo']
            lines.append(f"- PPO: {ppo.get('value')} | Signal: {ppo.get('signal')} | Hist: {ppo.get('histogram')}")
        lines.append("")

        # 波动率
        vol = features.get('volatility', {})
        lines.append("## 波动率指标")
        atr = vol.get('atr', {})
        lines.append(f"- ATR(14): {atr.get('value')} ({atr.get('pct_of_price')}% of price)")
        bb = vol.get('bollinger', {})
        lines.append(f"- Bollinger: Upper={bb.get('upper')} Middle={bb.get('middle')} Lower={bb.get('lower')}")
        lines.append(f"- Bollinger位置: %B={bb.get('percent_b')} | 带宽={bb.get('bandwidth')}% | 位置={bb.get('position')}")
        lines.append(f"- 历史波动率(20日): {vol.get('historical_volatility')}%")
        if vol.get('keltner'):
            k = vol['keltner']
            lines.append(f"- Keltner: Upper={k.get('upper')} Middle={k.get('middle')} Lower={k.get('lower')}")
        if vol.get('donchian'):
            d = vol['donchian']
            lines.append(f"- Donchian: Upper={d.get('upper')} Middle={d.get('middle')} Lower={d.get('lower')}")
        lines.append(f"- Ulcer Index: {vol.get('ulcer_index')}")
        lines.append("")

        # 量能
        vol_data = features.get('volume', {})
        lines.append("## 量能指标")
        if 'error' not in vol_data:
            lines.append(f"- 成交量: 最新{vol_data.get('latest_volume')} | 20日均{vol_data.get('avg_volume_20d')} | 量比{vol_data.get('volume_ratio')}")
            lines.append(f"- 量能趋势: {vol_data.get('volume_trend')}")
            obv = vol_data.get('obv', {})
            lines.append(f"- OBV: {obv.get('value')} (趋势{obv.get('trend')})")
            if vol_data.get('vwap'):
                lines.append(f"- VWAP: {vol_data.get('vwap')} (价格偏离{vol_data.get('price_vs_vwap_pct')}%)")
            lines.append(f"- MFI(14): {vol_data.get('mfi')}")
            lines.append(f"- Chaikin Oscillator: {vol_data.get('chaikin_oscillator')}")
            lines.append(f"- Force Index(13): {vol_data.get('force_index')}")
        lines.append("")

        # 形态
        pat = features.get('pattern', {})
        lines.append("## 形态检测")
        patterns = pat.get('patterns_detected', [])
        if patterns:
            for p in patterns:
                lines.append(f"- {p['name']}: 置信度{p.get('confidence', 'N/A')}%")
        else:
            lines.append("- 未检测到明确形态")
        sp = pat.get('swing_points', {})
        lines.append(f"- 近期极值: 高点{sp.get('latest_peaks', [])} | 低点{sp.get('latest_troughs', [])}")
        lines.append("")

        # 支撑阻力
        lvl = features.get('levels', {})
        lines.append("## 支撑阻力")
        lines.append(f"- 最近支撑: {lvl.get('nearest_support')} (距离{lvl.get('support_distance_pct')}%)")
        lines.append(f"- 最近阻力: {lvl.get('nearest_resistance')} (距离{lvl.get('resistance_distance_pct')}%)")
        if lvl.get('pivot_points'):
            pp = lvl['pivot_points']
            lines.append(f"- 枢轴点: PP={pp.get('pp')} R1={pp.get('r1')} S1={pp.get('s1')} R2={pp.get('r2')} S2={pp.get('s2')}")
        lines.append("")

        # 背离检测
        div = features.get('divergence', {})
        lines.append("## 背离检测")
        if 'error' not in div:
            divergences = div.get('divergences', [])
            if divergences:
                lines.append(f"- 发现 {div.get('count', 0)} 个背离信号")
                for d in divergences:
                    lines.append(f"  - [{d['type']}] {d['indicator']}: {d['description']} (强度{d.get('strength', 'N/A')})")
                lines.append(f"- 综合信号: {div.get('primary_signal', 'none')} | 强度: {div.get('strength', 'N/A')}")
            else:
                lines.append("- 未检测到明显背离信号")
        else:
            lines.append(f"- {div.get('error')}")
        lines.append("")

        # 趋势阶段
        ts = features.get('trend_stage', {})
        lines.append("## 趋势阶段评估")
        if 'error' not in ts:
            lines.append(f"- 阶段: {ts.get('stage', 'unknown')} (置信度{ts.get('stage_confidence')}%)")
            lines.append(f"- ADX 10日变化: {ts.get('adx_change_10d_pct', 'N/A')}%")
            lines.append(f"- 均线偏离: SMA20={ts.get('ma_deviation_20', 'N/A')}% | SMA50={ts.get('ma_deviation_50', 'N/A')}%")
            lines.append(f"- 偏离度10日变化: {ts.get('ma_deviation_change_10d', 'N/A')}%")
            lines.append(f"- 价格加速度: {ts.get('price_acceleration', 'N/A')}")
            if ts.get('extreme_deviation'):
                lines.append("- ⚠️ 极端偏离警告")
            lines.append(f"- 解读: {ts.get('interpretation', '')}")
        else:
            lines.append(f"- {ts.get('error')}")
        lines.append("")

        # 波动率状态
        vs = features.get('volatility_state', {})
        lines.append("## 波动率状态")
        if 'error' not in vs:
            lines.append(f"- 状态: {vs.get('state', 'unknown')}")
            lines.append(f"- Squeeze: {'是' if vs.get('squeeze') else '否'} | Expansion: {'是' if vs.get('expansion') else '否'}")
            lines.append(f"- 带宽趋势: {vs.get('bandwidth_trend', 'N/A')}")
            lines.append(f"- 带宽范围(20日): {vs.get('bandwidth_20d_range', 'N/A')}")
            if vs.get('squeeze_to_expansion_alert'):
                lines.append("- ⚠️ Squeeze→Expansion 突破预警: 波动率收缩后可能迎来大行情")
            lines.append(f"- 波动突破风险: {vs.get('volatility_breakout_risk', 'normal')}")
        else:
            lines.append(f"- {vs.get('error')}")
        lines.append("")

        # 动量加速度
        ma = features.get('momentum_accel', {})
        lines.append("## 动量加速度")
        if 'error' not in ma:
            lines.append(f"- RSI变化: 1日{ma.get('rsi_change_1d', 'N/A')} | 5日{ma.get('rsi_change_5d', 'N/A')} | 加速度{ma.get('rsi_acceleration', 'N/A')}")
            lines.append(f"- MACD Hist变化: 1日{ma.get('macd_hist_change_1d', 'N/A')} | 加速度{ma.get('macd_hist_acceleration', 'N/A')}")
            lines.append(f"- 价格加速度: {ma.get('price_acceleration', 'N/A')}")
            lines.append(f"- 动量方向: {ma.get('momentum_direction', 'N/A')}")
            lines.append(f"- 信号: {ma.get('signal', 'N/A')}")
        else:
            lines.append(f"- {ma.get('error')}")
        lines.append("")

        # 多时间框架
        mtf = features.get('multi_timeframe', {})
        lines.append("## 多时间框架一致性")
        if 'error' not in mtf:
            lines.append(f"- 短期(5日): {mtf.get('short_trend', 'N/A')} | 中期(20日): {mtf.get('mid_trend', 'N/A')} | 长期(50日): {mtf.get('long_trend', 'N/A')}")
            lines.append(f"- 一致性: {mtf.get('alignment', 'N/A')} (多头{mtf.get('up_count')}/空头{mtf.get('down_count')})")
            if mtf.get('short_turning'):
                lines.append(f"- 短期拐头: {mtf.get('short_turning')}")
            lines.append(f"- 长期趋势完好: {'是' if mtf.get('long_trend_intact') else '否'}")
            lines.append(f"- EMA斜率: 5日{mtf.get('ema5_slope_5d_pct', 'N/A')}% | 20日{mtf.get('ema20_slope_10d_pct', 'N/A')}% | 50日{mtf.get('ema50_slope_20d_pct', 'N/A')}%")
        else:
            lines.append(f"- {mtf.get('error')}")
        lines.append("")

        # 形态（更新为包含新形态）
        pat = features.get('pattern', {})
        lines.append("## 形态检测")
        patterns = pat.get('patterns_detected', [])
        if patterns:
            for p in patterns:
                lines.append(f"- {p['name']}: 置信度{p.get('confidence', 'N/A')}%")
        else:
            lines.append("- 未检测到明确形态")
        sp = pat.get('swing_points', {})
        lines.append(f"- 近期极值: 高点{sp.get('latest_peaks', [])} | 低点{sp.get('latest_troughs', [])}")
        # 缺口
        gaps = pat.get('gaps', {})
        if gaps and gaps.get('gaps'):
            lines.append(f"- 缺口: 共{len(gaps['gaps'])}个 | 突破{gaps.get('breakaway_count', 0)} | 持续{gaps.get('runaway_count', 0)} | 衰竭{gaps.get('exhaustion_count', 0)}")
            latest = gaps.get('latest_gap')
            if latest:
                lines.append(f"  - 最新缺口: {latest['type']} {latest['classification']} {latest['gap_pct']}%")
        lines.append("")

        return '\n'.join(lines)

    # ===== 辅助方法 =====

    def _safe_latest(self, series) -> Optional[float]:
        """安全获取序列最新值"""
        if series is None:
            return None
        if isinstance(series, pd.DataFrame):
            # 对于DataFrame，需要指定列，这里返回None表示调用方需要处理
            return None
        if len(series) == 0:
            return None
        val = series.iloc[-1]
        if pd.isna(val):
            return None
        return float(val)

    def _trend_stage_interpretation(self, stage: str, extreme_deviation: bool) -> str:
        """趋势阶段解读"""
        interpretations = {
            'early': '趋势初期：动能正在积累，可能还有较大空间',
            'early_acceleration': '趋势加速初期：动能增强，但注意是否过度加速',
            'middle': '趋势中期：趋势确立，但空间可能已消耗一部分',
            'late': '趋势末期：价格已大幅偏离均线，警惕反转风险',
            'fading': '趋势衰竭：动能正在减弱，ADX下降是明确信号',
            'ranging': '震荡区间：无明确趋势，等待方向选择',
            'unknown': '无法判断趋势阶段',
        }
        base = interpretations.get(stage, '未知')
        if extreme_deviation and stage in ['late', 'fading']:
            base += ' | 极端偏离警告：价格严重偏离均线，反转风险极高'
        elif extreme_deviation:
            base += ' | 价格偏离度较高，注意均值回归压力'
        return base

    def _rsi_signal(self, rsi: Optional[float]) -> str:
        if rsi is None:
            return 'unknown'
        if rsi > 70:
            return 'overbought'
        if rsi < 30:
            return 'oversold'
        if rsi > 50:
            return 'bullish_zone'
        return 'bearish_zone'

    def _adx_signal(self, adx: Optional[float]) -> str:
        if adx is None:
            return 'unknown'
        if adx > 40:
            return 'very_strong'
        if adx > 25:
            return 'strong'
        if adx > 20:
            return 'moderate'
        return 'weak/ranging'

    def _boll_position(self, pct_b: float) -> str:
        if pct_b > 0.95:
            return 'upper_band'
        if pct_b < 0.05:
            return 'lower_band'
        if pct_b > 0.8:
            return 'upper_half'
        if pct_b < 0.2:
            return 'lower_half'
        return 'middle'
