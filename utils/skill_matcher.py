"""SkillMatcher - 系统层面精确匹配 Skill 触发条件

核心设计：
1. Skill 增加 trigger 结构化条件（指标名、操作符、阈值）
2. 系统直接数值比较，零歧义
3. 输出三类：triggered / near_triggered / not_triggered
4. 只把 triggered + near_triggered 传给 LLM
"""

from typing import Any, Dict, List, Optional

NEAR_TRIGGER_PCT = 0.20  # 准触发阈值：距离目标值差20%


def build_alias_map() -> Dict[str, str]:
    """构建指标别名映射（模块级单一事实源）

    skill_knowledge 的提取 prompt 也从这里生成指标白名单，
    保证"提取时教给 LLM 的命名"与"匹配时可解析的名称"永不漂移。
    """
    # 延迟构建：实际字典在 _ALIAS_MAP_BUILDER 中（见文件底部）
    return _build_alias_map_impl().copy()


def _build_alias_map_impl() -> Dict[str, str]:
    """别名映射的完整定义（由 build_alias_map 导出）"""
    alias_map = {
            # 原始价格（extract_all 的 raw 段）
            'close': 'raw.close',
            'open': 'raw.open',
            'high': 'raw.high',
            'low': 'raw.low',
            'volume': 'raw.volume',
            # 趋势方向（蜡烛图类 Skill 常用 indicator='trend' 表示前置趋势）
            'trend': 'composite.mid_trend',
            # 动量
            'rsi': 'momentum.rsi.value',
            'rsi_14': 'momentum.rsi.value',
            'macd': 'momentum.macd.line',
            'macd_line': 'momentum.macd.line',
            'macd_histogram': 'momentum.macd.histogram',
            'macd_signal': 'momentum.macd.signal',
            'macd_trend': 'momentum.macd.trend',
            'cci': 'momentum.cci',
            'williams_r': 'momentum.williams_r',
            'kdj_k': 'momentum.kdj.k',
            'kdj_d': 'momentum.kdj.d',
            'kdj_j': 'momentum.kdj.j',
            'stoch_k': 'momentum.stochastic.k',
            'stoch_d': 'momentum.stochastic.d',
            'stochastic_k': 'momentum.stochastic.k',
            'stochastic_d': 'momentum.stochastic.d',
            'momentum': 'momentum.momentum',
            'tsi': 'momentum.tsi',
            'ao': 'momentum.awesome_oscillator',
            'uo': 'momentum.ultimate_oscillator',
            'ppo': 'momentum.ppo.value',
            'stoch_rsi': 'momentum.stoch_rsi.value',
            # 趋势
            'adx': 'trend.trend_strength.adx',
            'adx_value': 'trend.trend_strength.adx',
            'adx_signal': 'trend.trend_strength.adx_signal',
            'sma20': 'trend.moving_averages.sma20',
            'sma50': 'trend.moving_averages.sma50',
            'sma200': 'trend.moving_averages.sma200',
            'ema12': 'trend.moving_averages.ema12',
            'ema26': 'trend.moving_averages.ema26',
            'price': 'trend.price',
            'price_vs_sma20_pct': 'trend.moving_averages.price_vs_sma20_pct',
            'price_vs_sma200_pct': 'trend.moving_averages.price_vs_sma200_pct',
            'sma20_vs_sma50': 'trend.moving_averages.sma20_vs_sma50',
            'roc_12': 'trend.momentum.roc_12',
            'supertrend_direction': 'trend.supertrend.direction',
            'ichimoku_price_vs_kijun': 'trend.ichimoku.price_vs_kijun',
            # 波动率
            'atr': 'volatility.atr.value',
            'atr_value': 'volatility.atr.value',
            'atr_pct': 'volatility.atr.pct_of_price',
            'bollinger_upper': 'volatility.bollinger.upper',
            'bollinger_lower': 'volatility.bollinger.lower',
            'bollinger_middle': 'volatility.bollinger.middle',
            'bollinger_percent_b': 'volatility.bollinger.percent_b',
            'bollinger_bandwidth': 'volatility.bollinger.bandwidth',
            'bollinger_position': 'volatility.bollinger.position',
            'hist_vol': 'volatility.historical_volatility',
            'historical_volatility': 'volatility.historical_volatility',
            'ulcer_index': 'volatility.ulcer_index',
            # 量能
            'volume_ratio': 'volume.volume_ratio',
            'volume_trend': 'volume.volume_trend',
            'obv': 'volume.obv.value',
            'obv_value': 'volume.obv.value',
            'obv_trend': 'volume.obv.trend',
            'vwap': 'volume.vwap',
            'mfi': 'volume.mfi',
            'force_index': 'volume.force_index',
            'chaikin_osc': 'volume.chaikin_oscillator',
            'chaikin_oscillator': 'volume.chaikin_oscillator',
            # 背离
            'div_count': 'divergence.count',
            'div_bearish_count': 'divergence.bearish_count',
            'div_bullish_count': 'divergence.bullish_count',
            'div_primary': 'divergence.primary_signal',
            'divergence_count': 'divergence.count',
            'divergence_bearish_count': 'divergence.bearish_count',
            'divergence_bullish_count': 'divergence.bullish_count',
            'divergence_primary_signal': 'divergence.primary_signal',
            # 趋势阶段
            'trend_stage': 'trend_stage.stage',
            'trend_stage_confidence': 'trend_stage.stage_confidence',
            'adx_change_10d': 'trend_stage.adx_change_10d_pct',
            'adx_change_10d_pct': 'trend_stage.adx_change_10d_pct',
            'ma_deviation_20': 'trend_stage.ma_deviation_20',
            'ma_deviation_50': 'trend_stage.ma_deviation_50',
            'ma_deviation_change_10d': 'trend_stage.ma_deviation_change_10d',
            'price_acceleration': 'trend_stage.price_acceleration',
            'extreme_deviation': 'trend_stage.extreme_deviation',
            # 波动率状态
            'vol_state': 'volatility_state.state',
            'volatility_state': 'volatility_state.state',
            'squeeze': 'volatility_state.squeeze',
            'expansion': 'volatility_state.expansion',
            'volatility_squeeze': 'volatility_state.squeeze',
            'volatility_expansion': 'volatility_state.expansion',
            'squeeze_to_expansion_alert': 'volatility_state.squeeze_to_expansion_alert',
            # 动量加速度
            'rsi_change_1d': 'momentum_accel.rsi_change_1d',
            'rsi_change_5d': 'momentum_accel.rsi_change_5d',
            'rsi_acceleration': 'momentum_accel.rsi_acceleration',
            'macd_hist_accel': 'momentum_accel.macd_hist_acceleration',
            'macd_hist_acceleration': 'momentum_accel.macd_hist_acceleration',
            'price_accel': 'momentum_accel.price_acceleration',
            'price_acceleration_state': 'momentum_accel.price_acceleration',
            'momentum_direction': 'momentum_accel.momentum_direction',
            'momentum_signal': 'momentum_accel.signal',
            # 多时间框架
            'mtf_alignment': 'multi_timeframe.alignment',
            'mtf_short_trend': 'multi_timeframe.short_trend',
            'mtf_mid_trend': 'multi_timeframe.mid_trend',
            'mtf_long_trend': 'multi_timeframe.long_trend',
            'mtf_short_turning': 'multi_timeframe.short_turning',
            'mtf_long_intact': 'multi_timeframe.long_trend_intact',
            'mtf_long_trend_intact': 'multi_timeframe.long_trend_intact',
            # 形态
            'pattern_count': 'pattern.pattern_count',
            'swing_peaks': 'pattern.swing_points.peaks_count',
            'swing_troughs': 'pattern.swing_points.troughs_count',
            # 综合
            'composite_short_trend': 'composite.short_trend',
            'composite_mid_trend': 'composite.mid_trend',
            'price_position_60d': 'composite.price_position_60d',
            'return_1d': 'composite.returns.1d',
            'return_5d': 'composite.returns.5d',
            'return_20d': 'composite.returns.20d',
            'price_change_pct': 'composite.returns.1d',
        }

    # 额外周期均线（extract_all 的 moving_averages 段，数据足够时才存在）
    for p in (3, 4, 5, 9, 10, 13, 21, 40, 65, 90):
        alias_map[f'sma{p}'] = f'trend.moving_averages.sma{p}'
        alias_map[f'price_vs_sma{p}_pct'] = f'trend.moving_averages.price_vs_sma{p}_pct'
    # price_vs_sma65 是 sma65 偏离度的简写（与 price_vs_sma65_pct 同义）
    alias_map['price_vs_sma65'] = 'trend.moving_averages.price_vs_sma65_pct'

    return alias_map


class SkillMatcher:
    """Skill 条件匹配器 - 确定性计算"""

    def __init__(self):
        self.rules: List[Dict] = []
        self._load_active_rules()
        self._init_alias_map()

    def _init_alias_map(self):
        """初始化指标别名映射（取自模块级单一事实源 build_alias_map）

        注意：这里的别名必须覆盖两类名称：
        1. SEGMENT_EXTRACT_SYSTEM_PROMPT 中教给提取模型的指标命名规范
        2. skill_rules.jsonl 中存量规则实际使用的指标名
        缺失别名会导致条件评估为 unknown，Skill 永远不会触发。
        """
        self.alias_map = build_alias_map()



    def _load_active_rules(self):
        """加载所有 active 状态的 Skill"""
        from utils.rule_index import RuleIndex
        try:
            rule_index = RuleIndex()
            self.rules = rule_index.get_rules(status='active')
        except Exception:
            self.rules = []

    def match(self, features: Dict[str, Any],
              market_regime: Optional[str] = None) -> Dict[str, List[Dict]]:
        """匹配所有 Skill 条件（支持环境适配权重）

        Args:
            features: FeatureExtractor 输出的所有指标数值
            market_regime: 外部（MarketRegimeDetector.to_matcher_regime）提供的
                环境标签。传入后不再使用内置启发式检测——全系统统一环境口径。
                不传则回退到内置启发式（独立使用时的兼容路径）。

        Returns:
            {
                'triggered': [...],      # 条件完全满足
                'near_triggered': [...], # 接近但未满足（差20%以内）
                'not_triggered': [...]   # 明确未满足
            }
        """
        triggered = []
        near_triggered = []
        not_triggered = []

        # 检测当前市场环境（优先使用外部统一检测结果）
        if market_regime is None:
            market_regime = self._detect_market_regime(features)

        for rule in self.rules:
            trigger_def = rule.get('trigger')
            if not trigger_def:
                not_triggered.append({
                    'skill_id': rule['rule_id'],
                    'name': rule['name'],
                    'reason': '无结构化触发条件，需LLM判断'
                })
                continue

            conditions = trigger_def.get('conditions', [])
            logic = trigger_def.get('logic', 'AND')

            match_result = self._evaluate_conditions(
                conditions, logic, features, rule
            )

            # 应用环境适配权重调整
            detail = match_result['detail']
            adjusted = self._apply_regime_adjustment(
                detail, market_regime, features
            )
            detail['regime_adjustment'] = adjusted
            detail['market_regime'] = market_regime

            if match_result['status'] == 'triggered':
                triggered.append(detail)
            elif match_result['status'] == 'near_triggered':
                near_triggered.append(detail)
            else:
                not_triggered.append(detail)

        # 按环境调整后的强度排序
        triggered.sort(key=lambda x: x.get('adjusted_strength', x.get('signal_strength', 0)), reverse=True)
        near_triggered.sort(key=lambda x: x.get('gap_pct', 100))

        return {
            'triggered': triggered,
            'near_triggered': near_triggered,
            'not_triggered': not_triggered,
            'market_regime': market_regime,
            'summary': {
                'total_skills': len(self.rules),
                'triggered_count': len(triggered),
                'near_triggered_count': len(near_triggered),
                'not_triggered_count': len(not_triggered)
            }
        }

    def _detect_market_regime(self, features: Dict) -> str:
        """检测当前市场环境"""
        trend_stage = self._get_indicator_value(features, 'trend_stage') or ''
        adx = self._get_indicator_value(features, 'adx') or 0
        self._get_indicator_value(features, 'mtf_alignment') or ''
        extreme_dev = self._get_indicator_value(features, 'extreme_deviation') or False

        # 强趋势末期 + 极端偏离
        if adx > 40 and trend_stage in ('late', 'fading') and extreme_dev:
            return 'trending_up_late_extreme'
        # 强趋势末期
        if adx > 40 and trend_stage in ('late', 'fading'):
            return 'trending_up_late'
        # 强趋势中期
        if adx > 40 and trend_stage in ('early', 'early_acceleration', 'middle'):
            return 'trending_up_strong'
        # 中等趋势
        if adx > 25:
            return 'trending_up'
        # 震荡
        if adx < 20:
            return 'ranging'
        return 'mixed'

    def _apply_regime_adjustment(self, detail: Dict, regime: str,
                                  features: Dict) -> Dict:
        """根据市场环境调整Skill权重

        核心规则：
        1. 强趋势末期 + 极端偏离：降低超买/超卖类bearish/bullish skill权重
        2. 强趋势中：降低逆势skill权重
        3. 震荡市：降低趋势跟踪skill权重
        """
        skill_name = detail.get('name', '')
        signal_dir = detail.get('signal_direction', 'neutral')
        base_strength = detail.get('signal_strength', 0.5)
        adjustment = 0.0
        reason = []

        # 规则1: 强趋势末期极端偏离时，超买/超卖信号降权
        if regime in ('trending_up_late_extreme', 'trending_up_late'):
            # Bearish skill基于超买信号的降权
            if signal_dir == 'bearish':
                overbought_keywords = ['超买', 'overbought', '极端', '背离',
                                       '相反意见', '威廉斯', 'RSI超买']
                if any(kw in skill_name for kw in overbought_keywords):
                    adjustment = -0.3
                    reason.append(f"在{regime}环境下，超买类bearish skill降权")

            # Bullish趋势跟踪skill加分
            if signal_dir == 'bullish':
                trend_keywords = ['交叉', '突破', 'MACD', '均线', 'DI',
                                  '趋势', '移动平均']
                if any(kw in skill_name for kw in trend_keywords):
                    adjustment = +0.1
                    reason.append(f"在{regime}环境下，趋势跟踪类bullish skill加分")

        # 规则2: 震荡市中趋势跟踪skill降权
        if regime == 'ranging':
            if signal_dir in ('bullish', 'bearish'):
                trend_keywords = ['交叉', '突破', '趋势', '均线']
                if any(kw in skill_name for kw in trend_keywords):
                    adjustment = -0.2
                    reason.append("震荡市中趋势跟踪skill降权")

        # 规则3: 历史胜率微调（不淘汰 Skill，只让 LLM 看到并轻微影响排序）
        # 样本 >=5 才启用：胜率 50% 为中性，每偏离 10% 调整 ±0.04，上限 ±0.2
        perf = detail.get('performance', {})
        win_rate = perf.get('win_rate')
        used = perf.get('used_count', 0)
        if win_rate is not None and used >= 5:
            perf_adj = max(-0.2, min(0.2, (win_rate - 0.5) * 0.4))
            if abs(perf_adj) >= 0.02:
                adjustment += perf_adj
                reason.append(
                    f"历史胜率{win_rate * 100:.0f}%（{used}次验证）权重{'+' if perf_adj > 0 else ''}{perf_adj:.2f}")

        # 当前环境胜率（仅展示，不重复调整）
        regime_stats = (perf.get('by_regime') or {}).get(regime, {})
        regime_used = regime_stats.get('used', 0)
        regime_win_rate = None
        if regime_used >= 3:
            rw = regime_stats.get('wins', 0)
            rl = regime_stats.get('losses', 0)
            if rw + rl > 0:
                regime_win_rate = rw / (rw + rl)
                reason.append(f"当前环境胜率{regime_win_rate * 100:.0f}%（{regime_used}次）")

        # 应用调整
        adjusted_strength = max(0.0, min(1.0, base_strength + adjustment))

        return {
            'original_strength': base_strength,
            'adjusted_strength': round(adjusted_strength, 2),
            'adjustment': round(adjustment, 2),
            'reason': reason,
            'regime': regime,
            'regime_win_rate': regime_win_rate,
        }

    def _evaluate_conditions(self, conditions: List[Dict], logic: str,
                             features: Dict, rule: Dict) -> Dict:
        """评估单条 Skill 的所有条件"""
        results = []
        any_near = False
        max_gap_pct = 0

        for cond in conditions:
            indicator = cond.get('indicator', '')
            operator = cond.get('operator', '>')
            target_value = cond.get('value')
            value_ref = cond.get('value_ref')  # 引用另一个指标

            # 形态触发：{"indicator": "pattern", "value": "Double Bottom"}
            # 在 patterns_detected 列表中按名称匹配，而不是当数值指标解析
            if indicator in ('pattern', 'pattern_detected'):
                cond_result = self._evaluate_pattern_condition(
                    features, operator, target_value)
                results.append(cond_result)
                continue

            # 获取当前值
            current_value = self._get_indicator_value(features, indicator)

            # 如果 target_value 是引用，解析引用
            if value_ref and isinstance(value_ref, str):
                target_value = self._get_indicator_value(features, value_ref)

            if current_value is None or target_value is None:
                results.append({
                    'indicator': indicator,
                    'status': 'unknown',
                    'reason': f'指标 {indicator} 无数据'
                })
                continue

            # 评估条件
            cond_result = self._evaluate_single_condition(
                current_value, operator, target_value
            )
            results.append(cond_result)

            if cond_result['status'] == 'near':
                any_near = True
                max_gap_pct = max(max_gap_pct, cond_result.get('gap_pct', 0))

        # 根据逻辑组合结果
        if logic == 'AND':
            all_triggered = all(r['status'] == 'triggered' for r in results)
            all_not_triggered = all(r['status'] == 'not_triggered' for r in results)

            if all_triggered:
                status = 'triggered'
            elif any_near and not all_not_triggered:
                status = 'near_triggered'
            else:
                status = 'not_triggered'
        else:  # OR
            any_triggered = any(r['status'] == 'triggered' for r in results)
            if any_triggered:
                status = 'triggered'
            elif any_near:
                status = 'near_triggered'
            else:
                status = 'not_triggered'

        signal = rule.get('signal', {})
        perf = rule.get('performance') or {}
        by_regime = perf.get('by_regime', {})

        detail = {
            'skill_id': rule['rule_id'],
            'name': rule['name'],
            'core_idea': rule.get('core_idea', rule.get('definition', '')),
            'status': status,
            'conditions': results,
            'signal_direction': signal.get('direction', 'neutral'),
            'signal_strength': signal.get('strength', 0.5),
            'applicable_regimes': rule.get('applicable_regimes', []),
            'win_rate_hint': rule.get('win_rate_hint', {}),
            'common_pitfalls': rule.get('common_pitfalls', [])[:2],
            # 历史验证表现（供 LLM 参考 + 权重微调，不用于淘汰 Skill）
            'performance': {
                'used_count': perf.get('used_count', 0),
                'win_rate': perf.get('win_rate'),
                'by_regime': by_regime,
            },
        }

        if status == 'near_triggered':
            detail['gap_pct'] = max_gap_pct

        return {'status': status, 'detail': detail}

    def _evaluate_single_condition(self, current, operator: str,
                                   target) -> Dict:
        """评估单个条件（支持数值和字符串比较）"""
        # 处理字符串值（如趋势方向、形态名称等）
        if isinstance(current, str) or isinstance(target, str):
            return self._evaluate_string_condition(current, operator, target)

        # 计算差距百分比
        if target != 0 and isinstance(target, (int, float)):
            gap = abs(current - target)
            gap_pct = gap / abs(target)
        else:
            gap_pct = abs(current) if current != 0 else 0

        result = {
            'current_value': current,
            'target_value': target,
            'operator': operator,
            'gap_pct': round(gap_pct * 100, 2)
        }

        # 判断是否满足条件
        satisfied = False
        if operator == '>':
            satisfied = current > target
        elif operator == '>=':
            satisfied = current >= target
        elif operator == '<':
            satisfied = current < target
        elif operator == '<=':
            satisfied = current <= target
        elif operator == '=':
            satisfied = abs(current - target) < 0.001
        elif operator == 'between':
            low, high = target if isinstance(target, (list, tuple)) else (target * 0.9, target * 1.1)
            satisfied = low <= current <= high

        if satisfied:
            result['status'] = 'triggered'
            result['evidence'] = f'{current} {operator} {target} ✓'
        elif gap_pct <= NEAR_TRIGGER_PCT:
            result['status'] = 'near'
            result['evidence'] = f'{current} 接近 {target}（差{gap_pct*100:.1f}%）'
        else:
            result['status'] = 'not_triggered'
            result['evidence'] = f'{current} 不满足 {operator} {target}'

        return result

    def _evaluate_pattern_condition(self, features: Dict, operator: str,
                                    target) -> Dict:
        """评估形态触发条件（indicator='pattern'/'pattern_detected'）

        在 pattern.patterns_detected 列表中按名称匹配 target 形态。
        operator='=' / '==' → 形态被检测到；operator='!=' → 形态未被检测到。
        """
        pattern_list = features.get('pattern', {}).get('patterns_detected', [])
        target_norm = str(target or '').lower().replace(' ', '_').replace('-', '_')

        matched = None
        if target_norm and isinstance(pattern_list, list):
            for p in pattern_list:
                if not isinstance(p, dict):
                    continue
                pname = p.get('name', '').lower().replace(' ', '_').replace('-', '_')
                if target_norm in pname or pname in target_norm:
                    matched = p
                    break

        if operator in ('!=', '<>'):
            satisfied = matched is None
        else:
            satisfied = matched is not None

        result = {
            'current_value': matched.get('name') if matched else None,
            'target_value': target,
            'operator': operator,
            'gap_pct': 0 if satisfied else 100,
        }
        if satisfied:
            result['status'] = 'triggered'
            if matched:
                conf = matched.get('confidence', 'N/A')
                result['evidence'] = f"检测到形态 {matched.get('name')}（置信度{conf}）✓"
            else:
                result['evidence'] = f"未检测到形态 {target} ✓"
        else:
            result['status'] = 'not_triggered'
            result['evidence'] = f"未检测到形态 {target}"
        return result

    def _evaluate_string_condition(self, current: str, operator: str,
                                    target) -> Dict:
        """评估字符串条件（如趋势方向、阶段等）"""
        target_str = str(target).lower() if target else ''
        current_str = str(current).lower() if current else ''

        # 字符串相等判断（宽松匹配：相等或互相包含，兼容 'up'/'uptrend' 等写法）
        if operator in ('=', '=='):
            satisfied = (current_str == target_str
                         or (current_str and target_str
                             and (target_str in current_str or current_str in target_str)))
        elif operator == '!=':
            satisfied = current_str != target_str
        else:
            # 其他操作符对字符串使用包含判断
            satisfied = target_str in current_str

        result = {
            'current_value': current,
            'target_value': target,
            'operator': operator,
            'gap_pct': 0 if satisfied else 100
        }

        if satisfied:
            result['status'] = 'triggered'
            result['evidence'] = f'"{current}" 匹配 "{target}" ✓'
        else:
            result['status'] = 'not_triggered'
            result['evidence'] = f'"{current}" 不匹配 "{target}"'

        return result

    def _get_indicator_value(self, features: Dict, indicator_name,
                              _visited: set = None) -> Optional[float]:
        """从 features 中提取指标数值

        支持多级路径，如 'adx.value'、'bollinger.percent_b'
        支持布尔值（pattern detected等）转为 1.0/0.0
        支持列表中按name匹配（pattern列表）
        """
        if not indicator_name or not isinstance(indicator_name, str):
            return None

        if _visited is None:
            _visited = set()
        if indicator_name in _visited:
            return None  # 防止循环引用
        _visited.add(indicator_name)

        # 直接匹配
        if indicator_name in features:
            converted = self._to_comparable(features[indicator_name])
            if converted is not None:
                return converted

        # 多级路径匹配
        parts = indicator_name.split('.')
        current = features
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                current = None
                break

        if current is not None:
            converted = self._to_comparable(current)
            if converted is not None:
                return converted

        # 使用实例级别的别名映射（避免每次调用重建）
        if indicator_name in self.alias_map:
            return self._get_indicator_value(features, self.alias_map[indicator_name], _visited)

        # 特殊：pattern名称匹配（如 "Double Bottom", "Head and Shoulders"）
        # 检查 pattern.patterns_detected 列表中是否有匹配的形态
        pattern_list = features.get('pattern', {}).get('patterns_detected', [])
        if isinstance(pattern_list, list):
            indicator_lower = indicator_name.lower().replace(' ', '_').replace('-', '_')
            for p in pattern_list:
                if isinstance(p, dict):
                    pname = p.get('name', '').lower().replace(' ', '_').replace('-', '_')
                    if indicator_lower in pname or pname in indicator_lower:
                        # 返回形态检测置信度作为数值（默认50）
                        return float(p.get('confidence', 50))
            # 如果pattern列表不为空，且查询的是已知pattern类型，返回0表示未检测到
            known_patterns = ['double_bottom', 'head_and_shoulders', 'triangle', 'cup_and_handle',
                             'wedge', 'flag', 'pennant', 'channel', 'rectangle', 'rounded',
                             'v_reversal', 'island_reversal', 'gap']
            if any(kp in indicator_lower for kp in known_patterns):
                return 0.0

        return None

    @staticmethod
    def _to_comparable(val):
        """把 feature 值统一转为可比较的数值/字符串

        必须处理 numpy 标量（np.bool_ / np.integer / np.floating），
        它们不是 Python 内置 bool/int/float 的子类，否则会漏判为 None。
        """
        import numpy as np
        if isinstance(val, (bool, np.bool_)):
            return 1.0 if val else 0.0
        if isinstance(val, (int, float, np.integer, np.floating)):
            return float(val)
        if isinstance(val, str):
            # 先尝试解析为数值，不行就保留字符串（用于字符串比较）
            try:
                return float(val)
            except ValueError:
                return val
        if isinstance(val, list):
            # 列表长度作为数值（如pattern数量）
            return float(len(val))
        return None

    def calculate_risk_metrics(self, features: Dict, target_price: float = None,
                                stop_loss: float = None) -> Dict:
        """计算风险收益比和动态止损"""
        price = self._get_indicator_value(features, 'price') or 0
        atr = self._get_indicator_value(features, 'atr') or 0
        atr_pct = self._get_indicator_value(features, 'atr_pct') or 0
        trend_stage = self._get_indicator_value(features, 'trend_stage') or 'unknown'
        extreme_dev = self._get_indicator_value(features, 'extreme_deviation') or False

        if price <= 0:
            return {'error': 'Invalid price'}

        # 动态止损（ATR倍数）
        atr_multiplier = 2.0
        if trend_stage in ('late', 'fading') and extreme_dev:
            atr_multiplier = 3.0
        elif trend_stage in ('early', 'middle'):
            atr_multiplier = 1.5

        dynamic_stop = price - atr * atr_multiplier if atr > 0 else price * 0.93

        result = {
            'price': price,
            'dynamic_stop': round(dynamic_stop, 2),
            'atr': atr,
            'atr_pct': atr_pct,
            'atr_multiplier': atr_multiplier,
            'max_expected_drawdown_pct': round(atr * 3 / price * 100, 1) if atr > 0 else None,
        }

        if target_price and stop_loss:
            reward = target_price - price
            risk = price - stop_loss
            rr_ratio = reward / risk if risk > 0 else float('inf')

            if rr_ratio >= 2.0:
                verdict = "优秀 (≥2:1)"
            elif rr_ratio >= 1.0:
                verdict = "可接受 (≥1:1)"
            elif rr_ratio >= 0.5:
                verdict = "marginal (<1:1, 谨慎)"
            else:
                verdict = "不合格 (<0.5:1, 不建议入场)"

            result.update({
                'target_price': target_price,
                'stop_loss': stop_loss,
                'reward': round(reward, 2),
                'risk': round(risk, 2),
                'risk_reward_ratio': round(rr_ratio, 2),
                'verdict': verdict,
            })

        return result

    @staticmethod
    def format_for_llm(match_result: Dict) -> str:
        """将匹配结果格式化为 LLM-friendly 文本"""
        lines = []
        summary = match_result.get('summary', {})
        lines.append("## Skill 触发状态总览")
        lines.append(f"- 总Skill数: {summary.get('total_skills', 0)}")
        lines.append(f"- 已触发: {summary.get('triggered_count', 0)}")
        lines.append(f"- 准触发: {summary.get('near_triggered_count', 0)}")
        lines.append(f"- 未触发: {summary.get('not_triggered_count', 0)}")

        # 触发的 Skill
        triggered = match_result.get('triggered', [])
        if triggered:
            lines.append(f"\n### [✓ 触发] {len(triggered)} 条")
            for s in triggered:
                adj = s.get('regime_adjustment', {})
                lines.append(f"\n**{s['name']}** (信号强度{s['signal_strength']}"
                             f" → 环境调整后{adj.get('adjusted_strength', s['signal_strength'])})")
                lines.append(f"  信号方向: {s['signal_direction']}")
                lines.append(f"  核心思想: {s['core_idea'][:100]}")
                for c in s.get('conditions', []):
                    if c.get('status') == 'triggered':
                        lines.append(f"  - {c.get('evidence', '')}")
                # 教材胜率提示
                wr = s.get('win_rate_hint', {})
                if wr:
                    lines.append(f"  教材胜率参考: {', '.join(f'{k}={v*100:.0f}%' for k, v in wr.items())}")
                # 历史验证胜率（让 LLM 自行判断该 Skill 的可信度）
                perf = s.get('performance', {})
                if perf.get('win_rate') is not None:
                    lines.append(
                        f"  历史验证胜率: {perf['win_rate']*100:.0f}%"
                        f"（{perf.get('used_count', 0)}次验证）")
                if adj.get('regime_win_rate') is not None:
                    lines.append(f"  当前环境胜率: {adj['regime_win_rate']*100:.0f}%")
                for reason in adj.get('reason', []):
                    lines.append(f"  环境适配: {reason}")

        # 准触发的 Skill
        near = match_result.get('near_triggered', [])
        if near:
            lines.append(f"\n### [⚠ 准触发] {len(near)} 条")
            for s in near:
                lines.append(f"\n**{s['name']}** (差{s.get('gap_pct', 0):.1f}%)")
                lines.append(f"  核心思想: {s['core_idea'][:80]}")
                for c in s.get('conditions', []):
                    if c.get('status') == 'near':
                        lines.append(f"  - {c.get('evidence', '')}")
                lines.append("  注意: 接近阈值，若继续发展可能触发")

        # 未触发的 Skill（作为排除项）
        not_trig = match_result.get('not_triggered', [])
        if not_trig:
            lines.append(f"\n### [✗ 未触发] {len(not_trig)} 条")
            for s in not_trig[:5]:  # 只显示前5条，避免太长
                lines.append(f"  - {s['name']}: {s.get('reason', '条件不满足')}")
            if len(not_trig) > 5:
                lines.append(f"  ... 等共 {len(not_trig)} 条")

        return '\n'.join(lines)
