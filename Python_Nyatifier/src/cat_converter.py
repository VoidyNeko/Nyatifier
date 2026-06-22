"""猫猫语转换规则引擎"""

import re

# 句末语气词（仅 啊、啦、呢 — 呀/吧不替换，吗 全局替换）
TONE_PARTICLES = re.compile(r'[啊啦呢]$')
# 呀/吧结尾（仅用于多段文本中跳过段尾喵）
YA_BA_END = re.compile(r'[呀吧]$')
# 句末标点（含引号）
ENDING_PUNCTUATION = re.compile(r'[。！？!?…，,；;：:）\)】\]》〉"\'』」～~]+$')
# 断句标点 + 换行符
BREAK_SEPARATORS = re.compile(r'([，,；;。\n])')
# 句中已有喵
HAS_MEOW = re.compile(r'喵')
# 中文字符
CHINESE_CHAR = re.compile(r'[\u4e00-\u9fff]')


def _split_core_ending(text: str) -> tuple[str, str]:
    """分离核心文本和末尾标点"""
    match = ENDING_PUNCTUATION.search(text)
    if match:
        pos = match.start()
        return text[:pos], text[pos:]
    return text, ''


def _has_meow(text: str) -> bool:
    return bool(HAS_MEOW.search(text))


def _chinese_count(s: str) -> int:
    return len(CHINESE_CHAR.findall(s))


def _convert_sentence(text: str, in_multi: bool = False, full_mode: bool = True) -> str:
    """对单个子句执行猫猫语转换

    in_multi: 多段文本时为 True，控制 呀/吧 段尾喵抑制
    full_mode: True=猫模式（吗嘛啊啦呢），False=人模式（仅吗嘛）
    """
    text = text.strip()
    if not text:
        return text

    if _has_meow(text):
        return text

    core, ending = _split_core_ending(text)
    cn = _chinese_count(core)

    # 纯数字/英文（无中文）不处理
    if cn == 0:
        return core + ending

    # 啊/啦/呢 → 喵（仅猫模式）
    if full_mode and TONE_PARTICLES.search(core):
        core = TONE_PARTICLES.sub('喵', core)
        return core + ending

    # 段末是 呀/吧（多段模式下跳过段尾喵，单句则加喵）
    if YA_BA_END.search(core):
        if in_multi:
            return core + ending
        # 单句：加尾喵
        if ending:
            return core + '喵' + ending
        return core + '喵'

    # 冒号结尾不加喵
    if ending and ending.lstrip() and ending.lstrip()[0] in ('：', ':'):
        return core + ending

    # 有末尾标点，在标点前插入喵
    if ending:
        return core + '喵' + ending

    return core + '喵'


def convert_to_cat_speak(text: str, full_mode: bool = True) -> str:
    """
    猫猫语转换

    full_mode: True=猫模式（吗嘛啊啦呢），False=人模式（仅吗嘛）
    - 句尾、换行、标点前加喵
    - 呀/吧 不替换；多段中段尾不加喵，单句则加
    - 冒号结尾不加喵
    - 非中文不处理
    - 已有喵跳过
    - 末尾空行清除
    """
    text = text.strip()
    if not text:
        return text

    # 全局替换「吗」→「喵」
    text = text.replace('吗', '喵')
    # 全局替换「嘛」→「喵」，但「干嘛」不替换
    text = re.sub(r'(?<!干)嘛', '喵', text)

    parts = BREAK_SEPARATORS.split(text)

    if len(parts) <= 1:
        return _convert_sentence(text, in_multi=False, full_mode=full_mode).rstrip('\n')

    result = []
    i = 0
    while i < len(parts):
        segment = parts[i]
        sep = parts[i + 1] if i + 1 < len(parts) else ""

        segment = segment.strip()
        if not segment:
            result.append(sep)
            i += 2
            continue

        converted = _convert_sentence(segment, in_multi=True, full_mode=full_mode)
        result.append(converted)
        if sep:
            result.append(sep)
        i += 2

    return ''.join(result).rstrip('\n')
