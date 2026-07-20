"""Trade Planner - 交易计划生成器

基于技术分析结果生成具体可执行的交易计划：
1. 仓位计算（基于风险承受度和止损距离）
2. 止损策略选择（固定价格 / ATR倍数 / 吊灯止损）
3. 目标策略（固定目标 / 分批止盈）
4. 风险收益比评估
5. 持有时间预期
"""

import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from utils.position_sizer import PositionSizer


class TradePlanner:
    """交易计划生成器"""

    def __init__(self, capital: float = 1_000_000):
        self.capital = capital
        self.sizer = PositionSizer()

    def create_plan(self, analysis_result: Dict, features: Dict,
                    symbol: str = '', symbol_name: str = '',
                    triggered_skills: List[Dict] = None) -> Dict:
        """基于分析结果生成完整交易计划

        Args:
            analysis_result: LLM分析结果（含Phase 1-4）
            features: FeatureExtractor输出的指标
            symbol: 股票代码
            symbol_name: 股票名称

        Returns:
            完整交易计划字典
        """
        p4 = analysis_result.get('phase4_conclusion', {})
        p1 = analysis_result.get('phase1_indicator_inventory', {})

        # 1. 提取关键价位
        key_levels = p4.get('key_levels', {})
        entry_price = key_levels.get('trigger', features.get('trend', {}).get('price', 0))
        target_price = key_levels.get('target')
        stop_price = key_levels.get('stop_loss')

        if entry_price <= 0:
            return {'error': 'Invalid entry price'}

        # 2. 提取分析结论
        self.symbol = symbol
        direction = p4.get('final_judgment', 'NEUTRAL')
        confidence = p4.get('confidence', 50)
        trend_nature = p4.get('trend_nature', 'unknown')
        trend_stage = p4.get('trend_stage', 'unknown')

        # 3. 选择止损策略
        stop_strategy = self._select_stop_loss(features, stop_price)

        # 4. 计算仓位
        position = self._calculate_position(
            entry_price, stop_strategy['price'], confidence, features
        )

        if 'error' in position:
            return position

        # 5. 评估风险收益比
        actual_target = target_price or self._estimate_target(features, direction)
        rr_metrics = self._evaluate_risk_reward(
            entry_price, actual_target, stop_strategy['price']
        )

        # 6. 确定持有时间
        timeframe = self._estimate_timeframe(features, trend_nature)

        # 7. 提取触发的skills（优先使用传入的match结果，否则从LLM输出提取）
        if triggered_skills:
            skills_for_plan = triggered_skills
        else:
            skills_for_plan = self._extract_triggered_skills(analysis_result)

        # 8. 检测市场环境
        market_regime = self._detect_regime(features)

        # 9. 生成trade_id
        trade_id = self._generate_trade_id(symbol)

        # 计算验证日期
        analysis_date = datetime.now().strftime('%Y-%m-%d')
        verification_date = (datetime.now() + timedelta(days=timeframe['days'])).strftime('%Y-%m-%d')

        return {
            'trade_id': trade_id,
            'symbol': symbol,
            'symbol_name': symbol_name,
            'analysis_date': analysis_date,
            'planned_verification_date': verification_date,
            'timeframe_days': timeframe['days'],
            'status': 'planned',

            'plan': {
                'direction': 'long' if 'BULLISH' in direction else 'short' if 'BEARISH' in direction else 'neutral',
                'confidence': confidence,

                'entry': {
                    'type': 'market',
                    'price': entry_price,
                    'date': analysis_date,
                },

                'stop_loss': stop_strategy,

                'target': {
                    'type': 'fixed',
                    'price': actual_target,
                    'partial_exits': self._suggest_partial_exits(
                        entry_price, actual_target, stop_strategy['price']
                    ),
                },

                'position': position,

                'risk_metrics': rr_metrics,
            },

            'skills_triggered': [
                {
                    'id': s.get('skill_id', s.get('id', '')),
                    'name': s.get('name', 'Unknown'),
                    'direction': s.get('signal_direction', s.get('direction', 'neutral')),
                    'strength': s.get('signal_strength', s.get('strength', 0.5)),
                }
                for s in skills_for_plan
            ],
            'market_regime': market_regime,

            'recommendation': self._generate_recommendation(rr_metrics, confidence, market_regime),

            'created_at': datetime.now().isoformat(),
        }

    def _select_stop_loss(self, features: Dict,
                          llm_stop_price: Optional[float]) -> Dict:
        """选择最优止损策略

        优先级:
        1. ATR倍数止损（primary，最可靠）
        2. 固定价格止损（fallback，来自LLM建议）
        """
        price = features.get('trend', {}).get('price', 0)
        atr = features.get('volatility', {}).get('atr', {}).get('value', 0)
        atr_pct = features.get('volatility', {}).get('atr', {}).get('pct_of_price', 0)

        trend_stage = features.get('trend_stage', {}).get('stage', '')
        extreme_dev = features.get('trend_stage', {}).get('extreme_deviation', False)

        # 动态ATR倍数
        atr_multiplier = 2.0
        reason = 'standard'
        if trend_stage in ('late', 'fading') and extreme_dev:
            atr_multiplier = 3.0
            reason = 'late_stage_extreme_deviation'
        elif trend_stage in ('early', 'middle'):
            atr_multiplier = 1.5
            reason = 'early_or_middle_stage'

        # 计算动态止损
        dynamic_stop = None
        if price > 0 and atr > 0:
            dynamic_stop = price - atr * atr_multiplier

        # 选择最优止损
        if dynamic_stop and dynamic_stop > 0:
            return {
                'type': 'dynamic_atr',
                'price': round(dynamic_stop, 2),
                'fixed_price': llm_stop_price,
                'dynamic_price': round(dynamic_stop, 2),
                'atr': atr,
                'atr_pct': atr_pct,
                'atr_multiplier': atr_multiplier,
                'reason': reason,
                'note': f'基于{atr_multiplier}x ATR的动态止损，优于固定止损',
            }
        elif llm_stop_price and llm_stop_price > 0:
            return {
                'type': 'fixed',
                'price': llm_stop_price,
                'fixed_price': llm_stop_price,
                'dynamic_price': None,
                'atr': atr,
                'atr_pct': atr_pct,
                'atr_multiplier': None,
                'reason': 'llm_suggested',
                'note': '使用LLM建议的固定止损（无ATR数据）',
            }
        else:
            # 没有止损数据，用默认5%
            default_stop = price * 0.95 if price > 0 else 0
            return {
                'type': 'default',
                'price': round(default_stop, 2),
                'fixed_price': round(default_stop, 2),
                'dynamic_price': None,
                'atr': atr,
                'atr_pct': atr_pct,
                'atr_multiplier': None,
                'reason': 'default_5pct',
                'note': '使用默认5%止损（无止损数据）',
            }

    def _calculate_position(self, entry: float, stop: float,
                            confidence: float, features: Dict) -> Dict:
        """计算仓位"""
        # 置信度调整
        base_risk = 2.0
        adjusted_risk = PositionSizer.confidence_adjusted(base_risk, confidence)

        # 根据symbol判断市场，确定最小交易单位
        min_lot_size = 100 if self.symbol and (self.symbol.endswith('.SH') or self.symbol.endswith('.SZ') or
                                               (self.symbol.isdigit() and len(self.symbol) == 6)) else 1

        # 使用固定风险法
        result = PositionSizer.fixed_risk(
            self.capital, adjusted_risk, entry, stop,
            min_lot_size=min_lot_size
        )

        return result

    def _evaluate_risk_reward(self, entry: float, target: float,
                              stop: float) -> Dict:
        """评估风险收益比"""
        if entry <= 0 or target is None or stop is None:
            return {'error': 'Invalid prices for risk/reward calculation'}

        reward = abs(target - entry)
        risk = abs(entry - stop)
        rr_ratio = reward / risk if risk > 0 else float('inf')

        # 评级
        if rr_ratio >= 2.0:
            verdict = '优秀 (≥2:1)'
            grade = 'A'
        elif rr_ratio >= 1.0:
            verdict = '可接受 (≥1:1)'
            grade = 'B'
        elif rr_ratio >= 0.5:
            verdict = 'marginal (<1:1, 谨慎)'
            grade = 'C'
        else:
            verdict = '不合格 (<0.5:1, 不建议入场)'
            grade = 'D'

        return {
            'risk_reward_ratio': round(rr_ratio, 2),
            'reward': round(reward, 2),
            'risk': round(risk, 2),
            'verdict': verdict,
            'grade': grade,
            'entry_price': entry,
            'target_price': target,
            'stop_price': stop,
        }

    def _estimate_target(self, features: Dict, direction: str) -> float:
        """估算目标价位（当LLM未提供时）"""
        price = features.get('trend', {}).get('price', 0)
        atr = features.get('volatility', {}).get('atr', {}).get('value', 0)

        if 'BULLISH' in direction:
            # 目标 = 价格 + 2x ATR
            return round(price + atr * 2, 2) if atr > 0 else round(price * 1.05, 2)
        elif 'BEARISH' in direction:
            return round(price - atr * 2, 2) if atr > 0 else round(price * 0.95, 2)
        return price

    def _estimate_timeframe(self, features: Dict,
                            trend_nature: str) -> Dict:
        """估算持有时间"""
        adx = features.get('trend', {}).get('trend_strength', {}).get('adx', 0) or 0
        volatility_state = features.get('volatility_state', {}).get('state', '')

        base_days = 5  # 默认5天

        # 根据趋势强度调整
        if adx > 40:
            base_days = 3  # 强趋势，短期
        elif adx < 20:
            base_days = 10  # 弱趋势/震荡，长期

        # 根据波动率状态调整
        if volatility_state == 'squeeze':
            base_days = 3  # 挤压后即将突破
        elif volatility_state == 'expansion':
            base_days = 2  # 高波动，短期

        return {
            'days': base_days,
            'reason': f'ADX={adx}, volatility={volatility_state}, nature={trend_nature}',
        }

    def _suggest_partial_exits(self, entry: float, target: float,
                                stop: float) -> List[Dict]:
        """建议分批止盈方案"""
        if entry <= 0 or target <= 0:
            return []

        distance = abs(target - entry)

        # 方案1: 50%在目标位，50%移动止盈
        return [
            {
                'ratio': 0.5,
                'price': target,
                'reason': 'first_target',
                'note': '第一目标位了结50%仓位',
            },
            {
                'ratio': 0.5,
                'price': round(entry + distance * 1.5, 2),
                'reason': 'trailing_profit',
                'note': '剩余50%使用移动止盈，让利润奔跑',
            },
        ]

    def _extract_triggered_skills(self, analysis: Dict) -> List[Dict]:
        """提取触发的skill"""
        p2 = analysis.get('phase2_skill_application', {})
        triggered = p2.get('triggered_skills', [])

        return [
            {
                'name': s.get('name', 'Unknown'),
                'direction': s.get('signal_direction', 'neutral'),
                'strength': s.get('signal_strength', 0.5),
            }
            for s in triggered
        ]

    def _detect_regime(self, features: Dict) -> str:
        """检测市场环境"""
        trend_stage = features.get('trend_stage', {}).get('stage', '')
        adx = features.get('trend', {}).get('trend_strength', {}).get('adx', 0) or 0
        extreme_dev = features.get('trend_stage', {}).get('extreme_deviation', False)
        mtf = features.get('multi_timeframe', {}).get('alignment', '')

        if adx > 40 and trend_stage in ('late', 'fading') and extreme_dev:
            return 'trending_up_late_extreme'
        elif adx > 40 and trend_stage in ('late', 'fading'):
            return 'trending_up_late'
        elif adx > 40:
            return 'trending_up_strong'
        elif adx > 25:
            return 'trending_up'
        elif adx < 20:
            return 'ranging'
        return 'mixed'

    def _generate_recommendation(self, rr_metrics: Dict, confidence: float,
                                  regime: str) -> str:
        """生成交易建议"""
        rr = rr_metrics.get('risk_reward_ratio', 0)
        grade = rr_metrics.get('grade', 'D')

        parts = []

        # 风险收益比判断
        if grade == 'D':
            parts.append('风险收益比不合格，不建议新入场。')
        elif grade == 'C':
            parts.append('风险收益比marginal，如入场需严格控制仓位。')
        elif grade == 'B':
            parts.append('风险收益比可接受，可以正常仓位入场。')
        else:
            parts.append('风险收益比优秀，值得重点考虑。')

        # 置信度判断
        if confidence < 50:
            parts.append('预测置信度较低，建议观望或等待更明确信号。')
        elif confidence > 80:
            parts.append('预测置信度高，可以积极执行。')

        # 环境判断
        if 'late_extreme' in regime:
            parts.append('当前处于强趋势末期+极端偏离，追高风险极高。')

        return ' '.join(parts)

    def _generate_trade_id(self, symbol: str) -> str:
        """生成唯一交易ID（含时间戳+uuid，避免冲突）"""
        import uuid
        date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        symbol_clean = symbol.replace('.', '_').replace('-', '_')
        return f"{symbol_clean}_{date_str}_{uuid.uuid4().hex[:6]}"

    def save_plan(self, plan: Dict) -> str:
        """保存交易计划到文件"""
        trades_file = 'data/simulation/trades.jsonl'
        os.makedirs(os.path.dirname(trades_file), exist_ok=True)

        with open(trades_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(plan, ensure_ascii=False) + '\n')

        return trades_file
