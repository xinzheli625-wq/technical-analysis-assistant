"""Feedback loop - 记录、验证、LLM自动归因，无本地规则。"""

import json
import os
import statistics
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

RECORDS_FILE = 'data/feedback_records.json'
STATS_FILE = 'data/statistics.json'


class FeedbackLoop:
    """反馈循环 - 记录验证，LLM自动归因。"""

    def __init__(self, records_file: str = RECORDS_FILE, stats_file: str = STATS_FILE):
        self.records_file = records_file
        self.stats_file = stats_file
        self.records: List[Dict] = []
        self._load_records()

    def _load_records(self):
        if os.path.exists(self.records_file):
            try:
                with open(self.records_file, 'r', encoding='utf-8') as f:
                    self.records = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.records = []

    def _save_records(self):
        os.makedirs(os.path.dirname(self.records_file), exist_ok=True)
        with open(self.records_file, 'w', encoding='utf-8') as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)

    def _find_today_record(self, symbol: str) -> Optional[Dict]:
        """查找当天同一股票的最新记录"""
        today = datetime.now().strftime('%Y-%m-%d')
        matches = [
            r for r in self.records
            if r.get('symbol') == symbol and r.get('timestamp', '').startswith(today)
        ]
        return matches[-1] if matches else None

    def record_analysis(self, analysis_results: Dict[str, Any],
                        target_price: Optional[float] = None,
                        stop_loss: Optional[float] = None,
                        timeframe_days: int = 20,
                        skills_used: Optional[List[str]] = None,
                        allow_duplicate: bool = False) -> Dict[str, Any]:
        """记录分析。

        Args:
            skills_used: 本次分析使用的Skill规则ID列表（用于后续归因）
            allow_duplicate: 是否允许同一天重复记录（默认False则覆盖旧记录）

        Returns:
            {'record_id': str, 'is_update': bool}
        """
        symbol = analysis_results.get('symbol', 'UNKNOWN')

        # 检查当天是否已有同股票记录
        existing = None if allow_duplicate else self._find_today_record(symbol)

        if existing:
            # 覆盖旧记录
            record_id = existing['record_id']
            existing['timestamp'] = datetime.now().isoformat()
            existing['input_type'] = analysis_results.get('input_type', 'unknown')
            existing['identified_patterns'] = analysis_results.get('pattern_analysis', {}).get('patterns', [])
            existing['indicator_values'] = analysis_results.get('indicator_analysis', {})
            existing['composite_score'] = analysis_results.get('scoring', {}).get('composite_score', 0)
            existing['verdict'] = analysis_results.get('scoring', {}).get('verdict', 'neutral')
            existing['target_price'] = target_price
            existing['stop_loss'] = stop_loss
            existing['timeframe_days'] = timeframe_days
            # 调用方未提供 skills_used 时保留旧值，不要清空（否则验证时无法归因）
            if skills_used is not None:
                existing['skills_used'] = skills_used
            # 覆盖即重新分析：清除旧的验证状态，避免新分析按旧结果统计
            for key in ('validated', 'validated_at', 'actual_return_pct', 'target_reached',
                        'stop_hit', 'direction_correct', 'max_drawdown_pct', 'outcome',
                        'technical_correctness', 'failure_reason', 'should_adjust_rule',
                        'adjustment_type', 'notes', 'attribution_source'):
                existing.pop(key, None)
            existing['validated'] = False
            existing['updated_count'] = existing.get('updated_count', 0) + 1
            self._save_records()
            return {'record_id': record_id, 'is_update': True}

        # 新建记录
        record = {
            'record_id': str(uuid.uuid4())[:8],
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'market': analysis_results.get('market', 'UNKNOWN'),
            'input_type': analysis_results.get('input_type', 'unknown'),
            'identified_patterns': analysis_results.get('pattern_analysis', {}).get('patterns', []),
            'indicator_values': analysis_results.get('indicator_analysis', {}),
            'composite_score': analysis_results.get('scoring', {}).get('composite_score', 0),
            'verdict': analysis_results.get('scoring', {}).get('verdict', 'neutral'),
            'target_price': target_price,
            'stop_loss': stop_loss,
            'timeframe_days': timeframe_days,
            'skills_used': skills_used or [],
            'validated': False,
            'non_technical_factors': [],
            'updated_count': 0,
        }

        self.records.append(record)
        self._save_records()
        return {'record_id': record['record_id'], 'is_update': False}

    def validate_record(self, record_id: str,
                        actual_return_pct: float,
                        target_reached: bool,
                        stop_hit: bool,
                        direction_correct: bool,
                        max_drawdown_pct: float = 0.0,
                        price_history: Optional[List[Dict]] = None,
                        market_regime: str = 'unknown') -> Dict:
        """验证并LLM自动归因 + 概率思维更新Skill性能。

        Args:
            market_regime: 验证时的市场环境（如'trending_up'），用于分环境统计
        """
        for record in self.records:
            if record.get('record_id') == record_id:
                record['validated'] = True
                record['validated_at'] = datetime.now().isoformat()
                record['actual_return_pct'] = actual_return_pct
                record['target_reached'] = target_reached
                record['stop_hit'] = stop_hit
                record['direction_correct'] = direction_correct
                record['max_drawdown_pct'] = max_drawdown_pct
                record['market_regime'] = market_regime

                if target_reached:
                    record['outcome'] = 'win'
                elif stop_hit:
                    record['outcome'] = 'loss'
                else:
                    record['outcome'] = 'open'

                # LLM自动归因
                if record.get('outcome') == 'loss':
                    try:
                        from utils.llm_client import DeepSeekClient

                        client = DeepSeekClient()
                        history = price_history or self._mock_price_history(record)
                        llm_attr = client.auto_attribute_failure(record, history)

                        record['technical_correctness'] = llm_attr.get('attribution', 'unknown')
                        record['failure_reason'] = llm_attr.get('reason')
                        record['should_adjust_rule'] = llm_attr.get('should_adjust_rule', False)
                        record['adjustment_type'] = llm_attr.get('adjustment_type', 'none')
                        record['notes'] = f"[LLM归因] {llm_attr.get('reason', '')}"
                        record['attribution_source'] = 'llm_auto'

                    except Exception as e:
                        record['technical_correctness'] = 'unknown'
                        record['attribution_source'] = f'llm_failed: {str(e)}'
                else:
                    record['attribution_source'] = 'none_needed'

                # 概率思维：按Skill独立归因（无论整体对错）
                self._update_skill_performance_probabilistic(
                    record, actual_return_pct, market_regime
                )

                self._save_records()
                return record

        raise ValueError(f"Record {record_id} not found")

    def _update_skill_performance_probabilistic(self, record: Dict,
                                                  actual_return_pct: float,
                                                  market_regime: str):
        """概率思维更新Skill性能

        不是简单的"对了/错了"，而是：
        1. 每个Skill独立评价（触发的Skill预测是否正确）
        2. 区分"正常误差"（规则本身好，小概率事件）和"规则失效"
        3. 分市场环境统计
        """
        from utils.rule_index import RuleIndex

        try:
            rule_index = RuleIndex()
            skills_used = record.get('skills_used', [])

            if not skills_used:
                return

            # 获取当时的分析结果（判断各Skill的预测方向）
            analysis = record.get('indicator_values', {})
            verdict = record.get('verdict', 'neutral')

            skill_validations = []

            for skill_id in skills_used:
                rule = None
                for r in rule_index._rules:
                    if r['rule_id'] == skill_id:
                        rule = r
                        break

                if not rule:
                    continue

                # 判断这个Skill的预测方向
                skill_signal = self._infer_skill_signal(rule, analysis, verdict)

                # 判断Skill的预测是否正确
                skill_correct = self._is_skill_correct(skill_signal, actual_return_pct)

                # 更新性能（传入市场环境）
                outcome = 'win' if skill_correct else 'loss'
                rule_index.update_performance(skill_id, outcome, actual_return_pct, market_regime)

                # 生成归因结论
                rule_index.get_stats()  # 获取更新后的统计
                perf = rule.get('performance', {})
                win_rate = perf.get('win_rate')
                used_count = perf.get('used_count', 0)

                if not skill_correct:
                    if used_count < 5:
                        conclusion = "样本不足，暂不评价"
                    elif win_rate is not None and win_rate > 0.6:
                        conclusion = f"正常误差（历史胜率{win_rate:.0%}，本次属小概率事件）"
                    elif win_rate is not None:
                        conclusion = f"持续表现不佳（胜率{win_rate:.0%}），建议review"
                    else:
                        conclusion = "暂无胜率数据，暂不评价"

                    # 检查是否环境不匹配
                    by_regime = perf.get('by_regime', {})
                    regime_stats = by_regime.get(market_regime, {})
                    regime_used = regime_stats.get('used', 0)
                    regime_wins = regime_stats.get('wins', 0)
                    if regime_used >= 3:
                        regime_rate = regime_wins / regime_used
                        if regime_rate < (win_rate or 0.5) * 0.7:
                            conclusion += f" | 在{market_regime}环境下胜率仅{regime_rate:.0%}，可能不适用"
                else:
                    conclusion = "预测正确"

                skill_validations.append({
                    'skill_id': skill_id,
                    'skill_name': rule.get('name'),
                    'predicted_signal': skill_signal,
                    'actual_outcome': actual_return_pct,
                    'correct': skill_correct,
                    'conclusion': conclusion,
                    'current_win_rate': win_rate,
                    'sample_size': used_count
                })

            record['skill_validations'] = skill_validations

        except Exception:
            pass

    def _infer_skill_signal(self, rule: Dict, analysis: Dict, verdict: str) -> str:
        """推断Skill的预测方向

        基于Skill的core_idea和最终verdict推断。
        简化版本：如果整体verdict是看涨且Skill是bullish方法，则推断为bullish。
        """
        core = rule.get('core_idea', '')
        name = rule.get('name', '')

        # 简单的关键词判断
        bullish_keywords = ['突破', '金叉', '买入', '看多', '上涨', '底部']
        bearish_keywords = ['超买', '死叉', '卖出', '看空', '下跌', '顶部', '跌破']

        name_lower = name.lower()
        core_lower = core.lower()

        bullish_score = sum(1 for k in bullish_keywords if k in name_lower or k in core_lower)
        bearish_score = sum(1 for k in bearish_keywords if k in name_lower or k in core_lower)

        if bullish_score > bearish_score:
            return 'bullish'
        elif bearish_score > bullish_score:
            return 'bearish'
        else:
            return 'neutral'

    def _is_skill_correct(self, skill_signal: str, actual_return_pct: float) -> bool:
        """判断Skill的预测是否正确

        允许一定的容错空间（技术分析是概率游戏）
        """
        if skill_signal == 'bullish' and actual_return_pct > -0.02:
            # 看多：只要没大跌就算对（允许小回调）
            return True
        if skill_signal == 'bearish' and actual_return_pct < 0.02:
            # 看空：只要没大涨就算对
            return True
        if skill_signal == 'neutral' and abs(actual_return_pct) < 0.03:
            # 中性：波动在3%以内算对
            return True
        return False

    def get_unprocessed_records(self) -> List[Dict]:
        return [r for r in self.records if not r.get('processed_by_evolution', False)]

    def mark_processed_by_evolution(self, record_ids: List[str]):
        for record in self.records:
            if record.get('record_id') in record_ids:
                record['processed_by_evolution'] = True
                record['evolution_timestamp'] = datetime.now().isoformat()
        self._save_records()

    def calculate_statistics(self) -> Dict[str, Any]:
        validated = [r for r in self.records if r.get('validated')]

        if not validated:
            return {'error': 'No validated records yet'}

        wins = sum(1 for r in validated if r.get('outcome') == 'win')
        losses = sum(1 for r in validated if r.get('outcome') == 'loss')
        total = wins + losses
        win_rate = wins / total * 100 if total > 0 else 0

        returns = [r.get('actual_return_pct', 0) for r in validated if r.get('actual_return_pct') is not None]
        avg_return = statistics.mean(returns) if returns else 0

        stats = {
            'total_records': len(self.records),
            'validated_records': len(validated),
            'overall': {
                'win_rate': round(win_rate, 1),
                'avg_return': round(avg_return, 2),
                'wins': wins,
                'losses': losses
            },
            'last_updated': datetime.now().isoformat()
        }

        os.makedirs(os.path.dirname(self.stats_file), exist_ok=True)
        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

        return stats

    def _mock_price_history(self, record: Dict) -> List[Dict]:
        return [
            {'date': 'T+1', 'close': record.get('target_price', 0) * 0.98},
            {'date': 'T+2', 'close': record.get('target_price', 0) * 0.95},
            {'date': 'T+3', 'close': record.get('target_price', 0) * 0.97},
            {'date': 'T+5', 'close': record.get('target_price', 0) * 0.94},
        ]
