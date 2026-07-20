import os

from utils.report_generator import ReportGenerator

os.environ['DEEPSEEK_API_KEY'] = 'test-key'


def test_report_generator_init():
    """验证报告生成器能正确初始化"""
    generator = ReportGenerator()
    assert generator is not None
