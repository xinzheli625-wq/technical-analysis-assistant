"""环境检测统一 / 胜率权重 / 数据缓存 / 契约自动化的回归测试（2026-07）"""

import json
import os

import pandas as pd
import pytest

os.environ['DEEPSEEK_API_KEY'] = 'test-key'


@pytest.fixture(scope='module')
def features():
    from utils.feature_extractor import FeatureExtractor
    df = pd.read_csv('data/300502.csv')
    return FeatureExtractor().extract_all(df)


class TestRegimeMapping:
    """MarketRegimeDetector → matcher 标签映射"""

    def test_late_extreme(self):
        from utils.market_regime import to_matcher_regime
        assert to_matcher_regime('trending_up', 'late', True) == 'trending_up_late_extreme'
        assert to_matcher_regime('trending_up', 'late', False) == 'trending_up_late'

    def test_mature_and_early(self):
        from utils.market_regime import to_matcher_regime
        assert to_matcher_regime('trending_up', 'mature') == 'trending_up_strong'
        assert to_matcher_regime('trending_up', 'early') == 'trending_up'

    def test_other_primaries(self):
        from utils.market_regime import to_matcher_regime
        assert to_matcher_regime('trending_down', 'late') == 'trending_down'
        assert to_matcher_regime('ranging', 'tight') == 'ranging'
        assert to_matcher_regime('volatile', 'expansion') == 'volatile'
        assert to_matcher_regime('unknown') == 'mixed'


class TestExternalRegimeUsed:
    """传入外部环境标签时，matcher 不得使用内置启发式"""

    def test_match_uses_external_regime(self, features):
        from utils.skill_matcher import SkillMatcher
        sm = SkillMatcher()
        result = sm.match(features, 'ranging')
        assert result['market_regime'] == 'ranging'
        # 内置启发式对该数据会判为别的值（ADX=16.5 → ranging，恰好相同，
        # 所以换一个必然不同的标签验证）
        result2 = sm.match(features, 'trending_up_late_extreme')
        assert result2['market_regime'] == 'trending_up_late_extreme'


class TestWinRateWeighting:
    """历史胜率微调权重（不淘汰 Skill）"""

    def _make_rule(self, win_rate, used_count):
        return {
            'rule_id': 'test_wr', 'name': '测试胜率调整',
            'trigger': {'conditions': [
                {'indicator': 'rsi', 'operator': '>', 'value': 0}], 'logic': 'AND'},
            'signal': {'direction': 'bullish', 'strength': 0.5},
            'performance': {
                'used_count': used_count, 'wins': int(used_count * win_rate),
                'losses': used_count - int(used_count * win_rate),
                'win_rate': win_rate,
                'by_regime': {'ranging': {'used': 5, 'wins': 4, 'losses': 1}},
            },
        }

    def test_high_win_rate_boosts_strength(self, features):
        from utils.skill_matcher import SkillMatcher
        sm = SkillMatcher()
        rule = self._make_rule(0.9, 10)
        result = sm._evaluate_conditions(
            rule['trigger']['conditions'], 'AND', features, rule)
        adj = sm._apply_regime_adjustment(result['detail'], 'ranging', features)
        assert adj['adjustment'] > 0
        assert adj['adjusted_strength'] > adj['original_strength']
        # 当前环境胜率 4/5=80% 应被计算
        assert adj['regime_win_rate'] == pytest.approx(0.8)

    def test_low_win_rate_reduces_strength(self, features):
        from utils.skill_matcher import SkillMatcher
        sm = SkillMatcher()
        rule = self._make_rule(0.2, 10)
        result = sm._evaluate_conditions(
            rule['trigger']['conditions'], 'AND', features, rule)
        adj = sm._apply_regime_adjustment(result['detail'], 'ranging', features)
        assert adj['adjustment'] < 0

    def test_small_sample_no_adjustment(self, features):
        from utils.skill_matcher import SkillMatcher
        sm = SkillMatcher()
        rule = self._make_rule(0.9, 3)  # 样本 <5 不启用
        result = sm._evaluate_conditions(
            rule['trigger']['conditions'], 'AND', features, rule)
        adj = sm._apply_regime_adjustment(result['detail'], 'mixed', features)
        assert adj['adjustment'] == 0

    def test_format_for_llm_shows_win_rates(self, features):
        from utils.skill_matcher import SkillMatcher
        sm = SkillMatcher()
        rule = self._make_rule(0.75, 10)
        result = sm._evaluate_conditions(
            rule['trigger']['conditions'], 'AND', features, rule)
        detail = result['detail']
        detail['regime_adjustment'] = sm._apply_regime_adjustment(
            detail, 'ranging', features)
        text = SkillMatcher.format_for_llm({
            'triggered': [detail], 'near_triggered': [], 'not_triggered': [],
            'summary': {'total_skills': 1, 'triggered_count': 1,
                        'near_triggered_count': 0, 'not_triggered_count': 0},
        })
        assert '历史验证胜率: 75%' in text
        assert '当前环境胜率: 80%' in text


class TestPromptContractSync:
    """提取 prompt 的指标白名单必须与 alias_map 同步"""

    def test_prompt_contains_all_aliases(self):
        from utils.skill_knowledge import build_segment_extract_prompt
        from utils.skill_matcher import build_alias_map
        prompt = build_segment_extract_prompt()
        missing = [name for name in build_alias_map() if name not in prompt]
        assert missing == [], f'prompt 缺少别名: {missing}'

    def test_prompt_contains_pattern_spec(self):
        from utils.skill_knowledge import build_segment_extract_prompt
        prompt = build_segment_extract_prompt()
        assert '"indicator": "pattern"' in prompt
        assert 'Double Bottom' in prompt


class TestDataCache:
    """数据源当日缓存"""

    def test_cache_roundtrip(self, tmp_path, monkeypatch):
        import utils.data_source as ds
        monkeypatch.setattr(ds, 'CACHE_DIR', str(tmp_path))
        df = pd.DataFrame({
            'open': [1, 2], 'high': [1, 2], 'low': [1, 2],
            'close': [1, 2], 'volume': [100, 200],
        }, index=pd.date_range('2026-07-19', periods=2))

        ds._write_cache('TEST', 'cn', df)
        loaded = ds._read_cache('TEST', 'cn', 100)
        assert loaded is not None
        assert len(loaded) == 2
        assert list(loaded['close']) == [1, 2]

    def test_download_uses_cache(self, tmp_path, monkeypatch):
        import utils.data_source as ds
        monkeypatch.setattr(ds, 'CACHE_DIR', str(tmp_path))
        df = pd.DataFrame({
            'open': [1.0] * 70, 'high': [1.0] * 70, 'low': [1.0] * 70,
            'close': [1.0] * 70, 'volume': [100.0] * 70,
        }, index=pd.date_range('2026-05-01', periods=70))
        ds._write_cache('CACHED_STOCK', 'us', df)

        # yfinance 不应被调用（有缓存直接返回）
        def boom(*a, **k):
            raise AssertionError('不应走到 yfinance')
        monkeypatch.setattr(ds, '_download_yfinance', boom)
        result = ds.download_daily('CACHED_STOCK', days=60, market='us',
                                   prefer_local=False)
        assert len(result) == 60


class TestSafePrint:
    """GBK 控制台打印 Unicode 符号不崩溃（Windows 回归）"""

    def test_safe_print_with_unicode_symbols(self, capsys, monkeypatch):
        import io

        from utils.console import safe_print
        # 模拟 GBK stdout
        gbk_out = io.TextIOWrapper(io.BytesIO(), encoding='gbk')
        monkeypatch.setattr('sys.stdout', gbk_out)
        safe_print("  ⚠ 警告 ✓ ✗ ⊘ ✅")
        gbk_out.flush()
        assert gbk_out.buffer.getvalue()  # 有输出且不抛异常


class TestJsonRepair:
    """LLM 输出里中文语境内嵌双引号的 JSON 修复（2026-07 真实故障）"""

    def test_inner_cjk_quotes_escaped(self):
        from utils.llm_client import _safe_parse_json
        broken = '{"为什么不适用": "无强势"杯柄"中的杯体", "a": 1}'
        parsed = _safe_parse_json(broken)
        assert parsed.get('parse_error') is not True
        assert '杯柄' in parsed['为什么不适用']

    def test_structural_quotes_untouched(self):
        from utils.llm_client import _safe_parse_json
        good = '{"方向": "看多", "置信度": 80}'
        parsed = _safe_parse_json(good)
        assert parsed['方向'] == '看多'


class TestSnapshotJsonSafe:
    """快照保存时 numpy 标量不得让 json.dump 崩溃"""

    def test_numpy_scalars_serialized(self, tmp_path, monkeypatch):
        import numpy as np

        from utils.tracking_module import TrackingModule, _json_safe
        tm = TrackingModule()
        monkeypatch.setattr(tm, 'snapshots_dir', str(tmp_path))
        result = {
            'full_analysis': {'phase4_conclusion': {'direction': 'BEARISH', 'confidence': 70}},
            'indicator_features': {},
            'skill_match_result': {'triggered': []},
            'market_regime': {'primary': 'volatile',
                              'indicators': {'ma_aligned_down': np.bool_(True),
                                             'adx': np.float64(15.2)}},
        }
        tm.save_analysis_snapshot('TEST', result)
        saved = json.load(open(tmp_path / 'TEST.json', encoding='utf-8'))
        assert saved['regime']['indicators']['ma_aligned_down'] is True
        assert _json_safe(np.int64(3)) == 3
