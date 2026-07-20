"""针对本次修复的回归测试"""

import os

os.environ['DEEPSEEK_API_KEY'] = 'test-key'


class TestPositionSizerMarketAware:
    """测试仓位计算的市场感知能力"""

    def test_a_share_uses_100_lot(self):
        from utils.position_sizer import PositionSizer

        result = PositionSizer.fixed_risk(
            capital=1_000_000,
            risk_pct=2.0,
            entry=100.0,
            stop=95.0,
            min_lot_size=100
        )
        assert 'error' not in result
        assert result['shares'] % 100 == 0
        assert result['shares'] >= 100

    def test_us_stock_uses_1_lot(self):
        from utils.position_sizer import PositionSizer

        result = PositionSizer.fixed_risk(
            capital=1_000_000,
            risk_pct=2.0,
            entry=100.0,
            stop=95.0,
            min_lot_size=1
        )
        assert 'error' not in result
        # 美股不需要是100的整数倍
        assert result['shares'] >= 1

    def test_calculate_position_detects_a_share(self):
        from utils.position_sizer import PositionSizer

        analysis = {
            'phase4_conclusion': {
                'confidence': 60,
                'key_levels': {
                    'trigger': 100.0,
                    'stop_loss': 95.0,
                    'target': 110.0
                }
            }
        }
        features = {
            'volatility': {'atr': {'value': 2.5}}
        }
        result = PositionSizer.calculate_position(
            analysis, features, capital=1_000_000,
            symbol='603773', market='cn'
        )
        assert 'error' not in result
        assert result['shares'] % 100 == 0

    def test_calculate_position_detects_us_stock(self):
        from utils.position_sizer import PositionSizer

        analysis = {
            'phase4_conclusion': {
                'confidence': 60,
                'key_levels': {
                    'trigger': 100.0,
                    'stop_loss': 95.0,
                    'target': 110.0
                }
            }
        }
        features = {
            'volatility': {'atr': {'value': 2.5}}
        }
        result = PositionSizer.calculate_position(
            analysis, features, capital=1_000_000,
            symbol='AAPL', market='us'
        )
        assert 'error' not in result
        # 美股最小 1 股， shares 不需要是 100 倍数
        assert result['shares'] >= 1


class TestTradeIdUnique:
    """测试交易 ID 唯一性"""

    def test_trade_id_contains_uuid(self):
        from utils.trade_planner import TradePlanner

        planner = TradePlanner()
        trade_id = planner._generate_trade_id('AAPL')
        # 应包含 symbol、时间戳、uuid
        assert trade_id.startswith('AAPL_')
        # 最后一段应为 6 位 uuid
        parts = trade_id.split('_')
        assert len(parts[-1]) == 6

    def test_trade_ids_are_unique(self):
        from utils.trade_planner import TradePlanner

        planner = TradePlanner()
        ids = [planner._generate_trade_id('AAPL') for _ in range(100)]
        assert len(set(ids)) == 100


class TestTrackingSnapshotFields:
    """测试跟踪模块能正确读取英文字段名"""

    def test_snapshot_reads_english_p4_fields(self):
        from utils.tracking_module import TrackingModule

        tm = TrackingModule()
        result = {
            'last_close': 150.0,
            'full_analysis': {
                'phase4_conclusion': {
                    'direction': 'BULLISH',
                    'confidence': 75,
                    'target_price': 170.0,
                    'stop_loss': 140.0,
                    'key_levels': {'trigger': 150.0, 'target': 170.0, 'stop_loss': 140.0},
                    'watch_points': ['RSI'],
                    'invalidation_conditions': ['close below 140']
                }
            },
            'indicator_features': {},
            'skill_match_result': {'triggered': []},
            'market_regime': {'primary': 'trending_up'}
        }
        tm.save_analysis_snapshot('AAPL', result)
        snapshot = tm.get_latest_snapshot('AAPL')

        assert snapshot['verdict'] == 'BULLISH'
        assert snapshot['confidence'] == 75
        assert snapshot['target_price'] == '170.0'
        assert snapshot['stop_loss'] == '140.0'
        assert 'trigger' in snapshot['key_levels']

    def test_snapshot_fallback_to_chinese_p4_fields(self):
        from utils.tracking_module import TrackingModule

        tm = TrackingModule()
        result = {
            'last_close': 150.0,
            'full_analysis': {
                'phase4_conclusion': {
                    '方向': 'BEARISH',
                    '置信度': 60,
                    '目标价位': 130.0,
                    '止损价位': 155.0,
                }
            },
            'indicator_features': {},
            'skill_match_result': {'triggered': []},
            'market_regime': {}
        }
        tm.save_analysis_snapshot('TEST_CN', result)
        snapshot = tm.get_latest_snapshot('TEST_CN')

        assert snapshot['verdict'] == 'BEARISH'
        assert snapshot['confidence'] == 60


class TestDataSourceLocalCSV:
    """测试统一数据源本地 CSV 加载"""

    def test_load_sample_csv(self):
        from utils.data_source import _load_local_csv

        df = _load_local_csv('sample_aapl_daily', days=10)
        assert df is not None
        assert len(df) >= 5
        assert all(c in df.columns for c in ['open', 'high', 'low', 'close', 'volume'])


class TestFeedbackValidationFlow:
    """测试反馈验证完整流程"""

    def test_validate_with_dict_return(self):
        from utils.feedback_loop import FeedbackLoop

        feedback = FeedbackLoop(
            records_file='data/test_records_validate.json',
            stats_file='data/test_stats_validate.json'
        )

        analysis = {
            'symbol': 'TSLA',
            'market': 'US',
            'input_type': 'api',
            'pattern_analysis': {'patterns': []},
            'indicator_analysis': {},
            'scoring': {'composite_score': 2.0, 'verdict': 'bullish'}
        }
        record_info = feedback.record_analysis(analysis)
        record_id = record_info['record_id']

        record = feedback.validate_record(
            record_id,
            actual_return_pct=5.0,
            target_reached=True,
            stop_hit=False,
            direction_correct=True,
            max_drawdown_pct=-1.0,
            market_regime='trending_up'
        )

        assert record['validated'] is True
        assert record['outcome'] == 'win'

        # Cleanup
        for f in ['data/test_records_validate.json', 'data/test_stats_validate.json']:
            if os.path.exists(f):
                os.remove(f)
