"""Report generator - 全部通过大模型+Skill知识生成报告。"""

from typing import Dict, Any, Optional
from utils.llm_client import DeepSeekClient


class ReportGenerator:
    """报告生成器 - 所有报告通过大模型+Skill知识生成。"""

    def __init__(self, api_key: Optional[str] = None):
        self.client = DeepSeekClient(api_key=api_key)

    def generate(self, results: Dict[str, Any]) -> str:
        """通过大模型生成专业技术分析报告。"""
        return self.client.generate_report(results)
