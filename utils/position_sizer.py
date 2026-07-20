"""Position Sizer - 仓位计算器

提供多种仓位计算策略：
1. 固定风险法（默认）：基于止损距离计算仓位
2. 波动率调整法：高波动时自动减小仓位
3. Kelly公式（高级）：基于历史胜率和盈亏比
4. 置信度调整法：根据预测置信度调整风险敞口
"""

import math
from typing import Dict, Optional


class PositionSizer:
    """仓位计算器 - 多种策略可选"""

    # 默认参数
    DEFAULT_RISK_PCT = 2.0  # 单笔风险占总资金2%
    DEFAULT_MAX_POSITION_PCT = 10.0  # 单标的最大仓位10%
    DEFAULT_MIN_SHARES = 1  # 默认最小交易单位（美股等），A股调用时传入100

    @staticmethod
    def fixed_risk(capital: float, risk_pct: float, entry: float,
                   stop: float, max_position_pct: float = 10.0,
                   min_lot_size: int = 1) -> Dict:
        """固定风险法（默认策略）

        公式: risk_amount = capital * risk_pct
              risk_per_share = |entry - stop|
              shares = risk_amount / risk_per_share

        Args:
            capital: 总资金
            risk_pct: 单笔风险百分比（如2.0表示2%）
            entry: 入场价格
            stop: 止损价格
            max_position_pct: 单标的最大仓位百分比

        Returns:
            {
                'shares': 股数,
                'notional': 名义金额,
                'position_pct': 仓位占比,
                'risk_amount': 风险金额,
                'risk_per_share': 每股风险,
                'strategy': 'fixed_risk'
            }
        """
        if capital <= 0 or entry <= 0 or risk_pct <= 0:
            return {'error': 'Invalid input parameters'}

        risk_amount = capital * (risk_pct / 100.0)
        risk_per_share = abs(entry - stop)

        if risk_per_share <= 0:
            return {'error': 'Stop loss must differ from entry price'}

        shares = int(risk_amount / risk_per_share)

        # 确保至少最小交易单位
        if shares < min_lot_size:
            shares = min_lot_size

        notional = shares * entry
        position_pct = (notional / capital) * 100

        # 限制最大仓位
        max_notional = capital * (max_position_pct / 100.0)
        if notional > max_notional:
            shares = int(max_notional / entry)
            # 调整为最小交易单位的整数倍
            shares = (shares // min_lot_size) * min_lot_size
            if shares < min_lot_size:
                shares = min_lot_size
            notional = shares * entry
            position_pct = (notional / capital) * 100
            risk_amount = shares * risk_per_share

        return {
            'shares': shares,
            'notional': round(notional, 2),
            'position_pct': round(position_pct, 2),
            'risk_amount': round(risk_amount, 2),
            'risk_per_share': round(risk_per_share, 4),
            'risk_pct': round((risk_amount / capital) * 100, 2),
            'strategy': 'fixed_risk',
        }

    @staticmethod
    def volatility_adjusted(capital: float, risk_pct: float, entry: float,
                            atr: float, atr_multiplier: float = 2.0,
                            max_position_pct: float = 10.0,
                            min_lot_size: int = 1) -> Dict:
        """波动率调整法

        高ATR时自动减小仓位，低ATR时可适当增加。
        止损 = entry - atr * atr_multiplier

        Args:
            capital: 总资金
            risk_pct: 基础风险百分比
            entry: 入场价格
            atr: ATR值
            atr_multiplier: ATR倍数（默认2.0）
            max_position_pct: 单标的最大仓位百分比
        """
        if atr <= 0:
            return {'error': 'ATR must be positive'}

        stop = entry - atr * atr_multiplier
        result = PositionSizer.fixed_risk(capital, risk_pct, entry, stop,
                                           max_position_pct, min_lot_size=min_lot_size)
        if 'error' not in result:
            result['strategy'] = 'volatility_adjusted'
            result['atr'] = atr
            result['atr_multiplier'] = atr_multiplier
            result['stop_price'] = round(stop, 2)

        return result

    @staticmethod
    def confidence_adjusted(base_risk_pct: float,
                            confidence: float) -> float:
        """置信度调整

        根据预测置信度调整风险敞口：
        - confidence > 80: risk * 1.5（高置信度，允许更大仓位）
        - confidence 50-80: risk * 1.0（正常仓位）
        - confidence < 50: risk * 0.5（低置信度，减小仓位）

        Returns:
            调整后的风险百分比
        """
        if confidence >= 80:
            multiplier = 1.5
        elif confidence >= 50:
            multiplier = 1.0
        else:
            multiplier = 0.5

        return base_risk_pct * multiplier

    @staticmethod
    def kelly_criterion(win_rate: float, avg_win_pct: float,
                        avg_loss_pct: float) -> Dict:
        """Kelly公式（高级仓位管理）

        f* = (p * b - q) / b
        其中:
        - p = 胜率
        - q = 败率 = 1 - p
        - b = 平均盈利 / 平均亏损 (盈亏比)

        实际使用中通常用 "Half Kelly" 或 "Quarter Kelly" 来降低风险。

        Args:
            win_rate: 胜率（0-1）
            avg_win_pct: 平均盈利百分比
            avg_loss_pct: 平均亏损百分比（正数）

        Returns:
            {
                'kelly_fraction': Kelly最优仓位比例,
                'half_kelly': 半Kelly,
                'quarter_kelly': 四分之一Kelly,
                'recommended': 推荐使用的比例
            }
        """
        if win_rate <= 0 or avg_loss_pct <= 0:
            return {'error': 'Invalid parameters'}

        b = avg_win_pct / avg_loss_pct  # 盈亏比
        q = 1 - win_rate

        if b <= 0:
            return {'error': 'Win/loss ratio must be positive'}

        kelly = (win_rate * b - q) / b

        # Kelly可能为负（期望为负时不应交易）
        half_kelly = kelly / 2
        quarter_kelly = kelly / 4

        # 推荐：使用Quarter Kelly，且不超过20%
        recommended = min(quarter_kelly, 0.20)
        recommended = max(0, recommended)

        return {
            'kelly_fraction': round(kelly, 4),
            'half_kelly': round(half_kelly, 4),
            'quarter_kelly': round(quarter_kelly, 4),
            'recommended': round(recommended, 4),
            'win_rate': win_rate,
            'win_loss_ratio': round(b, 2),
        }

    @staticmethod
    def calculate_position(analysis: Dict, features: Dict,
                           capital: float = 1_000_000,
                           symbol: str = '',
                           market: str = '') -> Dict:
        """综合仓位计算（自动选择最优策略）

        策略选择逻辑：
        1. 如果有历史胜率数据，用Kelly公式作为参考
        2. 如果有ATR数据，用波动率调整法
        3. 否则用固定风险法
        4. 所有策略都会应用置信度调整

        Args:
            analysis: 分析结果（含confidence, target, stop等）
            features: FeatureExtractor输出的指标
            capital: 总资金

        Returns:
            完整仓位计算结果
        """
        p4 = analysis.get('phase4_conclusion', {})
        confidence = p4.get('confidence', 50)
        entry = p4.get('key_levels', {}).get('trigger', 0)
        stop = p4.get('key_levels', {}).get('stop_loss', 0)
        target = p4.get('key_levels', {}).get('target', 0)

        if entry <= 0:
            return {'error': 'Invalid entry price'}

        # 根据市场确定最小交易单位
        min_lot_size = 1
        if market == 'cn' or (symbol and (symbol.endswith('.SH') or symbol.endswith('.SZ') or
                                          (symbol.isdigit() and len(symbol) == 6))):
            min_lot_size = 100

        # 1. 置信度调整基础风险
        base_risk = PositionSizer.DEFAULT_RISK_PCT
        adjusted_risk = PositionSizer.confidence_adjusted(base_risk, confidence)

        # 2. 获取ATR
        atr = features.get('volatility', {}).get('atr', {}).get('value', 0)

        # 3. 选择策略
        if atr > 0 and stop > 0:
            # 有ATR和止损价，使用波动率调整法
            # 动态止损优先于固定止损
            atr_mult = 2.0
            trend_stage = features.get('trend_stage', {}).get('stage', '')
            extreme_dev = features.get('trend_stage', {}).get('extreme_deviation', False)
            if trend_stage in ('late', 'fading') and extreme_dev:
                atr_mult = 3.0
            elif trend_stage in ('early', 'middle'):
                atr_mult = 1.5

            result = PositionSizer.volatility_adjusted(
                capital, adjusted_risk, entry, atr, atr_mult,
                min_lot_size=min_lot_size
            )
        elif stop > 0:
            # 只有固定止损
            result = PositionSizer.fixed_risk(
                capital, adjusted_risk, entry, stop,
                min_lot_size=min_lot_size
            )
        else:
            return {'error': 'No stop loss specified'}

        # 4. 添加分析上下文
        if 'error' not in result:
            result['confidence'] = confidence
            result['confidence_adjusted_risk'] = round(adjusted_risk, 2)
            result['entry_price'] = entry
            result['target_price'] = target
            result['capital'] = capital

            # 风险收益比（基于实际使用的止损）
            actual_stop = result.get('stop_price', stop)
            if target > 0 and actual_stop > 0:
                reward = abs(target - entry)
                risk = abs(entry - actual_stop)
                rr = reward / risk if risk > 0 else 0
                result['risk_reward_ratio'] = round(rr, 2)

        return result
