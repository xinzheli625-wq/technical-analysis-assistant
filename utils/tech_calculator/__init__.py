"""Technical Analysis Calculator - 技术分析多维度计算引擎

设计哲学：
1. 每个分析维度都是独立的计算模块
2. 所有指标用pandas精确计算，不依赖LLM
3. 维度之间可以组合，形成综合分析
4. 新指标可以通过formula_generator自动注册
"""

from .registry import IndicatorRegistry
from .trend import TrendCalculator
from .momentum import MomentumCalculator
from .volatility import VolatilityCalculator
from .volume import VolumeCalculator
from .pattern import PatternDetector
from .levels import LevelCalculator

__all__ = [
    'IndicatorRegistry',
    'TrendCalculator',
    'MomentumCalculator',
    'VolatilityCalculator',
    'VolumeCalculator',
    'PatternDetector',
    'LevelCalculator',
]
