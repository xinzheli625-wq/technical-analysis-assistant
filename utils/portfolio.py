"""Portfolio - 模拟持仓管理

核心功能：
1. 模拟开仓/平仓
2. 每日盯市（mark-to-market）
3. 止损/止盈检查（区分盘中触发和收盘触发）
4. 资金曲线追踪
5. 风险敞口监控

设计要点：
- 支持多空双向（long/short）
- 区分盘中止损和收盘止损（603773教训）
- 资金曲线每日记录
- 单标的不超10%，总多头敞口不超50%
"""

import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime


class Portfolio:
    """模拟投资组合"""

    DEFAULT_INITIAL_CAPITAL = 1_000_000
    DEFAULT_MAX_POSITION_PCT = 10.0  # 单标的最大仓位
    DEFAULT_MAX_TOTAL_EXPOSURE_PCT = 50.0  # 总敞口上限
    DEFAULT_MIN_SHARES = 100  # A股最小交易单位

    def __init__(self, initial_capital: float = None,
                 portfolio_file: str = 'data/simulation/portfolio.json'):
        self.initial_capital = initial_capital or self.DEFAULT_INITIAL_CAPITAL
        self.portfolio_file = portfolio_file
        self.cash = self.initial_capital
        self.positions: Dict[str, Dict] = {}  # trade_id -> position
        self.trade_history: List[Dict] = []
        self.equity_curve: List[Dict] = []
        self._load()

    def _load(self):
        """从文件加载portfolio状态"""
        if os.path.exists(self.portfolio_file):
            try:
                with open(self.portfolio_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.cash = data.get('cash', self.initial_capital)
                self.positions = data.get('positions', {})
                self.trade_history = data.get('trade_history', [])
                self.equity_curve = data.get('equity_curve', [])
            except (json.JSONDecodeError, IOError):
                pass

        # 确保初始资金曲线记录
        if not self.equity_curve:
            self.equity_curve.append({
                'date': datetime.now().strftime('%Y-%m-%d'),
                'equity': self.initial_capital,
                'cash': self.initial_capital,
                'unrealized_pnl': 0,
            })

    def _save(self):
        """保存portfolio状态到文件"""
        os.makedirs(os.path.dirname(self.portfolio_file), exist_ok=True)
        data = {
            'capital': {
                'initial': self.initial_capital,
                'current': self.get_total_equity(),
                'cash': self.cash,
            },
            'positions': self.positions,
            'trade_history': self.trade_history[-50:],  # 保留最近50条
            'equity_curve': self.equity_curve,
            'exposure': self._calculate_exposure(),
            'updated_at': datetime.now().isoformat(),
        }
        with open(self.portfolio_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def open_position(self, trade_plan: Dict) -> Dict:
        """开仓

        Args:
            trade_plan: TradePlanner生成的交易计划

        Returns:
            position记录
        """
        plan = trade_plan.get('plan', trade_plan)
        position_info = plan.get('position', {})
        entry = plan.get('entry', {})
        stop = plan.get('stop_loss', {})
        target = plan.get('target', {})

        trade_id = trade_plan.get('trade_id', 'unknown')
        symbol = trade_plan.get('symbol', 'UNKNOWN')
        direction = plan.get('direction', 'long')
        shares = position_info.get('shares', 0)
        entry_price = entry.get('price', 0)
        notional = position_info.get('notional', shares * entry_price)

        if shares <= 0 or entry_price <= 0:
            return {'error': 'Invalid position parameters'}

        # 检查资金
        if notional > self.cash:
            return {'error': f'Insufficient cash: need {notional}, have {self.cash}'}

        # 检查敞口限制
        exposure = self._calculate_exposure()
        current_symbol_exposure = exposure.get('by_symbol', {}).get(symbol, 0)
        new_symbol_exposure = current_symbol_exposure + notional

        if new_symbol_exposure / self.initial_capital * 100 > self.DEFAULT_MAX_POSITION_PCT:
            return {'error': f'Position limit exceeded for {symbol}'}

        total_exposure = exposure.get('total_long', 0) + exposure.get('total_short', 0)
        if direction == 'long':
            new_total = total_exposure + notional
        else:
            new_total = total_exposure + notional  # short also consumes exposure

        if new_total / self.initial_capital * 100 > self.DEFAULT_MAX_TOTAL_EXPOSURE_PCT:
            return {'error': f'Total exposure limit exceeded: {new_total / self.initial_capital * 100:.1f}%'}

        # 扣除现金
        self.cash -= notional

        # 记录持仓
        position = {
            'trade_id': trade_id,
            'symbol': symbol,
            'symbol_name': trade_plan.get('symbol_name', ''),
            'direction': direction,
            'shares': shares,
            'entry_price': entry_price,
            'entry_date': entry.get('date', datetime.now().strftime('%Y-%m-%d')),
            'current_price': entry_price,
            'stop_price': stop.get('price', stop.get('dynamic_price', 0)),
            'stop_type': stop.get('type', 'unknown'),
            'target_price': target.get('price', 0),
            'notional': notional,
            'unrealized_pnl_pct': 0.0,
            'unrealized_pnl_amount': 0.0,
            'status': 'open',
            'created_at': datetime.now().isoformat(),
        }

        self.positions[trade_id] = position

        # 记录交易历史
        self.trade_history.append({
            'trade_id': trade_id,
            'action': 'open',
            'symbol': symbol,
            'direction': direction,
            'shares': shares,
            'price': entry_price,
            'notional': notional,
            'timestamp': datetime.now().isoformat(),
        })

        self._save()
        return position

    def close_position(self, trade_id: str, exit_price: float,
                       exit_reason: str, exit_date: str = None) -> Dict:
        """平仓

        Args:
            trade_id: 交易ID
            exit_price: 出场价格
            exit_reason: 出场原因 (target_reached / stop_hit / time_exit / manual)
            exit_date: 出场日期

        Returns:
            平仓结果
        """
        if trade_id not in self.positions:
            return {'error': f'Position {trade_id} not found'}

        pos = self.positions[trade_id]
        direction = pos['direction']
        shares = pos['shares']
        entry_price = pos['entry_price']
        notional = pos['notional']

        # 计算盈亏
        if direction == 'long':
            pnl_amount = (exit_price - entry_price) * shares
        else:
            pnl_amount = (entry_price - exit_price) * shares

        pnl_pct = (pnl_amount / notional) * 100 if notional > 0 else 0

        # 释放现金（本金 + 盈亏）
        self.cash += notional + pnl_amount

        # 记录平仓
        close_record = {
            'trade_id': trade_id,
            'action': 'close',
            'symbol': pos['symbol'],
            'direction': direction,
            'shares': shares,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'exit_reason': exit_reason,
            'exit_date': exit_date or datetime.now().strftime('%Y-%m-%d'),
            'pnl_amount': round(pnl_amount, 2),
            'pnl_pct': round(pnl_pct, 2),
            'holding_days': self._calculate_holding_days(pos['entry_date'], exit_date),
            'timestamp': datetime.now().isoformat(),
        }

        self.trade_history.append(close_record)

        # 从持仓中移除
        del self.positions[trade_id]

        # 更新资金曲线
        self._update_equity_curve()

        self._save()
        return close_record

    def daily_mark_to_market(self, prices: Dict[str, float],
                             date: str = None) -> Dict:
        """每日盯市

        Args:
            prices: {symbol: close_price} 字典
            date: 日期 (默认今天)

        Returns:
            portfolio摘要
        """
        date = date or datetime.now().strftime('%Y-%m-%d')
        total_unrealized = 0
        stop_hits = []

        for trade_id, pos in self.positions.items():
            symbol = pos['symbol']
            if symbol not in prices:
                continue

            current_price = prices[symbol]
            pos['current_price'] = current_price

            # 计算浮动盈亏
            if pos['direction'] == 'long':
                unrealized = (current_price - pos['entry_price']) * pos['shares']
            else:
                unrealized = (pos['entry_price'] - current_price) * pos['shares']

            pos['unrealized_pnl_amount'] = round(unrealized, 2)
            pos['unrealized_pnl_pct'] = round((unrealized / pos['notional']) * 100, 2) if pos['notional'] > 0 else 0
            total_unrealized += unrealized

        # 更新资金曲线
        self._update_equity_curve(date)

        self._save()

        return {
            'date': date,
            'total_equity': self.get_total_equity(),
            'cash': self.cash,
            'unrealized_pnl': round(total_unrealized, 2),
            'open_positions': len(self.positions),
            'exposure': self._calculate_exposure(),
        }

    def check_stop_loss(self, trade_id: str,
                        low_price: float, high_price: float,
                        close_price: float) -> Dict:
        """检查止损是否触发

        603773教训：区分盘中触发和收盘触发

        Args:
            trade_id: 交易ID
            low_price: 当日最低价（多头止损用）
            high_price: 当日最高价（空头止损用）
            close_price: 当日收盘价

        Returns:
            {
                'triggered': bool,
                'intraday_hit': bool,  # 盘中是否触发
                'close_hit': bool,     # 收盘是否触发
                'stop_price': float,
            }
        """
        if trade_id not in self.positions:
            return {'error': 'Position not found'}

        pos = self.positions[trade_id]
        stop_price = pos.get('stop_price', 0)
        direction = pos['direction']

        if stop_price <= 0:
            return {'triggered': False, 'reason': 'No stop price set'}

        intraday_hit = False
        close_hit = False

        if direction == 'long':
            # 多头：价格跌破止损价（最低价触发）
            intraday_hit = low_price <= stop_price
            close_hit = close_price <= stop_price
        else:
            # 空头：价格涨破止损价（最高价触发）
            intraday_hit = high_price >= stop_price
            close_hit = close_price >= stop_price

        return {
            'triggered': close_hit,  # 以收盘价触发为准执行
            'intraday_hit': intraday_hit,
            'close_hit': close_hit,
            'stop_price': stop_price,
            'current_price': close_price,
            'direction': direction,
        }

    def get_total_equity(self) -> float:
        """获取总权益（现金 + 持仓市值）"""
        total = self.cash
        for pos in self.positions.values():
            total += pos['notional'] + pos.get('unrealized_pnl_amount', 0)
        return total

    def get_summary(self) -> Dict:
        """获取组合摘要"""
        total_equity = self.get_total_equity()
        total_return = ((total_equity - self.initial_capital) / self.initial_capital) * 100

        # 计算最大回撤
        max_drawdown = self._calculate_max_drawdown()

        return {
            'initial_capital': self.initial_capital,
            'current_equity': round(total_equity, 2),
            'total_return_pct': round(total_return, 2),
            'cash': round(self.cash, 2),
            'open_positions': len(self.positions),
            'total_trades': len([t for t in self.trade_history if t.get('action') == 'close']),
            'max_drawdown_pct': round(max_drawdown, 2),
            'exposure': self._calculate_exposure(),
            'equity_latest': self.equity_curve[-1] if self.equity_curve else None,
        }

    def _calculate_exposure(self) -> Dict:
        """计算风险敞口"""
        total_long = 0
        total_short = 0
        by_symbol = {}

        for pos in self.positions.values():
            notional = pos['notional']
            symbol = pos['symbol']

            if pos['direction'] == 'long':
                total_long += notional
            else:
                total_short += notional

            by_symbol[symbol] = by_symbol.get(symbol, 0) + notional

        total = total_long + total_short

        return {
            'total_long': round(total_long, 2),
            'total_short': round(total_short, 2),
            'total': round(total, 2),
            'net_long_pct': round((total_long - total_short) / self.initial_capital * 100, 2),
            'gross_exposure_pct': round(total / self.initial_capital * 100, 2),
            'by_symbol': {k: round(v, 2) for k, v in by_symbol.items()},
        }

    def _calculate_max_drawdown(self) -> float:
        """计算最大回撤"""
        if not self.equity_curve:
            return 0

        max_dd = 0
        peak = self.equity_curve[0]['equity']

        for point in self.equity_curve:
            equity = point['equity']
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        return max_dd

    def _update_equity_curve(self, date: str = None):
        """更新资金曲线"""
        date = date or datetime.now().strftime('%Y-%m-%d')
        total_equity = self.get_total_equity()

        # 避免同一天重复记录
        if self.equity_curve and self.equity_curve[-1].get('date') == date:
            self.equity_curve[-1]['equity'] = round(total_equity, 2)
            self.equity_curve[-1]['cash'] = round(self.cash, 2)
        else:
            self.equity_curve.append({
                'date': date,
                'equity': round(total_equity, 2),
                'cash': round(self.cash, 2),
                'open_positions': len(self.positions),
            })

    def _calculate_holding_days(self, entry_date: str, exit_date: str) -> int:
        """计算持有天数"""
        try:
            from datetime import datetime
            d1 = datetime.strptime(entry_date, '%Y-%m-%d')
            d2 = datetime.strptime(exit_date or datetime.now().strftime('%Y-%m-%d'), '%Y-%m-%d')
            return (d2 - d1).days
        except:
            return 0

    def get_open_positions(self) -> List[Dict]:
        """获取所有持仓"""
        return list(self.positions.values())

    def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """获取交易历史"""
        return self.trade_history[-limit:]
