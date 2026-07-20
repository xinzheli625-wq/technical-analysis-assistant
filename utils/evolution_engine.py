"""Evolution engine - Skill进化引擎

链路：PDF/Word解析 -> Claude Code语义理解分段 -> 用户确认 -> 逐段DeepSeek提取 -> 规则索引库写入
"""

import json
import os
import hashlib
import re
from typing import Dict, List, Any, Optional
from datetime import datetime


class EvolutionEngine:
    """Skill进化引擎 - 从书籍/报告中提取规则并存入索引库"""

    def __init__(self, skills_dir: str = '.claude/skills/technical-analysis-core/references'):
        self.skills_dir = skills_dir
        self.processed_books: Dict[str, str] = {}
        self._load_book_registry()

    def _load_book_registry(self):
        registry_file = 'data/book_registry.json'
        if os.path.exists(registry_file):
            try:
                with open(registry_file, 'r', encoding='utf-8') as f:
                    self.processed_books = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.processed_books = {}

    def _save_book_registry(self):
        os.makedirs('data', exist_ok=True)
        with open('data/book_registry.json', 'w', encoding='utf-8') as f:
            json.dump(self.processed_books, f, ensure_ascii=False, indent=2)

    def _calculate_file_hash(self, file_path: str) -> str:
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def is_book_processed(self, file_path: str) -> bool:
        return self._calculate_file_hash(file_path) in self.processed_books

    # ========== 文本解析 ==========

    def parse_pdf(self, file_path: str) -> str:
        try:
            import pdfplumber
            segments = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        segments.append(text)
            return '\n'.join(segments)
        except Exception:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()

    def parse_word(self, file_path: str) -> str:
        try:
            from docx import Document
            doc = Document(file_path)
            return '\n'.join([p.text for p in doc.paragraphs])
        except Exception:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()

    def parse_pdf_ocr(self, file_path: str, page_start: int = 1,
                       page_end: Optional[int] = None,
                       dpi: int = 200) -> str:
        """OCR 解析扫描版 PDF（图片型 PDF）

        使用 RapidOCR（ONNX 轻量模型）进行本地 OCR，零 API 消耗。

        Args:
            file_path: PDF 文件路径
            page_start: 起始页码（从1开始）
            page_end: 结束页码（None 表示到最后一页）
            dpi: 渲染分辨率（默认200，越高越清晰但越慢）

        Returns:
            OCR 识别后的完整文本
        """
        import fitz  # pymupdf
        from rapidocr_onnxruntime import RapidOCR
        import tempfile
        import os

        print(f"[OCR] Parsing scanned PDF: {file_path}")
        print(f"   Page range: {page_start} - {page_end or 'end'}")
        print(f"   DPI: {dpi}")

        # 打开 PDF
        doc = fitz.open(file_path)
        total_pages = len(doc)

        if page_end is None or page_end > total_pages:
            page_end = total_pages

        if page_start < 1:
            page_start = 1

        print(f"   Total: {total_pages}, Processing: {page_end - page_start + 1} pages")

        # 初始化 OCR（首次加载模型约 1-2 秒）
        print("[OCR] Loading model...")
        ocr = RapidOCR()
        print("[OCR] Model ready")

        all_text = []
        temp_dir = tempfile.mkdtemp()

        for page_num in range(page_start - 1, page_end):
            # 渲染页面为图片
            page = doc[page_num]
            pix = page.get_pixmap(dpi=dpi)
            img_path = os.path.join(temp_dir, f"page_{page_num + 1}.png")
            pix.save(img_path)

            # OCR 识别
            result, _ = ocr(img_path)

            # 提取文字
            if result:
                page_text = '\n'.join([line[1] for line in result])
                all_text.append(page_text)

            # 删除临时图片
            os.remove(img_path)

            # 进度显示（每10页）
            if (page_num - page_start + 2) % 10 == 0 or page_num == page_end - 1:
                progress = page_num - page_start + 2
                print(f"   Progress: {progress}/{page_end - page_start + 1} pages")

        doc.close()
        os.rmdir(temp_dir)

        full_text = '\n\n'.join(all_text)
        print(f"[OCR] Complete, {len(full_text)} chars recognized")

        return full_text

    def is_scanned_pdf(self, file_path: str, sample_pages: int = 5) -> bool:
        """检测 PDF 是否为扫描版（图片型）

        策略：随机采样若干页，如果都没有文本层，则认为是扫描版。

        Returns:
            True: 扫描版（需要 OCR）
            False: 文本版（可直接提取）
        """
        try:
            import fitz
            doc = fitz.open(file_path)
            total = len(doc)

            # 采样：前3页 + 中间2页
            samples = [0, 1, 2]
            if total > 50:
                samples.append(total // 2)
            if total > 100:
                samples.append(total * 3 // 4)

            text_pages = 0
            for idx in samples:
                if idx < total:
                    text = doc[idx].get_text() or ''
                    if len(text.strip()) > 50:
                        text_pages += 1

            doc.close()

            # 如果采样页中 < 20% 有文本，认为是扫描版
            is_scanned = text_pages / len(samples) < 0.2
            print(f"   PDF 检测: 采样 {len(samples)} 页，{text_pages} 页有文本 → {'扫描版' if is_scanned else '文本版'}")
            return is_scanned

        except Exception as e:
            print(f"   PDF 检测失败: {e}，默认按文本版处理")
            return False

    # ========== 文本清洗（本地执行，零 API 消耗）==========

    def clean_text(self, text: str) -> str:
        """清洗文本：去页眉页脚、去重复空行、去页码等

        返回清洗后的全文，供 Claude Code 做语义分段。
        """
        lines = text.split('\n')
        cleaned_lines = []
        prev_line = None

        for line in lines:
            stripped = line.strip()

            # 跳过空行，但保留单空行（去连续多空行）
            if not stripped:
                if prev_line is not None and prev_line.strip():
                    cleaned_lines.append('')
                continue

            # 跳过常见页眉/页脚/页码
            # 纯数字（页码）
            if re.match(r'^\d+$', stripped):
                continue
            # "第 X 页" 格式
            if re.match(r'^[第\s]*\d+[\s]*[页\s]*$', stripped):
                continue
            # "Page X" 格式
            if re.match(r'^Page\s+\d+', stripped, re.IGNORECASE):
                continue

            # 跳过重复的相同行（常见于页眉重复）
            if prev_line and stripped == prev_line.strip():
                continue

            cleaned_lines.append(stripped)
            prev_line = line

        return '\n'.join(cleaned_lines)

    # ========== 分段接口（Claude Code 语义分段 + 用户确认）==========

    def create_segments(self, text: str, segments_config: List[Dict[str, Any]]) -> Dict[str, Any]:
        """根据 Claude Code + 用户确认的分段配置，创建分段地图

        Args:
            text: 清洗后的全文
            segments_config: 用户确认的分段配置，每项包含：
                {
                    'segment_id': int,
                    'title': '段标题（用户命名）',
                    'start_marker': '起始标记（原文中的一行，用于定位）',
                    'end_marker': '结束标记（原文中的一行，用于定位，可选）',
                    'note': '用户备注'
                }

        Returns:
            完整的分段地图
        """
        lines = text.split('\n')
        segments = []

        for config in segments_config:
            seg_id = config.get('segment_id', len(segments) + 1)
            start_marker = config.get('start_marker', '')
            end_marker = config.get('end_marker', '')

            # 定位起始行
            start_idx = 0
            if start_marker:
                for i, line in enumerate(lines):
                    if line.strip() == start_marker.strip():
                        start_idx = i
                        break

            # 定位结束行
            end_idx = len(lines)
            if end_marker:
                for i in range(start_idx + 1, len(lines)):
                    if lines[i].strip() == end_marker.strip():
                        end_idx = i
                        break
            else:
                # 没有结束标记：如果下一段有 start_marker，用它作为当前段的结束
                next_config = None
                for c in segments_config:
                    if c.get('segment_id') == seg_id + 1:
                        next_config = c
                        break
                if next_config and next_config.get('start_marker'):
                    next_start = next_config['start_marker']
                    for i in range(start_idx + 1, len(lines)):
                        if lines[i].strip() == next_start.strip():
                            end_idx = i
                            break

            seg_text = '\n'.join(lines[start_idx:end_idx]).strip()
            summary = seg_text[:200].replace('\n', ' ')

            segments.append({
                'segment_id': seg_id,
                'chapter_title': config.get('title', f'段{seg_id}'),
                'char_count': len(seg_text),
                'chapter_type': 'user_defined',
                'summary': summary + ('...' if len(seg_text) > 200 else ''),
                'start_marker': start_marker,
                'end_marker': end_marker if end_marker else (next_config.get('start_marker') if next_config else ''),
                'note': config.get('note', '')
            })

        return {
            'total_chars': len(text),
            'estimated_chapters': len(segments),
            'segments': segments
        }

    def get_segment_text(self, text: str, segment_id: int,
                         structure: Dict[str, Any]) -> str:
        """根据分段地图，提取指定段的完整原文"""
        if segment_id < 1 or segment_id > len(structure.get('segments', [])):
            return ""

        seg = structure['segments'][segment_id - 1]
        start_marker = seg.get('start_marker', '')
        end_marker = seg.get('end_marker', '')

        if not start_marker:
            return ""

        lines = text.split('\n')
        start_idx = None
        end_idx = len(lines)

        # 定位起始行
        for i, line in enumerate(lines):
            if line.strip() == start_marker.strip():
                start_idx = i
                break

        if start_idx is None:
            return ""

        # 定位结束行
        if end_marker:
            for i in range(start_idx + 1, len(lines)):
                if lines[i].strip() == end_marker.strip():
                    end_idx = i
                    break

        return '\n'.join(lines[start_idx:end_idx]).strip()

    # ========== 旧接口兼容（一次性整本提取）==========

    def update_skill_from_book(self, file_path: str, file_type: str = 'pdf') -> Dict[str, Any]:
        """旧接口：一次性整本提取（自动模式）"""
        if self.is_book_processed(file_path):
            return {'status': 'skipped', 'reason': 'Already processed', 'source': file_path}

        if file_type.lower() in ['pdf', '.pdf']:
            text = self.parse_pdf(file_path)
        elif file_type.lower() in ['docx', '.docx', 'word']:
            text = self.parse_word(file_path)
        else:
            return {'status': 'error', 'reason': f'Unsupported: {file_type}', 'source': file_path}

        from utils.llm_client import DeepSeekClient
        client = DeepSeekClient()

        llm_result = client.extract_knowledge_from_text(text, book_title=file_path)

        from utils.rule_index import RuleIndex
        rule_index = RuleIndex()

        added_rules = []
        for rule in llm_result.get('rules', []):
            rule = self._convert_to_methodology_format(rule)
            rule_id = rule_index.add_rule(rule, auto_activate=False)
            added_rules.append({
                'rule_id': rule_id,
                'name': rule.get('name'),
                'category': rule.get('rule_type', 'general'),
                'status': 'pending'
            })

        file_hash = self._calculate_file_hash(file_path)
        self.processed_books[file_hash] = datetime.now().isoformat()
        self._save_book_registry()

        return {
            'status': 'processed',
            'source': file_path,
            'rules_extracted': len(added_rules),
            'rules': added_rules,
            'pending_activation': [r['rule_id'] for r in added_rules],
            'summary': llm_result.get('summary', '')
        }

    def update_skill_from_natural_language(self, instruction: str) -> Dict[str, Any]:
        """自然语言文本提取（单条，无需分段）"""
        from utils.llm_client import DeepSeekClient
        client = DeepSeekClient()

        llm_result = client.parse_natural_language_instruction(instruction)

        from utils.rule_index import RuleIndex
        rule_index = RuleIndex()

        rule_data = {
            'category': llm_result.get('intent', 'general').replace('add_', '').replace('modify_', ''),
            'name': llm_result.get('rule_name', 'Unnamed'),
            'definition': llm_result.get('description', ''),
            'conditions': llm_result.get('conditions', []),
            'source': f'natural_language: {instruction[:100]}'
        }

        rule_id = rule_index.add_rule(rule_data, auto_activate=False)

        return {
            'status': 'pending_review',
            'instruction': instruction,
            'parsed_intent': llm_result,
            'rule_id': rule_id,
            'next_step': 'Call activate_rule(rule_id) to make it active, or review and modify first.'
        }

    def activate_rule(self, rule_id: str) -> Dict[str, Any]:
        """用户确认后激活规则"""
        from utils.rule_index import RuleIndex
        rule_index = RuleIndex()

        if rule_index.activate_rule(rule_id):
            from utils.skill_knowledge import get_skill_kb
            get_skill_kb().reload()
            return {
                'status': 'activated',
                'rule_id': rule_id,
                'message': 'Rule is now active and will be included in future analysis prompts.'
            }
        return {'status': 'error', 'message': f'Rule {rule_id} not found'}

    def _convert_to_methodology_format(self, rule: Dict) -> Dict:
        """将提取的规则转换为标准 Skill 教材格式

        确保所有必要字段都存在，包括新增加的 trigger 和 signal。
        """
        # 如果已经是新格式（有core_idea），直接补充缺失字段
        if 'core_idea' in rule or 'analysis_steps' in rule:
            # 补充 trigger 和 signal（如果缺失）
            if 'trigger' not in rule:
                rule['trigger'] = None
            if 'signal' not in rule:
                rule['signal'] = {'direction': 'neutral', 'strength': 0.5}
            return rule

        # 旧格式转换
        return {
            'category': rule.get('rule_type', rule.get('category', 'general')),
            'name': rule.get('name', 'Unnamed'),
            'type': 'methodology',
            'core_idea': rule.get('definition', ''),
            'analysis_steps': rule.get('conditions', []),
            'reference_data': rule.get('reference_data', {}),
            'win_rate_hint': rule.get('win_rate_hint', {}),
            'common_pitfalls': rule.get('common_pitfalls', []),
            'when_not_to_use': rule.get('when_not_to_use', []),
            'examples': rule.get('examples', []),
            'source': rule.get('source', ''),
            'applicable_regimes': rule.get('applicable_regimes', []),
            'trigger': rule.get('trigger', None),
            'signal': rule.get('signal', {'direction': 'neutral', 'strength': 0.5}),
        }

    def get_pending_rules(self) -> List[Dict]:
        """获取所有待审核的规则"""
        from utils.rule_index import RuleIndex
        rule_index = RuleIndex()
        return rule_index.get_rules(status='pending')

    def get_rule_stats(self) -> Dict[str, Any]:
        """获取规则库统计"""
        from utils.rule_index import RuleIndex
        rule_index = RuleIndex()
        return rule_index.get_stats()
