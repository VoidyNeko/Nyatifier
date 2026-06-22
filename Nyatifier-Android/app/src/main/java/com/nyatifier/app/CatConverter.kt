package com.nyatifier.app

/**
 * 猫猫语转换规则引擎
 * 从 Python cat_converter.py 直译 — 对齐 2026-06-22
 */
object CatConverter {

    // 句末语气词（仅 啊、啦、呢 — 呀/吧不替换，吗/嘛 全局替换）
    private val TONE_PARTICLES = Regex("[啊啦呢]$")
    // 呀/吧结尾
    private val YA_BA_END = Regex("[呀吧]$")
    // 句末标点
    private val ENDING_PUNCTUATION = Regex("[。！？!?…，,；;：:）\\)】」』》〉\"\'～~]+$")
    // 断句标点 + 换行符（匹配组用来保留分隔符）
    private val BREAK_SEPARATORS = Regex("([，,；;。\\n])")
    // 句中已有喵
    private val HAS_MEOW = Regex("喵")
    // 中文字符
    private val CHINESE_CHAR = Regex("[\\u4e00-\\u9fff]")

    /**
     * 模拟 Python re.split 含匹配组的行为：分隔符也作为元素保留
     */
    private fun splitKeepSeparators(text: String, regex: Regex): List<String> {
        val result = mutableListOf<String>()
        var lastEnd = 0
        for (m in regex.findAll(text)) {
            result.add(text.substring(lastEnd, m.range.first))
            result.add(m.groupValues[1])  // 捕获组 = 分隔符本身
            lastEnd = m.range.last + 1
        }
        result.add(text.substring(lastEnd))
        return result
    }

    /** 分离核心文本和末尾标点 */
    private fun splitCoreEnding(text: String): Pair<String, String> {
        val match = ENDING_PUNCTUATION.find(text)
        return if (match != null) {
            val pos = match.range.first
            Pair(text.substring(0, pos), text.substring(pos))
        } else {
            Pair(text, "")
        }
    }

    private fun hasMeow(text: String): Boolean = HAS_MEOW.containsMatchIn(text)

    private fun chineseCount(s: String): Int = CHINESE_CHAR.findAll(s).count()

    /**
     * 对单个子句执行猫猫语转换
     */
    private fun convertSentence(text: String, inMulti: Boolean = false, fullMode: Boolean = true): String {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return trimmed

        if (hasMeow(trimmed)) return trimmed

        val (core, ending) = splitCoreEnding(trimmed)
        val cn = chineseCount(core)

        // 纯数字/英文不处理
        if (cn == 0) return core + ending

        // 啊/啦/呢 → 喵（仅猫模式）
        if (fullMode && TONE_PARTICLES.containsMatchIn(core)) {
            return TONE_PARTICLES.replace(core, "喵") + ending
        }

        // 呀/吧 段尾
        if (YA_BA_END.containsMatchIn(core)) {
            if (inMulti) return core + ending
            return if (ending.isNotEmpty()) core + "喵" + ending else core + "喵"
        }

        // 冒号结尾不加喵
        if (ending.isNotEmpty() && ending.trimStart().firstOrNull() in listOf('：', ':')) {
            return core + ending
        }

        // 有末尾标点 → 标点前插入喵
        if (ending.isNotEmpty()) return core + "喵" + ending

        return core + "喵"
    }

    /**
     * 猫猫语转换主入口
     */
    fun convertToCatSpeak(text: String, fullMode: Boolean = true): String {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return trimmed

        // 全局替换：吗→喵
        var result = trimmed.replace("吗", "喵")
        // 全局替换：嘛→喵（保留"干嘛"）
        result = result.replace(Regex("(?<!干)嘛"), "喵")

        val parts = splitKeepSeparators(result, BREAK_SEPARATORS)

        if (parts.size <= 1) {
            return convertSentence(result, inMulti = false, fullMode = fullMode)
                .trimEnd('\n')
        }

        val sb = StringBuilder()
        var i = 0
        while (i < parts.size) {
            val segment = parts[i]
            val sep = parts.getOrElse(i + 1) { "" }

            if (segment.isEmpty()) {
                sb.append(sep)
                i += 2
                continue
            }

            val converted = convertSentence(segment, inMulti = true, fullMode = fullMode)
            sb.append(converted)
            if (sep.isNotEmpty()) sb.append(sep)
            i += 2
        }

        return sb.toString().trimEnd('\n')
    }
}
