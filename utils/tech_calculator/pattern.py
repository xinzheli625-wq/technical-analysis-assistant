"""Pattern Detection - 形态维度检测

使用数学方法检测经典技术形态：
- 极值点检测（波峰波谷）
- 双底/双顶
- 头肩顶/底
- 三角形（上升/下降/对称）
- 杯柄形态
- 旗形/三角旗
"""

from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

from .registry import IndicatorMeta, IndicatorRegistry


class PatternDetector:
    """形态检测器"""

    def __init__(self):
        self.registry = IndicatorRegistry()
        self._register_builtin()

    def _register_builtin(self):
        indicators = [
            IndicatorMeta('swing_points', '极值点', 'pattern',
                         '检测价格的波峰和波谷',
                         'scipy.signal.argrelextrema',
                         ['high', 'low'], ['peaks', 'troughs'],
                         {'window': 5}, 'builtin', ''),
            IndicatorMeta('double_bottom', '双底', 'pattern',
                         '两个相近低点+中间高点的反转形态',
                         '两个troughs相近 + peak在中间',
                         ['low'], ['detected', 'confidence'],
                         {}, 'builtin', ''),
            IndicatorMeta('head_shoulders', '头肩顶', 'pattern',
                         '三个峰，中间最高的反转形态',
                         'peak1 < peak2 > peak3, shoulders similar',
                         ['high'], ['detected', 'confidence'],
                         {}, 'builtin', ''),
            IndicatorMeta('triangle', '三角形', 'pattern',
                         '收敛的上下轨',
                         '趋势线收敛',
                         ['high', 'low'], ['detected', 'type', 'confidence'],
                         {}, 'builtin', ''),
            IndicatorMeta('cup_handle', '杯柄形态', 'pattern',
                         'U型底部+右侧小幅回调的延续形态',
                         'U型底部 + 右侧高点 + 柄部回调',
                         ['close'], ['detected', 'confidence', 'handle_depth_pct'],
                         {'cup_lookback': 60}, 'builtin', ''),
            IndicatorMeta('wedge', '楔形', 'pattern',
                         '同向收敛的趋势线',
                         '上下轨同向收敛',
                         ['high', 'low', 'close'], ['detected', 'type', 'confidence'],
                         {}, 'builtin', ''),
            IndicatorMeta('flag_pennant', '旗形三角旗', 'pattern',
                         '快速运动后的小幅整理',
                         '旗杆 + 旗面(小幅回调/收敛)',
                         ['close', 'high', 'low'], ['detected', 'type', 'confidence', 'direction'],
                         {'pole_lookback': 20}, 'builtin', ''),
            IndicatorMeta('channel', '通道', 'pattern',
                         '平行的上下轨形成的趋势通道',
                         'peaks连线和troughs连线近似平行',
                         ['high', 'low'], ['detected', 'type', 'confidence'],
                         {}, 'builtin', ''),
            IndicatorMeta('rectangle', '矩形', 'pattern',
                         '价格在水平支撑和阻力之间震荡',
                         '多个peaks在同一水平，多个troughs在同一水平',
                         ['high', 'low'], ['detected', 'confidence'],
                         {}, 'builtin', ''),
            IndicatorMeta('rounded', '圆弧', 'pattern',
                         '缓慢 rounded 的顶部或底部',
                         '价格缓慢改变方向，波动率逐渐下降',
                         ['close'], ['detected', 'type', 'confidence'],
                         {}, 'builtin', ''),
            IndicatorMeta('v_reversal', 'V形反转', 'pattern',
                         '快速反向运动形成V字',
                         '急剧下跌后急剧上涨（或相反）',
                         ['close'], ['detected', 'type', 'confidence'],
                         {}, 'builtin', ''),
            IndicatorMeta('island_reversal', '岛形反转', 'pattern',
                         '跳空缺口后反向跳空',
                         '向上跳空+小幅整理+向下跳空（或相反）',
                         ['high', 'low', 'close'], ['detected', 'type', 'confidence'],
                         {}, 'builtin', ''),
            IndicatorMeta('gaps', '缺口', 'pattern',
                         '价格跳空缺口分析',
                         '识别普通/突破/持续/衰竭缺口',
                         ['high', 'low', 'close'], ['gaps', 'breakaway', 'runaway', 'exhaustion'],
                         {}, 'builtin', ''),
        ]
        for meta in indicators:
            calc_fn = getattr(self, f'detect_{meta.name}', None)
            if calc_fn:
                self.registry.register(meta, calc_fn)

    def find_swing_points(self, highs: pd.Series, lows: pd.Series, window: int = 5) -> Tuple[List[int], List[int]]:
        """找极值点

        Returns:
            (peaks_indices, troughs_indices)
        """
        peaks = argrelextrema(highs.values, np.greater, order=window)[0]
        troughs = argrelextrema(lows.values, np.less, order=window)[0]
        return list(peaks), list(troughs)

    def detect_double_bottom(self, df: pd.DataFrame, tolerance: float = 0.03) -> Dict[str, Any]:
        """检测双底形态

        条件：
        1. 两个troughs价格相近（在tolerance范围内）
        2. 中间有一个明显的peak
        3. 第二个trough后价格突破中间peak
        """
        highs = df['high']
        lows = df['low']
        closes = df['close']

        peaks, troughs = self.find_swing_points(highs, lows)

        if len(troughs) < 2:
            return {'detected': False, 'confidence': 0}

        # 检查最近的troughs对
        for i in range(len(troughs) - 1):
            t1 = troughs[i]
            t2 = troughs[i + 1]

            # 找中间的peaks
            mid_peaks = [p for p in peaks if t1 < p < t2]
            if not mid_peaks:
                continue

            low1 = lows.iloc[t1]
            low2 = lows.iloc[t2]
            mid_high = max(highs.iloc[p] for p in mid_peaks)

            # 检查两个低点是否相近
            price_diff = abs(low1 - low2) / ((low1 + low2) / 2)
            if price_diff > tolerance:
                continue

            # 检查是否突破颈线
            if len(closes) > t2 + 1:
                recent_close = closes.iloc[-1]
                if recent_close > mid_high:
                    return {
                        'detected': True,
                        'confidence': round((1 - price_diff) * 100),
                        'trough1_idx': int(t1),
                        'trough2_idx': int(t2),
                        'neckline': round(mid_high, 2),
                        'low1': round(low1, 2),
                        'low2': round(low2, 2)
                    }

        return {'detected': False, 'confidence': 0}

    def detect_head_shoulders(self, df: pd.DataFrame, tolerance: float = 0.05) -> Dict[str, Any]:
        """检测头肩顶形态

        条件：
        1. 三个peaks，中间最高（head）
        2. 左右肩高度相近
        3. 价格跌破颈线（左右肩之间的 lows）
        """
        highs = df['high']
        lows = df['low']
        closes = df['close']

        peaks, troughs = self.find_swing_points(highs, lows, window=5)

        if len(peaks) < 3:
            return {'detected': False, 'confidence': 0}

        # 检查连续三个peaks
        for i in range(len(peaks) - 2):
            p1, p2, p3 = peaks[i], peaks[i+1], peaks[i+2]

            h1, h2, h3 = highs.iloc[p1], highs.iloc[p2], highs.iloc[p3]

            # 中间最高
            if not (h1 < h2 and h3 < h2):
                continue

            # 左右肩相近
            shoulder_diff = abs(h1 - h3) / ((h1 + h3) / 2)
            if shoulder_diff > tolerance:
                continue

            # 找颈线（两个troughs在peaks之间）
            neck_troughs = [t for t in troughs if p1 < t < p3]
            if len(neck_troughs) < 2:
                continue

            neckline = max(lows.iloc[t] for t in neck_troughs)

            # 检查是否跌破颈线
            if closes.iloc[-1] < neckline:
                return {
                    'detected': True,
                    'confidence': round((1 - shoulder_diff) * 100),
                    'left_shoulder_idx': int(p1),
                    'head_idx': int(p2),
                    'right_shoulder_idx': int(p3),
                    'neckline': round(neckline, 2),
                    'target': round(neckline - (h2 - neckline), 2)  # 等幅测量
                }

        return {'detected': False, 'confidence': 0}

    def detect_triangle(self, df: pd.DataFrame, min_touches: int = 3) -> Dict[str, Any]:
        """检测三角形形态

        条件：
        1. 上轨（peaks连线）下降或水平
        2. 下轨（troughs连线）上升或水平
        3. 收敛
        """
        highs = df['high']
        lows = df['low']

        peaks, troughs = self.find_swing_points(highs, lows, window=3)

        if len(peaks) < min_touches or len(troughs) < min_touches:
            return {'detected': False, 'confidence': 0}

        # 取最近几个极值点拟合趋势线
        recent_peaks = peaks[-min_touches:]
        recent_troughs = troughs[-min_touches:]

        # 上轨斜率
        upper_x = np.array(recent_peaks)
        upper_y = np.array([highs.iloc[p] for p in recent_peaks])
        upper_slope = np.polyfit(upper_x, upper_y, 1)[0]

        # 下轨斜率
        lower_x = np.array(recent_troughs)
        lower_y = np.array([lows.iloc[t] for t in recent_troughs])
        lower_slope = np.polyfit(lower_x, lower_y, 1)[0]

        # 判断类型
        triangle_type = None
        if upper_slope < -0.001 and lower_slope > 0.001:
            triangle_type = 'symmetrical'
        elif abs(upper_slope) < 0.001 and lower_slope > 0.001:
            triangle_type = 'ascending'
        elif upper_slope < -0.001 and abs(lower_slope) < 0.001:
            triangle_type = 'descending'

        if triangle_type:
            # 计算收敛程度
            upper_end = np.polyval(np.polyfit(upper_x, upper_y, 1), len(highs)-1)
            lower_end = np.polyval(np.polyfit(lower_x, lower_y, 1), len(highs)-1)
            convergence = (upper_end - lower_end) / highs.mean()

            return {
                'detected': True,
                'type': triangle_type,
                'confidence': min(95, int(100 - convergence * 1000)),
                'upper_slope': round(upper_slope, 4),
                'lower_slope': round(lower_slope, 4),
                'apex_estimate': int(len(highs) + (upper_end - lower_end) / abs(upper_slope - lower_slope)) if abs(upper_slope - lower_slope) > 0.001 else None
            }

        return {'detected': False, 'confidence': 0}

    def detect_cup_handle(self, df: pd.DataFrame, cup_lookback: int = 60,
                          tolerance: float = 0.05) -> Dict[str, Any]:
        """检测杯柄形态

        条件：
        1. 之前有明显上升趋势
        2. U型底部（圆润，不是V型）
        3. 右侧回升到接近左侧高点
        4. 在右侧高点附近有小幅回调（柄部）
        """
        if len(df) < cup_lookback:
            return {'detected': False, 'confidence': 0}

        recent = df.tail(cup_lookback)
        closes = recent['close']

        # 找杯部左右高点
        left_high_idx = closes.head(int(cup_lookback * 0.25)).idxmax()
        left_high = closes.loc[left_high_idx]

        # 找杯底（U型底部应该在中间区域）
        middle_start = int(cup_lookback * 0.3)
        middle_end = int(cup_lookback * 0.7)
        cup_bottom = closes.iloc[middle_start:middle_end].min()
        cup_bottom_idx = closes.iloc[middle_start:middle_end].idxmin()

        # 找右侧高点
        right_start = closes.index.get_loc(cup_bottom_idx)
        right_high = closes.iloc[right_start:].max()

        # 检查U型（底部圆润，不是尖锐V型）
        bottom_region = closes.iloc[middle_start:middle_end]
        bottom_smoothness = self._check_smoothness(bottom_region)

        # 右侧是否接近左侧高点
        right_match = abs(right_high - left_high) / left_high < tolerance

        # 找柄部（右侧高点后的小幅回调）
        right_high_idx = closes.iloc[right_start:].idxmax()
        handle_start = closes.index.get_loc(right_high_idx)
        if handle_start < len(closes) - 5:
            handle = closes.iloc[handle_start:]
            handle_low = handle.min()
            handle_depth = (right_high - handle_low) / right_high

            # 柄部深度应在8%-15%之间
            valid_handle = 0.08 < handle_depth < 0.15
        else:
            valid_handle = False

        if right_match and bottom_smoothness and valid_handle:
            return {
                'detected': True,
                'confidence': min(90, int(bottom_smoothness * 50 + right_match * 40)),
                'left_high': round(left_high, 2),
                'cup_bottom': round(cup_bottom, 2),
                'right_high': round(right_high, 2),
                'handle_depth_pct': round(handle_depth * 100, 1)
            }

        return {'detected': False, 'confidence': 0}

    def _check_smoothness(self, series: pd.Series) -> float:
        """检查序列的平滑度（用于判断U型底 vs V型底）"""
        if len(series) < 5:
            return 0
        second_deriv = series.diff().diff()
        # 二阶导数变化小 = 平滑
        smoothness = 1 - min(1, second_deriv.std() / (series.std() + 1e-6))
        return max(0, smoothness)

    def detect_channel(self, df: pd.DataFrame, min_touches: int = 3) -> Dict[str, Any]:
        """检测通道形态（上升通道/下降通道）

        条件：
        1. 上轨（peaks连线）和下轨（troughs连线）近似平行
        2. 价格在通道内运行
        3. 至少3个触点
        """
        highs = df['high']
        lows = df['low']
        closes = df['close']

        peaks, troughs = self.find_swing_points(highs, lows, window=3)

        if len(peaks) < min_touches or len(troughs) < min_touches:
            return {'detected': False, 'confidence': 0}

        recent_peaks = peaks[-min_touches:]
        recent_troughs = troughs[-min_touches:]

        upper_x = np.array(recent_peaks)
        upper_y = np.array([highs.iloc[p] for p in recent_peaks])
        upper_slope = np.polyfit(upper_x, upper_y, 1)[0]

        lower_x = np.array(recent_troughs)
        lower_y = np.array([lows.iloc[t] for t in recent_troughs])
        lower_slope = np.polyfit(lower_x, lower_y, 1)[0]

        # 检查是否平行（斜率相近且不为0）
        slope_diff = abs(upper_slope - lower_slope)
        parallel = slope_diff < abs(upper_slope) * 0.3 + 0.0001 and abs(upper_slope) > 0.0001

        if parallel:
            # 判断类型
            if upper_slope > 0.001:
                channel_type = 'ascending'  # 上升通道
            elif upper_slope < -0.001:
                channel_type = 'descending'  # 下降通道
            else:
                return {'detected': False, 'confidence': 0}

            # 检查当前价格是否在通道内
            upper_line = np.polyfit(upper_x, upper_y, 1)
            lower_line = np.polyfit(lower_x, lower_y, 1)

            current_upper = np.polyval(upper_line, len(highs) - 1)
            current_lower = np.polyval(lower_line, len(highs) - 1)
            current_price = closes.iloc[-1]

            in_channel = current_lower * 0.98 < current_price < current_upper * 1.02

            if in_channel:
                channel_width = (current_upper - current_lower) / closes.mean()
                return {
                    'detected': True,
                    'type': channel_type,
                    'confidence': min(90, int(60 + (1 - slope_diff / (abs(upper_slope) + 0.0001)) * 30)),
                    'upper_slope': round(upper_slope, 4),
                    'lower_slope': round(lower_slope, 4),
                    'channel_width_pct': round(channel_width * 100, 2),
                }

        return {'detected': False, 'confidence': 0}

    def detect_rectangle(self, df: pd.DataFrame, min_touches: int = 3) -> Dict[str, Any]:
        """检测矩形整理形态

        条件：
        1. 多个peaks在同一水平（阻力）
        2. 多个troughs在同一水平（支撑）
        3. 价格在区间内震荡至少20天
        """
        highs = df['high']
        lows = df['low']
        closes = df['close']

        if len(df) < 20:
            return {'detected': False, 'confidence': 0}

        peaks, troughs = self.find_swing_points(highs, lows, window=3)

        if len(peaks) < min_touches or len(troughs) < min_touches:
            return {'detected': False, 'confidence': 0}

        # 取最近的极值点
        recent_peaks = peaks[-min_touches:]
        recent_troughs = troughs[-min_touches:]

        peak_vals = [highs.iloc[p] for p in recent_peaks]
        trough_vals = [lows.iloc[t] for t in recent_troughs]

        # 检查是否在同一水平（变异系数小）
        peak_cv = np.std(peak_vals) / (np.mean(peak_vals) + 1e-6)
        trough_cv = np.std(trough_vals) / (np.mean(trough_vals) + 1e-6)

        flat_peaks = peak_cv < 0.03
        flat_troughs = trough_cv < 0.03

        if flat_peaks and flat_troughs:
            resistance = np.mean(peak_vals)
            support = np.mean(trough_vals)
            range_pct = (resistance - support) / closes.mean() * 100

            # 矩形宽度应在 5%-15% 之间
            if 5 < range_pct < 15:
                # 检查价格是否在区间内
                in_range = support * 0.98 < closes.iloc[-1] < resistance * 1.02
                if in_range:
                    return {
                        'detected': True,
                        'confidence': min(85, int(50 + (1 - (peak_cv + trough_cv) / 0.06) * 35)),
                        'support': round(support, 2),
                        'resistance': round(resistance, 2),
                        'range_pct': round(range_pct, 2),
                    }

        return {'detected': False, 'confidence': 0}

    def detect_rounded(self, df: pd.DataFrame, lookback: int = 40) -> Dict[str, Any]:
        """检测圆弧顶/圆弧底形态

        条件：
        1. 价格缓慢改变方向
        2. 波动率逐渐下降（波动收窄）
        3. 形成 rounded 形状（不是尖锐的V）
        """
        if len(df) < lookback:
            return {'detected': False, 'confidence': 0}

        recent = df.tail(lookback)
        closes = recent['close']
        highs = recent['high']
        lows = recent['low']

        # 找前半段和后半段的极值
        half = lookback // 2
        first_half = closes.iloc[:half]
        second_half = closes.iloc[half:]

        # 检查是否形成圆顶（前半段涨，后半段跌）
        rounded_top = first_half.max() > first_half.iloc[0] and second_half.min() < second_half.iloc[-1]
        # 检查是否形成圆底（前半段跌，后半段涨）
        rounded_bottom = first_half.min() < first_half.iloc[0] and second_half.max() > second_half.iloc[-1]

        if not (rounded_top or rounded_bottom):
            return {'detected': False, 'confidence': 0}

        # 检查平滑度（波动率下降）
        ranges = highs - lows
        first_vol = ranges.iloc[:half].mean()
        second_vol = ranges.iloc[half:].mean()
        vol_decline = first_vol > second_vol * 1.2

        # 检查 rounded 形状（二阶导数变化小）
        smoothness = self._check_smoothness(closes)

        if vol_decline and smoothness > 0.5:
            rounded_type = 'top' if rounded_top else 'bottom'
            return {
                'detected': True,
                'type': rounded_type,
                'confidence': min(85, int(40 + smoothness * 30 + (first_vol / (second_vol + 1e-6) - 1) * 20)),
                'vol_decline_pct': round((first_vol - second_vol) / first_vol * 100, 1),
            }

        return {'detected': False, 'confidence': 0}

    def detect_v_reversal(self, df: pd.DataFrame, lookback: int = 20) -> Dict[str, Any]:
        """检测V形反转形态

        条件：
        1. 快速单边运动（至少10%）
        2. 极值点后快速反向运动（至少7%）
        3. 整个周期短（lookback期内完成）
        """
        if len(df) < lookback:
            return {'detected': False, 'confidence': 0}

        recent = df.tail(lookback)
        closes = recent['close']

        # V底：急跌后急涨
        # 找最低点
        min_idx = closes.idxmin()
        min_price = closes.min()
        min_loc = closes.index.get_loc(min_idx)

        if min_loc < 3 or min_loc > len(closes) - 3:
            return {'detected': False, 'confidence': 0}

        # 下跌段
        before_min = closes.iloc[:min_loc]
        drop_pct = (before_min.iloc[0] - min_price) / before_min.iloc[0] * 100

        # 上涨段
        after_min = closes.iloc[min_loc:]
        rebound_pct = (after_min.iloc[-1] - min_price) / min_price * 100

        # V顶：急涨后急跌
        max_idx = closes.idxmax()
        max_price = closes.max()
        max_loc = closes.index.get_loc(max_idx)

        before_max = closes.iloc[:max_loc]
        rise_pct = (max_price - before_max.iloc[0]) / before_max.iloc[0] * 100

        after_max = closes.iloc[max_loc:]
        drop_back_pct = (max_price - after_max.iloc[-1]) / max_price * 100

        # 判断V底
        if drop_pct > 10 and rebound_pct > 7 and min_loc >= len(closes) * 0.3:
            return {
                'detected': True,
                'type': 'bottom',
                'confidence': min(90, int(50 + drop_pct * 2 + rebound_pct)),
                'drop_pct': round(drop_pct, 1),
                'rebound_pct': round(rebound_pct, 1),
            }

        # 判断V顶
        if rise_pct > 10 and drop_back_pct > 7 and max_loc >= len(closes) * 0.3:
            return {
                'detected': True,
                'type': 'top',
                'confidence': min(90, int(50 + rise_pct * 2 + drop_back_pct)),
                'rise_pct': round(rise_pct, 1),
                'drop_back_pct': round(drop_back_pct, 1),
            }

        return {'detected': False, 'confidence': 0}

    def detect_island_reversal(self, df: pd.DataFrame, lookback: int = 30) -> Dict[str, Any]:
        """检测岛形反转形态

        条件：
        1. 存在一个向上的跳空缺口（high[i-1] < low[i]）
        2. 之后几天在这个缺口上方整理
        3. 再之后出现一个向下的跳空缺口（low[j] > high[j-1]）
        4. 两个缺口之间的区域形成"孤岛"
        （或相反顺序：先向下跳空，再向上跳空）
        """
        if len(df) < lookback:
            return {'detected': False, 'confidence': 0}

        recent = df.tail(lookback)
        highs = recent['high'].values
        lows = recent['low'].values
        recent['close'].values

        # 找所有向上跳空（今日最低价 > 昨日最高价）
        up_gaps = []
        for i in range(1, len(recent)):
            if lows[i] > highs[i - 1]:
                gap_size = (lows[i] - highs[i - 1]) / highs[i - 1] * 100
                up_gaps.append((i, gap_size))

        # 找所有向下跳空（今日最高价 < 昨日最低价）
        down_gaps = []
        for i in range(1, len(recent)):
            if highs[i] < lows[i - 1]:
                gap_size = (lows[i - 1] - highs[i]) / highs[i] * 100
                down_gaps.append((i, gap_size))

        # 检查岛形顶：向上跳空 -> 整理 -> 向下跳空
        for up_idx, up_size in up_gaps:
            for down_idx, down_size in down_gaps:
                if down_idx > up_idx + 2 and down_idx < up_idx + 10:  # 间隔2-10天
                    # 检查中间区域是否被孤立（没有价格回填缺口）
                    max(highs[up_idx:down_idx])
                    min(lows[up_idx:down_idx])

                    # 两个缺口之间的区域形成岛
                    if up_size > 2 and down_size > 2:
                        return {
                            'detected': True,
                            'type': 'top',
                            'confidence': min(90, int(50 + up_size * 5 + down_size * 5)),
                            'up_gap_pct': round(up_size, 2),
                            'down_gap_pct': round(down_size, 2),
                            'island_days': down_idx - up_idx,
                        }

        # 检查岛形底：向下跳空 -> 整理 -> 向上跳空
        for down_idx, down_size in down_gaps:
            for up_idx, up_size in up_gaps:
                if up_idx > down_idx + 2 and up_idx < down_idx + 10:
                    if down_size > 2 and up_size > 2:
                        return {
                            'detected': True,
                            'type': 'bottom',
                            'confidence': min(90, int(50 + down_size * 5 + up_size * 5)),
                            'down_gap_pct': round(down_size, 2),
                            'up_gap_pct': round(up_size, 2),
                            'island_days': up_idx - down_idx,
                        }

        return {'detected': False, 'confidence': 0}

    def detect_gaps(self, df: pd.DataFrame, lookback: int = 60) -> Dict[str, Any]:
        """检测和分析缺口

        返回所有缺口及其分类：
        - breakaway: 突破缺口（出现在趋势初期，伴随放量）
        - runaway: 持续/测量缺口（趋势中期的跳空）
        - exhaustion: 衰竭缺口（趋势末期的跳空）
        """
        if len(df) < 10:
            return {'gaps': []}

        recent = df.tail(lookback)
        highs = recent['high'].values
        lows = recent['low'].values
        closes = recent['close'].values
        volumes = recent['volume'].values if 'volume' in recent.columns else None

        gaps = []

        for i in range(1, len(recent)):
            prev_high = highs[i - 1]
            prev_low = lows[i - 1]
            curr_high = highs[i]
            curr_low = lows[i]
            recent['open'].iloc[i] if 'open' in recent.columns else closes[i]

            # 向上跳空：今日最低 > 昨日最高
            if curr_low > prev_high:
                gap_size = (curr_low - prev_high) / prev_high * 100
                gap_type = self._classify_gap(
                    closes, volumes, i, gap_size, 'up',
                    recent['volume'].rolling(20).mean().iloc[i] if volumes is not None else None
                )
                gaps.append({
                    'type': 'up',
                    'gap_pct': round(gap_size, 2),
                    'date_idx': i,
                    'classification': gap_type,
                })

            # 向下跳空：今日最高 < 昨日最低
            elif curr_high < prev_low:
                gap_size = (prev_low - curr_high) / curr_high * 100
                gap_type = self._classify_gap(
                    closes, volumes, i, gap_size, 'down',
                    recent['volume'].rolling(20).mean().iloc[i] if volumes is not None else None
                )
                gaps.append({
                    'type': 'down',
                    'gap_pct': round(gap_size, 2),
                    'date_idx': i,
                    'classification': gap_type,
                })

        # 统计各类缺口
        breakaway = [g for g in gaps if g['classification'] == 'breakaway']
        runaway = [g for g in gaps if g['classification'] == 'runaway']
        exhaustion = [g for g in gaps if g['classification'] == 'exhaustion']
        common = [g for g in gaps if g['classification'] == 'common']

        return {
            'gaps': gaps,
            'breakaway_count': len(breakaway),
            'runaway_count': len(runaway),
            'exhaustion_count': len(exhaustion),
            'common_count': len(common),
            'latest_gap': gaps[-1] if gaps else None,
            'unfilled_gaps': len([g for g in gaps if g['gap_pct'] > 1]),
        }

    def _classify_gap(self, closes: np.ndarray, volumes, idx: int,
                      gap_size: float, direction: str, vol_avg: float) -> str:
        """对缺口进行分类"""
        # 突破缺口：出现在整理结束后，通常较大（>3%），伴随放量
        if gap_size > 3:
            if volumes is not None and vol_avg and volumes[idx] > vol_avg * 1.5:
                return 'breakaway'
            # 趋势中已经有一段运动后出现的跳空
            if idx > 10:
                trend_before = (closes[idx] - closes[max(0, idx - 10)]) / closes[max(0, idx - 10)]
                if abs(trend_before) > 0.05:
                    return 'runaway'
                return 'breakaway'
            return 'breakaway'

        # 衰竭缺口：趋势末期，伴随极端情绪
        if idx > 5:
            recent_trend = (closes[idx] - closes[max(0, idx - 5)]) / closes[max(0, idx - 5)]
            # 如果缺口方向与近期趋势一致，且近期已有较大涨幅
            if (direction == 'up' and recent_trend > 0.1) or (direction == 'down' and recent_trend < -0.1):
                return 'exhaustion'

        return 'common'

    def detect_wedge(self, df: pd.DataFrame, min_touches: int = 3) -> Dict[str, Any]:
        """检测楔形形态（上升楔形/下降楔形）"""
        highs = df['high']
        lows = df['low']
        closes = df['close']

        peaks, troughs = self.find_swing_points(highs, lows, window=3)

        if len(peaks) < min_touches or len(troughs) < min_touches:
            return {'detected': False, 'confidence': 0}

        recent_peaks = peaks[-min_touches:]
        recent_troughs = troughs[-min_touches:]

        # 上轨斜率
        upper_x = np.array(recent_peaks)
        upper_y = np.array([highs.iloc[p] for p in recent_peaks])
        upper_slope = np.polyfit(upper_x, upper_y, 1)[0]

        # 下轨斜率
        lower_x = np.array(recent_troughs)
        lower_y = np.array([lows.iloc[t] for t in recent_troughs])
        lower_slope = np.polyfit(lower_x, lower_y, 1)[0]

        # 楔形：两条线同向收敛
        wedge_type = None
        if upper_slope > 0.001 and lower_slope > 0.001 and upper_slope > lower_slope:
            wedge_type = 'rising'  # 上升楔形（看跌）
        elif upper_slope < -0.001 and lower_slope < -0.001 and upper_slope > lower_slope:
            wedge_type = 'falling'  # 下降楔形（看涨）

        if wedge_type:
            # 确认价格是否在楔形内部
            upper_line = np.polyfit(upper_x, upper_y, 1)
            lower_line = np.polyfit(lower_x, lower_y, 1)

            current_upper = np.polyval(upper_line, len(highs) - 1)
            current_lower = np.polyval(lower_line, len(highs) - 1)
            current_price = closes.iloc[-1]

            in_wedge = current_lower < current_price < current_upper

            if in_wedge:
                return {
                    'detected': True,
                    'type': wedge_type,
                    'confidence': min(85, int(70 + abs(upper_slope - lower_slope) * 1000)),
                    'upper_slope': round(upper_slope, 4),
                    'lower_slope': round(lower_slope, 4)
                }

        return {'detected': False, 'confidence': 0}

    def detect_flag_pennant(self, df: pd.DataFrame,
                            pole_lookback: int = 20) -> Dict[str, Any]:
        """检测旗形/三角旗形态

        条件：
        1. 之前有明显的单方向快速运动（旗杆）
        2. 之后出现小幅回调/整理（旗面）
        3. 旗面沿趋势反方向倾斜（旗形）或收敛（三角旗）
        """
        if len(df) < pole_lookback + 10:
            return {'detected': False, 'confidence': 0}

        closes = df['close']
        df['high']
        df['low']

        # 旗杆：前面一段的涨跌幅
        pole = closes.iloc[:-10]
        pole_return = (pole.iloc[-1] - pole.iloc[0]) / pole.iloc[0]

        # 旗面：最后10根K线
        flag = df.tail(10)
        flag_highs = flag['high']
        flag_lows = flag['low']

        # 旗面范围
        flag_range = (flag_highs.max() - flag_lows.min()) / flag['close'].mean()

        # 旗面应远小于旗杆运动
        pole_range = abs(pole_return)
        small_flag = flag_range < pole_range * 0.5

        # 判断旗面类型
        flag_peaks, flag_troughs = self.find_swing_points(flag_highs, flag_lows, window=2)

        if len(flag_peaks) >= 2 and len(flag_troughs) >= 2:
            # 检查是否收敛（三角旗）
            peak_vals = np.array([flag_highs.iloc[p] for p in flag_peaks])
            trough_vals = np.array([flag_lows.iloc[t] for t in flag_troughs])

            if len(flag_peaks) >= 2 and len(flag_troughs) >= 2:
                peak_slope = np.polyfit(range(len(peak_vals)), peak_vals, 1)[0]
                trough_slope = np.polyfit(range(len(trough_vals)), trough_vals, 1)[0]

                converging = abs(peak_slope - trough_slope) > 0.001

                if small_flag:
                    if converging:
                        pattern_type = 'pennant'
                        confidence = min(80, int(50 + abs(peak_slope - trough_slope) * 500))
                    else:
                        pattern_type = 'flag'
                        confidence = min(75, int(40 + pole_range * 100))

                    return {
                        'detected': True,
                        'type': pattern_type,
                        'confidence': confidence,
                        'pole_return_pct': round(pole_return * 100, 2),
                        'direction': 'bullish' if pole_return > 0 else 'bearish'
                    }

        return {'detected': False, 'confidence': 0}

    def analyze_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """综合形态检测"""
        patterns = []

        db = self.detect_double_bottom(df)
        if db['detected']:
            patterns.append({'name': 'Double Bottom', **db})

        hs = self.detect_head_shoulders(df)
        if hs['detected']:
            patterns.append({'name': 'Head and Shoulders', **hs})

        tri = self.detect_triangle(df)
        if tri['detected']:
            patterns.append({'name': f"{tri['type'].title()} Triangle", **tri})

        ch = self.detect_cup_handle(df)
        if ch['detected']:
            patterns.append({'name': 'Cup and Handle', **ch})

        wedge = self.detect_wedge(df)
        if wedge['detected']:
            patterns.append({'name': f"{wedge['type'].title()} Wedge", **wedge})

        fp = self.detect_flag_pennant(df)
        if fp['detected']:
            patterns.append({'name': f"{fp['type'].title()}", **fp})

        # 新增形态检测
        channel = self.detect_channel(df)
        if channel['detected']:
            patterns.append({'name': f"{channel['type'].title()} Channel", **channel})

        rect = self.detect_rectangle(df)
        if rect['detected']:
            patterns.append({'name': 'Rectangle', **rect})

        rounded = self.detect_rounded(df)
        if rounded['detected']:
            patterns.append({'name': f"Rounded {rounded['type'].title()}", **rounded})

        v_rev = self.detect_v_reversal(df)
        if v_rev['detected']:
            patterns.append({'name': f"V-Reversal {v_rev['type'].title()}", **v_rev})

        island = self.detect_island_reversal(df)
        if island['detected']:
            patterns.append({'name': f"Island Reversal {island['type'].title()}", **island})

        # 支撑阻力
        highs = df['high']
        lows = df['low']
        peaks, troughs = self.find_swing_points(highs, lows)

        support_levels = sorted([round(lows.iloc[t], 2) for t in troughs[-5:]]) if troughs else []
        resistance_levels = sorted([round(highs.iloc[p], 2) for p in peaks[-5:]]) if peaks else []

        # 缺口分析
        gaps = self.detect_gaps(df)

        return {
            'patterns': patterns,
            'pattern_count': len(patterns),
            'support_levels': support_levels[:3],
            'resistance_levels': resistance_levels[:3],
            'swing_points': {'peaks': len(peaks), 'troughs': len(troughs)},
            'gaps': gaps,
        }
