---
name: technical-analysis-assistant
description: >
  技术分析助手的Claude Code调用接口。
  当用户想要分析股票、管理技术分析Skill、验证分析结果、交易模拟时触发。
  提供统一的Python API入口，让Claude Code可以通过自然语言调用技术分析系统的所有功能。
  包含指标计算、Skill管理、反馈闭环、交易模拟、自动验证五大模块。
  此Skill与 technical-analysis-core 配合使用：core提供分析方法论，assistant提供调用接口。

  > **SOP参考**: USER_GUIDE.md — 每次调用必须遵循的标准操作流程。
---

# 技术分析助手 - Claude Code 调用指南

## 触发条件

当用户有以下意图时，调用此Skill：
- "分析一下AAPL" / "看看这只股票怎么样"
- "上传这本书的 Skill" / "我学到一个新方法"
- "验证上次分析的结果" / "上次AAPL涨了15%"
- "查看我有哪些Skill" / "哪些Skill胜率最高"
- "这个Skill在震荡市表现不好"
- "导出Skill知识库"

---

## 核心入口

所有功能通过 `api.py` 模块调用：

```python
# 方式1：使用全局实例
from api import assistant
result = assistant().analyze("AAPL", days=100)

# 方式2：使用便捷函数
from api import analyze, upload_skill, validate, list_skills
result = analyze("AAPL")
```

**重要**：调用前确保已设置 `DEEPSEEK_API_KEY` 环境变量。
获取地址: https://platform.deepseek.com/api_keys

---

## 功能1：分析股票

### 用户意图识别
用户说以下话时，触发分析：
- "分析一下 [股票代码]"
- "看看 [股票] 的技术面"
- "[股票] 怎么样"
- "帮我看看这个股票"

### 调用方式

```python
from api import analyze

# 从yfinance下载数据进行分析（必须指定天数）
result = analyze("AAPL", days=100)   # 中线
result = analyze("AAPL", days=30)    # 短线
result = analyze("AAPL", days=200)   # 长线

# 从用户上传的CSV/Excel文件分析
result = assistant().analyze_from_file("path/to/data.csv", symbol="AAPL")

# 注意：K线截图分析暂不可用（deepseek-v4-pro 不支持图片输入）
# 如用户上传截图，请引导其改用代码联网分析或导出CSV后 analyze_from_file

# 快速获取指标摘要（纯文本）
text = assistant().quick_indicators("AAPL", days=100)

# 生成可读报告
report = assistant().quick_report("AAPL", days=100)
```

### 返回结构

```python
result = {
    'trend_analysis': {...},       # 趋势分析
    'pattern_analysis': {...},      # 形态识别
    'indicator_analysis': {...},    # 指标分析（Phase 1/2/3/4）
    'volume_price_analysis': {...}, # 量价分析
    'behavior_analysis': {...},     # 资金行为
    'event_inference': {...},       # 事件推断
    'scoring': {...},               # 综合评分
    'market_regime': {              # 市场状态
        'primary': 'trending_up',
        'confidence': 0.85
    },
    'indicator_summary': '...',     # 指标摘要文本
    'record_id': 'abc123'           # 反馈记录ID（如果save=True）
}
```

### 输出给用户

展示 `indicator_analysis` 中的 Phase 1/2/3/4 结构：
1. **Phase 1: 指标盘点** - 逐项展示每个指标的状态
2. **Phase 2: Skill应用** - 哪些Skill触发了、哪些准触发、哪些未触发
3. **Phase 3: 协同与冲突** - 信号之间的协同和冲突裁决
4. **Phase 4: 综合结论** - 方向、置信度、关键依据

---

## 功能2：管理Skill

### 2.1 上传Skill（从书籍）

用户说：
- "我读了这本书，帮我提取方法"
- "上传这个PDF"
- "这本书里有个策略"

**用户操作**：拖拽上传PDF/Word文件

**必须按交互式分段流程执行**（详见 docs/SKILL_EXTRACTION_GUIDE.md，禁止整本批量提取）：

```python
from api import assistant
a = assistant()

# 1. 加载书籍（自动检测扫描版并触发OCR，返回清洗后全文）
result = a.upload_skill_book("path/to/book.pdf")

# 2. Claude Code 阅读全文，提出分段方案 → 用户审批
# 3. 用户确认后设置分段
a.set_book_segments([
    {'segment_id': 1, 'title': '趋势篇', 'start_marker': '第一章', 'note': '重点提取'},
])

# 4. 逐段提取（每段用户审核，可带自然语言指导）
skills = a.extract_book_segment(1, '重点提取趋势线画法，threshold用原文值')

# 5. 本地修改/删除（零API消耗）
a.modify_extracted_skill(0, 'reference_data.关键阈值', 'RSI>70')
a.remove_extracted_skill(2)

# 6. 保存到 pending 队列 → 用户确认后激活
a.save_book_skills()
```

**展示给用户**：
```
段1提取完成! 共 5 条Skill（待审核）
  - [a1b2c3d4] 量价突破确认法 (pending)
  - [e5f6g7h8] 相对强度选股法 (pending)

审核后激活：
  assistant().activate_skill("a1b2c3d4")
```

**重要**：新 Skill 的 trigger 指标名必须使用 SkillMatcher alias_map 可解析的名称
（rsi_14、adx_value、close、sma20、pattern 等），否则永远不会触发。
一次性自动模式（不推荐）：`upload_skill_book(path, auto_extract=True)`。

### 2.2 上传Skill（从自然语言）

用户说：
- "我学到一个方法：当..."
- "我的交易系统是..."
- "我发现一个规律..."

**Claude Code调用**：
```python
from api import assistant
result = assistant().upload_skill_text("用户描述的方法论文本")
```

### 2.3 查看所有Skill

用户说：
- "我现在有哪些Skill？"
- "查看我的知识库"
- "哪些Skill胜率最高？"

**Claude Code调用**：
```python
from api import assistant

# 列出所有Skill
skills = assistant().list_skills()

# 导出为HTML页面
assistant().export_skills_html("skills_dashboard.html")
```

**展示给用户**：列表 + HTML链接

### 2.4 激活/停用Skill

用户说：
- "激活这个Skill"
- "这个方法不好，停用"

**Claude Code调用**：
```python
assistant().activate_skill("a1b2c3d4")
assistant().deactivate_skill("a1b2c3d4")
```

### 2.5 查看Skill统计

用户说：
- "这个Skill表现怎么样？"
- "胜率多少？"

**Claude Code调用**：
```python
stats = assistant().skill_stats("a1b2c3d4")
```

---

### 2.6 从飞书文档导入Skill

用户说：
- "这个飞书文档里有我的交易方法"
- "从这篇飞书文章提取Skill"
- "我写在飞书上的策略"

**用户操作**：提供飞书文档URL

**Claude Code调用**：
```python
from api import assistant

# 从飞书文档URL导入
result = assistant().upload_skill_from_feishu(
    "https://xxx.feishu.cn/docx/AbCdEfGh"
)
```

---

## 功能3：反馈闭环

### 3.1 验证分析结果

用户说：
- "上次分析的AAPL我赚了15%"
- "验证一下记录abc123"
- "这个结果对了/错了"

**Claude Code调用**：
```python
from api import validate

result = validate(
    record_id="abc123",
    return_pct=15.0,
    target_hit=True,
    direction_correct=True
)
```

**展示给用户**：
```
验证完成!
  实际收益: 15.0%
  结果: win

Skill归因:
  ✅ 量价突破确认法: 预测正确（历史胜率75%）
  ✅ MACD金叉动能: 预测正确（历史胜率68%）
  ⚠️ RSI超买警戒: 未触发，不评价

统计更新:
  量价突破确认法: 胜率 76% (17/22) ↑
```

### 3.2 查看反馈统计

用户说：
- "最近表现怎么样？"
- "整体胜率多少？"

**Claude Code调用**：
```python
stats = assistant().feedback_stats()
```

---

## 功能4：飞书同步（产出管理）

### 4.1 启用飞书同步

用户说：
- "启用飞书同步"
- "把分析结果同步到飞书"

**Claude Code调用**：
```python
from api import assistant

# 启用飞书同步（首次会自动创建文件夹）
assistant().enable_feishu()

# 之后每次分析自动同步到飞书
result = assistant().analyze("AAPL", days=100)
# 输出中会显示飞书文档链接
```

**飞书产出结构**：
```
技术分析助手（文件夹）
  ├── AAPL 技术分析（文档）- 每次分析追加记录
  ├── NVDA 技术分析（文档）- 每次分析追加记录
  ├── 分析记录汇总（文档）- Markdown表格，记录所有分析
  └── ...
```

### 4.2 飞书文档中的分析记录

每个股票文档包含：
- 分析时间
- 市场环境
- 指标摘要
- 趋势分析
- 综合结论
- 记录ID（用于后续验证）

### 4.3 阶段性总结时同步验证

验证时也会同步到飞书汇总文档：
```python
assistant().validate("rec_001", actual_return_pct=15.0, target_hit=True)
# 验证结果会追加到汇总文档
```

---

## Skill 教材格式约定

上传的Skill必须是**教材式**的（不是条件模板）：

```json
{
  "name": "方法名称",
  "type": "methodology",
  "core_idea": "这个方法解决什么问题",
  "analysis_steps": [
    "步骤1：检查什么指标，判断标准",
    "步骤2：结合哪些其他指标确认",
    "步骤3：综合判断的逻辑"
  ],
  "reference_data": {
    "关键阈值": "数值参考"
  },
  "win_rate_hint": {
    "trending_up": 0.75,
    "ranging": 0.55
  },
  "common_pitfalls": [
    "常见误区1",
    "常见误区2"
  ],
  "when_not_to_use": [
    "不适用场景1"
  ],
  "applicable_regimes": ["trending_up", "trending_down"]
}
```

---

## 系统架构

```
用户（自然语言）
    ↓
Claude Code（理解意图）
    ↓
api.py（统一入口）
    ↓
├─ utils/technical_analyzer.py（LLM分析引擎）
├─ utils/feature_extractor.py（50+指标计算）
├─ utils/market_regime.py（市场状态检测）
├─ utils/evolution_engine.py（Skill提取）
├─ utils/rule_index.py（Skill索引）
└─ utils/feedback_loop.py（反馈闭环）
    ↓
返回结果（自然语言报告）
```

---

## 更新日志

| 日期 | 更新内容 |
|------|---------|
| 2026-05-23 | 创建Skill，统一调用入口api.py，移除CLI |
| 2026-05-22 | 完成反馈闭环概率思维、Skill教材格式、HTML导出 |
| 2026-05-21 | 完成指标库扩展(50+)、市场状态检测、Phase输出结构 |
| 2026-05-20 | 项目初始化，核心框架搭建 |

**此Skill与项目代码同步更新**。当项目代码修改后，此文档会自动更新以反映最新能力。

---

## 功能5：交易模拟

### 用户意图识别
用户说以下话时，触发交易模拟：
- "帮我做个交易计划"
- "分析一下 [股票]，带交易模拟"
- "这只股票能买吗"
- "模拟一下如果买入会怎么样"
- "看看风险收益比"
- "给我个止损建议"

### 调用方式

```python
from api import assistant

# 分析并生成交易计划（simulate=True）
result = assistant().analyze("603773", days=100, simulate=True)

# 输出包含：
# result['trade_plan'] — 完整交易计划
# result['portfolio'] — 模拟持仓状态
```

### 返回结构

```python
result = {
    # ... 原有分析结果 ...
    'trade_plan': {
        'trade_id': '603773_SH_20250606',
        'direction': 'long',
        'confidence': 70,
        'entry': {'type': 'market', 'price': 122.0},
        'stop_loss': {
            'type': 'dynamic_atr',
            'fixed_price': 113.93,      # LLM建议的固定止损
            'dynamic_price': 91.85,     # 系统计算的动态ATR止损
            'atr': 10.05,
            'atr_multiplier': 3.0,
        },
        'target': {'type': 'fixed', 'price': 126.76},
        'position': {
            'shares': 663,
            'notional': 80886.0,
            'position_pct': 8.09,
            'risk_amount': 20000.0,
        },
        'risk_metrics': {
            'risk_reward_ratio': 0.59,
            'verdict': 'marginal',
            'grade': 'C',
        },
        'recommendation': '方向看涨但风险收益比marginal，如入场需严格控制仓位',
    },
    'portfolio': {
        'initial_capital': 1000000,
        'current_equity': 1000000,
        'cash': 919114.0,
        'open_positions': 1,
        'exposure': {...},
    }
}
```

### 输出给用户

展示交易计划的关键要素：
1. **方向与置信度**
2. **入场价位**
3. **止损对比**（固定 vs 动态，优先推荐动态）
4. **目标价位**
5. **仓位大小**（股数 + 金额 + 仓位占比）
6. **风险收益比**（数值 + 评级）
7. **系统建议**（是否建议入场）

**如果R:R < 0.5（Grade D）**:
> ⚠️ 风险收益比不合格，系统不建议入场。
> 方向：BULLISH
> 风险收益比：0.16（D级）
> 建议：观望，等待更好的入场时机。

---

## 功能6：自动验证与归因

### 用户意图识别
用户说以下话时，触发验证：
- "验证一下上次的结果"
- "批量验证"
- "这只股票之前分析了，现在怎么样了"
- "看看Skill准确率"
- "归因分析"

### 调用方式

```python
from api import assistant

# 验证单笔交易
result = assistant().validate_trade("woge_20250602_001")

# 批量验证所有到期交易
result = assistant().batch_validate()

# 查看模拟持仓
result = assistant().get_portfolio()

# 查看资金曲线
result = assistant().get_equity_curve()
```

### 验证结果结构

```python
{
    'trade_id': 'woge_20250602_001',
    'symbol': '603773.SH',
    'outcome': {
        'entry_price': 122.0,
        'exit_price': 132.40,
        'exit_reason': 'target_reached',
        'pnl_pct': 8.52,
        'max_return_pct': 10.36,
        'max_drawdown_pct': -12.20,
        'target_reached': True,
        'stop_hit_intraday': False,
        'stop_hit_close': False,
        'direction_correct': True,
        'holding_days': 3,
    },
    'attribution': {
        'correct_skills': [
            {'name': 'DI交叉交易信号', 'direction': 'bullish'},
            {'name': 'MACD交叉信号', 'direction': 'bullish'},
        ],
        'wrong_skills': [
            {'name': 'RSI超买警告', 'direction': 'bearish'},
            {'name': '相反意见理论', 'direction': 'bearish'},
        ],
        'correct_count': 6,
        'wrong_count': 4,
    },
    'lessons': [
        '风险收益比0.16不合格，不应入场',
        '最大回撤-12.2%远超预期',
        '强趋势末期超买信号失效',
    ]
}
```

### 输出给用户

展示验证报告：
```
## 交易验证报告: 603773.SH

### 实际结果
- 收盘价: 132.40 (+8.52%)
- 最高: 134.64 (+10.36%)
- 最低: 107.11 (-12.20% 回撤)
- 目标达成: ✓
- 止损触发: ✗
- 方向正确: ✓

### Skill归因
✓ 正确的Skill (6个):
  - DI交叉交易信号 (bullish)
  - MACD交叉信号 (bullish)
  - ...

✗ 错误的Skill (4个):
  - RSI超买警告 (bearish)
  - 相反意见理论 (bearish)
  - ...

### 核心教训
1. 风险收益比0.16不合格
2. 最大回撤-12.2%远超预期
3. 强趋势末期超买信号全面失效

### 系统改进
- [已执行] bearish skill在trending_up_late环境下权重-0.3
```

---

## 关键设计更新

### 1. 动态止损优先原则
- 每次交易计划必须同时提供固定止损和动态ATR止损
- **优先使用动态止损**（固定止损仅作参考）
- ATR倍数根据趋势阶段自动选择：
  - early/middle: 1.5x ATR
  - late: 2x ATR
  - late + extreme_deviation: 3x ATR

### 2. 风险收益比强制评估
- 每次交易计划必须计算R:R ratio
- **R:R < 0.5 → 必须拒绝入场**（Grade D）
- **R:R < 1.0 → 必须降低仓位**（Grade C）
- R:R评级展示给用户

### 3. 环境适配权重
- Skill匹配后自动检测市场环境
- 根据环境调整Skill权重：
  - trending_up_late_extreme: bearish超买类skill权重-0.3
  - ranging: 趋势跟踪类skill权重-0.2
- 调整后的权重影响Phase 3冲突裁决

### 4. 模拟验证流程
- 分析时 simulate=True → 自动生成交易计划
- 交易计划自动保存到 Portfolio
- 每天自动跟踪（或手动触发）
- 到期后自动验证（或止损触发提前验证）
- 验证后自动更新Skill performance

---

## 系统架构（更新）

```
用户（自然语言）
    ↓
Claude Code（理解意图）
    ↓
api.py（统一入口）
    ↓
├─ utils/feature_extractor.py（50+指标计算）
├─ utils/skill_matcher.py（Skill匹配 + 环境适配权重）
├─ utils/market_regime.py（市场环境检测）
├─ utils/technical_analyzer.py（LLM四阶段分析）
├─ utils/trade_planner.py（交易计划生成）
├─ utils/position_sizer.py（仓位计算）
├─ utils/portfolio.py（模拟持仓管理）
├─ utils/auto_validator.py（自动验证 + 归因）
├─ utils/rule_index.py（Skill索引 + 性能追踪）
└─ utils/feedback_loop.py（反馈闭环）
    ↓
返回结果（分析报告 + 交易计划 + 验证报告）
```

---

## 更新日志

| 日期 | 更新内容 |
|------|---------|
| 2026-06-06 | 新增交易模拟功能（TradePlanner/PositionSizer/Portfolio/AutoValidator） |
| 2026-06-06 | 新增自动验证与归因系统 |
| 2026-06-06 | 新增环境适配权重（trending_up_late_extreme） |
| 2026-06-06 | 新增风险收益比强制评估（A/B/C/D评级） |
| 2026-06-06 | 新增动态ATR止损（1.5x/2x/3x） |
| 2026-05-23 | 创建Skill，统一调用入口api.py，移除CLI |
| 2026-05-22 | 完成反馈闭环概率思维、Skill教材格式、HTML导出 |
| 2026-05-21 | 完成指标库扩展(50+)、市场状态检测、Phase输出结构 |
| 2026-05-20 | 项目初始化，核心框架搭建 |

**此Skill与项目代码同步更新**。当项目代码修改后，此文档会自动更新以反映最新能力。
