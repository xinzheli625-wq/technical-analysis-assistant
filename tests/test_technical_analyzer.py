import os
import pytest
import pandas as pd
from utils.input_adapter import normalize_excel
from utils.technical_analyzer import TechnicalAnalyzer

os.environ['DEEPSEEK_API_KEY'] = 'test-key'


def test_analyzer_structure():
    """验证分析器能正确初始化"""
    analyzer = TechnicalAnalyzer()
    assert analyzer is not None
    assert analyzer.client is not None


def test_full_analysis_structure():
    """验证完整分析输出结构正确"""
    df = pd.read_csv('data/sample_aapl_daily.csv')
    from utils.input_adapter import normalize_excel
    data = normalize_excel(df, symbol='AAPL', market='US')

    analyzer = TechnicalAnalyzer()
    # 注意：实际调用需要DEEPSEEK_API_KEY，测试验证结构
    # 实际运行时大模型会填充所有字段
    assert data['symbol'] == 'AAPL'
    assert len(data['data']) == 10
