"""Skill 提取流程全面测试

覆盖从书籍/材料/自然语言提取技术分析 Skill 的完整流程，
重点验证 OCR、文本清洗、分段、提取、修改、保存、激活等环节的触发条件。

对应代码：
- api.py: upload_skill_book / set_book_segments / extract_book_segment /
  modify_extracted_skill / remove_extracted_skill / save_book_skills /
  upload_skill_from_feishu / upload_skill（便捷函数）
- utils/evolution_engine.py: is_scanned_pdf / parse_pdf / parse_pdf_ocr /
  parse_word / clean_text / create_segments / get_segment_text /
  update_skill_from_natural_language / activate_rule / _convert_to_methodology_format
"""

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ['DEEPSEEK_API_KEY'] = 'test-key'

import api  # noqa: E402


@pytest.fixture(autouse=True)
def reset_assistant_singleton():
    """api.assistant() 是单例，每个测试前重置，避免 mock 状态泄漏"""
    api._assistant = None
    yield
    api._assistant = None


def make_assistant():
    from api import assistant
    return assistant()


class FakePdfDoc:
    """模拟 fitz 打开的 PDF 文档，每页返回预设文本"""

    def __init__(self, pages):
        self.pages = pages
        self.closed = False

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, idx):
        page = MagicMock()
        page.get_text = MagicMock(return_value=self.pages[idx])
        return page

    def close(self):
        self.closed = True


LONG_TEXT = '这是一段足够长的文本，用于模拟文本版 PDF 的页面内容。' * 3  # > 50 字符
SHORT_TEXT = '短文本'  # <= 50 字符，视为无文本层


class TestScannedPdfDetection:
    """测试扫描版 PDF 检测逻辑（is_scanned_pdf）

    判定规则（utils/evolution_engine.py: is_scanned_pdf）：
    - 采样前 3 页；总页数 > 50 加采中间页；> 100 再加采 3/4 处页
    - 采样页中文本长度 > 50 字符才算"有文本层"
    - 有文本层的采样页占比 < 20% → 判定为扫描版（触发 OCR）
    - 任何异常 → 默认按文本版处理（不触发 OCR）
    """

    def test_all_pages_no_text_is_scanned(self):
        """采样页都没有文本 → 扫描版（应触发 OCR）"""
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        doc = FakePdfDoc([''] * 10)

        with patch('fitz.open', return_value=doc):
            assert engine.is_scanned_pdf('fake.pdf') is True

    def test_all_pages_with_text_is_not_scanned(self):
        """采样页都有文本 → 文本版（不触发 OCR）"""
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        doc = FakePdfDoc([LONG_TEXT] * 10)

        with patch('fitz.open', return_value=doc):
            assert engine.is_scanned_pdf('fake.pdf') is False

    def test_short_text_counts_as_no_text_layer(self):
        """文本 <= 50 字符视为无文本层（如扫描件里的页码水印）"""
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        doc = FakePdfDoc([SHORT_TEXT] * 10)

        with patch('fitz.open', return_value=doc):
            assert engine.is_scanned_pdf('fake.pdf') is True

    def test_boundary_exactly_20_percent_is_not_scanned(self):
        """边界：恰好 20% 采样页有文本（5 页中 1 页）→ 不是扫描版

        判定条件是 < 0.2（严格小于），所以 1/5 = 0.2 时仍按文本版处理。
        大书（>100 页）会采样 5 页：[0, 1, 2, total//2, total*3//4]
        """
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        pages = [''] * 200
        pages[0] = LONG_TEXT  # 仅第 1 页有文本 → 1/5 = 20%
        doc = FakePdfDoc(pages)

        with patch('fitz.open', return_value=doc):
            assert engine.is_scanned_pdf('fake.pdf') is False

    def test_large_book_samples_five_pages(self):
        """>100 页的书采样 5 页：前 3 页 + 中间页 + 3/4 处页

        只有中间页（total//2）有文本时也能被采到，避免漏判。
        """
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        pages = [''] * 200
        pages[100] = LONG_TEXT  # total//2 = 100
        doc = FakePdfDoc(pages)

        with patch('fitz.open', return_value=doc):
            assert engine.is_scanned_pdf('fake.pdf') is False

    def test_medium_book_samples_middle_page(self):
        """>50 页的书加采中间页"""
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        pages = [''] * 60
        pages[30] = LONG_TEXT  # total//2 = 30，1/4 = 25% → 文本版
        doc = FakePdfDoc(pages)

        with patch('fitz.open', return_value=doc):
            assert engine.is_scanned_pdf('fake.pdf') is False

    def test_defaults_to_text_on_exception(self):
        """检测异常时默认按文本版处理（不触发 OCR，走 parse_pdf 回退）"""
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()

        with patch('fitz.open', side_effect=Exception('cannot open')):
            assert engine.is_scanned_pdf('broken.pdf') is False


class TestUploadSkillBookDecision:
    """测试 upload_skill_book 中按文件类型/扫描检测的路由决策

    路由规则（api.py: upload_skill_book）：
    - .pdf 且 is_scanned_pdf=True  → parse_pdf_ocr（OCR，默认只识别前 100 页）
    - .pdf 且 is_scanned_pdf=False → parse_pdf（pdfplumber 直接提取）
    - 其他后缀（.docx 等）          → parse_word
    - auto_extract=True            → 旧模式整本一次性提取
    """

    def _make_mock_evolution(self, is_scanned):
        mock_evo = MagicMock()
        mock_evo.is_scanned_pdf = MagicMock(return_value=is_scanned)
        mock_evo.parse_pdf = MagicMock(return_value='text content')
        mock_evo.parse_pdf_ocr = MagicMock(return_value='ocr content')
        mock_evo.parse_word = MagicMock(return_value='word content')
        mock_evo.clean_text = MagicMock(side_effect=lambda t: t)
        return mock_evo

    def test_text_pdf_uses_parse_pdf_not_ocr(self):
        """文本版 PDF：调用 parse_pdf，绝不调用 OCR"""
        a = make_assistant()
        mock_evo = self._make_mock_evolution(is_scanned=False)
        a.evolution = mock_evo

        result = a.upload_skill_book('book.pdf', auto_extract=False)

        mock_evo.is_scanned_pdf.assert_called_once_with('book.pdf')
        mock_evo.parse_pdf.assert_called_once_with('book.pdf')
        mock_evo.parse_pdf_ocr.assert_not_called()
        assert result['status'] == 'loaded'

    def test_scanned_pdf_triggers_ocr(self):
        """扫描版 PDF：必须触发 parse_pdf_ocr，且不调用 parse_pdf"""
        a = make_assistant()
        mock_evo = self._make_mock_evolution(is_scanned=True)
        a.evolution = mock_evo

        result = a.upload_skill_book('book.pdf', auto_extract=False)

        mock_evo.is_scanned_pdf.assert_called_once_with('book.pdf')
        mock_evo.parse_pdf.assert_not_called()
        mock_evo.parse_pdf_ocr.assert_called_once()
        assert result['status'] == 'loaded'

    def test_scanned_pdf_ocr_defaults_to_first_100_pages(self):
        """扫描版 PDF 默认只 OCR 前 100 页（page_start=1, page_end=100）

        这是防止整本 OCR 太慢的保护措施，用户可覆盖页码范围。
        """
        a = make_assistant()
        mock_evo = self._make_mock_evolution(is_scanned=True)
        a.evolution = mock_evo

        a.upload_skill_book('book.pdf', auto_extract=False)

        mock_evo.parse_pdf_ocr.assert_called_once_with(
            'book.pdf', page_start=1, page_end=100)

    def test_word_file_uses_parse_word_and_skips_scan_detection(self):
        """Word 文件：直接 parse_word，不做扫描检测（Word 没有扫描版概念）"""
        a = make_assistant()
        mock_evo = self._make_mock_evolution(is_scanned=False)
        a.evolution = mock_evo

        result = a.upload_skill_book('book.docx', auto_extract=False)

        mock_evo.is_scanned_pdf.assert_not_called()
        mock_evo.parse_word.assert_called_once_with('book.docx')
        mock_evo.parse_pdf.assert_not_called()
        mock_evo.parse_pdf_ocr.assert_not_called()
        assert result['status'] == 'loaded'

    def test_clean_text_always_applied(self):
        """无论哪种解析路径，都必须经过 clean_text 清洗"""
        a = make_assistant()
        mock_evo = self._make_mock_evolution(is_scanned=True)
        a.evolution = mock_evo

        a.upload_skill_book('book.pdf', auto_extract=False)

        mock_evo.clean_text.assert_called_once_with('ocr content')

    def test_loaded_state_stored_for_segmentation(self):
        """加载后应缓存全文，等待 set_book_segments 设置分段"""
        a = make_assistant()
        mock_evo = self._make_mock_evolution(is_scanned=False)
        a.evolution = mock_evo

        result = a.upload_skill_book('book.pdf', auto_extract=False)

        assert a._pending_book_text == 'text content'
        assert a._pending_book_file == 'book.pdf'
        assert a._pending_book_structure is None
        assert result['total_chars'] == len('text content')

    def test_auto_extract_uses_legacy_one_shot(self):
        """auto_extract=True 走旧模式：整本一次性提取"""
        a = make_assistant()
        mock_evo = self._make_mock_evolution(is_scanned=False)
        mock_evo.update_skill_from_book = MagicMock(
            return_value={'status': 'processed', 'rules_extracted': 3})
        a.evolution = mock_evo

        result = a.upload_skill_book('book.pdf', auto_extract=True)

        mock_evo.update_skill_from_book.assert_called_once_with('book.pdf', 'pdf')
        assert result['status'] == 'processed'


class TestTextCleaning:
    """测试文本清洗（clean_text）

    清洗规则（utils/evolution_engine.py: clean_text）：
    - 去除纯数字行（页码）
    - 去除"第 X 页"、"Page X"格式的页码行
    - 去除连续重复行（跨页重复页眉）
    - 连续多个空行压缩为一个空行
    """

    def test_removes_pure_number_page_numbers(self):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        raw = "第一章\n\n1\n\n这是正文。\n\n2\n\n第二章"
        cleaned = engine.clean_text(raw)
        assert '1' not in cleaned.split('\n')
        assert '2' not in cleaned.split('\n')
        assert '这是正文' in cleaned

    def test_removes_chinese_page_markers(self):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        raw = "正文\n\n第 5 页\n\n更多正文"
        cleaned = engine.clean_text(raw)
        assert '第 5 页' not in cleaned

    def test_removes_english_page_markers(self):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        raw = "content\n\nPage 42\n\nmore content"
        cleaned = engine.clean_text(raw)
        assert 'Page 42' not in cleaned
        assert 'more content' in cleaned

    def test_removes_consecutive_duplicate_headers(self):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        raw = "技术分析\n重复标题\n重复标题\n内容一"
        cleaned = engine.clean_text(raw)
        lines = [line for line in cleaned.split('\n') if line]
        assert lines.count('重复标题') == 1

    def test_preserves_non_consecutive_duplicates(self):
        """非连续的重复行（如正文中重复出现的术语行）不应被去除"""
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        raw = "要点\n内容一\n\n要点\n内容二"
        cleaned = engine.clean_text(raw)
        lines = [line for line in cleaned.split('\n') if line]
        assert lines.count('要点') == 2

    def test_collapses_multiple_blank_lines(self):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        raw = "段落一\n\n\n\n\n段落二"
        cleaned = engine.clean_text(raw)
        assert '\n\n\n' not in cleaned
        assert '段落一' in cleaned and '段落二' in cleaned


class TestSegmentCreation:
    """测试分段功能（create_segments / get_segment_text）

    分段机制：
    - 每段用 start_marker / end_marker（原文中的整行文本）定位
    - 未指定 end_marker 时，自动用下一段的 start_marker 作为结束
    - marker 匹配是整行精确匹配（strip 后比较）
    """

    def test_create_segments_basic(self):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        text = "第一章\n内容一\n\n第二章\n内容二"
        config = [
            {'segment_id': 1, 'title': '第一章', 'start_marker': '第一章'},
            {'segment_id': 2, 'title': '第二章', 'start_marker': '第二章'},
        ]
        structure = engine.create_segments(text, config)

        assert len(structure['segments']) == 2
        assert structure['segments'][0]['segment_id'] == 1
        assert '第一章' in structure['segments'][0]['summary']

    def test_end_marker_inferred_from_next_segment(self):
        """未指定 end_marker 时，自动用下一段 start_marker 作为本段结束"""
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        text = "第一章\n内容一\n\n第二章\n内容二"
        config = [
            {'segment_id': 1, 'title': '第一章', 'start_marker': '第一章'},
            {'segment_id': 2, 'title': '第二章', 'start_marker': '第二章'},
        ]
        structure = engine.create_segments(text, config)

        # 段1 的 end_marker 应被推断为"第二章"
        assert structure['segments'][0]['end_marker'] == '第二章'
        seg1 = engine.get_segment_text(text, 1, structure)
        assert '内容一' in seg1
        assert '内容二' not in seg1

    def test_get_segment_text_with_explicit_end_marker(self):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        text = "第一章\n内容一\n\n第二章\n内容二"
        config = [
            {'segment_id': 1, 'title': '第一章', 'start_marker': '第一章',
             'end_marker': '第二章'},
            {'segment_id': 2, 'title': '第二章', 'start_marker': '第二章'},
        ]
        structure = engine.create_segments(text, config)

        seg1 = engine.get_segment_text(text, 1, structure)
        assert '第一章' in seg1
        assert '内容一' in seg1
        assert '第二章' not in seg1

    def test_get_segment_text_invalid_id_returns_empty(self):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        text = "第一章\n内容一"
        config = [{'segment_id': 1, 'title': '第一章', 'start_marker': '第一章'}]
        structure = engine.create_segments(text, config)

        assert engine.get_segment_text(text, 0, structure) == ''
        assert engine.get_segment_text(text, 99, structure) == ''

    def test_get_segment_text_marker_not_found_returns_empty(self):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        text = "第一章\n内容一"
        structure = {'segments': [
            {'segment_id': 1, 'start_marker': '不存在的标记', 'end_marker': ''}
        ]}
        assert engine.get_segment_text(text, 1, structure) == ''


class TestExtractBookSegment:
    """测试逐段 LLM 提取（extract_book_segment）

    触发条件：
    - 必须先 upload_skill_book 加载书籍，否则返回 error
    - segment_id 必须有效，否则返回 error
    - 提取结果缓存到 _last_extracted_skills 供本地修改/保存
    - user_instruction 原样传给 LLM，指导提取重点
    """

    def _prepare_book(self, a):
        a._pending_book_text = "第一章 趋势\n趋势线画法内容\n\n第二章 形态\n锤子线内容"
        a.set_book_segments([
            {'segment_id': 1, 'title': '趋势', 'start_marker': '第一章 趋势'},
            {'segment_id': 2, 'title': '形态', 'start_marker': '第二章 形态'},
        ])

    def test_error_when_no_book_loaded(self):
        a = make_assistant()
        result = a.extract_book_segment(1)
        assert 'error' in result

    def test_error_when_segment_invalid(self):
        a = make_assistant()
        self._prepare_book(a)
        result = a.extract_book_segment(99)
        assert 'error' in result

    def test_extracts_segment_text_and_caches_result(self):
        a = make_assistant()
        self._prepare_book(a)

        mock_client = MagicMock()
        mock_client.extract_skills_from_segment.return_value = {
            'rules': [{'name': '趋势线突破', 'category': 'trend'}],
            'summary': '提取了 1 条趋势 Skill',
        }
        a.analyzer.client = mock_client

        result = a.extract_book_segment(1, user_instruction='重点提取趋势线')

        # 传给 LLM 的应该是段1的原文，而不是全书
        sent_text, sent_instruction = \
            mock_client.extract_skills_from_segment.call_args[0]
        assert '趋势线画法内容' in sent_text
        assert '锤子线内容' not in sent_text
        assert sent_instruction == '重点提取趋势线'

        # 结果缓存供本地修改/保存
        assert a._last_extracted_skills == result['rules']
        assert a._last_extracted_segment_id == 1

    def test_parse_error_returned_without_caching(self):
        """LLM 返回解析失败时，原样返回，不污染缓存"""
        a = make_assistant()
        self._prepare_book(a)

        mock_client = MagicMock()
        mock_client.extract_skills_from_segment.return_value = {
            'parse_error': True, 'raw': 'broken json'}
        a.analyzer.client = mock_client

        result = a.extract_book_segment(1)
        assert result.get('parse_error') is True
        assert not hasattr(a, '_last_extracted_skills')


class TestExtractedSkillManagement:
    """测试提取后的 Skill 本地管理（修改/删除/保存，零 API 消耗）"""

    @pytest.fixture
    def assistant_with_extracted(self):
        a = make_assistant()
        a._last_extracted_skills = [
            {'name': '量价突破法', 'category': 'volume_price',
             'core_idea': '放量突破确认',
             'reference_data': {'阈值': '2倍量'}},
            {'name': 'RSI超买', 'category': 'indicators',
             'core_idea': 'RSI>70 超买'},
        ]
        a._last_extracted_segment_id = 1
        return a

    def test_modify_nested_field(self, assistant_with_extracted):
        """支持点号嵌套字段修改，如 reference_data.阈值"""
        a = assistant_with_extracted
        success = a.modify_extracted_skill(0, 'reference_data.阈值', '3倍量')

        assert success is True
        assert a._last_extracted_skills[0]['reference_data']['阈值'] == '3倍量'

    def test_modify_flat_field(self, assistant_with_extracted):
        a = assistant_with_extracted
        success = a.modify_extracted_skill(1, 'core_idea', 'RSI>80 超买')

        assert success is True
        assert a._last_extracted_skills[1]['core_idea'] == 'RSI>80 超买'

    def test_modify_invalid_index_returns_false(self, assistant_with_extracted):
        a = assistant_with_extracted
        assert a.modify_extracted_skill(99, 'name', 'x') is False
        assert a.modify_extracted_skill(-1, 'name', 'x') is False

    def test_modify_without_cache_returns_false(self):
        a = make_assistant()
        assert a.modify_extracted_skill(0, 'name', 'x') is False

    def test_remove_extracted_skill(self, assistant_with_extracted):
        a = assistant_with_extracted
        success = a.remove_extracted_skill(1)

        assert success is True
        assert len(a._last_extracted_skills) == 1
        assert a._last_extracted_skills[0]['name'] == '量价突破法'

    def test_remove_invalid_index_returns_false(self, assistant_with_extracted):
        a = assistant_with_extracted
        assert a.remove_extracted_skill(99) is False
        assert len(a._last_extracted_skills) == 2

    def test_save_book_skills_to_pending_queue(self, assistant_with_extracted):
        """保存的 Skill 必须进入 pending 队列（不直接激活）"""
        a = assistant_with_extracted

        with patch('utils.rule_index.RuleIndex') as MockRuleIndex:
            mock_index = MagicMock()
            mock_index.add_rule.return_value = 'rule_abc123'
            MockRuleIndex.return_value = mock_index

            result = a.save_book_skills()

            assert result['status'] == 'saved'
            assert result['count'] == 2
            assert all(s['status'] == 'pending' for s in result['skills'])
            # 必须 auto_activate=False
            for call in mock_index.add_rule.call_args_list:
                assert call[1]['auto_activate'] is False

    def test_save_without_skills_returns_error(self):
        a = make_assistant()
        result = a.save_book_skills()
        assert 'error' in result


class TestConvertToMethodologyFormat:
    """测试 Skill 格式转换（旧格式 → 教材格式，并补全 trigger/signal）"""

    def test_convert_old_format(self):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        old_rule = {
            'rule_type': 'indicators',
            'name': 'RSI Oversold',
            'definition': 'RSI < 30 means oversold',
            'conditions': ['RSI < 30'],
        }
        converted = engine._convert_to_methodology_format(old_rule)

        assert converted['category'] == 'indicators'
        assert converted['name'] == 'RSI Oversold'
        assert converted['core_idea'] == 'RSI < 30 means oversold'
        assert converted['analysis_steps'] == ['RSI < 30']
        assert 'trigger' in converted
        assert 'signal' in converted

    def test_convert_new_format_preserved(self):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        new_rule = {
            'name': '量价突破',
            'category': 'volume_price',
            'core_idea': '放量突破',
            'analysis_steps': ['识别阻力', '放量突破'],
        }
        converted = engine._convert_to_methodology_format(new_rule)

        assert converted['core_idea'] == '放量突破'
        assert converted['analysis_steps'] == ['识别阻力', '放量突破']
        assert 'trigger' in converted
        assert 'signal' in converted


class TestActivateRule:
    """测试 Skill 激活：激活后必须重新加载 Skill 知识库才能参与分析"""

    def test_activate_rule_triggers_kb_reload(self):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()

        with patch('utils.rule_index.RuleIndex') as MockRuleIndex, \
             patch('utils.skill_knowledge.get_skill_kb') as mock_get_kb:
            mock_index = MagicMock()
            mock_index.activate_rule.return_value = True
            MockRuleIndex.return_value = mock_index

            result = engine.activate_rule('rule_abc')

            assert result['status'] == 'activated'
            mock_get_kb.return_value.reload.assert_called_once()

    def test_activate_missing_rule_returns_error(self):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()

        with patch('utils.rule_index.RuleIndex') as MockRuleIndex:
            mock_index = MagicMock()
            mock_index.activate_rule.return_value = False
            MockRuleIndex.return_value = mock_index

            result = engine.activate_rule('rule_missing')
            assert result['status'] == 'error'


class TestNaturalLanguageSkill:
    """测试从自然语言提取 Skill"""

    def test_update_skill_from_natural_language(self):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()

        with patch('utils.llm_client.DeepSeekClient') as MockClient, \
             patch('utils.rule_index.RuleIndex') as MockRuleIndex:
            mock_client = MagicMock()
            mock_client.parse_natural_language_instruction.return_value = {
                'intent': 'add_pattern',
                'rule_name': '双底突破',
                'description': '价格形成双底后突破颈线买入',
                'conditions': [{'indicator': 'pattern', 'operator': '=',
                                'value': 'double_bottom'}]
            }
            MockClient.return_value = mock_client

            mock_index = MagicMock()
            mock_index.add_rule.return_value = 'rule_nl_123'
            MockRuleIndex.return_value = mock_index

            result = engine.update_skill_from_natural_language(
                "当价格形成双底并突破颈线时买入")

            assert result['status'] == 'pending_review'
            assert result['rule_id'] == 'rule_nl_123'


class TestUploadSkillConvenience:
    """测试 api.upload_skill 便捷函数（回归：activate kwarg 曾导致 TypeError）"""

    def test_file_path_with_activate(self):
        mock_result = {
            'status': 'processed',
            'pending_activation': ['rule_1', 'rule_2'],
        }
        a = make_assistant()
        a.upload_skill_book = MagicMock(return_value=mock_result)
        a.activate_skill = MagicMock(return_value={'status': 'activated'})

        with patch('api.assistant', return_value=a):
            result = api.upload_skill(file_path='book.pdf', activate=True)

        a.upload_skill_book.assert_called_once_with('book.pdf', auto_extract=True)
        assert a.activate_skill.call_count == 2
        assert result['status'] == 'processed'

    def test_file_path_without_activate(self):
        mock_result = {'status': 'processed',
                       'pending_activation': ['rule_1']}
        a = make_assistant()
        a.upload_skill_book = MagicMock(return_value=mock_result)
        a.activate_skill = MagicMock()

        with patch('api.assistant', return_value=a):
            api.upload_skill(file_path='book.pdf', activate=False)

        a.activate_skill.assert_not_called()

    def test_text_path(self):
        a = make_assistant()
        a.upload_skill_text = MagicMock(
            return_value={'status': 'pending_review', 'rule_id': 'rule_x'})
        a.activate_skill = MagicMock(return_value={'status': 'activated'})

        with patch('api.assistant', return_value=a):
            api.upload_skill(text='双底突破买入', activate=True)

        a.upload_skill_text.assert_called_once_with('双底突破买入')
        a.activate_skill.assert_called_once_with('rule_x')

    def test_no_input_raises(self):
        with pytest.raises(ValueError):
            api.upload_skill()


class TestUploadSkillFromFeishu:
    """测试从飞书文档导入 Skill（与书籍上传走同一套分段提取流程）"""

    def test_feishu_content_cleaned_and_loaded(self):
        a = make_assistant()

        mock_feishu = MagicMock()
        mock_feishu.read_doc_content.return_value = \
            "第一章 趋势\n\n1\n\n趋势线内容"
        with patch('utils.feishu_integration.FeishuIntegration',
                   return_value=mock_feishu):
            result = a.upload_skill_from_feishu('https://xxx.feishu.cn/docx/abc')

        assert result['status'] == 'loaded'
        # 清洗后页码"1"应被去除
        assert '\n1\n' not in a._pending_book_text
        assert '趋势线内容' in a._pending_book_text


class TestBookRegistry:
    """测试书籍处理注册表（防止同一本书重复提取）

    注意：注册表路径硬编码为 data/book_registry.json，
    测试前备份、测试后还原，避免污染真实数据。
    """

    REGISTRY = 'data/book_registry.json'

    @pytest.fixture
    def preserve_registry(self):
        backup = None
        if os.path.exists(self.REGISTRY):
            with open(self.REGISTRY, 'rb') as f:
                backup = f.read()
        yield
        if backup is not None:
            with open(self.REGISTRY, 'wb') as f:
                f.write(backup)
        elif os.path.exists(self.REGISTRY):
            os.remove(self.REGISTRY)

    def test_is_book_processed_and_persistence(self, preserve_registry, tmp_path):
        from utils.evolution_engine import EvolutionEngine

        if os.path.exists(self.REGISTRY):
            os.remove(self.REGISTRY)

        test_file = str(tmp_path / 'book.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write('test content')

        engine = EvolutionEngine()
        assert engine.is_book_processed(test_file) is False

        file_hash = engine._calculate_file_hash(test_file)
        engine.processed_books[file_hash] = '2026-01-01T00:00:00'
        engine._save_book_registry()

        # 新实例从磁盘加载后仍认为已处理（持久化生效）
        engine2 = EvolutionEngine()
        assert engine2.is_book_processed(test_file) is True


class TestParseFallbacks:
    """测试解析失败回退：专用库解析失败时回退到直接读文件，保证不中断流程"""

    def test_parse_pdf_fallback_to_file_read(self, tmp_path):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        test_file = str(tmp_path / 'fallback.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write('fallback text content')

        with patch('pdfplumber.open', side_effect=Exception('pdf error')):
            text = engine.parse_pdf(test_file)

        assert 'fallback text content' in text

    def test_parse_word_fallback_to_file_read(self, tmp_path):
        from utils.evolution_engine import EvolutionEngine

        engine = EvolutionEngine()
        test_file = str(tmp_path / 'fallback.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write('word fallback content')

        with patch('docx.Document', side_effect=Exception('docx error')):
            text = engine.parse_word(test_file)

        assert 'word fallback content' in text
