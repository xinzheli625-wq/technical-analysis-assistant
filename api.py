"""技术分析助手 - Claude Code统一调用入口

这个模块提供简洁的API，让Claude Code可以通过自然语言对话
直接调用技术分析系统的所有功能。

使用方式：
    from api import assistant
    result = assistant.analyze("AAPL", days=100)  # 从yfinance下载
    result = assistant.analyze_from_file("data.csv")  # 从文件读取
    result = assistant.analyze_screenshot("chart.png")  # 截图分析
"""

import os
import json
import yfinance as yf
import pandas as pd
from typing import Dict, List, Any, Optional

from utils.feature_extractor import FeatureExtractor
from utils.market_regime import MarketRegimeDetector
from utils.technical_analyzer import TechnicalAnalyzer
from utils.feedback_loop import FeedbackLoop
from utils.evolution_engine import EvolutionEngine
from utils.rule_index import RuleIndex
from utils.llm_client import DeepSeekClient


class TechnicalAnalysisAssistant:
    """技术分析助手 - 统一的Claude Code调用入口

    这个类封装了所有技术分析功能，提供简洁的方法签名，
    让Claude Code可以通过自然语言直接调用。
    """

    def __init__(self, api_key: Optional[str] = None, enable_feishu: bool = True):
        """初始化

        Args:
            api_key: DeepSeek API Key（可选，默认从环境变量 DEEPSEEK_API_KEY 读取）
            enable_feishu: 是否启用飞书同步（默认False）
        """
        self.api_key = api_key or os.environ.get('DEEPSEEK_API_KEY', '')
        if not self.api_key:
            raise ValueError(
                "未设置 API Key。请设置环境变量 DEEPSEEK_API_KEY=sk-xxx\n"
                "获取地址: https://platform.deepseek.com/api_keys"
            )

        self.extractor = FeatureExtractor()
        self.regime_detector = MarketRegimeDetector()
        self.analyzer = TechnicalAnalyzer(api_key=self.api_key)
        self.feedback = FeedbackLoop()
        self.evolution = EvolutionEngine()
        self.rules = RuleIndex()
        self._tracking = None  # 懒加载

        # 飞书集成（懒加载）
        self._feishu = None
        self._feishu_enabled = enable_feishu

    @property
    def feishu(self):
        """懒加载飞书集成"""
        if self._feishu is None:
            from utils.feishu_integration import FeishuIntegration
            self._feishu = FeishuIntegration()
        return self._feishu

    @property
    def tracking(self):
        """懒加载跟踪模块"""
        if self._tracking is None:
            from utils.tracking_module import TrackingModule
            self._tracking = TrackingModule()
        return self._tracking

    def enable_feishu(self):
        """启用飞书同步"""
        self._feishu_enabled = True
        # 触发初始化以验证连接
        _ = self.feishu.folder_token
        print("[OK] 飞书同步已启用")
        print(f"   文件夹: {self.feishu.get_folder_url()}")

    def disable_feishu(self):
        """禁用飞书同步"""
        self._feishu_enabled = False
        print("[OFF] 飞书同步已禁用")

    # ========== 分析功能 ==========

    def analyze(self, symbol: str, days: int = None,
                market: str = 'us',
                save_record: bool = True,
                allow_duplicate: bool = False,
                simulate: bool = False) -> Dict[str, Any]:
        """分析股票技术面（确定性流水线执行）

        底层通过 DeterministicPipeline 执行固定8步流程，
        保证每次分析都按SOP执行，不跳过、不重排。

        Args:
            symbol: 股票代码（如 AAPL, 000001.SZ）
            days: 分析天数（如 30, 60, 100, 200。不填则提示）
            market: 市场（us/cn）
            save_record: 是否保存到反馈系统
            allow_duplicate: 是否允许同一天重复记录
            simulate: 是否生成交易计划并模拟开仓

        Returns:
            完整的分析报告（兼容旧格式）
        """
        if days is None:
            raise ValueError(
                "请指定分析天数，例如：\n"
                "  assistant.analyze('AAPL', days=30)   # 短线\n"
                "  assistant.analyze('AAPL', days=100)  # 中线\n"
                "  assistant.analyze('AAPL', days=200)  # 长线"
            )

        # === 调用确定性流水线 ===
        from utils.deterministic_pipeline import DeterministicPipeline
        dp = DeterministicPipeline(api_key=self.api_key)
        pipeline_result = dp.analyze(
            symbol=symbol,
            days=days,
            market=market,
            simulate=simulate
        )

        # 检查致命错误
        if pipeline_result.has_critical_error():
            errors = "; ".join(pipeline_result.errors)
            raise RuntimeError(f"分析流水线失败: {errors}")

        # === 从PipelineResult组装兼容旧格式的结果 ===
        output = pipeline_result.final_output
        full = output.get('full_analysis', {})
        p1 = full.get('phase1_indicator_inventory', {})
        p2 = full.get('phase2_skill_application', {})
        p3 = full.get('phase3_synergy_conflict', {})
        p4 = full.get('phase4_conclusion', {})

        # 统一市场环境格式（pipeline返回字符串，转为对象兼容旧格式）
        regime_raw = output.get('market_regime', 'unknown')
        if isinstance(regime_raw, str):
            market_regime = {
                'primary': regime_raw,
                'secondary': '',
                'confidence': 0.8,
                'indicators': {}
            }
        else:
            market_regime = regime_raw

        result = {
            'symbol': symbol,
            'market': market,
            'input_type': 'api',
            'indicator_features': output.get('features'),
            'skill_match_result': output.get('skill_match'),
            'full_analysis': full,
            'indicator_summary': output.get('indicator_summary', ''),
            'market_regime': market_regime,
            'trade_plan': output.get('trade_plan'),
            'pipeline_result': pipeline_result.to_dict(),
            # 向后兼容字段
            'trend_analysis': p1.get('trend', {}),
            'pattern_analysis': p1.get('pattern', {}),
            'indicator_analysis': p1.get('momentum', {}),
            'volume_price_analysis': p1.get('volume', {}),
            'behavior_analysis': p3,
            'event_inference': p4,
            'scoring': p4,
        }

        # === 补充高层功能：反馈记录 ===
        if save_record:
            skill_match = output.get('skill_match', {})
            triggered = skill_match.get('triggered', [])
            skills_used = [s.get('skill_id') for s in triggered if s.get('skill_id')]

            record_info = self.feedback.record_analysis(
                result,
                timeframe_days=20,
                skills_used=skills_used,
                allow_duplicate=allow_duplicate
            )
            result['record_id'] = record_info['record_id']
            result['is_update'] = record_info['is_update']
            if record_info['is_update']:
                print(f"[UPDATE] 更新已有分析，记录ID: {record_info['record_id']}（当日重复分析已覆盖）")
            else:
                print(f"[SAVE] 分析已保存，记录ID: {record_info['record_id']}")
            print(f"   20天后可用 feedback.validate('{record_info['record_id']}', return_pct=XX) 验证")

        # === 补充高层功能：分析快照 ===
        if save_record:
            try:
                sid = self.tracking.save_analysis_snapshot(symbol, result)
                print(f"[SNAPSHOT] 分析快照已保存: {sid}")
            except Exception as e:
                print(f"[WARN] 快照保存失败: {e}")

        # === 补充高层功能：飞书同步 ===
        if self._feishu_enabled and save_record:
            try:
                self._sync_to_feishu(symbol, result)
            except Exception as e:
                print(f"[WARN]  飞书同步失败: {e}")

        return result

    def track(self, symbol: str, market: str = 'cn',
              days: int = 100, sync_feishu: bool = True) -> Dict[str, Any]:
        """跟踪已分析股票

        对已生成详细分析报告的股票，获取最新数据并重新计算指标，
        对比上次分析的预测与实际走势，给出跟踪评估和新判断。

        Args:
            symbol: 股票代码
            market: 市场（us/cn）
            days: 数据天数
            sync_feishu: 是否同步到飞书

        Returns:
            跟踪分析结果
        """
        print(f"[TRACK] 开始跟踪 {symbol}...")

        # 执行跟踪分析
        result = self.tracking.track(symbol, market=market, days=days)

        if result['status'] != 'success':
            print(f"[TRACK] 跟踪失败: {result.get('message', 'unknown')}")
            return result

        # 打印核心结论
        tr = result['tracking_result']
        print(f"\n{'='*50}")
        print(f"跟踪结论: {symbol}")
        print(f"{'='*50}")
        print(f"当前价格: {result['current_price']} ({result['price_change_pct']:+.2f}%)")
        print(f"距分析日: {result['days_since']} 天")
        print(f"符合预期: {tr.get('verdict_vs_expected', 'N/A')}")
        print(f"新判断: {tr.get('new_judgment', 'N/A')} -> {tr.get('new_direction', 'N/A')} (置信度{tr.get('new_confidence', 0)}%)")

        issues = tr.get('issues_found', [])
        if issues:
            print(f"\n发现的问题:")
            for issue in issues:
                print(f"  - {issue}")

        # 同步到飞书
        if sync_feishu and self._feishu_enabled:
            try:
                self._sync_tracking_to_feishu(symbol, result)
            except Exception as e:
                print(f"[WARN] 飞书跟踪同步失败: {e}")

        # 模拟持仓跟踪（确定性流水线）
        try:
            from utils.deterministic_pipeline import DeterministicPipeline
            dp = DeterministicPipeline(api_key=self.api_key)
            current_price = result.get('current_price', 0)
            if current_price > 0:
                sim_result = dp.track(symbol, {symbol: current_price})
                if sim_result.warnings:
                    for w in sim_result.warnings:
                        print(f"  [SIM] {w}")
                result['simulation_track'] = sim_result.to_dict()
        except Exception as e:
            print(f"[WARN] 模拟持仓跟踪失败: {e}")

        return result

    def _sync_tracking_to_feishu(self, symbol: str, track_result: Dict):
        """将跟踪结果同步到飞书跟踪文档"""
        from datetime import datetime

        tr = track_result['tracking_result']
        snapshot = track_result['snapshot']

        lines = [
            f"\n## {datetime.now().strftime('%Y-%m-%d')} 跟踪更新（分析后第{track_result['days_since']}天）",
            "",
            f"**当前价格**: {track_result['current_price']} ({track_result['price_change_pct']:+.2f}%)",
            f"**判断 vs 预期**: {tr.get('verdict_vs_expected', 'N/A')}",
            f"**新方向**: {tr.get('new_direction', 'N/A')}（{tr.get('new_judgment', 'N/A')}，置信度{tr.get('new_confidence', 0)}%）",
            "",
            "### 关键价位状态",
        ]

        kl_summary = tr.get('key_level_status_summary', {})
        for k, v in snapshot.get('key_levels', {}).items():
            if isinstance(kl_summary, dict):
                status = kl_summary.get(k, '未提及')
            else:
                status = str(kl_summary) if kl_summary else '未提及'
            lines.append(f"- {k} ({v}): {status}")

        lines.append("")
        lines.append("### 指标变化")
        changes = track_result.get('tracking_result', {}).get('indicator_trend', '')
        lines.append(changes if changes else "详见详细分析")

        issues = tr.get('issues_found', [])
        if issues:
            lines.append("")
            lines.append("### 发现的问题")
            for issue in issues:
                lines.append(f"- {issue}")

        lines.append("")
        lines.append("### 更新后的判断")
        lines.append(tr.get('reasoning', '无详细推理'))

        if tr.get('updated_targets'):
            lines.append(f"\n**更新目标**: {tr['updated_targets']}")
        if tr.get('updated_stop'):
            lines.append(f"**更新止损**: {tr['updated_stop']}")

        watch = tr.get('new_watch_points', [])
        if watch:
            lines.append("")
            lines.append("### 新的观察点")
            for w in watch:
                lines.append(f"- {w}")

        content = '\n'.join(lines)

        # 将跟踪记录插入到分析文档的"后续跟踪"部分（新记录放最前）
        self.feishu.prepend_to_tracking_section(symbol, content)

        doc_token = self.feishu.stock_docs.get(symbol)
        print(f"[OK] 已同步到飞书文档（分析文档 -> 后续跟踪）")
        track_result['feishu_sync'] = {
            'doc_token': doc_token,
            'url': self.feishu.get_stock_doc_url(symbol) if doc_token else None
        }

    def _format_full_analysis(self, full_analysis: Dict[str, Any]) -> str:
        """格式化完整的Phase 1/2/3/4分析结果为飞书Markdown

        新架构核心：将LLM的4阶段结构化输出格式化为可读文本。
        """
        if not full_analysis:
            return "\n\n**全局分析**: 无数据\n"

        # 解析失败的情况
        if full_analysis.get('parse_error') and 'raw_response' in full_analysis:
            return f"\n\n**全局分析（原始输出）**:\n\n```\n{full_analysis['raw_response'][:5000]}\n```\n"

        lines = ["\n\n---\n\n# 技术分析全局分析\n"]

        # ===== Phase 1: 全维度指标盘点 =====
        p1 = full_analysis.get('phase1_indicator_inventory', {})
        if p1:
            lines.append("## Phase 1: 全维度指标盘点\n")
            for dim, data in p1.items():
                lines.append(f"\n### {dim}")
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict):
                            lines.append(f"- **{k}**:")
                            for sk, sv in v.items():
                                lines.append(f"  - {sk}: {sv}")
                        elif isinstance(v, list):
                            lines.append(f"- **{k}**: {', '.join(str(x) for x in v[:5])}")
                        else:
                            lines.append(f"- **{k}**: {v}")
                elif isinstance(data, list):
                    for item in data[:10]:
                        lines.append(f"- {item}")
                else:
                    lines.append(f"- {data}")

        # ===== Phase 2: Skill应用与触发验证 =====
        p2 = full_analysis.get('phase2_skill_application', {})
        if p2:
            lines.append("\n## Phase 2: Skill应用与触发验证\n")

            triggered = p2.get('triggered', [])
            if triggered:
                lines.append("\n### 已触发Skill")
                for skill in triggered[:10]:
                    if isinstance(skill, dict):
                        name = skill.get('name', 'Unnamed')
                        conclusion = skill.get('conclusion', skill.get('assessment', ''))
                        lines.append(f"- **{name}**: {conclusion}")
                        steps = skill.get('steps_reached', skill.get('analysis_steps', []))
                        if steps:
                            lines.append(f"  - 走到步骤: {steps}")
                    else:
                        lines.append(f"- {skill}")

            near = p2.get('near_triggered', [])
            if near:
                lines.append("\n### 准触发Skill")
                for skill in near[:5]:
                    if isinstance(skill, dict):
                        name = skill.get('name', 'Unnamed')
                        gap = skill.get('gap', skill.get('gap_pct', 'N/A'))
                        lines.append(f"- **{name}** (差{gap}): {skill.get('assessment', '')}")
                    else:
                        lines.append(f"- {skill}")

            not_trig = p2.get('not_triggered', [])
            if not_trig:
                lines.append(f"\n### 未触发Skill ({len(not_trig)}条)")
                for skill in not_trig[:5]:
                    if isinstance(skill, dict):
                        lines.append(f"- **{skill.get('name', 'Unnamed')}**: {skill.get('reason', '不适用')}")
                    else:
                        lines.append(f"- {skill}")

        # ===== Phase 3: 跨维度协同与冲突裁决 =====
        p3 = full_analysis.get('phase3_synergy_conflict', {})
        if p3:
            lines.append("\n## Phase 3: 跨维度协同与冲突裁决\n")

            synergies = p3.get('synergies', [])
            if synergies:
                lines.append("\n### 协同信号")
                for syn in synergies[:10]:
                    if isinstance(syn, dict):
                        desc = syn.get('description', syn.get('desc', str(syn)))
                        conf = syn.get('confidence', syn.get('strength', 'N/A'))
                        lines.append(f"- {desc} (置信度: {conf})")
                    else:
                        lines.append(f"- {syn}")

            conflicts = p3.get('conflicts', [])
            if conflicts:
                lines.append("\n### 冲突裁决")
                for conf in conflicts[:10]:
                    if isinstance(conf, dict):
                        desc = conf.get('description', conf.get('desc', str(conf)))
                        resolution = conf.get('resolution', conf.get('verdict', ''))
                        reason = conf.get('reason', conf.get('rationale', ''))
                        lines.append(f"- **冲突**: {desc}")
                        lines.append(f"  - **裁决**: {resolution}")
                        if reason:
                            lines.append(f"  - **理由**: {reason}")
                    else:
                        lines.append(f"- {conf}")

            dominant = p3.get('dominant_force', '')
            if dominant:
                lines.append(f"\n### 主导力量判断\n{dominant}")

        # ===== Phase 4: 综合结论与风险 =====
        p4 = full_analysis.get('phase4_conclusion', {})
        if p4:
            lines.append("\n## Phase 4: 综合结论与风险\n")

            direction = p4.get('direction', 'N/A')
            confidence = p4.get('confidence', 'N/A')
            lines.append(f"\n### 最终判断")
            lines.append(f"- **方向**: {direction}")
            lines.append(f"- **置信度**: {confidence}")

            evidence = p4.get('key_evidence', [])
            if evidence:
                lines.append("\n### 关键依据")
                for ev in evidence[:10]:
                    lines.append(f"- {ev}")

            target = p4.get('target_price')
            if target is not None:
                lines.append(f"\n- **目标价**: {target}")

            stop = p4.get('stop_loss')
            if stop is not None:
                lines.append(f"- **止损位**: {stop}")

            risks = p4.get('risks', [])
            if risks:
                lines.append("\n### 风险因素")
                for r in risks[:10]:
                    lines.append(f"- {r}")

            watch = p4.get('watch_points', [])
            if watch:
                lines.append("\n### 观察点")
                for w in watch[:10]:
                    lines.append(f"- {w}")

            invalid = p4.get('invalidation_conditions', [])
            if invalid:
                lines.append("\n### 判断失效条件")
                for iv in invalid[:10]:
                    lines.append(f"- {iv}")

        return '\n'.join(lines)

    def _format_llm_analysis(self, analysis: Dict[str, Any], title: str) -> str:
        """格式化LLM分析结果为可读文本（向后兼容旧架构）"""
        if not analysis:
            return f"\n\n**{title}**: 无数据\n"

        # 情况2：解析失败，有原始文本
        if analysis.get('parse_error') and 'raw_response' in analysis:
            raw = analysis['raw_response']
            return f"\n\n**{title}**:\n\n{raw}\n"

        # 情况1：正常JSON，提取各Phase内容
        lines = [f"\n\n**{title}**:\n"]

        for phase_key in ['Phase 1', 'Phase 2', 'Phase 3', 'Phase 4',
                           'phase1', 'phase2', 'phase3', 'phase4',
                           'phase_1', 'phase_2', 'phase_3', 'phase_4']:
            if phase_key in analysis:
                phase_data = analysis[phase_key]
                if isinstance(phase_data, dict):
                    lines.append(f"\n***{phase_key}***:\n")
                    for k, v in phase_data.items():
                        if isinstance(v, dict):
                            lines.append(f"- **{k}**:")
                            for sk, sv in v.items():
                                lines.append(f"  - {sk}: {sv}")
                        else:
                            lines.append(f"- **{k}**: {v}")
                elif isinstance(phase_data, str):
                    lines.append(f"\n***{phase_key}***: {phase_data}\n")

        # 如果没有Phase结构，显示所有顶层字段
        if len(lines) == 1:
            for k, v in analysis.items():
                if k in ('symbol', 'market', 'input_type', 'parse_error', 'raw_response'):
                    continue
                if isinstance(v, dict):
                    lines.append(f"\n- **{k}**:")
                    for sk, sv in v.items():
                        lines.append(f"  - {sk}: {sv}")
                else:
                    lines.append(f"- **{k}**: {v}")

        return '\n'.join(lines)

    def _sync_to_feishu(self, symbol: str, result: Dict[str, Any]):
        """将分析结果同步到飞书文档（新架构：展示完整Phase 1/2/3/4分析链）"""
        from datetime import datetime

        regime = result.get('market_regime', {})
        record_id = result.get('record_id', 'N/A')
        full_analysis = result.get('full_analysis', {})
        skill_match = result.get('skill_match_result', {})
        p4 = full_analysis.get('phase4_conclusion', {}) if isinstance(full_analysis, dict) else {}

        # 从Phase 4提取最终判断
        verdict = p4.get('direction', 'N/A') if isinstance(p4, dict) else 'N/A'
        confidence = p4.get('confidence', 'N/A') if isinstance(p4, dict) else 'N/A'

        # 提取核心理由
        core_reason = ''
        evidence = p4.get('key_evidence', []) if isinstance(p4, dict) else []
        if evidence:
            core_reason = evidence[0] if isinstance(evidence[0], str) else str(evidence[0])
        if not core_reason:
            core_reason = '详见分析文档'

        is_update = result.get('is_update', False)
        update_badge = '[UPDATE] [覆盖]' if is_update else '[NEW] [新分析]'
        update_count = result.get('updated_count', 0)
        update_note = f'（第{update_count + 1}次更新）' if is_update else ''

        content = f"""\n\n## {update_badge} {record_id} | {datetime.now().strftime('%Y-%m-%d')} {update_note} | {verdict} | {core_reason[:50]}

**市场环境**: {regime.get('primary', 'unknown')} (置信度: {regime.get('confidence', 0):.0%})
**最终判断**: {verdict} (置信度: {confidence})

### 指标数据
{result.get('indicator_summary', '无数据')}
"""

        # 追加SkillMatcher系统匹配结果
        if skill_match and isinstance(skill_match, dict):
            summary = skill_match.get('summary', {})
            content += f"""\n### SkillMatcher系统匹配结果
- 总Skill数: {summary.get('total_skills', 0)}
- 已触发: {summary.get('triggered_count', 0)}
- 准触发: {summary.get('near_triggered_count', 0)}
- 未触发: {summary.get('not_triggered_count', 0)}
"""
            # 列出触发的Skill
            triggered = skill_match.get('triggered', [])
            if triggered:
                content += "\n**已触发Skill**:"
                for s in triggered[:10]:
                    if isinstance(s, dict):
                        name = s.get('name', 'Unnamed')
                        sig_dir = s.get('signal_direction', 'neutral')
                        sig_str = s.get('signal_strength', 0)
                        content += f"\n- {name} ({sig_dir}, 强度{sig_str})"
                    else:
                        content += f"\n- {s}"

        # 追加完整4阶段分析（新架构核心）
        content += self._format_full_analysis(full_analysis)

        # 向后兼容：也追加旧格式的分析（如果full_analysis解析失败）
        if full_analysis.get('parse_error'):
            content += self._format_llm_analysis(result.get('trend_analysis', {}), "趋势分析")
            content += self._format_llm_analysis(result.get('pattern_analysis', {}), "形态识别")
            content += self._format_llm_analysis(result.get('indicator_analysis', {}), "指标分析")
            content += self._format_llm_analysis(result.get('volume_price_analysis', {}), "量价分析")
            content += self._format_llm_analysis(result.get('behavior_analysis', {}), "资金行为")
            content += self._format_llm_analysis(result.get('event_inference', {}), "事件推断")
            content += self._format_llm_analysis(result.get('scoring', {}), "综合评分")

        content += f"""\n\n---\n**记录ID**: `{record_id}` | **验证状态**: 待验证\n---\n"""

        # 在末尾添加"后续跟踪"占位符（用于后续每日跟踪）
        content += "\n\n---\n\n# 后续跟踪\n\n"

        # 追加到股票文档
        doc_token = self.feishu.stock_docs.get(symbol)
        if doc_token:
            self.feishu.append_to_stock_doc(symbol, content)
            print(f"[DOC] 已同步到飞书文档: {self.feishu.get_stock_doc_url(symbol)}")
        else:
            doc_token = self.feishu.create_stock_doc(symbol, content)
            print(f"[DOC] 已在飞书创建文档: {self.feishu.get_stock_doc_url(symbol)}")

        # 保存完整文档内容到本地缓存（用于后续跟踪时重写）
        full_doc = self.feishu.load_doc_cache(symbol)
        if full_doc:
            full_doc += content
        else:
            full_doc = content
        self.feishu.save_doc_cache(symbol, full_doc)

        # 添加到汇总记录（标题式格式）
        update_mark = '[UPDATE]' if is_update else '[NEW]'
        record_summary = {
            'record_id': record_id,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'symbol': symbol,
            'verdict': f"{update_mark} {verdict}",
            'core_reason': core_reason[:100],
            'validation_status': '待验证',
            'actual_return': '-',
            'outcome': '-',
            'market_regime': regime.get('primary', 'unknown'),
        }
        self.feishu.add_record_to_summary(record_summary)
        print(f"[DATA] 已添加到汇总记录: {self.feishu.get_records_doc_url()}")

    def quick_indicators(self, symbol: str, days: int = 100) -> str:
        """快速获取指标摘要（纯文本，适合直接展示）"""
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=f"{days}d")
        features = self.extractor.extract_all(df)
        return self.extractor.format_for_llm(features)

    def analyze_from_file(self, file_path: str,
                          symbol: str = 'UNKNOWN',
                          market: str = 'us',
                          save_record: bool = True,
                          allow_duplicate: bool = False) -> Dict[str, Any]:
        """从CSV/Excel文件分析（用户上传的数据）

        Args:
            file_path: 数据文件路径（.csv 或 .xlsx/.xls）
            symbol: 股票代码（用于记录）
            market: 市场
            save_record: 是否保存到反馈系统

        期望的CSV列名:
            date, open, high, low, close, volume
            （或中文：日期, 开盘, 最高, 最低, 收盘, 成交量）
        """
        print(f"[FILE] 正在读取数据文件: {file_path}")

        # 读取文件
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif file_path.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file_path)
        else:
            raise ValueError("仅支持 .csv 或 .xlsx/.xls 格式")

        # 标准化列名
        column_mapping = {
            '日期': 'date', 'Date': 'date', 'date': 'date',
            '开盘': 'open', 'Open': 'open', 'open': 'open',
            '收盘': 'close', 'Close': 'close', 'close': 'close',
            '最高': 'high', 'High': 'high', 'high': 'high',
            '最低': 'low', 'Low': 'low', 'low': 'low',
            '成交量': 'volume', 'Volume': 'volume', 'volume': 'volume',
        }
        df = df.rename(columns=column_mapping)

        # 确保数值类型
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # 尝试解析日期
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.dropna(subset=['date'])

        print(f"[OK] 读取到 {len(df)} 条数据")
        if len(df) < 60:
            print(f"[WARN]  仅 {len(df)} 条数据，建议至少60条")

        # 计算指标
        print("正在计算技术指标...")
        features = self.extractor.extract_all(df)

        # 检测市场状态
        regime = self.regime_detector.detect(df)
        print(f"[TREND] 市场状态: {self.regime_detector.describe(regime)}")

        # 将日期转换为字符串（避免JSON序列化问题）
        df_str = df.copy()
        if 'date' in df_str.columns:
            df_str['date'] = df_str['date'].astype(str)

        # LLM分析
        print("[LLM] 正在调用大模型分析...")
        data = {
            'symbol': symbol,
            'market': market,
            'df': df,
            'data': df_str.to_dict('records'),
            'input_type': 'file',
            'market_regime': {
                'primary': regime.primary,
                'secondary': regime.secondary,
                'confidence': regime.confidence,
                'indicators': regime.indicators
            }
        }

        result = self.analyzer.run_full_analysis(data)
        result['market_regime'] = {
            'primary': regime.primary,
            'secondary': regime.secondary,
            'confidence': regime.confidence,
            'indicators': regime.indicators
        }
        result['indicator_summary'] = self.extractor.format_for_llm(features)

        if save_record:
            record_info = self.feedback.record_analysis(
                result,
                timeframe_days=20,
                skills_used=[],
                allow_duplicate=allow_duplicate
            )
            result['record_id'] = record_info['record_id']
            result['is_update'] = record_info['is_update']
            if record_info['is_update']:
                print(f"[UPDATE] 更新已有分析，记录ID: {record_info['record_id']}（当日重复分析已覆盖）")
            else:
                print(f"[SAVE] 分析已保存，记录ID: {record_info['record_id']}")

        # 同步到飞书（如果启用）
        if self._feishu_enabled and save_record:
            try:
                self._sync_to_feishu(symbol, result)
            except Exception as e:
                print(f"[WARN]  飞书同步失败: {e}")

        return result

    def analyze_screenshot(self, image_path: str,
                           symbol: str = 'UNKNOWN',
                           save_record: bool = True) -> Dict[str, Any]:
        """分析K线截图（用户上传的图片）

        Args:
            image_path: 截图文件路径（.png/.jpg/.jpeg）
            symbol: 股票代码（用于记录）
            save_record: 是否保存到反馈系统

        说明: 截图分析依赖LLM的视觉能力，指标值由LLM从图中估算，
              精度不如精确计算。建议作为辅助参考。
        """
        print(f"[IMG] 正在分析截图: {image_path}")

        # 使用LLM客户端的视觉分析
        raw = self.analyzer.client.analyze_screenshot(image_path)

        result = {
            'symbol': symbol,
            'input_type': 'screenshot',
            'screenshot_analysis': raw,
            'market_regime': {'primary': 'unknown', 'confidence': 0},
            'indicator_summary': '截图分析：指标值由LLM从图中估算',
        }

        if save_record:
            record_id = self.feedback.record_analysis(
                result,
                timeframe_days=20,
                skills_used=[]
            )
            result['record_id'] = record_id
            print(f"[SAVE] 分析已保存，记录ID: {record_id}")

        return result

    # ========== Skill管理 ==========

    # ========== Skill上传（交互式分段提取）==========

    def upload_skill_book(self, file_path: str,
                          auto_extract: bool = False) -> Dict[str, Any]:
        """从书籍PDF/Word上传Skill（Claude Code 语义分段 + 交互式提取）

        新流程：
        1. Claude Code 本地解析 + 清洗（零 API 消耗）
        2. 返回全文，Claude Code 理解内容后给出分段建议
        3. 用户确认/调整分段
        4. 用户逐段交互：指导提取 → DeepSeek 提取 → 本地修改/返工 → 保存

        Args:
            file_path: 文件路径
            auto_extract: 是否跳过交互，一次性自动提取整本（旧模式）

        Returns:
            清洗后的全文（auto_extract=False）或提取结果（auto_extract=True）
        """
        print(f"[BOOK] 正在解析书籍: {file_path}")

        # Step 1: 解析文本（本地）
        file_type = 'pdf' if file_path.endswith('.pdf') else 'word'
        if file_type == 'pdf':
            # 检测是否为扫描版 PDF
            if self.evolution.is_scanned_pdf(file_path):
                print("[IMG] 检测到扫描版 PDF，需要使用 OCR 识别")
                print("[TIP] 提示：可以指定页码范围以加快速度")
                print("   例如：ocr_pages=(50, 150) 只识别第50-150页")
                # 默认只 OCR 前 100 页（避免太慢），用户可以覆盖
                raw_text = self.evolution.parse_pdf_ocr(file_path, page_start=1, page_end=100)
            else:
                raw_text = self.evolution.parse_pdf(file_path)
        else:
            raw_text = self.evolution.parse_word(file_path)

        # Step 2: 清洗文本（去页眉页脚/页码，零 API）
        cleaned_text = self.evolution.clean_text(raw_text)
        text_len = len(cleaned_text)

        print(f"[OK] 读取完成，清洗后共 {text_len} 字符")
        print(f"   原始: {len(raw_text)} 字符 → 清洗后: {text_len} 字符")

        # 自动模式：一次性提取整本（旧模式，用于简单场景）
        if auto_extract:
            result = self.evolution.update_skill_from_book(file_path, file_type)
            return result

        # 交互模式：返回全文，由 Claude Code 语义分段 + 用户确认
        self._pending_book_text = cleaned_text
        self._pending_book_file = file_path
        self._pending_book_structure = None  # 等待用户通过 set_book_segments 设置

        # 展示前1000字预览
        preview = cleaned_text[:1000].replace('\n', ' ')
        print(f"\n[DOC] 全文预览（前1000字）：")
        print(f"{preview}...")

        print(f"\n[TIP] 接下来请告诉我你想如何分段？")
        print(f"   例如：'按章节分'、'合并前3章'、'跳过案例部分'")
        print(f"   或直接用 assistant.set_book_segments([...]) 设置分段")

        return {
            'status': 'loaded',
            'file_path': file_path,
            'total_chars': text_len,
            'cleaned_text': cleaned_text,
            'preview': preview + '...',
            'hint': 'Claude Code 理解内容结构后，与用户确认分段，然后调用 set_book_segments() 设置分段配置'
        }

    def get_book_segment_text(self, segment_id: int) -> str:
        """获取指定段的完整原文（用于展示给用户）"""
        if not hasattr(self, '_pending_book_text'):
            return "请先调用 upload_skill_book(file_path) 加载书籍"

        text = self._pending_book_text
        structure = self._pending_book_structure

        return self.evolution.get_segment_text(text, segment_id, structure)

    def extract_book_segment(self, segment_id: int,
                              user_instruction: str = "") -> Dict[str, Any]:
        """从指定段提取 Skill（调用 DeepSeek，一次一段）

        Args:
            segment_id: 段编号（从1开始）
            user_instruction: 你的提取指导（如"重点提取ADX判断法"、"threshold用原文值"）

        Returns:
            提取的 Skill 列表（JSON 格式）
        """
        if not hasattr(self, '_pending_book_text'):
            return {"error": "请先调用 upload_skill_book(file_path) 加载书籍"}

        segment_text = self.get_book_segment_text(segment_id)
        if not segment_text:
            return {"error": f"段{segment_id} 不存在或为空"}

        print(f"[LLM] 正在提取段{segment_id}...")
        if user_instruction:
            print(f"   你的指导: {user_instruction[:80]}")

        # 调用 DeepSeek（精简 system prompt，只传一段原文）
        result = self.analyzer.client.extract_skills_from_segment(
            segment_text, user_instruction
        )

        if result.get('parse_error'):
            print("[WARN]  JSON解析失败，但原始内容已保留")
            return result

        rules = result.get('rules', [])
        summary = result.get('summary', '')
        print(f"[OK] 提取完成，共 {len(rules)} 条Skill")
        print(f"   概括: {summary}")
        for r in rules:
            print(f"   - [{r.get('category', '?')}] {r.get('name', 'Unnamed')}")

        # 缓存当前段结果，供用户本地修改
        self._last_extracted_skills = rules
        self._last_extracted_segment_id = segment_id

        return result

    def modify_extracted_skill(self, skill_index: int,
                                field: str,
                                new_value: Any) -> bool:
        """本地修改已提取的 Skill（零 API 消耗）

        Args:
            skill_index: Skill 在列表中的索引（从0开始）
            field: 要修改的字段（如 'reference_data', 'analysis_steps', 'core_idea'）
            new_value: 新值

        Returns:
            是否修改成功
        """
        if not hasattr(self, '_last_extracted_skills'):
            print("[WARN]  没有缓存的提取结果，请先调用 extract_book_segment()")
            return False

        skills = self._last_extracted_skills
        if skill_index < 0 or skill_index >= len(skills):
            print(f"[WARN]  索引 {skill_index} 超出范围（共 {len(skills)} 条）")
            return False

        skill = skills[skill_index]

        # 支持嵌套字段，如 "reference_data.关键阈值"
        if '.' in field:
            parts = field.split('.')
            current = skill
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = new_value
        else:
            skill[field] = new_value

        print(f"[OK] 已修改 Skill[{skill_index}].{field}")
        return True

    def remove_extracted_skill(self, skill_index: int) -> bool:
        """本地删除已提取的 Skill（零 API 消耗）"""
        if not hasattr(self, '_last_extracted_skills'):
            print("[WARN]  没有缓存的提取结果")
            return False

        skills = self._last_extracted_skills
        if skill_index < 0 or skill_index >= len(skills):
            print(f"[WARN]  索引 {skill_index} 超出范围")
            return False

        removed = skills.pop(skill_index)
        print(f"[OK] 已删除 Skill[{skill_index}]: {removed.get('name', 'Unnamed')}")
        return True

    def save_book_skills(self, skills: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """保存已确认的 Skill 到 pending 队列

        Args:
            skills: 要保存的 Skill 列表（默认使用最后一次提取的结果）

        Returns:
            保存结果，包含 rule_id 列表
        """
        if skills is None:
            if not hasattr(self, '_last_extracted_skills'):
                return {"error": "没有可保存的 Skill"}
            skills = self._last_extracted_skills

        from utils.rule_index import RuleIndex
        rule_index = RuleIndex()

        saved = []
        for skill in skills:
            # 转换为标准格式
            rule_data = self.evolution._convert_to_methodology_format(skill)
            rule_id = rule_index.add_rule(rule_data, auto_activate=False)
            saved.append({
                'rule_id': rule_id,
                'name': rule_data.get('name', 'Unnamed'),
                'status': 'pending'
            })

        print(f"[SAVE] 已保存 {len(saved)} 条 Skill 到 pending 队列")
        for s in saved:
            print(f"   - [{s['rule_id']}] {s['name']}")
        print("   使用 assistant.activate_skill(id) 激活")

        return {
            'status': 'saved',
            'count': len(saved),
            'skills': saved
        }

    def upload_skill_text(self, text: str,
                          name: Optional[str] = None) -> Dict[str, Any]:
        """从自然语言文本上传Skill（单条，无需分段）

        直接调用 DeepSeek 提取，适合用户自己写的方法论描述。
        """
        print("[EDIT] 正在解析Skill文本...")

        result = self.evolution.update_skill_from_natural_language(text)

        if result.get('status') == 'pending_review':
            print(f"⏳ 解析完成，规则ID: {result.get('rule_id')}")
            print("   使用 assistant.activate_skill(id) 激活")

        return result

    def set_book_segments(self, segments_config: List[Dict[str, Any]]) -> Dict[str, Any]:
        """设置分段配置（Claude Code 语义分段 + 用户确认后调用）

        Args:
            segments_config: 分段配置列表，每项包含：
                {
                    'segment_id': int,        # 段编号
                    'title': str,             # 段标题（用户命名）
                    'start_marker': str,      # 起始标记（原文中的一行）
                    'end_marker': str,        # 结束标记（可选，下一段的 start_marker 会自动作为结束）
                    'note': str               # 备注（可选）
                }

        Returns:
            分段地图
        """
        if not hasattr(self, '_pending_book_text'):
            return {"error": "请先调用 upload_skill_book() 或 upload_skill_from_feishu() 加载文档"}

        text = self._pending_book_text
        structure = self.evolution.create_segments(text, segments_config)
        self._pending_book_structure = structure

        print(f"[LIST] 分段已设置（共 {len(structure['segments'])} 段）:")
        for seg in structure['segments']:
            print(f"\n  段{seg['segment_id']}: {seg['chapter_title']}")
            print(f"    长度: {seg['char_count']} 字符")
            print(f"    概括: {seg['summary'][:80]}...")
            if seg.get('note'):
                print(f"    备注: {seg['note']}")

        print("\n[TIP] 现在可以开始逐段提取：")
        print(f"  assistant.extract_book_segment(1, '你的提取指导')")
        print(f"  assistant.get_book_segment_text(1)")

        return structure

    def upload_skill_from_feishu(self, doc_url_or_token: str,
                                  auto_extract: bool = False) -> Dict[str, Any]:
        """从飞书文档导入Skill（Claude Code 语义分段 + 交互式提取）

        流程同 upload_skill_book：清洗全文 → Claude Code 语义分段 → 用户确认 → 逐段提取
        """
        print(f"[BOOK] 正在从飞书文档导入 Skill...")
        print(f"   文档: {doc_url_or_token}")

        from utils.feishu_integration import FeishuIntegration
        feishu = FeishuIntegration()

        # 读取飞书文档内容
        raw_content = feishu.read_doc_content(doc_url_or_token)
        cleaned_content = self.evolution.clean_text(raw_content)
        text_len = len(cleaned_content)

        print(f"[OK] 读取完成，清洗后共 {text_len} 字符")
        print(f"   原始: {len(raw_content)} 字符 → 清洗后: {text_len} 字符")

        # 自动模式
        if auto_extract:
            from utils.llm_client import DeepSeekClient
            client = DeepSeekClient()
            result = client.extract_knowledge_from_text(cleaned_content, book_title=doc_url_or_token)
            # ... 保存规则
            return result

        # 交互模式
        self._pending_book_text = cleaned_content
        self._pending_book_file = doc_url_or_token
        self._pending_book_structure = None

        preview = cleaned_content[:1000].replace('\n', ' ')
        print(f"\n[DOC] 全文预览（前1000字）：")
        print(f"{preview}...")

        print(f"\n[TIP] 接下来请告诉我你想如何分段？")
        print(f"   然后用 assistant.set_book_segments([...]) 设置分段")

        return {
            'status': 'loaded',
            'source': doc_url_or_token,
            'total_chars': text_len,
            'cleaned_text': cleaned_content,
            'preview': preview + '...',
            'hint': 'Claude Code 理解内容结构后，与用户确认分段，然后调用 set_book_segments()'
        }

    def list_skills(self, status: str = 'all',
                    category: Optional[str] = None) -> List[Dict]:
        """列出所有Skill

        Args:
            status: 状态筛选（all/active/pending/deprecated）
            category: 分类筛选

        Returns:
            Skill列表
        """
        if status == 'all':
            status = None

        rules = self.rules.get_rules(status=status or 'active')

        if category:
            rules = [r for r in rules if r.get('category') == category]

        return rules

    def activate_skill(self, rule_id: str) -> Dict[str, Any]:
        """激活待审核的Skill"""
        return self.evolution.activate_rule(rule_id)

    def deactivate_skill(self, rule_id: str) -> bool:
        """停用Skill"""
        return self.rules.deprecate_rule(rule_id, reason='user_deactivate')

    def skill_stats(self, rule_id: str) -> Optional[Dict]:
        """查看Skill统计"""
        for r in self.rules._rules:
            if r['rule_id'] == rule_id:
                return r
        return None

    def export_skills_html(self, output_path: str = 'skills_dashboard.html'):
        """导出所有Skill为HTML页面"""
        html = self._generate_skills_html(self.rules._rules)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"[DOC] 已导出到 {output_path}")

    def _generate_skills_html(self, rules: List[Dict]) -> str:
        """生成Skill仪表板HTML"""
        stats = {
            'total': len(rules),
            'active': len([r for r in rules if r.get('status') == 'active']),
            'pending': len([r for r in rules if r.get('status') == 'pending']),
            'deprecated': len([r for r in rules if r.get('status') == 'deprecated']),
        }

        cards = []
        for rule in sorted(rules, key=lambda r: r.get('performance', {}).get('win_rate') or 0, reverse=True):
            perf = rule.get('performance', {})
            win_rate = perf.get('win_rate')
            used = perf.get('used_count', 0)
            wins = perf.get('wins', 0)

            # 胜率颜色
            if win_rate is None:
                rate_color, rate_text = '#9ca3af', '未验证'
            elif win_rate >= 0.6:
                rate_color, rate_text = '#10b981', f'{win_rate*100:.0f}%'
            elif win_rate >= 0.4:
                rate_color, rate_text = '#f59e0b', f'{win_rate*100:.0f}%'
            else:
                rate_color, rate_text = '#ef4444', f'{win_rate*100:.0f}%'

            # 状态标签
            status = rule.get('status', 'unknown')
            status_colors = {'active': '#10b981', 'pending': '#f59e0b', 'deprecated': '#6b7280'}
            status_color = status_colors.get(status, '#6b7280')

            # 分析步骤
            steps = rule.get('analysis_steps', [])
            steps_html = ''.join(f'<li>{s}</li>' for s in steps[:5])

            # 参考数据
            ref_data = rule.get('reference_data', {})
            refs_html = ''.join(f'<span class="tag">{k}: {v}</span>' for k, v in list(ref_data.items())[:4])

            # 常见误区
            pitfalls = rule.get('common_pitfalls', [])
            pits_html = ''.join(f'<li>{p}</li>' for p in pitfalls[:3])

            # 分环境胜率
            by_regime = perf.get('by_regime', {})
            regime_html = ''
            if by_regime:
                regime_items = []
                for reg, data in by_regime.items():
                    r_used = data.get('used', 0)
                    r_wins = data.get('wins', 0)
                    if r_used > 0:
                        r_rate = r_wins / r_used
                        r_color = '#10b981' if r_rate >= 0.6 else '#f59e0b' if r_rate >= 0.4 else '#ef4444'
                        regime_items.append(f'<span style="color:{r_color}">{reg}: {r_rate*100:.0f}% ({r_wins}/{r_used})</span>')
                regime_html = '<div class="regimes">' + ' | '.join(regime_items) + '</div>'

            # 进度条宽度
            bar_width = (win_rate or 0.5) * 100

            cards.append(f'''
            <div class="card" data-status="{status}" data-category="{rule.get('category', 'general')}">
                <div class="card-header">
                    <div>
                        <span class="status-badge" style="background:{status_color}">{status}</span>
                        <span class="rule-name">{rule.get('name', 'Unnamed')}</span>
                        <span class="rule-id">[{rule.get('rule_id', '???')}]</span>
                    </div>
                    <div class="win-rate" style="color:{rate_color}">{rate_text}</div>
                </div>
                <div class="win-bar"><div class="win-bar-fill" style="width:{bar_width}%;background:{rate_color}"></div></div>
                <div class="card-body">
                    <div class="section"><strong>核心思想：</strong>{rule.get('core_idea', rule.get('definition', ''))}</div>
                    {'<div class="section"><strong>分析步骤：</strong><ol>' + steps_html + '</ol></div>' if steps else ''}
                    {'<div class="section"><strong>参考数据：</strong>' + refs_html + '</div>' if refs_html else ''}
                    {'<div class="section pitfalls"><strong>常见误区：</strong><ul>' + pits_html + '</ul></div>' if pits_html else ''}
                    {regime_html}
                    <div class="meta">使用次数: {used} | 胜场: {wins} | 权重: {rule.get('weight', 1.0)}</div>
                </div>
            </div>
            ''')

        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Skill 知识库 - {stats['total']} 条规则</title>
<style>
body {{ font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; max-width:1200px; margin:0 auto; padding:20px; background:#f3f4f6; }}
.header {{ background:linear-gradient(135deg,#1e3a5f,#2d5a87); color:white; padding:30px; border-radius:12px; margin-bottom:20px; }}
.stats {{ display:flex; gap:20px; margin-top:15px; }}
.stat {{ background:rgba(255,255,255,0.15); padding:12px 20px; border-radius:8px; }}
.stat-value {{ font-size:24px; font-weight:bold; }}
.filters {{ background:white; padding:15px; border-radius:8px; margin-bottom:20px; display:flex; gap:10px; flex-wrap:wrap; }}
.filters input, .filters select {{ padding:8px 12px; border:1px solid #e5e7eb; border-radius:6px; font-size:14px; }}
.filters input {{ flex:1; min-width:200px; }}
.card {{ background:white; border-radius:12px; padding:20px; margin-bottom:15px; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
.card-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }}
.rule-name {{ font-size:18px; font-weight:600; margin-left:8px; }}
.rule-id {{ color:#9ca3af; font-size:12px; }}
.status-badge {{ padding:2px 8px; border-radius:4px; color:white; font-size:12px; }}
.win-rate {{ font-size:20px; font-weight:bold; }}
.win-bar {{ height:6px; background:#e5e7eb; border-radius:3px; margin-bottom:12px; overflow:hidden; }}
.win-bar-fill {{ height:100%; border-radius:3px; transition:width 0.3s; }}
.card-body {{ color:#4b5563; line-height:1.6; }}
.section {{ margin:10px 0; }}
.section ol, .section ul {{ margin:5px 0; padding-left:20px; }}
.tag {{ display:inline-block; background:#d1fae5; color:#065f46; padding:3px 8px; border-radius:4px; font-size:12px; margin:2px; }}
.pitfalls ul {{ color:#991b1b; }}
.pitfalls ul li::marker {{ color:#ef4444; }}
.regimes {{ margin-top:8px; font-size:13px; color:#6b7280; }}
.meta {{ margin-top:10px; font-size:12px; color:#9ca3af; }}
</style>
</head>
<body>
<div class="header">
    <h1>Skill 知识库</h1>
    <div class="stats">
        <div class="stat"><div class="stat-value">{stats['total']}</div><div>总计</div></div>
        <div class="stat"><div class="stat-value">{stats['active']}</div><div>已激活</div></div>
        <div class="stat"><div class="stat-value">{stats['pending']}</div><div>待审核</div></div>
        <div class="stat"><div class="stat-value">{stats['deprecated']}</div><div>已停用</div></div>
    </div>
</div>
<div class="filters">
    <input type="text" id="search" placeholder="搜索 Skill 名称或内容..." onkeyup="filter()">
    <select id="statusFilter" onchange="filter()"><option value="">全部状态</option><option value="active">已激活</option><option value="pending">待审核</option><option value="deprecated">已停用</option></select>
</div>
<div id="cards">
    {''.join(cards) if cards else '<div style="text-align:center;color:#9ca3af;padding:60px;">暂无 Skill 记录</div>'}
</div>
<script>
function filter() {{
    const q = document.getElementById('search').value.toLowerCase();
    const s = document.getElementById('statusFilter').value;
    document.querySelectorAll('.card').forEach(c => {{
        const text = c.innerText.toLowerCase();
        const status = c.dataset.status;
        c.style.display = (!s || status === s) && text.includes(q) ? 'block' : 'none';
    }});
}}
</script>
</body>
</html>'''

    # ========== 反馈闭环 ==========

    def validate(self, record_id: str,
                 actual_return_pct: float,
                 target_hit: bool = False,
                 stop_hit: bool = False,
                 direction_correct: bool = False,
                 max_drawdown_pct: float = 0.0,
                 days: int = 20) -> Dict[str, Any]:
        """验证分析记录

        Args:
            record_id: 记录ID
            actual_return_pct: 实际收益率(%)
            target_hit: 是否达到目标价
            stop_hit: 是否触发止损
            direction_correct: 方向是否正确
            days: 持有天数

        Returns:
            验证结果，包含Skill归因
        """
        # 尝试检测市场环境
        market_regime = 'unknown'
        try:
            record = None
            for r in self.feedback.records:
                if r['record_id'] == record_id:
                    record = r
                    break
            if record:
                symbol = record.get('symbol', '')
                if symbol and symbol != 'UNKNOWN':
                    ticker = yf.Ticker(symbol)
                    df = ticker.history(period="60d")
                    if len(df) >= 60:
                        regime = self.regime_detector.detect(df)
                        market_regime = regime.primary
        except Exception:
            pass

        result = self.feedback.validate_record(
            record_id=record_id,
            actual_return_pct=actual_return_pct,
            target_reached=target_hit,
            stop_hit=stop_hit,
            direction_correct=direction_correct,
            max_drawdown_pct=max_drawdown_pct,
            market_regime=market_regime
        )

        print(f"[OK] 验证完成!")
        print(f"   实际收益: {actual_return_pct}%")
        print(f"   结果: {result.get('outcome')}")
        print(f"   市场环境: {market_regime}")

        # 显示Skill归因
        validations = result.get('skill_validations', [])
        if validations:
            print("\n[DATA] Skill归因:")
            for v in validations:
                status = "[OK]" if v['correct'] else "[FAIL]"
                print(f"   {status} {v['skill_name']}: {v['conclusion']}")

        # 同步到飞书（如果启用）
        if self._feishu_enabled:
            try:
                self.feishu.update_record_validation(record_id, {
                    'actual_return_pct': actual_return_pct,
                    'outcome': result.get('outcome'),
                    'market_regime': market_regime,
                })
                print(f"[DOC] 已同步验证结果到飞书")
            except Exception as e:
                print(f"[WARN]  飞书同步失败: {e}")

        return result

    def validate_trade(self, trade_id: str,
                       price_data: Any = None) -> Dict[str, Any]:
        """验证模拟交易（自动归因 + 教训生成 + Skill权重更新）

        区别于 validate()（验证分析记录），此方法验证模拟交易，
        使用 AutoValidator 自动下载价格数据、计算结果、Skill归因。

        Args:
            trade_id: 交易ID（如 woge_20250607_1234）
            price_data: 预加载的价格数据（可选，不传则自动下载）

        Returns:
            验证结果，包含 outcome/attribution/lessons
        """
        from utils.deterministic_pipeline import DeterministicPipeline
        dp = DeterministicPipeline(api_key=self.api_key)
        pipeline_result = dp.validate(trade_id, price_data=price_data)

        if pipeline_result.has_critical_error():
            errors = "; ".join(pipeline_result.errors)
            raise RuntimeError(f"验证失败: {errors}")

        result = pipeline_result.final_output
        if not result:
            return {'error': '验证无结果'}

        # 打印验证报告
        outcome = result.get('outcome', {})
        attribution = result.get('attribution', {})
        lessons = result.get('lessons', [])

        print(f"\n{'='*60}")
        print(f"交易验证报告: {result.get('symbol', 'N/A')}")
        print(f"{'='*60}")
        print(f"实际收益: {outcome.get('pnl_pct', 'N/A')}%")
        print(f"目标达成: {'✓' if outcome.get('target_reached') else '✗'}")
        print(f"止损触发(收盘): {'✓' if outcome.get('stop_hit_close') else '✗'}")
        print(f"方向正确: {'✓' if outcome.get('direction_correct') else '✗'}")
        print(f"持有天数: {outcome.get('holding_days', 'N/A')}")

        if attribution:
            print(f"\nSkill归因:")
            print(f"  ✓ 正确: {attribution.get('correct_count', 0)} 个")
            for s in attribution.get('correct_skills', [])[:5]:
                print(f"    - {s.get('name', 'Unknown')} ({s.get('direction', '')})")
            print(f"  ✗ 错误: {attribution.get('wrong_count', 0)} 个")
            for s in attribution.get('wrong_skills', [])[:5]:
                print(f"    - {s.get('name', 'Unknown')} ({s.get('direction', '')})")

        if lessons:
            print(f"\n教训:")
            for i, lesson in enumerate(lessons[:5], 1):
                print(f"  {i}. {lesson}")

        # 同步到飞书（如果启用）
        if self._feishu_enabled:
            try:
                self.feishu.update_record_validation(trade_id, {
                    'actual_return_pct': outcome.get('pnl_pct', 0),
                    'outcome': 'win' if outcome.get('direction_correct') else 'loss',
                })
            except Exception:
                pass

        return result

    def batch_validate(self) -> Dict[str, Any]:
        """批量验证所有到期的模拟交易"""
        from utils.auto_validator import AutoValidator
        validator = AutoValidator()
        return validator.run_batch_validation()

    def get_portfolio(self) -> Dict[str, Any]:
        """查看模拟组合状态"""
        from utils.portfolio import Portfolio
        return Portfolio().get_summary()

    def get_equity_curve(self) -> List[Dict]:
        """查看资金曲线"""
        from utils.portfolio import Portfolio
        return Portfolio().equity_curve

    def feedback_stats(self) -> Dict[str, Any]:
        """查看反馈统计"""
        return self.feedback.calculate_statistics()

    def list_records(self) -> List[Dict]:
        """列出所有分析记录"""
        return self.feedback.records

    # ========== 快捷方法 ==========

    def quick_report(self, symbol: str, days: int = None) -> str:
        """快速生成分析报告（Markdown格式，直接可读）"""
        result = self.analyze(symbol, days=days, save_record=True)

        lines = [
            f"# 技术分析报告: {symbol}",
            "",
            "## 综合评分",
            f"{json.dumps(result.get('scoring', {}), ensure_ascii=False, indent=2)}",
            "",
            "## 指标摘要",
            result.get('indicator_summary', '无数据'),
            "",
            "## 趋势分析",
            f"{json.dumps(result.get('trend_analysis', {}), ensure_ascii=False, indent=2)}",
            "",
            "## 市场状态",
            f"- 状态: {result.get('market_regime', {}).get('primary', 'unknown')}",
            f"- 置信度: {result.get('market_regime', {}).get('confidence', 0)}",
            "",
            f"记录ID: {result.get('record_id', 'N/A')}",
        ]

        return '\n'.join(lines)


# 全局实例
_assistant: Optional[TechnicalAnalysisAssistant] = None


def assistant(api_key: Optional[str] = None) -> TechnicalAnalysisAssistant:
    """获取技术分析助手实例（单例模式）

    使用方式:
        from api import assistant
        result = assistant().analyze("AAPL", days=100)
    """
    global _assistant
    if _assistant is None:
        _assistant = TechnicalAnalysisAssistant(api_key=api_key)
    return _assistant


# 便捷函数

def analyze(symbol: str, days: int = None) -> Dict[str, Any]:
    """分析股票（便捷函数）

    使用方式:
        from api import analyze
        result = analyze("AAPL", days=100)
    """
    return assistant().analyze(symbol, days=days)


def upload_skill(file_path: Optional[str] = None,
                 text: Optional[str] = None,
                 activate: bool = False) -> Dict[str, Any]:
    """上传Skill（便捷函数）"""
    if file_path:
        return assistant().upload_skill_book(file_path, activate=activate)
    elif text:
        return assistant().upload_skill_text(text)
    else:
        raise ValueError("请提供 file_path 或 text")


def validate(record_id: str, return_pct: float) -> Dict[str, Any]:
    """验证分析记录（便捷函数）"""
    return assistant().validate(record_id, return_pct)


def validate_trade(trade_id: str) -> Dict[str, Any]:
    """验证模拟交易（便捷函数）"""
    return assistant().validate_trade(trade_id)


def batch_validate() -> Dict[str, Any]:
    """批量验证到期交易（便捷函数）"""
    return assistant().batch_validate()


def get_portfolio() -> Dict[str, Any]:
    """查看模拟组合（便捷函数）"""
    return assistant().get_portfolio()


def get_equity_curve() -> List[Dict]:
    """查看资金曲线（便捷函数）"""
    return assistant().get_equity_curve()


def list_skills() -> List[Dict]:
    """列出所有Skill（便捷函数）"""
    return assistant().list_skills()
