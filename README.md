# 技术分析助手

基于1209本教材Skill知识库的多维度技术分析系统，支持交易模拟与自动验证。

## 快速开始

```bash
# 分析一只股票（含交易模拟）
python -c "from api import assistant; print(assistant().analyze('603773', days=100, simulate=True))"

# 批量验证到期交易
python -m utils.auto_validator --batch

# 查看Skill统计
python -c "from utils.rule_index import RuleIndex; print(RuleIndex().get_stats())"
```

## 核心能力

| 能力 | 说明 |
|------|------|
| **多维度分析** | 趋势/动量/波动率/量能/形态/背离/趋势阶段/多时间框架 |
| **Skill知识库** | 1209条教材Skill，100%有触发条件，77%有信号方向 |
| **环境适配** | 自动检测市场环境，超买类Skill在强趋势末期限自动降权 |
| **交易模拟** | 生成交易计划（仓位/动态止损/目标/R:R评估） |
| **自动验证** | 3-5天后自动验证预测，Skill级归因，权重自动调整 |
| **风险收益比** | 自动计算并评级（A/B/C/D），不合格时明确拒绝 |

## 标准操作流程（SOP）

见 [USER_GUIDE.md](USER_GUIDE.md) — 每次调用必须遵循的固定流程。

## 系统架构

```
用户请求
    ↓
api.py — 统一入口
    ↓
├─ FeatureExtractor — 50+指标精确计算
├─ SkillMatcher — 1209条Skill条件匹配（含环境适配权重）
├─ TechnicalAnalyzer — LLM四阶段分析（Phase 1/2/3/4）
├─ TradePlanner — 交易计划生成（仓位/止损/目标/R:R）
├─ Portfolio — 模拟持仓管理
├─ AutoValidator — 自动验证与归因
└─ RuleIndex — Skill索引与性能追踪
    ↓
分析报告 + 交易计划 + 验证报告
```

## 数据目录

| 目录 | 内容 |
|------|------|
| `data/skill_rules.jsonl` | 1209条Skill规则 |
| `data/predictions.json` | 预测记录与验证结果 |
| `data/simulation/` | 模拟交易与组合状态 |
| `data/snapshots/` | 分析快照 |
| `data/tracking/` | 每日跟踪记录 |

## 环境变量

```bash
DEEPSEEK_API_KEY=sk-xxx  # DeepSeek API Key
```

## 文档索引

| 文档 | 内容 |
|------|------|
| [USER_GUIDE.md](USER_GUIDE.md) | 用户使用指南与SOP |
| [INTERACTION_DESIGN.md](INTERACTION_DESIGN.md) | 人机交互设计 |
| [docs/system-architecture.md](docs/system-architecture.md) | 系统架构 |
| [docs/SKILL_EXTRACTION_GUIDE.md](docs/SKILL_EXTRACTION_GUIDE.md) | Skill提取指南 |
| `.claude/skills/technical-analysis-assistant/SKILL.md` | Claude Code Skill定义 |
| `.claude/skills/technical-analysis-core/SKILL.md` | 核心分析方法论 |
