"""Skill Rule Index - 技术分析规则的索引化存储与管理

核心设计：
1. 每条规则独立存储（JSONL），支持快速检索
2. 规则分级：core(核心框架) + active(已生效规则) + extension(扩展规则)
3. 规则状态：pending(待审核) → active(已生效) → deprecated(已废弃)
4. 性能追踪：每条规则记录胜率、使用次数、最后更新时间
"""

import json
import os
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime

RULES_FILE = 'data/skill_rules.jsonl'
RULES_INDEX_FILE = 'data/skill_rules_index.json'


class RuleIndex:
    """规则索引库 - 所有技术分析规则的结构化存储"""

    def __init__(self, rules_file: str = RULES_FILE):
        self.rules_file = rules_file
        self._rules: List[Dict[str, Any]] = []
        self._index: Dict[str, List[str]] = {}  # category -> [rule_ids]
        self._load()

    def _load(self):
        """加载所有规则到内存"""
        self._rules = []
        self._index = {}

        if not os.path.exists(self.rules_file):
            return

        with open(self.rules_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rule = json.loads(line)
                    self._rules.append(rule)
                    # 构建索引
                    cat = rule.get('category', 'general')
                    if cat not in self._index:
                        self._index[cat] = []
                    self._index[cat].append(rule['rule_id'])
                except json.JSONDecodeError:
                    continue

    def _save(self):
        """保存所有规则"""
        os.makedirs(os.path.dirname(self.rules_file), exist_ok=True)
        with open(self.rules_file, 'w', encoding='utf-8') as f:
            for rule in self._rules:
                f.write(json.dumps(rule, ensure_ascii=False) + '\n')
        self._save_index()

    def _save_index(self):
        """保存索引文件（用于快速查询统计）"""
        index = {
            'total_rules': len(self._rules),
            'by_category': {cat: len(ids) for cat, ids in self._index.items()},
            'by_status': {},
            'last_updated': datetime.now().isoformat()
        }
        for rule in self._rules:
            status = rule.get('status', 'unknown')
            index['by_status'][status] = index['by_status'].get(status, 0) + 1

        with open(RULES_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def add_rule(self, rule: Dict[str, Any], auto_activate: bool = False) -> str:
        """添加新规则

        Args:
            rule: 规则字典，必须包含 category, name, definition
            auto_activate: 是否直接标记为active（默认pending需审核）
        """
        rule_id = str(uuid.uuid4())[:8]

        # 检查是否与现有规则冲突
        conflicts = self._find_conflicts(rule)

        # 新 Skill 方法论格式：教材式结构
        new_rule = {
            'rule_id': rule_id,
            'category': rule.get('category', 'general'),
            'name': rule.get('name', 'Unnamed'),
            # 旧格式兼容
            'definition': rule.get('definition', ''),
            'conditions': rule.get('conditions', []),
            'examples': rule.get('examples', []),
            # 新 Skill 教材格式
            'type': rule.get('type', 'methodology'),  # methodology | pattern | signal
            'core_idea': rule.get('core_idea', rule.get('definition', '')),
            'analysis_steps': rule.get('analysis_steps', []),
            'reference_data': rule.get('reference_data', {}),
            'win_rate_hint': rule.get('win_rate_hint', {}),
            'common_pitfalls': rule.get('common_pitfalls', []),
            'when_not_to_use': rule.get('when_not_to_use', []),
            'source': rule.get('source', ''),
            'applicable_regimes': rule.get('applicable_regimes', []),
            'status': 'active' if auto_activate else 'pending',
            'version': 1,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'performance': {
                'used_count': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': None,
                'last_used': None,
                'total_pnl': 0.0,
                'by_regime': {},  # 分市场环境统计
            },
            'weight': rule.get('weight', 1.0),
            'conflicts': [c['rule_id'] for c in conflicts]
        }

        self._rules.append(new_rule)
        cat = new_rule['category']
        if cat not in self._index:
            self._index[cat] = []
        self._index[cat].append(rule_id)
        self._save()

        return rule_id

    def _find_conflicts(self, new_rule: Dict) -> List[Dict]:
        """查找与现有规则的冲突"""
        conflicts = []
        new_name = new_rule.get('name', '').lower()
        new_cat = new_rule.get('category', '')

        for rule in self._rules:
            if rule.get('status') != 'active':
                continue
            # 同名冲突
            if rule.get('name', '').lower() == new_name and rule.get('category') == new_cat:
                conflicts.append(rule)
            # 条件高度相似冲突（简化检查）
            # 实际实现可以更复杂的条件对比
        return conflicts

    def get_rules(self, category: Optional[str] = None,
                  status: str = 'active',
                  min_win_rate: Optional[float] = None,
                  regime: Optional[str] = None) -> List[Dict]:
        """检索规则

        Args:
            category: 规则类别，None表示全部
            status: 规则状态筛选
            min_win_rate: 最低胜率筛选（如0.5表示只返回胜率>50%的规则）
            regime: 市场状态筛选（如'trending_up'），None表示全部
        """
        results = []
        for rule in self._rules:
            if rule.get('status') != status:
                continue
            if category and rule.get('category') != category:
                continue
            if min_win_rate is not None:
                perf = rule.get('performance', {})
                win_rate = perf.get('win_rate')
                if win_rate is not None and win_rate < min_win_rate:
                    continue
            if regime:
                # 检查规则是否适用于当前市场状态
                applicable = rule.get('applicable_regimes', [])
                # 空列表表示通用规则，适用于所有状态
                if applicable and regime not in applicable:
                    continue
            results.append(rule)
        return results

    def get_rules_by_regime(self, regime: str, categories: List[str],
                            max_rules_per_cat: int = 5) -> Dict[str, List[Dict]]:
        """根据市场状态获取各分类的推荐规则

        策略：
        1. 先选适用当前状态的规则
        2. 再补充通用规则（applicable_regimes为空）
        3. 按胜率排序，每类最多返回max_rules_per_cat条
        """
        result = {}
        for cat in categories:
            # 1. 该分类下适用当前状态的规则
            regime_rules = self.get_rules(category=cat, status='active', regime=regime)
            # 2. 通用规则（未指定适用状态的）
            general_rules = [
                r for r in self.get_rules(category=cat, status='active')
                if not r.get('applicable_regimes')
            ]

            combined = regime_rules + general_rules

            # 按权重*胜率排序
            def sort_key(r):
                perf = r.get('performance', {})
                win_rate = perf.get('win_rate') or 0.5
                weight = r.get('weight', 1.0)
                return weight * win_rate

            combined.sort(key=sort_key, reverse=True)
            result[cat] = combined[:max_rules_per_cat]

        return result

    def get_rules_for_prompt(self, categories: List[str],
                             max_tokens: int = 6000,
                             regime: Optional[str] = None) -> str:
        """构建用于System Prompt的规则文本（核心方法）

        策略：
        1. 优先加载适用当前市场状态的规则
        2. 然后加载通用规则（未指定适用状态的）
        3. 超出token预算时，优先保留高胜率*高权重规则

        Args:
            categories: 规则类别列表
            max_tokens: 最大token预算
            regime: 当前市场状态（如'trending_up'），None表示不筛选
        """
        all_rules = []
        for cat in categories:
            # 1. 适用当前状态的规则（权重加成）
            if regime:
                regime_rules = self.get_rules(category=cat, status='active', regime=regime)
                for r in regime_rules:
                    r['_priority_boost'] = 0.2  # 适用状态加0.2优先级
                all_rules.extend(regime_rules)

            # 2. 通用规则
            general_rules = [
                r for r in self.get_rules(category=cat, status='active')
                if not r.get('applicable_regimes')
            ]
            for r in general_rules:
                r['_priority_boost'] = 0.0
            all_rules.extend(general_rules)

        if not all_rules:
            return "# 暂无具体规则"

        # 去重（可能有重叠）
        seen = set()
        unique_rules = []
        for r in all_rules:
            rid = r['rule_id']
            if rid not in seen:
                seen.add(rid)
                unique_rules.append(r)

        # 按权重*胜率+优先级排序
        def sort_key(r):
            perf = r.get('performance', {})
            win_rate = perf.get('win_rate') or 0.5
            weight = r.get('weight', 1.0)
            boost = r.get('_priority_boost', 0)
            return weight * win_rate + boost

        unique_rules.sort(key=sort_key, reverse=True)

        parts = []
        estimated_tokens = 0
        token_per_char = 0.4

        for rule in unique_rules:
            rule_text = self._format_rule_for_prompt(rule)
            rule_tokens = len(rule_text) * token_per_char

            if estimated_tokens + rule_tokens > max_tokens:
                summary = f"- {rule['name']}: {rule['definition'][:80]}..."
                summary_tokens = len(summary) * token_per_char
                if estimated_tokens + summary_tokens <= max_tokens:
                    parts.append(summary)
                    estimated_tokens += summary_tokens
                else:
                    break
            else:
                parts.append(rule_text)
                estimated_tokens += rule_tokens

        return '\n\n'.join(parts)

    def _format_rule_for_prompt(self, rule: Dict) -> str:
        """将单条规则格式化为prompt友好的教材式文本"""
        lines = [f"### {rule['name']}"]

        # 核心思想
        core = rule.get('core_idea') or rule.get('definition', '')
        if core:
            lines.append(f"核心思想：{core}")

        # 分析步骤（教材式方法）
        steps = rule.get('analysis_steps', [])
        if steps:
            lines.append("分析步骤：")
            for i, step in enumerate(steps, 1):
                lines.append(f"  {i}. {step}")

        # 参考数据
        ref_data = rule.get('reference_data', {})
        if ref_data:
            lines.append("参考数据：")
            for k, v in ref_data.items():
                lines.append(f"  - {k}：{v}")

        # 胜率提示
        win_hint = rule.get('win_rate_hint', {})
        if win_hint:
            lines.append("历史胜率参考：")
            for regime, rate in win_hint.items():
                lines.append(f"  - {regime}环境下约{rate*100:.0f}%")

        # 常见误区
        pitfalls = rule.get('common_pitfalls', [])
        if pitfalls:
            lines.append("常见误区：")
            for p in pitfalls[:2]:
                lines.append(f"  - {p}")

        # 不适用的场景
        not_use = rule.get('when_not_to_use', [])
        if not_use:
            lines.append("不适用场景：")
            for n in not_use[:2]:
                lines.append(f"  - {n}")

        # 实际验证胜率
        perf = rule.get('performance', {})
        win_rate = perf.get('win_rate')
        if win_rate is not None:
            lines.append(f"实际验证胜率：{win_rate*100:.0f}% (基于{perf.get('used_count', 0)}次)")
            by_regime = perf.get('by_regime', {})
            if by_regime:
                lines.append("分环境胜率：")
                for regime, rate in by_regime.items():
                    lines.append(f"  - {regime}：{rate*100:.0f}%")

        return '\n'.join(lines)

    def update_performance(self, rule_id: str, outcome: str, pnl: float = 0.0,
                           market_regime: str = 'unknown'):
        """更新规则性能统计（支持分市场环境统计）

        Args:
            rule_id: 规则ID
            outcome: 'win' | 'loss' | 'break_even'
            pnl: 收益金额/百分比
            market_regime: 当前市场环境（如'trending_up'）
        """
        for rule in self._rules:
            if rule['rule_id'] == rule_id:
                perf = rule['performance']
                perf['used_count'] = perf.get('used_count', 0) + 1
                perf['last_used'] = datetime.now().isoformat()

                if outcome == 'win':
                    perf['wins'] = perf.get('wins', 0) + 1
                elif outcome == 'loss':
                    perf['losses'] = perf.get('losses', 0) + 1

                perf['total_pnl'] = perf.get('total_pnl', 0) + pnl

                # 分市场环境统计
                by_regime = perf.get('by_regime', {})
                if market_regime not in by_regime:
                    by_regime[market_regime] = {'used': 0, 'wins': 0, 'losses': 0}
                by_regime[market_regime]['used'] += 1
                if outcome == 'win':
                    by_regime[market_regime]['wins'] += 1
                elif outcome == 'loss':
                    by_regime[market_regime]['losses'] += 1
                perf['by_regime'] = by_regime

                total = perf.get('wins', 0) + perf.get('losses', 0)
                if total > 0:
                    perf['win_rate'] = round(perf['wins'] / total, 2)

                # 根据胜率动态调整权重
                self._auto_adjust_weight(rule)

                rule['updated_at'] = datetime.now().isoformat()
                self._save()
                return True
        return False

    def _auto_adjust_weight(self, rule: Dict):
        """根据胜率自动调整规则权重

        策略：
        - 胜率 > 0.7 → 权重增加（更信任）
        - 胜率 0.4-0.7 → 权重不变
        - 胜率 < 0.4 → 权重降低（不太信任）
        - 使用次数 < 5 → 暂时不调整（样本不足）
        """
        perf = rule.get('performance', {})
        used = perf.get('used_count', 0)
        win_rate = perf.get('win_rate')

        if used < 5 or win_rate is None:
            return

        current_weight = rule.get('weight', 1.0)

        if win_rate > 0.7:
            # 高胜率规则权重增加，但不超过2.0
            new_weight = min(2.0, current_weight + 0.05)
        elif win_rate < 0.4:
            # 低胜率规则权重降低，但不低于0.3
            new_weight = max(0.3, current_weight - 0.05)
        else:
            # 中等胜率，微调
            new_weight = current_weight

        rule['weight'] = round(new_weight, 2)

    def adjust_weight(self, rule_id: str, delta: float) -> bool:
        """手动调整规则权重"""
        for rule in self._rules:
            if rule['rule_id'] == rule_id:
                current = rule.get('weight', 1.0)
                rule['weight'] = round(max(0.1, min(3.0, current + delta)), 2)
                rule['updated_at'] = datetime.now().isoformat()
                self._save()
                return True
        return False

    def activate_rule(self, rule_id: str) -> bool:
        """将pending规则标记为active"""
        for rule in self._rules:
            if rule['rule_id'] == rule_id:
                rule['status'] = 'active'
                rule['updated_at'] = datetime.now().isoformat()
                self._save()
                return True
        return False

    def deprecate_rule(self, rule_id: str, reason: str = '') -> bool:
        """废弃规则"""
        for rule in self._rules:
            if rule['rule_id'] == rule_id:
                rule['status'] = 'deprecated'
                rule['deprecation_reason'] = reason
                rule['updated_at'] = datetime.now().isoformat()
                self._save()
                return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """获取规则库统计"""
        return {
            'total': len(self._rules),
            'active': len([r for r in self._rules if r.get('status') == 'active']),
            'pending': len([r for r in self._rules if r.get('status') == 'pending']),
            'deprecated': len([r for r in self._rules if r.get('status') == 'deprecated']),
            'by_category': {cat: len(ids) for cat, ids in self._index.items()}
        }
