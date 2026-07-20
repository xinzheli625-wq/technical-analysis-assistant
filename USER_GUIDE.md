# 技术分析助手 — 用户使用指南与标准操作流程（SOP）

> **本文档是系统调用的唯一权威来源。** 每次执行必须严格遵循本文档定义的流程，不得跳过、修改或重排步骤。如有疑问，以本文档为准。

---

## 一、系统定位

本系统是**教材级技术分析决策辅助系统**，不是投资建议工具。

核心能力：从4本经典教材中提取的1209条技术分析Skill → 基于实时行情数据计算50+指标 → 自动匹配触发的Skill → LLM四阶段推理 → 输出结构化分析报告 + 交易计划。

---

## 二、标准操作流程（SOP）

### 流程总览

```
用户请求
  ↓
Step 1: 请求解析（必须）
  ↓
Step 2: 数据准备（必须）
  ↓
Step 3: 指标计算（必须）
  ↓
Step 4: Skill匹配 + 环境适配（必须）
  ↓
Step 5: LLM四阶段分析（必须）
  ↓
Step 6: 交易计划生成（simulate=True时必须，否则可选）
  ↓
Step 7: 结果输出（必须）
  ↓
[若 simulate=True]
Step 8: 模拟开仓（必须）
  ↓
Step 9: 每日跟踪（必须，直到平仓）
  ↓
Step 10: 自动验证（必须，到期触发）
  ↓
Step 11: 归因与权重更新（必须）
```

---

### Step 1: 请求解析（必须）

**输入**: 用户自然语言请求
**输出**: 标准化请求结构

**必须识别的要素**:
1. **标的**: 股票代码（如"603773"、"AAPL"）
2. **数据范围**: 天数（默认100天）
3. **分析类型**: 单次分析 / 跟踪 / 验证 / Skill管理
4. **是否启用模拟**: simulate=True/False（默认False）

**判断规则**:
- 如果只给代码 → 单次分析
- 如果问"之前分析的那只怎么样了" → 跟踪
- 如果给记录ID和实际结果 → 验证
- 如果给教材PDF → Skill提取

**不得**:
- 不得在没有明确标的情况下开始分析
- 不得跳过请求解析直接下载数据
- 不得假设用户意图（必须澄清模糊请求）

---

### Step 2: 数据准备（必须）

**输入**: 标的 + 天数
**输出**: OHLCV DataFrame

**数据源优先级**（必须按此顺序尝试）:
1. **本地CSV** — 检查 `data/{symbol}.csv` 是否存在且最新
2. **akshare** — A股数据（优先）
3. **yfinance** — 美股/全球（限流时等待重试）
4. **Eastmoney API** — 应急备用

**数据质量检查**（必须执行）:
- DataFrame长度 ≥ 60 行（否则报错）
- 必须包含 open/high/low/close/volume 五列
- 检查最近日期是否为交易日（如果不是，说明数据滞后，需告警）

**不得**:
- 不得使用少于60天的数据进行完整分析
- 不得在没有volume数据的情况下跳过量能分析
- 不得忽略数据源错误（必须向用户报告）

---

### Step 3: 指标计算（必须）

**输入**: OHLCV DataFrame
**输出**: 结构化指标字典

**必须计算的维度**（FeatureExtractor.extract_all）:
1. **trend**: 均线系统、ADX、SuperTrend、Ichimoku、Parabolic SAR
2. **momentum**: RSI(14)、MACD、KDJ、CCI、Williams %R、TSI、AO、UO、PPO、StochRSI
3. **volatility**: ATR、Bollinger、Keltner、Donchian、Ulcer Index、Chaikin Vol
4. **volume**: OBV、Volume Ratio、VWAP、MFI、Chaikin Osc、Ease of Movement、Force Index
5. **pattern**: 双底、头肩、三角形、杯柄、楔形、旗形、通道、矩形、圆弧、V形、岛形、缺口
6. **levels**: 枢轴点、斐波那契、支撑阻力
7. **divergence**: 价格-RSI、价格-MACD、价格-OBV背离
8. **trend_stage**: 趋势阶段（early/middle/late/fading/ranging）+ 极端偏离警告
9. **volatility_state**: Squeeze/Expansion/带宽趋势
10. **momentum_accel**: RSI加速度、MACD hist加速度、价格加速度
11. **multi_timeframe**: 短期/中期/长期趋势一致性
12. **composite**: 综合状态

**不得**:
- 不得跳过任何指标维度（即使LLM可能不需要）
- 不得让LLM自行计算指标（所有数值必须由此步骤精确计算）
- 不得忽略计算错误（必须try-catch并标记为error）

---

### Step 4: Skill匹配 + 环境适配（必须）

**输入**: 指标字典 + skill_rules.jsonl
**输出**: triggered / near_triggered / not_triggered skill列表 + 市场环境

**必须执行的子步骤**:

#### 4.1 Skill条件匹配
- 逐条评估1209条Skill的trigger条件
- 每个条件：获取指标值 → 数值比较（>, <, =, between）
- 支持多级路径（如 `momentum.rsi.value`）
- 支持字符串匹配（如 `trend_stage = 'late'`）
- 支持Pattern列表匹配（如检测"Double Bottom"）

#### 4.2 市场环境检测（必须）
- 基于 ADX + 趋势阶段 + 极端偏离 + 多时间框架一致性
- 输出6种环境之一：
  - `trending_up_late_extreme`
  - `trending_up_late`
  - `trending_up_strong`
  - `trending_up`
  - `ranging`
  - `mixed`

#### 4.3 环境适配权重调整（必须）
**规则**（硬编码，不得修改）:
- **trending_up_late_extreme** 环境下：
  - bearish + 超买关键词 → 权重 -0.3
  - bullish + 趋势跟踪关键词 → 权重 +0.1
- **ranging** 环境下：
  - 趋势跟踪类bullish/bearish → 权重 -0.2

**必须输出**:
- 市场环境标签
- 每条triggered skill的原始权重和调整后的权重
- 调整原因

**不得**:
- 不得跳过环境检测
- 不得在市场环境明确时不调整权重
- 不得在LLM分析后才做权重调整（必须在LLM分析前完成）

---

### Step 5: LLM四阶段分析（必须）

**输入**: 指标文本 + Skill匹配结果 + 市场环境
**输出**: Phase 1/2/3/4 结构化分析

**Prompt结构**（必须严格）:
1. **System Prompt**: 角色定义 + 四阶段分析框架 + 输出格式
2. **Indicator Data**: FeatureExtractor.format_for_llm() 输出
3. **Skill Matches**: SkillMatcher.format_for_llm() 输出
4. **User Request**: 股票信息 + 特殊关注要求

**必须包含的要求**:
- Phase 1: 全维度指标盘点（每个指标必须有数值、区域、趋势、判断、依据）
- Phase 2: Skill应用（每条triggered skill走到哪一步了）
- Phase 3: 协同与冲突 + 反转概率评估
- Phase 4: 综合结论 + 趋势性质判断（continuation/reversal/ranging）

**输出格式**: 严格JSON

**不得**:
- 不得跳过任何Phase
- 不得不引用具体数值就下结论
- 不得不给置信度计算逻辑
- 不得让LLM自由发挥（必须在框架内推理）

---

### Step 6: 交易计划生成（simulate=True时必须）

**输入**: LLM分析结果 + 指标字典
**输出**: 交易计划

**必须生成的要素**:
1. **方向**: long / short / neutral
2. **入场**: 价格、类型（market/limit/condition）
3. **止损**（必须提供两种）:
   - 固定止损（来自LLM建议）
   - 动态止损（ATR倍数，根据趋势阶段选择1.5x/2x/3x）
4. **目标**: 价格、分批止盈方案
5. **仓位**: 股数、名义金额、仓位占比
6. **风险收益比**: 数值 + 评级（A/B/C/D）
7. **持有时间**: 预期天数

**风险收益比评级规则**（硬编码）:
- ≥ 2.0: A（优秀）
- ≥ 1.0: B（可接受）
- ≥ 0.5: C（marginal，谨慎）
- < 0.5: D（不合格，不建议入场）

**必须执行的检查**:
- R:R < 0.5 → 必须拒绝入场，输出"方向看涨但风险收益比不合格"
- R:R < 1.0 → 必须降低仓位（risk_pct降至1%）
- 趋势阶段=late + 极端偏离=True → 必须使用3x ATR止损

**不得**:
- 不得在R:R不合格时仍建议入场
- 不得只提供固定止损（必须同时提供动态止损）
- 不得忽略仓位上限限制（单标的不超10%，总敞口不超50%）

---

### Step 7: 结果输出（必须）

**输出内容**（必须包含）:
1. **分析摘要**: 方向、置信度、趋势性质
2. **关键价位**: 目标、止损（固定+动态）、入场
3. **触发Skill**: 每条triggered skill的方向和调整后的权重
4. **风险收益比**: 数值 + 评级 + 是否建议入场
5. **主要风险**: 至少3条
6. **观察点**: 后续需监控的指标/价位

**输出格式**: Markdown（结构化、可读）

**若 simulate=True，额外输出**:
7. **交易计划**: 完整计划JSON
8. **模拟持仓**: Portfolio摘要

---

### Step 8: 模拟开仓（simulate=True时必须）

**输入**: 交易计划
**输出**: 持仓记录

**必须执行的检查**:
1. 资金是否足够
2. 单标的仓位是否超限（10%）
3. 总敞口是否超限（50%）
4. R:R评级是否为D（如果是，拒绝开仓）

**状态变更**:
- trade.status: planned → open
- Portfolio.cash 扣除名义金额
- Portfolio.positions 添加新持仓
- trade_history 记录open action

**不得**:
- 不得在资金不足时开仓
- 不得在超限情况下开仓
- 不得跳过R:R检查直接开仓

---

### Step 9: 每日跟踪（必须，直到平仓）

**触发条件**: 每天收盘后（可手动或Cron定时）

**必须执行**:
1. 获取最新价格
2. Portfolio.daily_mark_to_market() 更新浮动盈亏
3. 检查止损（盘中 + 收盘）
4. 检查止盈
5. 更新equity_curve

**止损检查规则**:
- 盘中触发: low ≤ stop（记录，不执行）
- 收盘触发: close ≤ stop（触发平仓）
- **优先使用动态止损**（如盘中触及固定止损但未触及动态止损，记录但不执行）

**若止损触发**:
- 立即触发Step 10验证（提前验证）
- 不等待planned_verification_date

---

### Step 10: 自动验证（必须，到期触发）

**触发条件**:
1. **计划验证**: 到达 planned_verification_date
2. **事件验证**: 止损/止盈触发

**必须执行**:
1. 下载验证期间价格数据（akshare → yfinance → eastmoney）
2. 构建price_path（entry_date → exit_date每日OHLC）
3. 计算:
   - 实际收益率
   - 最大回撤
   - 最大盈利
   - 目标是否达成
   - 止损是否触发（盘中/收盘）
   - 方向是否正确
4. Skill级归因（每个triggered skill预测是否正确）
5. 生成教训

**验证结果必须保存**:
- trade.status: open → closed
- trade.actual 填充完整结果
- trade.attribution 填充归因
- trade.lessons 填充教训

---

### Step 11: 归因与权重更新（必须）

**必须执行**:
1. 对正确的Skill: RuleIndex.update_performance(skill_id, 'win', regime)
2. 对错误的Skill: RuleIndex.update_performance(skill_id, 'loss', regime)
3. 自动调整权重（基于胜率）:
   - 胜率 > 70%: 权重 +0.1
   - 胜率 < 30%: 权重 -0.1
4. 分环境统计（by_regime）
5. 记录weight_updates.json

**必须生成的输出**:
- 验证报告（Markdown）
- Skill排行榜（按环境筛选）
- 系统改进建议

---

## 三、流程决策树

```
用户请求
  │
  ├─→ "分析股票X" ──────────────→ Step 1-7 (单次分析)
  │                                 └─→ simulate=True? ──→ Step 8-11 (交易模拟)
  │
  ├─→ "跟踪股票X" ──────────────→ Step 9 (每日跟踪)
  │
  ├─→ "验证记录X" ──────────────→ Step 10-11 (验证+归因)
  │
  ├─→ "上传教材提取Skill" ────────→ Skill提取流程（不在本文档范围）
  │
  └─→ "查看Skill统计" ───────────→ RuleIndex.get_stats()
```

---

## 四、强制规则（不得违反）

### 4.1 数据规则
- **必须**使用 ≥ 60 天数据
- **必须**包含 OHLCV 五列
- **不得**让LLM自行计算指标

### 4.2 Skill匹配规则
- **必须**检测市场环境
- **必须**应用环境适配权重
- **不得**在trending_up_late_extreme环境下忽略超买类Skill降权

### 4.3 分析规则
- **必须**输出四阶段分析
- **必须**每个结论引用具体数值
- **不得**跳过Phase 3的冲突裁决

### 4.4 交易计划规则
- **必须**同时提供固定止损和动态止损
- **必须**计算风险收益比
- **不得**在R:R < 0.5时建议入场
- **必须**在late+极端偏离时使用3x ATR止损

### 4.5 验证规则
- **必须**区分盘中触发和收盘触发
- **必须**做Skill级归因
- **必须**分环境统计胜率
- **不得**在验证后不更新Skill performance

---

## 五、常见错误与纠正

| 错误 | 纠正 |
|------|------|
| 跳过环境检测直接分析 | **必须**先运行 `_detect_market_regime()` |
| 只给固定止损不给动态止损 | **必须**同时提供两种，优先使用动态止损 |
| R:R不合格仍建议入场 | **必须**拒绝入场并明确说明原因 |
| 验证时只判断方向不判断过程 | **必须**同时评估方向、目标、止损、回撤 |
| 忽略Skill级归因 | **必须**逐条判断每个triggered skill的对错 |
| 不区分盘中/收盘止损 | **必须**分别记录intraday_hit和close_hit |
| 跳过风险收益比评估 | **必须**在Step 6中计算并评级 |

---

## 六、模块速查

| 模块 | 文件 | 核心功能 | 在SOP中的步骤 |
|------|------|---------|--------------|
| FeatureExtractor | `utils/feature_extractor.py` | 50+指标计算 | Step 3 |
| SkillMatcher | `utils/skill_matcher.py` | Skill匹配 + 环境适配 | Step 4 |
| MarketRegime | `utils/market_regime.py` | 市场环境检测 | Step 4.2 |
| TechnicalAnalyzer | `utils/technical_analyzer.py` | LLM四阶段分析 | Step 5 |
| TradePlanner | `utils/trade_planner.py` | 交易计划生成 | Step 6 |
| PositionSizer | `utils/position_sizer.py` | 仓位计算 | Step 6 |
| Portfolio | `utils/portfolio.py` | 模拟持仓 | Step 8-9 |
| AutoValidator | `utils/auto_validator.py` | 自动验证 | Step 10 |
| RuleIndex | `utils/rule_index.py` | Skill索引 + 性能追踪 | Step 4, 11 |

---

## 七、更新日志

| 日期 | 更新内容 |
|------|---------|
| 2026-06-06 | 新增交易模拟SOP（Step 6-11） |
| 2026-06-06 | 新增环境适配权重规则 |
| 2026-06-06 | 新增风险收益比强制评估规则 |
| 2026-06-06 | 新增动态止损优先规则 |
| 2026-06-06 | 新增Skill级归因强制规则 |
| 2026-05-23 | 初始版本（分析SOP Step 1-7） |
