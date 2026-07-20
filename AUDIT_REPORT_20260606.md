# 全量代码审计报告

> 审计日期: 2026-06-06
> 审计范围: 全部 Python 源码 + 全部 Markdown 文档 + 数据文件
> 审计目标: ①变量名/钩稽关系/代码细节 ②代码与文档吻合度 ③废弃文档识别 ④演进方向

---

## 一、模块依赖全景图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              入口层                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  api.py ────────────────┐                                                   │
│  deterministic_pipeline.py ─┘ (并行存在，未集成)                            │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                              核心分析层                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  technical_analyzer.py → DeepSeekClient, FeatureExtractor, SkillMatcher    │
│  feature_extractor.py → TrendCalc, MomentumCalc, VolatilityCalc,           │
│                         VolumeCalc, PatternDetector, LevelCalc              │
│  skill_matcher.py → RuleIndex (懒加载)                                     │
│  market_regime.py → TrendCalc, MomentumCalc, VolatilityCalc                │
├─────────────────────────────────────────────────────────────────────────────┤
│                              交易模拟层（新增）                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  trade_planner.py → PositionSizer                                           │
│  position_sizer.py ── (独立，无外部依赖)                                    │
│  portfolio.py ─────── (独立，读写 portfolio.json)                           │
│  auto_validator.py → Portfolio, RuleIndex                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                              反馈/进化层                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  feedback_loop.py → RuleIndex, DeepSeekClient                               │
│  rule_index.py ────── (独立，读写 skill_rules.jsonl)                        │
│  evolution_engine.py → (独立，PDF/Word解析)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                              辅助层                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  tracking_module.py → FeatureExtractor, DeepSeekClient                      │
│  llm_client.py ────── (独立，DeepSeek API封装)                              │
│  feishu_integration.py → (独立，lark-cli调用)                               │
│  report_generator.py → DeepSeekClient                                       │
│  input_adapter.py ─── (独立，输入归一化)                                    │
│  skill_knowledge.py ─ (独立，Skill知识底座)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  utils/tech_calculator/                                                     │
│  ├── trend.py, momentum.py, volatility.py, volume.py, pattern.py,           │
│  ├── levels.py, registry.py                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                              一次性脚本（待清理）                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  _ocr_book.py, _upload_ocr_to_feishu.py, _batch_repair_skills.py            │
│  repair_skills.py, extract_textbooks.py, demo.py, daily_track.py            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、关键变量名与数据流对照表

### 2.1 分析流程中的核心变量名

| 步骤 | 模块 | 核心变量名 | 类型 | 流向 |
|------|------|-----------|------|------|
| 数据下载 | api.py | `df` (DataFrame) | pd.DataFrame | → feature_extractor |
| 指标计算 | feature_extractor.py | `features` (Dict) | Dict[str, Any] | → skill_matcher, technical_analyzer |
|  |  | `features['trend']['price']` | float | 最新收盘价 |
|  |  | `features['trend']['trend_strength']['adx']` | float | ADX值 |
|  |  | `features['momentum']['rsi']['value']` | float | RSI(14) |
|  |  | `features['volatility']['atr']['value']` | float | ATR值 |
|  |  | `features['trend_stage']['stage']` | str | 趋势阶段 |
|  |  | `features['trend_stage']['extreme_deviation']` | bool | 极端偏离 |
| Skill匹配 | skill_matcher.py | `match_result` | Dict | → technical_analyzer |
|  |  | `match_result['triggered']` | List[Dict] | 触发技能 |
|  |  | `match_result['market_regime']` | str | 市场环境 |
| LLM分析 | technical_analyzer.py | `full_result` | Dict | → api.py组装 |
|  |  | `full_result['phase1_indicator_inventory']` | Dict | Phase 1 |
|  |  | `full_result['phase2_skill_application']` | Dict | Phase 2 |
|  |  | `full_result['phase3_synergy_conflict']` | Dict | Phase 3 |
|  |  | `full_result['phase4_conclusion']` | Dict | Phase 4 |
| 交易计划 | trade_planner.py | `plan` | Dict | → Portfolio |
|  |  | `plan['plan']['stop_loss']['dynamic_price']` | float | 动态止损 |
|  |  | `plan['plan']['risk_metrics']['grade']` | str | R:R评级 |
| 持仓 | portfolio.py | `positions[trade_id]` | Dict | 持仓字典 |
| 验证 | auto_validator.py | `outcome` | Dict | 验证结果 |

### 2.2 变量名一致性问题

| 问题 | 位置 | 说明 | 风险 |
|------|------|------|------|
| `amount` → `volume` 重命名 | api.py:130, tracking_module.py:328 | akshare返回`amount`列被重命名为`volume` | 一致，但tracking_module也重命名一次，冗余 |
| `market_regime` 三处定义 | api.py, skill_matcher.py, market_regime.py | api.py用`MarketRegime`对象；skill_matcher用字符串；pipeline用字符串 | **中风险** - 接口不统一，可能序列化失败 |
| `trade_plan` vs `plan` | trade_planner.py | `create_plan`返回外层叫`trade_plan`（含trade_id/plan/skills_triggered），内层叫`plan` | 容易混淆，TradePlanner内部`plan = trade_plan.get('plan', trade_plan)`做了兼容 |
| `position` 一词三义 | position_sizer.py | ①仓位大小(shares) ②position字典 ③职位 | 命名合理，上下文区分 |

---

## 三、代码与文档吻合度检查

### 3.1 ✅ 完全吻合

| 文档 | 代码 | 说明 |
|------|------|------|
| USER_GUIDE.md Step 1-5 | deterministic_pipeline.py analyze() | 8步流水线完全对应 |
| USER_GUIDE.md Step 6 (交易计划) | trade_planner.py create_plan() | 7要素齐全，R:R评级A/B/C/D |
| USER_GUIDE.md Step 8 (模拟开仓) | portfolio.py open_position() | 4项检查（资金/单标/总敞口/R:R） |
| USER_GUIDE.md Step 9 (每日跟踪) | portfolio.py daily_mark_to_market() | 盯市+止损检查 |
| USER_GUIDE.md Step 10 (自动验证) | auto_validator.py validate_trade() | 7步验证流程 |
| USER_GUIDE.md Step 11 (归因) | auto_validator.py _attribute_skills() | 逐条skill判断对错 |
| USER_GUIDE.md 4.4 交易计划规则 | trade_planner.py _evaluate_risk_reward() | 评级阈值一致 |
| SKILL.md 功能5/6 | trade_planner.py, auto_validator.py | 交易模拟+自动验证已实现 |
| README.md 系统架构 | 实际模块 | FeatureExtractor/SkillMatcher/TradePlanner等全部存在 |

### 3.2 ⚠️ 部分吻合/有差异

| 文档描述 | 实际代码 | 差异说明 | 建议 |
|----------|---------|---------|------|
| USER_GUIDE.md: "必须应用环境适配权重" | skill_matcher.py _apply_regime_adjustment() | 已应用，但**只调整triggered skill的detail，不修改rule本身权重** | 文档应明确说明是"临时调整"不是"永久调整" |
| USER_GUIDE.md: "Step 4.2 输出6种环境" | skill_matcher.py _detect_market_regime() | 输出6种，但**market_regime.py detect() 输出的是不同格式**（MarketRegime对象，primary/secondary/confidence） | 统一两处环境检测逻辑 |
| USER_GUIDE.md: "数据源优先级：本地CSV→akshare→yfinance→Eastmoney" | deterministic_pipeline.py _download_data() | pipeline只有本地→akshare→yfinance（**缺Eastmoney**） | pipeline补充eastmoney fallback |
| USER_GUIDE.md: "akshare → yfinance → eastmoney" | auto_validator.py _download_price_data() | 有3层fallback，✓吻合 | - |
| SKILL.md 系统架构图 | 实际代码 | **架构图中没有DeterministicPipeline** | 更新架构图 |
| SKILL.md: "api.py（统一入口）" | 实际 | api.py存在，但** DeterministicPipeline 是另一个独立入口** | 文档应说明双入口现状 |
| system-architecture.md | 实际代码 | 描述的是**旧9步分析流程**（Step 2-9），不是新4阶段 | 此文档已过时，需重写或标记 |
| INTERACTION_DESIGN.md | 实际代码 | 描述的旧流程，没有交易模拟/自动验证 | 需更新或标记过时 |

### 3.3 ❌ 不吻合/缺失

| 文档要求 | 实际状态 | 严重程度 |
|----------|---------|---------|
| api.py `analyze()` 应调用 DeterministicPipeline | **没有集成** - api.py走自己的老流程 | 🔴 高 |
| api.py `validate()` 应使用 AutoValidator | **仍用 feedback_loop.validate_record()** | 🔴 高 |
| api.py analyze() `skills_used=[]` 传空列表 | 应传入实际触发的skill IDs | 🟡 中 |
| DeterministicPipeline Step 5 market_regime | 硬编码`confidence: 0.8`，不是真实值 | 🟡 中 |
| SKILL.md: "此Skill与项目代码同步更新" | **未自动更新** - 手工维护 | 🟡 中 |

---

## 四、代码间钩稽关系详细检查

### 4.1 数据流正确性

```
api.py analyze() 数据流:
  1. df = download(symbol)                    ✓
  2. features = extractor.extract_all(df)     ✓
  3. regime = regime_detector.detect(df)      ✓ (但只用primary/secondary/confidence)
  4. result = analyzer.run_full_analysis(data) ✓
     - 内部: features = extractor.extract_all(df)  ← ⚠️ 重复计算！api.py已算过一次
     - 内部: skill_match = skill_matcher.match(features)
  5. result['indicator_summary'] = extractor.format_for_llm(features)  ✓
  6. feedback.record_analysis(result, skills_used=[])  ← ⚠️ skills_used=[] 永远空
  7. tracking.save_analysis_snapshot(symbol, result)   ✓
  8. feishu sync                                         ✓
```

**问题1: FeatureExtractor.extract_all() 被调用了两次**
- api.py:149 调用一次
- technical_analyzer.py:56 内部又调用一次
- 影响: 浪费计算，对大周期(200天)分析尤其明显
- 修复: technical_analyzer.run_full_analysis() 应优先使用传入的indicator_features

**问题2: skills_used=[] 永远为空**
- api.py:187 `skills_used=[]` 硬编码空列表
- 应该传入 `skill_match.get('triggered', [])` 中的skill IDs
- 影响: feedback_loop._update_skill_performance_probabilistic() 无法归因到具体skill

**问题3: MarketRegime 两个检测路径不一致**
- api.py 用 `MarketRegimeDetector.detect(df)` → 返回 MarketRegime 对象
- SkillMatcher 用 `_detect_market_regime(features)` → 返回字符串
- DeterministicPipeline 直接取 SkillMatcher 的结果
- 三处的环境判断逻辑**不完全一致**

### 4.2 关键方法调用链

```
TradePlanner.create_plan()
  ├── _select_stop_loss() → 返回 stop_loss dict
  │     └── 优先dynamic_atr (A), fallback fixed (B), fallback default 5% (C)
  ├── _calculate_position() → 返回 position dict
  │     └── PositionSizer.confidence_adjusted() (静态方法)  ← 注意：TradePlanner用类名调用
  │     └── PositionSizer.fixed_risk() (静态方法)
  ├── _evaluate_risk_reward() → 返回 rr_metrics dict
  │     └── 评级: A≥2.0, B≥1.0, C≥0.5, D<0.5
  ├── _estimate_target() → 如果LLM没给目标价
  ├── _estimate_timeframe() → 持有天数
  └── _detect_regime() → 市场环境

PositionSizer 方法状态:
  ├── fixed_risk()          → 被 TradePlanner._calculate_position() 调用 ✓
  ├── volatility_adjusted() → 未被调用（dead code?）
  ├── confidence_adjusted() → 被 TradePlanner._calculate_position() 调用 ✓
  ├── kelly_criterion()     → 未被调用
  └── calculate_position()  → 未被调用（整合方法，但没有入口）
```

**问题4: PositionSizer.calculate_position() 无人调用**
- 这是"综合仓位计算"方法，自动选择最优策略
- 但没有代码调用它
- TradePlanner._calculate_position() 直接调用 fixed_risk + confidence_adjusted

### 4.3 Portfolio 与 AutoValidator 协作

```
Portfolio.open_position(trade_plan)
  ├── 检查: cash足够 ✓
  ├── 检查: 单标的不超10% ✓
  ├── 检查: 总敞口不超50% ✓
  └── 保存到 portfolio.json ✓

Portfolio.check_stop_loss(trade_id, low, close)
  ├── long: intraday_hit = low <= stop ✓
  ├── long: close_hit = close <= stop ✓
  └── short: intraday_hit = low >= stop  ← ⚠️ 应该用 high >= stop

AutoValidator.validate_trade()
  ├── _find_trade() → 从 trades.jsonl 读取
  ├── _download_price_data() → akshare → yfinance → eastmoney ✓
  ├── _build_price_path() → 构建每日OHLC
  ├── _calculate_outcome() → 计算实际结果
  ├── _attribute_skills() → Skill级归因
  ├── _generate_lessons() → 教训生成
  ├── _update_portfolio() → 调用 Portfolio.close_position() ✓
  └── _update_skill_performance() → 调用 RuleIndex.update_performance() ✓
```

**问题5: Portfolio.check_stop_loss() short方向逻辑错误**
```python
# portfolio.py:313
intraday_hit = low_price >= stop_price  # 错误！应该用 high_price
```
空头止损是价格上涨时触发，应该检查high_price是否超过止损价。

**问题6: AutoValidator._update_skill_performance() skill_id不匹配**
```python
# auto_validator.py:472-473
skill_id = skill.get('id')  # trade_plan.skills_triggered 中的字段名
```
TradePlanner生成的skills_triggered字段名是`id`（见trade_planner.py:130），
但RuleIndex中的rule_id字段名是`rule_id`。
AutoValidator传入`skill.get('id')`到`rule_index.update_performance(skill_id, ...)`，
如果`id`字段的值就是rule_id则OK，需要验证。

---

## 五、可删除/需清理文件清单

### 5.1 🔴 建议删除（一次性脚本）

| 文件 | 类型 | 说明 |
|------|------|------|
| `_ocr_book.py` | 一次性 | OCR扫描版PDF，已用完 |
| `_upload_ocr_to_feishu.py` | 一次性 | 上传OCR结果到飞书 |
| `_batch_repair_skills.py` | 一次性 | 批量修复skill（已执行） |
| `repair_skills.py` | 一次性 | 修复skill（已执行） |
| `extract_textbooks.py` | 一次性 | 提取教材文本（已完成） |
| `demo.py` | 演示 | 早期演示脚本 |
| `daily_track.py` | 一次性 | 每日跟踪脚本（功能已合并到tracking_module） |

### 5.2 🟡 建议清理（历史数据/中间产物）

| 文件/目录 | 说明 | 建议操作 |
|-----------|------|---------|
| `data/muyuan_report.md` | 历史分析报告 | 移动到 `data/archive/` |
| `data/woge_603773_report.md` | 历史分析报告 | 移动到 `data/archive/` |
| `data/woge_603773_correct_report.md` | 历史分析报告 | 移动到 `data/archive/` |
| `data/woge_analysis_raw_response.md` | 原始LLM响应 | 移动到 `data/archive/` |
| `data/reflection_report_603773.md` | 反思报告 | 保留（有价值） |
| `data/extracted/*.md` | OCR提取的原始文本 | 移动到 `data/archive/extracted/` |
| `data/extracted/*_skills.json` | 提取的skill JSON | 保留（原始提取产物） |
| `data/extracted/*_segments.json` | 语义分段结果 | 移动到 `data/archive/` |
| `data/feishu_doc_cache/` | 飞书文档缓存 | 保留（运行时缓存） |
| `data/demo_records.json` | demo数据 | 删除 |
| `data/demo_stats.json` | demo数据 | 删除 |
| `300502_raw.json` | 临时数据 | 删除 |
| `data/muyuan_analysis_result.json` | 历史分析结果 | 移动到 `data/archive/` |
| `data/muyuan_extracted.json` | 历史提取结果 | 移动到 `data/archive/` |

### 5.3 🟢 过时文档（需更新而非删除）

| 文档 | 状态 | 建议 |
|------|------|------|
| `docs/system-architecture.md` | 描述旧9步流程 | **重写**为新4阶段+交易模拟架构 |
| `INTERACTION_DESIGN.md` | 无交易模拟/验证 | **更新**新增交互点 |
| `docs/SKILL_EXTRACTION_GUIDE.md` | 仍然有效 | 保留，但更新附录B接口 |
| `.claude/skills/technical-analysis-core/SKILL.md` | 描述旧8步分析 | **更新**为新4阶段+环境适配+交易模拟 |
| `.claude/skills/technical-analysis-core/references/` | 7个reference文件 | 保留（仍在使用） |
| `docs/superpowers/` | Claude Code设计文档 | **与项目无关**，可删除或移到外部 |

---

## 六、核心Bug/设计缺陷

### 6.1 🔴 必须修复

| # | 问题 | 位置 | 修复方案 |
|---|------|------|---------|
| 1 | api.py 未集成 DeterministicPipeline | api.py:92-213 | 重写 `analyze()` 调用 `dp.analyze()`，或标记api.py为deprecated |
| 2 | api.py validate() 未使用 AutoValidator | api.py:1307-1379 | 改为调用 `AutoValidator.validate_trade()` |
| 3 | `skills_used=[]` 永远为空 | api.py:187 | 传入 `skill_match_result.get('triggered', [])` |
| 4 | FeatureExtractor 重复计算 | technical_analyzer.py:56 | 优先使用传入的 `indicator_features`，不再内部重新计算 |
| 5 | Portfolio short止损逻辑错误 | portfolio.py:313 | `low >= stop` → `high >= stop` |

### 6.2 🟡 建议修复

| # | 问题 | 位置 | 修复方案 |
|---|------|------|---------|
| 6 | SkillMatcher alias_map 每次调用重建 | skill_matcher.py:396-476 | 移到 `__init__` 或模块级常量 |
| 7 | MarketRegime 两处检测逻辑不一致 | market_regime.py + skill_matcher.py | 统一为 `MarketRegimeDetector` 返回的字符串 |
| 8 | DeterministicPipeline Step 5 regime硬编码 | deterministic_pipeline.py:348-351 | 使用 SkillMatcher 返回的真实confidence |
| 9 | PositionSizer.calculate_position() 无人调用 | position_sizer.py:196 | 在TradePlanner中启用，或删除 |
| 10 | TradePlanner._generate_trade_id() 无唯一性保证 | trade_planner.py:387-391 | 添加随机后缀，或检查冲突 |
| 11 | AutoValidator _calculate_outcome short方向target逻辑 | auto_validator.py:340 | 空头target_reached应为 `min_low <= target_price` |

### 6.3 🟢 低优先级

| # | 问题 | 说明 |
|---|------|------|
| 12 | Portfolio._calculate_exposure() short计算 | 当前short也加到total中，逻辑正确但命名易混淆 |
| 13 | TrackingModule._compute_indicator_changes() key映射 | 映射键名与实际features键名可能不匹配 |
| 14 | FeedbackLoop._mock_price_history() | mock数据没有实际用途，可删除 |

---

## 七、未来演进方向

### 7.1 短期（1-2周）

| 方向 | 说明 | 优先级 |
|------|------|--------|
| **统一入口** | api.py 完全替换为 DeterministicPipeline 调用 | 🔴 |
| **文档同步** | 更新 SKILL.md / system-architecture.md / INTERACTION_DESIGN.md | 🔴 |
| **Bug修复** | 修复上述6个必须修复项 | 🔴 |
| **代码清理** | 删除一次性脚本，归档历史数据 | 🟡 |

### 7.2 中期（1-2月）

| 方向 | 说明 |
|------|------|
| **回测引擎** | 在历史数据上批量运行全部skill，选最优子集 |
| **多标的组合** | 考虑相关性，分散风险，组合级夏普比率 |
| **更丰富的仓位策略** | 启用 Kelly公式 / 波动率调整法（已有代码但未启用） |
| **Skill可视化** | HTML Dashboard展示skill触发状态、胜率趋势 |
| **分环境权重自动优化** | 基于验证数据自动优化 `_apply_regime_adjustment` 的权重参数 |

### 7.3 长期（3-6月）

| 方向 | 说明 |
|------|------|
| **机器学习归因** | 用SHAP值分析哪些指标组合最影响胜率 |
| **实盘对接** | 通过券商API真实下单（模拟→实盘） |
| **实时数据流** | websocket实时推送，盘中动态止损 |
| **多时间框架自动对齐** | 日线+60分钟+15分钟联动分析 |
| **市场状态预测** | 基于历史模式预测未来3-5天的市场环境变化 |

---

## 八、模块健康度评分

| 模块 | 行数 | 测试覆盖 | 文档匹配 | 接口稳定 | 综合 |
|------|------|---------|---------|---------|------|
| feature_extractor.py | 1202 | 未看到 | ✅ | ✅ | 🟢 A |
| skill_matcher.py | 604 | 未看到 | ✅ | ✅ | 🟢 A |
| trade_planner.py | 402 | 未看到 | ✅ | ⚠️ | 🟡 B+ |
| portfolio.py | 432 | 未看到 | ✅ | ⚠️ short逻辑 | 🟡 B |
| auto_validator.py | 507 | 未看到 | ✅ | ✅ | 🟢 A- |
| deterministic_pipeline.py | 717 | 未看到 | ✅ | ⚠️ 未集成 | 🟡 B |
| api.py | 1466 | 未看到 | ❌ 过时 | ❌ 双入口 | 🔴 C |
| feedback_loop.py | 348 | 未看到 | ⚠️ | ⚠️ 正被AutoValidator替代 | 🟡 B- |
| tracking_module.py | 459 | 未看到 | ✅ | ✅ | 🟢 A- |
| market_regime.py | 216 | 未看到 | ⚠️ 与skill_matcher不一致 | ⚠️ | 🟡 B |

---

*报告生成完毕。建议优先处理"6.1 必须修复"的5个问题，然后统一入口层。*
