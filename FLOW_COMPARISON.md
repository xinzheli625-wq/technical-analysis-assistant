# 双入口流程对比：api.py vs deterministic_pipeline.py

> 分析日期: 2026-06-06
> 目标: 帮助决策 api.py 是否应完全委托给 DeterministicPipeline

---

## 一、数据流总览对比

### api.py analyze() 数据流

```
用户调用: assistant().analyze("603773", days=100, simulate=True)
  │
  ├─→ ① 下载数据 (akshare/yfinance) ──→ df (DataFrame)
  │
  ├─→ ② FeatureExtractor.extract_all(df) ──→ features (Dict)
  │
  ├─→ ③ MarketRegimeDetector.detect(df) ──→ regime (MarketRegime对象)
  │       primary/secondary/confidence/indicators
  │
  ├─→ ④ TechnicalAnalyzer.run_full_analysis(data)
  │       ├── 内部: FeatureExtractor.extract_all(df)  ← ⚠️ 重复计算!
  │       ├── 内部: SkillMatcher.match(features)
  │       └── 内部: DeepSeekClient.analyze_full(...)
  │           返回: full_analysis {phase1, phase2, phase3, phase4}
  │
  ├─→ ⑤ 组装 result: market_regime + indicator_summary
  │
  ├─→ ⑥ FeedbackLoop.record_analysis(result, skills_used=[])  ← ⚠️ 空列表!
  │
  ├─→ ⑦ TrackingModule.save_analysis_snapshot(symbol, result)
  │
  └─→ ⑧ Feishu同步 (如果启用)
  │
  ├─→ [无!] simulate=True 时**不**生成交易计划  ← 🔴 缺失!
  ├─→ [无!] simulate=True 时**不**开仓  ← 🔴 缺失!
  ├─→ [无!] 不检查数据质量(行数/OHLCV)  ← 🔴 缺失!
  ├─→ [无!] 不检查R:R是否合格  ← 🔴 缺失!
  └─→ 返回: result (Dict)
```

### deterministic_pipeline.py analyze() 数据流

```
用户调用: dp.analyze("603773", days=100, simulate=True)
  │
  ├─→ Step 1: 请求解析 ──→ 标准化请求结构
  │
  ├─→ Step 2: 数据下载 ──→ df (DataFrame)
  │     ├── 优先级: 本地CSV → akshare → yfinance
  │     └── ⚠️ 缺少 Eastmoney fallback (与文档不一致)
  │
  ├─→ Step 2.5: 数据质量检查  ← ✅ 强制!
  │     ├── ≥60行? 否则报错
  │     ├── OHLCV五列完整?
  │     └── 无NaN?
  │
  ├─→ Step 3: 指标计算 ──→ features (Dict)
  │
  ├─→ Step 4: Skill匹配 + 环境适配
  │     ├── SkillMatcher.match(features)
  │     ├── 输出: triggered/near_triggered/not_triggered
  │     └── 输出: market_regime (字符串)
  │
  ├─→ Step 5: LLM四阶段分析
  │     ├── TechnicalAnalyzer.run_full_analysis(data)
  │     └── ⚠️ 内部又调用了一次 extract_all(df) ── 重复计算
  │
  ├─→ Step 6: 交易计划生成 (simulate=True时)
  │     ├── TradePlanner.create_plan(...)
  │     ├── 固定止损 + 动态ATR止损
  │     ├── 仓位计算
  │     ├── R:R评级 (A/B/C/D)
  │     └── ⚠️ R:R < 0.5 (Grade D) → 拒绝入场提示
  │
  ├─→ Step 7: 结果输出组装
  │
  ├─→ Step 8: 模拟开仓 (simulate=True时)
  │     ├── 检查: 资金足够?
  │     ├── 检查: 单标的不超10%?
  │     ├── 检查: 总敞口不超50%?
  │     ├── 检查: R:R Grade ≠ D?
  │     └── Portfolio.open_position(trade_plan)
  │
  ├─→ 保存 pipeline trace 到 data/pipeline_traces/
  │
  └─→ 返回: PipelineResult (含完整执行轨迹)
```

---

## 二、步骤级详细对比

### 2.1 分析流程 (simulate=True)

| 步骤 | api.py | pipeline.py | 差异 |
|------|--------|-------------|------|
| **请求解析** | 隐式(参数校验) | Step 1 显式 | pipeline更规范 |
| **数据下载** | akshare → yfinance | 本地CSV → akshare → yfinance | pipeline多本地优先 |
| **数据质量检查** | ❌ **无** | ✅ 强制检查 ≥60行/OHLCV/无NaN | **pipeline有，api无** |
| **数据源优先级** | akshare → yfinance → (报错) | 本地CSV → akshare → yfinance | pipeline多一层 |
| **指标计算** | extract_all(df) | extract_all(df) | 相同 |
| **市场环境检测** | MarketRegimeDetector.detect() → 对象 | SkillMatcher._detect_market_regime() → 字符串 | **格式不一致** |
| **Skill匹配** | analyzer内部调用 | Step 4 显式调用 | pipeline更透明 |
| **环境适配权重** | ❌ **无** | ✅ _apply_regime_adjustment() | **pipeline有，api无** |
| **LLM分析** | analyze_full() | analyze_full() | 相同 |
| **Phase 1/2/3/4** | 都有 | 都有 | 相同 |
| **指标摘要格式化** | format_for_llm() | format_for_llm() | 相同 |
| **交易计划生成** | ❌ **完全没有** | ✅ TradePlanner.create_plan() | **pipeline有，api无** |
| **动态止损** | ❌ **无** | ✅ 优先ATR倍数(1.5x/2x/3x) | **pipeline有，api无** |
| **R:R评级** | ❌ **无** | ✅ A/B/C/D评级 | **pipeline有，api无** |
| **仓位计算** | ❌ **无** | ✅ PositionSizer.fixed_risk() | **pipeline有，api无** |
| **模拟开仓** | ❌ **无** | ✅ Portfolio.open_position() | **pipeline有，api无** |
| **skilled_used记录** | ❌ **[] 空列表** | ❌ 未记录到feedback | 两者都没做好 |
| **反馈记录保存** | ✅ FeedbackLoop.record_analysis() | ❌ **未调用** | api有，pipeline无 |
| **分析快照保存** | ✅ TrackingModule.save_snapshot() | ❌ **未调用** | api有，pipeline无 |
| **飞书同步** | ✅ _sync_to_feishu() | ❌ **未调用** | api有，pipeline无 |
| **执行轨迹记录** | ❌ **无** | ✅ PipelineResult + StepTrace | **pipeline有，api无** |
| **检查点校验** | ❌ **无** | ✅ 每步有checkpoint_passed | **pipeline有，api无** |

### 2.2 跟踪流程 (每日跟踪)

| 功能 | api.py | pipeline.py | 差异 |
|------|--------|-------------|------|
| **入口方法** | `assistant().track(symbol)` | `dp.track(symbol, price_data)` | pipeline需要传入价格字典 |
| **数据获取** | TrackingModule内部获取 | 需要外部传入 | api更自动化 |
| **盯市更新** | ❌ **无** | ✅ Portfolio.daily_mark_to_market() | **pipeline有，api无** |
| **止损检查** | ❌ **无** | ✅ 区分盘中/收盘触发 | **pipeline有，api无** |
| **飞书同步** | ✅ _sync_tracking_to_feishu() | ❌ **无** | api有，pipeline无 |
| **保存跟踪记录** | ✅ save_tracking_record() | ❌ **无** | api有，pipeline无 |

### 2.3 验证流程

| 功能 | api.py | pipeline.py | 差异 |
|------|--------|-------------|------|
| **入口方法** | `assistant().validate(record_id, return_pct)` | `dp.validate(trade_id, price_data)` | 参数不同 |
| **数据源** | 内部用yfinance获取 | 需要外部传入/自动下载 | api更自动化 |
| **Skill归因** | ✅ feedback_loop 概率思维 | ✅ auto_validator _attribute_skills() | 两者都有，但逻辑不同 |
| **教训生成** | ❌ **无** | ✅ _generate_lessons() | **pipeline有，api无** |
| **Portfolio更新** | ❌ **无** | ✅ close_position() | **pipeline有，api无** |
| **自动下载价格** | ✅ 内部yfinance | ✅ akshare→yfinance→eastmoney | pipeline数据源更多 |
| **分环境统计** | ✅ by_regime | ✅ by_regime | 相同 |

---

## 三、返回结构对比

### api.py 返回 (Dict)

```python
{
    'symbol': '603773',
    'market': 'cn',
    'input_type': 'api',
    'indicator_features': {...},      # 50+指标
    'skill_match_result': {...},      # triggered/near/not
    'full_analysis': {                # Phase 1/2/3/4
        'phase1_indicator_inventory': {...},
        'phase2_skill_application': {...},
        'phase3_synergy_conflict': {...},
        'phase4_conclusion': {...},
    },
    # 向后兼容字段
    'trend_analysis': {...},
    'pattern_analysis': {...},
    'indicator_analysis': {...},
    'volume_price_analysis': {...},
    'behavior_analysis': {...},
    'event_inference': {...},
    'scoring': {...},
    # 元数据
    'market_regime': {'primary': ..., 'confidence': ...},
    'indicator_summary': '...',
    'record_id': 'abc123',
    'is_update': False,
}
```

### pipeline.py 返回 (PipelineResult)

```python
PipelineResult(
    pipeline_name='analyze_603773',
    trace=[StepTrace, StepTrace, ...],   # 每步执行记录
    final_output={
        'symbol': '603773',
        'market': 'cn',
        'features': {...},
        'market_regime': 'trending_up_late_extreme',  # 字符串
        'skill_match': {...},
        'full_analysis': {...},
        'indicator_summary': '...',
        'trade_plan': {...},  # <-- simulate=True时
    },
    errors=[],
    warnings=[],
)
```

**关键差异:**
- api返回平铺Dict，pipeline返回结构化PipelineResult
- api有 `record_id`（反馈系统ID），pipeline没有
- api有飞书同步产生的 `feishu_sync`，pipeline没有
- pipeline有 `trace`（执行轨迹），api没有
- pipeline的 `market_regime` 是字符串，api是对象

---

## 四、功能矩阵：谁在做什么

| 功能 | api.py | pipeline.py | 建议 |
|------|--------|-------------|------|
| 数据下载 | ✅ | ✅ (多本地优先) | pipeline更优 |
| 数据质量检查 | ❌ | ✅ | **pipeline有** |
| 指标计算 | ✅ | ✅ | 相同 |
| 市场环境检测 | ✅ (对象) | ✅ (字符串) | **需统一** |
| Skill匹配 | ✅ (analyzer内部) | ✅ (显式Step 4) | pipeline更透明 |
| 环境适配权重 | ❌ | ✅ | **pipeline有** |
| LLM四阶段分析 | ✅ | ✅ | 相同 |
| 交易计划生成 | ❌ | ✅ | **pipeline有** |
| 动态止损 | ❌ | ✅ | **pipeline有** |
| R:R评级 | ❌ | ✅ | **pipeline有** |
| 仓位计算 | ❌ | ✅ | **pipeline有** |
| 模拟开仓 | ❌ | ✅ | **pipeline有** |
| 反馈记录 | ✅ | ❌ | **api有** |
| 分析快照 | ✅ | ❌ | **api有** |
| 飞书同步 | ✅ | ❌ | **api有** |
| 执行轨迹 | ❌ | ✅ | **pipeline有** |
| 检查点校验 | ❌ | ✅ | **pipeline有** |

---

## 五、修复方案建议

### 方案A: api.py 完全委托给 pipeline（推荐）

```python
# api.py
class TechnicalAnalysisAssistant:
    def analyze(self, symbol, days=None, market='us', simulate=False, ...):
        from utils.deterministic_pipeline import DeterministicPipeline
        dp = DeterministicPipeline(api_key=self.api_key)
        result = dp.analyze(symbol, days=days, market=market, simulate=simulate)
        
        # pipeline 缺少的功能在这里补充
        if simulate and result.final_output.get('trade_plan'):
            # 保存反馈记录（pipeline里没做）
            self._save_feedback_record(result)
            # 飞书同步（pipeline里没做）
            if self._feishu_enabled:
                self._sync_to_feishu(symbol, result.final_output)
            # 保存快照（pipeline里没做）
            self.tracking.save_analysis_snapshot(symbol, result.final_output)
        
        return result
```

**优点**: 统一入口，pipeline的确定性流程得到保证
**缺点**: 需要把pipeline缺少的功能（反馈/飞书/快照）补充进去

### 方案B: pipeline 补充缺失功能，然后 api.py 委托

1. 在 pipeline Step 7 后添加：保存反馈记录、飞书同步、保存快照
2. api.py 的 analyze() 直接调用 dp.analyze()
3. 保留 api.py 的其他方法（Skill管理、列表等）不变

**优点**: 最干净，所有流程逻辑都在pipeline里
**缺点**: 改动范围稍大

### 方案C: 保留双入口，明确分工

- api.py: 只做**分析+输出报告**（老功能，向后兼容）
- pipeline.py: 做**完整交易模拟**（新功能）

**优点**: 改动最小
**缺点**: 双入口永久存在，技术债务，流程漂移风险仍在

---

## 六、我的建议

**采用方案B**：

1. **pipeline 补充3个缺失功能**（反馈记录、飞书同步、分析快照）
2. **api.py analyze() 完全委托给 pipeline**
3. **api.py 的其他方法**（Skill管理、validate、track等）**逐步迁移**到pipeline

这样：
- 分析流程的**确定性得到保证**（SOP写死在pipeline代码里）
- **所有现有功能保留**（反馈、飞书、快照一个不少）
- 用户接口不变（仍然 `assistant().analyze()`）
- 未来扩展都在pipeline框架内
