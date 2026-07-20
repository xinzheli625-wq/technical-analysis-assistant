"""重新提取 Trading for a Living 摘录（2026-07）

背景：
- 桌面 PDF 实为《The New Sell and Sell Short》的 30 页宣传摘录（非完整书籍）。
- 首次提取仅得 10 条 Skill（每段 1 条，密度过低）。
- 本脚本以更细分段（~2000 字符）+ 强化指导重新提取，
  所有新 Skill 存入 pending 队列等待用户审核激活，trigger 全部经过可解析性校验。

用法：
    python _reextract_trading_excerpt.py
"""

import json

from dotenv import load_dotenv

load_dotenv()

CLEAN_TEXT = 'data/extracted/Trading_for_a_Living_clean.txt'
OUT_FILE = 'data/extracted/Trading_for_a_Living_reextract_skills.json'
TARGET_SEG_CHARS = 2000

INSTRUCTION = """提取要求：
1. 本段可能包含多个方法论/交易规则/风险管理原则，请全部提取，不要只取一个
2. 卖出、做空、止损、资金管理、交易心理类的规则也是有效的 Skill，category 用 behavior 或 scoring
3. trigger 指标名只能使用：close, open, high, low, price, volume, sma5, sma10, sma20, sma50,
   ema12, ema26, price_vs_sma20_pct, rsi, rsi_14, macd_line, macd_signal, macd_histogram,
   adx, stochastic_k, stochastic_d, cci, williams_r, atr, atr_pct, bollinger_percent_b,
   bollinger_bandwidth, volume_ratio, obv_trend, mfi, trend_stage, mtf_alignment,
   composite_mid_trend, trend, return_1d, return_5d, return_20d
4. 形态相关条件用 {"indicator": "pattern", "operator": "=", "value": "形态名"}
5. 布尔指标（extreme_deviation 等）value 用 1 或 0
6. 账户状态类条件（仓位、盈亏、资金）系统无法计算，不要写入 trigger，
   可保留在 analysis_steps 中作为人工执行步骤
7. threshold 必须忠实原文，不要编造"""


def make_segments(text: str, target: int = TARGET_SEG_CHARS):
    """按段落边界切成 ~target 字符的段"""
    paragraphs = [p for p in text.split('\n\n') if p.strip()]
    segments = []
    current = []
    current_len = 0
    for p in paragraphs:
        if current_len + len(p) > target and current:
            segments.append('\n\n'.join(current))
            current = []
            current_len = 0
        current.append(p)
        current_len += len(p) + 2
    if current:
        segments.append('\n\n'.join(current))
    return segments


def main():
    import pandas as pd

    from utils.feature_extractor import FeatureExtractor
    from utils.llm_client import DeepSeekClient
    from utils.rule_index import RuleIndex
    from utils.skill_matcher import SkillMatcher

    with open(CLEAN_TEXT, encoding='utf-8') as f:
        text = f.read()

    segments = make_segments(text)
    print(f"共 {len(segments)} 段（目标 {TARGET_SEG_CHARS} 字符/段）")

    client = DeepSeekClient()
    sm = SkillMatcher()
    features = FeatureExtractor().extract_all(pd.read_csv('data/300502.csv'))

    # 现有 Skill 名称（用于去重）
    ri = RuleIndex()
    existing_names = {
        r.get('name', '').lower().replace(' ', '')
        for r in ri._rules if r.get('status') in ('active', 'pending')
    }

    all_rules = []
    skipped_dup = 0
    for i, seg in enumerate(segments, 1):
        result = client.extract_skills_from_segment(seg, INSTRUCTION)
        rules = result.get('rules', [])
        print(f"[{i}/{len(segments)}] 提取 {len(rules)} 条")

        for rule in rules:
            name_key = rule.get('name', '').lower().replace(' ', '')
            if not name_key or name_key in existing_names:
                skipped_dup += 1
                continue

            # trigger 可解析性校验
            bad = []
            for c in (rule.get('trigger') or {}).get('conditions', []):
                ind = c.get('indicator', '')
                if ind in ('pattern', 'pattern_detected'):
                    continue
                if sm._get_indicator_value(features, ind) is None:
                    bad.append(ind)
            if bad:
                print(f"    [跳过] {rule.get('name')}: 不可解析指标 {bad}")
                continue

            rule['source'] = 'Trading_for_a_Living (excerpt re-extract 2026-07)'
            rule['source_chapter'] = f'segment_{i}'
            existing_names.add(name_key)
            all_rules.append(rule)

    print(f"\n有效新 Skill: {len(all_rules)} 条, 重复/已有跳过: {skipped_dup}")

    # 保存到 pending 队列
    saved = []
    for rule in all_rules:
        rule_id = ri.add_rule(rule, auto_activate=False)
        saved.append({'rule_id': rule_id, 'name': rule.get('name')})

    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump({'rules': all_rules, 'saved': saved}, f, ensure_ascii=False, indent=2)

    print(f"已保存 {len(saved)} 条到 pending 队列: {OUT_FILE}")
    print("审核后用 assistant().activate_skill(rule_id) 激活")


if __name__ == '__main__':
    main()
