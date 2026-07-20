"""Indicator Registry - 指标注册中心

所有技术指标的统一注册、管理和调用入口。
支持动态注册（通过formula_generator自动生成的新指标）。
"""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


@dataclass
class IndicatorMeta:
    """指标元数据"""
    name: str                    # 指标英文名称
    name_cn: str                 # 指标中文名称
    category: str                # 所属维度: trend/momentum/volatility/volume/pattern/levels
    description: str             # 指标描述
    formula: str                 # 数学公式（文本描述）
    inputs: List[str]            # 输入字段: [close/high/low/volume]
    outputs: List[str]           # 输出字段
    parameters: Dict[str, Any]   # 默认参数
    source: str                  # 来源: builtin | generated_from_book | generated_from_nl
    created_at: str

    def to_dict(self) -> Dict:
        return asdict(self)


class IndicatorRegistry:
    """指标注册中心 - 单例模式"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._indicators: Dict[str, IndicatorMeta] = {}
            cls._instance._calculators: Dict[str, Callable] = {}
            cls._instance._load_registry()
        return cls._instance

    def register(self, meta: IndicatorMeta, calculator: Callable):
        """注册一个指标

        Args:
            meta: 指标元数据
            calculator: 计算函数，签名: fn(df, **params) -> pd.DataFrame|pd.Series
        """
        self._indicators[meta.name] = meta
        self._calculators[meta.name] = calculator
        self._save_registry()

    def get(self, name: str) -> Optional[IndicatorMeta]:
        """获取指标元数据"""
        return self._indicators.get(name)

    def get_calculator(self, name: str) -> Optional[Callable]:
        """获取指标计算函数"""
        return self._calculators.get(name)

    def list_by_category(self, category: str) -> List[IndicatorMeta]:
        """按维度列出指标"""
        return [m for m in self._indicators.values() if m.category == category]

    def list_all(self) -> List[IndicatorMeta]:
        """列出所有指标"""
        return list(self._indicators.values())

    def calculate(self, name: str, df, **kwargs):
        """执行指标计算"""
        calc = self._calculators.get(name)
        if calc is None:
            raise ValueError(f"Indicator '{name}' not registered")
        return calc(df, **kwargs)

    def _save_registry(self):
        """保存注册表到文件"""
        os.makedirs('data', exist_ok=True)
        data = {
            'updated_at': datetime.now().isoformat(),
            'indicators': {k: v.to_dict() for k, v in self._indicators.items()}
        }
        with open('data/indicator_registry.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_registry(self):
        """从文件加载注册表"""
        filepath = 'data/indicator_registry.json'
        if not os.path.exists(filepath):
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for name, meta_dict in data.get('indicators', {}).items():
                self._indicators[name] = IndicatorMeta(**meta_dict)
            # 注意：calculator函数无法序列化，需要在加载后重新注册
        except (json.JSONDecodeError, TypeError):
            pass

    def get_stats(self) -> Dict[str, Any]:
        """获取注册表统计"""
        categories = {}
        for m in self._indicators.values():
            cat = m.category
            categories[cat] = categories.get(cat, 0) + 1
        return {
            'total': len(self._indicators),
            'by_category': categories,
            'builtins': len([m for m in self._indicators.values() if m.source == 'builtin']),
            'generated': len([m for m in self._indicators.values() if m.source != 'builtin'])
        }


def get_registry() -> IndicatorRegistry:
    """获取全局注册中心"""
    return IndicatorRegistry()
