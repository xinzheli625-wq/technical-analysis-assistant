"""Data Source - 统一数据源管理

统一分析、跟踪、验证三个阶段的数据获取逻辑，避免口径不一致。
优先级：
1. 本地 CSV（data/{symbol}.csv）
2. 当日缓存（data/cache/，同一交易日不重复下载）
3. akshare（A 股）
4. yfinance（美股/全球）

所有方法统一返回标准化的 DataFrame：
    columns: [open, high, low, close, volume], index: date
"""

import logging
import os
from datetime import datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

CACHE_DIR = 'data/cache'


class DataSourceError(Exception):
    """数据源异常"""
    pass


def _cache_path(symbol: str, market: str) -> str:
    """当日缓存路径（按交易日区分，隔天自动失效）"""
    today = datetime.now().strftime('%Y%m%d')
    safe = symbol.replace('.', '_').replace('/', '_')
    return f"{CACHE_DIR}/{safe}_{market}_{today}.csv"


def _read_cache(symbol: str, market: str, days: int) -> Optional[pd.DataFrame]:
    """读取当日缓存（仅同一交易日有效）"""
    path = _cache_path(symbol, market)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        required = ['open', 'high', 'low', 'close', 'volume']
        if not all(c in df.columns for c in required) or df.empty:
            return None
        logger.info(f"使用当日缓存: {symbol}, {len(df)} 条")
        return df.tail(days)
    except Exception as e:
        logger.warning(f"读取缓存失败 {path}: {e}")
        return None


def _write_cache(symbol: str, market: str, df: pd.DataFrame):
    """写入当日缓存"""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        df.to_csv(_cache_path(symbol, market))
    except Exception as e:
        logger.warning(f"写入缓存失败: {e}")


def _local_csv_path(symbol: str) -> str:
    """生成本地 CSV 路径候选"""
    return f"data/{symbol.replace('.', '_')}.csv"


def _load_local_csv(symbol: str, days: Optional[int] = None) -> Optional[pd.DataFrame]:
    """尝试读取本地 CSV"""
    local_path = _local_csv_path(symbol)
    if not os.path.exists(local_path):
        return None

    try:
        df = pd.read_csv(local_path)
        df.columns = [c.lower() for c in df.columns]

        # 标准化列名
        column_mapping = {
            '日期': 'date', 'date': 'date',
            '开盘': 'open', 'open': 'open',
            '收盘': 'close', 'close': 'close',
            '最高': 'high', 'high': 'high',
            '最低': 'low', 'low': 'low',
            '成交量': 'volume', '成交额': 'volume', 'volume': 'volume', 'amount': 'volume',
        }
        df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})

        required = ['date', 'open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required if c not in df.columns]
        if missing:
            logger.warning(f"本地 CSV {local_path} 缺少列: {missing}")
            return None

        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=['open', 'high', 'low', 'close', 'volume'])
        df = df.sort_values('date').set_index('date')

        if days is not None and len(df) >= days:
            return df.tail(days)
        return df
    except Exception as e:
        logger.warning(f"读取本地 CSV {local_path} 失败: {e}")
        return None


def _cn_prefix(code: str) -> str:
    """根据 A 股代码推断交易所前缀（60/68/9→sh，00/30→sz，4/8→bj）"""
    if code.startswith(('60', '68', '9')):
        return 'sh'
    if code.startswith(('00', '30')):
        return 'sz'
    if code.startswith(('4', '8')):
        return 'bj'
    return 'sh' if code.startswith('6') else 'sz'


def _standardize_akshare_hist(df: pd.DataFrame, days: Optional[int] = None) -> Optional[pd.DataFrame]:
    """标准化 akshare stock_zh_a_hist 的中文列输出"""
    df = df.rename(columns={
        '日期': 'date', '开盘': 'open', '收盘': 'close',
        '最高': 'high', '最低': 'low', '成交量': 'volume',
    })
    required = ['date', 'open', 'high', 'low', 'close', 'volume']
    if not all(c in df.columns for c in required):
        logger.warning(f"akshare 返回列不完整: {list(df.columns)}")
        return None

    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['open', 'high', 'low', 'close', 'volume'])
    df = df.sort_values('date').set_index('date')
    return df.tail(days) if days else df


def _download_akshare(symbol: str, days: int) -> Optional[pd.DataFrame]:
    """通过 akshare 下载 A 股数据"""
    try:
        import akshare as ak
    except ImportError:
        logger.warning("akshare 未安装，跳过 A 股数据源")
        return None

    code = symbol.split('.')[0]

    # 优先东方财富接口（stock_zh_a_hist）：包含真实成交量（股），列名规范
    try:
        df = ak.stock_zh_a_hist(symbol=code, period='daily', adjust='qfq')
        if df is not None and len(df) > 0:
            return _standardize_akshare_hist(df, days)
    except Exception as e:
        logger.warning(f"akshare(eastmoney) 下载 {symbol} 失败: {e}")

    # 回退腾讯接口（stock_zh_a_hist_tx）：注意其 amount 列为成交额而非成交量，
    # 仅在东财接口不可用时兜底，量能指标口径可能与其他来源不一致
    try:
        prefix = 'sh' if symbol.endswith('.SH') else 'sz' if symbol.endswith('.SZ') else _cn_prefix(code)
        df = ak.stock_zh_a_hist_tx(symbol=f'{prefix}{code}')
        if df is None or len(df) == 0:
            return None

        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={'amount': 'volume'})

        required = ['date', 'open', 'high', 'low', 'close', 'volume']
        if not all(c in df.columns for c in required):
            logger.warning(f"akshare 返回列不完整: {list(df.columns)}")
            return None

        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=['open', 'high', 'low', 'close', 'volume'])
        df = df.sort_values('date').set_index('date')
        return df.tail(days)
    except Exception as e:
        logger.warning(f"akshare 下载 {symbol} 失败: {e}")
        return None


def _download_yfinance(symbol: str, days: int) -> Optional[pd.DataFrame]:
    """通过 yfinance 下载数据"""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance 未安装，跳过该数据源")
        return None

    try:
        ticker = symbol.replace('.SH', '.SS').replace('.SZ', '.SZ')
        df = yf.download(ticker, period=f"{days}d", progress=False)
        if df is None or df.empty:
            return None

        # yfinance（>=0.2.x）单 ticker 也可能返回 MultiIndex 列 (Price, Ticker)，
        # 必须先展开 MultiIndex 再统一小写，否则 tuple.lower() 直接抛异常
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]

        # 标准化列名
        column_mapping = {
            'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
            'adj close': 'close', 'volume': 'volume',
        }
        df = df.rename(columns=column_mapping)

        # 如果索引不是 date，尝试转换
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        required = ['open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required if c not in df.columns]
        if missing:
            logger.warning(f"yfinance 返回列不完整: {list(df.columns)}")
            return None

        for col in required:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=required)
        return df
    except Exception as e:
        logger.warning(f"yfinance 下载 {symbol} 失败: {e}")
        return None


def download_daily(symbol: str, days: int = 100, market: str = 'cn',
                   prefer_local: bool = True) -> pd.DataFrame:
    """统一下载日线数据

    Args:
        symbol: 股票代码，如 '603773' 或 'AAPL'
        days: 需要的天数
        market: 'cn' 或 'us'
        prefer_local: 是否优先使用本地 CSV

    Returns:
        标准化的 DataFrame

    Raises:
        DataSourceError: 所有数据源都失败
    """
    if prefer_local:
        df = _load_local_csv(symbol, days=days)
        if df is not None and len(df) >= min(days, 60):
            logger.info(f"使用本地 CSV 数据: {symbol}, {len(df)} 条")
            return df

    # 当日缓存：同一交易日不重复下载
    df = _read_cache(symbol, market, days)
    if df is not None and len(df) >= min(days, 60):
        return df

    if market == 'cn':
        df = _download_akshare(symbol, days)
        if df is not None and not df.empty:
            logger.info(f"使用 akshare 数据: {symbol}, {len(df)} 条")
            _write_cache(symbol, market, df)
            return df

    df = _download_yfinance(symbol, days)
    if df is not None and not df.empty:
        logger.info(f"使用 yfinance 数据: {symbol}, {len(df)} 条")
        _write_cache(symbol, market, df)
        return df

    raise DataSourceError(f"无法获取 {symbol} 的数据（已尝试本地 CSV / 当日缓存 / akshare / yfinance）")


def download_range(symbol: str, start_date: str, end_date: str,
                   market: str = 'cn') -> pd.DataFrame:
    """下载指定日期范围的数据（用于验证）

    Args:
        symbol: 股票代码
        start_date: 开始日期 'YYYY-MM-DD'
        end_date: 结束日期 'YYYY-MM-DD'
        market: 'cn' 或 'us'

    Returns:
        标准化的 DataFrame
    """
    # 先尝试 yfinance（支持日期范围）
    try:
        import yfinance as yf
        ticker = symbol.replace('.SH', '.SS').replace('.SZ', '.SZ')
        df = yf.download(ticker, start=start_date, end=end_date, progress=False)
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [str(c).lower() for c in df.columns]
            df = df.rename(columns={'adj close': 'close'})
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            df.index.name = 'date'
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=['open', 'high', 'low', 'close'])
            return df
    except Exception as e:
        logger.warning(f"yfinance 范围下载失败: {e}")

    # A 股尝试 akshare
    if market == 'cn':
        try:
            import akshare as ak
            code = symbol.split('.')[0]
            df = ak.stock_zh_a_hist(
                symbol=code, period='daily',
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust='qfq'
            )
            if df is not None and not df.empty:
                # 中文列名必须显式映射（lower() 不会翻译中文）
                df = _standardize_akshare_hist(df)
                if df is not None:
                    return df
        except Exception as e:
            logger.warning(f"akshare 范围下载失败: {e}")

    raise DataSourceError(f"无法获取 {symbol} 在 {start_date} ~ {end_date} 的数据")
