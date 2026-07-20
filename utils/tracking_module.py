"""跟踪模块 - 对已分析股票进行每日跟踪

核心功能：
1. 保存分析快照（从Phase 4结论提取关键预测数据）
2. 每日获取最新数据，重新计算指标
3. 对比上次快照，调用LLM评估预测vs实际
4. 保存跟踪记录，同步到飞书跟踪文档
"""

import json
import os
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime

import pandas as pd


class TrackingModule:
    """股票跟踪模块"""

    def __init__(self):
        self.snapshots_dir = 'data/snapshots'
        self.tracking_dir = 'data/tracking'
        os.makedirs(self.snapshots_dir, exist_ok=True)
        os.makedirs(self.tracking_dir, exist_ok=True)

    # ========== 快照管理 ==========

    def save_analysis_snapshot(self, symbol: str,
                               analysis_result: Dict[str, Any]) -> str:
        """从完整分析结果中提取关键预测数据，保存为快照

        Args:
            symbol: 股票代码
            analysis_result: analyze()返回的完整结果

        Returns:
            snapshot_id
        """
        snapshot_id = uuid.uuid4().hex[:8]

        full_analysis = analysis_result.get('full_analysis', {})
        p4 = full_analysis.get('phase4_conclusion', {}) if isinstance(
            full_analysis, dict) else {}

        # 如果LLM输出解析失败，尝试从raw_response提取
        if not p4 and analysis_result.get('full_analysis', {}).get('raw_response'):
            raw = analysis_result['full_analysis']['raw_response']
            if isinstance(raw, str):
                import re
                # 尝试提取关键字段
                direction_match = re.search(r'"方向"\s*:\s*"([^"]+)"', raw)
                confidence_match = re.search(r'"置信度"\s*:\s*(\d+)', raw)
                p4 = {
                    '方向': direction_match.group(1) if direction_match else 'unknown',
                    '置信度': int(confidence_match.group(1)) if confidence_match else 0,
                }

        # 提取关键价位（兼容中英文输出）
        key_levels = {}
        kl_raw = p4.get('key_levels') or p4.get('关键价位（触发位置）', {})
        if isinstance(kl_raw, dict):
            for k, v in kl_raw.items():
                try:
                    key_levels[k] = float(v)
                except (ValueError, TypeError):
                    key_levels[k] = str(v)

        # 提取指标签名（用于后续对比）
        indicator_sig = {}
        features = analysis_result.get('indicator_features', {})
        if features:
            for cat in ['trend', 'momentum', 'volatility', 'volume', 'composite']:
                cat_data = features.get(cat, {})
                if isinstance(cat_data, dict):
                    for k, v in cat_data.items():
                        if isinstance(v, (int, float)):
                            indicator_sig[f"{cat}.{k}"] = round(v, 2)

        # 提取触发的Skill
        skills = []
        skill_match = analysis_result.get('skill_match_result', {})
        for s in skill_match.get('triggered', []):
            skills.append(s.get('skill', {}).get('name', 'unnamed'))

        snapshot = {
            'snapshot_id': snapshot_id,
            'symbol': symbol,
            'analysis_date': datetime.now().isoformat(),
            'analysis_doc_token': analysis_result.get('feishu_doc_token', ''),
            'current_price': analysis_result.get('last_close'),
            'verdict': p4.get('direction') or p4.get('方向', 'unknown'),
            'confidence': p4.get('confidence') or p4.get('置信度', 0),
            'target_price': str(p4.get('target_price') or p4.get('目标价位', 'N/A')),
            'stop_loss': str(p4.get('stop_loss') or p4.get('止损价位', 'N/A')),
            'key_levels': key_levels,
            'watch_points': p4.get('watch_points') or p4.get('观察点', []),
            'invalidation_conditions': p4.get('invalidation_conditions') or p4.get('判断失效条件（重新评估触发点）', []),
            'regime': analysis_result.get('market_regime', {}),
            'indicator_signature': indicator_sig,
            'skills_triggered': skills,
        }

        path = os.path.join(self.snapshots_dir, f'{symbol}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

        return snapshot_id

    def get_latest_snapshot(self, symbol: str) -> Optional[Dict]:
        """读取某股票最新的分析快照"""
        path = os.path.join(self.snapshots_dir, f'{symbol}.json')
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    # ========== 跟踪分析 ==========

    def track(self, symbol: str, market: str = 'cn',
              days: int = 100) -> Dict[str, Any]:
        """对某只股票执行跟踪分析

        Returns:
            {
                'status': 'success' | 'no_snapshot' | 'error',
                'symbol': symbol,
                'snapshot': {...},
                'current_price': float,
                'price_change_pct': float,
                'days_since': int,
                'tracking_result': {...},
                'feishu_sync': {...}
            }
        """
        # 1. 读取快照
        snapshot = self.get_latest_snapshot(symbol)
        if not snapshot:
            return {
                'status': 'no_snapshot',
                'symbol': symbol,
                'message': f'{symbol} 没有找到分析快照，请先运行完整分析'
            }

        # 2. 获取最新数据
        df = None
        fetch_error = None
        try:
            df = self._fetch_latest_data(symbol, market, days)
        except Exception as e:
            fetch_error = str(e)
            # 回退：尝试从本地CSV读取（尝试多种文件名模式）
            possible_paths = [
                f'data/{symbol.replace(".", "_")}.csv',
                f'data/muyuan_{symbol.split(".")[0]}.csv',
                f'data/*{symbol.split(".")[0]}*.csv',
            ]
            for local_csv in possible_paths:
                if os.path.exists(local_csv):
                    try:
                        df = pd.read_csv(local_csv)
                        # 统一列名小写
                        df.columns = [c.lower() for c in df.columns]
                        df['date'] = pd.to_datetime(df['date'])
                        df = df.set_index('date').sort_index()
                        print(f"[INFO] 使用本地CSV数据: {local_csv}")
                        break
                    except Exception as e2:
                        pass  # 尝试下一个文件

        if df is None:
            return {
                'status': 'error',
                'symbol': symbol,
                'message': f'获取数据失败: {fetch_error}'
            }

        if len(df) < 2:
            return {
                'status': 'error',
                'symbol': symbol,
                'message': '数据不足，无法跟踪'
            }

        current_price = float(df['close'].iloc[-1])
        snapshot_price = snapshot.get('current_price')
        price_change_pct = ((current_price - snapshot_price) / snapshot_price * 100) if snapshot_price else 0

        # 计算快照日期至今的天数
        snapshot_date = datetime.fromisoformat(snapshot['analysis_date'])
        days_since = (datetime.now() - snapshot_date).days

        # 3. 重新计算指标
        from utils.feature_extractor import FeatureExtractor
        extractor = FeatureExtractor()
        current_features = extractor.extract_all(df)

        # 4. 计算指标变化
        indicator_changes = self._compute_indicator_changes(
            snapshot.get('indicator_signature', {}),
            current_features
        )

        # 5. 检查关键价位状态
        key_level_status = self._check_key_levels(
            snapshot.get('key_levels', {}),
            current_price,
            df
        )

        # 6. 构建价格变化摘要
        price_summary = {
            'current_price': current_price,
            'snapshot_price': snapshot_price,
            'change_pct': round(price_change_pct, 2),
            'days_since': days_since,
            'high_since': float(df['high'].max()),
            'low_since': float(df['low'].min()),
            'volume_avg': float(df['volume'].mean()),
        }

        # 7. 调用LLM跟踪分析
        from utils.llm_client import DeepSeekClient
        client = DeepSeekClient()

        tracking_result = client.track_analysis(
            snapshot=snapshot,
            current_features=current_features,
            price_summary=price_summary,
            indicator_changes=indicator_changes,
            key_level_status=key_level_status,
        )

        # 8. 保存跟踪记录
        record = {
            'track_date': datetime.now().isoformat(),
            'snapshot_id': snapshot['snapshot_id'],
            'symbol': symbol,
            'current_price': current_price,
            'price_change_pct': round(price_change_pct, 2),
            'days_since_analysis': days_since,
            'verdict_vs_expected': tracking_result.get('verdict_vs_expected', 'unknown'),
            'key_level_status': key_level_status,
            'indicator_changes': {k: v['text'] for k, v in indicator_changes.items()},
            'new_judgment': tracking_result.get('new_judgment', 'unknown'),
            'new_direction': tracking_result.get('new_direction', 'unknown'),
            'new_confidence': tracking_result.get('new_confidence', 0),
            'updated_targets': tracking_result.get('updated_targets', ''),
            'updated_stop': tracking_result.get('updated_stop', ''),
            'issues_found': tracking_result.get('issues_found', []),
            'raw_llm_response': tracking_result,
        }
        self.save_tracking_record(symbol, record)

        return {
            'status': 'success',
            'symbol': symbol,
            'snapshot': snapshot,
            'current_price': current_price,
            'price_change_pct': round(price_change_pct, 2),
            'days_since': days_since,
            'tracking_result': tracking_result,
        }

    # ========== 数据获取 ==========

    def _fetch_latest_data(self, symbol: str, market: str,
                           days: int) -> pd.DataFrame:
        """获取最新数据（统一入口）

        优先级：
        1. 本地 CSV
        2. akshare（A股）
        3. yfinance（美股/全球）
        """
        from utils.data_source import download_daily, DataSourceError

        try:
            return download_daily(symbol, days=days, market=market)
        except DataSourceError as e:
            raise ValueError(f"无法获取 {symbol} 的数据: {e}")
        except Exception as e:
            raise ValueError(f"获取 {symbol} 数据异常: {e}")

    # ========== 指标对比 ==========

    def _compute_indicator_changes(self, snapshot_sig: Dict,
                                   current_features: Dict) -> Dict[str, Dict]:
        """计算指标变化，返回可读的变化描述"""
        changes = {}

        # 从current_features中提取当前值
        current_sig = {}
        for cat in ['trend', 'momentum', 'volatility', 'volume', 'composite']:
            cat_data = current_features.get(cat, {})
            if isinstance(cat_data, dict):
                for k, v in cat_data.items():
                    if isinstance(v, (int, float)):
                        current_sig[f"{cat}.{k}"] = round(v, 2)

        # 对比关键指标
        key_metrics = {
            'rsi': ['momentum.rsi_14', 'trend.rsi'],
            'macd_hist': ['momentum.macd_hist', 'trend.macd_hist'],
            'adx': ['trend.adx_14', 'trend.adx'],
            'atr_pct': ['volatility.atr_pct', 'volatility.atr_14'],
            'bb_width': ['volatility.bb_width', 'volatility.bb_width_pct'],
        }

        for display_name, possible_keys in key_metrics.items():
            old_val = None
            for k in possible_keys:
                if k in snapshot_sig:
                    old_val = snapshot_sig[k]
                    break

            new_val = None
            for k in possible_keys:
                if k in current_sig:
                    new_val = current_sig[k]
                    break

            if old_val is not None and new_val is not None:
                delta = new_val - old_val
                direction = "↑" if delta > 0 else "↓" if delta < 0 else "→"
                changes[display_name] = {
                    'old': old_val,
                    'new': new_val,
                    'delta': round(delta, 2),
                    'text': f"{old_val} → {new_val} ({direction}{abs(round(delta, 2))})"
                }

        return changes

    def _check_key_levels(self, key_levels: Dict, current_price: float,
                          df: pd.DataFrame) -> Dict[str, str]:
        """检查关键价位触发状态"""
        status = {}
        for name, level in key_levels.items():
            if not isinstance(level, (int, float)):
                status[name] = f"{level} (非数值)"
                continue

            pct_dist = (current_price - level) / level * 100

            # 判断方向：如果是阻力位，向上突破算触发；如果是支撑位，向下跌破算触发
            if '阻力' in name or '暂缓' in name or '预警' in name or '止损' in name:
                if current_price >= level:
                    status[name] = f"已突破 ({level}, 当前{current_price})"
                else:
                    status[name] = f"未触发，距离+{abs(round(pct_dist, 2))}%"
            elif '支撑' in name or '确认' in name or '目标' in name:
                if current_price <= level:
                    status[name] = f"已跌破 ({level}, 当前{current_price})"
                else:
                    status[name] = f"未触发，距离-{abs(round(pct_dist, 2))}%"
            else:
                if abs(pct_dist) < 1:
                    status[name] = f"触及 ({level}, 偏差{round(pct_dist, 2)}%)"
                else:
                    status[name] = f"距离{round(pct_dist, 2)}%"

        return status

    # ========== 记录存储 ==========

    def save_tracking_record(self, symbol: str, record: Dict):
        """保存跟踪记录到JSONL文件"""
        path = os.path.join(self.tracking_dir, f'{symbol}.jsonl')
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    def get_tracking_history(self, symbol: str) -> List[Dict]:
        """获取某股票的跟踪历史"""
        path = os.path.join(self.tracking_dir, f'{symbol}.jsonl')
        if not os.path.exists(path):
            return []
        records = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return records

    def list_tracked_symbols(self) -> List[str]:
        """列出所有有快照的股票"""
        symbols = []
        for f in os.listdir(self.snapshots_dir):
            if f.endswith('.json'):
                symbols.append(f.replace('.json', ''))
        return symbols
