import os
import pandas as pd
from utils.input_adapter import normalize_excel

os.environ['DEEPSEEK_API_KEY'] = 'test-key'


def test_end_to_end_excel_input():
    """端到端测试：Excel -> 标准化数据结构"""
    df = pd.read_csv('data/sample_aapl_daily.csv')
    data = normalize_excel(df, symbol='AAPL', market='US')

    assert data['symbol'] == 'AAPL'
    assert data['market'] == 'US'
    assert len(data['data']) == 10
    assert data['data'][0]['close'] == 186.5


def test_skill_knowledge_loading():
    """测试Skill知识库加载"""
    from utils.skill_knowledge import get_skill_kb

    kb = get_skill_kb()
    trend = kb.get('trend')
    assert 'Wyckoff' in trend or 'Stage' in trend

    patterns = kb.get('patterns')
    assert len(patterns) > 0
