"""Deterministic Pipeline — 确定性执行流水线

核心设计：把USER_GUIDE.md中的SOP写死在代码里。
每次调用必须按固定步骤执行，不允许跳过、重排或漂移。

使用方式：
    from utils.deterministic_pipeline import DeterministicPipeline
    dp = DeterministicPipeline()
    result = dp.analyze("603773", days=100, simulate=True)
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional

import pandas as pd


class StepStatus(Enum):
    """步骤执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepTrace:
    """单步骤执行记录"""
    step_name: str
    step_number: int
    status: StepStatus
    input_summary: str = ""      # 输入摘要（隐私保护，不存完整数据）
    output_summary: str = ""     # 输出摘要
    error: str = ""              # 错误信息
    duration_ms: float = 0.0     # 执行耗时
    checkpoint_passed: bool = False  # 检查点是否通过


@dataclass
class PipelineResult:
    """流水线执行结果"""
    pipeline_name: str           # 流水线名称
    trace: List[StepTrace] = field(default_factory=list)  # 执行轨迹
    final_output: Dict = field(default_factory=dict)       # 最终输出
    errors: List[str] = field(default_factory=list)        # 错误列表
    warnings: List[str] = field(default_factory=list)      # 警告列表
    start_time: str = ""
    end_time: str = ""

    def add_step(self, step: StepTrace):
        """添加步骤记录"""
        self.trace.append(step)

    def has_critical_error(self) -> bool:
        """是否有致命错误（导致后续步骤无法执行）"""
        critical_steps = ["data_prepare", "indicator_compute", "llm_analyze"]
        for step in self.trace:
            if step.step_name in critical_steps and step.status == StepStatus.FAILED:
                return True
        return False

    def get_step(self, name: str) -> Optional[StepTrace]:
        """按名称查找步骤"""
        for step in self.trace:
            if step.step_name == name:
                return step
        return None

    def to_dict(self) -> Dict:
        """转为字典（用于序列化）"""
        return {
            'pipeline_name': self.pipeline_name,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'trace': [
                {
                    'step_name': s.step_name,
                    'step_number': s.step_number,
                    'status': s.status.value,
                    'input_summary': s.input_summary,
                    'output_summary': s.output_summary,
                    'error': s.error,
                    'duration_ms': s.duration_ms,
                    'checkpoint_passed': s.checkpoint_passed,
                }
                for s in self.trace
            ],
            'errors': self.errors,
            'warnings': self.warnings,
            'final_output_keys': list(self.final_output.keys()),
        }


class DeterministicPipeline:
    """确定性执行流水线

    所有方法内部按死顺序执行步骤，不允许跳过。
    每个步骤都有前置条件检查和后置输出校验。
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('DEEPSEEK_API_KEY', '')

        # 懒加载模块（需要时才import，避免循环依赖）
        self._extractor = None
        self._regime_detector = None
        self._analyzer = None
        self._skill_matcher = None
        self._trade_planner = None
        self._portfolio = None
        self._validator = None
        self._rule_index = None
        self._feedback = None

    # ========== 懒加载属性 ==========

    @property
    def extractor(self):
        if self._extractor is None:
            from utils.feature_extractor import FeatureExtractor
            self._extractor = FeatureExtractor()
        return self._extractor

    @property
    def regime_detector(self):
        if self._regime_detector is None:
            from utils.market_regime import MarketRegimeDetector
            self._regime_detector = MarketRegimeDetector()
        return self._regime_detector

    @property
    def analyzer(self):
        if self._analyzer is None:
            from utils.technical_analyzer import TechnicalAnalyzer
            self._analyzer = TechnicalAnalyzer(api_key=self.api_key)
        return self._analyzer

    @property
    def skill_matcher(self):
        if self._skill_matcher is None:
            from utils.skill_matcher import SkillMatcher
            self._skill_matcher = SkillMatcher()
        return self._skill_matcher

    @property
    def trade_planner(self):
        if self._trade_planner is None:
            from utils.trade_planner import TradePlanner
            self._trade_planner = TradePlanner(capital=1_000_000)
        return self._trade_planner

    @property
    def portfolio(self):
        if self._portfolio is None:
            from utils.portfolio import Portfolio
            self._portfolio = Portfolio(initial_capital=1_000_000)
        return self._portfolio

    @property
    def validator(self):
        if self._validator is None:
            from utils.auto_validator import AutoValidator
            self._validator = AutoValidator()
        return self._validator

    @property
    def rule_index(self):
        if self._rule_index is None:
            from utils.rule_index import RuleIndex
            self._rule_index = RuleIndex()
        return self._rule_index

    @property
    def feedback(self):
        if self._feedback is None:
            from utils.feedback_loop import FeedbackLoop
            self._feedback = FeedbackLoop()
        return self._feedback

    # ========== 工具方法 ==========

    def _run_step(self, name: str, number: int,
                  func: Callable, *args, **kwargs) -> tuple:
        """执行单步骤并记录trace

        Returns:
            (output, step_trace)
        """
        import time
        start = time.time()
        trace = StepTrace(
            step_name=name,
            step_number=number,
            status=StepStatus.RUNNING,
        )

        try:
            output = func(*args, **kwargs)
            trace.status = StepStatus.SUCCESS
            trace.output_summary = self._summarize_output(output)
            trace.checkpoint_passed = True
        except Exception as e:
            trace.status = StepStatus.FAILED
            trace.error = f"{type(e).__name__}: {str(e)}"
            trace.checkpoint_passed = False
            output = None

        trace.duration_ms = (time.time() - start) * 1000
        return output, trace

    def _summarize_output(self, output) -> str:
        """输出摘要（避免太大）"""
        if output is None:
            return "None"
        if isinstance(output, dict):
            return f"dict with keys: {list(output.keys())}"
        if isinstance(output, pd.DataFrame):
            return f"DataFrame {output.shape}"
        if isinstance(output, list):
            return f"list with {len(output)} items"
        return str(output)[:100]

    def _check_data_quality(self, df: pd.DataFrame) -> tuple:
        """数据质量检查

        Returns:
            (pass: bool, error_msg: str)
        """
        if df is None or df.empty:
            return False, "DataFrame is None or empty"

        if len(df) < 60:
            return False, f"Only {len(df)} rows, need at least 60"

        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            return False, f"Missing columns: {missing}"

        # 检查是否有NaN
        for col in required_cols:
            if df[col].isna().any():
                na_count = df[col].isna().sum()
                return False, f"Column {col} has {na_count} NaN values"

        return True, ""

    def _save_trace(self, result: PipelineResult):
        """保存执行轨迹到文件"""
        trace_dir = 'data/pipeline_traces'
        os.makedirs(trace_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{trace_dir}/{result.pipeline_name}_{timestamp}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

    # ========== 流水线1: 标准分析 ==========

    def analyze(self, symbol: str, days: int = 100,
                market: str = 'cn',
                simulate: bool = False) -> PipelineResult:
        """标准分析流水线（Step 1-7，可选Step 6-8）

        死顺序执行：
        1. 请求解析
        2. 数据准备
        3. 指标计算
        4. Skill匹配 + 环境适配
        5. LLM四阶段分析
        6. 交易计划生成（simulate=True时）
        7. 结果输出
        8. 模拟开仓（simulate=True时）
        """
        result = PipelineResult(
            pipeline_name=f"analyze_{symbol}",
            start_time=datetime.now().isoformat(),
        )

        # === Step 1: 请求解析 ===
        print(f"\n[Step 1/8] 请求解析: {symbol}, days={days}, simulate={simulate}")
        _, trace1 = self._run_step("request_parse", 1,
            lambda: {"symbol": symbol, "days": days, "market": market, "simulate": simulate})
        result.add_step(trace1)

        # === Step 2: 数据准备 ===
        print("[Step 2/8] 数据准备...")
        df, trace2 = self._run_step("data_prepare", 2,
            self._download_data, symbol, days, market)
        result.add_step(trace2)

        if df is None:
            result.errors.append("数据准备失败，无法继续")
            result.end_time = datetime.now().isoformat()
            self._save_trace(result)
            return result

        # 数据质量检查
        quality_ok, quality_msg = self._check_data_quality(df)
        trace2.checkpoint_passed = quality_ok
        if not quality_ok:
            result.errors.append(f"数据质量检查失败: {quality_msg}")
            # 继续执行（不致命），但标记警告

        # === Step 3: 指标计算 ===
        print("[Step 3/8] 指标计算...")
        features, trace3 = self._run_step("indicator_compute", 3,
            self.extractor.extract_all, df)
        result.add_step(trace3)

        if features is None:
            result.errors.append("指标计算失败，无法继续")
            result.end_time = datetime.now().isoformat()
            self._save_trace(result)
            return result

        # === Step 4: Skill匹配 + 环境适配 ===
        print("[Step 4/8] Skill匹配 + 环境适配...")
        match_result, trace4 = self._run_step("skill_match", 4,
            self.skill_matcher.match, features)
        result.add_step(trace4)

        if match_result is None:
            result.errors.append("Skill匹配失败，无法继续")
            result.end_time = datetime.now().isoformat()
            self._save_trace(result)
            return result

        # 提取市场环境
        market_regime = match_result.get('market_regime', 'unknown')
        print(f"  市场环境: {market_regime}")
        print(f"  触发Skill: {match_result.get('summary', {}).get('triggered_count', 0)}条")
        print(f"  准触发Skill: {match_result.get('summary', {}).get('near_triggered_count', 0)}条")

        # === Step 5: LLM四阶段分析 ===
        print("[Step 5/8] LLM四阶段分析...")
        # 使用MarketRegimeDetector获取真实confidence（避免硬编码）
        regime_obj = None
        regime_primary = market_regime
        regime_confidence = 0.8
        try:
            regime_obj = self.regime_detector.detect(df)
            regime_primary = regime_obj.primary
            regime_confidence = regime_obj.confidence
        except Exception:
            pass  # 检测失败时用 matcher 的环境标签兜底

        regime_info = {
            'primary': regime_primary,
            'secondary': getattr(regime_obj, 'secondary', '') if regime_obj else '',
            'confidence': regime_confidence,
            'indicators': getattr(regime_obj, 'indicators', {}) if regime_obj else {},
        }
        analysis_input = {
            'symbol': symbol,
            'market': market,
            'df': df,
            'data': df.reset_index().to_dict('records') if hasattr(df, 'reset_index') else [],
            'input_type': 'api',
            'indicator_features': features,  # 传入已计算的指标，避免重复计算
            'skill_match_result': match_result,  # 传入已完成的匹配，避免 analyzer 重复匹配
            'indicator_text': self.extractor.format_for_llm(features) if features else '',
            'market_regime': regime_info,
        }
        llm_result, trace5 = self._run_step("llm_analyze", 5,
            self.analyzer.run_full_analysis, analysis_input)
        result.add_step(trace5)

        if llm_result is None:
            result.errors.append("LLM分析失败，无法继续")
            result.end_time = datetime.now().isoformat()
            self._save_trace(result)
            return result

        # 检查Phase 1/2/3/4是否都存在
        for phase in ['phase1_indicator_inventory', 'phase2_skill_application',
                       'phase3_synergy_conflict', 'phase4_conclusion']:
            if phase not in llm_result.get('full_analysis', {}):
                result.warnings.append(f"LLM输出缺少 {phase}")

        # === Step 6: 交易计划生成（simulate=True时必须）===
        trade_plan = None
        if simulate:
            print("[Step 6/8] 交易计划生成...")
            # create_plan 期望 Phase1-4 顶层结构，传入 full_analysis 而非整个 analyzer 结果
            full_analysis = llm_result.get('full_analysis', llm_result)
            trade_plan, trace6 = self._run_step("trade_plan", 6,
                self.trade_planner.create_plan,
                full_analysis, features, symbol, symbol,
                match_result.get('triggered', []))
            result.add_step(trace6)

            if trade_plan and 'plan' in trade_plan:
                p = trade_plan['plan']
                rr = p.get('risk_metrics', {})
                print(f"  R/R Ratio: {rr.get('risk_reward_ratio')} ({rr.get('grade')})")
                print(f"  动态止损: {p.get('stop_loss', {}).get('dynamic_price')}")
                print(f"  仓位: {p.get('position', {}).get('shares')}股")

                # R:R检查点
                if rr.get('grade') == 'D':
                    result.warnings.append(
                        f"风险收益比不合格({rr.get('risk_reward_ratio')})，不建议入场"
                    )

        # === Step 7: 结果输出 ===
        print("[Step 7/8] 结果输出...")
        output = {
            'symbol': symbol,
            'market': market,
            'features': features,
            'market_regime': regime_info,  # MarketRegimeDetector 的真实检测结果（含 confidence）
            'skill_match': match_result,
            'full_analysis': llm_result.get('full_analysis', {}),
            'indicator_summary': self.extractor.format_for_llm(features) if features else '',
            'trade_plan': trade_plan,
        }
        _, trace7 = self._run_step("output", 7, lambda: output)
        result.add_step(trace7)
        result.final_output = output

        # === Step 8: 模拟开仓（simulate=True时必须）===
        if simulate and trade_plan:
            print("[Step 8/8] 模拟开仓...")

            # 检查R:R是否合格（D级不执行）
            rr_grade = trade_plan.get('plan', {}).get('risk_metrics', {}).get('grade', 'D')
            if rr_grade == 'D':
                print("  ⚠️ R/R Grade D，跳过开仓")
                trace8 = StepTrace(
                    step_name="simulation_open",
                    step_number=8,
                    status=StepStatus.SKIPPED,
                    output_summary="R/R Grade D, skipped",
                )
                result.add_step(trace8)
            else:
                position, trace8 = self._run_step("simulation_open", 8,
                    self.portfolio.open_position, trade_plan)
                result.add_step(trace8)

                if position and 'error' not in position:
                    # 保存交易记录（状态置为 open，否则自动验证永远找不到待验证交易）
                    trade_plan['status'] = 'open'
                    self.trade_planner.save_plan(trade_plan)
                    print(f"  ✅ 模拟持仓已建立: {position.get('shares', 0)}股")
                else:
                    err = position.get('error', 'unknown') if isinstance(position, dict) else 'open_position returned None'
                    result.errors.append(f"模拟开仓失败: {err}")

        # === 完成 ===
        result.end_time = datetime.now().isoformat()
        self._save_trace(result)

        # 打印摘要
        self._print_summary(result)

        return result

    # ========== 流水线2: 每日跟踪 ==========

    def track(self, symbol: str, price_data: Dict[str, float]) -> PipelineResult:
        """每日跟踪流水线

        死顺序：
        1. 更新价格
        2. 盯市
        3. 止损检查
        4. 止盈检查
        5. 记录状态
        """
        result = PipelineResult(
            pipeline_name=f"track_{symbol}",
            start_time=datetime.now().isoformat(),
        )

        # Step 1: 更新价格
        _, trace1 = self._run_step("update_price", 1,
            lambda: price_data)
        result.add_step(trace1)

        # Step 2: 盯市
        summary, trace2 = self._run_step("mark_to_market", 2,
            self.portfolio.daily_mark_to_market, price_data)
        result.add_step(trace2)

        # Step 3: 止损检查（每条持仓）
        positions = self.portfolio.get_open_positions()
        for pos in positions:
            trade_id = pos['trade_id']
            symbol_in_pos = pos['symbol']
            if symbol_in_pos in price_data:
                close_price = price_data[symbol_in_pos]
                # 简化估计：low=close*0.98, high=close*1.02
                low_price = close_price * 0.98
                high_price = close_price * 1.02

                stop_check, trace3 = self._run_step(
                    f"stop_check_{trade_id}", 3,
                    self.portfolio.check_stop_loss,
                    trade_id, low_price, high_price, close_price
                )
                result.add_step(trace3)

                # 如果收盘触发止损 → 提前验证
                if stop_check and stop_check.get('close_hit'):
                    result.warnings.append(
                        f"持仓 {trade_id} 收盘触发止损，建议立即验证"
                    )

        result.end_time = datetime.now().isoformat()
        self._save_trace(result)
        return result

    # ========== 流水线3: 自动验证 ==========

    def validate(self, trade_id: str,
                 price_data: pd.DataFrame = None) -> PipelineResult:
        """自动验证流水线

        死顺序：
        1. 读取交易记录
        2. 下载/获取价格数据
        3. 计算结果
        4. Skill归因
        5. 更新Portfolio
        6. 更新Skill performance
        7. 生成报告
        """
        result = PipelineResult(
            pipeline_name=f"validate_{trade_id}",
            start_time=datetime.now().isoformat(),
        )

        # Step 1: 读取交易记录
        trade, trace1 = self._run_step("load_trade", 1,
            self.validator._find_trade, trade_id)
        result.add_step(trace1)

        if trade is None:
            result.errors.append(f"Trade {trade_id} not found")
            result.end_time = datetime.now().isoformat()
            self._save_trace(result)
            return result

        # Step 2-7: 完整验证
        validation_result, trace_all = self._run_step("full_validate", 2,
            self.validator.validate_trade, trade_id, price_data)
        result.add_step(trace_all)

        if validation_result and 'error' not in validation_result:
            result.final_output = validation_result
        else:
            result.errors.append(
                validation_result.get('error', 'Validation failed') if validation_result else 'Validation failed'
            )

        result.end_time = datetime.now().isoformat()
        self._save_trace(result)
        return result

    # ========== 流水线4: Skill提取 ==========

    def extract_skills(self, text: str, source: str = "text") -> PipelineResult:
        """Skill提取流水线

        死顺序：
        1. 文本清洗
        2. LLM提取
        3. 格式校验
        4. 去重
        5. 保存到pending
        """
        result = PipelineResult(
            pipeline_name=f"extract_skills_{source}",
            start_time=datetime.now().isoformat(),
        )

        # Step 1: 文本清洗
        cleaned, trace1 = self._run_step("clean_text", 1,
            lambda t: t.strip()[:50000], text)  # 限制长度
        result.add_step(trace1)

        # Step 2: LLM提取
        from utils.llm_client import DeepSeekClient
        client = DeepSeekClient(api_key=self.api_key)
        extracted, trace2 = self._run_step("llm_extract", 2,
            client.extract_knowledge_from_text, cleaned, source)
        result.add_step(trace2)

        # Step 3: 格式校验
        valid_skills = []
        if extracted and 'rules' in extracted:
            for skill in extracted['rules']:
                if self._validate_skill_format(skill):
                    valid_skills.append(skill)
                else:
                    result.warnings.append(f"Skill格式校验失败: {skill.get('name', 'unknown')}")

        trace3 = StepTrace(
            step_name="validate_format",
            step_number=3,
            status=StepStatus.SUCCESS if valid_skills else StepStatus.FAILED,
            output_summary=f"{len(valid_skills)}/{len(extracted.get('rules', []))} valid",
        )
        result.add_step(trace3)

        # Step 4: 去重
        unique_skills = self._dedup_skills(valid_skills)
        trace4 = StepTrace(
            step_name="dedup",
            step_number=4,
            status=StepStatus.SUCCESS,
            output_summary=f"{len(unique_skills)} unique skills",
        )
        result.add_step(trace4)

        # Step 5: 保存到pending
        saved = []
        for skill in unique_skills:
            try:
                from utils.rule_index import RuleIndex
                idx = RuleIndex()
                rid = idx.add_rule(skill, auto_activate=False)
                saved.append({'rule_id': rid, 'name': skill.get('name', 'Unnamed')})
            except Exception as e:
                result.warnings.append(f"保存失败: {skill.get('name', 'unknown')}: {e}")

        trace5 = StepTrace(
            step_name="save_pending",
            step_number=5,
            status=StepStatus.SUCCESS if saved else StepStatus.FAILED,
            output_summary=f"{len(saved)} saved to pending",
        )
        result.add_step(trace5)

        result.final_output = {'extracted': len(extracted.get('rules', [])),
                                'valid': len(valid_skills),
                                'unique': len(unique_skills),
                                'saved': saved}
        result.end_time = datetime.now().isoformat()
        self._save_trace(result)
        return result

    # ========== 内部方法 ==========

    def _download_data(self, symbol: str, days: int, market: str) -> Optional[pd.DataFrame]:
        """下载数据（统一入口）

        异常直接抛出，由 _run_step 捕获并记录到 trace.error
        （不要往 self.errors 写——那是 PipelineResult 的属性）。
        """
        from utils.data_source import download_daily
        return download_daily(symbol, days=days, market=market)

    def _validate_skill_format(self, skill: Dict) -> bool:
        """校验Skill格式"""
        required = ['name', 'category', 'core_idea']
        for f_name in required:
            if f_name not in skill or not skill[f_name]:
                return False
        return True

    def _dedup_skills(self, skills: List[Dict]) -> List[Dict]:
        """基于名称去重"""
        seen = set()
        unique = []
        for s in skills:
            name = s.get('name', '').lower().replace(' ', '').replace('-', '')
            if name and name not in seen:
                seen.add(name)
                unique.append(s)
        return unique

    def _print_summary(self, result: PipelineResult):
        """打印执行摘要"""
        print(f"\n{'='*60}")
        print(f"流水线执行完成: {result.pipeline_name}")
        print(f"{'='*60}")

        success_count = sum(1 for s in result.trace if s.status == StepStatus.SUCCESS)
        failed_count = sum(1 for s in result.trace if s.status == StepStatus.FAILED)
        skipped_count = sum(1 for s in result.trace if s.status == StepStatus.SKIPPED)

        print(f"总步骤: {len(result.trace)} | 成功: {success_count} | 失败: {failed_count} | 跳过: {skipped_count}")

        if result.errors:
            print("\n错误:")
            for e in result.errors:
                print(f"  ✗ {e}")

        if result.warnings:
            print("\n警告:")
            for w in result.warnings:
                print(f"  ⚠ {w}")

        print("\n步骤详情:")
        for s in result.trace:
            icon = "✓" if s.status == StepStatus.SUCCESS else "✗" if s.status == StepStatus.FAILED else "⊘"
            print(f"  {icon} Step {s.step_number}: {s.step_name} ({s.duration_ms:.0f}ms) {s.output_summary}")

        print(f"{'='*60}")
