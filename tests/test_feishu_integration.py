"""飞书集成模块测试

使用 mock 验证 lark-cli 命令生成与结果解析，不调用真实飞书 API。
"""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

os.environ['DEEPSEEK_API_KEY'] = 'test-key'


class TestFeishuIntegration:
    """测试飞书集成功能"""

    @pytest.fixture
    def feishu(self, tmp_path):
        """创建 FeishuIntegration 实例，使用临时缓存目录"""
        from utils.feishu_integration import FeishuIntegration

        # 使用临时目录避免污染真实缓存
        with patch.object(FeishuIntegration, '_ensure_folder'), \
             patch.object(FeishuIntegration, '_ensure_records_doc'):
            instance = FeishuIntegration(folder_name="测试文件夹")
            instance.doc_cache_dir = str(tmp_path / 'feishu_doc_cache')
            instance.folder_token = "test_folder_token"
            instance.records_doc_token = "test_records_token"
            instance.stock_docs = {}
            return instance

    def test_extract_json_simple(self, feishu):
        """测试从 lark-cli 输出中提取 JSON"""
        text = 'some log\n{"ok": true, "data": {"doc_id": "abc123"}}\nmore log'
        result = feishu._extract_json(text, text.find('{'))
        assert result == '{"ok": true, "data": {"doc_id": "abc123"}}'

    def test_extract_json_nested(self, feishu):
        """测试提取嵌套 JSON"""
        text = '{"outer": {"inner": "value"}}'
        result = feishu._extract_json(text, 0)
        assert json.loads(result)['outer']['inner'] == 'value'

    def test_run_parses_stdout_json(self, feishu):
        """测试 _run 正确解析 stdout 中的 JSON"""
        mock_result = MagicMock()
        mock_result.stdout = '{"ok": true, "data": {"doc_id": "doc_abc"}}'
        mock_result.stderr = ''

        with patch('subprocess.run', return_value=mock_result):
            result = feishu._run('lark-cli docs +create --title TEST')

        assert result['ok'] is True
        assert result['data']['doc_id'] == 'doc_abc'

    def test_run_falls_back_to_stderr_json(self, feishu):
        """测试 stdout 解析失败时回退到 stderr"""
        mock_result = MagicMock()
        mock_result.stdout = 'not json'
        mock_result.stderr = 'some log\n{"ok": true, "data": {"doc_id": "doc_def"}}'

        with patch('subprocess.run', return_value=mock_result):
            result = feishu._run('lark-cli docs +create --title TEST')

        assert result['ok'] is True
        assert result['data']['doc_id'] == 'doc_def'

    def test_create_stock_doc_command(self, feishu):
        """测试创建股票文档时生成的 lark-cli 命令"""
        mock_result = MagicMock()
        mock_result.stdout = '{"ok": true, "data": {"doc_id": "new_doc_123"}}'
        mock_result.stderr = ''

        with patch('subprocess.run', return_value=mock_result) as mock_run, \
             patch.object(feishu, '_write_temp_markdown', return_value='feishu_tmp.md'):
            doc_token = feishu.create_stock_doc('AAPL', content='# AAPL 分析')

        assert doc_token == 'new_doc_123'
        assert feishu.stock_docs['AAPL'] == 'new_doc_123'

        # 验证命令包含关键参数
        call_args = mock_run.call_args[0][0]
        assert 'lark-cli docs +create' in call_args
        assert 'AAPL 技术分析' in call_args
        assert 'test_folder_token' in call_args
        assert '@feishu_tmp.md' in call_args

    def test_append_to_stock_doc_uses_cached_token(self, feishu):
        """测试追加内容时使用缓存的 doc_token"""
        feishu.stock_docs['AAPL'] = 'cached_doc_456'

        mock_result = MagicMock()
        mock_result.stdout = '{"ok": true}'
        mock_result.stderr = ''

        with patch('subprocess.run', return_value=mock_result) as mock_run, \
             patch.object(feishu, '_write_temp_markdown', return_value='feishu_tmp.md'):
            success = feishu.append_to_stock_doc('AAPL', content='## 追加内容')

        assert success is True
        call_args = mock_run.call_args[0][0]
        assert 'cached_doc_456' in call_args
        assert '--mode append' in call_args

    def test_get_stock_doc_url(self, feishu):
        """测试文档 URL 生成"""
        feishu.stock_docs['AAPL'] = 'doc_abc'
        url = feishu.get_stock_doc_url('AAPL')
        assert url == 'https://www.feishu.cn/docx/doc_abc'

    def test_read_doc_content_command(self, feishu):
        """测试读取飞书文档内容命令"""
        mock_result = MagicMock()
        mock_result.stdout = '{"ok": true, "data": "文档内容"}'
        mock_result.stderr = ''

        with patch('subprocess.run', return_value=mock_result) as mock_run:
            result = feishu.read_doc_content('https://www.feishu.cn/docx/AbC123xyz')

        assert result == '文档内容'
        call_args = mock_run.call_args[0][0]
        assert 'lark-cli docs +fetch' in call_args
        assert 'AbC123xyz' in call_args

    def test_list_stock_docs(self, feishu):
        """测试列出股票文档"""
        feishu.stock_docs = {
            'AAPL': 'doc_a',
            'TSLA': 'doc_b'
        }
        urls = feishu.list_stock_docs()
        assert urls['AAPL'] == 'https://www.feishu.cn/docx/doc_a'
        assert urls['TSLA'] == 'https://www.feishu.cn/docx/doc_b'

    def test_prepend_to_tracking_section_no_cache(self, feishu):
        """测试没有本地缓存时尝试从飞书读取"""
        feishu.stock_docs['AAPL'] = 'doc_abc'

        with patch.object(feishu, 'read_doc_content', return_value='## 后续跟踪\n旧记录'), \
             patch.object(feishu, 'overwrite_doc', return_value=True) as mock_overwrite, \
             patch.object(feishu, 'save_doc_cache') as mock_save:
            success = feishu.prepend_to_tracking_section('AAPL', '## 新跟踪\n新记录')

        assert success is True
        mock_overwrite.assert_called_once()
        mock_save.assert_called_once()

    def test_api_enables_feishu_sync(self):
        """测试 assistant API 中启用飞书同步的接口"""
        from api import TechnicalAnalysisAssistant

        with patch('utils.feishu_integration.FeishuIntegration') as MockFeishu:
            mock_instance = MagicMock()
            mock_instance.folder_token = 'folder_123'
            mock_instance.get_folder_url.return_value = 'https://my.feishu.cn/drive/folder/folder_123'
            MockFeishu.return_value = mock_instance

            assistant = TechnicalAnalysisAssistant(api_key='test-key')
            assistant.enable_feishu()

            assert assistant._feishu_enabled is True
            mock_instance.get_folder_url.assert_called_once()

    def test_analyze_saves_record_with_feishu_disabled_by_default(self):
        """测试默认情况下不启用飞书同步"""
        from api import TechnicalAnalysisAssistant

        assistant = TechnicalAnalysisAssistant(api_key='test-key', enable_feishu=False)
        assert assistant._feishu_enabled is False
