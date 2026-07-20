"""将OCR文本上传到飞书文档"""

import os
from utils.feishu_integration import FeishuIntegration

feishu = FeishuIntegration()

ocr_path = 'data/金融市场技术分析_ocr.txt'
title = '金融市场技术分析（2010）- OCR文字版'

print(f'Reading OCR file: {ocr_path}')
with open(ocr_path, 'r', encoding='utf-8') as f:
    full_text = f.read()

print(f'Total chars: {len(full_text)}')

# Split by batch markers
batches = []
current_batch = []
for line in full_text.split('\n'):
    if line.startswith('=== Pages '):
        if current_batch:
            batches.append('\n'.join(current_batch))
            current_batch = []
        current_batch.append(line)
    else:
        current_batch.append(line)
if current_batch:
    batches.append('\n'.join(current_batch))

print(f'Total batches: {len(batches)}')

# Create document with first batch as initial content
first_content = f"# {title}\n\n> 来源：《金融市场技术分析》（2010年版）\n> 总页数：488页\n> OCR生成时间：2026-05-26\n\n---\n\n{batches[0]}"

import tempfile
fd, abs_path = tempfile.mkstemp(suffix='.md', prefix='feishu_', dir='.')
with os.fdopen(fd, 'w', encoding='utf-8') as f:
    f.write(first_content)

temp_path = os.path.basename(abs_path)

try:
    result = feishu._run(
        f'lark-cli docs +create --title "{title}" '
        f'--folder-token {feishu.folder_token} '
        f'--markdown @{temp_path}'
    )
finally:
    if os.path.exists(temp_path):
        os.remove(temp_path)

if not result.get('ok'):
    print(f'Create doc failed: {result}')
    exit(1)

doc_token = result['data']['doc_id']
print(f'Doc created: {doc_token}')
print(f'URL: https://www.feishu.cn/docx/{doc_token}')

# Append remaining batches
for i, batch in enumerate(batches[1:], start=2):
    batch_md = f"\n\n{batch}"
    fd, abs_path = tempfile.mkstemp(suffix='.md', prefix='feishu_', dir='.')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(batch_md)
    temp_path = os.path.basename(abs_path)

    try:
        result = feishu._run(
            f'lark-cli docs +update --doc {doc_token} '
            f'--markdown @{temp_path} --mode append'
        )
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    if result.get('ok'):
        print(f'  Batch {i}/{len(batches)} appended')
    else:
        print(f'  Batch {i} failed: {result}')

print('\nUpload complete!')
print(f'URL: https://www.feishu.cn/docx/{doc_token}')

# Save doc token for later use
import json
cache_file = 'data/feishu_cache.json'
with open(cache_file, 'r', encoding='utf-8') as f:
    cache = json.load(f)
cache['book_ocr_doc_token'] = doc_token
with open(cache_file, 'w', encoding='utf-8') as f:
    json.dump(cache, f, ensure_ascii=False, indent=2)
print(f'Doc token saved to cache')
