"""Bug 修复回归测试

覆盖 2026-07 全面审查中修复的关键 bug：
- Skill 触发指标名解析（alias_map + raw OHLCV + pattern 触发）
- Portfolio 现金持久化
- 交易状态 planned→open 流转
- 空头止损方向
- min_lot 静默突破限制
- 跟踪模块关键价位方向判断
- rule_index by_regime 格式化
- auto_validator 空头结果计算 / 止损出场盈亏一致性
- _safe_parse_json 返回非 dict
- feedback_loop 覆盖更新残留验证状态
"""

import json
import os

import pandas as pd
import pytest

os.environ['DEEPSEEK_API_KEY'] = 'test-key'

DATA_FILE = 'data/300502.csv'

# 单只股票 OHLCV 无法计算的指标（市场广度/情绪/交易参数/形态几何参数），
# 这些条件评估为 unknown 是预期行为，不属于回归。
KNOWN_UNRESOLVABLE = {
    'ad_line', 'arms_index', 'arms_index_10ma', 'open_trin', 'tick_index',
    'mcclellan_oscillator', 'mcclellan_sum_index', 'hpi_value', 'di_value',
    'bullish_consensus', 'consensus_bullish', 'bullish_ratio', 'sentiment_consensus',
    'correlation_coefficient', 'capital', 'position_size', 'risk_amount',
    'profit_loss', 'profit_loss_ratio', 'profit_target', 'reward_risk_ratio',
    'equity_curve', 'avg_trade_pnl', 'month', 'timeframe', '持仓量',
    'bottom_separation_days', 'neckline_slope', 'left_shoulder_height',
    'distance_to_apex_pct', 'width', 'price_retracement_pct',
    'price_change_since_breakout', 'price_vs_trendline', 'price_vs_trendline_pct',
    'trendline_break', 'sma3_vs_sma9_diff', 'close_vs_sma5_diff',
    'sma5_vs_sma20', 'sma6_vs_sma18', 'sma_cross_signal', 'price_move_pct',
    'price_range', 'price_trend', 'momentum_prev', 'price_vs_sar',
    'daily_high - daily_low', 'price_change_2m_pct',
    # 需要 >=200 天数据（测试数据只有 100 行）
    'sma200', 'price_vs_sma200_pct',
}


@pytest.fixture(scope='module')
def features():
    from utils.feature_extractor import FeatureExtractor
    df = pd.read_csv(DATA_FILE)
    return FeatureExtractor().extract_all(df)


class TestSkillTriggerResolution:
    """Skill 触发条件中的指标名必须能解析出数值

    回归背景：修复前 110 个指标名中 91 个（83%）无法解析，
    连 close/pattern 都不行，1209 条 Skill 大部分永远不会触发。
    """

    def test_raw_ohlcv_resolvable(self, features):
        from utils.skill_matcher import SkillMatcher
        sm = SkillMatcher()
        for ind in ('close', 'open', 'high', 'low', 'volume'):
            assert sm._get_indicator_value(features, ind) is not None, ind

    def test_prompt_spec_names_resolvable(self, features):
        """提取 prompt 教给 LLM 的指标命名规范必须全部可解析"""
        from utils.skill_matcher import SkillMatcher
        sm = SkillMatcher()
        names = [
            'rsi_14', 'macd_line', 'macd_histogram', 'adx_value', 'sma20',
            'stochastic_k', 'stochastic_d', 'obv_value', 'obv_trend',
            'volume_ratio', 'volume_trend', 'atr_value', 'bollinger_percent_b',
            'bollinger_bandwidth', 'historical_volatility', 'chaikin_oscillator',
            'divergence_count', 'divergence_bullish_count',
            'divergence_primary_signal', 'trend_stage', 'adx_change_10d_pct',
            'extreme_deviation', 'volatility_state', 'volatility_squeeze',
            'rsi_change_5d', 'macd_hist_acceleration', 'momentum_direction',
            'mtf_alignment', 'mtf_long_trend_intact', 'mtf_short_turning',
            'momentum', 'roc_12', 'macd_trend', 'adx_signal',
            'price_vs_sma20_pct', 'sma20_vs_sma50', 'trend',
        ]
        for name in names:
            assert sm._get_indicator_value(features, name) is not None, name

    def test_extra_sma_periods_resolvable(self, features):
        from utils.skill_matcher import SkillMatcher
        sm = SkillMatcher()
        for p in (3, 4, 5, 9, 10, 13, 21, 40, 65, 90):
            assert sm._get_indicator_value(features, f'sma{p}') is not None, f'sma{p}'

    def test_all_rulebook_indicators_resolvable_or_whitelisted(self, features):
        """规则库中所有指标名：要么可解析，要么在已知不可计算白名单中"""
        from utils.skill_matcher import SkillMatcher
        sm = SkillMatcher()
        inds = set()
        with open('data/skill_rules.jsonl', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if r.get('status') != 'active':
                    continue
                for c in (r.get('trigger') or {}).get('conditions', []):
                    inds.add(c.get('indicator', ''))

        failures = []
        for ind in sorted(inds):
            if ind in ('pattern', 'pattern_detected') or ind in KNOWN_UNRESOLVABLE:
                continue
            if sm._get_indicator_value(features, ind) is None:
                failures.append(ind)
        assert failures == [], f'新增不可解析指标: {failures}（应加别名或加入白名单）'

    def test_pattern_trigger_detected(self, features):
        """indicator='pattern' 必须按形态名匹配，而不是当数值指标解析"""
        from utils.skill_matcher import SkillMatcher
        sm = SkillMatcher()
        # 注入合成形态：真实行情数据不保证任何时刻都有形态检出，
        # 本测试验证的是匹配逻辑而非检测器
        features['pattern']['patterns_detected'] = [
            {'name': 'Double Bottom', 'confidence': 0.8, 'direction': 'bullish'},
        ]

        result = sm._evaluate_pattern_condition(features, '=', 'Double Bottom')
        assert result['status'] == 'triggered'

        result = sm._evaluate_pattern_condition(features, '=', 'Nonexistent Pattern XYZ')
        assert result['status'] == 'not_triggered'

        result = sm._evaluate_pattern_condition(features, '!=', 'Nonexistent Pattern XYZ')
        assert result['status'] == 'triggered'

    def test_pattern_trigger_end_to_end(self, features):
        """完整条件评估：pattern 条件不再返回 unknown"""
        from utils.skill_matcher import SkillMatcher
        sm = SkillMatcher()
        features['pattern']['patterns_detected'] = [
            {'name': 'Double Bottom', 'confidence': 0.8, 'direction': 'bullish'},
        ]
        rule = {
            'rule_id': 'test', 'name': 'test',
            'trigger': {'conditions': [
                {'indicator': 'pattern', 'operator': '=', 'value': 'Double Bottom'}],
                'logic': 'AND'},
            'signal': {'direction': 'bullish', 'strength': 0.6},
        }
        result = sm._evaluate_conditions(
            rule['trigger']['conditions'], 'AND', features, rule)
        assert result['status'] == 'triggered'


class TestPortfolioCashPersistence:
    """回归：cash 保存在 capital 段下，重载后不得回血到初始资金"""

    def test_cash_survives_reload(self, tmp_path):
        from utils.portfolio import Portfolio
        pf = str(tmp_path / 'portfolio.json')

        p = Portfolio(initial_capital=100000, portfolio_file=pf)
        p.cash = 42000  # 模拟开仓后的现金
        p._save()

        p2 = Portfolio(initial_capital=100000, portfolio_file=pf)
        assert p2.cash == 42000

    def test_trade_history_not_truncated(self, tmp_path):
        from utils.portfolio import Portfolio
        pf = str(tmp_path / 'portfolio.json')
        p = Portfolio(initial_capital=100000, portfolio_file=pf)
        p.trade_history = [{'id': i} for i in range(120)]
        p._save()

        p2 = Portfolio(initial_capital=100000, portfolio_file=pf)
        assert len(p2.trade_history) == 120


class TestTradeStatusFlow:
    """回归：validate 只接受 open 状态；planned 必须给出清晰错误"""

    def test_validate_rejects_planned_with_clear_message(self, tmp_path):
        from utils.auto_validator import AutoValidator
        trades_file = str(tmp_path / 'trades.jsonl')
        trade = {
            'trade_id': 't1', 'symbol': 'AAPL', 'status': 'planned',
            'plan': {'entry': {'price': 100, 'date': '2026-01-01'},
                     'target': {'price': 110}, 'stop_loss': {'price': 95},
                     'direction': 'long'},
        }
        with open(trades_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(trade) + '\n')

        v = AutoValidator(trades_file=trades_file,
                          portfolio_file=str(tmp_path / 'p.json'))
        result = v.validate_trade('t1')
        assert 'not opened' in result['error']

    def test_pending_validations_finds_open_trades(self, tmp_path):
        from utils.auto_validator import AutoValidator
        trades_file = str(tmp_path / 'trades.jsonl')
        for tid, status in [('t_open', 'open'), ('t_planned', 'planned')]:
            trade = {'trade_id': tid, 'status': status,
                     'planned_verification_date': '2020-01-01'}
            with open(trades_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(trade) + '\n')

        v = AutoValidator(trades_file=trades_file,
                          portfolio_file=str(tmp_path / 'p.json'))
        pending = v.find_pending_validations('2026-01-01')
        assert [t['trade_id'] for t in pending] == ['t_open']


class TestShortDirection:
    """回归：空头止损必须在入场价上方"""

    def _features(self):
        return {
            'trend': {'price': 100.0},
            'volatility': {'atr': {'value': 5.0, 'pct_of_price': 5.0}},
            'trend_stage': {'stage': 'middle', 'extreme_deviation': False},
        }

    def test_short_stop_above_entry(self):
        from utils.trade_planner import TradePlanner
        tp = TradePlanner()
        stop = tp._select_stop_loss(self._features(), None, 'short')
        assert stop['price'] > 100.0

    def test_long_stop_below_entry(self):
        from utils.trade_planner import TradePlanner
        tp = TradePlanner()
        stop = tp._select_stop_loss(self._features(), None, 'long')
        assert stop['price'] < 100.0

    def test_volatility_adjusted_short(self):
        from utils.position_sizer import PositionSizer
        result = PositionSizer.volatility_adjusted(
            100000, 2.0, 100, 5, direction='short')
        assert result['stop_price'] > 100

    def test_create_plan_reads_phase4_direction(self):
        """回归：create_plan 必须读到 phase4.direction（而非永远 NEUTRAL）"""
        from utils.trade_planner import TradePlanner
        tp = TradePlanner()
        analysis = {'phase4_conclusion': {
            'direction': 'BEARISH', 'confidence': 70,
            'target_price': 90, 'stop_loss': 105,
        }}
        plan = tp.create_plan(analysis, self._features(), 'AAPL', 'AAPL')
        assert plan['plan']['direction'] == 'short'
        assert plan['plan']['stop_loss']['price'] > 100


class TestPositionSizerLimits:
    """回归：min_lot 补齐不得静默突破仓位上限或总资金"""

    def test_min_lot_exceeds_max_position_returns_error(self):
        from utils.position_sizer import PositionSizer
        # capital 10万，上限10%=1万，A股一手100股*150元=1.5万 > 上限
        result = PositionSizer.fixed_risk(
            100000, 2.0, 150, 50, max_position_pct=10.0, min_lot_size=100)
        assert 'error' in result

    def test_min_lot_exceeds_capital_returns_error(self):
        from utils.position_sizer import PositionSizer
        result = PositionSizer.fixed_risk(
            5000, 2.0, 100, 50, min_lot_size=100)
        assert 'error' in result

    def test_min_lot_bump_warns_and_recomputes_risk(self):
        from utils.position_sizer import PositionSizer
        # 风险预算 2000 元只够 40 股，补到 100 股后实际风险 5000
        result = PositionSizer.fixed_risk(
            100000, 2.0, 100, 50, min_lot_size=100)
        assert result['shares'] == 100
        assert result['risk_amount'] == 5000
        assert 'warnings' in result


class TestTrackingKeyLevels:
    """回归：止损在下方被跌破触发，目标在上方被突破触发"""

    def _checker(self):
        from utils.tracking_module import TrackingModule
        tm = TrackingModule.__new__(TrackingModule)  # 避开 __init__ 的文件依赖
        return tm

    def test_stop_triggers_when_price_falls_below(self):
        tm = self._checker()
        status = tm._check_key_levels({'止损位': 95.0}, 100.0, None)
        assert '未触发' in status['止损位']
        status = tm._check_key_levels({'止损位': 95.0}, 94.0, None)
        assert '已跌破' in status['止损位']

    def test_target_triggers_when_price_rises_above(self):
        tm = self._checker()
        status = tm._check_key_levels({'目标位': 120.0}, 125.0, None)
        assert '已突破' in status['目标位']
        status = tm._check_key_levels({'目标位': 120.0}, 110.0, None)
        assert '未触发' in status['目标位']

    def test_zero_level_no_crash(self):
        tm = self._checker()
        status = tm._check_key_levels({'止损位': 0}, 100.0, None)
        assert '无效' in status['止损位']


class TestRuleIndexFormatting:
    """回归：by_regime 是 dict 统计结构，格式化不得 TypeError"""

    def test_format_rule_with_by_regime_dict(self):
        from utils.rule_index import RuleIndex
        ri = RuleIndex.__new__(RuleIndex)
        rule = {
            'rule_id': 'r1', 'name': '测试规则', 'category': 'trend',
            'core_idea': '测试', 'definition': '测试',
            'performance': {
                'used_count': 10, 'wins': 6, 'losses': 4, 'win_rate': 0.6,
                'by_regime': {'trending_up': {'used': 5, 'wins': 4, 'losses': 1}},
            },
        }
        text = ri._format_rule_for_prompt(rule)
        assert '分环境胜率' in text
        assert '80%' in text  # 4/5

    def test_load_skips_lines_without_rule_id(self, tmp_path):
        from utils.rule_index import RuleIndex
        rules_file = str(tmp_path / 'rules.jsonl')
        with open(rules_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps({'name': '没有ID的规则'}) + '\n')
            f.write(json.dumps({'rule_id': 'ok1', 'name': '正常规则'}) + '\n')
        ri = RuleIndex(rules_file=rules_file)
        assert len(ri._rules) == 1

    def test_get_rules_by_regime_no_duplicates(self, tmp_path):
        from utils.rule_index import RuleIndex
        rules_file = str(tmp_path / 'rules.jsonl')
        # 通用规则（无 applicable_regimes）不应在结果中出现两次
        rule = {'rule_id': 'g1', 'name': '通用', 'category': 'trend',
                'status': 'active', 'applicable_regimes': [],
                'performance': {}, 'weight': 1.0}
        with open(rules_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(rule) + '\n')
        ri = RuleIndex(rules_file=rules_file)
        result = ri.get_rules_by_regime('trending_up', ['trend'])
        ids = [r['rule_id'] for r in result['trend']]
        assert ids == ['g1']


class TestAutoValidatorOutcome:
    """回归：空头计算不崩溃；止损出场后盈亏与出场价一致"""

    def _validator(self, tmp_path):
        from utils.auto_validator import AutoValidator
        return AutoValidator(trades_file=str(tmp_path / 't.jsonl'),
                             portfolio_file=str(tmp_path / 'p.json'))

    def test_short_outcome_no_unbound_error(self, tmp_path):
        v = self._validator(tmp_path)
        path = [{'date': f'2026-01-{d:02d}', 'open': 100, 'high': 101,
                 'low': 96, 'close': 98, 'volume': 1000} for d in range(1, 6)]
        outcome = v._calculate_outcome(100, 90, 110, 'short', path)
        assert 'target_reached_date' in outcome
        assert outcome['pnl_pct'] > 0  # 价格跌了，空头盈利

    def test_stop_hit_pnl_consistent_with_exit_price(self, tmp_path):
        v = self._validator(tmp_path)
        # 先跌破止损 95，再反弹收 102：止损出场，盈亏必须为止损亏损而非盈利
        path = [
            {'date': '2026-01-01', 'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 1},
            {'date': '2026-01-02', 'open': 99, 'high': 99, 'low': 94, 'close': 94.5, 'volume': 1},
            {'date': '2026-01-03', 'open': 96, 'high': 103, 'low': 96, 'close': 102, 'volume': 1},
        ]
        outcome = v._calculate_outcome(100, 110, 95, 'long', path)
        assert outcome['exit_reason'] == 'stop_hit'
        assert outcome['exit_price'] == 95
        assert outcome['pnl_pct'] == pytest.approx(-5.0)
        assert outcome['direction_correct'] is False


class TestSafeParseJson:
    """回归：LLM 返回 JSON 数组时也必须返回 dict"""

    def test_array_wrapped_in_dict(self):
        from utils.llm_client import _safe_parse_json
        result = _safe_parse_json('[1, 2, 3]')
        assert isinstance(result, dict)
        assert result['data'] == [1, 2, 3]

    def test_object_returned_as_is(self):
        from utils.llm_client import _safe_parse_json
        assert _safe_parse_json('{"a": 1}') == {'a': 1}


class TestFeedbackOverwrite:
    """回归：同日覆盖分析必须清除旧验证状态、保留未提供的 skills_used"""

    def test_overwrite_clears_validation_state(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        os.makedirs('data', exist_ok=True)
        from utils.feedback_loop import FeedbackLoop
        fl = FeedbackLoop()

        fl.record_analysis({'symbol': 'AAPL'}, skills_used=['s1'])
        fl.records[0]['validated'] = True
        fl.records[0]['outcome'] = 'loss'
        fl.records[0]['actual_return_pct'] = -5.0

        r2 = fl.record_analysis({'symbol': 'AAPL'})  # 同日覆盖，不传 skills_used
        assert r2['is_update'] is True
        rec = fl.records[0]
        assert rec['validated'] is False
        assert 'outcome' not in rec
        assert rec['skills_used'] == ['s1']  # 保留旧值
