"""DeepSeek 官方 API 客户端 - 技术分析核心引擎

迁移说明：
- 从火山引擎(ARK_API_KEY)迁移到 DeepSeek 官方 API
- Base URL: https://api.deepseek.com/v1
- 模型: deepseek-v4-pro
- 环境变量: DEEPSEEK_API_KEY
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import OpenAI

BASE_URL = "https://api.deepseek.com/v1"
MODEL_DEFAULT = "deepseek-v4-pro"


def _ensure_dict(obj: Any) -> Dict[str, Any]:
    """json.loads 可能返回 list/标量，统一包装成 dict，避免调用方 .get() 崩溃"""
    if isinstance(obj, dict):
        return obj
    return {'data': obj}


def _safe_parse_json(text: str) -> Dict[str, Any]:
    """安全解析JSON，处理 markdown 代码块包裹和不完整JSON

    策略：
    1. 去掉 markdown 代码块标记
    2. 尝试直接解析完整JSON（strict=False允许更多字符）
    3. 如果失败，尝试提取最大闭合JSON对象
    4. 尝试修复常见JSON错误（尾部逗号等）
    5. 如果都失败，返回 raw_response 保留原始文本
    """
    if not text or not text.strip():
        return {"raw_response": "", "parse_error": True, "error": "empty_response"}

    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # 尝试1：直接解析（strict=False更宽松）
    for strict in [True, False]:
        try:
            return _ensure_dict(json.loads(text, strict=strict))
        except (json.JSONDecodeError, ValueError):
            pass

    # 尝试2：提取最大闭合JSON对象
    extracted = _extract_json_object(text)
    if extracted:
        for strict in [True, False]:
            try:
                return _ensure_dict(json.loads(extracted, strict=strict))
            except (json.JSONDecodeError, ValueError):
                pass

    # 尝试3：修复尾部逗号后重新解析
    fixed = _fix_trailing_commas(text)
    if fixed != text:
        for strict in [True, False]:
            try:
                return _ensure_dict(json.loads(fixed, strict=strict))
            except (json.JSONDecodeError, ValueError):
                pass

    # 尝试4：修复 LLM 高频 JSON 语法错误后重新解析
    # a) 中文句子里直接写 ASCII 双引号（如 无强势"杯柄"中的杯体）→ 截断字符串
    # b) 裸数字后跟括号注释（如 "当前值": 13.38 (占股价10.85%),）→ 非法值
    repaired = _repair_common_llm_json_errors(text)
    if repaired != text:
        for candidate in [repaired, _fix_trailing_commas(repaired)]:
            for strict in [True, False]:
                try:
                    return _ensure_dict(json.loads(candidate, strict=strict))
                except (json.JSONDecodeError, ValueError):
                    pass

    # 尝试5：如果文本本身是一个JSON字符串（被引号包裹的JSON）
    try:
        if text.startswith('"') and text.endswith('"'):
            unquoted = json.loads(text)
            if isinstance(unquoted, str):
                return _ensure_dict(json.loads(unquoted))
    except (json.JSONDecodeError, ValueError):
        pass

    # 都失败了，返回原始文本
    return {"raw_response": text, "parse_error": True}


def _escape_inner_cjk_quotes(text: str) -> str:
    """转义被 CJK 字符夹住的内嵌 ASCII 双引号（LLM 高频 JSON 错误）"""
    import re
    # 引号前后都是 CJK → 内容引号（如 势"杯柄"中 的两个引号）
    return re.sub(r'(?<=[一-鿿])"(?=[一-鿿])', r'\\"', text)


def _repair_common_llm_json_errors(text: str) -> str:
    """组合修复 LLM 输出的高频 JSON 语法错误"""
    import re
    # b) 裸数字 + 括号注释 → 整体加引号变成字符串
    #    "当前值": 13.38 (占股价10.85%),  →  "当前值": "13.38 (占股价10.85%)",
    text = re.sub(r'(:\s*)(-?\d+(?:\.\d+)?)(\s*\([^)]*\))(\s*[,}\]])',
                  r'\1"\2\3"\4', text)
    # a) CJK 夹住的内嵌引号 → 转义
    text = _escape_inner_cjk_quotes(text)
    return text


def _fix_trailing_commas(text: str) -> str:
    """修复JSON中常见的尾部逗号问题"""
    import re
    # 移除对象和数组中的尾部逗号
    fixed = re.sub(r',(\s*[}\]])', r'\1', text)
    return fixed


def _extract_json_object(text: str) -> Optional[str]:
    """从文本中提取最大的闭合JSON对象"""
    best = None
    for start in range(len(text)):
        if text[start] != '{':
            continue
        brace_count = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == '\\':
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if not in_string:
                if c == '{':
                    brace_count += 1
                elif c == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        candidate = text[start:i+1]
                        if best is None or len(candidate) > len(best):
                            best = candidate
                        break
    return best


def _log_token_usage(resp, tag: str = ''):
    """把每次 API 调用的 token 用量落盘到 data/token_usage.jsonl（可追溯）

    DeepSeek 返回的 usage 含 prompt_cache_hit/miss_tokens，
    推理模型还有 completion_tokens_details.reasoning_tokens，
    这些是精确核算单次分析成本的依据。
    """
    usage = getattr(resp, 'usage', None)
    if usage is None:
        return
    try:
        record = {
            'ts': datetime.now().isoformat(timespec='seconds'),
            'model': getattr(resp, 'model', ''),
            'tag': tag,
            'prompt_tokens': getattr(usage, 'prompt_tokens', None),
            'completion_tokens': getattr(usage, 'completion_tokens', None),
            'total_tokens': getattr(usage, 'total_tokens', None),
            'cache_hit_tokens': getattr(usage, 'prompt_cache_hit_tokens', None),
            'cache_miss_tokens': getattr(usage, 'prompt_cache_miss_tokens', None),
        }
        details = getattr(usage, 'completion_tokens_details', None)
        if details is not None:
            record['reasoning_tokens'] = getattr(details, 'reasoning_tokens', None)
        os.makedirs('data', exist_ok=True)
        with open('data/token_usage.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    except Exception:
        pass  # 计量失败不影响主流程


class DeepSeekClient:
    """DeepSeek 官方大模型客户端"""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY not found. "
                "请设置环境变量 DEEPSEEK_API_KEY=sk-xxx 或传入 api_key 参数。"
                "获取地址: https://platform.deepseek.com/api_keys"
            )

        self.client = OpenAI(api_key=self.api_key, base_url=BASE_URL)
        self.model = MODEL_DEFAULT

    def _call(self, messages: List[Dict], temperature: float = 0.2,
              max_tokens: Optional[int] = None, tag: str = '') -> str:
        kwargs = {"model": self.model, "messages": messages, "temperature": temperature}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        # 带重试的API调用
        last_error = None
        for attempt in range(3):
            try:
                resp = self.client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content
                if content and content.strip():
                    _log_token_usage(resp, tag)
                    return content.strip()
                # 空响应，重试
                from utils.console import safe_print
                safe_print(f"  ⚠️ API返回空内容，第{attempt+1}次重试...")
                import time
                time.sleep(1 + attempt)
            except Exception as e:
                last_error = e
                from utils.console import safe_print
                safe_print(f"  ⚠️ API调用失败({attempt+1}/3): {e}")
                import time
                time.sleep(1 + attempt)

        raise RuntimeError(f"API调用失败（已重试3次）: {last_error}")

    def _build_prompt(self, scene: str, max_tokens: int = 8000, df=None) -> str:
        """使用SkillKnowledgeBase动态构建system prompt"""
        from utils.skill_knowledge import get_skill_kb
        return get_skill_kb().build_prompt(scene, include_rules=True, max_tokens=max_tokens, df=df)

    # ========== 核心业务 ==========

    def analyze_screenshot(self, image_path: str) -> Dict[str, Any]:
        """截图视觉分析（当前不可用：deepseek-v4-pro 不支持图片输入）

        已实测确认 DeepSeek 官方 API 拒绝 image_url 类型消息（400）。
        保留此方法用于将来接入支持视觉的模型。
        """
        raise NotImplementedError(
            "deepseek-v4-pro 不支持图片输入，截图分析不可用。"
            "如需恢复，请改用支持视觉的模型。"
        )

    def analyze_trend(self, price_data: List[Dict],
                      indicator_text: Optional[str] = None) -> Dict[str, Any]:
        """趋势分析"""
        system_prompt = self._build_prompt('trend', max_tokens=5000)
        summary = self._summarize_price_data(price_data)

        user_content = f"价格数据：\n{json.dumps(summary, ensure_ascii=False)}"
        if indicator_text:
            user_content += f"\n\n---\n\n{indicator_text}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        raw = self._call(messages, temperature=0.2)
        return _safe_parse_json(raw)

    def analyze_patterns(self, price_data: List[Dict],
                         indicator_text: Optional[str] = None) -> Dict[str, Any]:
        """形态识别"""
        system_prompt = self._build_prompt('patterns', max_tokens=6000)
        summary = self._summarize_price_data(price_data)

        user_content = f"价格数据：\n{json.dumps(summary, ensure_ascii=False)}"
        if indicator_text:
            user_content += f"\n\n---\n\n{indicator_text}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        raw = self._call(messages, temperature=0.2)
        return _safe_parse_json(raw)

    def analyze_indicators(self, price_data: List[Dict],
                           indicator_text: Optional[str] = None,
                           indicator_features: Optional[Dict] = None) -> Dict[str, Any]:
        """指标分析"""
        system_prompt = self._build_prompt('indicators', max_tokens=5000)
        summary = self._summarize_price_data(price_data)

        user_content = f"价格数据：\n{json.dumps(summary, ensure_ascii=False)}"
        if indicator_text:
            user_content += f"\n\n---\n\n{indicator_text}"
            user_content += "\n\n请基于上述精确的指标数据进行技术分析。注意：所有指标数值已通过数学公式精确计算，请直接引用这些数值进行分析，不需要重新计算。"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        raw = self._call(messages, temperature=0.2)
        return _safe_parse_json(raw)

    def analyze_volume_price(self, price_data: List[Dict],
                             indicator_text: Optional[str] = None,
                             indicator_features: Optional[Dict] = None) -> Dict[str, Any]:
        """量价分析"""
        system_prompt = self._build_prompt('volume_price', max_tokens=5000)
        summary = self._summarize_price_data(price_data)

        user_content = f"价格+成交量数据：\n{json.dumps(summary, ensure_ascii=False)}"
        if indicator_text:
            user_content += f"\n\n---\n\n{indicator_text}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        raw = self._call(messages, temperature=0.2)
        return _safe_parse_json(raw)

    def analyze_behavior(self, all_signals: Dict[str, Any],
                         indicator_text: Optional[str] = None) -> Dict[str, Any]:
        """资金行为解读"""
        system_prompt = self._build_prompt('behavior', max_tokens=6000)

        user_content = f"综合技术信号：\n{json.dumps(all_signals, ensure_ascii=False, indent=2)}"
        if indicator_text:
            user_content += f"\n\n---\n\n{indicator_text}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        raw = self._call(messages, temperature=0.3)
        return _safe_parse_json(raw)

    def infer_events(self, all_signals: Dict[str, Any],
                     indicator_text: Optional[str] = None) -> Dict[str, Any]:
        """事件推断"""
        system_prompt = self._build_prompt('events', max_tokens=7000)

        user_content = f"技术信号：\n{json.dumps(all_signals, ensure_ascii=False, indent=2)}"
        if indicator_text:
            user_content += f"\n\n---\n\n{indicator_text}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        raw = self._call(messages, temperature=0.3)
        return _safe_parse_json(raw)

    def calculate_score(self, all_signals: Dict[str, Any],
                        indicator_text: Optional[str] = None) -> Dict[str, Any]:
        """多维度评分"""
        system_prompt = self._build_prompt('scoring', max_tokens=8000)

        user_content = f"分析结果：\n{json.dumps(all_signals, ensure_ascii=False, indent=2)}"
        if indicator_text:
            user_content += f"\n\n---\n\n{indicator_text}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        raw = self._call(messages, temperature=0.2)
        return _safe_parse_json(raw)

    def analyze_full(self, price_data: List[Dict],
                     indicator_text: Optional[str] = None,
                     indicator_features: Optional[Dict] = None,
                     skill_match_result: Optional[Dict] = None,
                     regime: Optional[Dict] = None) -> Dict[str, Any]:
        """单轮全局分析 - 一次性分析所有维度（新架构核心方法）

        替代之前的7轮独立分析，在一个Prompt中完成：
        - Phase 1: 全维度指标盘点
        - Phase 2: Skill应用与触发验证
        - Phase 3: 跨维度协同与冲突裁决
        - Phase 4: 综合结论与风险

        Args:
            price_data: 价格数据列表
            indicator_text: FeatureExtractor格式化的指标文本
            indicator_features: 结构化指标数据（供SkillMatcher使用）
            skill_match_result: SkillMatcher.match()的输出
            regime: 市场状态 {'primary': ..., 'confidence': ...}

        Returns:
            包含 phase1/2/3/4 的完整分析结果
        """
        system_prompt = self._build_prompt('full', max_tokens=12000)

        # 注入市场状态上下文
        if regime:
            regime_info = (
                f"\n## 当前市场状态\n"
                f"- 主状态: {regime.get('primary', 'unknown')}\n"
                f"- 置信度: {regime.get('confidence', 0):.0%}\n"
                f"- 辅助状态: {regime.get('secondary', 'unknown')}\n"
            )
            system_prompt += regime_info

        # 构建用户输入：价格数据 + 精确指标 + Skill匹配结果
        parts = []

        # 1. 价格数据摘要
        summary = self._summarize_price_data(price_data)
        parts.append(f"## 价格数据\n{json.dumps(summary, ensure_ascii=False)}")

        # 2. 精确指标数据
        if indicator_text:
            parts.append(f"## 精确指标数据\n{indicator_text}")
            parts.append(
                "注意：以上所有指标数值已通过数学公式精确计算，"
                "请直接引用这些数值进行分析，不需要重新计算。"
            )

        # 3. Skill触发清单（由SkillMatcher系统精确匹配生成）
        if skill_match_result:
            from utils.skill_matcher import SkillMatcher
            skill_text = SkillMatcher.format_for_llm(skill_match_result)
            parts.append(f"## Skill匹配结果（系统精确匹配）\n{skill_text}")
        else:
            parts.append(
                "## Skill匹配结果\n暂无Skill匹配数据。"
                "请基于技术分析体系框架和指标数据进行独立分析。"
            )

        user_content = "\n\n".join(parts)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        raw = self._call(messages, temperature=0.2, tag='analyze_full')
        return _safe_parse_json(raw)

    def generate_report(self, all_results: Dict[str, Any]) -> str:
        """报告生成"""
        system_prompt = self._build_prompt('report', max_tokens=10000)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"分析数据：\n{json.dumps(all_results, ensure_ascii=False, indent=2)}"}
        ]
        return self._call(messages, temperature=0.3)

    # ========== 进化引擎业务 ==========

    def extract_knowledge_from_text(self, text: str, book_title: str = "") -> Dict[str, Any]:
        """书籍知识提取"""
        system_prompt = self._build_prompt('knowledge_extract', max_tokens=12000)

        text_truncated = text[:30000] if len(text) > 30000 else text
        user_content = f"书籍名称：{book_title}\n\n章节内容：\n\n{text_truncated}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        raw = self._call(messages, temperature=0.2)
        return _safe_parse_json(raw)

    def extract_skills_from_segment(self, segment_text: str,
                                     user_instruction: str = "") -> Dict[str, Any]:
        """从单段文本提取 Skill（分段交互式提取的核心方法）

        特点：
        1. 使用固定精简的 system prompt（~500 tokens），不加载 references
        2. 每次只处理一段文本（500-3000 tokens），额度消耗低
        3. 支持用户指导 prompt，可多次返工

        Args:
            segment_text: 单段原文（已提纯的方法论文本）
            user_instruction: 用户的提取指导（如"重点提取ADX判断法"、"threshold用原文值"）

        Returns:
            {"rules": [...], "summary": "..."}
        """
        from utils.skill_knowledge import build_segment_extract_prompt

        system_prompt = build_segment_extract_prompt()

        user_content = f"## 原文段落\n\n{segment_text}\n"
        if user_instruction:
            user_content += f"\n## 提取指导\n\n{user_instruction}\n"
        user_content += "\n请从上述段落中提取技术分析方法论 Skill，按指定 JSON 格式输出。"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        raw = self._call(messages, temperature=0.2)
        return _safe_parse_json(raw)

    def parse_natural_language_instruction(self, instruction: str) -> Dict[str, Any]:
        """NL指令解析"""
        system_prompt = self._build_prompt('nl_instruction', max_tokens=10000)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户指令：{instruction}"}
        ]
        raw = self._call(messages, temperature=0.3)
        return _safe_parse_json(raw)

    def auto_attribute_failure(self, record: Dict, price_history: List[Dict]) -> Dict[str, Any]:
        """归因分类"""
        system_prompt = self._build_prompt('attribution', max_tokens=5000)

        content = f"""分析记录：
- 结论: {record.get('verdict', 'unknown')}
- 目标价: {record.get('target_price', 'N/A')}
- 止损位: {record.get('stop_loss', 'N/A')}
- 形态: {json.dumps(record.get('identified_patterns', []), ensure_ascii=False)}

后续走势：
{json.dumps([{'date': h.get('date'), 'close': h.get('close')} for h in price_history[:20]], ensure_ascii=False)}
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content}
        ]
        raw = self._call(messages, temperature=0.2)
        return _safe_parse_json(raw)

    # ========== 跟踪分析 ==========

    def track_analysis(self, snapshot: Dict, current_features: Dict,
                       price_summary: Dict, indicator_changes: Dict,
                       key_level_status: Dict) -> Dict[str, Any]:
        """跟踪分析 - 评估预测vs实际，给出新判断

        Args:
            snapshot: 上次分析的快照
            current_features: 当前指标特征
            price_summary: 价格变化摘要
            indicator_changes: 指标变化描述
            key_level_status: 关键价位触发状态

        Returns:
            {
                "verdict_vs_expected": "符合预期/部分符合/不符合",
                "key_level_status_summary": "...",
                "indicator_trend": "...",
                "issues_found": [...],
                "new_judgment": "维持/修正/反转",
                "new_direction": "STRONGLY_BEARISH/...",
                "new_confidence": 0-100,
                "updated_targets": "...",
                "updated_stop": "...",
                "new_watch_points": [...],
                "reasoning": "..."
            }
        """
        from utils.skill_knowledge import TRACKING_SYSTEM_PROMPT

        # 构建用户输入
        parts = []

        # 1. 上次分析快照
        parts.append("## 上次分析快照\n")
        parts.append(f"- 分析日期: {snapshot.get('analysis_date', 'N/A')[:10]}")
        parts.append(f"- 当时价格: {snapshot.get('current_price', 'N/A')}")
        parts.append(f"- 判断方向: {snapshot.get('verdict', 'N/A')}")
        parts.append(f"- 置信度: {snapshot.get('confidence', 'N/A')}%")
        parts.append(f"- 目标价位: {snapshot.get('target_price', 'N/A')}")
        parts.append(f"- 止损价位: {snapshot.get('stop_loss', 'N/A')}")

        kl = snapshot.get('key_levels', {})
        if kl:
            parts.append("- 关键价位:")
            for k, v in kl.items():
                parts.append(f"  - {k}: {v}")

        wp = snapshot.get('watch_points', [])
        if wp:
            parts.append(f"- 观察点: {', '.join(wp)}")

        inv = snapshot.get('invalidation_conditions', [])
        if inv:
            parts.append(f"- 失效条件: {', '.join(inv)}")

        # 2. 最新价格数据
        parts.append("\n## 最新价格数据\n")
        parts.append(f"- 当前价格: {price_summary.get('current_price', 'N/A')}")
        parts.append(f"- 分析时价格: {price_summary.get('snapshot_price', 'N/A')}")
        parts.append(f"- 涨跌幅: {price_summary.get('change_pct', 'N/A')}%")
        parts.append(f"- 分析后最高: {price_summary.get('high_since', 'N/A')}")
        parts.append(f"- 分析后最低: {price_summary.get('low_since', 'N/A')}")
        parts.append(f"- 距分析日: {price_summary.get('days_since', 'N/A')} 天")

        # 3. 关键价位触发状态
        parts.append("\n## 关键价位触发状态\n")
        for k, v in key_level_status.items():
            parts.append(f"- {k}: {v}")

        # 4. 指标变化
        parts.append("\n## 指标变化对比\n")
        for name, info in indicator_changes.items():
            parts.append(f"- {name}: {info.get('text', 'N/A')}")

        # 5. 当前指标摘要
        parts.append("\n## 当前指标摘要\n")
        composite = current_features.get('composite', {})
        if composite:
            for k, v in composite.items():
                parts.append(f"- {k}: {v}")

        user_content = "\n".join(parts)
        user_content += "\n\n请基于上述信息，对上次分析的预测与实际走势进行对比评估，给出跟踪分析结论。按指定JSON格式输出。"

        messages = [
            {"role": "system", "content": TRACKING_SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ]
        raw = self._call(messages, temperature=0.2)
        return _safe_parse_json(raw)

    # ========== 工具方法 ==========

    def _summarize_price_data(self, price_data: List[Dict]) -> Dict[str, Any]:
        # 转换Timestamp为字符串
        def clean_record(d):
            r = dict(d)
            for k, v in list(r.items()):
                if hasattr(v, 'isoformat'):
                    r[k] = v.isoformat()
                elif hasattr(v, 'strftime'):
                    r[k] = v.strftime('%Y-%m-%d')
            return r

        clean_data = [clean_record(d) for d in price_data]

        if len(clean_data) <= 60:
            return {"data_points": len(clean_data), "data": clean_data}

        n = len(clean_data)
        early_samples = clean_data[::max(1, (n - 60) // 10)][:10]
        recent = clean_data[-50:]

        return {
            "data_points": n,
            "early_samples": early_samples,
            "recent_50": recent,
            "summary": {
                "first_close": clean_data[0].get('close') if clean_data else None,
                "last_close": clean_data[-1].get('close') if clean_data else None,
                "period_high": max([d.get('high', d.get('close', 0)) for d in clean_data]) if clean_data else None,
                "period_low": min([d.get('low', d.get('close', 0)) for d in clean_data]) if clean_data else None,
            }
        }
