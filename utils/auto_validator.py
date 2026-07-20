"""Auto Validator - 自动验证引擎

3-5天后自动验证交易结果：
1. 查找待验证的交易
2. 下载验证期间价格数据
3. 计算实际结果（方向/目标/止损/回撤）
4. Skill级归因
5. 更新Portfolio和Skill performance
"""

import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

import pandas as pd


class AutoValidator:
    """自动验证引擎"""

    def __init__(self, trades_file: str = 'data/simulation/trades.jsonl',
                 portfolio_file: str = 'data/simulation/portfolio.json'):
        self.trades_file = trades_file
        self.portfolio_file = portfolio_file

    def find_pending_validations(self, date: str = None) -> List[Dict]:
        """查找所有待验证的交易

        Returns:
            待验证交易列表
        """
        date = date or datetime.now().strftime('%Y-%m-%d')
        pending = []

        if not os.path.exists(self.trades_file):
            return pending

        with open(self.trades_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    trade = json.loads(line)
                    if trade.get('status') != 'open':
                        continue
                    verification_date = trade.get('planned_verification_date', '')
                    if verification_date and verification_date <= date:
                        pending.append(trade)
                except json.JSONDecodeError:
                    continue

        return pending

    def validate_trade(self, trade_id: str,
                       price_data: pd.DataFrame = None) -> Dict:
        """验证单笔交易

        Args:
            trade_id: 交易ID
            price_data: 预加载的价格数据（可选，不传入则自动下载）

        Returns:
            验证结果
        """
        # 1. 读取交易记录
        trade = self._find_trade(trade_id)
        if not trade:
            return {'error': f'Trade {trade_id} not found'}

        if trade.get('status') != 'open':
            return {'error': f'Trade {trade_id} already validated'}

        plan = trade.get('plan', {})
        symbol = trade.get('symbol', '')
        entry_price = plan.get('entry', {}).get('price', 0)
        entry_date = plan.get('entry', {}).get('date', '')
        target_price = plan.get('target', {}).get('price', 0)
        stop_price = plan.get('stop_loss', {}).get('price', 0)
        direction = plan.get('direction', 'long')

        # 2. 获取价格数据
        if price_data is None:
            price_data = self._download_price_data(symbol, entry_date)

        if price_data is None or price_data.empty:
            return {'error': f'Could not download price data for {symbol}'}

        # 3. 构建price_path
        price_path = self._build_price_path(price_data, entry_date)

        if not price_path:
            return {'error': 'No price data after entry date'}

        # 4. 计算实际结果
        outcome = self._calculate_outcome(
            entry_price, target_price, stop_price, direction, price_path
        )

        # 5. Skill级归因
        attribution = self._attribute_skills(trade, outcome)

        # 6. 生成教训
        lessons = self._generate_lessons(trade, outcome, attribution)

        # 7. 更新交易记录
        trade['status'] = 'closed'
        trade['actual'] = outcome
        trade['attribution'] = attribution
        trade['lessons'] = lessons
        trade['verified_at'] = datetime.now().isoformat()

        # 8. 更新Portfolio
        self._update_portfolio(trade_id, outcome)

        # 9. 更新Skill performance
        self._update_skill_performance(trade, attribution)

        # 10. 保存更新
        self._update_trade_file(trade_id, trade)

        return {
            'trade_id': trade_id,
            'symbol': symbol,
            'outcome': outcome,
            'attribution': attribution,
            'lessons': lessons,
        }

    def run_batch_validation(self, date: str = None) -> Dict:
        """批量验证所有到期交易

        Returns:
            批量验证摘要
        """
        pending = self.find_pending_validations(date)
        results = []
        errors = []

        for trade in pending:
            trade_id = trade.get('trade_id')
            try:
                result = self.validate_trade(trade_id)
                if 'error' in result:
                    errors.append({'trade_id': trade_id, 'error': result['error']})
                else:
                    results.append(result)
            except Exception as e:
                errors.append({'trade_id': trade_id, 'error': str(e)})

        return {
            'date': date or datetime.now().strftime('%Y-%m-%d'),
            'total_pending': len(pending),
            'validated': len(results),
            'errors': len(errors),
            'results': results,
            'error_details': errors,
        }

    def _find_trade(self, trade_id: str) -> Optional[Dict]:
        """查找交易记录"""
        if not os.path.exists(self.trades_file):
            return None

        with open(self.trades_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    trade = json.loads(line)
                    if trade.get('trade_id') == trade_id:
                        return trade
                except json.JSONDecodeError:
                    continue
        return None

    def _download_price_data(self, symbol: str,
                              start_date: str) -> Optional[pd.DataFrame]:
        """下载验证期间价格数据（统一入口）"""
        from utils.data_source import download_range, DataSourceError
        from datetime import datetime, timedelta

        end_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        market = 'cn' if symbol.endswith(('.SH', '.SZ')) else 'us'

        try:
            return download_range(symbol, start_date=start_date,
                                  end_date=end_date, market=market)
        except DataSourceError as e:
            logger.warning(f"自动验证下载数据失败: {e}")
            return None
        except Exception as e:
            logger.warning(f"自动验证下载数据异常: {e}")
            return None

    def _download_eastmoney(self, symbol: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """从东方财富下载历史K线"""
        import requests

        code = symbol.split('.')[0]
        secid = f"1.{code}" if symbol.endswith('.SH') else f"0.{code}"

        url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
        params = {
            'secid': secid,
            'fields1': 'f1,f2,f3,f4,f5,f6',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'klt': '101',
            'fqt': '1',
            'beg': start.replace('-', ''),
            'end': end.replace('-', ''),
        }

        r = requests.get(url, params=params, timeout=15)
        data = r.json()

        klines = data.get('data', {}).get('klines', [])
        if not klines:
            return None

        rows = []
        for k in klines:
            parts = k.split(',')
            rows.append({
                'date': parts[0],
                'open': float(parts[1]),
                'close': float(parts[2]),
                'high': float(parts[3]),
                'low': float(parts[4]),
                'volume': float(parts[5]),
            })

        return pd.DataFrame(rows)

    def _build_price_path(self, df: pd.DataFrame,
                          entry_date: str) -> List[Dict]:
        """构建价格路径"""
        path = []

        # 确定日期列名
        date_col = None
        for col in ['date', '日期', 'trade_date']:
            if col in df.columns:
                date_col = col
                break

        if date_col is None:
            return path

        # 筛选entry_date之后的数据
        for _, row in df.iterrows():
            date_str = str(row[date_col])
            # 统一日期格式
            if '-' in date_str:
                pass  # already formatted
            else:
                date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

            if date_str >= entry_date:
                path.append({
                    'date': date_str,
                    'open': float(row.get('open', row.get('开盘', 0))),
                    'high': float(row.get('high', row.get('最高', 0))),
                    'low': float(row.get('low', row.get('最低', 0))),
                    'close': float(row.get('close', row.get('收盘', 0))),
                    'volume': float(row.get('volume', row.get('成交量', 0))),
                })

        return path

    def _calculate_outcome(self, entry_price: float, target_price: float,
                           stop_price: float, direction: str,
                           price_path: List[Dict]) -> Dict:
        """计算交易结果"""
        if not price_path:
            return {'error': 'Empty price path'}

        # 提取价格序列
        closes = [p['close'] for p in price_path]
        highs = [p['high'] for p in price_path]
        lows = [p['low'] for p in price_path]

        exit_price = closes[-1]  # 默认以最后收盘价出场
        exit_date = price_path[-1]['date']
        exit_reason = 'time_exit'

        # 判断方向
        if direction == 'long':
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100

            # 目标达成检查
            max_high = max(highs)
            target_reached = max_high >= target_price if target_price > 0 else False
            target_reached_date = None
            if target_reached:
                for p in price_path:
                    if p['high'] >= target_price:
                        target_reached_date = p['date']
                        break

            # 止损检查
            min_low = min(lows)
            stop_hit_intraday = min_low <= stop_price if stop_price > 0 else False
            stop_hit_close = any(p['close'] <= stop_price for p in price_path) if stop_price > 0 else False

            # 如果盘中触发止损，以止损价作为出场价（保守估计）
            if stop_hit_close:
                exit_reason = 'stop_hit'
                exit_price = stop_price

        else:  # short
            pnl_pct = ((entry_price - exit_price) / entry_price) * 100

            # 空头目标：价格跌到目标价以下
            min_low = min(lows)
            target_reached = min_low <= target_price if target_price > 0 else False

            # 空头止损：价格涨到止损价以上
            max_high = max(highs)
            stop_hit_intraday = max_high >= stop_price if stop_price > 0 else False
            stop_hit_close = any(p['close'] >= stop_price for p in price_path) if stop_price > 0 else False

            if stop_hit_close:
                exit_reason = 'stop_hit'
                exit_price = stop_price

        # 如果目标达成且未触发止损，以目标价出场（乐观估计）
        if target_reached and not stop_hit_close:
            exit_reason = 'target_reached'
            # 实际以验证日收盘价出场更合理
            # exit_price = target_price

        # 计算最大回撤和最大盈利
        if direction == 'long':
            max_profit_pct = ((max(highs) - entry_price) / entry_price) * 100
            max_drawdown_pct = ((min(lows) - entry_price) / entry_price) * 100
        else:
            max_profit_pct = ((entry_price - min(lows)) / entry_price) * 100
            max_drawdown_pct = ((entry_price - max(highs)) / entry_price) * 100

        holding_days = len(price_path) - 1  # 不含entry day

        return {
            'entry_price': entry_price,
            'exit_price': round(exit_price, 2),
            'exit_date': exit_date,
            'exit_reason': exit_reason,
            'holding_days': holding_days,
            'price_path': price_path,
            'pnl_pct': round(pnl_pct, 2),
            'max_return_pct': round(max_profit_pct, 2),
            'max_drawdown_pct': round(max_drawdown_pct, 2),
            'target_reached': target_reached,
            'target_reached_date': target_reached_date,
            'stop_hit_intraday': stop_hit_intraday,
            'stop_hit_close': stop_hit_close,
            'direction_correct': pnl_pct > 0,
        }

    def _attribute_skills(self, trade: Dict,
                          outcome: Dict) -> Dict:
        """Skill级归因"""
        triggered = trade.get('skills_triggered', [])
        actual_return = outcome.get('pnl_pct', 0)
        regime = trade.get('market_regime', 'unknown')

        correct_skills = []
        wrong_skills = []

        for skill in triggered:
            predicted = skill.get('direction', 'neutral')

            # 判断skill预测是否正确
            if predicted == 'bullish' and actual_return > 0:
                correct_skills.append(skill)
            elif predicted == 'bearish' and actual_return < 0:
                correct_skills.append(skill)
            elif predicted == 'neutral' and abs(actual_return) < 3:
                correct_skills.append(skill)
            else:
                wrong_skills.append(skill)

        return {
            'correct_skills': correct_skills,
            'wrong_skills': wrong_skills,
            'correct_count': len(correct_skills),
            'wrong_count': len(wrong_skills),
            'total_count': len(triggered),
            'market_regime': regime,
        }

    def _generate_lessons(self, trade: Dict, outcome: Dict,
                          attribution: Dict) -> List[str]:
        """生成教训"""
        lessons = []
        plan = trade.get('plan', {})
        rr = plan.get('risk_metrics', {})

        # 1. 风险收益比教训
        rr_ratio = rr.get('risk_reward_ratio', 0)
        if rr_ratio < 0.5:
            lessons.append(f'风险收益比{rr_ratio}不合格，不应入场')

        # 2. 止损教训
        if outcome.get('stop_hit_intraday') and not outcome.get('stop_hit_close'):
            lessons.append('盘中触发止损但收盘未触发，说明止损设置过紧')
        if outcome.get('stop_hit_close'):
            lessons.append('止损被触发，需复盘止损策略是否合理')

        # 3. 回撤教训
        max_dd = outcome.get('max_drawdown_pct', 0)
        if abs(max_dd) > 10:
            lessons.append(f'最大回撤{max_dd}%远超预期，波动率极高')

        # 4. Skill教训
        wrong_skills = attribution.get('wrong_skills', [])
        if wrong_skills:
            wrong_names = [s['name'] for s in wrong_skills]
            lessons.append(f'以下Skill预测错误: {", ".join(wrong_names)}')

        # 5. 环境教训
        regime = trade.get('market_regime', '')
        if 'late_extreme' in regime and outcome.get('direction_correct'):
            lessons.append('强趋势末期+极端偏离时趋势延续，超买信号失效')

        return lessons

    def _update_portfolio(self, trade_id: str, outcome: Dict):
        """更新Portfolio"""
        try:
            from utils.portfolio import Portfolio
            portfolio = Portfolio()

            exit_price = outcome.get('exit_price', 0)
            exit_reason = outcome.get('exit_reason', 'unknown')
            exit_date = outcome.get('exit_date', '')

            portfolio.close_position(trade_id, exit_price, exit_reason, exit_date)
        except Exception:
            pass  # Portfolio可能不存在或不适用

    def _update_skill_performance(self, trade: Dict, attribution: Dict):
        """更新Skill performance"""
        try:
            from utils.rule_index import RuleIndex
            rule_index = RuleIndex()
            regime = trade.get('market_regime', 'unknown')

            for skill in attribution.get('correct_skills', []):
                skill_id = skill.get('id')
                if skill_id:
                    rule_index.update_performance(skill_id, 'win', 0, regime)

            for skill in attribution.get('wrong_skills', []):
                skill_id = skill.get('id')
                if skill_id:
                    rule_index.update_performance(skill_id, 'loss', 0, regime)
        except Exception:
            pass

    def _update_trade_file(self, trade_id: str, updated_trade: Dict):
        """更新交易文件中的记录"""
        if not os.path.exists(self.trades_file):
            return

        lines = []
        with open(self.trades_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    trade = json.loads(line)
                    if trade.get('trade_id') == trade_id:
                        lines.append(json.dumps(updated_trade, ensure_ascii=False))
                    else:
                        lines.append(line)
                except json.JSONDecodeError:
                    lines.append(line)

        with open(self.trades_file, 'w', encoding='utf-8') as f:
            for line in lines:
                f.write(line + '\n')
