"""控制台安全输出 - Windows GBK 控制台下打印 Unicode 符号不崩溃

print() 在 GBK 控制台打印 ⚠ ✓ ✗ ⊘ 等符号会抛 UnicodeEncodeError，
导致流水线在结果已算完的情况下崩溃。统一走 safe_print：
编码失败时按当前 stdout 编码替换不可表示字符后重试。
"""

import sys


def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        enc = (sys.stdout.encoding or 'utf-8')
        text = ' '.join(str(a) for a in args)
        print(text.encode(enc, errors='replace').decode(enc, errors='replace'), **kwargs)
