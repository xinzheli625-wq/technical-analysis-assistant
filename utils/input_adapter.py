"""Input adapter: normalizes all input types. Screenshot analysis uses LLM Vision + Skill context."""

from typing import Dict, List, Any, Optional
import pandas as pd


class InputAdapter:
    """输入适配器 - 所有输入归一化。截图通过LLM Vision + Skill分析。"""

    COLUMN_ALIASES = {
        'date': ['date', 'Date', 'DATE', '日期', '时间', 'datetime', 'timestamp'],
        'open': ['open', 'Open', 'OPEN', '开盘', '开盘价'],
        'high': ['high', 'High', 'HIGH', '最高', '最高价', '最高價'],
        'low': ['low', 'Low', 'LOW', '最低', '最低价', '最低價'],
        'close': ['close', 'Close', 'CLOSE', '收盘', '收盘价', '收盤價'],
        'volume': ['volume', 'Volume', 'VOLUME', 'vol', '成交量', '成交额']
    }

    def detect_column_mapping(self, df: pd.DataFrame) -> Dict[str, str]:
        """Auto-detect DataFrame column mapping."""
        mapping = {}
        df_columns = list(df.columns)
        for standard_field, aliases in self.COLUMN_ALIASES.items():
            for col in df_columns:
                if col in aliases:
                    mapping[standard_field] = col
                    break
        return mapping

    def normalize_excel(self, df: pd.DataFrame, symbol: str, market: str = "US",
                        timeframe: str = "daily") -> Dict[str, Any]:
        """Convert Excel/CSV to standard format."""
        mapping = self.detect_column_mapping(df)

        if 'date' not in mapping:
            raise ValueError(f"Could not detect date column. Columns: {list(df.columns)}")
        if 'close' not in mapping:
            raise ValueError(f"Could not detect close price column. Columns: {list(df.columns)}")

        records = []
        for _, row in df.iterrows():
            record = {
                'date': str(row[mapping.get('date', 'date')]),
                'open': float(row[mapping.get('open', mapping.get('close'))]) if mapping.get('open') else None,
                'high': float(row[mapping.get('high', mapping.get('close'))]) if mapping.get('high') else None,
                'low': float(row[mapping.get('low', mapping.get('close'))]) if mapping.get('low') else None,
                'close': float(row[mapping['close']]),
                'volume': float(row[mapping.get('volume', 'volume')]) if mapping.get('volume') else None,
            }
            records.append(record)

        closes = [r['close'] for r in records if r['close'] is not None]
        volumes = [r['volume'] for r in records if r['volume'] is not None]

        metadata = {
            'current_price': closes[-1] if closes else None,
            'period_high': max(closes) if closes else None,
            'period_low': min(closes) if closes else None,
            'avg_volume': sum(volumes) / len(volumes) if volumes else None,
            'data_points': len(records)
        }

        return {
            'symbol': symbol,
            'market': market,
            'timeframe': timeframe,
            'input_type': 'excel',
            'data': records,
            'metadata': metadata
        }

    def normalize_api_data(self, raw_data: List[Dict], symbol: str, market: str = "US") -> Dict[str, Any]:
        """Normalize API data."""
        return self.normalize_excel(pd.DataFrame(raw_data), symbol, market)

    def process_screenshot(self, image_path: str, symbol: str, market: str = "US",
                           timeframe: str = "daily") -> Dict[str, Any]:
        """Process screenshot using LLM Vision + Skill knowledge."""
        from utils.llm_client import DeepSeekClient

        client = DeepSeekClient()
        vision_result = client.analyze_screenshot(image_path)

        return {
            'symbol': symbol,
            'market': market,
            'timeframe': timeframe,
            'input_type': 'screenshot',
            'data': [],
            'metadata': {
                'image_path': image_path,
                'llm_vision_analysis': vision_result,
                'precision_note': '分析基于LLM视觉识别+Skill知识体系',
                'vision_analysis_status': 'success' if not vision_result.get('parse_error') else 'partial'
            }
        }


def normalize_excel(df: pd.DataFrame, symbol: str, market: str = "US", timeframe: str = "daily") -> Dict[str, Any]:
    """Convenience function."""
    adapter = InputAdapter()
    return adapter.normalize_excel(df, symbol, market, timeframe)
