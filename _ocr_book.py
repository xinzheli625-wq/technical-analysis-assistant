import os
from utils.evolution_engine import EvolutionEngine

engine = EvolutionEngine()
pdf_path = 'D:\\lxz\\金融市场技术分析（2010）.pdf'
output_path = 'data/金融市场技术分析_ocr.txt'
batch_size = 50
total_pages = 488

# Check for existing progress
start_page = 1
existing_text = ""
if os.path.exists(output_path):
    with open(output_path, 'r', encoding='utf-8') as f:
        existing_text = f.read()
    page_count = existing_text.count('--- Page ')
    if page_count > 0:
        start_page = page_count + 1
        print(f'Found progress: {page_count} pages done, resuming from page {start_page}')
    else:
        print('Output exists but no page markers, restarting from page 1')
        existing_text = ""

print(f'Starting OCR: {pdf_path}')
print(f'Total pages: {total_pages}, starting from page {start_page}')
print(f'Batch size: {batch_size} pages/batch')
print(f'DPI: 150')
print()

file_mode = 'a' if start_page > 1 and existing_text else 'w'

with open(output_path, file_mode, encoding='utf-8') as f:
    for batch_start in range(start_page, total_pages + 1, batch_size):
        batch_end = min(batch_start + batch_size - 1, total_pages)
        print(f'OCR pages {batch_start}-{batch_end}...', flush=True)

        try:
            text = engine.parse_pdf_ocr(
                pdf_path,
                page_start=batch_start,
                page_end=batch_end,
                dpi=150
            )

            f.write(f'=== Pages {batch_start}-{batch_end} ===\n')
            f.write(text)
            f.write('\n\n')
            f.flush()

            print(f'  Done {batch_end}/{total_pages} pages ({len(text)} chars)')

        except Exception as e:
            print(f'  Failed pages {batch_start}-{batch_end}: {e}')
            f.write(f'=== Pages {batch_start}-{batch_end} [OCR FAILED: {e}] ===\n\n')
            f.flush()

print()
final_size = os.path.getsize(output_path)
print(f'OCR Complete!')
print(f'Output: {output_path}')
print(f'Size: {final_size / 1024 / 1024:.1f} MB')
