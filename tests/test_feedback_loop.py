import os
from utils.feedback_loop import FeedbackLoop

os.environ['DEEPSEEK_API_KEY'] = 'test-key'


def test_feedback_loop_record():
    feedback = FeedbackLoop(
        records_file='data/test_records.json',
        stats_file='data/test_stats.json'
    )

    analysis = {
        'symbol': 'AAPL',
        'market': 'US',
        'input_type': 'excel',
        'pattern_analysis': {'patterns': [{'name': 'Cup with Handle', 'type': 'continuation', 'confidence': 85}]},
        'indicator_analysis': {'rsi': {'value': 62, 'signal': 'neutral'}},
        'scoring': {'composite_score': 3.2, 'verdict': 'bullish'}
    }

    record_id = feedback.record_analysis(analysis, target_price=210, stop_loss=185, timeframe_days=20)
    assert record_id is not None
    assert len(feedback.records) == 1

    # Cleanup
    for f in ['data/test_records.json', 'data/test_stats.json']:
        if os.path.exists(f):
            os.remove(f)


def test_feedback_loop_statistics():
    feedback = FeedbackLoop(
        records_file='data/test_records2.json',
        stats_file='data/test_stats2.json'
    )

    for i in range(5):
        analysis = {
            'symbol': f'STOCK{i}',
            'market': 'US',
            'input_type': 'excel',
            'pattern_analysis': {'patterns': [{'name': 'Double Bottom', 'type': 'reversal', 'confidence': 70}]},
            'indicator_analysis': {},
            'scoring': {'composite_score': 2.5, 'verdict': 'bullish'}
        }
        rid = feedback.record_analysis(analysis)['record_id']
        is_win = i < 3
        feedback.validate_record(
            rid,
            max_drawdown_pct=-1.5,
            actual_return_pct=5.0 if is_win else -4.0,
            target_reached=is_win,
            stop_hit=not is_win,
            direction_correct=is_win,
        )

    stats = feedback.calculate_statistics()
    assert stats['total_records'] == 5
    assert stats['validated_records'] == 5
    assert stats['overall']['wins'] == 3
    assert stats['overall']['losses'] == 2

    # Cleanup
    for f in ['data/test_records2.json', 'data/test_stats2.json']:
        if os.path.exists(f):
            os.remove(f)
