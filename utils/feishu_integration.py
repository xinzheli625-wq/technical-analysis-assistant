"""飞书集成模块 - 将分析产出同步到飞书文档

基于 lark-cli 命令行工具实现，支持：
- 创建/管理飞书文件夹
- 为每个股票创建分析文档
- 创建分析记录汇总文档（Markdown表格）
- 从飞书文档导入Skill

依赖：lark-cli 已配置并登录
"""

import json
import os
import re
import subprocess
from datetime import datetime
from typing import Any, Dict, Optional


class FeishuIntegration:
    """飞书集成 - 技术分析产出管理"""

    def __init__(self, folder_name: str = "技术分析助手"):
        self.folder_name = folder_name
        self.folder_token = None
        self.records_doc_token = None  # 汇总文档token
        self.stock_docs = {}  # 股票代码 -> 文档token 缓存
        self.doc_cache_dir = 'data/feishu_doc_cache'
        os.makedirs(self.doc_cache_dir, exist_ok=True)
        self._ensure_folder()
        self._ensure_records_doc()

    # ========== 底层命令封装 ==========

    def _run(self, cmd: str) -> Dict[str, Any]:
        """运行 lark-cli 命令，返回JSON结果"""
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                               encoding='utf-8', errors='replace')

        # lark-cli 的 JSON 输出通常在 stdout，但可能混杂 stderr 的日志
        # 优先解析 stdout，失败则尝试 stderr
        for output in [result.stdout, result.stderr]:
            if not output.strip():
                continue
            try:
                # 查找第一个 { 开头的JSON
                json_start = output.find('{')
                if json_start == -1:
                    continue
                # 尝试提取到匹配的 }
                json_str = self._extract_json(output, json_start)
                if json_str:
                    data = json.loads(json_str)
                    return data
            except json.JSONDecodeError:
                continue

        # 都失败了，返回原始输出
        combined = result.stdout + '\n' + result.stderr
        return {"ok": False, "error": combined}

    def _extract_json(self, text: str, start: int) -> Optional[str]:
        """从文本中提取完整JSON对象"""
        brace_count = 0
        in_string = False
        escape_next = False
        end = -1

        for i in range(start, len(text)):
            c = text[i]
            if escape_next:
                escape_next = False
                continue
            if c == '\\':
                escape_next = True
                continue
            if c == '"' and not in_string:
                in_string = True
                continue
            if c == '"' and in_string:
                in_string = False
                continue
            if not in_string:
                if c == '{':
                    brace_count += 1
                elif c == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break

        return text[start:end] if end > 0 else None

    def _run_jq(self, cmd: str, jq_filter: str) -> Any:
        """运行 lark-cli 命令，用jq过滤结果"""
        full_cmd = f'{cmd} -q \'{jq_filter}\''
        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True,
                               encoding='utf-8', errors='replace')
        output = result.stdout.strip()
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output

    # ========== 文件夹管理 ==========

    def _ensure_folder(self):
        """确保文件夹存在，获取 folder_token

        策略：
        1. 先检查本地缓存（复用已有文件夹）
        2. 尝试创建新文件夹
        3. 如果创建失败（已存在），从错误中读取或提示用户
        """
        cache_file = 'data/feishu_cache.json'

        # 步骤1：优先从缓存读取（复用现有文件夹）
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                if cache.get('folder_token'):
                    self.folder_token = cache['folder_token']
                    self.records_doc_token = cache.get('records_doc_token')
                    self.stock_docs = cache.get('stock_docs', {})
                    return
            except (json.JSONDecodeError, IOError):
                pass

        # 步骤2：尝试创建新文件夹
        result = self._run(f'lark-cli drive +create-folder --name "{self.folder_name}"')

        if result.get('ok'):
            data = result.get('data', {})
            if data.get('folder_token'):
                self.folder_token = data['folder_token']
                self._save_cache()
                return

        # 步骤3：创建失败，提示用户手动提供
        error_msg = result.get('error', str(result))
        raise RuntimeError(
            f'创建文件夹失败: {error_msg}\n'
            f'建议：在飞书中手动创建文件夹"{self.folder_name}"，\n'
            f'然后从URL中提取 folder_token 设置到 data/feishu_cache.json 中'
        )

    def _ensure_records_doc(self):
        """确保汇总文档存在"""
        # 检查本地缓存
        cache_file = 'data/feishu_cache.json'
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                self.records_doc_token = cache.get('records_doc_token')
                self.stock_docs = cache.get('stock_docs', {})
                if cache.get('folder_token'):
                    self.folder_token = cache['folder_token']
            except (json.JSONDecodeError, IOError):
                pass

    def _save_cache(self):
        """保存缓存到本地"""
        cache = {
            'folder_token': self.folder_token,
            'records_doc_token': self.records_doc_token,
            'stock_docs': self.stock_docs,
            'updated_at': datetime.now().isoformat()
        }
        os.makedirs('data', exist_ok=True)
        with open('data/feishu_cache.json', 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

    # ========== 文档操作 ==========

    def _write_temp_markdown(self, content: str) -> str:
        """将 Markdown 内容写入临时文件，返回相对路径

        lark-cli 要求文件路径是相对路径（在当前目录内）
        """
        import tempfile
        # 使用当前目录，文件名用相对路径
        fd, abs_path = tempfile.mkstemp(suffix='.md', prefix='feishu_', dir='.')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception:
            os.close(fd)
            raise
        # 返回相对路径（只返回文件名）
        return os.path.basename(abs_path)

    def create_stock_doc(self, symbol: str, content: str = "") -> str:
        """为股票创建分析文档，返回 doc_token"""
        if symbol in self.stock_docs:
            return self.stock_docs[symbol]

        title = f"{symbol} 技术分析"
        markdown = content or f"# {symbol} 技术分析\n\n> 创建于 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n---\n"

        # 写入临时文件，通过 @file 方式传入
        temp_path = self._write_temp_markdown(markdown)
        try:
            result = self._run(
                f'lark-cli docs +create --title "{title}" '
                f'--folder-token {self.folder_token} '
                f'--markdown @{temp_path}'
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        if not result.get('ok'):
            raise RuntimeError(f'创建文档失败: {result.get("error", "unknown")}')

        doc_token = result['data']['doc_id']
        self.stock_docs[symbol] = doc_token
        self._save_cache()

        return doc_token

    def append_to_stock_doc(self, symbol: str, content: str) -> bool:
        """追加分析内容到股票文档"""
        doc_token = self.stock_docs.get(symbol)
        if not doc_token:
            # 尝试创建新文档
            doc_token = self.create_stock_doc(symbol)

        # 写入临时文件
        temp_path = self._write_temp_markdown(content)
        try:
            result = self._run(
                f'lark-cli docs +update --doc {doc_token} '
                f'--markdown @{temp_path} --mode append'
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        return result.get('ok', False)

    def get_stock_doc_url(self, symbol: str) -> Optional[str]:
        """获取股票文档的URL"""
        doc_token = self.stock_docs.get(symbol)
        if doc_token:
            return f"https://www.feishu.cn/docx/{doc_token}"
        return None

    # ========== 汇总记录文档 ==========

    def _ensure_records_doc_created(self):
        """确保汇总记录文档已创建"""
        if self.records_doc_token:
            return

        title = "分析记录汇总"
        intro = (
            f"# {title}\n\n"
            f"> 格式：每行记录以 **标的 | 日期 | 分析结果 | 核心理由** 为标题\n\n"
            f"---\n\n"
        )

        temp_path = self._write_temp_markdown(intro)
        try:
            result = self._run(
                f'lark-cli docs +create --title "{title}" '
                f'--folder-token {self.folder_token} '
                f'--markdown @{temp_path}'
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        if result.get('ok'):
            self.records_doc_token = result['data']['doc_id']
            self._save_cache()
        else:
            raise RuntimeError(f'创建汇总文档失败: {result.get("error", "unknown")}')

    def add_record_to_summary(self, record: Dict[str, Any]):
        """添加分析记录到汇总文档（标题式格式）"""
        self._ensure_records_doc_created()

        # 标题式记录
        row = (
            f"\n\n## {record.get('symbol', 'UNKNOWN')} | {record.get('date', '')} | "
            f"{record.get('verdict', '-')} | {record.get('core_reason', '')[:80]}\n\n"
            f"- **记录ID**: `{record.get('record_id', 'N/A')}`\n"
            f"- **市场环境**: {record.get('market_regime', '-')}\n"
            f"- **验证状态**: {record.get('validation_status', '待验证')}\n"
            f"- **实际收益%**: {record.get('actual_return', '-')}\n"
            f"- **结果**: {record.get('outcome', '-')}\n"
            f"\n---\n"
        )

        temp_path = self._write_temp_markdown(row)
        try:
            result = self._run(
                f'lark-cli docs +update --doc {self.records_doc_token} '
                f'--markdown @{temp_path} --mode append'
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        return result.get('ok', False)

    def update_record_validation(self, record_id: str, updates: Dict[str, Any]):
        """更新汇总文档中的验证信息

        注意：飞书文档v1 API不支持精准替换某一行，
        这里采用重新生成整个表格的方式。
        对于大量数据，建议定期导出为CSV或Excel。
        """
        # 读取当前文档内容
        result = self._run(
            f'lark-cli docs +fetch --doc {self.records_doc_token} --format pretty'
        )
        # 由于v1 API的限制，这里只做追加说明
        # 实际项目中可以维护本地缓存，定期全量更新

        note = (
            f"\n\n> **验证更新** - 记录 `{record_id}`:\n"
            f"> - 实际收益: {updates.get('actual_return_pct', '-')} |\n"
            f"> - 结果: {updates.get('outcome', '-')} |\n"
            f"> - 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        )

        temp_path = self._write_temp_markdown(note)
        try:
            result = self._run(
                f'lark-cli docs +update --doc {self.records_doc_token} '
                f'--markdown @{temp_path} --mode append'
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        return result.get('ok', False)

    # ========== Skill 导入 ==========

    def read_doc_content(self, doc_url_or_token: str) -> str:
        """从飞书文档读取内容

        Args:
            doc_url_or_token: 飞书文档URL或token
                URL格式: https://xxx.feishu.cn/docx/<token>
        """
        # 从URL提取token
        token = doc_url_or_token
        if 'feishu.cn' in doc_url_or_token or 'larksuite.com' in doc_url_or_token:
            match = re.search(r'/(docx?|wiki)/([a-zA-Z0-9_]+)', doc_url_or_token)
            if match:
                token = match.group(2)

        result = self._run(
            f'lark-cli docs +fetch --doc {token} --format pretty'
        )

        if result.get('ok'):
            # pretty格式输出是纯文本内容
            # 尝试从stdout获取
            return result.get('data', '') or str(result)

        raise RuntimeError(f'读取文档失败: {result.get("error", "unknown")}')

    def upload_skill_from_feishu_doc(self, doc_url_or_token: str) -> Dict[str, Any]:
        """从飞书文档导入 Skill

        Args:
            doc_url_or_token: 飞书文档URL或token
        """
        print("📖 正在从飞书文档读取 Skill 内容...")
        content = self.read_doc_content(doc_url_or_token)

        # 使用 EvolutionEngine 提取 Skill
        from utils.evolution_engine import EvolutionEngine
        engine = EvolutionEngine()
        result = engine.update_skill_from_natural_language(content)

        if result.get('status') == 'pending_review':
            print(f"⏳ 提取完成，规则ID: {result.get('rule_id')}")
            print("   使用 assistant.activate_skill(id) 激活")

        return result

    # ========== 快捷方法 ==========

    def get_folder_url(self) -> str:
        """获取文件夹URL"""
        return f"https://my.feishu.cn/drive/folder/{self.folder_token}"

    def get_records_doc_url(self) -> Optional[str]:
        """获取汇总文档URL"""
        if self.records_doc_token:
            return f"https://www.feishu.cn/docx/{self.records_doc_token}"
        return None

    def list_stock_docs(self) -> Dict[str, str]:
        """列出所有股票文档"""
        return {symbol: f"https://www.feishu.cn/docx/{token}"
                for symbol, token in self.stock_docs.items()}

    # ========== 跟踪文档管理 ==========

    def get_or_create_tracking_doc(self, symbol: str) -> str:
        """获取或创建某股票的跟踪文档，返回 doc_token"""
        cache_key = f"tracking_{symbol}"
        if cache_key in self.stock_docs:
            return self.stock_docs[cache_key]

        title = f"{symbol} 跟踪日志"
        markdown = (
            f"# {symbol} 跟踪日志\n\n"
            f"> 创建于 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"> 本文档记录该股票分析后的每日跟踪更新\n\n"
            f"---\n"
        )

        temp_path = self._write_temp_markdown(markdown)
        try:
            result = self._run(
                f'lark-cli docs +create --title "{title}" '
                f'--folder-token {self.folder_token} '
                f'--markdown @{temp_path}'
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        if not result.get('ok'):
            raise RuntimeError(f'创建跟踪文档失败: {result.get("error", "unknown")}')

        doc_token = result['data']['doc_id']
        self.stock_docs[cache_key] = doc_token
        self._save_cache()

        return doc_token

    def append_to_doc(self, doc_token: str, content: str) -> bool:
        """追加内容到指定文档"""
        temp_path = self._write_temp_markdown(content)
        try:
            result = self._run(
                f'lark-cli docs +update --doc {doc_token} '
                f'--markdown @{temp_path} --mode append'
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        return result.get('ok', False)

    def get_tracking_doc_url(self, symbol: str) -> Optional[str]:
        """获取跟踪文档URL"""
        cache_key = f"tracking_{symbol}"
        token = self.stock_docs.get(cache_key)
        if token:
            return f"https://www.feishu.cn/docx/{token}"
        return None

    # ========== 文档本地缓存（用于重写文档，实现新内容放最前） ==========

    def _doc_cache_path(self, symbol: str) -> str:
        """获取文档缓存文件路径"""
        return os.path.join(self.doc_cache_dir, f'{symbol}.md')

    def save_doc_cache(self, symbol: str, content: str):
        """保存文档内容到本地缓存"""
        path = self._doc_cache_path(symbol)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    def load_doc_cache(self, symbol: str) -> Optional[str]:
        """从本地缓存读取文档内容"""
        path = self._doc_cache_path(symbol)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except (IOError, UnicodeDecodeError):
            return None

    def overwrite_doc(self, doc_token: str, content: str) -> bool:
        """用新内容覆盖整个文档（实现新内容放最前）

        注意：飞书文档v1 API不支持精准插入到中间位置，
        这里采用重新生成整个文档的方式。
        """
        temp_path = self._write_temp_markdown(content)
        try:
            result = self._run(
                f'lark-cli docs +update --doc {doc_token} '
                f'--markdown @{temp_path} --mode overwrite'
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        return result.get('ok', False)

    def prepend_to_tracking_section(self, symbol: str, tracking_content: str) -> bool:
        """在文档的'后续跟踪'部分前插入新内容

        实现逻辑：
        1. 读取本地缓存的完整文档内容
        2. 找到'## 后续跟踪'标题位置
        3. 将新记录插入到标题之后（最前面）
        4. 用 overwrite 模式重写整个文档
        5. 更新本地缓存

        Returns:
            是否成功
        """
        doc_token = self.stock_docs.get(symbol)
        if not doc_token:
            print(f"[WARN] 找不到 {symbol} 的文档token，无法更新跟踪")
            return False

        cached = self.load_doc_cache(symbol)
        if not cached:
            print(f"[WARN] 找不到 {symbol} 的本地文档缓存，尝试从飞书获取...")
            try:
                cached = self.read_doc_content(doc_token)
            except Exception:
                print("[WARN] 从飞书获取文档内容失败")
                return False

        # 找到 "## 后续跟踪" 标题
        marker = '## 后续跟踪'
        idx = cached.find(marker)
        if idx == -1:
            # 如果没有找到标记，在文档末尾添加
            print(f"[INFO] 文档中未找到'{marker}'标记，追加到末尾")
            cached += f"\n\n---\n\n{marker}\n\n{tracking_content}\n"
        else:
            # 在标记之后插入新内容
            after_marker = idx + len(marker)
            # 找到标记后的第一个空行或内容开始位置
            # 插入新记录到标记之后
            cached = (
                cached[:after_marker] + '\n\n' + tracking_content + '\n' +
                cached[after_marker:]
            )

        # 重写文档
        success = self.overwrite_doc(doc_token, cached)
        if success:
            self.save_doc_cache(symbol, cached)
            print(f"[OK] 已更新 {symbol} 文档，新跟踪记录已放到最前")
        else:
            print("[WARN] 覆盖文档失败，尝试用append模式")
            # 降级：用append模式追加到末尾
            self.append_to_stock_doc(symbol, '\n' + tracking_content)

        return success
