"""核心技术分析引擎 - 大模型+精确指标数据+Skill上下文

架构：
1. FeatureExtractor 精确计算所有技术指标（数学，无幻觉）
2. 指标数据格式化后注入 LLM Prompt
3. LLM 基于精确数据 + Skill 上下文进行分析推理
4. 输出结构化分析结果
"""

from typing import Dict, List, Any, Optional
import pandas as pd
from utils.llm_client import DeepSeekClient
from utils.feature_extractor import FeatureExtractor
from utils.skill_matcher import SkillMatcher


class TechnicalAnalyzer:
    """技术分析引擎 - SkillMatcher系统精确匹配 + 单轮全局LLM分析"""

    def __init__(self, api_key: Optional[str] = None):
        self.client = DeepSeekClient(api_key=api_key)
        self.feature_extractor = FeatureExtractor()
        self.skill_matcher = SkillMatcher()

    def run_full_analysis(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """运行完整的技术分析（新架构：SkillMatcher + 单轮全局分析）

        新架构流程：
        1. 数据准备 + 精确指标计算
        2. SkillMatcher系统精确匹配所有Skill触发条件
        3. 单轮全局LLM分析（analyze_full），一次性完成Phase 1/2/3/4

        Args:
            data: {
                'symbol': str,
                'market': str,
                'df': pd.DataFrame,  # OHLCV数据（优先）
                'data': List[Dict],   # 兼容旧格式
                'input_type': str
            }

        Returns:
            包含完整4阶段分析链的结果
        """
        symbol = data.get('symbol', 'UNKNOWN')
        market = data.get('market', 'UNKNOWN')

        # Step 1: 数据准备 - 统一转为DataFrame
        df = self._prepare_dataframe(data)

        # Step 2: 计算所有技术指标（精确数学计算）
        # 优先使用传入的指标数据（避免重复计算）
        indicator_features = data.get('indicator_features')
        indicator_text = data.get('indicator_text')

        # 如果没有传入，才内部计算
        if indicator_features is None and df is not None and len(df) >= 60:
            try:
                features = self.feature_extractor.extract_all(df)
                indicator_features = features
                indicator_text = self.feature_extractor.format_for_llm(features)
            except Exception:
                pass

        # Step 3: SkillMatcher系统精确匹配（确定性计算，零歧义）
        skill_match = None
        if indicator_features:
            try:
                skill_match = self.skill_matcher.match(indicator_features)
            except Exception:
                pass

        # Step 4: 单轮全局LLM分析（替代之前的7轮独立调用）
        price_data = data.get('data', [])
        full_result = self.client.analyze_full(
            price_data=price_data,
            indicator_text=indicator_text,
            indicator_features=indicator_features,
            skill_match_result=skill_match,
            regime=data.get('market_regime')
        )

        # 构建返回结果（新架构 + 向后兼容）
        result = {
            'symbol': symbol,
            'market': market,
            'input_type': data.get('input_type', 'data'),
            'indicator_features': indicator_features,
            'skill_match_result': skill_match,  # 系统精确匹配结果
            'full_analysis': full_result,  # Phase 1/2/3/4 完整分析
        }

        # 向后兼容：将新架构结果映射到旧字段
        p1 = full_result.get('phase1_indicator_inventory', {})
        p2 = full_result.get('phase2_skill_application', {})
        p3 = full_result.get('phase3_synergy_conflict', {})
        p4 = full_result.get('phase4_conclusion', {})

        result['trend_analysis'] = p1.get('trend', {})
        result['pattern_analysis'] = p1.get('pattern', {})
        result['indicator_analysis'] = p1.get('momentum', {})
        result['volume_price_analysis'] = p1.get('volume', {})
        result['behavior_analysis'] = p3
        result['event_inference'] = p4
        result['scoring'] = p4

        return result

    def _prepare_dataframe(self, data: Dict) -> Optional[pd.DataFrame]:
        """统一数据格式为DataFrame"""
        # 如果已经是DataFrame
        if 'df' in data and isinstance(data['df'], pd.DataFrame):
            return data['df']

        # 从List[Dict]转换
        price_data = data.get('data', [])
        if not price_data:
            return None

        df = pd.DataFrame(price_data)

        # 标准化列名
        column_mapping = {
            '日期': 'date', 'Date': 'date',
            '开盘': 'open', 'Open': 'open',
            '收盘': 'close', 'Close': 'close',
            '最高': 'high', 'High': 'high',
            '最低': 'low', 'Low': 'low',
            '成交量': 'volume', 'Volume': 'volume',
        }
        df = df.rename(columns=column_mapping)

        # 确保数值类型
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df

    def analyze_trend(self, price_data: List[Dict],
                      indicator_text: Optional[str] = None) -> Dict[str, Any]:
        """Step 2: 趋势分析 -> DeepSeek + 精确指标数据"""
        return self.client.analyze_trend(price_data, indicator_text=indicator_text)

    def analyze_patterns(self, price_data: List[Dict],
                         indicator_text: Optional[str] = None) -> Dict[str, Any]:
        """Step 3: 形态识别 -> DeepSeek + 精确指标数据"""
        return self.client.analyze_patterns(price_data, indicator_text=indicator_text)

    def analyze_indicators(self, price_data: List[Dict],
                           indicator_text: Optional[str] = None,
                           indicator_features: Optional[Dict] = None) -> Dict[str, Any]:
        """Step 4: 指标分析 -> DeepSeek + 精确指标数据"""
        return self.client.analyze_indicators(
            price_data,
            indicator_text=indicator_text,
            indicator_features=indicator_features
        )

    def analyze_volume_price(self, price_data: List[Dict],
                             indicator_text: Optional[str] = None,
                             indicator_features: Optional[Dict] = None) -> Dict[str, Any]:
        """Step 5: 量价分析 -> DeepSeek + 精确指标数据"""
        return self.client.analyze_volume_price(
            price_data,
            indicator_text=indicator_text,
            indicator_features=indicator_features
        )

    def analyze_behavior(self, all_signals: Dict[str, Any],
                         indicator_text: Optional[str] = None) -> Dict[str, Any]:
        """Step 6: 资金行为解读 -> DeepSeek + 精确指标数据"""
        return self.client.analyze_behavior(all_signals, indicator_text=indicator_text)

    def infer_events(self, all_signals: Dict[str, Any],
                     indicator_text: Optional[str] = None) -> Dict[str, Any]:
        """Step 7: 基本面事件推断 -> DeepSeek + 精确指标数据"""
        return self.client.infer_events(all_signals, indicator_text=indicator_text)

    def calculate_score(self, all_signals: Dict[str, Any],
                        indicator_text: Optional[str] = None) -> Dict[str, Any]:
        """Step 8: 多维度评分 -> DeepSeek + 精确指标数据"""
        return self.client.calculate_score(all_signals, indicator_text=indicator_text)

    def quick_indicator_summary(self, df: pd.DataFrame) -> str:
        """快速获取指标摘要文本（用于即时查询）"""
        if len(df) < 60:
            return "数据不足（需要至少60个交易日）"

        features = self.feature_extractor.extract_all(df)
        return self.feature_extractor.format_for_llm(features)
