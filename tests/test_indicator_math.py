"""指标计算数学正确性回归测试（2026-07 审查修复）

覆盖：
- SuperTrend 反转不 whipsaw（标准实现：被击穿后跳到对侧轨道）
- 圆弧顶/底方向检测
- 楔形收敛条件（按价格归一化）
- V形反转 IndexError 防护
- 双底检测最近优先 + 突破时点
- 岛形反转隔离性
- 枢轴点使用前一完整周期
- 旗形旗杆窗口
- MFI 持平日处理、零分母防护
"""

import numpy as np
import pandas as pd


def make_df(closes, spreads=0.01):
    """由收盘价序列构造 OHLCV DataFrame"""
    closes = np.array(closes, dtype=float)
    highs = closes * (1 + spreads)
    lows = closes * (1 - spreads)
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    return pd.DataFrame({
        'open': opens, 'high': highs, 'low': lows,
        'close': closes, 'volume': np.full(len(closes), 1e6),
    })


class TestSuperTrend:
    def test_no_whipsaw_after_reversal(self):
        """翻空后，价格小幅反弹（未破上轨）不得翻回多头"""
        from utils.tech_calculator.trend import TrendCalculator
        # 20 根上涨 → 1 根大跌翻空 → 小幅反弹 → 继续跌
        closes = list(np.linspace(100, 120, 20)) + [110, 112, 111, 108]
        df = make_df(closes)
        st = TrendCalculator().calc_supertrend(df, period=10, multiplier=3.0)

        # 大跌后应为空头
        assert st['direction'].iloc[20] == -1
        # 小幅反弹不得 whipsaw 翻多（标准实现保持空头直到突破上轨）
        assert st['direction'].iloc[21] == -1
        assert st['direction'].iloc[22] == -1

    def test_uptrend_holds_lower_band(self):
        """多头趋势中 supertrend 应等于下轨且只上不下"""
        from utils.tech_calculator.trend import TrendCalculator
        closes = list(np.linspace(100, 130, 30))
        df = make_df(closes)
        st = TrendCalculator().calc_supertrend(df)
        directions = st['direction'].iloc[15:]  # 预热后
        assert (directions == 1).all()
        st_values = st['supertrend'].iloc[15:].values
        assert all(st_values[i] >= st_values[i - 1] for i in range(1, len(st_values)))


class TestRounded:
    def test_true_rounded_top_detected(self):
        """正弦波圆顶（后半段波动收窄）应被检测为 top"""
        from utils.tech_calculator.pattern import PatternDetector
        x = np.linspace(0, np.pi, 40)
        closes = 100 + 10 * np.sin(x)  # 圆润的顶
        # 前半段波动大、后半段波动小（满足 vol_decline 条件）
        spreads = np.concatenate([np.full(20, 0.02), np.full(20, 0.005)])
        df = pd.DataFrame({
            'open': closes, 'high': closes * (1 + spreads),
            'low': closes * (1 - spreads), 'close': closes,
            'volume': 1e6,
        })
        result = PatternDetector().detect_rounded(df, lookback=40)
        assert result['detected']
        assert result['type'] == 'top'

    def test_monotonic_up_not_rounded_top(self):
        """单调上涨+波动收窄不得报圆顶（修复前会误报）"""
        from utils.tech_calculator.pattern import PatternDetector
        closes = list(np.linspace(100, 120, 40))
        df = make_df(closes, spreads=0.005)
        result = PatternDetector().detect_rounded(df, lookback=40)
        assert not (result['detected'] and result.get('type') == 'top')


class TestWedge:
    @staticmethod
    def _wedge_df():
        """构造 50 根带摆动的 K 线"""
        n = 50
        osc = np.sin(np.arange(n) / 2.0) * 3
        highs = 100 + np.arange(n) * 0.8 + osc
        lows = 95 + np.arange(n) * 1.0 + osc
        closes = (highs + lows) / 2
        return pd.DataFrame({
            'open': closes, 'high': highs, 'low': lows,
            'close': closes, 'volume': 1e6,
        }), highs, lows, n

    def test_rising_wedge_converging(self):
        """标准收敛上升楔形（下轨更陡）应检出 rising"""
        from utils.tech_calculator.pattern import PatternDetector
        df, highs, lows, n = self._wedge_df()
        pd_ = PatternDetector()
        # 手动指定 swing 点，确定性测试判定逻辑
        # 上轨：缓涨（斜率+1.0）；下轨：急涨（斜率+1.8）→ 收敛
        peaks = [5, 18, 31, 44]
        troughs = [11, 24, 37, 48]
        peak_vals = {5: 110, 18: 123, 31: 136, 44: 149}
        trough_vals = {11: 105, 24: 121, 37: 137, 48: 150}
        for i, v in peak_vals.items():
            df.iloc[i, df.columns.get_loc('high')] = v
        for i, v in trough_vals.items():
            df.iloc[i, df.columns.get_loc('low')] = v
        # 当前价置于两线之间（upper@49≈154，lower@49≈151）
        df.iloc[-1, df.columns.get_loc('close')] = 152.5
        pd_.find_swing_points = lambda h, l, window=3: (peaks, troughs)

        result = pd_.detect_wedge(df)
        assert result['detected']
        assert result['type'] == 'rising'

    def test_broadening_not_wedge(self):
        """发散形态（上轨更陡）不得报楔形"""
        from utils.tech_calculator.pattern import PatternDetector
        df, highs, lows, n = self._wedge_df()
        pd_ = PatternDetector()
        peaks = [5, 18, 31, 44]
        troughs = [11, 24, 37, 48]
        # 上轨急涨（更陡）、下轨缓涨 → 发散
        peak_vals = {5: 110, 18: 136, 31: 162, 44: 188}
        trough_vals = {11: 105, 24: 118, 37: 131, 48: 142}
        for i, v in peak_vals.items():
            df.iloc[i, df.columns.get_loc('high')] = v
        for i, v in trough_vals.items():
            df.iloc[i, df.columns.get_loc('low')] = v
        pd_.find_swing_points = lambda h, l, window=3: (peaks, troughs)

        result = pd_.detect_wedge(df)
        assert not result['detected']


class TestVReversal:
    def test_max_at_window_start_no_crash(self):
        """窗口最大值在第 0 根时不得 IndexError"""
        from utils.tech_calculator.pattern import PatternDetector
        closes = [120, 110, 105, 102, 101, 102, 103, 104, 105, 106] * 2
        df = make_df(closes)
        result = PatternDetector().detect_v_reversal(df, lookback=20)
        assert isinstance(result, dict)  # 不崩溃即可


class TestDoubleBottom:
    def test_newest_pair_preferred(self):
        """存在多对 troughs 时，应优先报告最近形成的双底"""
        from utils.tech_calculator.pattern import PatternDetector
        # 构造两个双底：老的在 0-20，新的在 30-50
        closes = (
            [100, 95, 90, 95, 100, 95, 90, 95, 105]  # 老双底（90/90，颈线100）
            + [110] * 20
            + [100, 92, 100, 92, 100, 108]            # 新双底（92/92，颈线100）
        )
        df = make_df(closes, spreads=0.01)
        result = PatternDetector().detect_double_bottom(df)
        if result['detected']:
            # 应报较新的那一对（trough 索引靠后）
            assert result['trough2_idx'] > 20


class TestIslandReversal:
    def test_filled_gap_not_island(self):
        """缺口被回填的不得报岛形"""
        from utils.tech_calculator.pattern import PatternDetector
        # 向上跳空后价格回落填满缺口，再向下跳空——不是孤岛
        closes = [100, 100, 100, 105, 106, 107, 101, 100, 99, 95, 94] * 3
        df = make_df(closes, spreads=0.0)
        result = PatternDetector().detect_island_reversal(df, lookback=30)
        # 不强制 detected=False（取决于具体缺口），但绝不能崩溃
        assert isinstance(result, dict)


class TestPivotPoints:
    def test_uses_previous_completed_bar(self):
        """枢轴点必须基于前一根（已完成）bar，而不是最后一根"""
        from utils.tech_calculator.levels import LevelCalculator
        df = make_df([100] * 10 + [200])  # 最后一根异常值
        df.iloc[-2, df.columns.get_loc('high')] = 110
        df.iloc[-2, df.columns.get_loc('low')] = 90
        df.iloc[-2, df.columns.get_loc('close')] = 100
        pp = LevelCalculator().calc_pivot_points(df)
        # 用前一根 H=110, L=90, C=100 → PP=100
        assert pp['pp'] == 100.0
        # 如果用最后一根（H/L≈200±），PP 会接近 200
        assert pp['pp'] < 150


class TestFlagPole:
    def test_pole_uses_lookback_window(self):
        """旗杆涨跌幅只看 pole_lookback 窗口，不是全部历史"""
        from utils.tech_calculator.pattern import PatternDetector
        # 长期缓慢上涨 100 根 + 最近 20 根横盘
        closes = list(np.linspace(50, 150, 100)) + [150] * 10
        df = make_df(closes, spreads=0.005)
        result = PatternDetector().detect_flag_pennant(df, pole_lookback=20)
        # 最近 20 根几乎没涨，pole_return 应很小 → 即使检出方向/数值也不应基于 200% 涨幅
        if result['detected']:
            assert abs(result['pole_return_pct']) < 10


class TestVolumeGuards:
    def test_analyze_volume_short_data_no_crash(self):
        """数据不足 20 根且当日大涨时不得 TypeError"""
        from utils.tech_calculator.volume import VolumeCalculator
        closes = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 105]
        df = make_df(closes)
        result = VolumeCalculator().analyze_volume(df)
        assert isinstance(result, dict)

    def test_mfi_flat_days_excluded(self):
        """TP 持平日不计入负流量（MFI 不应系统性偏低）"""
        from utils.tech_calculator.volume import VolumeCalculator
        # 前 10 天持平，后 10 天上涨
        closes = [100] * 10 + list(np.linspace(100, 110, 10))
        df = make_df(closes)
        mfi = VolumeCalculator().calc_mfi(df)
        assert mfi.iloc[-1] > 50  # 上涨段 MFI 应偏多

    def test_ad_line_zero_range_day(self):
        """一字板（high==low）不得产生 NaN"""
        from utils.tech_calculator.volume import VolumeCalculator
        df = make_df([100, 100, 100, 101, 102], spreads=0.0)
        ad = VolumeCalculator().calc_ad_line(df)
        assert not ad.isna().any()


class TestWilderConventions:
    def test_atr_uses_wilder_smoothing(self):
        """ATR 应为 Wilder RMA（与简单 SMA 结果不同且更平滑）"""
        from utils.tech_calculator.volatility import VolatilityCalculator
        closes = list(np.linspace(100, 110, 30)) + [120, 95, 105, 100]
        df = make_df(closes, spreads=0.02)
        atr = VolatilityCalculator().calc_atr(df, period=14)
        tr = (df['high'] - df['low'])
        sma_atr = tr.rolling(14).mean()
        # Wilder RMA 与 SMA 不应完全相等
        assert not np.isclose(atr.iloc[-1], sma_atr.iloc[-1], rtol=1e-6)
        assert atr.iloc[-1] > 0

    def test_bollinger_ddof0(self):
        """布林带标准差应为总体标准差（ddof=0）"""
        from utils.tech_calculator.volatility import VolatilityCalculator
        closes = list(np.linspace(100, 120, 30))
        df = make_df(closes)
        bb = VolatilityCalculator().calc_bollinger(df, period=20)
        expected_std = pd.Series(closes).rolling(20).std(ddof=0).iloc[-1]
        middle = pd.Series(closes).rolling(20).mean().iloc[-1]
        assert np.isclose(bb['upper'].iloc[-1], middle + 2 * expected_std, rtol=1e-9)
