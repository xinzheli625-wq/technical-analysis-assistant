# Skill 提取操作指南（严格流程版）

> 从技术分析教材中提取结构化 Skill 的**人机协作**标准操作流程。
>
> **核心原则**：用户必须在每个关键决策点参与审批。禁止一次性批量提取所有段。

---

## 阶段 0：文件预处理（OCR 检测）

**触发条件**：用户上传 PDF / Word / 图片文件

**Claude Code 动作**：

1. 检测文件类型和是否为扫描版（`is_scanned_pdf`）
2. 如果是扫描版 → 调用 OCR（`parse_pdf_ocr`），输出 `*_ocr.txt`
3. 如果是文本版 → 直接提取文本（`parse_pdf` 或 `parse_word`）
4. 对文本进行清洗（`clean_text`：去页眉页脚、页码、重复行）

**用户参与**：无（纯技术步骤）

---

## 阶段 1：目录提取与分段（需用户审批）

**Claude Code 动作**：

### 1.1 提取目录结构

读取清洗后的全文，识别章节标题和页码范围，输出完整目录：

```
=== 书籍目录 ===
Ch 1  Introduction ........................ P1
Ch 2  A Historical Background .............. P14
Ch 3  Constructing the Candlesticks ........ P21
...
```

### 1.2 提出分段方案

根据章节内容密度提出分段建议。每段标注：

| 字段 | 说明 |
|------|------|
| `segment_id` | 段编号 |
| `title` | 段标题 |
| `page_range` | 页码范围 |
| `core_content` | 核心内容摘要（3-5 句话） |
| `note` | 提取建议 |

**分段原则**：
- 纯概念/历史章：合并或标注"可跳过"
- 方法论密集章：单独一段，标注"重点提取"
- 每段控制在 500-3000 tokens（约 1500-9000 中文字）

### 1.3 展示给用户审批

```
=== 分段方案（请审批）===

[段1] 基础理论（P1-XX）
核心内容：道氏理论三大前提、趋势定义、峰谷结构...
建议：概念为主，提取为定义型 Skill

[段2] 趋势与支撑阻挡（PXX-XX）
核心内容：趋势线画法、支撑阻力识别、管道线...
建议：方法论密集，重点提取

...

请确认或修改：
- 哪些段保留 / 合并 / 删除？
- 段标题是否需要调整？
```

**用户参与**：
- 审批分段方案（确认 / 修改 / 合并 / 删除）
- 调整段标题和提取重点
- **审批通过后，进入阶段 2**

---

## 阶段 2：逐段 LLM 提取（每段需用户确认）

**对每一段重复以下流程**：

### Step 2.1 展示当前段信息

```
=== 段 {N}: {title} ===
页码范围：P{X}-P{Y}
预估字符数：{Z}

本段核心原文预览（前 500 字）：
---
{preview}
---

现在向 LLM 发送提取请求。
```

### Step 2.2 询问用户是否需要补充说明

```
是否需要为本段添加自然语言说明（指导 LLM 提取重点）？

例如：
- "重点提取锤子线的确认条件"
- "threshold 用原文值，不要编造"
- "区分反转形态和持续形态"

选项：
1. 直接提取（不加说明）
2. 添加说明（请输入）：
```

### Step 2.3 调用 LLM 提取

根据用户选择：
- 选项 1：直接调用 `extract_skills_from_segment(segment_text)`
- 选项 2：调用 `extract_skills_from_segment(segment_text, user_instruction="用户输入的说明")`

### Step 2.4 展示提取结果

```
=== 段 {N} 提取结果 ===
共提取 {X} 个 Skill：

[0] {skill_name} ({category})
    Core: {core_idea}

[1] {skill_name} ({category})
    Core: {core_idea}
    ...
```

### Step 2.5 用户审核提取结果

```
请审核本段提取结果：
- 哪些 Skill 保留 / 删除 / 修改？
- 是否需要调整字段（如 reference_data、win_rate_hint）？
- 是否重新提取（换说明词）？
```

### Step 2.6 保存审核通过的 Skill

用户确认后，保存到索引库（状态：`pending`）。

**循环**：重复 Step 2.1-2.6，直到所有段处理完毕。

---

## 阶段 3：批量激活（可选）

全部段处理完成后：

```
全部 {N} 段提取完成，共 {X} 个 Skill 待激活。
是否全部激活？（激活后将用于股票分析）
- 全部激活
- 逐条审核后激活
- 暂不激活
```

---

## 附录 A：输出格式（LLM 返回的 Skill 结构）

```json
{
  "rules": [
    {
      "name": "方法论名称（简洁，8字以内）",
      "category": "trend/patterns/indicators/volume_price/behavior/events/scoring",
      "type": "methodology",
      "core_idea": "这个方法解决什么问题，在什么场景下使用",
      "analysis_steps": [
        "步骤1：检查什么指标，判断标准是什么",
        "步骤2：结合哪些其他指标确认",
        "步骤3：综合判断的逻辑和出场条件"
      ],
      "reference_data": {
        "关键阈值": "数值参考（用原文中的值）",
        "典型周期": "指标常用周期",
        "其他参数": "原文中提到的其他关键数值"
      },
      "win_rate_hint": {
        "trending_up": 0.0,
        "trending_down": 0.0,
        "ranging": 0.0
      },
      "common_pitfalls": [
        "常见误区1",
        "常见误区2"
      ],
      "when_not_to_use": [
        "不适用场景1"
      ],
      "applicable_regimes": ["trending_up", "trending_down", "ranging", "volatile"]
    }
  ],
  "summary": "本段提取了 N 个方法论，涵盖..."
}
```

## 附录 B：技术接口参考

```python
from api import assistant
a = assistant()

# 修改某个 Skill 的字段
a.modify_extracted_skill(0, 'reference_data.关键阈值', 'RSI>70')

# 删除不满意的 Skill
a.remove_extracted_skill(2)

# 保存到规则索引库
a.save_book_skills()

# 激活 Skill
a.activate_skill("rule_id")
```

## 附录 C：环境设置

```bash
# Windows 避免编码问题
export PYTHONIOENCODING=utf-8
export DEEPSEEK_API_KEY=your_key
```

## 附录 D：关键原则速查

| 原则 | 说明 |
|------|------|
| **用户必须在场** | 分段方案和每段提取都需要用户审批 |
| **逐段进行** | 一段审批通过后再进行下一段 |
| **自然语言指导** | 每段发送前询问用户是否需要补充说明 |
| **可回滚** | 每段提取结果独立保存，可随时修改/删除 |
| **零批量** | 禁止一次性批量提取所有段 |
