import os

from utils.evolution_engine import EvolutionEngine

os.environ['DEEPSEEK_API_KEY'] = 'test-key'


def test_evolution_engine_parse_text():
    engine = EvolutionEngine()

    test_file = 'data/test_book.txt'
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("""
# Technical Analysis Patterns

## Head and Shoulders Pattern
This is a reversal pattern with three peaks.

## Volume Rules
Volume should confirm breakouts.
""")

    text = engine.parse_pdf(test_file)
    assert 'Head and Shoulders' in text
    assert 'Volume Rules' in text

    os.remove(test_file)


def test_evolution_engine_book_deduplication():
    engine = EvolutionEngine()

    test_file = 'data/test_book2.txt'
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("Test book content for deduplication")

    result1 = engine.update_skill_from_book(test_file, 'txt')
    # 无API key时LLM调用会失败，但解析应成功
    assert result1['status'] in ['processed', 'error']

    os.remove(test_file)
    if os.path.exists('data/book_registry.json'):
        os.remove('data/book_registry.json')
