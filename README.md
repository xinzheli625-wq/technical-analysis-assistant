# 技术分析助手

基于 **1209 条教材 Skill 知识库** 的多维度技术分析系统，支持交易模拟与自动验证。

仓库地址：https://github.com/xinzheli625-wq/technical-analysis-assistant

> **免责声明**：本系统仅供学习和技术分析研究使用，不构成投资建议。所有交易决策由用户自行负责。

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **多维度分析** | 趋势 / 动量 / 波动率 / 量能 / 形态 / 背离 / 趋势阶段 / 多时间框架 |
| **Skill 知识库** | 1209 条教材 Skill，100% 有触发条件，77% 有信号方向 |
| **环境适配** | 自动检测市场环境，超买类 Skill 在强趋势末期限自动降权 |
| **交易模拟** | 生成交易计划（仓位 / 动态止损 / 目标 / R:R 评估） |
| **自动验证** | 3-5 天后自动验证预测，Skill 级归因，权重自动调整 |
| **风险收益比** | 自动计算并评级（A/B/C/D），不合格时明确拒绝 |
| **飞书文档同步** | 分析结果、跟踪记录自动写入飞书文档 |
| **多输入支持** | 股票代码、CSV/Excel（K线截图暂不可用：deepseek-v4-pro 不支持图片输入） |

---

## 安装

### 环境要求

- Python 3.10+
- Git

### 1. 克隆仓库

```bash
git clone https://github.com/xinzheli625-wq/technical-analysis-assistant.git
cd technical-analysis-assistant
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

或安装为可编辑包：

```bash
pip install -e ".[dev]"
```

### 3. 配置 API Key

```bash
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux
```

编辑 `.env` 文件：

```bash
DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here
```

> 注意：`.env` 文件已被 `.gitignore` 忽略，不会提交到仓库。

---

## 快速开始

### 分析一只股票

```python
from api import assistant

# 单次分析
result = assistant().analyze('AAPL', days=100, market='us')

# 生成交易计划并模拟开仓
result = assistant().analyze('603773', days=100, market='cn', simulate=True)
```

### 从文件分析

```python
result = assistant().analyze_from_file('data/sample_aapl_daily.csv', symbol='AAPL', market='us')
```

### 批量验证到期交易

```bash
python -m utils.auto_validator --batch
```

### 查看 Skill 统计

```python
from utils.rule_index import RuleIndex
print(RuleIndex().get_stats())
```

---

## Skill 提取流程（上传学习材料）

系统支持在 Claude Code 对话中上传教材/笔记/飞书文档，提炼为结构化 Skill 存入知识库。
整个流程是**人机协作**的：解析、清洗、OCR 等纯技术步骤全自动（零 API 消耗），
分段方案和每段提取结果必须经用户审批。完整交互规范见
[docs/SKILL_EXTRACTION_GUIDE.md](docs/SKILL_EXTRACTION_GUIDE.md)。

### 整体链路

```
用户上传材料（PDF / Word / 飞书文档 / 自然语言）
    ↓
[阶段0] 解析路由 + 扫描检测（本地，零 API）
    ├─ 文本版 PDF  → parse_pdf（pdfplumber）
    ├─ 扫描版 PDF  → parse_pdf_ocr（RapidOCR，本地模型）
    ├─ Word        → parse_word（python-docx）
    └─ 解析失败    → 回退为直接读取文件文本，流程不中断
    ↓
[阶段0] 文本清洗 clean_text（本地，零 API）
    ↓
[阶段1] Claude Code 语义分段 → 用户审批分段方案
    ↓
[阶段2] 逐段 LLM 提取（DeepSeek）→ 用户审核每段结果
    ↓   （可本地修改/删除/换指导词重新提取，零 API）
    ↓
保存到规则索引库（status=pending，不参与分析）
    ↓
[阶段3] 用户确认激活 → 知识库 reload → 后续分析生效
```

### 阶段 0：解析路由与 OCR 触发条件

入口 `assistant().upload_skill_book(file_path)` 按文件类型路由：

| 输入 | 判定 | 解析方式 |
|------|------|----------|
| `.pdf`，文本版 | `is_scanned_pdf()` 返回 False | `parse_pdf`（pdfplumber 逐页提取文本层） |
| `.pdf`，扫描版 | `is_scanned_pdf()` 返回 True | `parse_pdf_ocr`（RapidOCR 本地 OCR） |
| `.docx` 等其他后缀 | 不做扫描检测 | `parse_word`（python-docx） |
| 飞书文档 URL | — | `upload_skill_from_feishu()` 读取文档内容 |
| 自然语言描述 | — | `upload_skill_text()` 直接送 LLM 解析，无需分段 |

**扫描版检测算法**（`EvolutionEngine.is_scanned_pdf`）：

1. 用 PyMuPDF 打开 PDF，采样若干页：
   - 始终采样前 3 页（索引 0/1/2）；
   - 总页数 > 50 时加采中间页（`total // 2`）；
   - 总页数 > 100 时再加采 3/4 处页（`total * 3 // 4`）。
2. 采样页提取的文本 **> 50 字符** 才算"有文本层"
   （避免扫描件里的页码、水印被误判为文本）。
3. 有文本层的采样页占比 **< 20%（严格小于）→ 判定为扫描版，触发 OCR**。
   边界情况：5 个采样页中恰好 1 页有文本（= 20%）时按文本版处理。
4. 检测过程出现任何异常（文件损坏等）→ **默认按文本版处理**，
   由 `parse_pdf` 的失败回退兜底，绝不因误判扫描版而浪费 OCR 时间。

**OCR 执行**（`EvolutionEngine.parse_pdf_ocr`）：

- 引擎：RapidOCR（ONNX 轻量模型），完全本地运行，零 API 消耗；
- 流程：PyMuPDF 将每页渲染为 PNG（默认 200 DPI）→ RapidOCR 识别 →
  拼接文本，临时图片随用随删；
- **默认只识别前 100 页**（`page_start=1, page_end=100`），防止整本 OCR 过慢，
  需要更大范围时可通过参数覆盖；
- 每 10 页打印一次进度。

**失败回退**：`parse_pdf` / `parse_word` 在专用库解析失败时，
回退为按 UTF-8 直接读取文件内容，保证流程不中断。

### 阶段 0：文本清洗规则（`clean_text`）

| 规则 | 说明 |
|------|------|
| 去纯数字行 | 页码 |
| 去"第 X 页" / "Page X" 行 | 中英文页码标记 |
| 去连续重复行 | 跨页重复出现的页眉（非连续重复保留，避免误删正文术语） |
| 压缩连续空行 | 多个空行合并为一个，保留段落分隔 |

### 阶段 1：语义分段（`set_book_segments`）

清洗后的全文由 Claude Code 理解结构、提出分段方案，用户审批后调用
`set_book_segments(segments_config)` 设置。分段定位机制：

- 每段用 `start_marker` / `end_marker` 定位，marker 是**原文中的整行文本**
  （strip 后精确匹配）；
- `end_marker` 可省略：自动以**下一段的 `start_marker`** 作为本段结束；
- 分段原则：概念章合并、方法论密集章单独成段，每段约 500–3000 tokens。

### 阶段 2：逐段 LLM 提取（`extract_book_segment`）

- 一次只提取一段：只把该段原文（而非全书）发给 DeepSeek，
  可选附带用户的自然语言指导（如"threshold 用原文值，不要编造"）；
- LLM 返回教材式 Skill JSON（name / category / core_idea / analysis_steps /
  reference_data / win_rate_hint / common_pitfalls / when_not_to_use /
  applicable_regimes），格式详见提取指南附录 A；
- JSON 解析失败时原样返回原始内容（`parse_error=True`），不污染缓存；
- 提取结果缓存在本地，用户可用以下零 API 接口审核：
  - `modify_extracted_skill(index, field, value)`：修改字段，
    支持点号嵌套（如 `reference_data.关键阈值`）；
  - `remove_extracted_skill(index)`：删除不满意的条目；
  - 换指导词重新调用 `extract_book_segment` 返工。

### 阶段 2→3：保存与激活

- `save_book_skills()`：审核通过的 Skill 写入规则索引库
  （`data/skill_rules.jsonl`），状态为 **`pending`（不参与分析）**；
  写入前统一经 `_convert_to_methodology_format` 转换为教材格式并补全
  `trigger` / `signal` 字段（兼容旧格式规则）；
- `activate_skill(rule_id)`：用户确认后激活，激活时自动
  **reload Skill 知识库**，之后的分析立即生效；
- 防重复：每本书按文件 MD5 记入 `data/book_registry.json`，
  整本自动模式（`auto_extract=True`）下同一本书不会重复提取。

### 对应测试

以上每个环节的触发条件都有测试覆盖（`tests/test_skill_extraction.py`，50 条用例）：

- 扫描版检测：全无文本 / 全文本 / 短文本（≤50 字符）/ 20% 边界 / 大书采样点 / 异常回退；
- 路由决策：文本版绝不走 OCR、扫描版必须走 OCR、OCR 默认前 100 页、
  Word 不做扫描检测、任何路径都必须经过清洗；
- 清洗：各类页码、连续重复页眉、非连续重复保留、空行压缩；
- 分段：marker 定位、end_marker 自动推断、非法段 ID、marker 未命中；
- 提取：未加载书籍报错、只发送当前段原文、指导词透传、解析失败不污染缓存；
- 管理：嵌套字段修改、越界保护、pending 保存（`auto_activate=False`）、
  激活触发知识库 reload、书籍注册表持久化、解析回退、飞书导入、便捷函数。

---

## 飞书文档同步

系统支持将分析结果、跟踪记录、验证结果自动同步到飞书文档。

### 前置条件

1. 安装飞书命令行工具 [lark-cli](https://open.larksuite.com/document/tools-and-resources/cli/overview) 并登录：

   ```bash
   lark-cli auth login
   ```

2. 首次运行时会自动在飞书云盘中创建文件夹 `技术分析助手`，并为每只股票创建独立分析文档。

### 启用同步

```python
from api import assistant

a = assistant()
a.enable_feishu()  # 启用飞书同步

# 分析后会自动同步到飞书
result = a.analyze('AAPL', days=100, market='us')
```

### 手动同步已有分析

```python
# 重新同步某只股票的分析到飞书
a._sync_to_feishu('AAPL', result)

# 同步跟踪更新
a.track('AAPL', market='us', days=100)
```

### 查看已同步文档

```python
from utils.feishu_integration import FeishuIntegration

feishu = FeishuIntegration()
print(feishu.list_stock_docs())
print(f"汇总文档: {feishu.get_records_doc_url()}")
```

### 缓存说明

飞书文件夹、文档 token 会缓存到 `data/feishu_cache.json`，避免重复创建。该文件已加入 `.gitignore`，不会提交到仓库。

---

## 标准操作流程（SOP）

每次分析严格遵循以下 8 步流水线：

```
用户请求
    ↓
Step 1: 请求解析
    ↓
Step 2: 数据准备（本地 CSV → akshare → yfinance）
    ↓
Step 3: 指标计算（50+ 指标精确计算）
    ↓
Step 4: Skill 匹配 + 环境适配
    ↓
Step 5: LLM 四阶段分析（Phase 1/2/3/4）
    ↓
Step 6: 交易计划生成（simulate=True 时）
    ↓
Step 7: 结果输出
    ↓
Step 8: 模拟开仓（simulate=True 时）
```

详见 [USER_GUIDE.md](USER_GUIDE.md)。Claude Code 在此仓库工作时自动加载
[CLAUDE.md](CLAUDE.md) 中的固定任务流纪律。

---

## 分析流程设计（维度 / Skill 触发 / 模型交互）

### 核心分工原则

```
代码（确定性）                LLM（推理）
─────────────                ─────────────
精确计算所有指标数值     →    不计算任何数值
确定性匹配 Skill 触发    →    在触发清单之上做四阶段推理
R:R 强制评估、仓位计算   →    给出方向、置信度、关键价位
```

LLM 只做判断，不做计算——所有数值在送入 prompt 前已由数学公式确定。

### 分析维度（Step 3，FeatureExtractor.extract_all）

每次分析固定计算 12 个维度、50+ 指标，不按场景裁剪：

| 维度 | 内容 |
|------|------|
| `raw` | 最新 K 线 OHLCV（供 Skill 条件直接引用 close/open 等） |
| `trend` | SMA/EMA 全系（3-200 共 13 个周期）、ADX、SuperTrend、Ichimoku、Parabolic SAR |
| `momentum` | RSI、MACD、KDJ、Stochastic、CCI、Williams %R、TSI、AO、UO、PPO、StochRSI |
| `volatility` | ATR、Bollinger、Keltner、Donchian、历史波动率、Ulcer Index |
| `volume` | 量比、OBV、VWAP、MFI、Chaikin Osc、Force Index、NVI/PVI |
| `pattern` | 18 种形态检测、波段点、缺口分类、支撑阻力 |
| `levels` | 枢轴点、斐波那契、最近支撑/阻力及距离 |
| `divergence` | 价格-RSI/MACD/OBV 背离检测与强度 |
| `trend_stage` | 趋势阶段（early/middle/late/fading/ranging）+ 极端偏离警告 |
| `volatility_state` | squeeze/expansion 状态与带宽趋势 |
| `momentum_accel` | RSI/MACD/价格加速度 |
| `multi_timeframe` | 短/中/长期趋势一致性 |
| `composite` | 综合状态与 1/5/20 日收益 |

### Skill 触发机制（Step 4，SkillMatcher）

触发是**确定性规则引擎**，不是 LLM 判断：

1. 每条 Skill 携带结构化 `trigger`：`{conditions: [{indicator, operator, value|value_ref}], logic: AND|OR}`
2. `indicator` 名称经 **alias_map** 映射到指标路径（如 `rsi_14` → `momentum.rsi.value`，
   `close` → `raw.close`）；**alias_map 是 Skill 库与指标体系的契约**——
   新提取的 Skill 必须使用可解析的指标名，否则该 Skill 永远不会触发
   （`tests/test_bugfix_regression.py` 对规则库全部指标名做了解析性回归）。
3. 条件评估输出三态：`triggered` / `near_triggered`（距阈值 ≤20%）/ `not_triggered`；
   形态条件（`indicator: "pattern"`）按 `patterns_detected` 名称匹配。
4. **环境适配**：基于 ADX + 趋势阶段 + 极端偏离判定 6 种市场环境，
   在送入 LLM 前完成权重调整（如强趋势末期超买类 bearish Skill -0.3）。

### 模型交互（Step 5，单轮全局分析）

一次 LLM 调用完成四阶段，而非多轮拼装：

- **System prompt**（SkillKnowledgeBase 动态构建）：场景相关类别的核心框架
  （references 精炼版，约 30% 预算）+ 规则索引库中按环境/胜率筛选的具体规则
  （约 60% 预算）+ 四阶段输出格式约束。
- **User message**：价格摘要 + 精确指标文本 + Skill 触发清单
  （triggered/near_triggered，含每条证据和调整后权重）。
- **输出**：严格 JSON 的 Phase 1（指标盘点）→ Phase 2（Skill 应用）→
  Phase 3（协同/冲突裁决 + 反转概率）→ Phase 4（结论/价位/风险），
  要求每条结论引用具体数值、可追溯。

### 可追溯性

| 产物 | 位置 | 内容 |
|------|------|------|
| 流水线轨迹 | `data/pipeline_traces/` | 每次分析 8 步的状态、耗时、错误 |
| 分析快照 | `data/snapshots/` | 指标签名 + 关键价位，供跟踪对比 |
| 反馈记录 | `data/feedback_records.json` | 分析记录与验证结果 |
| 模拟交易 | `data/simulation/trades.jsonl` | 计划→开仓→验证全生命周期 |
| Skill 性能 | `data/skill_rules.jsonl` | 每条 Skill 的胜率（含分环境统计） |

---

## 项目结构

```
.
├── api.py                          # Claude Code 统一调用入口
├── utils/
│   ├── deterministic_pipeline.py   # SOP 固化执行流水线
│   ├── feature_extractor.py        # 50+ 技术指标精确计算
│   ├── market_regime.py            # 市场环境检测
│   ├── skill_matcher.py            # 1209 条 Skill 条件匹配
│   ├── technical_analyzer.py       # LLM 四阶段分析入口
│   ├── trade_planner.py            # 交易计划生成
│   ├── portfolio.py                # 模拟持仓管理
│   ├── auto_validator.py           # 自动验证与归因
│   ├── feedback_loop.py            # 反馈闭环
│   ├── rule_index.py               # Skill 索引与性能追踪
│   ├── evolution_engine.py         # Skill 进化引擎
│   ├── tracking_module.py          # 每日跟踪
│   ├── data_source.py              # 统一数据下载接口
│   ├── feishu_integration.py       # 飞书文档同步
│   └── tech_calculator/            # 各维度指标计算模块
├── data/
│   ├── skill_rules.jsonl           # Skill 规则库（核心资产）
│   ├── sample_aapl_daily.csv       # 示例数据
│   └── simulation/                 # 模拟交易数据（运行时生成）
├── docs/
│   ├── system-architecture.md      # 系统架构文档
│   └── SKILL_EXTRACTION_GUIDE.md   # Skill 提取指南
├── tests/                          # 测试用例
├── README.md                       # 本文件
├── USER_GUIDE.md                   # 用户使用指南与 SOP
├── requirements.txt                # 依赖列表
└── pyproject.toml                  # 包配置
```

---

## 配置说明

所有敏感配置通过环境变量管理：

| 环境变量 | 必填 | 说明 |
|----------|------|------|
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API Key |

其他参数（如分析天数、市场、初始资金等）均在调用时通过参数传入，不写入配置文件，保证灵活性。

---

## 测试

### 运行全部测试

```bash
python -m pytest tests/ -v
```

### 运行单个测试文件

```bash
python -m pytest tests/test_feedback_loop.py -v
```

### 代码检查（可选，需安装 dev 依赖）

```bash
ruff check .
mypy utils
```

---

## 数据管理

- **核心资产**（已加入版本控制）：
  - `data/skill_rules.jsonl`
  - `data/skill_rules_index.json`
  - `data/indicator_registry.json`
  - `data/sample_aapl_daily.csv`

- **运行时生成**（已忽略）：
  - `data/simulation/`
  - `data/snapshots/`
  - `data/tracking/`
  - `data/pipeline_traces/`
  - `data/feedback_records.json`
  - `data/statistics.json`
  - `.env`

---

## 主要文档

| 文档 | 内容 |
|------|------|
| [CLAUDE.md](CLAUDE.md) | Claude Code 固定任务流纪律（会话自动加载） |
| [USER_GUIDE.md](USER_GUIDE.md) | 用户使用指南与标准操作流程（SOP） |
| [INTERACTION_DESIGN.md](INTERACTION_DESIGN.md) | 人机交互设计 |
| [docs/system-architecture.md](docs/system-architecture.md) | 系统架构详细说明 |
| [docs/SKILL_EXTRACTION_GUIDE.md](docs/SKILL_EXTRACTION_GUIDE.md) | 从教材提取 Skill 的标准流程 |

---

## 贡献与改进

已完成：核心模块回归测试（Skill 触发解析、交易流转、提取流程）、全仓库 ruff 清零。

当前已知改进方向：

1. 将 `api.py` 拆分为更小职责的模块。
2. 将 `skill_knowledge.py` 中的超长 prompt 拆成独立模板文件；
   `_extract_core_framework` 目前是启发式行过滤，信息有损，可改为人工策划的框架摘要。
3. 市场环境检测存在三处实现（`MarketRegimeDetector` / `SkillMatcher._detect_market_regime` /
   `TradePlanner._detect_regime`），建议统一为单一事实源。
4. mypy 目前为建议性检查（动态 dict 结构存量噪音较多），逐步收紧类型。
5. 引入 logging 替代 print。
6. 飞书集成：当前基于 `lark-cli` subprocess，后续可迁移到 Lark OpenAPI 以获得更稳定的错误处理。
7. 端到端集成测试（含真实数据源与 LLM 的 mock）。
8. 可追溯性增强：分析时记录规则库版本哈希，保证历史分析可复现。

---

## License

MIT
