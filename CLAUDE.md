# CLAUDE.md — 技术分析助手（Claude Code 固定任务流）

> 本文件是 Claude Code 在此仓库中工作时的**强制纪律**。
> 任何股票分析、跟踪、验证、Skill 提取请求，都必须按本文件的固定流程执行，
> 不得跳步、不得自由发挥、不得绕过代码中的确定性模块。

## 系统定位

教材级技术分析决策辅助系统（非投资建议工具）。核心链路：

```
精确指标计算（数学）→ Skill 确定性匹配（规则引擎）→ LLM 四阶段推理（只做判断，不做计算）
→ 交易计划（R:R 强制评估）→ 模拟持仓 → 每日跟踪 → 到期验证 → Skill 归因与权重更新
```

**分工原则**：所有数值由代码精确计算；LLM 只在精确数据 + Skill 触发清单之上做推理。
你（Claude Code）是流程的编排者和与用户的交互界面，**不是**指标计算器。

## 唯一入口

所有功能通过 `api.py` 调用，**禁止**自己重写分析逻辑或直接拼凑 prompt：

```python
from api import assistant
a = assistant()  # 需要环境变量 DEEPSEEK_API_KEY
```

## 固定任务流（按用户意图选择）

### 1. 分析股票 → 必须走确定性流水线（Step 1-8）

```python
result = a.analyze('603773', days=100, market='cn', simulate=False)
```

- 底层 `DeterministicPipeline.analyze()` 固化执行：请求解析 → 数据准备 →
  指标计算（12 维度 50+ 指标）→ Skill 匹配 + 环境适配 → LLM 四阶段分析 →
  （simulate=True 时）交易计划 → 输出 → 模拟开仓。执行轨迹自动落盘
  `data/pipeline_traces/`，**长期可追溯**。
- `days` 必须让用户明确（30 短线 / 100 中线 / 200 长线）。days<200 时
  sma200 类 Skill 不参与匹配，需在结果中说明。
- 输出必须包含：Phase 1-4、市场环境、触发/准触发 Skill 清单、
  （simulate 时）交易计划与 R:R 评级。**R:R 评级 D 必须明确建议不入场**。

### 2. 跟踪 → `a.track(symbol, market=..., days=...)`

对比上次快照，输出符合预期判断、关键价位状态、新方向。

### 3. 验证 → `a.validate_trade(trade_id)` / `a.batch_validate()`

到期或止损触发时执行，自动完成 Skill 归因和 performance 更新。

### 4. 上传书籍/材料提取 Skill → 交互式分段流程（人机协作）

严格按 `docs/SKILL_EXTRACTION_GUIDE.md` 执行，**禁止一次性整本批量提取**：

```python
a.upload_skill_book('book.pdf')        # 自动检测扫描版→OCR；返回清洗后全文
# → 你阅读全文，提出分段方案，用户审批
a.set_book_segments([...])             # 用户确认后设置
a.extract_book_segment(1, '提取指导')   # 逐段提取，每段用户审核
a.modify_extracted_skill(0, 'reference_data.阈值', '3倍量')  # 本地修改（零API）
a.save_book_skills()                   # 存入 pending 队列
a.activate_skill('rule_id')            # 用户确认后激活（激活才会参与分析）
```

- 扫描版 PDF 自动触发 OCR（本地 RapidOCR，默认前 100 页，可指定页码范围）。
- 新提取 Skill 的 trigger 指标名**必须**使用 `utils/skill_matcher.py` 中
  `alias_map` 可解析的名称（如 rsi_14、adx_value、close、sma20、pattern），
  否则该 Skill 永远不会触发。提取后应向用户报告每条 Skill 的 trigger 可解析性。

### 5. Skill 管理 → `a.list_skills()` / `a.skill_stats(id)` / `a.deactivate_skill(id)`

## 强制规则（违反即流程错误）

1. **不得**自己计算任何技术指标数值——一律来自 `FeatureExtractor`。
2. **不得**跳过 Skill 匹配直接让 LLM 分析——触发清单是 LLM 输入的必要组成部分。
3. **不得**在 R:R < 0.5（Grade D）时给出入场建议。
4. **不得**把 pending 状态的 Skill 当作已生效——只有 activate 后才参与匹配。
5. **不得**修改 `data/skill_rules.jsonl` 等核心数据文件后不跑测试。
6. 分析结果、跟踪、验证的可追溯文件（pipeline_traces / snapshots / trades.jsonl /
   feedback_records）不得删除。

## 测试

改动任何 `utils/` 或 `api.py` 代码后必须运行：

```bash
python -m pytest tests/ -q
python -m ruff check .
```

关键回归测试：`tests/test_bugfix_regression.py`（Skill 触发解析、交易状态流转、
空头止损、现金持久化等）、`tests/test_skill_extraction.py`（OCR 触发条件等）。

## 详细规范

- `USER_GUIDE.md` — 标准操作流程（SOP）的唯一权威来源
- `docs/SKILL_EXTRACTION_GUIDE.md` — Skill 提取人机协作流程
- `docs/system-architecture.md` — 系统架构
- `README.md` — 安装、使用、提取流程详细逻辑
