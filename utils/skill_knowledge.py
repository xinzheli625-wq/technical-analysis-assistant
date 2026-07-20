"""Skill Knowledge Base - 加载reference文件 + 规则索引，动态构建System Prompt

核心改进：
1. 不再一次性注入全部42K token skill内容
2. 采用"核心框架 + 规则索引"双轨制：
   - 核心框架：简短精炼的技术分析体系概述（约2K tokens）
   - 规则索引：按需加载的具体规则（约3-8K tokens，可控）
3. 每个分析场景只加载相关规则，token预算管理
"""

import os
from typing import Dict, List, Any, Optional


SKILLS_DIR = '.claude/skills/technical-analysis-core/references'


# 轻量级 Skill 提取 System Prompt（固定复用，~500 tokens）
# 用于 upload_skill_book / 飞书导入时的分段提取场景
# 不加载 references，只包含输出格式要求
SEGMENT_EXTRACT_SYSTEM_PROMPT = """你是技术分析教材编辑。任务是从用户提供的技术分析文本段落中，提取结构化的方法论教材（Skill）。

## 提取原则
1. 只提取"方法论"——教读者如何结合多个指标进行分析的完整方法，不是零散的知识点
2. 如果段落中没有完整的方法论，提取为"概念/定义"类型
3. 如果段落中只有一个知识点，输出 rules 列表只有一条
4. 如果段落中有多个方法论，输出 rules 列表有多条

## 输出格式（严格JSON）
{
  "rules": [
    {
      "name": "方法论名称（简洁，8字以内）",
      "category": "分类：trend/patterns/indicators/volume_price/behavior/events/scoring",
      "type": "methodology",
      "core_idea": "核心思想：这个方法解决什么问题，在什么场景下使用",
      "analysis_steps": [
        "步骤1：检查什么指标，判断标准是什么",
        "步骤2：结合哪些其他指标确认",
        "步骤3：综合判断的逻辑和出场条件"
      ],
      "reference_data": {
        "关键阈值": "数值参考（如RSI>70，用原文中的值）",
        "典型周期": "指标常用周期（如14日、20日）",
        "其他参数": "原文中提到的其他关键数值"
      },
      "win_rate_hint": {
        "trending_up": 0.0,
        "trending_down": 0.0,
        "ranging": 0.0
      },
      "common_pitfalls": [
        "常见误区1：只看单一指标",
        "常见误区2：忽略市场环境"
      ],
      "when_not_to_use": [
        "不适用场景1",
        "不适用场景2"
      ],
      "trigger": {
        "conditions": [
          {"indicator": "指标名（如rsi_14/macd_line/adx_value/close/sma20等）", "operator": ">|>=|<|<=|=|between", "value": 数值, "value_ref": "可选：引用另一个指标名"}
        ],
        "logic": "AND|OR"
      },
      "signal": {
        "direction": "bullish|bearish|neutral",
        "strength": 0.0
      },
      "applicable_regimes": ["trending_up", "trending_down", "ranging", "volatile"],
      "source_chapter": "来源章节"
    }
  ],
  "summary": "本段核心方法论概述（50字以内）"
}

## 重要规则
1. 所有输出必须使用中文
2. 数值、阈值必须忠实于原文，不能编造
3. 如果原文没有给出胜率数据，win_rate_hint 填 0.0 占位
4. 如果原文没有提到不适用场景，when_not_to_use 留空列表
5. 如果原文没有提到常见误区，common_pitfalls 留空列表
6. **trigger条件必须结构化**：每条方法论都必须提取触发条件。根据analysis_steps中的判断标准，转化为indicator+operator+value的格式。如"RSI>70" → {"indicator": "rsi_14", "operator": ">", "value": 70}
7. **signal方向必须明确**：根据方法论的结论方向填写。看涨方法填bullish，看跌方法填bearish，中性/观望填neutral。strength根据原文信心度填写0.0-1.0
8. 形态类方法（如头肩顶）的trigger可用price_vs_ma、pattern_detected等近似指标，或填{"indicator": "pattern", "operator": "=", "value": "head_and_shoulders"}

## 可用指标名称规范（必须严格使用以下名称）

### 趋势指标
trend: adx, adx_signal, sma20, sma50, sma200, price_vs_sma20_pct, price_vs_sma200_pct, sma20_vs_sma50, supertrend_direction, roc_12, ichimoku_price_vs_kijun

### 动量指标
momentum: rsi, rsi_signal, macd_line, macd_signal, macd_histogram, macd_trend, kdj_k, kdj_d, kdj_j, cci, williams_r, stochastic_k, stochastic_d, momentum, tsi, awesome_oscillator, ultimate_oscillator, ppo_value, stoch_rsi

### 波动率指标
volatility: atr_value, bollinger_percent_b, bollinger_bandwidth, bollinger_position, historical_volatility, ulcer_index

### 量能指标
volume: volume_ratio, volume_trend, obv_value, obv_trend, vwap, mfi, chaikin_oscillator, force_index

### 背离检测（新增）
divergence: divergence_count, divergence_bearish_count, divergence_bullish_count, divergence_primary_signal
- divergence_primary_signal 值: 'bearish'/'bullish'/'none'

### 趋势阶段（新增）
trend_stage: trend_stage, adx_change_10d_pct, ma_deviation_20, ma_deviation_change_10d, price_acceleration, extreme_deviation
- trend_stage 值: 'early'/'early_acceleration'/'middle'/'late'/'fading'/'ranging'
- extreme_deviation 值: true/false

### 波动率状态（新增）
volatility_state: volatility_state, volatility_squeeze, volatility_expansion, squeeze_to_expansion_alert
- volatility_state 值: 'squeeze'/'expansion'/'expanding'/'contracting'/'normal'
- volatility_squeeze/volatility_expansion/squeeze_to_expansion_alert 值: true/false

### 动量加速度（新增）
momentum_accel: rsi_change_5d, macd_hist_acceleration, price_acceleration_state, momentum_direction
- price_acceleration_state 值: 'accelerating'/'decelerating'/'mixed'
- momentum_direction 值: 'strengthening'/'weakening'/'neutral'

### 多时间框架（新增）
multi_timeframe: mtf_alignment, mtf_short_turning, mtf_long_trend_intact
- mtf_alignment 值: 'strongly_bullish'/'bullish'/'strongly_bearish'/'bearish'/'mixed'
- mtf_long_trend_intact 值: true/false

### 形态检测
pattern: pattern_detected
- 可用形态名: 'Double Bottom', 'Head and Shoulders', 'Ascending Triangle', 'Descending Triangle', 'Symmetrical Triangle', 'Cup and Handle', 'Rising Wedge', 'Falling Wedge', 'Flag', 'Pennant', 'Ascending Channel', 'Descending Channel', 'Rectangle', 'Rounded Top', 'Rounded Bottom', 'V-Reversal Bottom', 'V-Reversal Top', 'Island Reversal Top', 'Island Reversal Bottom'
"""


# 每个分析场景需要的规则类别映射
SCENE_RULE_CATEGORIES = {
    'full': ['trend', 'patterns', 'indicators', 'volume_price', 'behavior', 'events', 'scoring'],
    'screenshot': ['patterns', 'indicators', 'volume_price', 'trend'],
    'trend': ['trend'],
    'patterns': ['patterns', 'indicators'],
    'indicators': ['indicators'],
    'volume_price': ['volume_price'],
    'behavior': ['behavior', 'volume_price'],
    'events': ['events', 'behavior'],
    'scoring': ['scoring', 'trend', 'patterns', 'indicators', 'volume_price'],
    'report': ['trend', 'patterns', 'indicators', 'volume_price', 'behavior', 'events', 'scoring'],
    'knowledge_extract': ['trend', 'patterns', 'indicators', 'volume_price', 'behavior', 'events', 'scoring'],
    'nl_instruction': ['trend', 'patterns', 'indicators', 'volume_price', 'behavior', 'events', 'scoring'],
    'attribution': ['patterns', 'indicators', 'trend'],
}


class SkillKnowledgeBase:
    """技术分析Skill知识库 - 动态构建System Prompt"""

    SKILL_FILES = {
        'trend': 'trend-analysis.md',
        'patterns': 'chart-patterns.md',
        'indicators': 'indicators.md',
        'volume_price': 'volume-price-analysis.md',
        'behavior': 'market-behavior.md',
        'events': 'event-inference.md',
        'scoring': 'scoring-framework.md',
    }

    def __init__(self, skills_dir: str = SKILLS_DIR):
        self.skills_dir = skills_dir
        self._raw_cache: Dict[str, str] = {}  # 原始文件内容
        self._core_cache: Dict[str, str] = {}  # 精炼后的核心框架
        self._load_all()

    def _load_all(self):
        """加载并预处理所有skill文件"""
        for name, filename in self.SKILL_FILES.items():
            filepath = os.path.join(self.skills_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                self._raw_cache[name] = content
                self._core_cache[name] = self._extract_core_framework(content)
            else:
                self._raw_cache[name] = f"# {filename} not found"
                self._core_cache[name] = ""

    def _extract_core_framework(self, content: str) -> str:
        """从完整skill文件中提取核心框架（简短版本，约原文30%长度）

        策略：
        - 保留标题和一级目录结构
        - 保留关键定义和阈值
        - 去掉冗长的示例和解释
        """
        lines = content.split('\n')
        core_lines = []
        in_example = False

        for line in lines:
            stripped = line.strip()

            # 保留所有标题行
            if stripped.startswith('#'):
                core_lines.append(line)
                in_example = False
                continue

            # 跳过示例块
            if 'example' in stripped.lower() or '示例' in stripped:
                in_example = True
                continue
            if in_example and (stripped.startswith('```') or stripped == ''):
                in_example = False
                continue
            if in_example:
                continue

            # 保留包含数字/阈值/关键条件的行
            if any(c.isdigit() for c in stripped) or '%' in stripped:
                core_lines.append(line)
                continue

            # 保留表格分隔符和表格行
            if '|' in stripped and ('---' in stripped or any(c in stripped for c in ['>', '<', '='])):
                core_lines.append(line)
                continue

            # 保留"注意"/"规则"/"条件"等关键行
            keywords = ['rule', 'condition', 'threshold', '注意', '规则', '条件', '阈值', '必须', '只能']
            if any(kw in stripped.lower() for kw in keywords):
                core_lines.append(line)
                continue

        return '\n'.join(core_lines)

    def build_prompt(self, scene: str,
                     include_rules: bool = True,
                     max_tokens: int = 8000,
                     df=None) -> str:
        """构建指定场景的System Prompt（核心方法）

        Args:
            scene: 分析场景（screenshot/trend/patterns/...）
            include_rules: 是否包含规则索引库中的具体规则
            max_tokens: 最大token预算
            df: 可选的OHLCV DataFrame，用于市场状态检测和动态Skill选择
        """
        # 市场状态检测（如果提供了数据）
        regime = None
        regime_desc = ""
        applicable_cats = None

        if df is not None and len(df) >= 60:
            try:
                from utils.market_regime import MarketRegimeDetector
                detector = MarketRegimeDetector()
                regime_obj = detector.detect(df)
                regime = regime_obj.primary
                regime_desc = detector.describe(regime_obj)
                applicable_cats = detector.get_applicable_categories(regime_obj)
            except Exception:
                pass  # 市场状态检测失败不影响主流程

        # 确定使用的类别
        categories = SCENE_RULE_CATEGORIES.get(scene, [])
        if not categories:
            categories = list(self.SKILL_FILES.keys())

        # 如果有市场状态检测的推荐类别，取交集（更精准）
        if applicable_cats:
            categories = [c for c in categories if c in applicable_cats] or categories

        parts = []
        estimated_chars = max_tokens * 2.5
        used_chars = 0

        # 0. 市场状态上下文（如果检测到）
        if regime_desc:
            regime_text = f"# 当前市场状态\n{regime_desc}\n"
            parts.append(regime_text)
            used_chars += len(regime_text)

        # 1. 加载核心框架（约占预算30%）
        core_budget = int(estimated_chars * 0.3)
        core_text = self._build_core_section(categories, core_budget)
        parts.append(core_text)
        used_chars += len(core_text)

        # 2. 加载规则索引（按需，约占预算60%）
        if include_rules:
            rule_budget = int(estimated_chars * 0.6)
            try:
                from utils.rule_index import RuleIndex
                rule_index = RuleIndex()
                rules_text = rule_index.get_rules_for_prompt(
                    categories,
                    max_tokens=int(rule_budget / 2.5),
                    regime=regime
                )
                if rules_text and rules_text != "# 暂无具体规则":
                    parts.append(f"\n## 具体规则\n\n{rules_text}")
                    used_chars += len(rules_text)
            except Exception:
                pass

        # 3. 输出格式指导（约占预算10%）
        format_text = self._get_format_guide(scene)
        parts.append(format_text)

        return '\n\n'.join(parts)

    def _build_core_section(self, categories: List[str], max_chars: int) -> str:
        """构建核心框架部分"""
        parts = ["# 技术分析体系框架\n"]
        used = len(parts[0])

        for cat in categories:
            core = self._core_cache.get(cat, '')
            if not core:
                continue

            header = f"\n## {cat.upper()}\n"
            if used + len(header) + len(core) <= max_chars:
                parts.append(header + core)
                used += len(header) + len(core)
            else:
                # 超出预算，只保留标题和第一行
                first_line = core.split('\n')[0] if core else ''
                truncated = header + first_line + "...（省略详细内容）"
                parts.append(truncated)
                break

        return '\n'.join(parts)

    def _get_format_guide(self, scene: str) -> str:
        """获取输出格式指导"""
        guides = {
            'full': """\n# 输出要求（全局综合分析 - 强制4阶段输出）\n\n这是单轮全局分析，你必须一次性分析所有维度，按以下4个Phase结构化输出：\n\n## Phase 1: 全维度指标盘点\n对所有技术指标进行盘点，每个指标给出：\n- 当前数值（精确值）\n- 所处区域/状态（如超买/超卖/中性）\n- 近期趋势方向（上升/下降/走平/背离）\n- 你的判断（偏多/偏空/中性）\n- 判断依据（必须引用具体数值）\n\n涵盖维度：趋势（均线、ADX、趋势阶段）、动量（RSI、MACD、KDJ、背离检测）、波动率（布林带、ATR、squeeze/expansion状态）、量能（成交量、OBV、MFI）、形态（近期高低点、支撑压力位）

**新增要求 - 趋势阶段评估（必须执行）：**
基于以下指标判断当前趋势阶段，并纳入Phase 1输出：
- ADX变化率（10日）：ADX在上升还是下降？
- 均线偏离度变化（10日）：价格在加速远离均线还是回归？
- 价格加速度：近期涨速 vs 前期涨速
- 综合判断：趋势处于 初期(early) / 中期(middle) / 末期(late) / 衰竭(fading) / 震荡(ranging)
- 极端偏离警告：价格是否严重偏离均线（偏离>25%）？

**新增要求 - 背离检测（必须执行）：**
- 价格-RSI背离：价格新高但RSI未新高（顶背离）？或价格新低但RSI未新低（底背离）？
- 价格-MACD背离：价格与MACD histogram是否背离？
- 价格-成交量背离：价格新高但OBV未新高？
- 背离信号强度：每个背离给出0-100的强度评分
- 背离结论：当前是否存在有效背离？方向是bullish还是bearish？

## Phase 2: Skill应用与触发验证
n对每条触发的Skill教材：\n- Skill名称及核心思想\n- 触发条件评估（哪些条件已满足？哪些接近？）\n- 走到分析步骤的哪一步了？结论是什么？\n- 历史胜率参考\n\n对每条准触发的Skill：\n- 还差多少触发？\n- 如果后续如何发展会触发？\n\n对明确未触发的Skill（作为排除项）：\n- 为什么不适用当前情况？\n\n## Phase 3: 跨维度协同与冲突裁决\n这是联合分布分析的核心阶段：\n\n### 3.1 协同识别\n- 哪些指标/Skill指向同一方向？形成什么级别的共振？\n- 价格-动量-量能三维是否一致？\n- 短期-中期-长期时间维度是否一致？\n- 每个协同组合的整体置信度\n\n### 3.2 冲突识别\n- 哪些指标/Skill方向相反？\n- 冲突的双方各自的证据强度\n- 基于以下因素做裁决：\n  * 当前市场状态（趋势市/震荡市/高波动）\n  * 各Skill的历史胜率（分环境胜率优先）\n  * 证据的数学确定性（数值vs形态判断）\n  * 时间框架（短期信号vs中期信号冲突时，中期优先）\n\n### 3.3 主导力量判断\n- 当前市场中哪类力量（多头/空头/中性）占主导？\n- 主导力量的证据链（必须可追溯Phase 1/2的内容）\n\n### 3.4 反转概率评估（新增）
- 当前是否存在趋势反转的信号？（是/否/不确定）
- 反转信号来源：
  * 背离检测：价格-RSI/价格-MACD/价格-OBV是否存在有效背离？
  * 趋势阶段：是否处于late/fading阶段？
  * 动量衰竭：RSI/MACD histogram是否在减速？
  * 极端偏离：价格是否严重偏离均线且开始回归？
  * 波动率变化：是否从squeeze转为expansion？
- 反转方向概率：
  * 看涨反转概率：0-100%（基于底背离+趋势衰竭+支撑位）
  * 看跌反转概率：0-100%（基于顶背离+趋势衰竭+阻力位）
- 延续概率：0-100%（基于趋势阶段early/middle+无背离+动量加速）
- 最终判断：continuation（延续）/ reversal（反转）/ uncertain（不确定）

## Phase 4: 综合结论与风险\n\n### 4.1 最终判断
- 方向：STRONGLY_BULLISH / BULLISH / NEUTRAL / BEARISH / STRONGLY_BEARISH
- 置信度：0-100（必须说明计算逻辑）
- **趋势性质判断（新增）：continuation（趋势延续）/ reversal（趋势反转）/ ranging（区间震荡）**
  * 如果是continuation：说明趋势处于哪个阶段（early/middle/late），还有多大空间
  * 如果是reversal：说明反转信号是什么（背离/极端偏离/形态破位），反转目标位
  * 如果是ranging：说明震荡区间上下沿，突破方向判断
- 关键依据（每条依据必须标注来源：Phase X 的具体内容）

### 4.2 关键价位\n- 目标价位（基于形态/均线/量能推算）\n- 止损价位（基于ATR/支撑位/近期低点）\n- 触发位置（什么价位/指标变化会改变当前判断）\n\n### 4.3 风险因素\n- 主要风险（可能让判断失效的因素）\n- 观察点（后续需要监控的指标/价位变化）\n- 判断失效条件（在什么情况下需要重新评估）\n\n## 输出格式\n输出严格JSON格式：\n{\n  \"phase1_indicator_inventory\": {\n    \"trend\": {...},\n    \"momentum\": {...},\n    \"volatility\": {...},\n    \"volume\": {...},\n    \"pattern\": {...}\n  },\n  \"phase2_skill_application\": {\n    \"triggered\": [...],\n    \"near_triggered\": [...],\n    \"not_triggered\": [...]\n  },\n  \"phase3_synergy_conflict\": {\n    \"synergies\": [...],\n    \"conflicts\": [...],\n    \"dominant_force\": \"...\"\n  },\n  \"phase4_conclusion\": {\n    \"direction\": \"...\",\n    \"confidence\": 0,\n    \"key_evidence\": [...],\n    \"target_price\": null,\n    \"stop_loss\": null,\n    \"risks\": [...],\n    \"watch_points\": [...],\n    \"invalidation_conditions\": [...]\n  }\n}\n\n**重要规则**：
1. 所有输出必须使用中文（包括指标名称、状态描述、判断依据、结论等）
2. 所有结论必须可追溯至Phase 1/2/3的具体内容
3. 不允许跳过任何Phase
4. Phase 3的冲突裁决必须明确说明裁决理由
5. 置信度必须有计算逻辑，不能随意给数字
""",
            'screenshot': """\n# 输出要求\n基于上述体系分析K线图，输出JSON格式分析结果。""",
            'trend': """\n# 输出要求\n输出JSON，必须包含以下Phase：\n\n## Phase 1: 趋势指标盘点\n- 各均线数值及排列状态\n- ADX数值及趋势强度判断\n- 其他趋势指标状态\n\n## Phase 2: Skill应用\n- 哪些趋势分析方法适用？\n- 当前处于什么阶段（如Weinstein阶段）？\n\n## Phase 3: 综合\n- 短期/中期/长期趋势一致性判断\n- 矛盾点及裁决\n\n## Phase 4: 结论\n- 趋势方向及置信度\n- 关键依据\n- 趋势反转风险点""",
            'patterns': """\n# 输出要求\n输出JSON，必须包含以下Phase：\n\n## Phase 1: 形态检测盘点\n- 检测到的形态：名称、置信度、关键点位\n- 未检测到的形态：为什么不符合条件？\n\n## Phase 2: Skill应用\n- 各形态分析方法的应用过程\n- 假形态识别（如假突破的判断）\n\n## Phase 3: 形态协同\n- 多个形态是否指向同一方向？\n- 形态与趋势/动量是否一致？\n\n## Phase 4: 结论\n- 主要形态信号及置信度\n- 形态失效风险""",
            'indicators': """\n# 输出要求\n输出JSON，必须包含以下Phase：\n\n## Phase 1: 指标盘点\n对每个指标给出：\n- 当前数值\n- 所处区域/状态\n- 趋势方向（上升/下降/走平）\n- 你的判断（偏多/偏空/中性）\n- 判断依据\n\n## Phase 2: Skill应用\n对每条Skill教材中的方法：\n- 是否适用当前情况\n- 如适用，走到哪一步了？结论是什么？\n- 如不适用，为什么？\n\n## Phase 3: 协同与冲突\n- 同向共振的信号有哪些？\n- 反向冲突的信号有哪些？你如何裁决？\n\n## Phase 4: 综合判断\n- 方向：UP / DOWN / NEUTRAL\n- 置信度：0-100\n- 关键依据（必须引用Phase 1/2/3的具体内容）\n- 风险点\n\n所有结论必须可追溯。""",
            'volume_price': """\n# 输出要求\n输出JSON，必须包含以下Phase：\n\n## Phase 1: 量能指标盘点\n- 成交量状态（量比、趋势）\n- OBV/MFI/VWAP等量能指标状态\n- 量价关系（同步/背离）\n\n## Phase 2: Skill应用\n- VSA分析方法的应用\n- 吸筹/派发/突破量能判断\n\n## Phase 3: 量价协同\n- 价格信号与量能信号是否一致？\n- 不一致时如何裁决？\n\n## Phase 4: 结论\n- 量能方向判断及置信度\n- 关键量能信号""",
            'behavior': """\n# 输出要求\n输出JSON，必须包含以下Phase：\n\n## Phase 1: 信号盘点\n- 各维度信号汇总\n- 主力/散户行为迹象\n\n## Phase 2: Skill应用\n- 资金行为分析方法的应用\n- 筹码分析过程\n\n## Phase 3: 行为推断\n- 主导力量判断\n- 意图推断（吸筹/洗盘/拉升/出货）\n- 各推断的置信度\n\n## Phase 4: 结论\n- 综合行为判断\n- 关键风险信号""",
            'events': """\n# 输出要求\n输出JSON：inferred_events(事件列表，含probability/confidence/timeframe)、scenario_analysis(情景分析)。""",
            'scoring': """\n# 输出要求\n输出JSON，必须包含以下Phase：\n\n## Phase 1: 各维度评分\n- trend/patterns/indicators/volume_price/behavior/events各维度\n- 每个维度的得分（-5~5）及理由\n\n## Phase 2: 维度协同分析\n- 哪些维度信号一致？\n- 哪些维度矛盾？\n- 矛盾时如何裁决？\n\n## Phase 3: 综合评分\n- 综合得分（-5~5）\n- 评分理由（引用Phase 1/2）\n\n## Phase 4: 结论\n- 最终判断（强烈看多/看多/中性/看空/强烈看空）\n- 置信度\n- 关键风险因素""",
            'report': """\n# 输出要求\n生成专业中文技术分析报告，Markdown格式，包含：趋势评估、形态识别、技术指标、量价分析、资金行为、事件推断、综合评分、风险提示、免责声明。""",
            'knowledge_extract': """\n# 输出要求\n从书籍内容提取技术分析方法论教材，输出JSON。\n\n每条规则应该是一个"教材"——教读者如何结合多个技术指标进行分析，而不是简单的"如果A则B"条件。\n\nrules列表，每条包含：\n{\n  "name": "方法论名称",\n  "category": "分类：trend/patterns/indicators/volume_price/behavior",\n  "type": "methodology",\n  "core_idea": "核心思想：这个方法解决什么问题",\n  "analysis_steps": [\n    "步骤1：检查什么指标，判断标准是什么",\n    "步骤2：结合哪些其他指标确认",\n    "步骤3：综合判断的逻辑"\n  ],\n  "reference_data": {\n    "关键阈值": "数值参考（如RSI>70）",\n    "典型周期": "指标常用周期"\n  },\n  "win_rate_hint": {\n    "trending_up": 0.75,\n    "trending_down": 0.70,\n    "ranging": 0.55\n  },\n  "common_pitfalls": [\n    "常见误区1：只看单一指标",\n    "常见误区2：忽略市场环境"\n  ],\n  "when_not_to_use": [\n    "不适用场景1",\n    "不适用场景2"\n  ],\n  "applicable_regimes": ["trending_up", "trending_down"],\n  "source_chapter": "来源章节"\n}\n\nsummary：书籍核心观点摘要。""",
            'nl_instruction': """\n# 输出要求\n解析用户指令为结构化规则变更，输出JSON：intent/target_file/rule_name/description/conditions/conflict_level/notes。""",
            'attribution': """\n# 输出要求\n判断失败原因，输出JSON：attribution(A-F)/reason/should_adjust_rule/adjustment_type。""",
        }
        return guides.get(scene, "\n# 输出要求\n输出JSON格式结果。")

    def reload(self):
        """重新加载（skill文件更新后调用）"""
        self._raw_cache.clear()
        self._core_cache.clear()
        self._load_all()

    # 兼容旧接口（用于非LLM场景或回退）
    def get(self, name: str) -> str:
        return self._raw_cache.get(name, '')

    def get_all(self) -> str:
        return '\n\n'.join([f"## {k.upper()}\n\n{v}" for k, v in self._raw_cache.items()])


# ========== 跟踪分析 System Prompt ==========

TRACKING_SYSTEM_PROMPT = """你是资深技术分析跟踪评估专家。你的任务是对比上次技术分析的预测与后续实际走势，评估预测的准确性，指出问题，并给出更新后的判断。

## 评估维度

1. **预测符合度**：实际走势是否符合上次分析的预期？
   - 如果判断看跌，价格是否确实下跌？
   - 如果判断看涨，价格是否确实上涨？
   - 目标价位是否触及？止损位是否触及？
   - 关键价位（支撑/阻力）的预测是否准确？

2. **发现的问题**：
   - 上次分析中哪些预测是正确的？哪些是错误的？
   - 是否有被忽略的因素导致了意外走势？
   - 指标信号是否如预期般演变？

3. **更新判断**：
   - 维持原判断 / 修正（调整目标/止损/置信度） / 反转方向
   - 更新后的方向、目标价位、止损位、关键价位
   - 更新后的置信度
   - 新的观察点和风险因素

## 输出格式（严格JSON）

{
  "verdict_vs_expected": "符合预期 / 部分符合 / 不符合",
  "key_level_status_summary": "关键价位触发情况的文字总结",
  "indicator_trend": "指标变化趋势的文字总结",
  "issues_found": [
    "具体发现的问题1",
    "具体发现的问题2"
  ],
  "new_judgment": "维持 / 修正 / 反转",
  "new_direction": "STRONGLY_BEARISH / BEARISH / NEUTRAL / BULLISH / STRONGLY_BULLISH",
  "new_confidence": 0-100的整数,
  "updated_targets": "更新的目标价位",
  "updated_stop": "更新的止损位",
  "new_watch_points": [
    "新的观察点1",
    "新的观察点2"
  ],
  "reasoning": "推理过程的详细文字说明"
}

## 评估原则

- 客观：如实承认预测错误，不辩解
- 量化：尽可能用具体价格、涨跌幅、指标数值说话
-  actionable：新判断必须包含可操作的目标/止损/观察点
- 如果上次分析预测完全错误，大胆给出反转判断，不要固执
"""


# 全局单例
_skill_kb: Optional[SkillKnowledgeBase] = None


def get_skill_kb() -> SkillKnowledgeBase:
    global _skill_kb
    if _skill_kb is None:
        _skill_kb = SkillKnowledgeBase()
    return _skill_kb
