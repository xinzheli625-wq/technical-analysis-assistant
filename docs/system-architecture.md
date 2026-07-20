# Technical Analysis Assistant - 完整系统架构

## 一、系统全景图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         技术分析助手 - 完整数据流                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                     │
│  │   截图输入   │    │  Excel/CSV  │    │   API数据   │                     │
│  │  (PNG/JPG)  │    │  (OHLCV)    │    │  (yfinance) │                     │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                     │
│         │                  │                  │                            │
│         ▼                  ▼                  ▼                            │
│  ┌─────────────────────────────────────────────────────┐                   │
│  │              Input Adapter 输入适配层                │                   │
│  │  • 截图 → Doubao-Seed-2.0-lite Vision + Skill       │                   │
│  │  • Excel → 列名自动检测(中英) → 标准化数据结构       │                   │
│  │  • API → 标准化数据结构                              │                   │
│  └─────────────────────────┬───────────────────────────┘                   │
│                            │                                                │
│                            ▼                                                │
│  ┌─────────────────────────────────────────────────────┐                   │
│  │        Skill Knowledge Base 知识底座构建层           │                   │
│  │                                                     │                   │
│  │  ┌──────────────┐  ┌──────────────────────────┐    │                   │
│  │  │ 7个reference │  │    Rule Index 规则索引库  │    │                   │
│  │  │   文件       │  │  (data/skill_rules.jsonl) │    │                   │
│  │  │              │  │                          │    │                   │
│  │  │ • trend      │  │  每条规则:               │    │                   │
│  │  │ • patterns   │  │  - rule_id               │    │                   │
│  │  │ • indicators │  │  - category/name/def     │    │                   │
│  │  │ • volume     │  │  - conditions/examples   │    │                   │
│  │  │ • behavior   │  │  - source/status/version │    │                   │
│  │  │ • events     │  │  - performance(win_rate) │    │                   │
│  │  │ • scoring    │  │                          │    │                   │
│  │  └──────────────┘  └──────────────────────────┘    │                   │
│  │                                                     │                   │
│  │  核心方法: build_prompt(scene)                      │                   │
│  │  - 按场景加载相关skill (3-10K tokens)               │                   │
│  │  - 核心框架(精炼30%) + 规则索引(按需)               │                   │
│  │  - Token预算管理，超限时自动摘要                    │                   │
│  └─────────────────────────┬───────────────────────────┘                   │
│                            │                                                │
│                            ▼                                                │
│  ┌─────────────────────────────────────────────────────┐                   │
│  │         VolcEngineClient 大模型推理引擎              │                   │
│  │                                                     │                   │
│  │  ┌─────────────────┐ ┌─────────────────┐           │                   │
│  │  │ Doubao-Seed     │ │ DeepSeek-V3.2   │           │                   │
│  │  │ 2.0-mini        │ │                 │           │                   │
│  │  │ (性价比)        │ │ (高性能)        │           │                   │
│  │  │                 │ │                 │           │                   │
│  │  │ • NL指令解析    │ │ • 趋势分析      │           │                   │
│  │  │ • 归因分类      │ │ • 形态识别      │           │                   │
│  │  │                 │ │ • 指标计算      │           │                   │
│  │  └─────────────────┘ │ • 量价分析      │           │                   │
│  │                      │ • 资金行为      │           │                   │
│  │  ┌─────────────────┐ │ • 事件推断      │           │                   │
│  │  │ Doubao-Seed     │ │ • 评分/报告     │           │                   │
│  │  │ 2.0-lite        │ │ • 知识提取      │           │                   │
│  │  │ (多模态)        │ └─────────────────┘           │                   │
│  │  │                 │                               │                   │
│  │  │ • 截图Vision    │  System Prompt结构:            │                   │
│  │  │   分析          │  ┌──────────────────────┐     │                   │
│  │  └─────────────────┘  │ # 技术分析体系框架   │     │                   │
│  │                       │ ## TREND             │     │                   │
│  │                       │ [精炼核心内容...]    │     │                   │
│  │                       │ ## PATTERNS          │     │                   │
│  │                       │ [精炼核心内容...]    │     │                   │
│  │                       │ ## 具体规则          │     │                   │
│  │                       │ ### Cup with Handle  │     │                   │
│  │                       │ [规则详情...]        │     │                   │
│  │                       │ ## 输出要求          │     │                   │
│  │                       │ [JSON格式定义]       │     │                   │
│  │                       └──────────────────────┘     │                   │
│  └─────────────────────────┬───────────────────────────┘                   │
│                            │                                                │
│                            ▼                                                │
│  ┌─────────────────────────────────────────────────────┐                   │
│  │          Technical Analyzer 9步分析流程              │                   │
│  │                                                     │                   │
│  │  Step 1: 数据标准化    (InputAdapter完成)            │                   │
│  │  Step 2: 趋势分析      → DeepSeek + trend skill      │                   │
│  │  Step 3: 形态识别      → DeepSeek + patterns skill   │                   │
│  │  Step 4: 指标分析      → DeepSeek + indicators skill │                   │
│  │  Step 5: 量价分析      → DeepSeek + volume skill     │                   │
│  │  Step 6: 资金行为      → DeepSeek + behavior skill   │                   │
│  │  Step 7: 事件推断      → DeepSeek + events skill     │                   │
│  │  Step 8: 多维度评分    → DeepSeek + scoring skill    │                   │
│  │  Step 9: 报告生成      → DeepSeek + all skills       │                   │
│  │                                                     │                   │
│  │  输出: {                                            │                   │
│  │    symbol, market, input_type,                     │                   │
│  │    trend_analysis, pattern_analysis,               │                   │
│  │    indicator_analysis, volume_price_analysis,      │                   │
│  │    behavior_analysis, event_inference, scoring     │                   │
│  │  }                                                 │                   │
│  └─────────────────────────┬───────────────────────────┘                   │
│                            │                                                │
│                            ▼                                                │
│  ┌─────────────────────────────────────────────────────┐                   │
│  │         Report Generator 报告生成层                  │                   │
│  │                                                     │                   │
│  │  DeepSeek + 全部Skill → 专业中文分析报告            │                   │
│  │                                                     │                   │
│  │  报告结构:                                          │                   │
│  │  1. 趋势评估     2. 形态识别     3. 技术指标         │                   │
│  │  4. 量价分析     5. 资金行为     6. 事件推断         │                   │
│  │  7. 综合评分     8. 风险提示     9. 免责声明         │                   │
│  └─────────────────────────┬───────────────────────────┘                   │
│                            │                                                │
│                            ▼                                                │
│  ┌─────────────────────────────────────────────────────┐                   │
│  │         Feedback Loop 反馈闭环系统                   │                   │
│  │                                                     │                   │
│  │  分析时 → record_analysis() → 存入反馈记录           │                   │
│  │                                                     │                   │
│  │  N天后 → validate_record() → LLM自动归因            │                   │
│  │                                                     │                   │
│  │  归因分类(A-F):                                      │                   │
│  │  A. Pattern Misidentification (形态误判)            │                   │
│  │  B. Level Miscalculation      (价位误算)            │                   │
│  │  C. Indicator Misread         (指标误读)            │                   │
│  │  D. Correct Tech, External Shock (外部冲击)         │                   │
│  │  E. Correct Tech, Stop Too Tight (止损过紧)         │                   │
│  │  F. Correct Tech, Timeframe Mismatch (时间错配)     │                   │
│  │                                                     │                   │
│  │  只有A/B/C触发Skill规则调整                         │                   │
│  │  D/E/F不调整，避免外部因素干扰                      │                   │
│  └─────────────────────────┬───────────────────────────┘                   │
│                            │                                                │
│                            ▼                                                │
│  ┌─────────────────────────────────────────────────────┐                   │
│  │       Evolution Engine Skill自我进化系统             │                   │
│  │                                                     │                   │
│  │  通道1: 书籍/报告上传                                │                   │
│  │    PDF/Word → parse_text → LLM提取规则              │                   │
│  │    → 冲突检测 → RuleIndex.add_rule(pending)         │                   │
│  │    → 用户activate_rule() → active → skill_kb.reload │                   │
│  │                                                     │                   │
│  │  通道2: 自然语言指令                                 │                   │
│  │    "Add pattern X..." → LLM解析 → RuleIndex         │                   │
│  │    → pending → 用户确认 → active                    │                   │
│  │                                                     │                   │
│  │  通道3: 反馈数据驱动                                 │                   │
│  │    feedback_records → 统计失败规则                  │                   │
│  │    → 标记需要review的规则                           │                   │
│  │    → 提示用户调整或废弃                             │                   │
│  └─────────────────────────────────────────────────────┘                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 二、各层详细说明

### Layer 1: 输入层 (Input Adapter)

**三种输入方式统一归一化：**

| 输入方式 | 处理逻辑 | 输出数据结构 |
|---------|---------|-------------|
| **截图** | Doubao-Seed-2.0-lite Vision + 全部Skill(10K tokens) | `{input_type: "screenshot", data: [], metadata: {llm_vision_analysis: {...}}}` |
| **Excel/CSV** | 自动检测中英文列名 → 解析OHLCV → 计算元数据 | `{symbol, market, data: [{date, open, high, low, close, volume}], metadata}` |
| **API** | 透传为DataFrame → 标准化 | 同Excel |

**Excel列名自动检测：**
- 英文: `Date/Open/High/Low/Close/Volume`
- 中文: `日期/开盘/最高/最低/收盘/成交量`

### Layer 2: Skill知识底座

**双轨制架构：**

```
SkillKnowledgeBase
├── _raw_cache: 7个reference文件原始内容（仅用于初始化）
├── _core_cache: 精炼后的核心框架（原文30%长度）
│   └── 提取策略: 保留标题+阈值+条件，去掉冗长示例
└── RuleIndex (外部)
    └── data/skill_rules.jsonl (动态规则，可热更新)
```

**build_prompt(scene) 构建流程：**

```
用户请求分析AAPL趋势
        ↓
scene = "trend"
        ↓
SCENE_RULE_CATEGORIES['trend'] = ['trend']
        ↓
1. 加载核心框架: _core_cache['trend'] (~2K tokens)
2. 加载规则索引: RuleIndex.get_rules_for_prompt(['trend'])
   - 检索active状态的trend类规则
   - 按胜率排序
   - token预算内加载，超出时摘要化
3. 添加输出格式指导
        ↓
最终system prompt: ~3-5K tokens (vs 重构前42K)
```

### Layer 3: 大模型推理引擎

**模型分工：**

| 模型 | 角色 | 调用场景 | 预估Token |
|------|------|---------|----------|
| **Doubao-Seed-2.0-lite** | 视觉专家 | 截图K线分析 | 输入12K / 输出2K |
| **DeepSeek-V3.2** | 分析专家 | 趋势/形态/指标/量价/行为/事件/评分 | 输入5-10K / 输出2K |
| **Doubao-Seed-2.0-mini** | 轻量助手 | NL指令解析、归因分类 | 输入5-10K / 输出1K |

**单次分析完整Token消耗（以Excel输入为例）：**

```
Step 2 趋势分析:  输入5K  + 输出1K  = 6K
Step 3 形态识别:  输入6K  + 输出1K  = 7K
Step 4 指标分析:  输入5K  + 输出1K  = 6K
Step 5 量价分析:  输入5K  + 输出1K  = 6K
Step 6 资金行为:  输入6K  + 输出1.5K = 7.5K
Step 7 事件推断:  输入7K  + 输出1K  = 8K
Step 8 多维度评分: 输入8K  + 输出1K  = 9K
Step 9 报告生成:  输入10K + 输出3K  = 13K
─────────────────────────────────────────
总计: ~62K tokens/次分析

成本估算 (DeepSeek-V3.2 ~￥3/1M tokens, mini ~￥0.4/1M):
~￥0.15-0.20 / 次完整分析
```

### Layer 4: 9步分析流程

**每步的输入输出：**

| 步骤 | 输入 | LLM处理 | 输出JSON字段 |
|------|------|---------|-------------|
| 2.趋势 | 价格数据摘要 | Wyckoff阶段判断 + MA排列 | `stage`, `ma_alignment`, `moving_averages` |
| 3.形态 | 价格数据摘要 | 形态识别 + 支撑阻力 | `patterns[]`, `support_levels`, `resistance_levels` |
| 4.指标 | 价格数据摘要 | RSI/MACD/KDJ/布林带计算 | `rsi`, `macd`, `kdj`, `bollinger` |
| 5.量价 | 价格+成交量 | VSA信号识别 | `volume_ratio`, `interpretation`, `vsa_signals[]` |
| 6.行为 | 前5步结果综合 | 资金行为推断 | `dominant_force`, `intent`, `chip_status`, `sentiment` |
| 7.事件 | 前6步结果综合 | 基本面事件概率 | `inferred_events[]`, `scenario_analysis` |
| 8.评分 | 全部信号 | 6维度加权评分 | `dimension_scores`, `composite_score`, `verdict` |
| 9.报告 | 全部结构化数据 | 中文报告生成 | Markdown格式完整报告 |

### Layer 5: 反馈闭环

**记录 → 验证 → 归因 → 统计 的完整链路：**

```
分析时:
  record_analysis(analysis_results, target_price=210, stop_loss=185)
  → 生成 record_id: "abc123"
  → 存入 data/feedback_records.json

N天后:
  validate_record("abc123",
    actual_return_pct=8.5,
    target_reached=True,
    stop_hit=False,
    direction_correct=True)
  → outcome: "win"
  → 无需归因（非失败）

如果失败:
  → outcome: "loss"
  → LLM自动归因:
     mini + attribution skill → {"attribution": "A", "reason": "..."}
  → 只有A/B/C触发规则调整
  → D/E/F记录但不调整（鲁棒性）

定期:
  calculate_statistics()
  → 胜率、平均收益、按形态统计
  → 识别表现差的规则
```

### Layer 6: Skill进化

**三条进化通道：**

**通道1 - 书籍提取：**
```
用户上传《日本蜡烛图技术》.pdf
        ↓
parse_pdf() → 提取文本
        ↓
LLM(DeepSeek) + 现有Skill上下文
→ 提取结构化规则:
  {
    "rules": [
      {"rule_type": "pattern", "name": "Morning Star",
       "conditions": [{"field": "candle_1", "value": "long_red"}, ...],
       "confidence_weight": 85}
    ]
  }
        ↓
RuleIndex.add_rule(rule, auto_activate=False)
→ 状态: pending
→ 冲突检测: 与现有"Morning Star"规则对比
        ↓
返回给用户:
  {rules: [{rule_id, name, status: "pending"}], conflicts: [...]}
        ↓
用户确认: activate_rule("rule_id")
→ 状态变为 active
→ skill_kb.reload() 立即生效
```

**通道2 - 自然语言：**
```
用户: "Add pattern 'Springboard' - break below support on high volume but close back above within 2 days"
        ↓
LLM(mini) + Skill上下文
→ 解析为结构化规则:
  {intent: "add_pattern", target_file: "chart-patterns.md", ...}
        ↓
RuleIndex.add_rule(parsed_rule, auto_activate=False)
        ↓
返回: {rule_id, status: "pending", next_step: "Call activate_rule()"}
```

**通道3 - 反馈驱动：**
```
50条验证记录 → analyze_feedback_for_updates()
        ↓
筛选 technical_correctness in [A, B, C] 的失败记录
        ↓
关联到具体规则:
  Pattern "Double Bottom" 失败5次 → win_rate: 30%
        ↓
生成建议:
  {rule_id: "xyz", rule_name: "Double Bottom",
   suggestion: "Review conditions, current win_rate: 30%"}
        ↓
用户决定: 调整条件 / 废弃规则 / 保持观察
```

## 三、数据持久化

```
data/
├── feedback_records.json       # 分析记录 + 验证结果 + 归因
├── statistics.json             # 统计摘要
├── skill_rules.jsonl           # 规则索引库 (JSONL, 每行一条规则)
├── skill_rules_index.json      # 规则索引统计
└── book_registry.json          # 已处理书籍哈希
```

## 四、预期效果

### 分析质量
- **一致性**: 所有分析遵循统一的7个reference文件定义的技术体系
- **专业性**: System Prompt注入专业知识，大模型以"技术分析专家"身份作答
- **可解释性**: 每步输出结构化JSON，包含推理理由

### 成本效率
- **Token节省**: 按需加载skill，单次分析从42K降至5-10K（节省75-88%）
- **模型分层**: 复杂分析用DeepSeek，简单任务用mini，视觉用lite
- **单次成本**: 完整9步分析约￥0.15-0.20

### 可进化性
- **知识可更新**: 上传书籍/报告自动提取规则
- **NL可操作**: 自然语言描述即可添加/修改规则
- **数据驱动**: 基于实际表现自动识别问题规则
- **版本管理**: 规则有版本号，可追溯变更

### 鲁棒性
- **归因分级**: 区分"技术错误"vs"外部冲击"，避免过度调整
- **优雅降级**: API失败时有明确错误信息（不再本地回退）
- **热更新**: 激活新规则后立即生效，无需重启
