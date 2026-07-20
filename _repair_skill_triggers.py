"""修复问题 Skill 的触发条件（2026-07 全面审查后）

背景：
- 规则库 1209 条 active Skill 中，77 条的 trigger 条件使用了 SkillMatcher
  无法解析的指标名，导致这些 Skill 永远不会触发。
- 其中 price_vs_sma200_pct / sma200 类在 days>=200 时有效，不需要修。
- 市场广度/情绪类（arms_index、mcclellan、consensus 等）单股 OHLCV 无法计算，
  做 deprecate 处理。
- 其余通过 LLM 将 trigger 改写为可解析的指标名（保留方法论不变）。

用法：
    python _repair_skill_triggers.py            # 全量修复
    python _repair_skill_triggers.py --dry-run  # 只诊断不修改
"""

import json
import os
import sys

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

RULES_FILE = 'data/skill_rules.jsonl'
REPAIR_LOG = 'data/extracted/trigger_repair_log.json'

# 市场广度/情绪/账户参数类：单股 OHLCV 原理上无法计算 → deprecate
DEPRECATE_INDICATORS = {
    'ad_line', 'arms_index', 'arms_index_10ma', 'open_trin', 'tick_index',
    'mcclellan_oscillator', 'mcclellan_sum_index', 'hpi_value',
    'bullish_consensus', 'consensus_bullish', 'bullish_ratio',
    'sentiment_consensus', 'correlation_coefficient',
    'capital', 'position_size', 'risk_amount', 'profit_loss',
    'profit_loss_ratio', 'profit_target', 'reward_risk_ratio',
    'equity_curve', 'avg_trade_pnl', 'month', 'timeframe', '持仓量',
}

# 需要 >=200 天数据，days=200 分析时有效，不需要修
VALID_LONG_WINDOW = {'sma200', 'price_vs_sma200_pct'}

# LLM 修复时可用的指标名白名单（与 SkillMatcher.alias_map 对齐）
ALLOWED_INDICATORS = """
数值比较类（operator: > >= < <= = between）：
- 价格：close, open, high, low, price, volume
- 均线：sma3, sma4, sma5, sma9, sma10, sma13, sma20, sma21, sma40, sma50, sma65, sma90, sma200,
  ema12, ema26, price_vs_sma20_pct, price_vs_sma50_pct(不存在勿用), price_vs_sma200_pct, sma20_vs_sma50
- 动量：rsi, rsi_14, macd_line, macd_signal, macd_histogram, macd_trend, kdj_k, kdj_d, kdj_j,
  stochastic_k, stochastic_d, cci, williams_r, momentum, roc_12, tsi, ao, uo, ppo, stoch_rsi
- 趋势强度：adx, adx_value, adx_signal, supertrend_direction, ichimoku_price_vs_kijun
- 波动率：atr, atr_value, atr_pct, bollinger_upper, bollinger_middle, bollinger_lower,
  bollinger_percent_b, bollinger_bandwidth, bollinger_position, historical_volatility, ulcer_index
- 量能：volume_ratio, volume_trend, obv, obv_value, obv_trend, vwap, mfi,
  force_index, chaikin_oscillator
- 背离：divergence_count, divergence_bullish_count, divergence_bearish_count,
  divergence_primary_signal（值: bullish/bearish/none）
- 趋势阶段：trend_stage（值: early/early_acceleration/middle/late/fading/ranging）,
  adx_change_10d_pct, ma_deviation_20, ma_deviation_50, price_acceleration,
  extreme_deviation（值: 1/0）
- 波动率状态：volatility_state（值: squeeze/expansion/expanding/contracting/normal）,
  volatility_squeeze, volatility_expansion, squeeze_to_expansion_alert（值: 1/0）
- 动量加速度：rsi_change_1d, rsi_change_5d, rsi_acceleration, macd_hist_acceleration,
  price_acceleration_state, momentum_direction（值: strengthening/weakening/neutral）
- 多时间框架：mtf_alignment（值: strongly_bullish/bullish/mixed/bearish/strongly_bearish）,
  mtf_short_turning, mtf_long_trend_intact（值: 1/0）
- 综合：composite_short_trend, composite_mid_trend（值: up/down/range）,
  trend（前置趋势，值: up/down）, price_position_60d, return_1d, return_5d, return_20d

形态类（operator: =，value 为形态名）：
- {"indicator": "pattern", "operator": "=", "value": "Double Bottom"} 表示检测到该形态
- 可用形态名：Double Bottom, Head and Shoulders, Ascending Triangle, Descending Triangle,
  Symmetrical Triangle, Cup and Handle, Rising Wedge, Falling Wedge, Flag, Pennant,
  Ascending Channel, Descending Channel, Rectangle, Rounded Top, Rounded Bottom,
  V-Reversal Bottom, V-Reversal Top, Island Reversal Top, Island Reversal Bottom
- 形态几何参数（颈线斜率、肩高、到顶点距离等）无法计算，不要用
"""


def load_features():
    from utils.feature_extractor import FeatureExtractor
    df = pd.read_csv('data/300502.csv')
    return FeatureExtractor().extract_all(df)


def get_bad_indicators(rule, sm, features):
    """返回规则中不可解析的指标名列表"""
    bad = []
    for c in (rule.get('trigger') or {}).get('conditions', []):
        ind = c.get('indicator', '')
        if ind in ('pattern', 'pattern_detected'):
            continue
        if sm._get_indicator_value(features, ind) is None:
            bad.append(ind)
    return bad


def repair_trigger_with_llm(client, rule, bad_inds, sm, features, max_attempts=2):
    """让 LLM 把 trigger 改写为可解析指标名，返回新 trigger 或 None"""
    for attempt in range(max_attempts):
        prompt = f"""以下是一个技术分析 Skill 的完整定义。它的 trigger 触发条件中，
这些指标名系统无法解析：{bad_inds}

请把 trigger 改写为系统可解析的形式，要求：
1. 保持方法论原意，用等价或最接近的可解析条件替换
2. 只能使用下方白名单中的指标名
3. 形态相关条件用 {{"indicator": "pattern", "operator": "=", "value": "形态名"}}
4. 布尔类指标（extreme_deviation、volatility_squeeze 等）value 用 1 或 0
5. 如果实在无法用白名单指标表达该方法的触发条件，返回 {{"trigger": null}}

## Skill 定义
{json.dumps({k: v for k, v in rule.items() if k in ('name', 'category', 'core_idea', 'analysis_steps', 'reference_data', 'trigger', 'signal')}, ensure_ascii=False, indent=2)}

## 可解析指标白名单
{ALLOWED_INDICATORS}

## 输出格式（严格JSON，只输出trigger）
{{"trigger": {{"conditions": [...], "logic": "AND"}}}} 或 {{"trigger": null}}
"""
        raw = client._call([{'role': 'user', 'content': prompt}], temperature=0.1)
        from utils.llm_client import _safe_parse_json
        result = _safe_parse_json(raw)

        new_trigger = result.get('trigger')
        if new_trigger is None:
            return None  # LLM 判断无法表达

        # 验证新 trigger 的所有条件都可解析
        still_bad = []
        for c in new_trigger.get('conditions', []):
            ind = c.get('indicator', '')
            if ind in ('pattern', 'pattern_detected'):
                continue
            if sm._get_indicator_value(features, ind) is None:
                still_bad.append(ind)

        if not still_bad:
            return new_trigger
        bad_inds = still_bad  # 带反馈重试

    return None


def main():
    dry_run = '--dry-run' in sys.argv

    from utils.skill_matcher import SkillMatcher
    sm = SkillMatcher()
    features = load_features()

    # 加载规则库
    rules = []
    with open(RULES_FILE, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rules.append(json.loads(line))

    to_repair = []      # (index, rule, bad_inds)
    to_deprecate = []   # (index, rule, bad_inds)
    skipped_long_window = 0

    for i, r in enumerate(rules):
        if r.get('status') != 'active':
            continue
        bad = get_bad_indicators(r, sm, features)
        if not bad:
            continue
        bad_set = set(bad)
        if bad_set <= VALID_LONG_WINDOW:
            skipped_long_window += 1
            continue
        if bad_set <= DEPRECATE_INDICATORS:
            to_deprecate.append((i, r, bad))
        else:
            to_repair.append((i, r, bad))

    print(f"诊断: 需LLM修复 {len(to_repair)} 条, 需弃用 {len(to_deprecate)} 条, "
          f"长周期有效跳过 {skipped_long_window} 条")

    if dry_run:
        for _, r, bad in to_repair:
            print(f"  [修复] {r['name']} [{r['rule_id']}]: {bad}")
        for _, r, bad in to_deprecate:
            print(f"  [弃用] {r['name']} [{r['rule_id']}]: {bad}")
        return

    # 弃用处理
    for i, r, bad in to_deprecate:
        r['status'] = 'deprecated'
        r['deprecated_reason'] = (
            f"触发条件依赖市场广度/账户数据（{', '.join(sorted(set(bad)))}），"
            f"单股 OHLCV 无法计算，2026-07 审查弃用")
        print(f"[弃用] {r['name']}: {sorted(set(bad))}")

    # LLM 修复
    from utils.llm_client import DeepSeekClient
    client = DeepSeekClient()

    repaired, failed = [], []
    for n, (i, r, bad) in enumerate(to_repair, 1):
        print(f"[{n}/{len(to_repair)}] 修复 {r['name']} (不可解析: {bad})...")
        new_trigger = repair_trigger_with_llm(client, r, bad, sm, features)
        if new_trigger:
            r['trigger'] = new_trigger
            r.setdefault('notes', '')
            r['notes'] = (r['notes'] + ' | ' if r['notes'] else '') + \
                f"trigger 2026-07 LLM修复（原指标: {', '.join(sorted(set(bad)))}）"
            r['version'] = r.get('version', 1) + 1
            repaired.append(r['name'])
            print(f"    -> 修复成功: {json.dumps(new_trigger['conditions'], ensure_ascii=False)[:120]}")
        else:
            # 修复不了 → 弃用
            r['status'] = 'deprecated'
            r['deprecated_reason'] = (
                f"触发条件（{', '.join(sorted(set(bad)))}）无法改写为可解析指标，2026-07 审查弃用")
            failed.append(r['name'])
            print(f"    -> 无法修复，已弃用")

    # 写回规则库
    with open(RULES_FILE, 'w', encoding='utf-8') as f:
        for r in rules:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    # 重建索引
    from utils.rule_index import RuleIndex
    RuleIndex()._save_index()

    log = {
        'repaired': repaired,
        'repair_failed_deprecated': failed,
        'deprecated_breadth': [r['name'] for _, r, _ in to_deprecate],
        'skipped_long_window': skipped_long_window,
    }
    os.makedirs('data/extracted', exist_ok=True)
    with open(REPAIR_LOG, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(f"\n完成: 修复 {len(repaired)} 条, 无法修复弃用 {len(failed)} 条, "
          f"广度类弃用 {len(to_deprecate)} 条")
    print(f"日志: {REPAIR_LOG}")


if __name__ == '__main__':
    main()
