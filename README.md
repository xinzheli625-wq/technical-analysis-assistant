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
| **多输入支持** | 股票代码、CSV/Excel、K 线截图 |

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

详见 [USER_GUIDE.md](USER_GUIDE.md)。

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
| [USER_GUIDE.md](USER_GUIDE.md) | 用户使用指南与标准操作流程（SOP） |
| [INTERACTION_DESIGN.md](INTERACTION_DESIGN.md) | 人机交互设计 |
| [docs/system-architecture.md](docs/system-architecture.md) | 系统架构详细说明 |
| [docs/SKILL_EXTRACTION_GUIDE.md](docs/SKILL_EXTRACTION_GUIDE.md) | 从教材提取 Skill 的标准流程 |

---

## 贡献与改进

当前已知改进方向：

1. 补充核心模块单元测试（`FeatureExtractor`、`SkillMatcher`、`TradePlanner`、`Portfolio`）。
2. 将 `api.py` 拆分为更小职责的模块。
3. 将 `skill_knowledge.py` 中的超长 prompt 拆成独立模板文件。
4. 引入配置系统，支持热加载。
5. 引入 logging 替代 print。
6. 飞书集成从 `lark-cli` subprocess 迁移到 Lark OpenAPI。

欢迎提交 Issue 和 PR。

---

## License

MIT
